//! Interface languages (`AppLanguage`) and operating-system language detection.

use serde::{Deserialize, Deserializer, Serialize, Serializer};

use crate::localize::t;

/// Interface language, mirroring the Swift `AppLanguage` enum.
///
/// [`AppLanguage::System`] means "follow the operating system"; every consumer
/// resolves it first, so [`AppLanguage::resolved`] never returns `System` and
/// [`crate::current_language`] never stores it.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Hash)]
pub enum AppLanguage {
    /// Follow the operating system's preferred language.
    System,
    /// English (also the identity translation and the final fallback).
    En,
    /// Ukrainian.
    Uk,
    /// Russian.
    Ru,
    /// German.
    De,
    /// French.
    Fr,
    /// Spanish.
    Es,
    /// Polish.
    Pl,
    /// Portuguese.
    Pt,
    /// Italian.
    It,
}

impl AppLanguage {
    /// Number of enum values; used for the atomic language index.
    const COUNT: u8 = 10;

    /// The concrete language used by this value.
    ///
    /// `System` is mapped through [`AppLanguage::system`]; everything else is
    /// returned unchanged. The result is never `System`.
    pub fn resolved(self) -> AppLanguage {
        if self == AppLanguage::System {
            AppLanguage::system()
        } else {
            self
        }
    }

    /// Stable storage/JSON code (`"system"`, `"en"`, `"uk"`, ...).
    pub fn code(self) -> &'static str {
        match self {
            AppLanguage::System => "system",
            AppLanguage::En => "en",
            AppLanguage::Uk => "uk",
            AppLanguage::Ru => "ru",
            AppLanguage::De => "de",
            AppLanguage::Fr => "fr",
            AppLanguage::Es => "es",
            AppLanguage::Pl => "pl",
            AppLanguage::Pt => "pt",
            AppLanguage::It => "it",
        }
    }

    /// `en_US`-style identifier, resolved through the OS for `System`.
    pub fn locale_identifier(self) -> &'static str {
        match self.resolved() {
            AppLanguage::Uk => "uk_UA",
            AppLanguage::Ru => "ru_RU",
            AppLanguage::De => "de_DE",
            AppLanguage::Fr => "fr_FR",
            AppLanguage::Es => "es_ES",
            AppLanguage::Pl => "pl_PL",
            AppLanguage::Pt => "pt_PT",
            AppLanguage::It => "it_IT",
            // `resolved` never yields `System`; English is the safe fallback.
            AppLanguage::System | AppLanguage::En => "en_US",
        }
    }

    /// Native language name shown in the interface language picker.
    ///
    /// `System` is translated through the catalogue, everything else is the
    /// language's own name (`"Українська"`, `"Deutsch"`, ...).
    pub fn picker_title(self) -> String {
        match self {
            AppLanguage::System => t("System").to_owned(),
            AppLanguage::En => "English".to_owned(),
            AppLanguage::Uk => "Українська".to_owned(),
            AppLanguage::Ru => "Русский".to_owned(),
            AppLanguage::De => "Deutsch".to_owned(),
            AppLanguage::Fr => "Français".to_owned(),
            AppLanguage::Es => "Español".to_owned(),
            AppLanguage::Pl => "Polski".to_owned(),
            AppLanguage::Pt => "Português".to_owned(),
            AppLanguage::It => "Italiano".to_owned(),
        }
    }

    /// Parse a stored/UI language value.
    ///
    /// Tolerant like the Python `coerce_app_language`: surrounding whitespace,
    /// case and a region suffix (`"uk-UA"`, `"pt_BR"`) are ignored, and the
    /// legacy code `"ua"` maps to [`AppLanguage::Uk`]. Unknown values return
    /// `None`.
    pub fn from_code(code: &str) -> Option<AppLanguage> {
        let trimmed = code.trim();
        if trimmed.is_empty() {
            return None;
        }
        if trimmed.eq_ignore_ascii_case("system") {
            return Some(AppLanguage::System);
        }
        // `split` yields at least one item, so `next` is always `Some`.
        let base = trimmed.split(['_', '-']).next().unwrap_or(trimmed).trim();
        match base.to_ascii_lowercase().as_str() {
            "en" => Some(AppLanguage::En),
            "uk" | "ua" => Some(AppLanguage::Uk),
            "ru" => Some(AppLanguage::Ru),
            "de" => Some(AppLanguage::De),
            "fr" => Some(AppLanguage::Fr),
            "es" => Some(AppLanguage::Es),
            "pl" => Some(AppLanguage::Pl),
            "pt" => Some(AppLanguage::Pt),
            "it" => Some(AppLanguage::It),
            _ => None,
        }
    }

    /// Detect the operating system's interface language.
    ///
    /// The `LC_ALL`, `LC_MESSAGES`, `LANG` and `LANGUAGE` environment variables
    /// are consulted in that order (the Python port's order); on Windows the
    /// user default UI language is used when none of them is set. Anything
    /// unsupported falls back to English, and the result is never `System`.
    pub fn system() -> AppLanguage {
        if let Some(code) = environment_code() {
            let detected =
                AppLanguage::from_code(&code).filter(|language| *language != AppLanguage::System);
            return detected.unwrap_or(AppLanguage::En);
        }
        #[cfg(windows)]
        if let Some(language) = windows_ui_language() {
            return language;
        }
        AppLanguage::En
    }

    /// Compact index used by the global atomic language cell.
    pub(crate) const fn as_index(self) -> u8 {
        match self {
            AppLanguage::System => 0,
            AppLanguage::En => 1,
            AppLanguage::Uk => 2,
            AppLanguage::Ru => 3,
            AppLanguage::De => 4,
            AppLanguage::Fr => 5,
            AppLanguage::Es => 6,
            AppLanguage::Pl => 7,
            AppLanguage::Pt => 8,
            AppLanguage::It => 9,
        }
    }

    /// Inverse of [`AppLanguage::as_index`]; `None` for out-of-range bytes.
    pub(crate) const fn from_index(value: u8) -> Option<AppLanguage> {
        if value >= AppLanguage::COUNT {
            return None;
        }
        Some(match value {
            0 => AppLanguage::System,
            1 => AppLanguage::En,
            2 => AppLanguage::Uk,
            3 => AppLanguage::Ru,
            4 => AppLanguage::De,
            5 => AppLanguage::Fr,
            6 => AppLanguage::Es,
            7 => AppLanguage::Pl,
            8 => AppLanguage::Pt,
            _ => AppLanguage::It,
        })
    }
}

impl Default for AppLanguage {
    /// Defaults to [`AppLanguage::System`], like the Swift enum.
    fn default() -> Self {
        AppLanguage::System
    }
}

impl std::fmt::Display for AppLanguage {
    /// Writes the storage code, so `format!("{}", language)` is JSON-safe.
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.code())
    }
}

impl Serialize for AppLanguage {
    /// Serialises as the storage code (`"system"`, `"uk"`, ...).
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(self.code())
    }
}

impl<'de> Deserialize<'de> for AppLanguage {
    /// Accepts any string [`AppLanguage::from_code`] understands.
    ///
    /// Unknown values deserialise to [`AppLanguage::System`] instead of failing,
    /// matching the Python port's tolerance of stale settings files.
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = String::deserialize(deserializer)?;
        Ok(AppLanguage::from_code(&raw).unwrap_or(AppLanguage::System))
    }
}

/// First non-empty locale environment variable, reduced to its language code.
fn environment_code() -> Option<String> {
    for variable in ["LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"] {
        let raw = match std::env::var(variable) {
            Ok(value) => value,
            Err(_) => continue,
        };
        let trimmed = raw.trim();
        if trimmed.is_empty() {
            continue;
        }
        let code = trimmed
            .split(['.', ':', '@', '_', '-'])
            .next()
            .unwrap_or(trimmed);
        return Some(code.to_ascii_lowercase());
    }
    None
}

/// Win32 UI language, used when no locale environment variable is set.
#[cfg(windows)]
fn windows_ui_language() -> Option<AppLanguage> {
    // Win32 `GetUserDefaultUILanguage` from `kernel32`, the same call the Python
    // port reaches through `ctypes`.
    #[link(name = "kernel32")]
    extern "system" {
        fn GetUserDefaultUILanguage() -> u16;
    }

    // SAFETY: `GetUserDefaultUILanguage` takes no arguments, cannot fail and
    // only reads the current user's preferred UI language. The returned LANGID
    // is masked to its primary-language bits before use.
    let language_id = unsafe { GetUserDefaultUILanguage() } & 0x03FF;
    let code = match language_id {
        0x07 => "de",
        0x09 => "en",
        0x0A => "es",
        0x0C => "fr",
        0x10 => "it",
        0x15 => "pl",
        0x16 => "pt",
        0x19 => "ru",
        0x22 => "uk",
        _ => return None,
    };
    AppLanguage::from_code(code)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codes_are_stable() {
        assert_eq!(AppLanguage::System.code(), "system");
        assert_eq!(AppLanguage::En.code(), "en");
        assert_eq!(AppLanguage::Uk.code(), "uk");
        assert_eq!(AppLanguage::Ru.code(), "ru");
        assert_eq!(AppLanguage::De.code(), "de");
        assert_eq!(AppLanguage::Fr.code(), "fr");
        assert_eq!(AppLanguage::Es.code(), "es");
        assert_eq!(AppLanguage::Pl.code(), "pl");
        assert_eq!(AppLanguage::Pt.code(), "pt");
        assert_eq!(AppLanguage::It.code(), "it");
    }

    #[test]
    fn index_round_trips() {
        let all = [
            AppLanguage::System,
            AppLanguage::En,
            AppLanguage::Uk,
            AppLanguage::Ru,
            AppLanguage::De,
            AppLanguage::Fr,
            AppLanguage::Es,
            AppLanguage::Pl,
            AppLanguage::Pt,
            AppLanguage::It,
        ];
        assert_eq!(all.len(), usize::from(AppLanguage::COUNT));
        for language in all {
            assert_eq!(AppLanguage::from_index(language.as_index()), Some(language));
        }
        assert_eq!(AppLanguage::from_index(AppLanguage::COUNT), None);
        assert_eq!(AppLanguage::from_index(255), None);
    }

    #[test]
    fn locale_identifiers_match_the_swift_enum() {
        assert_eq!(AppLanguage::En.locale_identifier(), "en_US");
        assert_eq!(AppLanguage::Uk.locale_identifier(), "uk_UA");
        assert_eq!(AppLanguage::Pt.locale_identifier(), "pt_PT");
        assert_eq!(AppLanguage::It.locale_identifier(), "it_IT");
        assert_eq!(
            AppLanguage::System.locale_identifier(),
            AppLanguage::system().locale_identifier()
        );
    }

    #[test]
    fn resolved_never_returns_system() {
        assert_eq!(AppLanguage::Uk.resolved(), AppLanguage::Uk);
        assert_ne!(AppLanguage::system(), AppLanguage::System);
        assert_eq!(AppLanguage::System.resolved(), AppLanguage::system());
    }

    #[test]
    fn picker_titles_are_native_names() {
        assert_eq!(AppLanguage::En.picker_title(), "English");
        assert_eq!(AppLanguage::Uk.picker_title(), "Українська");
        assert_eq!(AppLanguage::Ru.picker_title(), "Русский");
        assert_eq!(AppLanguage::De.picker_title(), "Deutsch");
        assert_eq!(AppLanguage::Fr.picker_title(), "Français");
        assert_eq!(AppLanguage::Es.picker_title(), "Español");
        assert_eq!(AppLanguage::Pl.picker_title(), "Polski");
        assert_eq!(AppLanguage::Pt.picker_title(), "Português");
        assert_eq!(AppLanguage::It.picker_title(), "Italiano");
    }

    #[test]
    fn from_code_is_tolerant() {
        assert_eq!(AppLanguage::from_code(""), None);
        assert_eq!(AppLanguage::from_code("   "), None);
        assert_eq!(AppLanguage::from_code("system"), Some(AppLanguage::System));
        assert_eq!(AppLanguage::from_code("SYSTEM"), Some(AppLanguage::System));
        assert_eq!(AppLanguage::from_code("uk_UA"), Some(AppLanguage::Uk));
        assert_eq!(AppLanguage::from_code("uk-UA"), Some(AppLanguage::Uk));
        assert_eq!(AppLanguage::from_code("UA"), Some(AppLanguage::Uk));
        assert_eq!(AppLanguage::from_code("de-DE"), Some(AppLanguage::De));
        assert_eq!(AppLanguage::from_code(" pt_BR "), Some(AppLanguage::Pt));
        assert_eq!(AppLanguage::from_code("klingon"), None);
        assert_eq!(AppLanguage::from_code("zz"), None);
    }

    #[test]
    fn serde_round_trip_and_tolerance() {
        for language in [AppLanguage::System, AppLanguage::Uk, AppLanguage::It] {
            let json = serde_json::to_string(&language).unwrap();
            assert_eq!(json, format!("\"{}\"", language.code()));
            let parsed: AppLanguage = serde_json::from_str(&json).unwrap();
            assert_eq!(parsed, language);
        }
        let unknown: AppLanguage = serde_json::from_str("\"klingon\"").unwrap();
        assert_eq!(unknown, AppLanguage::System);
    }

    #[test]
    fn serde_uses_the_storage_codes() {
        let expected = [
            (AppLanguage::System, "\"system\""),
            (AppLanguage::En, "\"en\""),
            (AppLanguage::Uk, "\"uk\""),
            (AppLanguage::Ru, "\"ru\""),
            (AppLanguage::De, "\"de\""),
            (AppLanguage::Fr, "\"fr\""),
            (AppLanguage::Es, "\"es\""),
            (AppLanguage::Pl, "\"pl\""),
            (AppLanguage::Pt, "\"pt\""),
            (AppLanguage::It, "\"it\""),
        ];
        for (language, json) in expected {
            assert_eq!(serde_json::to_string(&language).unwrap(), json);
            assert_eq!(serde_json::from_str::<AppLanguage>(json).unwrap(), language);
        }
        // Region suffixes and the legacy "ua" code survive a round trip.
        assert_eq!(
            serde_json::from_str::<AppLanguage>("\"uk-UA\"").unwrap(),
            AppLanguage::Uk
        );
        assert_eq!(
            serde_json::from_str::<AppLanguage>("\"ua\"").unwrap(),
            AppLanguage::Uk
        );
        assert_eq!(
            serde_json::from_str::<AppLanguage>("\"klingon\"").unwrap(),
            AppLanguage::System
        );
    }

    #[test]
    fn default_is_system() {
        assert_eq!(AppLanguage::default(), AppLanguage::System);
    }

    #[test]
    fn display_uses_the_storage_code() {
        assert_eq!(AppLanguage::Uk.to_string(), "uk");
    }
}
