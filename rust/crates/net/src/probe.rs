//! Model discovery and tolerant model-id matching.
//!
//! Port of `windows/deepl_ofm/services/probe.py`: Ollama advertises models on
//! `/api/tags`, every OpenAI-compatible backend on `/v1/models` (the `/v1`
//! segment follows the same rule as the chat endpoint).

use reqwest::Client;
use serde_json::Value;

use ofm_config::{BackendConfig, BackendKind};

use crate::error::{http_error, ErrorKind, TranslationError};
use crate::wire::{auth_headers, ollama_tags_endpoint, openai_endpoint};

/// Timeout for a model listing; short so Settings stays responsive.
pub(crate) const PROBE_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(8);

/// Endpoint that advertises the models of `config`'s backend.
pub(crate) fn models_endpoint(base: &str, kind: BackendKind) -> String {
    match kind {
        BackendKind::Ollama => ollama_tags_endpoint(base),
        BackendKind::OpenAI => openai_endpoint(base, "models"),
    }
}

/// Ask `config`'s backend for its model ids.
///
/// Raises [`ErrorKind::Connection`], [`ErrorKind::InvalidUrl`],
/// [`ErrorKind::Unauthorized`], [`ErrorKind::RateLimit`],
/// [`ErrorKind::Server`], [`ErrorKind::Http`] or [`ErrorKind::Unexpected`],
/// like the Python `probe_models` (a missing model list yields an empty vector).
pub(crate) async fn probe_models(
    client: &Client,
    config: &BackendConfig,
) -> Result<Vec<String>, TranslationError> {
    let base = config.compatible_base();
    let url = models_endpoint(&base, config.kind);
    crate::translator::validate_url(&url, &base)?;

    let headers = auth_headers(config, &base)?;
    let response = client
        .get(&url)
        .headers(headers)
        .timeout(PROBE_TIMEOUT)
        .send()
        .await
        .map_err(|error| crate::translator::request_error(&error, &base))?;

    let status = response.status().as_u16();
    if !(200..300).contains(&status) {
        return Err(http_error(status, ""));
    }
    let body = response
        .text()
        .await
        .map_err(|error| crate::translator::request_error(&error, &base))?;
    let payload: Value = serde_json::from_str(&body)
        .map_err(|_| TranslationError::new(ErrorKind::Unexpected).with_detail("invalid JSON"))?;
    parse_models(config.kind, &payload)
}

/// Extract model ids from a `/api/tags` or `/v1/models` payload.
pub(crate) fn parse_models(
    kind: BackendKind,
    payload: &Value,
) -> Result<Vec<String>, TranslationError> {
    let Some(object) = payload.as_object() else {
        return Err(TranslationError::new(ErrorKind::Unexpected)
            .with_detail("unexpected model list payload"));
    };
    let entries = match kind {
        BackendKind::Ollama => object.get("models").and_then(Value::as_array),
        BackendKind::OpenAI => object.get("data").and_then(Value::as_array),
    };
    let Some(entries) = entries else {
        return Ok(Vec::new());
    };

    let mut models = Vec::with_capacity(entries.len());
    for entry in entries {
        let Some(entry) = entry.as_object() else {
            continue;
        };
        let name = match kind {
            BackendKind::Ollama => {
                non_empty_string(entry.get("name")).or_else(|| non_empty_string(entry.get("model")))
            }
            BackendKind::OpenAI => non_empty_string(entry.get("id")),
        };
        if let Some(name) = name {
            models.push(name.to_string());
        }
    }
    Ok(models)
}

/// A non-empty JSON string, or `None`.
fn non_empty_string(value: Option<&Value>) -> Option<&str> {
    value
        .and_then(Value::as_str)
        .filter(|text| !text.is_empty())
}

/// Whether `name` is present as an exact id, `name:tag` or `vendor/name`.
///
/// Port of `Probe.model(_:isListedIn:)`; the comparison is case-insensitive on
/// both sides.
pub fn model_listed(name: &str, models: &[String]) -> bool {
    if models.is_empty() {
        return false;
    }
    let target = name.to_lowercase();
    models.iter().any(|listed| {
        let value = listed.to_lowercase();
        value == target
            || value.starts_with(&format!("{target}:"))
            || value.ends_with(&format!("/{target}"))
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn strings(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| value.to_string()).collect()
    }

    #[test]
    fn parses_ollama_tags() {
        let payload = serde_json::json!({
            "models": [
                {"name": "hy-mt2:7b"},
                {"name": "llama3:latest"},
                {"model": "legacy-entry"},
                {"size": 123},
                {"name": ""},
            ]
        });
        let models = parse_models(BackendKind::Ollama, &payload).expect("models");
        assert_eq!(
            models,
            strings(&["hy-mt2:7b", "llama3:latest", "legacy-entry"])
        );
    }

    #[test]
    fn parses_openai_models() {
        let payload = serde_json::json!({"data": [{"id": "gpt-4o-mini"}, {"id": "local-7b"}]});
        let models = parse_models(BackendKind::OpenAI, &payload).expect("models");
        assert_eq!(models, strings(&["gpt-4o-mini", "local-7b"]));
    }

    #[test]
    fn missing_lists_are_empty_and_wrong_payloads_are_unexpected() {
        assert!(parse_models(BackendKind::Ollama, &serde_json::json!({}))
            .expect("empty")
            .is_empty());
        let error = parse_models(BackendKind::OpenAI, &serde_json::json!([1, 2]))
            .expect_err("not an object");
        assert_eq!(error.kind, ErrorKind::Unexpected);
    }

    #[test]
    fn model_listed_matches_exact_tag_and_vendor_forms() {
        assert!(model_listed("hy-mt2:7b", &strings(&["hy-mt2:7b"])));
        assert!(model_listed("hy-mt2:7b", &strings(&["HY-MT2:7B"])));
        assert!(model_listed("hy-mt2", &strings(&["hy-mt2:7b"])));
        assert!(model_listed("hy-mt2-7b", &strings(&["tencent/hy-mt2-7b"])));
        assert!(model_listed("gpt-oss", &strings(&["gpt-oss:120b-cloud"])));
        assert!(!model_listed("hy-mt2:7b", &[]));
        assert!(!model_listed("hy-mt2:7b", &strings(&["llama-3.3-70b"])));
        assert!(!model_listed(
            "hy-mt2",
            &strings(&["tencent/hy-mt2-7b-extra"])
        ));
    }
}
