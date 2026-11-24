//! Global interface language state and the `t` / `t_in` / `tf` lookups.
//!
//! The English source string is the key: a missing translation falls back to the
//! key itself, exactly like `ukrainian[key] ?? key` in the Swift app. The
//! generated [`crate::catalog`] holds one table per translated language, and the
//! Windows-only strings live in a second table that is merged in at first use.

use std::collections::HashMap;
use std::fmt::Write as _;
use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::OnceLock;

use crate::app_language::AppLanguage;
use crate::catalog;

/// Number of translated tables in [`crate::catalog::TABLES`].
const TABLE_COUNT: usize = 8;

/// One resolved lookup table: English key to translation.
type Table = HashMap<&'static str, &'static str>;

/// Languages with a translation table, English first (the Python order).
static AVAILABLE: [AppLanguage; 9] = [
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

/// Current interface language, stored as an [`AppLanguage::as_index`] byte so
/// that `t()` can be called from any thread without locking.
static CURRENT: AtomicU8 = AtomicU8::new(AppLanguage::En.as_index());

/// Merged catalogue and Windows-only tables, built once on first lookup.
static TABLES: OnceLock<[Table; TABLE_COUNT]> = OnceLock::new();

/// Switch the global interface language.
///
/// [`AppLanguage::System`] is resolved immediately, so
/// [`current_language`] never returns it.
pub fn set_language(language: AppLanguage) {
    CURRENT.store(language.resolved().as_index(), Ordering::Relaxed);
}

/// The concrete interface language currently in effect (never `System`).
pub fn current_language() -> AppLanguage {
    AppLanguage::from_index(CURRENT.load(Ordering::Relaxed)).unwrap_or(AppLanguage::En)
}

/// Interface languages with a translation table, English first.
///
/// `System` is not listed: it is a preference, not a language.
pub fn available_languages() -> &'static [AppLanguage] {
    &AVAILABLE
}

/// Translate `key` into the current interface language.
///
/// Returns `key` unchanged when the catalogue does not know it, and also for
/// English, whose translation is the identity.
pub fn t(key: &str) -> &str {
    t_in(key, current_language())
}

/// Translate `key` into `language`, resolving `System` first.
///
/// Returns `key` unchanged when the catalogue does not know it.
pub fn t_in(key: &str, language: AppLanguage) -> &str {
    if key.is_empty() {
        return key;
    }
    let Some(index) = table_index(language.resolved()) else {
        return key;
    };
    tables()
        .get(index)
        .and_then(|table| table.get(key))
        .copied()
        .unwrap_or(key)
}

/// Translate `key` and fill its Swift `printf` placeholders from `args`.
///
/// Placeholders (`%@`, `%d`, `%s`, `%.1f`, ...) are replaced left to right,
/// ignoring width, precision and positional prefixes; `%%` becomes a literal
/// percent sign. A wrong argument count never panics: surplus arguments are
/// ignored and a missing argument leaves its placeholder visible (`"%d"`), so
/// the bug shows up in the UI instead of crashing it.
pub fn tf(key: &str, args: &[&dyn std::fmt::Display]) -> String {
    let template = t(key);
    if args.is_empty() {
        // Nothing to substitute; `%%` is only collapsed when formatting.
        return template.to_owned();
    }
    let mut output = String::with_capacity(template.len() + 16);
    let mut argument = 0;
    let mut index = 0;
    while index < template.len() {
        if template.as_bytes()[index] != b'%' {
            match template[index..].chars().next() {
                Some(character) => {
                    output.push(character);
                    index += character.len_utf8();
                }
                None => break,
            }
            continue;
        }
        match placeholder_len(&template[index..]) {
            Some(length) => {
                let placeholder = &template[index..index + length];
                if placeholder == "%%" {
                    output.push('%');
                } else if let Some(value) = args.get(argument) {
                    // Writing into a `String` cannot fail.
                    let _ = write!(output, "{value}");
                    argument += 1;
                } else {
                    output.push_str(placeholder);
                }
                index += length;
            }
            None => {
                output.push('%');
                index += 1;
            }
        }
    }
    output
}

/// Index of `language` in [`crate::catalog::TABLES`], or `None` for English.
fn table_index(language: AppLanguage) -> Option<usize> {
    match language {
        AppLanguage::Uk => Some(0),
        AppLanguage::Ru => Some(1),
        AppLanguage::De => Some(2),
        AppLanguage::Fr => Some(3),
        AppLanguage::Es => Some(4),
        AppLanguage::Pl => Some(5),
        AppLanguage::Pt => Some(6),
        AppLanguage::It => Some(7),
        AppLanguage::En | AppLanguage::System => None,
    }
}

/// The merged tables, built on first use.
///
/// The catalogue is inserted last, so a Swift translation always wins over a
/// duplicate in the Windows-only table (the generator rejects conflicts).
fn tables() -> &'static [Table; TABLE_COUNT] {
    TABLES.get_or_init(|| {
        std::array::from_fn(|index| {
            let catalogue = catalog::TABLES.get(index).copied().unwrap_or(&[]);
            let extra = catalog::EXTRA_TABLES.get(index).copied().unwrap_or(&[]);
            let mut table = Table::with_capacity(catalogue.len() + extra.len());
            table.extend(extra.iter().copied());
            table.extend(catalogue.iter().copied());
            table
        })
    })
}

/// Every known key with its translation for `language`.
///
/// The desktop frontend needs the whole table at once to translate its own
/// labels: English is the key, so the result maps directly onto the strings the
/// interface already uses.
pub fn catalogue(language: AppLanguage) -> Vec<(&'static str, &'static str)> {
    let resolved = language.resolved();
    match table_index(resolved) {
        Some(index) => tables()[index]
            .iter()
            .map(|(key, value)| (*key, *value))
            .collect(),
        None => {
            // English is the identity mapping; iterate the keys so the shared
            // table does not have to hold them twice.
            let mut keys: Vec<&'static str> = tables()[0].keys().copied().collect();
            keys.sort_unstable();
            keys.into_iter().map(|key| (key, key)).collect()
        }
    }
}

/// Length of the `printf` placeholder at the start of `template`, if any.
///
/// The grammar is the one used by the Python port: `%%`, an optional positional
/// prefix (`%1$`), an optional length modifier (`h`, `hh`, `l`, `ll`), a
/// conversion character (`@`, `d`, `s`, `f`, ...), or the `%.1f` precision form.
fn placeholder_len(template: &str) -> Option<usize> {
    let bytes = template.as_bytes();
    if bytes.first() != Some(&b'%') {
        return None;
    }
    if bytes.get(1) == Some(&b'%') {
        return Some(2);
    }
    let mut index = 1;
    // Positional prefix; the index is ignored, arguments are consumed in order.
    let digits_start = index;
    while bytes.get(index).is_some_and(u8::is_ascii_digit) {
        index += 1;
    }
    if index > digits_start && bytes.get(index) == Some(&b'$') {
        index += 1;
    } else {
        index = digits_start;
    }
    // Length modifier.
    if bytes
        .get(index..)
        .is_some_and(|rest| rest.starts_with(b"hh") || rest.starts_with(b"ll"))
    {
        index += 2;
    } else if bytes
        .get(index..)
        .is_some_and(|rest| rest.starts_with(b"h") || rest.starts_with(b"l"))
    {
        index += 1;
    }
    if bytes
        .get(index)
        .is_some_and(|byte| b"@dsifFgGeExXocpaA".contains(byte))
    {
        return Some(index + 1);
    }
    // Precision form, `%.1f`.
    if bytes.get(index) == Some(&b'.') {
        let mut cursor = index + 1;
        let precision_start = cursor;
        while bytes.get(cursor).is_some_and(u8::is_ascii_digit) {
            cursor += 1;
        }
        if cursor > precision_start
            && bytes
                .get(cursor)
                .is_some_and(|byte| b"fFgGeE".contains(byte))
        {
            return Some(cursor + 1);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Mutex, MutexGuard};

    /// Serialises the tests that touch the global interface language.
    static LANGUAGE_LOCK: Mutex<()> = Mutex::new(());

    /// Interface languages in the order of the generated tables.
    const TABLE_LANGUAGES: [AppLanguage; 8] = [
        AppLanguage::Uk,
        AppLanguage::Ru,
        AppLanguage::De,
        AppLanguage::Fr,
        AppLanguage::Es,
        AppLanguage::Pl,
        AppLanguage::Pt,
        AppLanguage::It,
    ];

    /// Lock the global language and set it, resetting to English afterwards.
    fn with_language(language: AppLanguage) -> MutexGuard<'static, ()> {
        let guard = LANGUAGE_LOCK
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        set_language(language);
        guard
    }

    /// Placeholder texts of a template, in order (mirrors the generator check).
    fn placeholders(template: &str) -> Vec<&str> {
        let mut found = Vec::new();
        let mut index = 0;
        while index < template.len() {
            if template.as_bytes()[index] == b'%' {
                if let Some(length) = placeholder_len(&template[index..]) {
                    found.push(&template[index..index + length]);
                    index += length;
                    continue;
                }
            }
            index += template[index..].chars().next().map_or(1, char::len_utf8);
        }
        found
    }

    #[test]
    fn catalogue_has_305_keys_per_language() {
        assert_eq!(catalog::TABLES.len(), TABLE_COUNT);
        for (index, table) in catalog::TABLES.iter().enumerate() {
            assert_eq!(
                table.len(),
                305,
                "{:?} has {} keys",
                TABLE_LANGUAGES[index],
                table.len()
            );
        }
    }

    #[test]
    fn windows_only_table_has_74_keys_per_language() {
        assert_eq!(catalog::EXTRA_TABLES.len(), TABLE_COUNT);
        for (index, table) in catalog::EXTRA_TABLES.iter().enumerate() {
            assert_eq!(
                table.len(),
                74,
                "{:?} has {} extra keys",
                TABLE_LANGUAGES[index],
                table.len()
            );
        }
    }

    #[test]
    fn every_language_shares_the_same_key_set() {
        let reference: Vec<&str> = catalog::TABLES[0].iter().map(|(key, _)| *key).collect();
        for (index, table) in catalog::TABLES.iter().enumerate().skip(1) {
            let keys: Vec<&str> = table.iter().map(|(key, _)| *key).collect();
            assert_eq!(keys, reference, "{:?}", TABLE_LANGUAGES[index]);
        }
        let extra_reference: Vec<&str> = catalog::EXTRA_TABLES[0]
            .iter()
            .map(|(key, _)| *key)
            .collect();
        for (index, table) in catalog::EXTRA_TABLES.iter().enumerate().skip(1) {
            let keys: Vec<&str> = table.iter().map(|(key, _)| *key).collect();
            assert_eq!(keys, extra_reference, "{:?}", TABLE_LANGUAGES[index]);
        }
    }

    #[test]
    fn tables_are_sorted_and_well_formed() {
        for table in catalog::TABLES.iter().chain(catalog::EXTRA_TABLES.iter()) {
            for (key, value) in *table {
                assert!(!key.trim().is_empty(), "blank key");
                assert!(!value.trim().is_empty(), "blank value for {key:?}");
            }
            assert!(
                table.windows(2).all(|pair| pair[0].0 < pair[1].0),
                "table is not sorted"
            );
        }
    }

    #[test]
    fn placeholders_match_between_key_and_translation() {
        for (index, table) in catalog::TABLES.iter().enumerate() {
            for (key, value) in *table {
                let mut expected = placeholders(key);
                let mut actual = placeholders(value);
                expected.sort_unstable();
                actual.sort_unstable();
                assert_eq!(
                    actual, expected,
                    "{:?}: placeholder mismatch for {key:?} -> {value:?}",
                    TABLE_LANGUAGES[index]
                );
            }
        }
    }

    #[test]
    fn the_windows_table_does_not_conflict_with_the_catalogue() {
        for (catalogue, extra) in catalog::TABLES.iter().zip(catalog::EXTRA_TABLES.iter()) {
            for (key, value) in *extra {
                if let Some((_, translation)) = catalogue.iter().find(|(name, _)| name == key) {
                    assert_eq!(translation, value, "conflicting translation for {key:?}");
                }
            }
        }
    }

    #[test]
    fn spot_checks_match_the_swift_source() {
        let expected: [(&str, [&str; 5]); 8] = [
            (
                "uk",
                [
                    "Налаштування",
                    "Копіювати",
                    "Скасувати",
                    "Історія",
                    "Перекласти на",
                ],
            ),
            (
                "ru",
                [
                    "Настройки",
                    "Копировать",
                    "Отмена",
                    "История",
                    "Перевести на",
                ],
            ),
            (
                "de",
                [
                    "Einstellungen",
                    "Kopieren",
                    "Abbrechen",
                    "Verlauf",
                    "Übersetzen nach",
                ],
            ),
            (
                "fr",
                [
                    "Paramètres",
                    "Copier",
                    "Annuler",
                    "Historique",
                    "Traduire vers",
                ],
            ),
            (
                "es",
                [
                    "Configuración",
                    "Copiar",
                    "Cancelar",
                    "Historial",
                    "Traducir a",
                ],
            ),
            (
                "pl",
                [
                    "Ustawienia",
                    "Kopiuj",
                    "Anuluj",
                    "Historia",
                    "Przetłumacz na",
                ],
            ),
            (
                "pt",
                [
                    "Configurações",
                    "Copiar",
                    "Cancelar",
                    "Histórico",
                    "Traduzir para",
                ],
            ),
            (
                "it",
                [
                    "Impostazioni",
                    "Copia",
                    "Annulla",
                    "Cronologia",
                    "Traduci in",
                ],
            ),
        ];
        let keys = ["Settings", "Copy", "Cancel", "History", "Translate to"];
        for (language, translations) in TABLE_LANGUAGES.iter().zip(expected.iter()) {
            assert_eq!(language.code(), translations.0);
            for (key, translation) in keys.iter().zip(translations.1.iter()) {
                assert_eq!(t_in(key, *language), *translation, "{:?} {key:?}", language);
            }
        }
    }

    #[test]
    fn english_is_the_identity_mapping() {
        for (key, _) in catalog::TABLES[0] {
            assert_eq!(t_in(key, AppLanguage::En), *key);
        }
        for (key, _) in catalog::EXTRA_TABLES[0] {
            assert_eq!(t_in(key, AppLanguage::En), *key);
        }
    }

    #[test]
    fn unknown_key_returns_the_key_itself() {
        let missing = "This string does not exist in the Swift catalogue";
        for language in AVAILABLE
            .iter()
            .chain(std::iter::once(&AppLanguage::System))
        {
            assert_eq!(t_in(missing, *language), missing);
        }
    }

    #[test]
    fn empty_key_is_returned_unchanged() {
        assert_eq!(t_in("", AppLanguage::Uk), "");
    }

    #[test]
    fn language_codes_are_tolerant() {
        let ukrainian = AppLanguage::from_code("uk-UA").expect("uk-UA");
        assert_eq!(t_in("Settings", ukrainian), "Налаштування");
        let legacy = AppLanguage::from_code("UA").expect("UA");
        assert_eq!(t_in("Settings", legacy), "Налаштування");
        let portuguese = AppLanguage::from_code("pt_BR").expect("pt_BR");
        assert_eq!(t_in("Settings", portuguese), "Configurações");
    }

    #[test]
    fn every_extra_key_is_reachable_through_t_in() {
        for (index, table) in catalog::EXTRA_TABLES.iter().enumerate() {
            let language = TABLE_LANGUAGES[index];
            for (key, value) in *table {
                assert_eq!(t_in(key, language), *value, "{:?} {key:?}", language);
            }
        }
    }

    #[test]
    fn windows_only_key_translate_is_reachable() {
        assert!(catalog::TABLES[0]
            .iter()
            .all(|(key, _)| *key != "Translate"));
        assert!(catalog::EXTRA_TABLES[0]
            .iter()
            .any(|(key, _)| *key == "Translate"));
        assert_eq!(t_in("Translate", AppLanguage::Uk), "Перекласти");
        assert_eq!(t_in("Translate text", AppLanguage::Uk), "Перекласти текст");
    }

    #[test]
    fn set_language_switches_results() {
        let _guard = with_language(AppLanguage::Uk);
        assert_eq!(current_language(), AppLanguage::Uk);
        assert_eq!(t("Settings"), "Налаштування");
        assert_eq!(t("History"), "Історія");

        set_language(AppLanguage::De);
        assert_eq!(current_language(), AppLanguage::De);
        assert_eq!(t("Settings"), "Einstellungen");
        assert_eq!(t("Cancel"), "Abbrechen");

        set_language(AppLanguage::Fr);
        assert_eq!(current_language(), AppLanguage::Fr);
        assert_eq!(t("Copy"), "Copier");

        set_language(AppLanguage::En);
        assert_eq!(current_language(), AppLanguage::En);
        assert_eq!(t("Settings"), "Settings");
    }

    #[test]
    fn system_language_is_resolved_immediately() {
        let _guard = with_language(AppLanguage::System);
        assert_ne!(current_language(), AppLanguage::System);
        assert_eq!(current_language(), AppLanguage::system());
        assert_eq!(t("Settings"), t_in("Settings", current_language()));
    }

    #[test]
    fn available_languages_lists_english_first() {
        let languages = available_languages();
        assert_eq!(languages[0], AppLanguage::En);
        assert!(!languages.contains(&AppLanguage::System));
        let codes: Vec<&str> = languages.iter().map(|language| language.code()).collect();
        assert_eq!(
            codes,
            ["en", "uk", "ru", "de", "fr", "es", "pl", "pt", "it"]
        );
    }

    #[test]
    fn tf_formats_integer_placeholders() {
        let _guard = with_language(AppLanguage::Uk);
        assert_eq!(
            tf("Translating… %d of %d", &[&3, &10]),
            "Перекладаю… 3 з 10"
        );
        assert_eq!(tf("Models: %d", &[&3]), "Моделей: 3");
        assert_eq!(
            tf(
                "Some paragraphs are still in the original language (%d).",
                &[&2]
            ),
            "Деякі абзаци залишилися мовою оригіналу (2)."
        );

        set_language(AppLanguage::De);
        assert_eq!(tf("Models: %d", &[&7]), "Modelle: 7");
        assert_eq!(
            tf(
                "Some paragraphs are still in the original language (%d).",
                &[&2]
            ),
            "Einige Absätze sind noch in der Originalsprache (2)."
        );
    }

    #[test]
    fn tf_preserves_non_breaking_spaces() {
        let _guard = with_language(AppLanguage::Fr);
        // The French table uses a no-break space before the colon.
        assert_eq!(tf("Models: %d", &[&7]), "Modèles\u{a0}: 7");
    }

    #[test]
    fn tf_formats_object_placeholders() {
        let _guard = with_language(AppLanguage::Uk);
        assert_eq!(
            tf("Translate clipboard (%@)", &[&"Ctrl+Alt+T"]),
            "Перекласти буфер обміну (Ctrl+Alt+T)"
        );

        set_language(AppLanguage::De);
        assert_eq!(
            tf("Model “%@” not found", &[&"llama3"]),
            "Modell “llama3” nicht gefunden"
        );
        assert_eq!(
            tf("Server returned error %@: %@", &[&500, &"boom"]),
            "Server gab Fehler 500 zurück: boom"
        );
    }

    #[test]
    fn tf_formats_english_keys_in_place() {
        let _guard = with_language(AppLanguage::En);
        assert_eq!(tf("Models: %d", &[&4]), "Models: 4");
        assert_eq!(
            tf("Translate clipboard (%@)", &[&"Ctrl+Alt+T"]),
            "Translate clipboard (Ctrl+Alt+T)"
        );
    }

    #[test]
    fn tf_without_arguments_returns_the_translation() {
        let _guard = with_language(AppLanguage::De);
        assert_eq!(tf("Models: %d", &[]), "Modelle: %d");
    }

    #[test]
    fn tf_converts_double_percent_to_a_literal_percent() {
        let _guard = with_language(AppLanguage::En);
        assert_eq!(tf("100%% done %d", &[&50]), "100% done 50");
    }

    #[test]
    fn tf_leaves_missing_arguments_visible() {
        let _guard = with_language(AppLanguage::De);
        assert_eq!(tf("Translating… %d of %d", &[&3]), "Übersetze… 3 von %d");
    }

    #[test]
    fn tf_never_panics_and_ignores_extra_arguments() {
        let _guard = with_language(AppLanguage::De);
        let cases: [(&str, &[&dyn std::fmt::Display]); 7] = [
            ("Translating… %d of %d", &[&3]),
            ("Models: %d", &[&1, &2, &3]),
            ("Literal {braces} and %@", &[&"x"]),
            ("No placeholders at all", &[&1]),
            ("Unknown %@ key", &[&"x"]),
            ("", &[&"x"]),
            ("100%% done %d", &[&50]),
        ];
        for (key, args) in cases {
            let result = tf(key, args);
            assert!(result.is_char_boundary(result.len()));
        }
        // Braces are plain text in Rust, unlike the Python `str.format` port.
        assert_eq!(
            tf("Literal {braces} and %@", &[&"x"]),
            "Literal {braces} and x"
        );
        assert_eq!(tf("Models: %d", &[&1, &2, &3]), "Modelle: 1");
    }

    #[test]
    fn tf_handles_unknown_keys_and_empty_templates() {
        let _guard = with_language(AppLanguage::Uk);
        assert_eq!(tf("Unknown %@ key", &[&"x"]), "Unknown x key");
        assert_eq!(tf("", &[&"x"]), "");
        assert_eq!(tf("%s", &[&"value"]), "value");
        assert_eq!(tf("%.1f s", &[&1.5]), "1.5 с");
    }
}
