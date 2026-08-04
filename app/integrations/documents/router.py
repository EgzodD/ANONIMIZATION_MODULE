"""
Эндпоинт обезличивания документов: POST /anonymize/document.

Принимает файл (.docx или .pdf), возвращает обезличенную версию тем же типом.
Диспетчер выбирает обработчик по MIME/расширению. mapping НЕ возвращается —
для документа это ключ де-анонимизации целого файла (сводка о найденном — в
заголовке X-Anonymization-Summary, без значений ПДн).
"""
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.auth import require_api_key
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"])

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MIME = "application/pdf"


def _parse_disable_entities(raw: str | None):
    """Form-параметр disable_entities: строка через запятую → список."""
    if not raw:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


@router.post(
    "/anonymize/document",
    dependencies=[Depends(require_api_key)],
    summary="Обезличить документ (.docx или .pdf)",
)
async def anonymize_document(
    file: UploadFile = File(..., description="Документ .docx или .pdf"),
    disable_entities: str | None = Form(
        None, description="Список типов через запятую, которые НЕ скрывать "
                          "(только сужение политики, как в /anonymize/text)"),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Пустой файл")
    if len(data) > settings.document_max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Файл больше лимита {settings.document_max_bytes} байт",
        )

    name = (file.filename or "").lower()
    disabled = _parse_disable_entities(disable_entities)

    try:
        if name.endswith(".docx") or file.content_type == _DOCX_MIME:
            from .docx_handler import anonymize_docx
            out, summary = anonymize_docx(data, disable_entities=disabled)
            media, ext = _DOCX_MIME, ".docx"
        elif name.endswith(".pdf") or file.content_type == _PDF_MIME:
            from .pdf_handler import anonymize_pdf
            out, summary = anonymize_pdf(
                data, disable_entities=disabled,
                max_pages=settings.document_max_pdf_pages,
                dpi=settings.document_pdf_dpi,
            )
            media, ext = _PDF_MIME, ".pdf"
        else:
            raise HTTPException(
                status_code=415,
                detail="Поддерживаются только .docx и .pdf",
            )
    except HTTPException:
        raise
    except ValueError as e:
        # лимиты/пустой файл из обработчиков — без утечки содержимого
        raise HTTPException(status_code=422, detail=str(e)) from None
    except Exception:
        # НЕ логируем содержимое/имя — только факт ошибки
        logger.exception("Ошибка обезличивания документа (формат %s)",
                         "docx" if name.endswith(".docx") else "pdf")
        raise HTTPException(status_code=500, detail="Ошибка обработки документа") from None

    out_name = "anonymized_" + (file.filename.rsplit(".", 1)[0] if file.filename else "document") + ext
    return Response(
        content=out,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{out_name}"',
            # сводка без значений ПДн — только счётчики/предупреждения
            "X-Anonymization-Summary": json.dumps(summary, ensure_ascii=False),
        },
    )
