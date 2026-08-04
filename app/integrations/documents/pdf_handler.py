"""
Обезличивание текстового PDF растеризацией (пермиссивный стек, без AGPL).

Почему растеризация, а не редакция «поверх текста»: настоящая текстовая редакция
(физически удалить текст, оставив PDF выделяемым) надёжно есть только в
PyMuPDF под AGPL — несовместимо с продажей ПО. Пермиссивный путь: рендерим
страницу в изображение (pypdfium2, BSD), закрашиваем области ПДн (Pillow) и
собираем PDF заново. На выходе нет текстового слоя вовсе — утечь физически
нечему. Минус: результат не выделяется/не ищется (это изображение).

Координаты ПДн:
  1) pdfplumber даёт слова с bbox (в пунктах, начало координат — верх-лево);
  2) строим текст страницы + карту «символьное смещение → слово»;
  3) ядро находит спаны ПДн → слова, чьи символы попали в спан;
  4) bbox таких слов масштабируем в пиксели (× dpi/72) и закрашиваем.
"""
import io
import logging

import pdfplumber
import pypdfium2
from PIL import ImageDraw

from app.anonymizer import anonymize_text

logger = logging.getLogger(__name__)


def _pii_word_boxes(page, disable_entities):
    """Возвращает bbox (в пунктах) слов, попавших в спаны ПДн на странице."""
    words = page.extract_words(use_text_flow=True)
    if not words:
        return 0, []
    # текст страницы + карта смещений: (start, end, word)
    parts, offsets, cur = [], [], 0
    for w in words:
        t = w["text"]
        offsets.append((cur, cur + len(t), w))
        parts.append(t)
        cur += len(t) + 1  # разделитель-пробел
    text = " ".join(parts)

    res = anonymize_text(text, disable_entities=disable_entities)
    spans = [(e["start"], e["end"]) for e in res["entities_found"]]
    boxes = []
    for s, e, w in offsets:
        if any(not (e <= ps or s >= pe) for ps, pe in spans):
            boxes.append((w["x0"], w["top"], w["x1"], w["bottom"]))
    return len(res["entities_found"]), boxes


def anonymize_pdf(data: bytes, disable_entities=None, max_pages: int = 100,
                  dpi: int = 150) -> tuple[bytes, dict]:
    """Обезличивает текстовый PDF. Возвращает (байты нового PDF, сводка)."""
    scale = dpi / 72.0
    images = []
    total_entities = 0
    pages_with_pii = 0

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        n_pages = len(pdf.pages)
        if n_pages > max_pages:
            raise ValueError(f"PDF содержит {n_pages} страниц, лимит {max_pages}")

        pdfium = pypdfium2.PdfDocument(data)
        try:
            for i, page in enumerate(pdf.pages):
                n_ent, boxes = _pii_word_boxes(page, disable_entities)
                total_entities += n_ent
                if boxes:
                    pages_with_pii += 1

                # рендер страницы в изображение и закрашивание областей ПДн
                pil = pdfium[i].render(scale=scale).to_pil().convert("RGB")
                if boxes:
                    draw = ImageDraw.Draw(pil)
                    for x0, top, x1, bottom in boxes:
                        draw.rectangle(
                            [x0 * scale, top * scale, x1 * scale, bottom * scale],
                            fill=(0, 0, 0),
                        )
                images.append(pil)
        finally:
            pdfium.close()

    if not images:
        raise ValueError("PDF пуст — нет страниц для обработки")

    out = io.BytesIO()
    images[0].save(out, format="PDF", save_all=True, append_images=images[1:],
                   resolution=float(dpi))
    summary = {
        "format": "pdf",
        "entities_found": total_entities,
        "pages": len(images),
        "pages_with_pii": pages_with_pii,
        "rasterized": True,  # текстового слоя на выходе нет
    }
    return out.getvalue(), summary
