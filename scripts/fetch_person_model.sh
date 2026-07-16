#!/usr/bin/env bash
# Загрузка дообученной PERSON-модели (ruBERT) для приватностного гейта в CI.
#
# Модель НЕ хранится в репозитории (~114 МБ, папка models/ в .gitignore).
# Чтобы приватностный гейт (LeakRate) работал в CI, положите архив модели
# (.tar.gz с файлами config.json / model.safetensors / tokenizer* в корне)
# в доступное хранилище и задайте секрет PERSON_MODEL_URL со ссылкой на него.
#
# Использование:
#   PERSON_MODEL_URL=<url> ./scripts/fetch_person_model.sh [DEST]
# DEST по умолчанию: models/person_ruBERT
set -euo pipefail

DEST="${1:-models/person_ruBERT}"
: "${PERSON_MODEL_URL:?нужна переменная PERSON_MODEL_URL (ссылка на .tar.gz с моделью)}"

echo "Загрузка модели из PERSON_MODEL_URL в ${DEST} ..."
mkdir -p "${DEST}"
curl -fL --retry 3 "${PERSON_MODEL_URL}" -o /tmp/person_model.tar.gz
tar -xzf /tmp/person_model.tar.gz -C "${DEST}"

if [ ! -f "${DEST}/config.json" ]; then
    echo "ОШИБКА: в ${DEST} нет config.json — проверьте структуру архива" >&2
    exit 1
fi
echo "Готово. Содержимое ${DEST}:"
ls -la "${DEST}"
