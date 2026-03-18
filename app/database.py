from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer)
    name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    identifier = Column(String(255))
    additional_attributes = Column(JSONB)
    custom_attributes = Column(JSONB)
    last_activity_at = Column(DateTime)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer)
    inbox_id = Column(Integer)
    contact_id = Column(Integer)
    contact_inbox_id = Column(Integer)
    assignee_id = Column(Integer)
    team_id = Column(Integer)
    status = Column(Integer)
    priority = Column(Integer)
    display_id = Column(Integer, nullable=False)
    uuid = Column(String(36), nullable=False)
    identifier = Column(String(255))
    agent_last_seen_at = Column(DateTime)
    contact_last_seen_at = Column(DateTime)
    locked = Column(Boolean)
    first_reply_created_at = Column(DateTime)
    last_activity_at = Column(DateTime)
    additional_attributes = Column(JSONB)
    custom_attributes = Column(JSONB)
    snoozed_until = Column(DateTime)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    messages = relationship("Message", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer)
    account_id = Column(Integer)
    inbox_id = Column(Integer)
    user_id = Column(Integer)
    contact_id = Column(Integer)
    message_type = Column(Integer)
    content_type = Column(Integer)
    status = Column(Integer)
    content = Column(Text)
    content_attributes = Column(JSONB)
    private = Column(Boolean)
    source_id = Column(String(255))
    external_source_ids = Column(JSONB)
    sender_type = Column(String(50))
    sender_id = Column(Integer)
    echo_id = Column(String(255))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    conversation = relationship("Conversation", back_populates="messages")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
