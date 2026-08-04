"""
Обезличивание Word (.docx) с сохранением вёрстки.

Обходит ВСЕ текстовые места (тело, таблицы, колонтитулы), прогоняет каждый
параграф через ядро анонимизации и вписывает результат обратно. Метаданные и
текст правок-удалений вычищаются (см. metadata.py).

Ключевая деталь корректности — ПДн, разорванная по runs. Word режет текст
параграфа на runs по форматированию: «Иван **Петров**» может лежать в двух runs.
Поэтому анонимизируем ТЕКСТ ПАРАГРАФА ЦЕЛИКОМ, а не отдельные runs. Если ПДн
найдена, результат кладём в первый run, остальные очищаем: внутрипараграфное
форматирование в таких (и только таких) параграфах не сохраняется — это
осознанный безопасный компромисс, приватность важнее.
"""
import io
import logging

from docx import Document

from app.anonymizer import anonymize_text

from .metadata import detect_review_leftovers, scrub_docx_metadata

logger = logging.getLogger(__name__)


def _iter_paragraphs(document):
    """Все параграфы документа: тело, таблицы (в т.ч. вложенные), колонтитулы."""
    def walk_container(container):
        yield from container.paragraphs
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from walk_container(cell)

    yield from walk_container(document)
    for section in document.sections:
        for hf in (section.header, section.footer,
                   section.first_page_header, section.first_page_footer,
                   section.even_page_header, section.even_page_footer):
            yield from walk_container(hf)


def _anonymize_paragraph(paragraph, disable_entities) -> int:
    """Обезличивает один параграф. Возвращает число найденных сущностей."""
    if not paragraph.runs:
        return 0
    full = "".join(r.text for r in paragraph.runs)
    if not full.strip():
        return 0
    res = anonymize_text(full, disable_entities=disable_entities)
    if res["anonymized"] == full:
        return 0
    # ПДн найдена — весь обезличенный текст в первый run, остальные очищаем
    paragraph.runs[0].text = res["anonymized"]
    for r in paragraph.runs[1:]:
        r.text = ""
    return len(res["entities_found"])


def anonymize_docx(data: bytes, disable_entities=None) -> tuple[bytes, dict]:
    """Обезличивает .docx. Возвращает (байты нового файла, сводка).

    Сводка — только счётчики и предупреждения, БЕЗ значений ПДн и mapping
    (де-анонимизирующие данные в вывод не попадают)."""
    document = Document(io.BytesIO(data))

    total_entities = 0
    paragraphs_changed = 0
    for para in _iter_paragraphs(document):
        n = _anonymize_paragraph(para, disable_entities)
        if n:
            total_entities += n
            paragraphs_changed += 1

    warnings = detect_review_leftovers(document)
    scrub_docx_metadata(document)
    if warnings:
        logger.warning("docx: остаточные ревью-артефакты не обработаны в v1: %s", warnings)

    out = io.BytesIO()
    document.save(out)
    summary = {
        "format": "docx",
        "entities_found": total_entities,
        "paragraphs_changed": paragraphs_changed,
        "warnings": warnings,
    }
    return out.getvalue(), summary
