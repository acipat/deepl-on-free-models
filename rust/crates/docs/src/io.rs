//! Small shared helpers: cancellation, paragraph translation and atomic writes.

use std::io::Write;
use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};

use crate::error::{write_failed, DocumentError, DocumentErrorKind};

/// Return [`DocumentErrorKind::Cancelled`] when the flag is set.
pub(crate) fn check_cancel(cancel: Option<&AtomicBool>) -> Result<(), DocumentError> {
    if cancel.is_some_and(|flag| flag.load(Ordering::Relaxed)) {
        return Err(DocumentError::simple(DocumentErrorKind::Cancelled));
    }
    Ok(())
}

/// Translate every paragraph, leaving whitespace-only ones untouched.
///
/// Progress counts only the paragraphs that are actually sent to the model, so
/// "X of Y" matches what the user sees (blank paragraphs are not translation
/// units). The cancellation flag is checked before every paragraph.
pub(crate) fn translate_paragraphs(
    paragraphs: &[String],
    translate: &mut dyn FnMut(&str) -> Result<String, String>,
    on_progress: Option<&dyn Fn(usize, usize)>,
    cancel: Option<&AtomicBool>,
) -> Result<Vec<String>, DocumentError> {
    translate_paragraphs_inner(paragraphs, translate, on_progress, cancel, false)
}

/// Like [`translate_paragraphs`], but keeps the paragraph's leading and
/// trailing spaces/tabs out of the translation callable.
///
/// DOCX runs often end with a meaningful space ("Hello " + a field); a model
/// round-trip trims it, which would glue words together. The edges are layout
/// and are re-attached verbatim.
pub(crate) fn translate_paragraphs_preserving_edges(
    paragraphs: &[String],
    translate: &mut dyn FnMut(&str) -> Result<String, String>,
    on_progress: Option<&dyn Fn(usize, usize)>,
    cancel: Option<&AtomicBool>,
) -> Result<Vec<String>, DocumentError> {
    translate_paragraphs_inner(paragraphs, translate, on_progress, cancel, true)
}

fn translate_paragraphs_inner(
    paragraphs: &[String],
    translate: &mut dyn FnMut(&str) -> Result<String, String>,
    on_progress: Option<&dyn Fn(usize, usize)>,
    cancel: Option<&AtomicBool>,
    preserve_edges: bool,
) -> Result<Vec<String>, DocumentError> {
    let total = paragraphs
        .iter()
        .filter(|paragraph| !paragraph.trim().is_empty())
        .count();
    let mut translated = Vec::with_capacity(paragraphs.len());
    let mut completed = 0usize;
    for paragraph in paragraphs {
        check_cancel(cancel)?;
        if paragraph.trim().is_empty() {
            translated.push(paragraph.clone());
            continue;
        }
        let (leading, body, trailing) = if preserve_edges {
            split_edges(paragraph)
        } else {
            ("", paragraph.as_str(), "")
        };
        let text = translate(body)
            .map_err(|detail| DocumentError::new(DocumentErrorKind::WriteFailed, detail))?;
        if preserve_edges {
            translated.push(format!("{leading}{text}{trailing}"));
        } else {
            translated.push(text);
        }
        completed += 1;
        if let Some(progress) = on_progress {
            progress(completed, total);
        }
    }
    Ok(translated)
}

fn split_edges(paragraph: &str) -> (&str, &str, &str) {
    let is_space = |character: char| character == ' ' || character == '\t';
    let without_leading = paragraph.trim_start_matches(is_space);
    let leading = &paragraph[..paragraph.len() - without_leading.len()];
    let body = without_leading.trim_end_matches(is_space);
    let trailing = &without_leading[body.len()..];
    (leading, body, trailing)
}

static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Write `data` to `path` through a temporary sibling and a rename.
///
/// A failed write never truncates or replaces an existing file, matching
/// `_write_bytes` in the Python port.
pub(crate) fn write_atomic(path: &Path, data: &[u8]) -> Result<(), DocumentError> {
    let parent = if path.parent().is_some_and(|dir| !dir.as_os_str().is_empty()) {
        path.parent().unwrap_or(Path::new("."))
    } else {
        Path::new(".")
    };
    let name = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_else(|| "output".to_string());

    let mut temporary = None;
    for _ in 0..8 {
        let counter = TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);
        let candidate = parent.join(format!(
            ".deepl-ofm-{}-{}-{counter}.tmp",
            std::process::id(),
            name
        ));
        match std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&candidate)
        {
            Ok(mut file) => {
                let result = file
                    .write_all(data)
                    .and_then(|()| file.sync_all())
                    .and_then(|()| std::fs::rename(&candidate, path));
                drop(file);
                if let Err(error) = result {
                    let _ = std::fs::remove_file(&candidate);
                    return Err(write_failed(error.to_string()));
                }
                temporary = Some(candidate);
                break;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(write_failed(error.to_string())),
        }
    }
    if temporary.is_none() {
        return Err(write_failed("could not create a temporary file"));
    }
    Ok(())
}
