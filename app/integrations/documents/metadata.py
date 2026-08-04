"""
Очистка метаданных документа — обязательный шаг обезличивания.

Персональные данные утекают не только в видимом тексте, но и в свойствах файла
(автор, организация), правках (track changes) и комментариях. «Извлёк текст →
заменил → сохранил» без очистки метаданных = инцидент по 152-ФЗ.

Объём v1: полная очистка свойств документа (.docx) + удаление deleted-текста
правок (w:del содержит удалённый текст — потенциально ПДн). Комментарии и
принятие вставок правок — детект + предупреждение (см. detect_review_leftovers),
полная обработка запланирована в v1.1.

Для PDF отдельная очистка не нужна: адаптер растеризует страницы и собирает файл
заново — исходные метаданные в результат не переносятся вовсе.
"""
import logging

from docx.oxml.ns import qn

logger = logging.getLogger(__name__)

# Текстовые свойства документа, которые могут содержать ПДн (ФИО автора и т.п.).
_CORE_PROPS = (
    "author", "last_modified_by", "title", "subject", "keywords",
    "comments", "category", "content_status", "identifier", "version",
)


def scrub_docx_metadata(document) -> None:
    """Очищает свойства документа и удаляет текст правок-удалений (in place)."""
    cp = document.core_properties
    for attr in _CORE_PROPS:
        try:
            setattr(cp, attr, "")
        except (ValueError, TypeError):
            pass  # некоторые свойства типизированы (даты/числа) — их не трогаем

    # Удаляем правки-удаления: элемент w:del несёт удалённый текст (w:delText),
    # который мог содержать ПДн и в видимый текст не попадает.
    body = document.element.body
    for el in list(body.iter(qn("w:del"))):
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)


def detect_review_leftovers(document) -> list:
    """Возвращает список остаточных ревью-артефактов (для предупреждения вызывающему).

    Track-changes-вставки (w:ins) и комментарии в v1 не обрабатываются полностью —
    сообщаем о них явно, чтобы утечка не прошла молча."""
    body = document.element.body
    found = []
    if body.find(".//" + qn("w:ins")) is not None:
        found.append("tracked_insertions")
    # ссылки на комментарии
    if body.find(".//" + qn("w:commentReference")) is not None:
        found.append("comments")
    return found
