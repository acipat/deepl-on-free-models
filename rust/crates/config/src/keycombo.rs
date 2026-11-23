//! Keyboard shortcut value object with Windows semantics.
//!
//! Ported from `windows/deepl_ofm/core/keycombo.py`, which replaces the Carbon
//! key code plus a modifier bit mask of the macOS app with a normalised key name
//! and four booleans. The Python `command`/`option`/`control` flags map onto
//! [`KeyCombo::ctrl`]/[`KeyCombo::alt`]; the legacy names are still accepted when
//! reading JSON, so files written by the Swift or Python builds keep working.

use serde::{Deserialize, Deserializer, Serialize, Serializer};
use serde_json::{Map, Value};
use unicode_normalization::char::canonical_combining_class;

/// Keyboard shortcuts longer than this are rejected as garbage.
const MAX_KEY_LENGTH: usize = 24;

/// One shortcut: a key name plus modifier flags (Ctrl is `ctrl`).
#[derive(Clone, Debug, PartialEq, Eq, Default)]
pub struct KeyCombo {
    /// Canonical lower-case key name (`"t"`, `"f5"`, `"space"`).
    pub key: String,
    /// Ctrl (the macOS ⌘/⌃ flags both map here).
    pub ctrl: bool,
    /// Alt (the macOS ⌥ flag).
    pub alt: bool,
    /// Shift.
    pub shift: bool,
    /// Meta/Super/Windows key. Only the Rust port and the JSON alias tables
    /// know it; the Python build had no field for it.
    pub meta: bool,
}

impl KeyCombo {
    /// Human readable shortcut, e.g. `Ctrl+Alt+T`.
    pub fn display(&self) -> String {
        let mut parts: Vec<String> = Vec::with_capacity(5);
        if self.ctrl {
            parts.push("Ctrl".to_string());
        }
        if self.alt {
            parts.push("Alt".to_string());
        }
        if self.shift {
            parts.push("Shift".to_string());
        }
        if self.meta {
            parts.push("Meta".to_string());
        }
        let label = fallback_label(&self.key);
        if !label.is_empty() {
            parts.push(label);
        }
        parts.join("+")
    }

    /// True when a usable key with at least one of Ctrl/Alt is present.
    pub fn is_valid(&self) -> bool {
        !self.key.is_empty() && (self.ctrl || self.alt)
    }

    /// Default translate shortcut: Ctrl+Alt+T.
    pub fn standard() -> Self {
        Self {
            key: "t".to_string(),
            ctrl: true,
            alt: true,
            ..Self::default()
        }
    }

    /// Default selection translate shortcut: Ctrl+Alt+C.
    pub fn selection() -> Self {
        Self {
            key: "c".to_string(),
            ctrl: true,
            alt: true,
            ..Self::default()
        }
    }

    /// Serialise the combo with the canonical Rust field names.
    pub fn to_json(&self) -> Value {
        let mut object = Map::new();
        object.insert("key".to_string(), Value::String(self.key.clone()));
        object.insert("ctrl".to_string(), Value::Bool(self.ctrl));
        object.insert("alt".to_string(), Value::Bool(self.alt));
        object.insert("shift".to_string(), Value::Bool(self.shift));
        object.insert("meta".to_string(), Value::Bool(self.meta));
        Value::Object(object)
    }

    /// Tolerant parser for [`Self::to_json`] output and the legacy shapes.
    ///
    /// Accepts a JSON string, the Python `command`/`option`/`control` names, the
    /// Swift `label`/`modifiers` Codable shape, and numbers in `0`/`1` position.
    /// Anything unusable becomes an empty (invalid) combo instead of panicking.
    pub fn from_json(value: &Value) -> Self {
        match value {
            Value::String(text) => match serde_json::from_str::<Value>(text) {
                Ok(parsed) => Self::from_json(&parsed),
                Err(_) => Self::default(),
            },
            Value::Object(object) => Self::from_object(object),
            _ => Self::default(),
        }
    }

    /// Build a combo from a JSON object, tolerating every historical spelling.
    fn from_object(object: &Map<String, Value>) -> Self {
        let raw_key = object.get("key").or_else(|| object.get("label"));
        let key = match raw_key {
            Some(value) => normalize_key(value),
            None => String::new(),
        };

        let has_flags = [
            "command", "cmd", "ctrl", "option", "alt", "control", "shift", "meta", "win", "super",
        ]
        .iter()
        .any(|name| object.contains_key(*name));

        let (ctrl, alt, shift, meta) = if has_flags {
            let ctrl = flag(object, &["command", "cmd", "ctrl", "control"]).unwrap_or(false);
            let alt = flag(object, &["option", "alt"]).unwrap_or(false);
            let shift = flag(object, &["shift"]).unwrap_or(false);
            let meta = flag(object, &["meta", "win", "super"]).unwrap_or(false);
            (ctrl, alt, shift, meta)
        } else {
            modifiers(object.get("modifiers"))
        };

        Self {
            key,
            ctrl,
            alt,
            shift,
            meta,
        }
    }
}

impl Serialize for KeyCombo {
    /// Serialises with the canonical field names (the shape the UI reads).
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        self.to_json().serialize(serializer)
    }
}

impl<'de> Deserialize<'de> for KeyCombo {
    /// Accepts the canonical shape and every legacy spelling via [`Self::from_json`].
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = Value::deserialize(deserializer)?;
        Ok(Self::from_json(&value))
    }
}

/// Read the first present boolean flag from a JSON object.
fn flag(object: &Map<String, Value>, names: &[&str]) -> Option<bool> {
    for name in names {
        if let Some(value) = object.get(*name) {
            return Some(match value {
                Value::Bool(flag) => *flag,
                Value::Number(number) => number.as_i64() == Some(1),
                _ => false,
            });
        }
    }
    None
}

/// Decode the AppKit modifier bit mask of the Swift Codable representation.
fn modifiers(value: Option<&Value>) -> (bool, bool, bool, bool) {
    const NS_COMMAND: u64 = 0x0010_0000;
    const NS_OPTION: u64 = 0x0008_0000;
    const NS_CONTROL: u64 = 0x0004_0000;
    const NS_SHIFT: u64 = 0x0002_0000;

    let mask = value
        .and_then(Value::as_u64)
        .or_else(|| value.and_then(Value::as_i64).map(|raw| raw as u64))
        .unwrap_or(0);
    (
        mask & (NS_COMMAND | NS_CONTROL) != 0,
        mask & NS_OPTION != 0,
        mask & NS_SHIFT != 0,
        false,
    )
}

/// Return the canonical lower-case key name, or an empty string when unusable.
fn normalize_key(value: &Value) -> String {
    let text = match value {
        Value::String(text) => text.trim(),
        _ => return String::new(),
    };
    if text.is_empty() {
        return String::new();
    }
    let compact: String = if text.chars().count() > 1 {
        text.chars()
            .filter(|character| {
                !character.is_whitespace() && *character != '_' && *character != '-'
            })
            .collect()
    } else {
        text.to_string()
    };
    let lowered = compact.to_lowercase();
    if lowered.chars().count() > MAX_KEY_LENGTH {
        return String::new();
    }
    for character in lowered.chars() {
        let code = character as u32;
        if code < 0x20 || (0x7F..=0x9F).contains(&code) {
            return String::new();
        }
        if (0xF700..=0xF8FF).contains(&code) {
            return String::new();
        }
        if canonical_combining_class(character) != 0 {
            return String::new();
        }
    }
    lowered
}

/// Display label for a named or function key; `None` for a one-character key.
fn key_display(key: &str) -> Option<String> {
    if let Some((_, label)) = NAMED_KEYS.iter().find(|(name, _)| *name == key) {
        return Some((*label).to_string());
    }
    function_key_number(key).map(|number| format!("F{number}"))
}

/// Number of an `f1` … `f24` key.
fn function_key_number(key: &str) -> Option<u8> {
    let rest = key.strip_prefix('f')?;
    if rest.is_empty() || rest.starts_with('0') {
        return None;
    }
    match rest.parse::<u8>() {
        Ok(number) if (1..=24).contains(&number) => Some(number),
        _ => None,
    }
}

/// Named keys with their user-facing labels.
const NAMED_KEYS: &[(&str, &str)] = &[
    ("space", "Space"),
    ("enter", "Enter"),
    ("return", "Enter"),
    ("esc", "Esc"),
    ("escape", "Esc"),
    ("tab", "Tab"),
    ("backspace", "Backspace"),
    ("delete", "Delete"),
    ("del", "Delete"),
    ("insert", "Insert"),
    ("ins", "Insert"),
    ("home", "Home"),
    ("end", "End"),
    ("left", "Left"),
    ("right", "Right"),
    ("up", "Up"),
    ("down", "Down"),
    ("pageup", "Page Up"),
    ("pgup", "Page Up"),
    ("pagedown", "Page Down"),
    ("pgdn", "Page Down"),
    ("print", "Print Screen"),
    ("printscreen", "Print Screen"),
    ("pause", "Pause"),
    ("menu", "Menu"),
    ("capslock", "Caps Lock"),
    ("numlock", "Num Lock"),
    ("scrolllock", "Scroll Lock"),
];

/// Human-readable label for an arbitrary key name; empty when unusable.
fn fallback_label(key: &str) -> String {
    if let Some(label) = key_display(key) {
        return label;
    }
    if key.is_empty() {
        return String::new();
    }
    let mut characters = key.chars();
    if let (Some(character), None) = (characters.next(), characters.next()) {
        return character.to_uppercase().collect();
    }
    key.replace('_', " ")
        .split_whitespace()
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                Some(first) => first.to_uppercase().chain(chars).collect::<String>(),
                None => String::new(),
            }
        })
        .collect::<Vec<String>>()
        .join(" ")
}

impl KeyCombo {
    /// Display label of [`Self::key`], empty when the key is unusable.
    pub fn key_label(&self) -> String {
        fallback_label(&self.key)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// Struct literal helper: every test combo starts from the defaults.
    fn combo(key: &str) -> KeyCombo {
        KeyCombo {
            key: key.to_string(),
            ..KeyCombo::default()
        }
    }

    fn normalize(value: &str) -> String {
        normalize_key(&Value::String(value.to_string()))
    }

    #[test]
    fn standard_shortcut() {
        let standard = KeyCombo::standard();
        assert_eq!(
            standard,
            KeyCombo {
                key: "t".to_string(),
                ctrl: true,
                alt: true,
                ..KeyCombo::default()
            }
        );
        assert_eq!(standard.display(), "Ctrl+Alt+T");
        assert!(standard.is_valid());
    }

    #[test]
    fn selection_shortcut() {
        let selection = KeyCombo::selection();
        assert_eq!(
            selection,
            KeyCombo {
                key: "c".to_string(),
                ctrl: true,
                alt: true,
                ..KeyCombo::default()
            }
        );
        assert_eq!(selection.display(), "Ctrl+Alt+C");
        assert!(selection.is_valid());
    }

    #[test]
    fn display_order() {
        let combo = KeyCombo {
            key: "t".to_string(),
            ctrl: true,
            alt: true,
            shift: true,
            meta: false,
        };
        assert_eq!(combo.display(), "Ctrl+Alt+Shift+T");
    }

    #[test]
    fn punctuation_key_is_readable() {
        let combo = KeyCombo {
            key: "'".to_string(),
            alt: true,
            ..KeyCombo::default()
        };
        assert_eq!(combo.display(), "Alt+'");
    }

    #[test]
    fn recorded_label_wins() {
        // The label is stored as the key itself, so "є" is what gets displayed.
        let combo = KeyCombo::from_json(&json!({"label": "є", "modifiers": 0x0008_0000}));
        assert_eq!(combo.key, "є");
        assert_eq!(combo.display(), "Alt+Є");
        assert!(combo.alt);
    }

    #[test]
    fn meta_is_displayed_after_shift() {
        let combo = KeyCombo {
            key: "t".to_string(),
            ctrl: true,
            shift: true,
            meta: true,
            ..KeyCombo::default()
        };
        assert_eq!(combo.display(), "Ctrl+Shift+Meta+T");
    }

    #[test]
    fn named_keys_display() {
        let with_ctrl = |key: &str| KeyCombo {
            key: key.to_string(),
            ctrl: true,
            ..KeyCombo::default()
        };
        assert_eq!(with_ctrl("space").display(), "Ctrl+Space");
        assert_eq!(with_ctrl("f5").display(), "Ctrl+F5");
        assert_eq!(with_ctrl("pageup").display(), "Ctrl+Page Up");
        assert_eq!(with_ctrl("enter").display(), "Ctrl+Enter");
        assert_eq!(with_ctrl("left").display(), "Ctrl+Left");
        assert_eq!(
            KeyCombo {
                key: "delete".to_string(),
                alt: true,
                ..KeyCombo::default()
            }
            .display(),
            "Alt+Delete"
        );
    }

    #[test]
    fn key_normalisation() {
        assert_eq!(normalize("T"), "t");
        assert_eq!(normalize(" F5 "), "f5");
        assert_eq!(normalize("Page Up"), "pageup");
        assert_eq!(normalize("page_up"), "pageup");
        assert_eq!(normalize(""), "");
        assert_eq!(normalize("   "), "");
    }

    #[test]
    fn validation_requires_ctrl_or_alt() {
        assert!(!combo("t").is_valid());
        assert!(!KeyCombo {
            key: "t".to_string(),
            shift: true,
            ..KeyCombo::default()
        }
        .is_valid());
        assert!(KeyCombo {
            key: "t".to_string(),
            ctrl: true,
            ..KeyCombo::default()
        }
        .is_valid());
        assert!(KeyCombo {
            key: "t".to_string(),
            alt: true,
            ..KeyCombo::default()
        }
        .is_valid());
        assert!(!KeyCombo {
            key: String::new(),
            ctrl: true,
            alt: true,
            ..KeyCombo::default()
        }
        .is_valid());
    }

    #[test]
    fn rejected_keys() {
        assert!(!KeyCombo {
            key: normalize("\u{1}"),
            ctrl: true,
            ..KeyCombo::default()
        }
        .is_valid());
        assert_eq!(normalize("\u{f700}"), "");
        assert_eq!(normalize("combining\u{301}"), "");
        assert_eq!(normalize(&"x".repeat(40)), "");
    }

    #[test]
    fn round_trip() {
        let combo = KeyCombo {
            key: "t".to_string(),
            ctrl: true,
            alt: true,
            shift: true,
            meta: false,
        };
        let data = combo.to_json();
        assert_eq!(
            data,
            json!({"key": "t", "ctrl": true, "alt": true, "shift": true, "meta": false})
        );
        assert_eq!(KeyCombo::from_json(&data), combo);
    }

    #[test]
    fn serde_uses_the_canonical_shape() {
        let combo = KeyCombo::standard();
        let json = serde_json::to_value(&combo).expect("serialise combo");
        assert_eq!(json, combo.to_json());
        let parsed: KeyCombo =
            serde_json::from_value(json!({"key": "T", "command": true, "option": true}))
                .expect("parse legacy combo");
        assert_eq!(parsed, combo);
        let parsed: KeyCombo =
            serde_json::from_value(json!("{\"key\": \"c\", \"ctrl\": true}")).expect("parse");
        assert_eq!(
            parsed,
            KeyCombo {
                key: "c".to_string(),
                ctrl: true,
                ..KeyCombo::default()
            }
        );
    }

    #[test]
    fn from_json_accepts_legacy_aliases() {
        assert_eq!(
            KeyCombo::from_json(&json!({"key": "T", "command": true, "option": true})),
            KeyCombo {
                key: "t".to_string(),
                ctrl: true,
                alt: true,
                ..KeyCombo::default()
            }
        );
        assert_eq!(
            KeyCombo::from_json(&json!({"key": "t", "ctrl": true, "alt": true})),
            KeyCombo {
                key: "t".to_string(),
                ctrl: true,
                alt: true,
                ..KeyCombo::default()
            }
        );
        let combo = KeyCombo::from_json(&json!({"key": "x", "command": 1, "shift": 0}));
        assert!(combo.ctrl);
        assert!(!combo.shift);
    }

    #[test]
    fn from_json_reads_the_swift_codable_shape() {
        let combo = KeyCombo::from_json(&json!({
            "keyCode": 17,
            "modifiers": 0x0010_0000 | 0x0008_0000,
            "label": "t"
        }));
        assert_eq!(combo.key, "t");
        assert!(combo.ctrl);
        assert!(combo.alt);
        assert_eq!(combo.display(), "Ctrl+Alt+T");
    }

    #[test]
    fn from_json_reads_a_json_string() {
        assert_eq!(
            KeyCombo::from_json(&json!(
                "{\"key\": \"k\", \"command\": true, \"shift\": true}"
            )),
            KeyCombo {
                key: "k".to_string(),
                ctrl: true,
                shift: true,
                ..KeyCombo::default()
            }
        );
    }

    #[test]
    fn from_json_rejects_garbage_without_panicking() {
        for payload in [
            Value::Null,
            json!(""),
            json!("not json"),
            json!([]),
            json!({}),
            json!(42),
            json!({"foo": "bar"}),
        ] {
            let combo = KeyCombo::from_json(&payload);
            assert!(!combo.is_valid(), "{payload:?}");
        }
    }

    #[test]
    fn key_label_falls_back_to_title_case() {
        assert_eq!(combo("f5").key_label(), "F5");
        assert_eq!(combo("pageup").key_label(), "Page Up");
        assert_eq!(combo("some_key").key_label(), "Some Key");
        assert_eq!(combo("").key_label(), "");
    }
}
