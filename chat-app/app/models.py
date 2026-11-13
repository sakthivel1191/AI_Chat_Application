import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.database import Base

class ChatSession(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key_hash = Column(String, nullable=False, index=True)
    total_tokens = Column(Integer, default=0)
    total_cost = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    messages = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan"
    )
class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        String,
        ForeignKey("sessions.id"),
        nullable=False
    )
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    session = relationship("ChatSession", back_populates="messages")
    