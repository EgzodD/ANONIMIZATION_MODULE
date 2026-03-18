-- Contacts
CREATE TABLE IF NOT EXISTS contacts (
    id SERIAL PRIMARY KEY,
    account_id INTEGER,
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    identifier VARCHAR(255),
    additional_attributes JSONB,
    custom_attributes JSONB,
    last_activity_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    account_id INTEGER,
    inbox_id INTEGER,
    contact_id INTEGER REFERENCES contacts(id),
    contact_inbox_id INTEGER,
    assignee_id INTEGER,
    team_id INTEGER,
    status INTEGER DEFAULT 0,
    priority INTEGER DEFAULT 0,
    display_id INTEGER NOT NULL,
    uuid VARCHAR(36) NOT NULL,
    identifier VARCHAR(255),
    agent_last_seen_at TIMESTAMP,
    contact_last_seen_at TIMESTAMP,
    locked BOOLEAN DEFAULT FALSE,
    first_reply_created_at TIMESTAMP,
    last_activity_at TIMESTAMP DEFAULT NOW(),
    additional_attributes JSONB,
    custom_attributes JSONB,
    snoozed_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id),
    account_id INTEGER,
    inbox_id INTEGER,
    user_id INTEGER,
    contact_id INTEGER,
    message_type INTEGER DEFAULT 0,
    content_type INTEGER DEFAULT 0,
    status INTEGER DEFAULT 0,
    content TEXT,
    content_attributes JSONB,
    private BOOLEAN DEFAULT FALSE,
    source_id VARCHAR(255),
    external_source_ids JSONB,
    sender_type VARCHAR(50),
    sender_id INTEGER,
    echo_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Test data: contacts
INSERT INTO contacts (id, account_id, name, email, phone) VALUES
(10, 1, 'Иван Сергеевич Петров', 'ivan.petrov@yandex.ru', '+7 999 123 45 67'),
(20, 1, 'Мария Николаевна Сидорова', 'm.sidorova@mail.ru', '8 (495) 555-12-34'),
(30, 1, 'Алексей Козлов', 'a.kozlov@gmail.com', '+79037778899');

-- Test data: conversations
INSERT INTO conversations (id, account_id, inbox_id, contact_id, display_id, uuid, identifier, status, additional_attributes, custom_attributes) VALUES
(1, 1, 1, 10, 1, 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'Иван Петров', 0,
 '{"browser": "Chrome", "referer": "https://example.com"}',
 '{"comment": "VIP клиент, ИНН 772012345678"}'),
(2, 1, 2, 20, 2, 'b2c3d4e5-f6a7-8901-bcde-f12345678901', NULL, 1,
 '{"browser": "Firefox"}',
 '{"note": "СНИЛС 123-456-789 00"}'),
(3, 1, 1, 30, 3, 'c3d4e5f6-a7b8-9012-cdef-123456789012', 'support@company.ru', 0,
 NULL, NULL);

-- Test data: messages
INSERT INTO messages (conversation_id, account_id, inbox_id, contact_id, message_type, content, sender_type, sender_id) VALUES
(1, 1, 1, 10, 0, 'Здравствуйте, меня зовут Иван Петров. Мой телефон +7 999 123 45 67, email ivan.petrov@yandex.ru', 'Contact', 10),
(1, 1, 1, NULL, 1, 'Здравствуйте, Иван! Чем могу вам помочь?', 'User', 1),
(1, 1, 1, 10, 0, 'Хочу оформить кредит. Мой ИНН 772012345678, паспорт 45 15 678901', 'Contact', 10),
(2, 1, 2, 20, 0, 'Добрый день! Я Мария Сидорова, СНИЛС 123-456-789 00, дата рождения 15.03.1990', 'Contact', 20),
(2, 1, 2, NULL, 1, 'Мария Николаевна, заявка оформлена. Проверьте данные.', 'User', 2),
(3, 1, 1, 30, 0, 'Прошу перевести на карту 4276 1234 5678 9012 получателю Алексей Козлов в Москве', 'Contact', 30);
