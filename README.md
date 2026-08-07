# Anonymization Service

Микросервис анонимизации персональных данных в русскоязычных текстах.
Использует Microsoft Presidio + кастомные распознаватели для русского языка.

**Самостоятельный сервис.** Ядро (обезличивание текста через `/anonymize/text`)
работает автономно и не требует БД. Интеграция с Chatwoot — **опциональная**,
включается флагом `CHATWOOT_ENABLED=true` и добавляет эндпоинты для работы
с базой Chatwoot (conversation/batch) и webhook. По умолчанию флаг выключен.

---

## 1. Клонирование репозитория

```bash
git clone https://github.com/your-org/your-repo.git
cd your-repo
```

---

## 2. Настройка переменных окружения

```bash
cp .env.example .env
```

Сервис работает в двух режимах. Что заполнять в `.env` — зависит от режима.

### Режим A. Автономный (по умолчанию) — обезличивание текста

Подключение к БД и Chatwoot не нужно. Достаточно:

```env
CHATWOOT_ENABLED=false          # можно не указывать — это значение по умолчанию
API_KEY=<длинный_случайный_ключ>  # защита эндпоинтов; пусто = без аутентификации (только для разработки)
PERSON_MODEL_DIR=/app/models/person_ruBERT  # модель ФИО; ОБЯЗАТЕЛЬНА — без неё сервис не стартует
```

`DATABASE_URL` и `CHATWOOT_WEBHOOK_SECRET` в этом режиме не требуются.

### Режим B. С интеграцией Chatwoot

Добавляются параметры БД. `DATABASE_URL` обязателен — без него сервис не
стартует (fail-fast).

```env
CHATWOOT_ENABLED=true
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DB_NAME
CHATWOOT_WEBHOOK_SECRET=<секрет_из_chatwoot>   # желателен на проде; пусто = проверка подписи выключена
API_KEY=<ключ>
PERSON_MODEL_DIR=/app/models/person_ruBERT
```

| Параметр | Описание | Пример |
|----------|----------|--------|
| USER | Имя пользователя PostgreSQL | `chatwoot` |
| PASSWORD | Пароль | `secret123` |
| HOST | Хост БД | `localhost` / `192.168.1.100` / `chatwoot-db` |
| PORT | Порт PostgreSQL | `5432` |
| DB_NAME | Имя базы данных | `chatwoot_production` |

Пример для БД в Docker-сети:
```env
DATABASE_URL=postgresql://chatwoot:secret123@chatwoot-db:5432/chatwoot_production
```

### Режим C. Обезличивание документов (PDF / Word)

Опциональный адаптер: приём файлов `.docx` и `.pdf`. Включается флагом и не зависит
от Chatwoot — можно комбинировать с любым режимом выше.

```env
DOCUMENT_ENABLED=true           # по умолчанию false — эндпоинт /anonymize/document выключен
# Необязательные лимиты (значения по умолчанию):
DOCUMENT_MAX_BYTES=20971520     # 20 МБ на файл
DOCUMENT_MAX_PDF_PAGES=100      # предел страниц PDF
DOCUMENT_PDF_DPI=150            # DPI растеризации PDF
```

При `DOCUMENT_ENABLED=false` библиотеки для документов не загружаются, ядро остаётся лёгким.

---

## 3. Запуск через Docker

### Вариант A: Автономный режим (по умолчанию)

БД не нужна. `.env` — как в Режиме A (шаг 2). Поднимается один контейнер:

```bash
docker compose up --build -d
```

Сервис `db` в `docker-compose.yml` по умолчанию закомментирован — он нужен
только для интеграции с Chatwoot (Вариант C).

### Вариант B: Подключение к существующей БД Chatwoot (продакшн)

`.env` — как в Режиме B (`CHATWOOT_ENABLED=true` + `DATABASE_URL`). Сервис
подключается к базе Chatwoot напрямую:

```bash
docker compose up --build -d
```

Если БД Chatwoot работает в отдельной Docker-сети, подключите сервис к ней.
Откройте `docker-compose.yml` и добавьте:

```yaml
services:
  anonymizer:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    networks:
      - chatwoot_network

networks:
  chatwoot_network:
    external: true
```

Имя сети (`chatwoot_network`) замените на реальное.
Узнать его можно командой:

```bash
docker network ls
```

### Вариант C: Локальная разработка с тестовой БД

Для тестирования интеграции без настоящей БД Chatwoot. Поднимается свой
PostgreSQL с тестовыми данными (3 контакта, 3 разговора, 6 сообщений).
Раскомментируйте сервис `db` и `depends_on` в `docker-compose.yml`. Порт
Postgres наружу не публикуется — доступ только внутри Docker-сети:

```yaml
services:
  db:
    image: postgres:16-alpine
    env_file: .env
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql

  anonymizer:
    build: .
    ports:
      - "8000:8000"
    environment:
      CHATWOOT_ENABLED: "true"
      DATABASE_URL: postgresql://user:password@db:5432/conversations_db
    depends_on:
      - db

volumes:
  pgdata:
```

```bash
docker compose up --build -d
```

---

## 4. Проверка работоспособности

После запуска сервис доступен на `http://localhost:8000`.

Проверка статуса:
```bash
curl http://localhost:8000/health
```

Ожидаемый ответ:
```json
{
  "status": "ok",
  "analyzer_ready": true,
  "person_model_loaded": true,
  "chatwoot_enabled": false,
  "db_connected": null,
  "supported_entities": ["CREDIT_CARD", "DATE_OF_BIRTH", "EMAIL_ADDRESS", "INN", "PASSPORT", "PERSON", "PHONE_NUMBER", "SNILS"]
}
```

`db_connected` равен `null` в автономном режиме (БД не используется). При
`CHATWOOT_ENABLED=true` поле показывает `true`/`false` по состоянию базы, а
`status` становится `degraded`, если база недоступна.

`person_model_loaded` показывает, загружена ли модель распознавания ФИО. **В проде
должно быть `true`.** Если `false` — ФИО не распознаются и уйдут в ответ открытым
текстом; `status` при этом `degraded`. Обычно сервис в таком состоянии просто не
стартует, но если он был запущен с `ALLOW_NO_PERSON_MODEL=true` (режим для тестов
и CI) — это единственный способ увидеть проблему снаружи.

Swagger UI (интерактивная документация API):
```
http://localhost:8000/docs
```

---

## 5. Интеграция с Chatwoot (webhook)

Сервис интегрируется с Chatwoot через вебхуки — **без изменений в основном проекте**.
Работает по той же схеме, что и SpringQwenWebhook (AI-бот).

### Как подключить

1. Откройте Chatwoot: **Settings -> Integrations -> Webhooks -> Add new webhook**
2. Укажите URL: `http://anonymizer:8000/webhook` (или `http://localhost:8000/webhook`)
3. Выберите событие: `message_created`
4. Сохраните

Теперь при каждом новом сообщении Chatwoot автоматически отправляет
его на наш сервис. Сервис анонимизирует текст и данные отправителя.

### Как это работает в архитектуре

```
Пользователь пишет сообщение в чат
          |
          v
     +-----------+
     |  Chatwoot  |  (основной проект, не трогаем)
     +-----------+
          |
          | webhook: message_created
          |
          v
+-------------------------+                    +------------------------+
|  Anonymization Service  |                    |  SpringQwenWebhook     |
|  POST /webhook          |                    |  (AI-бот)              |
|                         |                    |                        |
|  1. Получает сообщение  |   анонимизирован-  |  Получает чистый текст |
|  2. Находит ПДн         |-- ный текст -------->  без ПДн              |
|  3. Заменяет на         |                    |  Генерирует ответ      |
|     плейсхолдеры        |                    |  Отправляет в Chatwoot |
+-------------------------+                    +------------------------+
          |
          | Также можно вызывать
          | напрямую по HTTP
          |
          v
   Любой другой сервис
   POST /anonymize/text
   POST /anonymize/conversation
```

Сервис **только читает** данные — ничего не записывает и не изменяет в БД.

### Пример webhook payload от Chatwoot

```json
{
  "event": "message_created",
  "id": 100,
  "content": "Здравствуйте, меня зовут Иван Петров, тел +79991234567",
  "message_type": "incoming",
  "conversation": {"id": 1, "status": "open"},
  "sender": {
    "id": 10,
    "name": "Иван Петров",
    "email": "ivan@mail.ru",
    "phone_number": "+79991234567"
  }
}
```

### Ответ сервиса

```json
{
  "event": "message_created",
  "message_id": 100,
  "conversation_id": 1,
  "original_content": "Здравствуйте, меня зовут Иван Петров, тел +79991234567",
  "anonymized_content": "Здравствуйте, меня зовут <PERSON>, тел <PHONE>",
  "sender_anonymized": {
    "id": 10,
    "name": "<PERSON>",
    "email": "<EMAIL>",
    "phone_number": "<PHONE>"
  },
  "entities_found": [...],
  "total_entities": 4
}
```

---

## 6. Использование API напрямую

### 6.1 Анонимизация произвольного текста

Не требует БД. Принимает текст, возвращает обезличенный.

```bash
curl -X POST http://localhost:8000/anonymize/text \
  -H "Content-Type: application/json" \
  -d '{"text": "Меня зовут Иван Петров, тел +7 999 123 45 67, email ivan@mail.ru"}'
```

Ответ:
```json
{
  "original": "Меня зовут Иван Петров, тел +7 999 123 45 67, email ivan@mail.ru",
  "anonymized": "Меня зовут <PERSON>, тел <PHONE>, email <EMAIL>",
  "entities_found": [
    {"entity_type": "PERSON", "start": 12, "end": 24, "score": 0.85, "value": "Иван Петров"},
    {"entity_type": "PHONE_NUMBER", "start": 30, "end": 48, "score": 0.9, "value": "+7 999 123 45 67"},
    {"entity_type": "EMAIL_ADDRESS", "start": 56, "end": 69, "score": 0.9, "value": "ivan@mail.ru"}
  ],
  "mapping": {
    "<PERSON>": "Иван Петров",
    "<PHONE>": "+7 999 123 45 67",
    "<EMAIL>": "ivan@mail.ru"
  }
}
```

### 6.2 Анонимизация разговора из БД

Подтягивает из БД conversation + все messages + contact и обезличивает.

```bash
curl -X POST http://localhost:8000/anonymize/conversation \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": 1}'
```

Ответ содержит:
- анонимизированные поля conversation (identifier, additional_attributes, custom_attributes)
- анонимизированный contact (name, email, phone, attributes)
- список всех messages с анонимизированным content

### 6.3 Пакетная анонимизация

Несколько разговоров за один запрос:

```bash
curl -X POST http://localhost:8000/anonymize/batch \
  -H "Content-Type: application/json" \
  -d '{"conversation_ids": [1, 2, 3]}'
```

### 6.4 Обезличивание документа (PDF / Word)

Требует `DOCUMENT_ENABLED=true`. Принимает файл `.docx` или `.pdf`, возвращает
обезличенную версию тем же типом (multipart-загрузка).

```bash
curl -X POST http://localhost:8000/anonymize/document \
  -F "file=@/path/to/document.docx" \
  -o anonymized_document.docx
```

- **Word (.docx):** обезличивается тело, таблицы и колонтитулы; очищаются свойства
  документа (автор и т.п.). Вёрстка сохраняется.
- **PDF:** страницы растеризуются, области с ПДн закрашиваются, файл собирается заново
  — на выходе **нет текстового слоя**, скопировать ПДн из результата нельзя.
- Сводка о найденном (без значений ПДн) — в заголовке ответа `X-Anonymization-Summary`.
- `mapping` для документов не возвращается (это ключ де-анонимизации целого файла).
- Необязательный form-параметр `disable_entities` (список типов через запятую) —
  как в `/anonymize/text`, только сужение.

---

## 7. Вызов из другого сервиса (Python)

```python
import httpx

ANONYMIZER_URL = "http://anonymizer:8000"  # имя контейнера в Docker-сети

# Текст на лету
response = httpx.post(f"{ANONYMIZER_URL}/anonymize/text", json={
    "text": "Клиент Иван Петров, тел +79991234567"
})
clean = response.json()["anonymized"]
# "Клиент <PERSON>, тел <PHONE>"

# Целый разговор из БД
response = httpx.post(f"{ANONYMIZER_URL}/anonymize/conversation", json={
    "conversation_id": 42
})
data = response.json()
for msg in data["messages"]:
    print(msg["anonymized_content"])
```

---

## 8. Что анонимизируется

| Тип ПДн | Плейсхолдер | Пример |
|---------|-------------|--------|
| ФИО | `<PERSON>` | Иван Петров -> `<PERSON>` |
| Телефон | `<PHONE>` | +7 999 123 45 67 -> `<PHONE>` |
| Email | `<EMAIL>` | ivan@mail.ru -> `<EMAIL>` |
| ИНН | `<INN>` | 772012345678 -> `<INN>` |
| СНИЛС | `<SNILS>` | 123-456-789 00 -> `<SNILS>` |
| Паспорт | `<PASSPORT>` | 45 15 678901 -> `<PASSPORT>` |
| Дата рождения | `<DATE_OF_BIRTH>` | 15.03.1990 -> `<DATE_OF_BIRTH>` |
| Банковская карта | `<CREDIT_CARD>` | 4276 1234 5678 9012 -> `<CREDIT_CARD>` |

### Форматы на входе

| Формат | Эндпоинт | Требует |
|--------|----------|---------|
| Произвольный текст | `/anonymize/text` | — |
| Разговор/пакет из БД (JSON) | `/anonymize/conversation`, `/anonymize/batch` | `CHATWOOT_ENABLED=true` |
| Word `.docx`, PDF | `/anonymize/document` | `DOCUMENT_ENABLED=true` |

### Что НЕ анонимизируется

**LOCATION** (города, адреса, улицы) — по требованию проекта остаются в тексте как есть.

### Какие поля обрабатываются из БД

| Таблица | Поля |
|---------|------|
| conversations | identifier, additional_attributes, custom_attributes |
| messages | content, content_attributes |
| contacts | name, email, phone, additional_attributes, custom_attributes |

---

## 9. Запуск тестов

```bash
# Локально (без Docker)
cd source/realization
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download ru_core_news_lg
python -m pytest tests/ -v
```

---

## 10. Структура проекта

```
realization/
├── app/
│   ├── main.py               # FastAPI-приложение, ядро: /health, /anonymize/text
│   ├── auth.py                # Проверка API-ключа (общая)
│   ├── config.py              # Настройки из .env (CHATWOOT_ENABLED, DATABASE_URL, ...)
│   ├── models.py              # Pydantic-схемы ядра
│   ├── anonymizer.py          # Логика анонимизации (Presidio + кастомные распознаватели)
│   ├── custom_recognizers.py  # Regex-распознаватели для русских ПДн
│   └── integrations/
│       ├── chatwoot/          # Опциональный адаптер Chatwoot (за CHATWOOT_ENABLED)
│       │   ├── database.py    #   SQLAlchemy-модели + ленивое подключение к БД
│       │   ├── schemas.py     #   Pydantic-схемы Chatwoot
│       │   ├── service.py     #   Обход conversation → messages → contacts
│       │   └── router.py      #   Эндпоинты /anonymize/conversation, /batch, /webhook
│       └── documents/         # Опциональный адаптер документов (за DOCUMENT_ENABLED)
│           ├── docx_handler.py #   Обезличивание Word (.docx) — тело/таблицы/колонтитулы
│           ├── pdf_handler.py  #   Обезличивание PDF растеризацией (без AGPL)
│           ├── metadata.py     #   Очистка метаданных документа
│           └── router.py       #   Эндпоинт /anonymize/document
├── data/
│   └── ru_training_data.csv   # Датасет для тестирования качества распознавания
├── tests/
│   ├── conftest.py            # Фикстуры pytest
│   ├── test_anonymizer.py     # Тесты модуля анонимизации (28 тестов)
│   └── test_api.py            # Тесты API + webhook (15 тестов)
├── Dockerfile                 # Образ сервиса
├── docker-compose.yml         # Оркестрация контейнеров
├── init.sql                   # Тестовые данные для локальной БД
├── requirements.txt           # Python-зависимости
├── .env.example               # Шаблон переменных окружения
└── .dockerignore
```
