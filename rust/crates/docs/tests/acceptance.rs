//! Acceptance tests ported from `windows/tests/test_documents.py` and
//! `windows/tests/test_text_encodings.py`.
//!
//! Fixtures are generated in the tests: a DOCX package is zipped here, PDFs are
//! built with `lopdf`, and text files are written with CRLF/BOM/cp1251 bytes.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};

use lopdf::{dictionary, Document, Object, Stream};
use ofm_docs::{
    cjk_font_available, system_font_available, DocumentErrorKind, DocumentKind, DocumentTranslator,
};
use ofm_i18n::{Language, LanguageTable};
use zip::write::SimpleFileOptions;
use zip::{CompressionMethod, ZipArchive, ZipWriter};

// ---------------------------------------------------------------------------
// Helpers

fn target(code: &str) -> &'static Language {
    LanguageTable::get(code).expect("known language")
}

fn approx(actual: f32, expected: f32) -> bool {
    (actual - expected).abs() < 0.01
}

fn escape_pdf(text: &str) -> String {
    text.replace('\\', "\\\\")
        .replace('(', "\\(")
        .replace(')', "\\)")
}

const WORD_NS: &str = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";

const CONTENT_TYPES: &[u8] = b"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\
<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">\
<Default Extension=\"xml\" ContentType=\"application/xml\"/>\
<Default Extension=\"bin\" ContentType=\"application/octet-stream\"/>\
<Override PartName=\"/word/document.xml\"\
 ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>\
</Types>";

const RELS: &[u8] = b"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\
<Relationship Id=\"rId1\"\
 Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\"\
 Target=\"word/document.xml\"/></Relationships>";

const STYLES: &[u8] = b"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\
<w:styles xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">\
<w:style w:type=\"paragraph\" w:styleId=\"Normal\">\
<w:name w:val=\"Normal\"/></w:style></w:styles>";

fn document_xml() -> Vec<u8> {
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\
         <w:document xmlns:w=\"{WORD_NS}\" \
         xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" \
         xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" \
         mc:Ignorable=\"w14\"><w:body>\
         <w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr>\
         <w:r><w:rPr><w:b/></w:rPr><w:t>Hello </w:t></w:r>\
         <w:r><w:t>world</w:t></w:r></w:p>\
         <w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p>\
         <w:p/>\
         </w:body></w:document>"
    )
    .into_bytes()
}

fn image_bytes() -> Vec<u8> {
    (0..768).map(|index| (index % 256) as u8).collect()
}

fn make_docx(path: &Path) {
    let mut archive = ZipWriter::new(fs::File::create(path).unwrap());
    let deflated = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);
    for (name, data) in [
        ("[Content_Types].xml", CONTENT_TYPES),
        ("_rels/.rels", RELS),
        ("word/document.xml", &document_xml()),
        ("word/styles.xml", STYLES),
    ] {
        archive.start_file(name, deflated).unwrap();
        archive.write_all(data).unwrap();
    }
    let stored = SimpleFileOptions::default()
        .compression_method(CompressionMethod::Stored)
        .last_modified_time(zip::DateTime::from_date_and_time(2024, 1, 2, 3, 4, 6).unwrap());
    archive.start_file("word/media/image1.bin", stored).unwrap();
    archive.write_all(&image_bytes()).unwrap();
    archive.finish().unwrap();
}

fn empty_docx(path: &Path) {
    let xml = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\
         <w:document xmlns:w=\"{WORD_NS}\"><w:body>\
         <w:p><w:r><w:t>   </w:t></w:r></w:p></w:body></w:document>"
    );
    let mut archive = ZipWriter::new(fs::File::create(path).unwrap());
    archive
        .start_file("[Content_Types].xml", SimpleFileOptions::default())
        .unwrap();
    archive.write_all(CONTENT_TYPES).unwrap();
    archive
        .start_file("word/document.xml", SimpleFileOptions::default())
        .unwrap();
    archive.write_all(xml.as_bytes()).unwrap();
    archive.finish().unwrap();
}

fn media_box() -> Object {
    Object::Array(vec![
        Object::Integer(0),
        Object::Integer(0),
        Object::Integer(400),
        Object::Integer(300),
    ])
}

fn make_pdf(path: &Path, pages: &[&[&str]]) {
    let mut document = Document::with_version("1.5");
    let pages_id = document.new_object_id();
    let font_id = document.add_object(dictionary! {
        "Type" => "Font",
        "Subtype" => "Type1",
        "BaseFont" => "Helvetica",
        "Encoding" => "WinAnsiEncoding",
    });
    let mut kids = Vec::new();
    for lines in pages {
        let mut content = String::new();
        if lines.is_empty() {
            content.push_str("0.8 0.1 0.1 RG\n2 w\n30 200 80 40 re\nS\n");
        } else {
            content.push_str("BT\n/F1 14 Tf\n");
            let mut baseline = 250.0f64;
            for line in *lines {
                content.push_str(&format!(
                    "1 0 0 1 50 {baseline} Tm\n({}) Tj\n",
                    escape_pdf(line)
                ));
                baseline -= 30.0;
            }
            content.push_str("ET\n");
        }
        let content_id =
            document.add_object(Stream::new(lopdf::Dictionary::new(), content.into_bytes()));
        let page_id = document.add_object(dictionary! {
            "Type" => "Page",
            "Parent" => pages_id,
            "Contents" => content_id,
            "Resources" => dictionary! { "Font" => dictionary! { "F1" => font_id } },
            "MediaBox" => media_box(),
        });
        kids.push(Object::Reference(page_id));
    }
    let count = kids.len() as i64;
    document.objects.insert(
        pages_id,
        Object::Dictionary(dictionary! {
            "Type" => "Pages",
            "Kids" => kids,
            "Count" => count,
        }),
    );
    let catalog_id = document.add_object(dictionary! {
        "Type" => "Catalog",
        "Pages" => pages_id,
    });
    document.trailer.set("Root", catalog_id);
    document.save(path).unwrap();
}

fn make_shaded_pdf(path: &Path) {
    let mut document = Document::with_version("1.5");
    let pages_id = document.new_object_id();
    let font_id = document.add_object(dictionary! {
        "Type" => "Font",
        "Subtype" => "Type1",
        "BaseFont" => "Helvetica",
        "Encoding" => "WinAnsiEncoding",
    });
    let content = "0.2 0.4 0.6 rg\n40 200 240 80 re\nf\n\
                   0 0 0 rg\nBT\n/F1 12 Tf\n\
                   1 0 0 1 50 250 Tm\n(Line one) Tj\n\
                   1 0 0 1 50 234 Tm\n(Line two) Tj\n\
                   ET\n";
    let content_id = document.add_object(Stream::new(lopdf::Dictionary::new(), content.into()));
    let page_id = document.add_object(dictionary! {
        "Type" => "Page",
        "Parent" => pages_id,
        "Contents" => content_id,
        "Resources" => dictionary! { "Font" => dictionary! { "F1" => font_id } },
        "MediaBox" => media_box(),
    });
    document.objects.insert(
        pages_id,
        Object::Dictionary(dictionary! {
            "Type" => "Pages",
            "Kids" => vec![Object::Reference(page_id)],
            "Count" => 1i64,
        }),
    );
    let catalog_id = document.add_object(dictionary! {
        "Type" => "Catalog",
        "Pages" => pages_id,
    });
    document.trailer.set("Root", catalog_id);
    document.save(path).unwrap();
}

fn make_link_pdf(path: &Path) {
    let mut document = Document::with_version("1.5");
    let pages_id = document.new_object_id();
    let font_id = document.add_object(dictionary! {
        "Type" => "Font",
        "Subtype" => "Type1",
        "BaseFont" => "Helvetica",
        "Encoding" => "WinAnsiEncoding",
    });
    let annotation_id = document.add_object(dictionary! {
        "Type" => "Annot",
        "Subtype" => "Link",
        "Rect" => vec![
            Object::Integer(45),
            Object::Integer(235),
            Object::Integer(220),
            Object::Integer(275),
        ],
        "Border" => vec![Object::Integer(0), Object::Integer(0), Object::Integer(0)],
        "A" => dictionary! {
            "S" => "URI",
            "URI" => Object::string_literal("https://example.com/"),
        },
    });
    let content = "BT\n/F1 14 Tf\n1 0 0 1 50 250 Tm\n(Hello world) Tj\nET\n";
    let content_id = document.add_object(Stream::new(lopdf::Dictionary::new(), content.into()));
    let page_id = document.add_object(dictionary! {
        "Type" => "Page",
        "Parent" => pages_id,
        "Contents" => content_id,
        "Resources" => dictionary! { "Font" => dictionary! { "F1" => font_id } },
        "MediaBox" => media_box(),
        "Annots" => vec![Object::Reference(annotation_id)],
    });
    document.objects.insert(
        pages_id,
        Object::Dictionary(dictionary! {
            "Type" => "Pages",
            "Kids" => vec![Object::Reference(page_id)],
            "Count" => 1i64,
        }),
    );
    let catalog_id = document.add_object(dictionary! {
        "Type" => "Catalog",
        "Pages" => pages_id,
    });
    document.trailer.set("Root", catalog_id);
    document.save(path).unwrap();
}

fn make_encrypted_pdf(path: &Path) {
    let mut document = Document::with_version("1.5");
    let pages_id = document.new_object_id();
    let page_id = document.add_object(dictionary! {
        "Type" => "Page",
        "Parent" => pages_id,
        "MediaBox" => vec![
            Object::Integer(0),
            Object::Integer(0),
            Object::Integer(200),
            Object::Integer(200),
        ],
        "Resources" => lopdf::Dictionary::new(),
    });
    document.objects.insert(
        pages_id,
        Object::Dictionary(dictionary! {
            "Type" => "Pages",
            "Kids" => vec![Object::Reference(page_id)],
            "Count" => 1i64,
        }),
    );
    let catalog_id = document.add_object(dictionary! {
        "Type" => "Catalog",
        "Pages" => pages_id,
    });
    document.trailer.set("Root", catalog_id);
    let encrypt_id = document.add_object(dictionary! {
        "Filter" => "Standard",
        "V" => 1i64,
        "R" => 2i64,
        "O" => Object::string_literal(vec![0u8; 32]),
        "U" => Object::string_literal(vec![0u8; 32]),
        "P" => -4i64,
    });
    document
        .trailer
        .set("Encrypt", Object::Reference(encrypt_id));
    document.save(path).unwrap();
}

fn page_count(path: &Path) -> usize {
    Document::load(path).unwrap().get_pages().len()
}

fn write_text(path: &Path, text: &str) {
    fs::write(path, text.as_bytes()).unwrap();
}

// ---------------------------------------------------------------------------
// Kind detection

#[test]
fn from_path_is_case_insensitive_and_unknown_extensions_are_none() {
    assert_eq!(
        DocumentKind::from_path(Path::new("Report.PDF")),
        Some(DocumentKind::Pdf)
    );
    assert_eq!(
        DocumentKind::from_path(Path::new("notes.Docx")),
        Some(DocumentKind::Docx)
    );
    assert_eq!(
        DocumentKind::from_path(Path::new("readme.MD")),
        Some(DocumentKind::Markdown)
    );
    assert_eq!(
        DocumentKind::from_path(Path::new("note.TXT")),
        Some(DocumentKind::Text)
    );
    assert_eq!(DocumentKind::from_path(Path::new("archive.tar.gz")), None);
    assert_eq!(DocumentKind::Text.pattern(), "*.txt");
    assert_eq!(DocumentKind::Markdown.pattern(), "*.md");
    assert_eq!(DocumentKind::Pdf.pattern(), "*.pdf");
    assert_eq!(DocumentKind::Docx.pattern(), "*.docx");
    assert_eq!(
        DocumentTranslator::suggested_path(Path::new("report.PDF"), target("de")),
        Path::new("report_de.pdf")
    );
}

// ---------------------------------------------------------------------------
// TXT / Markdown

#[test]
fn txt_roundtrip_preserves_blank_lines_and_reports_progress() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("Note.TXT");
    write_text(&source, "Hello\n\nWorld\n");

    let document = DocumentTranslator::read(&source).unwrap();
    assert_eq!(document.kind, DocumentKind::Text);
    assert_eq!(document.source_text.as_deref(), Some("Hello\n\nWorld\n"));
    assert!(document.paragraphs.is_empty());
    assert_eq!(document.text(), "Hello\n\nWorld\n");

    let output = DocumentTranslator::suggested_path(&source, target("uk"));
    assert_eq!(output, directory.path().join("Note_uk.txt"));

    let mut calls = Vec::new();
    let progress = std::cell::RefCell::new(Vec::new());
    let on_progress = |done: usize, total: usize| progress.borrow_mut().push((done, total));
    let mut translate = |text: &str| {
        calls.push(text.to_string());
        Ok(text.to_uppercase())
    };
    let returned =
        DocumentTranslator::write(&document, &output, &mut translate, Some(&on_progress), None)
            .unwrap();
    assert_eq!(returned, output);
    assert_eq!(calls, vec!["Hello", "World"]);
    assert_eq!(fs::read_to_string(&output).unwrap(), "HELLO\n\nWORLD\n");
    assert_eq!(fs::read_to_string(&source).unwrap(), "Hello\n\nWorld\n");
    assert_eq!(*progress.borrow(), vec![(1, 2), (2, 2)]);
}

#[test]
fn markdown_keeps_fenced_code_and_blank_lines() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("page.md");
    write_text(&source, "# Title\n\n```python\nprint('hi')\n```\n\nBody\n");

    let document = DocumentTranslator::read(&source).unwrap();
    assert_eq!(document.kind, DocumentKind::Markdown);

    let mut translations = Vec::new();
    let mut translate = |text: &str| {
        translations.push(text.to_string());
        Ok(text.to_uppercase())
    };
    let output = directory.path().join("page_uk.md");
    let progress = std::cell::RefCell::new(Vec::new());
    let on_progress = |done: usize, total: usize| progress.borrow_mut().push((done, total));
    DocumentTranslator::write(&document, &output, &mut translate, Some(&on_progress), None)
        .unwrap();
    assert_eq!(translations, vec!["# Title", "Body"]);
    assert_eq!(
        fs::read_to_string(&output).unwrap(),
        "# TITLE\n\n```python\nprint('hi')\n```\n\nBODY\n"
    );
    assert_eq!(*progress.borrow(), vec![(1, 2), (2, 2)]);
}

#[test]
fn markdown_keeps_crlf_and_unclosed_fences() {
    let directory = tempfile::tempdir().unwrap();
    let source_text =
        "\r\nTitle\r\nline 2\r\n \r\n\r\n````swift\r\n\r\n```\r\nlet n = 10\r\n````\r\nNext\r\n";
    let expected =
        "\r\nTITLE\r\nLINE 2\r\n \r\n\r\n````swift\r\n\r\n```\r\nlet n = 10\r\n````\r\nNEXT\r\n";
    let source = directory.path().join("crlf.md");
    write_text(&source, source_text);
    let output = directory.path().join("crlf_uk.md");
    DocumentTranslator::write(
        &DocumentTranslator::read(&source).unwrap(),
        &output,
        &mut |text| Ok(text.to_uppercase()),
        None,
        None,
    )
    .unwrap();
    assert_eq!(fs::read(&output).unwrap(), expected.as_bytes());

    let unclosed = "Start\n~~~sh\n\nprintf 'hello'\n";
    write_text(&source, unclosed);
    DocumentTranslator::write(
        &DocumentTranslator::read(&source).unwrap(),
        &output,
        &mut |text| Ok(text.to_uppercase()),
        None,
        None,
    )
    .unwrap();
    assert_eq!(
        fs::read_to_string(&output).unwrap(),
        "START\n~~~sh\n\nprintf 'hello'\n"
    );
}

#[test]
fn blank_text_file_raises_no_text() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("blank.txt");
    write_text(&source, " \n\n\t");
    let error = DocumentTranslator::read(&source).unwrap_err();
    assert_eq!(error.kind, DocumentErrorKind::NoText);
    assert!(!error.message().is_empty());
}

#[test]
fn empty_file_raises_no_text() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("empty.txt");
    write_text(&source, "");
    assert_eq!(
        DocumentTranslator::read(&source).unwrap_err().kind,
        DocumentErrorKind::NoText
    );
}

// ---------------------------------------------------------------------------
// Encodings

#[test]
fn text_decoding_matrix() {
    let cases: Vec<(&str, Vec<u8>, &str)> = vec![
        (
            "utf8.txt",
            "Привіт, світе!\nДругий рядок.".as_bytes().to_vec(),
            "Привіт, світе!",
        ),
        (
            "utf8-bom.txt",
            [b"\xef\xbb\xbf".as_slice(), "Привіт!".as_bytes()].concat(),
            "Привіт!",
        ),
        (
            "cp1251-ru.txt",
            encoding_rs::WINDOWS_1251
                .encode("Привет, мир! Это проверка.")
                .0
                .into_owned(),
            "Привет, мир! Это проверка.",
        ),
        (
            "cp1251-uk.txt",
            encoding_rs::WINDOWS_1251
                .encode("Привіт, світе! Це перевірка.")
                .0
                .into_owned(),
            "Привіт, світе! Це перевірка.",
        ),
        (
            "utf16.txt",
            [
                b"\xff\xfe".as_slice(),
                "Привіт!"
                    .encode_utf16()
                    .flat_map(u16::to_le_bytes)
                    .collect::<Vec<u8>>()
                    .as_slice(),
            ]
            .concat(),
            "Привіт!",
        ),
        (
            "cp1252-de.txt",
            encoding_rs::WINDOWS_1252
                .encode("Grüße aus München.")
                .0
                .into_owned(),
            "Grüße aus München.",
        ),
        (
            "cp1252-fr.txt",
            encoding_rs::WINDOWS_1252
                .encode("Très bien, ça va.")
                .0
                .into_owned(),
            "Très bien, ça va.",
        ),
        (
            "ascii.txt",
            b"Plain text, no accents.".to_vec(),
            "Plain text, no accents.",
        ),
    ];
    let directory = tempfile::tempdir().unwrap();
    for (name, payload, expected) in cases {
        let path = directory.path().join(name);
        fs::write(&path, payload).unwrap();
        let document = DocumentTranslator::read(&path).unwrap();
        let text = document
            .source_text
            .unwrap_or_else(|| document.paragraphs.join("\n"));
        assert_eq!(text.lines().next().unwrap(), expected, "case {name}");
    }
}

#[test]
fn written_text_is_utf8() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("note.txt");
    write_text(&source, "Привіт!\n\nДругий абзац.");
    let document = DocumentTranslator::read(&source).unwrap();
    let output = DocumentTranslator::suggested_path(&source, target("uk"));
    DocumentTranslator::write(
        &document,
        &output,
        &mut |line| Ok(line.to_uppercase()),
        None,
        None,
    )
    .unwrap();
    let bytes = fs::read(&output).unwrap();
    assert!(bytes.starts_with("ПРИВІТ!".as_bytes()));
}

// ---------------------------------------------------------------------------
// DOCX

#[test]
fn docx_roundtrip_keeps_package_and_formatting() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("Sample.Docx");
    make_docx(&source);

    let document = DocumentTranslator::read(&source).unwrap();
    assert_eq!(document.kind, DocumentKind::Docx);
    assert_eq!(
        document.paragraphs,
        vec!["Hello world", "Second paragraph", ""]
    );
    assert_eq!(document.text(), "Hello world\nSecond paragraph\n");

    let mut calls = Vec::new();
    let mut translate = |text: &str| {
        calls.push(text.to_string());
        Ok(text.to_uppercase())
    };
    assert_eq!(
        DocumentTranslator::suggested_path(&source, target("uk")),
        directory.path().join("Sample_uk.docx")
    );
    let output = directory.path().join("Sample_uk.Docx");
    let progress = std::cell::RefCell::new(Vec::new());
    let on_progress = |done: usize, total: usize| progress.borrow_mut().push((done, total));
    DocumentTranslator::write(&document, &output, &mut translate, Some(&on_progress), None)
        .unwrap();
    assert_eq!(calls, vec!["Hello world", "Second paragraph"]);
    assert_eq!(*progress.borrow(), vec![(1, 2), (2, 2)]);
    assert_eq!(
        DocumentTranslator::read(&output).unwrap().paragraphs,
        vec!["HELLO WORLD", "SECOND PARAGRAPH", ""]
    );

    let mut original = ZipArchive::new(fs::File::open(&source).unwrap()).unwrap();
    let mut translated = ZipArchive::new(fs::File::open(&output).unwrap()).unwrap();
    let names: Vec<String> = original.file_names().map(str::to_string).collect();
    let translated_names: Vec<String> = translated.file_names().map(str::to_string).collect();
    assert_eq!(translated_names, names);
    for name in &names {
        if name == "word/document.xml" {
            continue;
        }
        let mut original_bytes = Vec::new();
        std::io::Read::read_to_end(&mut original.by_name(name).unwrap(), &mut original_bytes)
            .unwrap();
        let mut translated_bytes = Vec::new();
        std::io::Read::read_to_end(
            &mut translated.by_name(name).unwrap(),
            &mut translated_bytes,
        )
        .unwrap();
        assert_eq!(translated_bytes, original_bytes, "{name}");
        assert_eq!(
            translated.by_name(name).unwrap().compression(),
            original.by_name(name).unwrap().compression(),
            "{name}"
        );
    }

    let mut xml = String::new();
    std::io::Read::read_to_string(
        &mut translated.by_name("word/document.xml").unwrap(),
        &mut xml,
    )
    .unwrap();
    assert!(xml.contains("<w:b"), "{xml}");
    assert!(xml.contains("<w:pStyle"), "{xml}");
    assert!(xml.contains("xml:space=\"preserve\""), "{xml}");
    assert!(xml.contains("mc:Ignorable=\"w14\""), "{xml}");
    assert!(xml.contains("xmlns:w14="), "{xml}");
    assert!(xml.contains(">HELLO </w:t>"), "{xml}");
    assert!(xml.contains(">WORLD</w:t>"), "{xml}");
}

#[test]
fn docx_without_text_raises_no_text() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("empty.docx");
    empty_docx(&source);
    let error = DocumentTranslator::read(&source).unwrap_err();
    assert_eq!(error.kind, DocumentErrorKind::NoText);
    assert!(!error.message().is_empty());
}

// ---------------------------------------------------------------------------
// PDF

#[test]
fn pdf_overlay_keeps_page_count_and_original_text_layer() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("Report.PDF");
    make_pdf(
        &source,
        &[&["Hello world", "Second line"][..], &["Another page"][..]],
    );

    let document = DocumentTranslator::read(&source).unwrap();
    assert_eq!(document.kind, DocumentKind::Pdf);
    assert!(document.paragraphs.iter().any(|text| text == "Hello world"));
    assert!(document
        .paragraphs
        .iter()
        .any(|text| text == "Another page"));
    assert!(document.text().contains("Hello world"));

    assert_eq!(
        DocumentTranslator::suggested_path(&source, target("uk")),
        directory.path().join("Report_uk.pdf")
    );
    let output = directory.path().join("Report_uk.PDF");
    let progress = std::cell::RefCell::new(Vec::new());
    let on_progress = |done: usize, total: usize| progress.borrow_mut().push((done, total));
    DocumentTranslator::write(
        &document,
        &output,
        &mut |text| Ok(text.to_uppercase()),
        Some(&on_progress),
        None,
    )
    .unwrap();

    assert_eq!(page_count(&output), 2);
    let translated = DocumentTranslator::read(&output).unwrap();
    let text = translated.text();
    // The overlay shares the original baseline, so a position-based extractor
    // interleaves the two layers; both are individually still present.
    assert!(text.contains("Hello") && text.contains("world"), "{text}");
    assert!(text.contains("HELLO") && text.contains("WORLD"), "{text}");
    assert!(text.contains("SECOND") && text.contains("LINE"), "{text}");
    assert!(text.contains("ANOTHER") && text.contains("PAGE"), "{text}");
    assert_eq!(
        progress.borrow().last().copied(),
        Some((document.paragraphs.len(), document.paragraphs.len()))
    );
    assert_ne!(fs::read(&source).unwrap(), fs::read(&output).unwrap());
}

#[test]
fn pdf_graphics_only_page_is_left_unchanged() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("mixed.pdf");
    make_pdf(
        &source,
        &[&["First page"][..], &[][..], &["Third page"][..]],
    );

    let document = DocumentTranslator::read(&source).unwrap();
    assert_eq!(document.paragraphs, vec!["First page", "Third page"]);

    let output = directory.path().join("mixed_uk.pdf");
    DocumentTranslator::write(
        &document,
        &output,
        &mut |text| Ok(text.to_uppercase()),
        None,
        None,
    )
    .unwrap();
    assert_eq!(page_count(&output), 3);
    let translated = DocumentTranslator::read(&output).unwrap();
    assert!(!translated.blocks_on_page(1));
    assert!(translated.text().contains("FIRST"));
    assert!(translated.text().contains("THIRD"));
}

trait BlocksOnPage {
    fn blocks_on_page(&self, page: usize) -> bool;
}

impl BlocksOnPage for ofm_docs::OpenedDocument {
    fn blocks_on_page(&self, page: usize) -> bool {
        match &self.payload {
            ofm_docs::Payload::Pdf(layout) => {
                layout.blocks.iter().any(|block| block.page_index == page)
            }
            _ => false,
        }
    }
}

#[test]
fn pdf_without_text_raises_no_text() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("graphics.pdf");
    make_pdf(&source, &[&[][..]]);
    assert_eq!(
        DocumentTranslator::read(&source).unwrap_err().kind,
        DocumentErrorKind::NoText
    );
}

#[test]
fn pdf_uses_cid_font_for_chinese() {
    if !cjk_font_available() {
        eprintln!("skipping CJK overlay test: no CJK TrueType font installed");
        return;
    }
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("chinese.pdf");
    make_pdf(&source, &[&["Hello world"][..]]);
    let output = directory.path().join("chinese_uk.pdf");
    DocumentTranslator::write(
        &DocumentTranslator::read(&source).unwrap(),
        &output,
        &mut |_| Ok("你好世界".to_string()),
        None,
        None,
    )
    .unwrap();
    let extracted = DocumentTranslator::read(&output).unwrap().text();
    assert!(extracted.contains("你好世界"), "{extracted}");
}

#[test]
fn pdf_uses_unicode_font_for_cyrillic() {
    if !system_font_available() {
        eprintln!("skipping Cyrillic overlay test: no Unicode TrueType font installed");
        return;
    }
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("cyrillic.pdf");
    make_pdf(&source, &[&["Hello world"][..]]);
    let output = directory.path().join("cyrillic_uk.pdf");
    DocumentTranslator::write(
        &DocumentTranslator::read(&source).unwrap(),
        &output,
        &mut |_| Ok("Привіт світе".to_string()),
        None,
        None,
    )
    .unwrap();
    let extracted = DocumentTranslator::read(&output).unwrap().text();
    assert!(extracted.contains("Привіт"), "{extracted}");
    assert!(extracted.contains("світе"), "{extracted}");
}

#[test]
fn encrypted_pdf_raises_encrypted() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("secret.pdf");
    make_encrypted_pdf(&source);
    let error = DocumentTranslator::read(&source).unwrap_err();
    assert_eq!(error.kind, DocumentErrorKind::Encrypted);
    assert!(!error.message().is_empty());
}

#[test]
fn pdf_samples_shaded_block_background_and_line_pitch() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("shaded.pdf");
    make_shaded_pdf(&source);
    let document = DocumentTranslator::read(&source).unwrap();
    let ofm_docs::Payload::Pdf(layout) = &document.payload else {
        panic!("expected a PDF payload");
    };
    assert_eq!(layout.blocks.len(), 1);
    let block = &layout.blocks[0];
    assert_eq!(block.text, "Line one Line two");
    assert!(approx(block.background[0], 0.2), "{:?}", block.background);
    assert!(approx(block.background[1], 0.4), "{:?}", block.background);
    assert!(approx(block.background[2], 0.6), "{:?}", block.background);
    assert!(
        (block.line_pitch - 16.0).abs() < 0.6,
        "{}",
        block.line_pitch
    );
    assert!(approx(block.text_color[0], 0.0));
    assert!(approx(block.text_color[1], 0.0));
    assert!(approx(block.text_color[2], 0.0));
}

#[test]
fn pdf_white_page_background_and_single_line_leading() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("plain.pdf");
    make_pdf(&source, &[&["Hello world"][..]]);
    let document = DocumentTranslator::read(&source).unwrap();
    let ofm_docs::Payload::Pdf(layout) = &document.payload else {
        panic!("expected a PDF payload");
    };
    let block = &layout.blocks[0];
    assert!(approx(block.background[0], 1.0));
    assert!(approx(block.background[1], 1.0));
    assert!(approx(block.background[2], 1.0));
    assert!(approx(block.line_pitch, 0.0));
    assert!(approx(block.text_color[0], 0.0));
}

#[test]
fn pdf_keeps_link_annotations() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("link.pdf");
    make_link_pdf(&source);
    let output = directory.path().join("link_uk.pdf");
    DocumentTranslator::write(
        &DocumentTranslator::read(&source).unwrap(),
        &output,
        &mut |text| Ok(text.to_uppercase()),
        None,
        None,
    )
    .unwrap();

    let document = Document::load(&output).unwrap();
    let page_id = *document.get_pages().values().next().unwrap();
    let page = document.get_dictionary(page_id).unwrap();
    let annotations = page.get(b"Annots").unwrap();
    let annotations = document.dereference(annotations).unwrap().1;
    let annotations = annotations.as_array().unwrap();
    let mut found = false;
    for annotation in annotations {
        let (_, annotation) = document.dereference(annotation).unwrap();
        let annotation = annotation.as_dict().unwrap();
        if annotation.get(b"Subtype").and_then(Object::as_name).ok() == Some(b"Link".as_slice()) {
            let action = annotation
                .get(b"A")
                .and_then(|object| document.dereference(object))
                .map(|(_, object)| object.clone())
                .unwrap();
            let action = action.as_dict().unwrap();
            let uri = action.get(b"URI").unwrap().as_str().unwrap();
            if uri == b"https://example.com/".as_slice() {
                found = true;
            }
        }
    }
    assert!(found, "the link annotation was lost");
}

// ---------------------------------------------------------------------------
// Failure handling

#[test]
fn unsupported_extension_raises_unsupported() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("data.xyz");
    write_text(&source, "hello");
    let error = DocumentTranslator::read(&source).unwrap_err();
    assert_eq!(error.kind, DocumentErrorKind::Unsupported);
    assert!(!error.message().is_empty());
}

#[test]
fn cancellation_aborts_between_paragraphs() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("cancel.txt");
    write_text(&source, "One\n\nTwo\n\nThree\n");
    let document = DocumentTranslator::read(&source).unwrap();
    let output = directory.path().join("cancel_uk.txt");

    let cancel = AtomicBool::new(false);
    let mut calls = Vec::new();
    let mut translate = |text: &str| {
        calls.push(text.to_string());
        cancel.store(true, Ordering::Relaxed);
        Ok(text.to_uppercase())
    };
    let error = DocumentTranslator::write(&document, &output, &mut translate, None, Some(&cancel))
        .unwrap_err();
    assert_eq!(error.kind, DocumentErrorKind::Cancelled);
    assert_eq!(calls, vec!["One"]);
    assert!(!output.exists());

    let already = AtomicBool::new(true);
    let error = DocumentTranslator::write(
        &document,
        &output,
        &mut |_| panic!("translate must not run after cancellation"),
        None,
        Some(&already),
    )
    .unwrap_err();
    assert_eq!(error.kind, DocumentErrorKind::Cancelled);
    assert!(!output.exists());
}

#[test]
fn translation_errors_propagate_without_output() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("error.txt");
    write_text(&source, "One\n\nTwo\n");
    let document = DocumentTranslator::read(&source).unwrap();
    let output = directory.path().join("error_uk.txt");
    let error = DocumentTranslator::write(
        &document,
        &output,
        &mut |_| Err("provider failed".to_string()),
        None,
        None,
    )
    .unwrap_err();
    assert_eq!(error.kind, DocumentErrorKind::WriteFailed);
    assert!(error.detail.contains("provider failed"));
    assert!(!output.exists());
}

#[test]
fn output_path_is_never_the_source_path() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("report.pdf");
    fs::write(&source, b"%PDF-1.4\n").unwrap();
    let suggested = DocumentTranslator::suggested_path(&source, target("uk"));
    assert_ne!(suggested, source);
    assert_eq!(suggested.extension().unwrap(), "pdf");
    let _: PathBuf = suggested;
}

// ---------------------------------------------------------------------------
// Regression tests for the independent audit (F1..F3)

const MATH_NS: &str = "http://schemas.openxmlformats.org/officeDocument/2006/math";
const VML_NS: &str = "urn:schemas-microsoft-com:vml";
const MC_NS: &str = "http://schemas.openxmlformats.org/markup-compatibility/2006";

fn make_docx_from_xml(path: &Path, document_xml: &[u8]) {
    let mut archive = ZipWriter::new(fs::File::create(path).unwrap());
    let deflated = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);
    for (name, data) in [
        ("[Content_Types].xml", CONTENT_TYPES),
        ("_rels/.rels", RELS),
        ("word/document.xml", document_xml),
    ] {
        archive.start_file(name, deflated).unwrap();
        archive.write_all(data).unwrap();
    }
    archive.finish().unwrap();
}

fn math_document_xml() -> Vec<u8> {
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\
         <w:document xmlns:w=\"{WORD_NS}\" xmlns:m=\"{MATH_NS}\" \
         xmlns:mc=\"{MC_NS}\" xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" \
         mc:Ignorable=\"w14\"><w:body>\
         <w:p><w:r><w:t xml:space=\"preserve\">Equation: </w:t></w:r>\
         <m:oMath><m:r><m:t>x+y=2</m:t></m:r></m:oMath></w:p>\
         <w:p><w:r><w:t>An ordinary paragraph after the equation.</w:t></w:r></w:p>\
         </w:body></w:document>"
    )
    .into_bytes()
}

fn nested_document_xml() -> Vec<u8> {
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\
         <w:document xmlns:w=\"{WORD_NS}\" xmlns:v=\"{VML_NS}\" \
         xmlns:mc=\"{MC_NS}\" xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" \
         mc:Ignorable=\"w14\"><w:body>\
         <w:p><w:r><w:t xml:space=\"preserve\">Outer start. </w:t></w:r>\
         <w:r><w:pict><v:shape style=\"width:200pt;height:40pt\"><v:textbox>\
         <w:txbxContent><w:p><w:r><w:t>Inner text box paragraph.</w:t></w:r></w:p>\
         </w:txbxContent></v:textbox></v:shape></w:pict></w:r>\
         <w:r><w:t>Outer end.</w:t></w:r></w:p>\
         <w:p><w:r><w:t>After the text box.</w:t></w:r></w:p>\
         </w:body></w:document>"
    )
    .into_bytes()
}

fn field_document_xml() -> Vec<u8> {
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\
         <w:document xmlns:w=\"{WORD_NS}\" xmlns:v=\"{VML_NS}\" \
         xmlns:mc=\"{MC_NS}\" xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" \
         mc:Ignorable=\"w14\"><w:body>\
         <w:p><w:r><w:t xml:space=\"preserve\">Total </w:t></w:r>\
         <w:r><w:instrText xml:space=\"preserve\"> PAGE </w:instrText></w:r>\
         <w:r><w:t>pages</w:t></w:r>\
         <w:del><w:r><w:delText>old</w:delText></w:r></w:del>\
         <mc:AlternateContent><mc:Choice Requires=\"wps\"><w:drawing>\
         <w:p><w:r><w:t>choice text</w:t></w:r></w:p></w:drawing></mc:Choice>\
         <mc:Fallback><w:pict><w:p><w:r><w:t>fallback text</w:t></w:r></w:p></w:pict>\
         </mc:Fallback></mc:AlternateContent></w:p>\
         </w:body></w:document>"
    )
    .into_bytes()
}

fn document_xml_of(path: &Path) -> String {
    let mut archive = ZipArchive::new(fs::File::open(path).unwrap()).unwrap();
    let mut xml = String::new();
    std::io::Read::read_to_string(&mut archive.by_name("word/document.xml").unwrap(), &mut xml)
        .unwrap();
    xml
}

#[test]
fn docx_keeps_math_text_untouched() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("math.docx");
    make_docx_from_xml(&source, &math_document_xml());

    let document = DocumentTranslator::read(&source).unwrap();
    assert_eq!(
        document.paragraphs,
        vec!["Equation: ", "An ordinary paragraph after the equation."]
    );

    let output = directory.path().join("math_uk.docx");
    DocumentTranslator::write(
        &document,
        &output,
        &mut |text| Ok(text.to_uppercase()),
        None,
        None,
    )
    .unwrap();

    let xml = document_xml_of(&output);
    assert!(
        xml.contains("<m:t>x+y=2</m:t>"),
        "math text was rewritten: {xml}"
    );
    assert!(
        xml.contains("<w:t xml:space=\"preserve\">EQUATION: </w:t>"),
        "body text not translated in place (including its trailing space): {xml}"
    );
    assert_eq!(
        DocumentTranslator::read(&output).unwrap().paragraphs,
        vec!["EQUATION: ", "AN ORDINARY PARAGRAPH AFTER THE EQUATION."]
    );
}

#[test]
fn docx_nested_text_box_is_not_duplicated() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("nested.docx");
    make_docx_from_xml(&source, &nested_document_xml());

    let document = DocumentTranslator::read(&source).unwrap();
    assert_eq!(
        document.paragraphs,
        vec![
            "Outer start. Outer end.",
            "Inner text box paragraph.",
            "After the text box.",
        ]
    );

    let output = directory.path().join("nested_uk.docx");
    DocumentTranslator::write(
        &document,
        &output,
        &mut |text| Ok(text.to_uppercase()),
        None,
        None,
    )
    .unwrap();

    let xml = document_xml_of(&output);
    assert!(xml.contains(">OUTER START. </w:t>"), "{xml}");
    assert!(xml.contains(">OUTER END.</w:t>"), "{xml}");
    assert!(xml.contains(">INNER TEXT BOX PARAGRAPH.</w:t>"), "{xml}");
    assert_eq!(
        xml.matches("INNER TEXT BOX PARAGRAPH.").count(),
        1,
        "the text box content was duplicated: {xml}"
    );
    assert_eq!(
        DocumentTranslator::read(&output).unwrap().paragraphs,
        vec![
            "OUTER START. OUTER END.",
            "INNER TEXT BOX PARAGRAPH.",
            "AFTER THE TEXT BOX.",
        ]
    );
}

#[test]
fn docx_keeps_fields_deleted_text_and_compatibility_fallback() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("fields.docx");
    make_docx_from_xml(&source, &field_document_xml());

    let document = DocumentTranslator::read(&source).unwrap();
    assert_eq!(document.paragraphs, vec!["Total pages", "choice text"]);

    let output = directory.path().join("fields_uk.docx");
    DocumentTranslator::write(
        &document,
        &output,
        &mut |text| Ok(text.to_uppercase()),
        None,
        None,
    )
    .unwrap();

    let xml = document_xml_of(&output);
    assert!(
        xml.contains("<w:instrText xml:space=\"preserve\"> PAGE </w:instrText>"),
        "field instruction was rewritten: {xml}"
    );
    assert!(
        xml.contains("<w:delText>old</w:delText>"),
        "deleted revision text was rewritten: {xml}"
    );
    assert!(
        xml.contains("<w:t>fallback text</w:t>"),
        "mc:Fallback content was rewritten: {xml}"
    );
    assert!(xml.contains(">CHOICE TEXT</w:t>"), "{xml}");
}

fn make_times_pdf(path: &Path) {
    let mut document = Document::with_version("1.5");
    let pages_id = document.new_object_id();
    let times_id = document.add_object(dictionary! {
        "Type" => "Font",
        "Subtype" => "Type1",
        "BaseFont" => "Times-Roman",
        "Encoding" => "WinAnsiEncoding",
    });
    let helvetica_id = document.add_object(dictionary! {
        "Type" => "Font",
        "Subtype" => "Type1",
        "BaseFont" => "Helvetica",
        "Encoding" => "WinAnsiEncoding",
    });
    let content = "BT\n/F1 11 Tf\n1 0 0 1 72 692 Tm\n(A line in Times Roman on page one.) Tj\nET\n\
                   BT\n/F2 6 Tf\n1 0 0 1 238 690.7 Tm\n(123) Tj\nET\n";
    let content_id = document.add_object(Stream::new(lopdf::Dictionary::new(), content.into()));
    let page_id = document.add_object(dictionary! {
        "Type" => "Page",
        "Parent" => pages_id,
        "Contents" => content_id,
        "Resources" => dictionary! {
            "Font" => dictionary! { "F1" => times_id, "F2" => helvetica_id },
        },
        "MediaBox" => vec![
            Object::Integer(0),
            Object::Integer(0),
            Object::Integer(612),
            Object::Integer(792),
        ],
    });
    document.objects.insert(
        pages_id,
        Object::Dictionary(dictionary! {
            "Type" => "Pages",
            "Kids" => vec![Object::Reference(page_id)],
            "Count" => 1i64,
        }),
    );
    let catalog_id = document.add_object(dictionary! {
        "Type" => "Catalog",
        "Pages" => pages_id,
    });
    document.trailer.set("Root", catalog_id);
    document.save(path).unwrap();
}

#[test]
fn pdf_times_metrics_do_not_erase_neighbours() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("times.pdf");
    make_times_pdf(&source);

    let document = DocumentTranslator::read(&source).unwrap();
    let ofm_docs::Payload::Pdf(layout) = &document.payload else {
        panic!("expected a PDF payload");
    };
    let times = layout
        .blocks
        .iter()
        .find(|block| block.font_name.contains("Times"))
        .expect("Times block");
    let number = layout
        .blocks
        .iter()
        .find(|block| block.text == "123")
        .expect("123 block");
    // pdfplumber measures the same line as x0=72.00 .. x1=233.93 at 11 pt.
    assert!((times.x0 - 72.0).abs() < 0.1, "x0={}", times.x0);
    assert!((times.x1 - 233.93).abs() < 0.6, "x1={}", times.x1);
    assert!(times.text.starts_with("A line in Times"), "{}", times.text);
    // Fig. F2: the cover is drawn from x0-2 to x1+2; it must not reach `123`.
    let cover_right = times.x1 + 2.0;
    assert!(
        cover_right < number.x0,
        "cover reaches {cover_right}, erasing the {:.1} block at {}",
        number.x0,
        number.text
    );

    // Writing (the translation of `123` is unchanged, so it gets no cover) must
    // keep both blocks present.
    let output = directory.path().join("times_uk.pdf");
    DocumentTranslator::write(
        &document,
        &output,
        &mut |text| Ok(text.to_uppercase()),
        None,
        None,
    )
    .unwrap();
    let translated = DocumentTranslator::read(&output).unwrap();
    assert!(translated.text().contains("123"));
    assert!(translated.text().contains("TIMES"));
}

#[test]
fn docx_keeps_paragraph_edges_out_of_the_translation() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("edges.docx");
    let xml = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\
         <w:document xmlns:w=\"{WORD_NS}\"><w:body>\
         <w:p><w:r><w:t xml:space=\"preserve\">  spaced text  </w:t></w:r></w:p>\
         <w:p><w:r><w:t xml:space=\"preserve\">Hello </w:t></w:r>\
         <w:r><w:t>world</w:t></w:r></w:p>\
         </w:body></w:document>"
    );
    make_docx_from_xml(&source, xml.as_bytes());

    let document = DocumentTranslator::read(&source).unwrap();
    assert_eq!(document.paragraphs, vec!["  spaced text  ", "Hello world"]);

    let mut seen = Vec::new();
    let output = directory.path().join("edges_uk.docx");
    DocumentTranslator::write(
        &document,
        &output,
        &mut |text| {
            seen.push(text.to_string());
            Ok(text.to_uppercase())
        },
        None,
        None,
    )
    .unwrap();
    assert_eq!(seen, vec!["spaced text", "Hello world"]);
    assert_eq!(
        DocumentTranslator::read(&output).unwrap().paragraphs,
        vec!["  SPACED TEXT  ", "HELLO WORLD"]
    );
}
