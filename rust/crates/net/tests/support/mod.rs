//! Hand-written HTTP/1.1 server for the tests.
//!
//! No extra crates: a [`tokio::net::TcpListener`] accepts connections, parses
//! one request (request line, headers and a JSON body), records it and writes
//! the reply the handler asked for. Streaming replies are written piece by
//! piece with an optional gap so tests can split a frame — even a single
//! multi-byte UTF-8 character — across two reads of the response body.

#![allow(dead_code)]

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde_json::Value;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};

/// One request as the assertion helpers see it.
#[derive(Clone, Debug)]
pub struct RecordedRequest {
    /// HTTP method.
    pub method: String,
    /// Request path, including the query string.
    pub path: String,
    /// Lower-cased header names.
    pub headers: HashMap<String, String>,
    /// Parsed JSON body (`Value::Null` when the body is not JSON).
    pub body: Value,
    /// Raw body text.
    pub raw_body: String,
}

impl RecordedRequest {
    /// `messages[0].content` of a chat request.
    pub fn content(&self) -> &str {
        self.body["messages"][0]["content"].as_str().unwrap_or("")
    }

    /// `model` of a chat request.
    pub fn model(&self) -> &str {
        self.body["model"].as_str().unwrap_or("")
    }

    /// Value of a header, matched case-insensitively.
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers.get(&name.to_lowercase()).map(String::as_str)
    }
}

/// What the server writes back.
#[derive(Clone, Debug)]
pub struct Reply {
    status: u16,
    headers: Vec<(String, String)>,
    writes: Vec<Vec<u8>>,
    gap: Duration,
    content_length: bool,
}

impl Reply {
    /// An empty response with the given status.
    pub fn status(status: u16) -> Self {
        Self {
            status,
            headers: Vec::new(),
            writes: Vec::new(),
            gap: Duration::ZERO,
            content_length: true,
        }
    }

    /// A JSON response.
    pub fn json(status: u16, value: &Value) -> Self {
        let mut reply = Self::status(status);
        reply
            .headers
            .push(("Content-Type".to_string(), "application/json".to_string()));
        reply.writes.push(value.to_string().into_bytes());
        reply
    }

    /// A 200 response with a fixed body and `Content-Length`.
    pub fn body(body: Vec<u8>) -> Self {
        Self {
            status: 200,
            headers: Vec::new(),
            writes: vec![body],
            gap: Duration::ZERO,
            content_length: true,
        }
    }

    /// A streaming response; every write is flushed separately.
    pub fn stream(writes: Vec<Vec<u8>>) -> Self {
        Self {
            status: 200,
            headers: Vec::new(),
            writes,
            gap: Duration::ZERO,
            content_length: false,
        }
    }

    /// A streaming response with a pause between the writes.
    pub fn slow_stream(writes: Vec<Vec<u8>>, gap: Duration) -> Self {
        Self {
            gap,
            ..Self::stream(writes)
        }
    }

    /// Add a header to the response.
    pub fn header(mut self, name: &str, value: &str) -> Self {
        self.headers.push((name.to_string(), value.to_string()));
        self
    }
}

type Handler = Arc<dyn Fn(&RecordedRequest) -> Reply + Send + Sync>;

/// A running fake server; it is aborted when dropped.
pub struct FakeServer {
    address: SocketAddr,
    requests: Arc<Mutex<Vec<RecordedRequest>>>,
    task: tokio::task::JoinHandle<()>,
}

impl FakeServer {
    /// Start a server that answers with `handler`.
    pub async fn start<F>(handler: F) -> Self
    where
        F: Fn(&RecordedRequest) -> Reply + Send + Sync + 'static,
    {
        let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
        let address = listener.local_addr().expect("local addr");
        let requests: Arc<Mutex<Vec<RecordedRequest>>> = Arc::new(Mutex::new(Vec::new()));
        let handler: Handler = Arc::new(handler);
        let requests_for_task = Arc::clone(&requests);
        let task = tokio::spawn(async move {
            loop {
                let Ok((mut socket, _)) = listener.accept().await else {
                    break;
                };
                let handler = Arc::clone(&handler);
                let requests = Arc::clone(&requests_for_task);
                tokio::spawn(async move {
                    let _ = serve(&mut socket, &handler, &requests).await;
                });
            }
        });
        Self {
            address,
            requests,
            task,
        }
    }

    /// Address the server listens on.
    pub fn address(&self) -> SocketAddr {
        self.address
    }

    /// Base URL for `BackendConfig::base_url`.
    pub fn url(&self) -> String {
        format!("http://{}", self.address)
    }

    /// Requests received so far, in arrival order.
    pub fn requests(&self) -> Vec<RecordedRequest> {
        self.requests.lock().expect("request log").clone()
    }

    /// Number of requests received so far.
    pub fn request_count(&self) -> usize {
        self.requests.lock().expect("request log").len()
    }
}

impl Drop for FakeServer {
    fn drop(&mut self) {
        self.task.abort();
    }
}

async fn serve(
    socket: &mut TcpStream,
    handler: &Handler,
    requests: &Mutex<Vec<RecordedRequest>>,
) -> std::io::Result<()> {
    let Some(request) = read_request(socket).await? else {
        return Ok(());
    };
    requests.lock().expect("request log").push(request.clone());
    write_reply(socket, handler(&request)).await
}

async fn read_request(socket: &mut TcpStream) -> std::io::Result<Option<RecordedRequest>> {
    let mut buffer = Vec::new();
    let mut chunk = [0u8; 4096];
    let header_end;
    loop {
        let read = socket.read(&mut chunk).await?;
        if read == 0 {
            return Ok(None);
        }
        buffer.extend_from_slice(&chunk[..read]);
        if let Some(position) = find_bytes(&buffer, b"\r\n\r\n") {
            header_end = position + 4;
            break;
        }
        if buffer.len() > 1 << 20 {
            return Ok(None);
        }
    }

    let head = String::from_utf8_lossy(&buffer[..header_end]).into_owned();
    let mut lines = head.split("\r\n");
    let request_line = lines.next().unwrap_or("");
    let mut parts = request_line.split_whitespace();
    let method = parts.next().unwrap_or("").to_string();
    let path = parts.next().unwrap_or("").to_string();
    let mut headers = HashMap::new();
    for line in lines {
        if let Some((name, value)) = line.split_once(':') {
            headers.insert(name.trim().to_lowercase(), value.trim().to_string());
        }
    }

    let length: usize = headers
        .get("content-length")
        .and_then(|value| value.parse().ok())
        .unwrap_or(0);
    let mut body = buffer[header_end..].to_vec();
    while body.len() < length {
        let read = socket.read(&mut chunk).await?;
        if read == 0 {
            break;
        }
        body.extend_from_slice(&chunk[..read]);
    }
    let raw_body = String::from_utf8_lossy(&body).into_owned();
    let body = serde_json::from_str(&raw_body).unwrap_or(Value::Null);

    Ok(Some(RecordedRequest {
        method,
        path,
        headers,
        body,
        raw_body,
    }))
}

async fn write_reply(socket: &mut TcpStream, reply: Reply) -> std::io::Result<()> {
    let length: usize = reply.writes.iter().map(Vec::len).sum();
    let mut head = format!(
        "HTTP/1.1 {} {}\r\nConnection: close\r\n",
        reply.status,
        reason(reply.status)
    );
    if reply.content_length {
        head.push_str(&format!("Content-Length: {length}\r\n"));
    }
    for (name, value) in &reply.headers {
        head.push_str(&format!("{name}: {value}\r\n"));
    }
    head.push_str("\r\n");
    socket.write_all(head.as_bytes()).await?;

    for (index, write) in reply.writes.iter().enumerate() {
        if index > 0 && !reply.gap.is_zero() {
            tokio::time::sleep(reply.gap).await;
        }
        if socket.write_all(write).await.is_err() {
            return Ok(());
        }
        let _ = socket.flush().await;
    }
    let _ = socket.shutdown().await;
    Ok(())
}

fn reason(status: u16) -> &'static str {
    match status {
        200 => "OK",
        201 => "Created",
        400 => "Bad Request",
        401 => "Unauthorized",
        403 => "Forbidden",
        404 => "Not Found",
        422 => "Unprocessable Entity",
        429 => "Too Many Requests",
        500 => "Internal Server Error",
        502 => "Bad Gateway",
        503 => "Service Unavailable",
        _ => "Error",
    }
}

/// Position of `needle` inside `haystack` (plain byte search).
pub fn find_bytes(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    if needle.is_empty() || haystack.len() < needle.len() {
        return None;
    }
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

// ---------------------------------------------------------------- fixtures

/// One Ollama NDJSON content frame.
pub fn ollama_frame(content: &str) -> Vec<u8> {
    let value = serde_json::json!({"message": {"content": content}, "done": false});
    format!("{value}\n").into_bytes()
}

/// The Ollama terminal frame, with server-side generation statistics.
pub fn ollama_done(tokens: u64, duration_ns: u64) -> Vec<u8> {
    let value = serde_json::json!({
        "done": true,
        "done_reason": "stop",
        "eval_count": tokens,
        "eval_duration": duration_ns,
    });
    format!("{value}\n").into_bytes()
}

/// An Ollama stream from `pieces`, closed by a "done" frame.
pub fn ollama_stream(pieces: &[&str]) -> Vec<Vec<u8>> {
    let mut writes: Vec<Vec<u8>> = pieces.iter().map(|piece| ollama_frame(piece)).collect();
    writes.push(ollama_done(pieces.len().max(1) as u64, 500_000_000));
    writes
}

/// One OpenAI SSE content frame (followed by the blank line).
pub fn sse_frame(content: &str) -> Vec<u8> {
    let value = serde_json::json!({
        "choices": [{"delta": {"content": content}, "finish_reason": null}],
    });
    format!("data: {value}\n\n").into_bytes()
}

/// The OpenAI terminal frames (`finish_reason: stop` and `[DONE]`).
pub fn sse_done() -> Vec<u8> {
    let value = serde_json::json!({"choices": [{"delta": {}, "finish_reason": "stop"}]});
    format!("data: {value}\n\ndata: [DONE]\n\n").into_bytes()
}

/// An OpenAI SSE stream from `pieces`, closed by the terminal frames.
pub fn sse_stream(pieces: &[&str]) -> Vec<Vec<u8>> {
    let mut writes: Vec<Vec<u8>> = pieces.iter().map(|piece| sse_frame(piece)).collect();
    writes.push(sse_done());
    writes
}
