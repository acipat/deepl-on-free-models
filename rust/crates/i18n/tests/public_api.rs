//! Integration tests for the public `ofm-i18n` API.
//!
//! The unit tests inside the crate also cover the generated tables; this file
//! only uses what `ofm-app`, `ofm-net` and the desktop shell can see.

use std::sync::{Mutex, MutexGuard};

use ofm_i18n::{
    available_languages, current_language, set_language, t, t_in, tf, AppLanguage, LanguageTable,
};

/// Serialises the tests that change the global interface language.
static LANGUAGE_LOCK: Mutex<()> = Mutex::new(());

/// Lock the global language cell for the duration of a test.
fn lock_language() -> MutexGuard<'static, ()> {
    LANGUAGE_LOCK
        .lock()
        .unwrap_or_else(|error| error.into_inner())
}

#[test]
fn interface_languages_translate_a_known_key() {
    let expected = [
        (AppLanguage::En, "Settings"),
        (AppLanguage::Uk, "Налаштування"),
        (AppLanguage::Ru, "Настройки"),
        (AppLanguage::De, "Einstellungen"),
        (AppLanguage::Fr, "Paramètres"),
        (AppLanguage::Es, "Configuración"),
        (AppLanguage::Pl, "Ustawienia"),
        (AppLanguage::Pt, "Configurações"),
        (AppLanguage::It, "Impostazioni"),
    ];
    for (language, translation) in expected {
        assert_eq!(t_in("Settings", language), translation);
    }
}

#[test]
fn missing_keys_and_unknown_languages_do_not_panic() {
    assert_eq!(t_in("no such key", AppLanguage::Uk), "no such key");
    assert_eq!(AppLanguage::from_code("zz"), None);
    assert_eq!(LanguageTable::get("zz"), None);
    assert_eq!(LanguageTable::detect("", AppLanguage::System), None);
}

#[test]
fn the_global_language_is_thread_safe_and_switchable() {
    let _guard = lock_language();
    let original = current_language();
    set_language(AppLanguage::Uk);
    assert_eq!(current_language(), AppLanguage::Uk);
    assert_eq!(t("Cancel"), "Скасувати");

    set_language(AppLanguage::It);
    assert_eq!(t("Cancel"), "Annulla");
    assert_eq!(tf("Models: %d", &[&7]), "Modelli: 7");

    set_language(AppLanguage::System);
    assert_ne!(current_language(), AppLanguage::System);

    set_language(original);
    assert_eq!(current_language(), original);
}

#[test]
fn available_languages_are_the_nine_interface_languages() {
    let codes: Vec<&str> = available_languages()
        .iter()
        .map(|language| language.code())
        .collect();
    assert_eq!(
        codes,
        ["en", "uk", "ru", "de", "fr", "es", "pl", "pt", "it"]
    );
}

#[test]
fn detection_prefers_the_requested_cyrillic_language_on_a_tie() {
    let ukrainian = LanguageTable::detect("ключ", AppLanguage::Uk);
    let russian = LanguageTable::detect("ключ", AppLanguage::Ru);
    assert_eq!(ukrainian.map(|language| language.code), Some("uk"));
    assert_eq!(russian.map(|language| language.code), Some("ru"));
}

#[test]
fn language_metadata_is_complete() {
    let all = LanguageTable::all();
    assert_eq!(all.len(), 38);
    for language in all {
        assert!(!language.english_name.is_empty());
        assert!(language.bcp47.is_some());
        assert!(!language.display_name(AppLanguage::En).is_empty());
    }
    assert!(LanguageTable::AUTO.is_auto());
}

#[test]
fn placeholders_are_filled_in_order() {
    let _guard = lock_language();
    assert_eq!(
        t_in("Translating… %d of %d", AppLanguage::Uk),
        "Перекладаю… %d з %d"
    );
    set_language(AppLanguage::Uk);
    assert_eq!(
        tf("Translating… %d of %d", &[&3, &10]),
        "Перекладаю… 3 з 10"
    );
    // A wrong argument count keeps the placeholder visible instead of panicking.
    assert_eq!(tf("Translating… %d of %d", &[&3]), "Перекладаю… 3 з %d");
    set_language(AppLanguage::En);
}
