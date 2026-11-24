"""A tiny local HTTP server that speaks the Ollama and OpenAI streaming protocols.

Used by the end-to-end tests so the whole pipeline runs over real sockets:
chunker → prompt → HTTP stream → byte budget → sanitizer → compose → controller.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # a stream ends when the connection closes

    requests: list[dict] = []

    def log_message(self, *_args) -> None:
        return

    # --------------------------------------------------------------- helpers
    def _json(self, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path.endswith("/api/tags"):
            self._json({"models": [{"name": "hy-mt2:7b"}, {"name": "qwen3:8b"}]})
            return
        if self.path.endswith("/v1/models") or self.path.endswith("/models"):
            self._json({"data": [{"id": "hy-mt2:7b"}, {"id": "gpt-oss-120b"}]})
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        type(self).requests.append({"path": self.path, "body": payload})

        if self.path.endswith("/api/chat"):
            self._ollama()
            return
        if self.path.endswith("/chat/completions"):
            self._openai()
            return
        self.send_error(404)

    # -------------------------------------------------------------- protocol
    def _answer(self) -> str:
        return f"Antwort {len(type(self).requests)}"

    def _ollama(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        text = self._answer()
        for piece in (text[:4], text[4:]):
            frame = {
                "model": "hy-mt2:7b",
                "message": {"role": "assistant", "content": piece},
                "done": False,
            }
            self.wfile.write((json.dumps(frame) + "\n").encode())
            self.wfile.flush()
            time.sleep(0.005)
        done = {
            "model": "hy-mt2:7b",
            "message": {"content": ""},
            "done": True,
            "eval_count": 12,
            "eval_duration": 30_000_000,
        }
        self.wfile.write((json.dumps(done) + "\n").encode())

    def _openai(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        text = self._answer()
        for piece in (text[:5], text[5:]):
            frame = {"id": "x", "choices": [{"delta": {"content": piece}, "index": 0}]}
            self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.005)
        self.wfile.write(b"data: [DONE]\n\n")


class FakeProvider:
    """Context manager wrapping the server in a background thread."""

    def __init__(self) -> None:
        FakeProviderHandler.requests = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProviderHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def requests(self) -> list[dict]:
        return FakeProviderHandler.requests

    def __enter__(self) -> "FakeProvider":
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._server.shutdown()
        self._server.server_close()
