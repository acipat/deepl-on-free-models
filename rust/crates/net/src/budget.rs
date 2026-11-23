//! Byte-capped streaming accumulator with cross-chunk marker detection.
//!
//! Port of `_OutputBudget` at the end of `translation.py` (itself a port of
//! `TranslationOutput` in `TranslationService.swift`). A chat-template marker
//! (`hy-assistant`, `hy_end`, `<|`, …) ends generation early; a marker that
//! starts beyond the byte cap proves the model finished, so the tail is
//! dropped without flagging an overflow.

/// Chat-template markers that mean "the model started answering as the next
/// role" and therefore end the translation.
const MARKERS: [&[u8]; 7] = [
    b"hy-assistant",
    b"hy-user",
    b"hy_end",
    "<\u{FF5C}".as_bytes(),
    b"<|",
    b"</|",
    "\u{FF5C}hy".as_bytes(),
];

/// Length of the longest marker.
const fn longest_marker() -> usize {
    let mut index = 0;
    let mut longest = 0;
    while index < MARKERS.len() {
        let length = MARKERS[index].len();
        if length > longest {
            longest = length;
        }
        index += 1;
    }
    longest
}

/// One byte less than the longest marker: how much of the previous piece has
/// to be re-examined together with the next one so a marker split across two
/// stream chunks is still found.
const OVERLAP: usize = longest_marker() - 1;

/// UTF-8 accumulator with a byte cap and streaming marker detection.
#[derive(Debug)]
pub(crate) struct OutputBudget {
    max_bytes: usize,
    bytes: Vec<u8>,
    exceeded_limit: bool,
}

impl OutputBudget {
    /// Create a budget that accepts at most `max_bytes` UTF-8 bytes.
    pub(crate) fn new(max_bytes: usize) -> Self {
        Self {
            max_bytes,
            bytes: Vec::new(),
            exceeded_limit: false,
        }
    }

    /// True when the byte cap, rather than a marker, stopped the stream.
    pub(crate) fn exceeded_limit(&self) -> bool {
        self.exceeded_limit
    }

    /// Accumulated text; invalid trailing bytes become U+FFFD.
    pub(crate) fn text(&self) -> String {
        String::from_utf8_lossy(&self.bytes).into_owned()
    }

    /// Append one streamed piece; returns `false` when generation must stop.
    pub(crate) fn append(&mut self, piece: &str) -> bool {
        if piece.is_empty() {
            return true;
        }
        let overlap = OVERLAP.min(self.bytes.len());
        let remaining = self.max_bytes.saturating_sub(self.bytes.len());
        let data = piece.as_bytes();
        // Read a little past the cap so a marker that would start behind the
        // cap is still recognised inside the overlap window.
        let fragment = &data[..data.len().min(remaining + OVERLAP + 1)];

        let mut window = Vec::with_capacity(overlap + fragment.len());
        window.extend_from_slice(&self.bytes[self.bytes.len() - overlap..]);
        window.extend_from_slice(fragment);

        let folded: Vec<u8> = window
            .iter()
            .map(|byte| {
                if byte.is_ascii_uppercase() {
                    byte + 32
                } else {
                    *byte
                }
            })
            .collect();

        let mut marker_offset: Option<usize> = None;
        for marker in MARKERS {
            if let Some(offset) = find(&folded, marker) {
                marker_offset = Some(marker_offset.map_or(offset, |current| current.min(offset)));
            }
        }

        if let Some(offset) = marker_offset {
            if offset < overlap {
                // The marker started inside the previous piece: drop the part
                // of it that was already accepted.
                let keep = self.bytes.len() - (overlap - offset);
                self.bytes.truncate(keep);
            } else if offset - overlap <= remaining {
                self.bytes.extend_from_slice(&window[overlap..offset]);
            } else {
                // The marker starts behind the byte cap: the cap truncated the
                // generation, so this is an overflow, not a finished answer
                // (`TranslationService.swift:1128`). Keep the part that fitted
                // under the cap so nothing already accepted is thrown away.
                self.exceeded_limit = true;
                let under_cap = overlap + remaining;
                self.bytes
                    .extend_from_slice(&window[overlap..under_cap.min(offset)]);
                self.trim_to_char_boundary();
            }
            return false;
        }

        if fragment.len() > remaining {
            self.exceeded_limit = true;
            return false;
        }
        self.bytes.extend_from_slice(fragment);
        true
    }

    /// Drop a partially written UTF-8 character at the end of the buffer.
    ///
    /// Only the overflow branch can cut a multi-byte character, because it
    /// stops at a byte offset chosen by the cap rather than by the producer.
    fn trim_to_char_boundary(&mut self) {
        if let Err(error) = std::str::from_utf8(&self.bytes) {
            self.bytes.truncate(error.valid_up_to());
        }
    }
}

/// Plain byte search; the window is at most a few dozen bytes.
fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    if needle.is_empty() || haystack.len() < needle.len() {
        return None;
    }
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn marker_finds_the_earliest_of_several_hits() {
        let mut budget = OutputBudget::new(64);
        assert!(budget.append("Hello "));
        assert!(!budget.append("a<|b hy_end"));
        assert_eq!(budget.text(), "Hello a");
    }

    #[test]
    fn detects_a_marker_split_across_unicode_pieces() {
        let expected = "é".repeat(80) + " • 👩🏽‍💻 cafe\u{301}";
        let mut output = OutputBudget::new(1_000);
        assert!(output.append(&(expected.clone() + "<")));
        assert!(!output.append("｜hy_ending"));
        assert_eq!(output.text(), expected);
    }

    #[test]
    fn rejects_instead_of_cutting_a_replacement_character() {
        let mut output = OutputBudget::new(4);
        assert!(output.append("éé"));
        assert!(!output.append("😀"));
        assert!(output.exceeded_limit());
        assert_eq!(output.text(), "éé");
    }

    #[test]
    fn a_marker_past_the_cap_is_an_overflow() {
        // Marker reached after the cap already truncated the generation.
        let mut output = OutputBudget::new(10);
        assert!(output.append("abcdefghij"));
        assert!(!output.append("KL<|"));
        assert!(output.exceeded_limit());
        assert_eq!(output.text(), "abcdefghij");

        // The same overrun inside one piece: only the capped prefix is kept.
        let mut output = OutputBudget::new(10);
        assert!(!output.append("abcdefghijk<|"));
        assert!(output.exceeded_limit());
        assert_eq!(output.text(), "abcdefghij");
    }

    #[test]
    fn an_overflow_marker_keeps_only_whole_characters() {
        // The marker starts past the cap inside a multi-byte character; the
        // bytes that fitted are kept up to the last complete character.
        let mut output = OutputBudget::new(4);
        assert!(output.append("\u{4e00}"));
        assert!(!output.append("\u{4e00}<|"));
        assert!(output.exceeded_limit());
        assert_eq!(output.text(), "\u{4e00}");
    }

    #[test]
    fn marker_at_the_cap_is_not_an_overflow() {
        let mut exact = OutputBudget::new(4);
        assert!(!exact.append("ééHY_END"));
        assert!(!exact.exceeded_limit());
        assert_eq!(exact.text(), "éé");

        let mut exact = OutputBudget::new(10);
        assert!(exact.append("abcdefghij"));
        assert!(!exact.append("<|"));
        assert!(!exact.exceeded_limit());
        assert_eq!(exact.text(), "abcdefghij");
    }

    #[test]
    fn detects_a_lowercase_marker_inside_a_short_piece() {
        let mut output = OutputBudget::new(1_000);
        assert!(output.append("Hello "));
        assert!(!output.append("HY-ASSISTANT"));
        assert_eq!(output.text(), "Hello ");
        assert!(!output.exceeded_limit());
    }

    #[test]
    fn stops_at_the_cap_when_no_marker_is_present() {
        let mut output = OutputBudget::new(8);
        assert!(output.append("abcd"));
        assert!(!output.append("efghijkl"));
        assert!(output.exceeded_limit());
        assert_eq!(output.text(), "abcd");
    }
}
