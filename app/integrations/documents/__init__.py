"""
Опциональный адаптер обезличивания документов (PDF / Word).

Включается флагом DOCUMENT_ENABLED (см. app/config.py). По умолчанию выключен —
ядро не тянет python-docx/pdfplumber/pypdfium2. Ядро анонимизации (Presidio +
ruBERT) переиспользуется как есть; здесь только слои извлечения текста, записи
обратно и очистки метаданных.

Лицензии зависимостей (важно для поставки продукта, без AGPL):
  python-docx — MIT, pdfplumber — MIT, pypdfium2 — BSD-3, Pillow — MIT-CMU.
"""
