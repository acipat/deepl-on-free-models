//! Language metadata, localised display names and stop words.
//!
//! **Generated file -- do not edit.**  Regenerate it with
//! `python3 rust/scripts/gen_i18n.py` from the checkout root.
//!
//! Everything here comes from `windows/deepl_ofm/core/languages.py`, the
//! behavioural reference of the port; `language.rs` holds the algorithms
//! that consume it.

use crate::language::Language;
use crate::AppLanguage;

/// The 38 Hy-MT2 languages, in the order of the Swift `Language` enum.
#[rustfmt::skip]
pub(crate) static ALL: [Language; 38] = [
    Language { code: "zh", english_name: "Chinese", local_name: "китайська", bcp47: Some("zh-CN") },
    Language { code: "en", english_name: "English", local_name: "англійська", bcp47: Some("en-US") },
    Language { code: "fr", english_name: "French", local_name: "французька", bcp47: Some("fr-FR") },
    Language { code: "pt", english_name: "Portuguese", local_name: "португальська", bcp47: Some("pt-PT") },
    Language { code: "es", english_name: "Spanish", local_name: "іспанська", bcp47: Some("es-ES") },
    Language { code: "ja", english_name: "Japanese", local_name: "японська", bcp47: Some("ja-JP") },
    Language { code: "tr", english_name: "Turkish", local_name: "турецька", bcp47: Some("tr-TR") },
    Language { code: "ru", english_name: "Russian", local_name: "російська", bcp47: Some("ru-RU") },
    Language { code: "ar", english_name: "Arabic", local_name: "арабська", bcp47: Some("ar-SA") },
    Language { code: "ko", english_name: "Korean", local_name: "корейська", bcp47: Some("ko-KR") },
    Language { code: "th", english_name: "Thai", local_name: "тайська", bcp47: Some("th-TH") },
    Language { code: "it", english_name: "Italian", local_name: "італійська", bcp47: Some("it-IT") },
    Language { code: "de", english_name: "German", local_name: "німецька", bcp47: Some("de-DE") },
    Language { code: "vi", english_name: "Vietnamese", local_name: "в'єтнамська", bcp47: Some("vi-VN") },
    Language { code: "ms", english_name: "Malay", local_name: "малайська", bcp47: Some("ms-MY") },
    Language { code: "id", english_name: "Indonesian", local_name: "індонезійська", bcp47: Some("id-ID") },
    Language { code: "tl", english_name: "Filipino", local_name: "філіппінська", bcp47: Some("fil-PH") },
    Language { code: "hi", english_name: "Hindi", local_name: "гінді", bcp47: Some("hi-IN") },
    Language { code: "zh-Hant", english_name: "Traditional Chinese", local_name: "китайська (традиційна)", bcp47: Some("zh-TW") },
    Language { code: "pl", english_name: "Polish", local_name: "польська", bcp47: Some("pl-PL") },
    Language { code: "cs", english_name: "Czech", local_name: "чеська", bcp47: Some("cs-CZ") },
    Language { code: "nl", english_name: "Dutch", local_name: "нідерландська", bcp47: Some("nl-NL") },
    Language { code: "km", english_name: "Khmer", local_name: "кхмерська", bcp47: Some("km-KH") },
    Language { code: "my", english_name: "Burmese", local_name: "бірманська", bcp47: Some("my-MM") },
    Language { code: "fa", english_name: "Persian", local_name: "перська", bcp47: Some("fa-IR") },
    Language { code: "gu", english_name: "Gujarati", local_name: "гуджараті", bcp47: Some("gu-IN") },
    Language { code: "ur", english_name: "Urdu", local_name: "урду", bcp47: Some("ur-PK") },
    Language { code: "te", english_name: "Telugu", local_name: "телугу", bcp47: Some("te-IN") },
    Language { code: "mr", english_name: "Marathi", local_name: "маратхі", bcp47: Some("mr-IN") },
    Language { code: "he", english_name: "Hebrew", local_name: "іврит", bcp47: Some("he-IL") },
    Language { code: "bn", english_name: "Bengali", local_name: "бенгальська", bcp47: Some("bn-BD") },
    Language { code: "ta", english_name: "Tamil", local_name: "тамільська", bcp47: Some("ta-IN") },
    Language { code: "uk", english_name: "Ukrainian", local_name: "українська", bcp47: Some("uk-UA") },
    Language { code: "bo", english_name: "Tibetan", local_name: "тибетська", bcp47: Some("bo-CN") },
    Language { code: "kk", english_name: "Kazakh", local_name: "казахська", bcp47: Some("kk-KZ") },
    Language { code: "mn", english_name: "Mongolian", local_name: "монгольська", bcp47: Some("mn-MN") },
    Language { code: "ug", english_name: "Uyghur", local_name: "уйгурська", bcp47: Some("ug-CN") },
    Language { code: "yue", english_name: "Cantonese", local_name: "кантонська", bcp47: Some("yue-HK") },
];

/// Localised language names: `(code, [ru, de, fr, es, pl, pt, it])`.
///
/// Ported verbatim from `_LOCALIZED_NAMES`; the column order matches
/// [`NAME_COLUMNS`].
#[rustfmt::skip]
pub(crate) static LOCALIZED_NAMES: &[(&str, [&str; 7])] = &[
    ("ar", ["арабский", "Arabisch", "arabe", "árabe", "arabski", "árabe", "arabo"]),
    ("bn", ["бенгальский", "Bengalisch", "bengali", "bengalí", "bengalski", "bengali", "bengalese"]),
    ("bo", ["тибетский", "Tibetisch", "tibétain", "tibetano", "tybetański", "tibetano", "tibetano"]),
    ("cs", ["чешский", "Tschechisch", "tchèque", "checo", "czeski", "checo", "ceco"]),
    ("de", ["немецкий", "Deutsch", "allemand", "alemán", "niemiecki", "alemão", "tedesco"]),
    ("en", ["английский", "Englisch", "anglais", "inglés", "angielski", "inglês", "inglese"]),
    ("es", ["испанский", "Spanisch", "espagnol", "español", "hiszpański", "espanhol", "spagnolo"]),
    ("fa", ["персидский", "Persisch", "persan", "persa", "perski", "persa", "persiano"]),
    ("fr", ["французский", "Französisch", "français", "francés", "francuski", "francês", "francese"]),
    ("gu", ["гуджарати", "Gujarati", "gujarati", "guyaratí", "gudżarati", "guzerate", "gujarati"]),
    ("he", ["иврит", "Hebräisch", "hébreu", "hebreo", "hebrajski", "hebraico", "ebraico"]),
    ("hi", ["хинди", "Hindi", "hindi", "hindi", "hindi", "híndi", "hindi"]),
    ("id", ["индонезийский", "Indonesisch", "indonésien", "indonesio", "indonezyjski", "indonésio", "indonesiano"]),
    ("it", ["итальянский", "Italienisch", "italien", "italiano", "włoski", "italiano", "italiano"]),
    ("ja", ["японский", "Japanisch", "japonais", "japonés", "japoński", "japonês", "giapponese"]),
    ("kk", ["казахский", "Kasachisch", "kazakh", "kazajo", "kazachski", "cazaque", "kazako"]),
    ("km", ["кхмерский", "Khmer", "khmer", "jemer", "khmerski", "khmer", "khmer"]),
    ("ko", ["корейский", "Koreanisch", "coréen", "coreano", "koreański", "coreano", "coreano"]),
    ("mn", ["монгольский", "Mongolisch", "mongol", "mongol", "mongolski", "mongol", "mongolo"]),
    ("mr", ["маратхи", "Marathi", "marathi", "maratí", "marathi", "marata", "marathi"]),
    ("ms", ["малайский", "Malaiisch", "malais", "malayo", "malajski", "malaio", "malese"]),
    ("my", ["бирманский", "Birmanisch", "birman", "birmano", "birmański", "birmanês", "birmano"]),
    ("nl", ["нидерландский", "Niederländisch", "néerlandais", "neerlandés", "niderlandzki", "neerlandês", "olandese"]),
    ("pl", ["польский", "Polnisch", "polonais", "polaco", "polski", "polaco", "polacco"]),
    ("pt", ["португальский", "Portugiesisch", "portugais", "portugués", "portugalski", "português", "portoghese"]),
    ("ru", ["русский", "Russisch", "russe", "ruso", "rosyjski", "russo", "russo"]),
    ("ta", ["тамильский", "Tamil", "tamoul", "tamil", "tamilski", "tâmil", "tamil"]),
    ("te", ["телугу", "Telugu", "télougou", "telugu", "telugu", "telugu", "telugu"]),
    ("th", ["тайский", "Thailändisch", "thaï", "tailandés", "tajski", "tailandês", "thailandese"]),
    ("tl", ["филиппинский", "Filipino", "philippin", "filipino", "filipiński", "filipino", "filippino"]),
    ("tr", ["турецкий", "Türkisch", "turc", "turco", "turecki", "turco", "turco"]),
    ("ug", ["уйгурский", "Uigurisch", "ouïghour", "uigur", "ujgurski", "uigure", "uiguro"]),
    ("uk", ["украинский", "Ukrainisch", "ukrainien", "ucraniano", "ukraiński", "ucraniano", "ucraino"]),
    ("ur", ["урду", "Urdu", "ourdou", "urdu", "urdu", "urdu", "urdu"]),
    ("vi", ["вьетнамский", "Vietnamesisch", "vietnamien", "vietnamita", "wietnamski", "vietnamita", "vietnamita"]),
    ("yue", ["кантонский", "Kantonesisch", "cantonais", "cantonés", "kantoński", "cantonês", "cantonese"]),
    ("zh", ["китайский", "Chinesisch", "chinois", "chino", "chiński", "chinês", "cinese"]),
    ("zh-Hant", ["китайский (традиционный)", "Chinesisch (traditionell)", "chinois traditionnel", "chino tradicional", "chiński tradycyjny", "chinês tradicional", "cinese tradizionale"]),
];

/// Interface languages with curated display names, in column order.
#[rustfmt::skip]
pub(crate) static NAME_COLUMNS: [AppLanguage; 7] = [
    AppLanguage::Ru, AppLanguage::De, AppLanguage::Fr, AppLanguage::Es, AppLanguage::Pl, AppLanguage::Pt, AppLanguage::It,
];

/// Localised display name of `code` for the interface language `ui`.
///
/// `None` when the pair is not curated; the caller then falls back to
/// [`Language::english_name`].
pub(crate) fn localized_name(code: &str, ui: AppLanguage) -> Option<&'static str> {
    let column = NAME_COLUMNS.iter().position(|language| *language == ui)?;
    let (_, names) = LOCALIZED_NAMES
        .iter()
        .find(|(candidate, _)| *candidate == code)?;
    names.get(column).copied()
}

/// Words that score Ukrainian in the Cyrillic heuristic.
#[rustfmt::skip]
pub(crate) static UKRAINIAN_WORDS: &[&str] = &[
    "або", "безкоштовно", "було", "вже", "ви", "вони", "його", "локальні", "мене", "ми", "мова",
    "можна", "переклад", "потрібно", "провайдери", "після", "рядки", "рядок", "також", "тебе",
    "хмарні", "цей", "цього", "ця", "ці", "ще", "що", "яка", "який", "які", "її",
];

/// Words that score Russian in the Cyrillic heuristic.
#[rustfmt::skip]
pub(crate) static RUSSIAN_WORDS: &[&str] = &[
    "бесплатно", "было", "вы", "его", "еще", "ещё", "её", "или", "которая", "которые", "который",
    "локальные", "меня", "можно", "мы", "нужно", "облачные", "они", "перевод", "после",
    "провайдеры", "строка", "строки", "также", "тебя", "что", "эта", "эти", "это", "этого", "этот",
    "язык",
];

/// Latin languages of the stop-word scorer, in tie-break order.
#[rustfmt::skip]
pub(crate) static LATIN_ORDER: [&str; 12] = [
    "en", "fr", "de", "es", "pt", "it", "pl", "nl", "tr", "vi", "id", "ms",
];

/// Folded stop words for each [`LATIN_ORDER`] language.
#[rustfmt::skip]
pub(crate) static LATIN_STOP_WORDS: [&[&str]; 12] = [
    &[
        "about", "above", "after", "again", "all", "also", "and", "any", "are", "as", "at", "be",
        "because", "been", "before", "being", "below", "between", "both", "but", "by", "can",
        "could", "did", "do", "does", "during", "each", "few", "for", "from", "had", "has", "have",
        "he", "hello", "her", "here", "his", "how", "if", "in", "into", "is", "it", "its", "just",
        "me", "more", "most", "my", "no", "not", "of", "on", "once", "one", "only", "or", "other",
        "our", "out", "own", "please", "same", "she", "should", "so", "some", "such", "than",
        "thanks", "that", "the", "their", "them", "then", "there", "these", "they", "this",
        "those", "through", "to", "too", "two", "up", "very", "was", "we", "were", "what", "when",
        "where", "which", "while", "who", "whom", "why", "will", "with", "would", "you", "your",
    ],
    &[
        "a", "ainsi", "alors", "apres", "au", "aussi", "aux", "avant", "avec", "avoir", "bien",
        "bonjour", "ce", "ceci", "cela", "celle", "celui", "ces", "cette", "chez", "comme",
        "comment", "dans", "de", "deja", "depuis", "des", "dit", "dois", "doit", "donc", "dont",
        "du", "elle", "elles", "en", "encore", "entre", "est", "et", "etaient", "etait", "etre",
        "faire", "fait", "il", "ils", "jamais", "je", "la", "le", "les", "leur", "leurs", "ma",
        "mais", "merci", "mes", "mon", "non", "notre", "nous", "ou", "oui", "par", "pas",
        "pendant", "peut", "peuvent", "plus", "pour", "pourquoi", "quand", "que", "quel", "quelle",
        "quelles", "quels", "qui", "sa", "salut", "sans", "sera", "seront", "ses", "son", "sont",
        "sous", "sur", "ta", "tes", "ton", "toujours", "tous", "tout", "toute", "toutes", "tres",
        "tu", "un", "une", "vers", "veut", "veux", "votre", "vous",
    ],
    &[
        "aber", "als", "auch", "auf", "aus", "bei", "bitte", "danke", "dann", "das", "dass",
        "dein", "deine", "dem", "den", "der", "des", "die", "diese", "diesem", "diesen", "dieser",
        "dieses", "dort", "du", "durch", "ein", "eine", "einem", "einen", "einer", "eines", "er",
        "es", "euer", "fur", "gegen", "guten", "haben", "hallo", "hat", "hatte", "hier", "ich",
        "ihr", "ihre", "im", "in", "ist", "ja", "kann", "konnen", "mehr", "mein", "meine", "mit",
        "muss", "mussen", "nach", "nein", "nicht", "noch", "nur", "oder", "ohne", "sehr", "sein",
        "seine", "sich", "sie", "sind", "so", "tag", "uber", "um", "und", "unsere", "unter", "von",
        "war", "waren", "warum", "was", "weil", "wenn", "wer", "werden", "wie", "wir", "wird",
        "wo", "worden", "wurde", "zu", "zum", "zur", "zwischen",
    ],
    &[
        "al", "bien", "buenos", "como", "con", "cuando", "de", "del", "dias", "dice", "dijo",
        "donde", "el", "en", "entre", "es", "esa", "esas", "ese", "esos", "esta", "estan", "estar",
        "estas", "este", "estos", "fue", "gracias", "ha", "hace", "hacer", "han", "hay", "he",
        "hola", "la", "las", "le", "les", "lo", "los", "mal", "mas", "me", "mi", "mis", "muy",
        "no", "nos", "nuestra", "nuestro", "o", "os", "otra", "otras", "otro", "otros", "para",
        "pero", "por", "porque", "puede", "pueden", "que", "se", "ser", "servicio", "si", "sin",
        "sobre", "son", "su", "sus", "tambien", "te", "tiene", "tienen", "toda", "todas", "todo",
        "todos", "tu", "tus", "un", "una", "unas", "unos", "y", "ya",
    ],
    &[
        "ao", "aos", "aquilo", "as", "bom", "com", "como", "da", "das", "de", "dia", "disse",
        "diz", "do", "dos", "e", "em", "entre", "essa", "esse", "esta", "estao", "estar", "estas",
        "este", "estes", "faz", "fazer", "foi", "funciona", "ha", "isso", "isto", "ja", "lhe",
        "mais", "mas", "me", "meu", "minha", "muito", "na", "nao", "nas", "no", "nos", "nossa",
        "nosso", "num", "numa", "o", "obrigado", "ola", "onde", "os", "ou", "para", "pela",
        "pelas", "pelo", "pelos", "pode", "podem", "por", "porque", "quando", "que", "sao", "se",
        "sem", "ser", "servico", "seu", "seus", "sim", "sobre", "sua", "suas", "tambem", "te",
        "tem", "toda", "todas", "todo", "todos", "traducao", "um", "uma", "umas", "uns", "voce",
        "voces", "vos",
    ],
    &[
        "ai", "al", "alla", "alle", "allo", "anche", "bene", "buongiorno", "che", "ciao", "come",
        "con", "dei", "del", "della", "delle", "detto", "di", "dice", "dove", "e", "essere", "fa",
        "fare", "fra", "fu", "gia", "gli", "grazie", "ha", "hanno", "ho", "i", "il", "la", "le",
        "lo", "ma", "male", "mia", "mio", "molto", "nel", "nella", "non", "nostra", "nostro",
        "per", "perche", "piu", "possono", "puo", "quando", "quella", "quello", "questa", "queste",
        "questi", "questo", "senza", "si", "sono", "stare", "stato", "su", "sua", "sue", "suo",
        "suoi", "tra", "tutta", "tutte", "tutti", "tutto", "un", "una", "uno",
    ],
    &[
        "albo", "ale", "bardzo", "bez", "był", "była", "było", "były", "czesc", "czy", "dla", "do",
        "dobry", "dziekuje", "dzien", "i", "jak", "jest", "jeszcze", "juz", "ktora", "ktore",
        "ktory", "ktorych", "lub", "ma", "maja", "miec", "miedzy", "moze", "mozna", "na", "nad",
        "nie", "o", "od", "oraz", "po", "pod", "przez", "przy", "sa", "sie", "ta", "tak", "te",
        "tego", "tej", "ten", "to", "tych", "tylko", "tym", "w", "z", "za", "ze",
    ],
    &[
        "aan", "al", "als", "bij", "dank", "dat", "de", "deze", "die", "dit", "door", "een", "en",
        "goedemorgen", "haar", "had", "hallo", "hebben", "heeft", "heel", "het", "hij", "hun",
        "ik", "in", "is", "je", "jij", "jouw", "jullie", "kan", "kunnen", "maar", "met", "mijn",
        "moet", "moeten", "naar", "niet", "nog", "of", "om", "onder", "ons", "ook", "op", "over",
        "te", "tegen", "tussen", "u", "uit", "van", "voor", "waren", "was", "we", "wij", "ze",
        "zeer", "zij", "zijn", "zonder",
    ],
    &[
        "ama", "bazı", "ben", "benim", "bir", "biz", "bizim", "bu", "cok", "cunku", "da", "daha",
        "de", "degil", "en", "fakat", "gibi", "her", "icin", "ile", "ki", "merhaba", "mi", "mu",
        "mı", "nasıl", "ne", "neden", "o", "olan", "olarak", "onlar", "onların", "onun", "sen",
        "senin", "siz", "sizin", "su", "tesekkur", "tum", "var", "ve", "veya", "ya", "yok",
    ],
    &[
        "anh", "ban", "cac", "cam", "chao", "chi", "cho", "chung", "co", "cua", "cung", "duoi",
        "em", "ho", "hoac", "khi", "khong", "la", "ma", "mot", "nay", "nguoi", "nhu", "nhung",
        "on", "rat", "se", "theo", "thi", "toi", "tren", "trong", "tu", "va", "ve", "viec", "voi",
        "xin", "đa", "đang", "đe", "đen", "đo", "đuoc",
    ],
    &[
        "ada", "adalah", "akan", "atau", "bahasa", "baik", "banyak", "bisa", "buku", "dalam",
        "dan", "dapat", "dari", "dengan", "di", "dia", "dunia", "ini", "itu", "jika", "juga",
        "kami", "kamu", "karena", "kasih", "ke", "ketika", "kita", "lebih", "mereka", "oleh",
        "orang", "pada", "pagi", "sangat", "satu", "saya", "sebelum", "sebuah", "selamat", "semua",
        "setelah", "sudah", "telah", "terima", "terjemahan", "tes", "tetapi", "tidak", "untuk",
        "yang",
    ],
    &[
        "akan", "anda", "apabila", "atau", "awak", "bahasa", "baik", "banyak", "boleh", "dalam",
        "dan", "dapat", "dari", "dengan", "di", "dia", "ialah", "ini", "itu", "jika", "juga",
        "kami", "kamu", "kasih", "ke", "kerana", "kita", "lebih", "mereka", "oleh", "pada", "pagi",
        "sangat", "satu", "saya", "sebelum", "selamat", "selepas", "semua", "telah", "terima",
        "terjemahan", "tetapi", "tiada", "tidak", "ujian", "untuk", "yang",
    ],
];

/// Lower-case Latin characters whose NFKD decomposition starts with a
/// different character, mapped to that base character (`'é' -> 'e'`).
///
/// Dependency-free stand-in for `unicodedata.normalize("NFKD", ...)` plus
/// `str.casefold()`, used by the stop-word scorer so that `cómo` matches
/// the stop word `como`.  Sorted by source character; entries whose
/// casefolded form has more than one character (`ß` -> `ss`) are omitted
/// because no stop word depends on them.
#[rustfmt::skip]
pub(crate) static FOLD_PAIRS: &[(char, char)] = &[
    ('ª', 'a'), ('µ', 'μ'), ('º', 'o'), ('à', 'a'), ('á', 'a'),
    ('â', 'a'), ('ã', 'a'), ('ä', 'a'), ('å', 'a'), ('ç', 'c'),
    ('è', 'e'), ('é', 'e'), ('ê', 'e'), ('ë', 'e'), ('ì', 'i'),
    ('í', 'i'), ('î', 'i'), ('ï', 'i'), ('ñ', 'n'), ('ò', 'o'),
    ('ó', 'o'), ('ô', 'o'), ('õ', 'o'), ('ö', 'o'), ('ù', 'u'),
    ('ú', 'u'), ('û', 'u'), ('ü', 'u'), ('ý', 'y'), ('ÿ', 'y'),
    ('ā', 'a'), ('ă', 'a'), ('ą', 'a'), ('ć', 'c'), ('ĉ', 'c'),
    ('ċ', 'c'), ('č', 'c'), ('ď', 'd'), ('ē', 'e'), ('ĕ', 'e'),
    ('ė', 'e'), ('ę', 'e'), ('ě', 'e'), ('ĝ', 'g'), ('ğ', 'g'),
    ('ġ', 'g'), ('ģ', 'g'), ('ĥ', 'h'), ('ĩ', 'i'), ('ī', 'i'),
    ('ĭ', 'i'), ('į', 'i'), ('ĵ', 'j'), ('ķ', 'k'), ('ĺ', 'l'),
    ('ļ', 'l'), ('ľ', 'l'), ('ń', 'n'), ('ņ', 'n'), ('ň', 'n'),
    ('ō', 'o'), ('ŏ', 'o'), ('ő', 'o'), ('ŕ', 'r'), ('ŗ', 'r'),
    ('ř', 'r'), ('ś', 's'), ('ŝ', 's'), ('ş', 's'), ('š', 's'),
    ('ţ', 't'), ('ť', 't'), ('ũ', 'u'), ('ū', 'u'), ('ŭ', 'u'),
    ('ů', 'u'), ('ű', 'u'), ('ų', 'u'), ('ŵ', 'w'), ('ŷ', 'y'),
    ('ź', 'z'), ('ż', 'z'), ('ž', 'z'), ('ſ', 's'), ('ơ', 'o'),
    ('ư', 'u'), ('ǎ', 'a'), ('ǐ', 'i'), ('ǒ', 'o'), ('ǔ', 'u'),
    ('ǖ', 'u'), ('ǘ', 'u'), ('ǚ', 'u'), ('ǜ', 'u'), ('ǟ', 'a'),
    ('ǡ', 'a'), ('ǣ', 'æ'), ('ǧ', 'g'), ('ǩ', 'k'), ('ǫ', 'o'),
    ('ǭ', 'o'), ('ǯ', 'ʒ'), ('ǰ', 'j'), ('ǵ', 'g'), ('ǹ', 'n'),
    ('ǻ', 'a'), ('ǽ', 'æ'), ('ǿ', 'ø'), ('ȁ', 'a'), ('ȃ', 'a'),
    ('ȅ', 'e'), ('ȇ', 'e'), ('ȉ', 'i'), ('ȋ', 'i'), ('ȍ', 'o'),
    ('ȏ', 'o'), ('ȑ', 'r'), ('ȓ', 'r'), ('ȕ', 'u'), ('ȗ', 'u'),
    ('ș', 's'), ('ț', 't'), ('ȟ', 'h'), ('ȧ', 'a'), ('ȩ', 'e'),
    ('ȫ', 'o'), ('ȭ', 'o'), ('ȯ', 'o'), ('ȱ', 'o'), ('ȳ', 'y'),
    ('ḁ', 'a'), ('ḃ', 'b'), ('ḅ', 'b'), ('ḇ', 'b'), ('ḉ', 'c'),
    ('ḋ', 'd'), ('ḍ', 'd'), ('ḏ', 'd'), ('ḑ', 'd'), ('ḓ', 'd'),
    ('ḕ', 'e'), ('ḗ', 'e'), ('ḙ', 'e'), ('ḛ', 'e'), ('ḝ', 'e'),
    ('ḟ', 'f'), ('ḡ', 'g'), ('ḣ', 'h'), ('ḥ', 'h'), ('ḧ', 'h'),
    ('ḩ', 'h'), ('ḫ', 'h'), ('ḭ', 'i'), ('ḯ', 'i'), ('ḱ', 'k'),
    ('ḳ', 'k'), ('ḵ', 'k'), ('ḷ', 'l'), ('ḹ', 'l'), ('ḻ', 'l'),
    ('ḽ', 'l'), ('ḿ', 'm'), ('ṁ', 'm'), ('ṃ', 'm'), ('ṅ', 'n'),
    ('ṇ', 'n'), ('ṉ', 'n'), ('ṋ', 'n'), ('ṍ', 'o'), ('ṏ', 'o'),
    ('ṑ', 'o'), ('ṓ', 'o'), ('ṕ', 'p'), ('ṗ', 'p'), ('ṙ', 'r'),
    ('ṛ', 'r'), ('ṝ', 'r'), ('ṟ', 'r'), ('ṡ', 's'), ('ṣ', 's'),
    ('ṥ', 's'), ('ṧ', 's'), ('ṩ', 's'), ('ṫ', 't'), ('ṭ', 't'),
    ('ṯ', 't'), ('ṱ', 't'), ('ṳ', 'u'), ('ṵ', 'u'), ('ṷ', 'u'),
    ('ṹ', 'u'), ('ṻ', 'u'), ('ṽ', 'v'), ('ṿ', 'v'), ('ẁ', 'w'),
    ('ẃ', 'w'), ('ẅ', 'w'), ('ẇ', 'w'), ('ẉ', 'w'), ('ẋ', 'x'),
    ('ẍ', 'x'), ('ẏ', 'y'), ('ẑ', 'z'), ('ẓ', 'z'), ('ẕ', 'z'),
    ('ẖ', 'h'), ('ẗ', 't'), ('ẘ', 'w'), ('ẙ', 'y'), ('ẛ', 's'),
    ('ạ', 'a'), ('ả', 'a'), ('ấ', 'a'), ('ầ', 'a'), ('ẩ', 'a'),
    ('ẫ', 'a'), ('ậ', 'a'), ('ắ', 'a'), ('ằ', 'a'), ('ẳ', 'a'),
    ('ẵ', 'a'), ('ặ', 'a'), ('ẹ', 'e'), ('ẻ', 'e'), ('ẽ', 'e'),
    ('ế', 'e'), ('ề', 'e'), ('ể', 'e'), ('ễ', 'e'), ('ệ', 'e'),
    ('ỉ', 'i'), ('ị', 'i'), ('ọ', 'o'), ('ỏ', 'o'), ('ố', 'o'),
    ('ồ', 'o'), ('ổ', 'o'), ('ỗ', 'o'), ('ộ', 'o'), ('ớ', 'o'),
    ('ờ', 'o'), ('ở', 'o'), ('ỡ', 'o'), ('ợ', 'o'), ('ụ', 'u'),
    ('ủ', 'u'), ('ứ', 'u'), ('ừ', 'u'), ('ử', 'u'), ('ữ', 'u'),
    ('ự', 'u'), ('ỳ', 'y'), ('ỵ', 'y'), ('ỷ', 'y'), ('ỹ', 'y'),
];
