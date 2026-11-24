//! Text decoding for the Windows encodings found in real `.txt`/`.md` files.
//!
//! Detection order is the one from the Python port: a byte-order mark first,
//! then strict UTF-8, then a cp1251/cp1252 plausibility contest. Output is
//! always a Rust `String` (written back as UTF-8).

use encoding_rs::{MACINTOSH, WINDOWS_1251, WINDOWS_1252};
use ofm_i18n::{current_language, AppLanguage};

/// Byte-order marks, checked before any heuristic decoding.
///
/// UTF-32 comes before UTF-16 because the little-endian UTF-32 BOM starts with
/// the UTF-16 BOM.
const BOMS: &[(&[u8], Bom)] = &[
    (b"\xef\xbb\xbf", Bom::Utf8),
    (b"\xff\xfe\x00\x00", Bom::Utf32Le),
    (b"\x00\x00\xfe\xff", Bom::Utf32Be),
    (b"\xff\xfe", Bom::Utf16Le),
    (b"\xfe\xff", Bom::Utf16Be),
];

#[derive(Clone, Copy)]
enum Bom {
    Utf8,
    Utf16Le,
    Utf16Be,
    Utf32Le,
    Utf32Be,
}

/// Decode a text file with BOM, UTF-8 and legacy-Windows detection.
pub(crate) fn decode_text(data: &[u8]) -> String {
    for (bom, kind) in BOMS {
        if let Some(rest) = data.strip_prefix(*bom) {
            if let Some(text) = decode_with(*kind, rest) {
                return text;
            }
            // Python breaks out of the BOM loop here and tries plain UTF-8
            // (which keeps the BOM as U+FEFF) before falling back to legacy.
            break;
        }
    }
    if let Ok(text) = std::str::from_utf8(data) {
        return text.to_string();
    }
    decode_legacy(data)
}

fn decode_with(kind: Bom, data: &[u8]) -> Option<String> {
    match kind {
        Bom::Utf8 => std::str::from_utf8(data).ok().map(str::to_string),
        Bom::Utf16Le => decode_utf16(data, true),
        Bom::Utf16Be => decode_utf16(data, false),
        Bom::Utf32Le => decode_utf32(data, true),
        Bom::Utf32Be => decode_utf32(data, false),
    }
}

fn decode_utf16(data: &[u8], little_endian: bool) -> Option<String> {
    if data.len() % 2 != 0 {
        return None;
    }
    let units: Vec<u16> = data
        .chunks_exact(2)
        .map(|pair| {
            if little_endian {
                u16::from_le_bytes([pair[0], pair[1]])
            } else {
                u16::from_be_bytes([pair[0], pair[1]])
            }
        })
        .collect();
    String::from_utf16(&units).ok()
}

fn decode_utf32(data: &[u8], little_endian: bool) -> Option<String> {
    if data.len() % 4 != 0 {
        return None;
    }
    let mut text = String::with_capacity(data.len() / 4);
    for chunk in data.chunks_exact(4) {
        let code = if little_endian {
            u32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]])
        } else {
            u32::from_be_bytes([chunk[0], chunk[1], chunk[2], chunk[3]])
        };
        text.push(char::from_u32(code)?);
    }
    Some(text)
}

/// Decode a Windows text file without a byte-order mark.
///
/// Notepad on an older Russian or Ukrainian installation writes cp1251, a
/// Western one writes cp1252. Both are scored and the more plausible result
/// wins; the interface language only breaks an exact tie.
fn decode_legacy(data: &[u8]) -> String {
    let cyrillic_first = matches!(current_language(), AppLanguage::Uk | AppLanguage::Ru);
    let order = if cyrillic_first {
        [WINDOWS_1251, WINDOWS_1252]
    } else {
        [WINDOWS_1252, WINDOWS_1251]
    };
    let mut best: Option<(String, f64)> = None;
    for encoding in order {
        let (text, _, _) = encoding.decode(data);
        let score = plausibility(&text);
        if best
            .as_ref()
            .is_none_or(|(_, best_score)| score > *best_score)
        {
            best = Some((text.into_owned(), score));
        }
    }
    match best {
        Some((text, _)) if !text.is_empty() => text,
        _ => String::from_utf8_lossy(data).into_owned(),
    }
}

/// Score a legacy decoding; higher means "looks like real prose".
///
/// cp1251 and cp1252 both accept almost every byte sequence, so the choice
/// cannot be made from exceptions alone. Two signals separate them reliably:
/// a mis-decoded Cyrillic file turns into a run of accented Latin-1 letters
/// (`ïðèâåò`), and the wrong code page mixes Cyrillic and Latin letters inside
/// single words (`GrьЯe`).
pub(crate) fn plausibility(text: &str) -> f64 {
    let words: Vec<&str> = text.split_whitespace().collect();
    let letters: Vec<char> = text
        .chars()
        .filter(|character| character.is_alphabetic())
        .collect();
    if letters.is_empty() || words.is_empty() {
        return 0.0;
    }
    let total = letters.len() as f64;
    let accented = letters
        .iter()
        .filter(|character| ('\u{c0}'..='\u{ff}').contains(character))
        .count() as f64;
    let cyrillic = letters
        .iter()
        .filter(|character| ('\u{400}'..='\u{4ff}').contains(character))
        .count();
    let mut mixed = 0usize;
    for word in &words {
        let has_latin = word
            .chars()
            .any(|character| character.to_ascii_lowercase().is_ascii_lowercase());
        let has_cyrillic = word
            .chars()
            .any(|character| ('\u{400}'..='\u{4ff}').contains(&character));
        if has_latin && has_cyrillic {
            mixed += 1;
        }
    }
    let base = if cyrillic > 0 { 1.0 } else { 0.0 };
    base - 2.5 * (accented / total) - 3.0 * (mixed as f64 / words.len() as f64)
}

/// Decode a single win-ansi byte (used by the PDF reader for simple fonts).
pub(crate) fn win_ansi(byte: u8) -> Option<char> {
    let input = [byte];
    let (text, _, had_errors) = WINDOWS_1252.decode(&input);
    if had_errors {
        None
    } else {
        text.chars().next()
    }
}

/// Decode a single MacRoman byte (used by the PDF reader for simple fonts).
pub(crate) fn mac_roman(byte: u8) -> Option<char> {
    let input = [byte];
    let (text, _, had_errors) = MACINTOSH.decode(&input);
    if had_errors {
        None
    } else {
        text.chars().next()
    }
}

/// Encode text as Windows-1252 bytes, or `None` when a character is outside it.
pub(crate) fn encode_win_ansi(text: &str) -> Option<Vec<u8>> {
    let (bytes, _, had_errors) = WINDOWS_1252.encode(text);
    if had_errors {
        None
    } else {
        Some(bytes.into_owned())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plausibility_prefers_cyrillic_over_accented_latin1() {
        let real_cp1251 = "Привет, мир! Это проверка.";
        let misread = WINDOWS_1252.decode(real_cp1251.as_bytes()).0.into_owned();
        // The cp1252 reading of cp1251 bytes is a run of accented letters.
        assert!(misread
            .chars()
            .any(|character| ('\u{c0}'..='\u{ff}').contains(&character)));
        let correct = plausibility("Привет, мир! Это проверка.");
        let wrong = plausibility(&misread);
        assert!(correct > wrong, "correct={correct} wrong={wrong}");
    }

    #[test]
    fn plausibility_penalises_words_mixing_scripts() {
        assert!(plausibility("Привет, мир!") > plausibility("GrьЯe aus Mюnchen."));
    }

    #[test]
    fn utf16_and_utf32_boms_use_the_declared_byte_order() {
        let utf16be: Vec<u8> = std::iter::once(0xfe)
            .chain(std::iter::once(0xff))
            .chain("Привіт!".encode_utf16().flat_map(u16::to_be_bytes))
            .collect();
        assert_eq!(decode_text(&utf16be), "Привіт!");

        let utf32le: Vec<u8> = [0xff, 0xfe, 0x00, 0x00]
            .into_iter()
            .chain(
                "Привіт!"
                    .chars()
                    .flat_map(|character| (character as u32).to_le_bytes()),
            )
            .collect();
        assert_eq!(decode_text(&utf32le), "Привіт!");
    }

    #[test]
    fn ascii_and_utf8_do_not_need_the_legacy_contest() {
        assert_eq!(
            decode_text(b"Plain text, no accents."),
            "Plain text, no accents."
        );
        assert_eq!(decode_text("Привіт!".as_bytes()), "Привіт!");
    }
}
