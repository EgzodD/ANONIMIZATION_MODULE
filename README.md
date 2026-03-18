# Anonymization Service

Микросервис анонимизации персональных данных в русскоязычных текстах.
Использует Microsoft Presidio + кастомные распознаватели для русского языка.
Интегрируется с Chatwoot через webhook — не требует изменений в основном проекте.

---

## 1. Клонирование репозитория

```bash
git clone https://github.com/your-org/your-repo.git
cd your-repo
```

---

## 2. Настройка переменных окружения

Скопируйте файл с примером и заполните данные подключения к БД:

```bash
cp .env.example .env
```

Откройте `.env` и укажите параметры вашей БД Chatwoot:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DB_NAME
```

| Параметр | Описание | Пример |
|----------|----------|--------|
| USER | Имя пользователя PostgreSQL | `chatwoot` |
| PASSWORD | Пароль | `secret123` |
| HOST | Хост БД | `localhost` или `192.168.1.100` или `chatwoot-db` |
| PORT | Порт PostgreSQL | `5432` |
| DB_NAME | Имя базы данных | `chatwoot_production` |

Пример для локальной БД:
```env
DATABASE_URL=postgresql://chatwoot:secret123@localhost:5432/chatwoot_production
```

Пример для БД в Docker-сети:
```env
DATABASE_URL=postgresql://chatwoot:secret123@chatwoot-db:5432/chatwoot_production
```

---

## 3. Запуск через Docker

### Вариант A: Подключение к существующей БД Chatwoot (продакшн)

Сервису нужна только сама БД — он подключается к ней напрямую.
Убедитесь, что `.env` заполнен (шаг 2), затем:

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

### Вариант B: Локальная разработка с тестовой БД

Для тестирования без настоящей БД Chatwoot. Поднимается свой PostgreSQL
с тестовыми данными (3 контакта, 3 разговора, 6 сообщений):

Для этого варианта измените `docker-compose.yml` — раскомментируйте сервис `db`:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
      POSTGRES_DB: conversations_db
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql

  anonymizer:
    build: .
    ports:
      - "8000:8000"
    environment:
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
  "supported_entities": ["CREDIT_CARD", "DATE_OF_BIRTH", "EMAIL_ADDRESS", "INN", "PASSPORT", "PERSON", "PHONE_NUMBER", "SNILS"]
}
```

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
python -m spacy download ru_core_news_sm
python -m pytest tests/ -v
```

---

## 10. Структура проекта

```
realization/
├── app/
│   ├── main.py               # FastAPI-приложение, эндпоинты API + webhook
│   ├── config.py              # Настройки из .env (DATABASE_URL)
│   ├── models.py              # Pydantic-схемы запросов и ответов
│   ├── database.py            # SQLAlchemy-модели (conversations, messages, contacts)
│   ├── anonymizer.py          # Логика анонимизации (Presidio + кастомные распознаватели)
│   └── custom_recognizers.py  # Regex-распознаватели для русских ПДн
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
