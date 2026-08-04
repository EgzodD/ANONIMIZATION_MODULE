"""
Обработчик PDF: растеризация + закрашивание ПДн. Категория: integration.
Ключевая гарантия приватности — на выходе НЕТ текстового слоя (утечь нечему).
"""
import io

import pdfplumber
import pytest

from app.integrations.documents.pdf_handler import anonymize_pdf

from .conftest import SAMPLE, build_pdf

pytestmark = pytest.mark.integration


def _extract(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


class TestPdfLeaks:
    def test_output_has_no_text_layer(self):
        """Растеризация: в выходном PDF текстового слоя нет — ПДн физически негде утечь."""
        out, summary = anonymize_pdf(build_pdf(), dpi=120)
        assert _extract(out).strip() == ""
        assert summary["rasterized"] is True

    def test_no_pii_values_in_output(self):
        out, _ = anonymize_pdf(build_pdf(), dpi=120)
        extracted = _extract(out)
        for name, value in SAMPLE.items():
            assert value not in extracted, f"утечка {name} в PDF"

    def test_page_count_preserved(self):
        src = build_pdf()
        out, summary = anonymize_pdf(src, dpi=120)
        with pdfplumber.open(io.BytesIO(src)) as p:
            src_pages = len(p.pages)
        assert summary["pages"] == src_pages

    def test_entities_detected(self):
        _, summary = anonymize_pdf(build_pdf(), dpi=120)
        assert summary["entities_found"] >= 3
        assert summary["pages_with_pii"] >= 1

    def test_page_limit_enforced(self):
        with pytest.raises(ValueError):
            anonymize_pdf(build_pdf(), dpi=120, max_pages=0)
