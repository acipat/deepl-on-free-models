"""Dev-only visual check for the PDF overlay: render before/after pages to PNG.

Usage:  .venv/bin/python tools/pdf_check.py
Requires pypdfium2 (development convenience only, not a runtime dependency).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from deepl_ofm.services.documents import DocumentTranslator

OUT = ROOT / "docs"


def build_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 20)
    c.drawString(25 * mm, height - 30 * mm, "Quarterly report")
    c.setFont("Helvetica", 11)
    lines = [
        "Revenue grew by 18 percent compared with the previous quarter.",
        "The translation pipeline now runs on every supported platform.",
        "Customers asked for offline models and a smaller download.",
        "",
        "Support answered 1,240 tickets in total, and the median reply",
        "time dropped to just under three hours.",
    ]
    y = height - 45 * mm
    for line in lines:
        c.drawString(25 * mm, y, line)
        y -= 7 * mm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(25 * mm, y - 6 * mm, "Next steps")
    c.setFont("Helvetica", 11)
    c.drawString(25 * mm, y - 16 * mm, "Hire two engineers and ship the Windows build.")
    c.showPage()

    c.setFont("Helvetica-Bold", 16)
    c.drawString(25 * mm, height - 30 * mm, "Appendix")
    c.setFont("Helvetica", 11)
    c.drawString(25 * mm, height - 42 * mm, "Figures are unaudited and rounded to the nearest thousand.")
    c.showPage()
    c.save()


TRANSLATIONS = {
    "Quarterly report": "Квартальний звіт",
    "Revenue grew by 18 percent compared with the previous quarter.":
        "Дохід зріс на 18 відсотків порівняно з попереднім кварталом.",
    "The translation pipeline now runs on every supported platform.":
        "Конвеєр перекладу тепер працює на кожній підтримуваній платформі.",
    "Customers asked for offline models and a smaller download.":
        "Клієнти просили офлайн-моделі та менший обсяг завантаження.",
    "Support answered 1,240 tickets in total, and the median reply":
        "Підтримка опрацювала загалом 1 240 звернень, а медіанний час",
    "time dropped to just under three hours.":
        "відповіді скоротився до трохи менше трьох годин.",
    "Next steps": "Наступні кроки",
    "Hire two engineers and ship the Windows build.":
        "Найняти двох інженерів і випустити збірку для Windows.",
    "Appendix": "Додаток",
    "Figures are unaudited and rounded to the nearest thousand.":
        "Цифри не перевірені аудитом і округлені до найближчої тисячі.",
}


def translate(line: str) -> str:
    return TRANSLATIONS.get(line, line)


def render(pdf: Path, prefix: str) -> list[Path]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(pdf))
    paths = []
    for index in range(len(document)):
        bitmap = document[index].render(scale=2.0)
        target = OUT / f"{prefix}-{index + 1}.png"
        bitmap.to_pil().save(target)
        paths.append(target)
    return paths


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source = OUT / "check-source.pdf"
    build_pdf(source)

    document = DocumentTranslator.read(source)
    output = DocumentTranslator.suggested_path(source, _target())
    DocumentTranslator.write(document, output, translate)

    print("rendered:", *[str(p) for p in render(source, "pdf-before")])
    print("rendered:", *[str(p) for p in render(output, "pdf-after")])
    print("output:", output)
    return 0


def _target():
    from deepl_ofm.core.languages import get_language

    return get_language("uk")


if __name__ == "__main__":
    raise SystemExit(main())
