"""
Эндпоинт POST /anonymize/document: диспетчер формата, лимиты, коды ошибок.
Категория: integration + security (лимиты — защита от DoS).
"""
import pytest

from .conftest import build_docx, build_pdf

pytestmark = pytest.mark.integration

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class TestDocumentEndpoint:
    def test_docx_roundtrip(self, client):
        r = client.post(
            "/anonymize/document",
            files={"file": ("t.docx", build_docx(), _DOCX_MIME)},
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == _DOCX_MIME
        assert "attachment" in r.headers["content-disposition"]
        assert "X-Anonymization-Summary" in r.headers
        assert len(r.content) > 0

    def test_pdf_roundtrip(self, client):
        r = client.post(
            "/anonymize/document",
            files={"file": ("t.pdf", build_pdf(), "application/pdf")},
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"

    def test_unknown_format_415(self, client):
        r = client.post(
            "/anonymize/document",
            files={"file": ("t.txt", b"just text", "text/plain")},
        )
        assert r.status_code == 415

    def test_empty_file_422(self, client):
        r = client.post(
            "/anonymize/document",
            files={"file": ("t.docx", b"", _DOCX_MIME)},
        )
        assert r.status_code == 422

    @pytest.mark.security
    def test_oversize_rejected_413(self, client):
        from app.config import settings
        orig = settings.document_max_bytes
        settings.document_max_bytes = 100
        try:
            r = client.post(
                "/anonymize/document",
                files={"file": ("t.docx", build_docx(), _DOCX_MIME)},
            )
            assert r.status_code == 413
        finally:
            settings.document_max_bytes = orig


class TestDocumentDisabledByDefault:
    def test_route_absent_when_flag_off(self):
        """Без DOCUMENT_ENABLED роут не зарегистрирован (используем стандартный client)."""
        import importlib

        import app.main as m
        from app.config import settings
        orig = settings.document_enabled
        settings.document_enabled = False
        try:
            importlib.reload(m)
            from fastapi.testclient import TestClient
            c = TestClient(m.app, raise_server_exceptions=False)
            r = c.post("/anonymize/document",
                       files={"file": ("t.docx", b"x", _DOCX_MIME)})
            assert r.status_code == 404
        finally:
            settings.document_enabled = orig
            importlib.reload(m)
