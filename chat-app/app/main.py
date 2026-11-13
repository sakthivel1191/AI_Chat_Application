import os
import time
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed
from dotenv import load_dotenv
from app.database import Base, engine, get_db, SessionLocal
from app.models import ChatSession, Message
from app.security import verify_api_key

load_dotenv()
Base.metadata.create_all(bind=engine)
app = FastAPI(title="AI Chat Application")
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)
MODEL = os.getenv("MODEL")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", 10))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", 1000))
class ChatRequest(BaseModel):
    message: str
@app.post("/sessions")
def create_session(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    session = ChatSession(api_key_hash=api_key)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": session.id}
@app.get("/sessions/{session_id}/messages")
def get_messages(
    session_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    session = db.query(ChatSession).filter_by(
        id=session_id,
        api_key_hash=api_key
    ).first()
    if not session:
        raise HTTPException(404, "Session not found")
    messages = db.query(Message).filter_by(
        session_id=session_id
    ).order_by(Message.created_at).all()
    return [
        {
            "role": m.role,
            "content": m.content,
            "tokens": m.tokens,
            "created_at": m.created_at
        }
        for m in messages
    ]
@app.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    session = db.query(ChatSession).filter_by(
        id=session_id,
        api_key_hash=api_key
    ).first()
    if not session:
        raise HTTPException(404, "Session not found")
    db.delete(session)
    db.commit()
    return {"message": "Session deleted"}
@app.post("/sessions/{session_id}/chat")
def chat(
    session_id: str,
    data: ChatRequest,
    response: Response,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    session = db.query(ChatSession).filter_by(
        id=session_id,
        api_key_hash=api_key
    ).first()
    if not session:
        raise HTTPException(404, "Session not found")
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    message_count = (
        db.query(func.count(Message.id))
        .join(ChatSession)
        .filter(
            ChatSession.api_key_hash == api_key,
            Message.role == "user",
            Message.created_at >= one_hour_ago
        )
        .scalar()
    )
    if message_count >= 20:
        response.headers["Retry-After"] = "3600"
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "3600"}
        )
    user_message = Message(
        session_id=session_id,
        role="user",
        content=data.message,
        tokens=max(1, len(data.message) // 4)
    )
    db.add(user_message)
    db.commit()
    history = db.query(Message).filter_by(
        session_id=session_id
    ).order_by(Message.created_at).all()
    history = history[-MAX_HISTORY:]
    messages = [
        {"role": "system", "content": "You are a helpful assistant."}
    ]
    for msg in history:
        messages.append({
            "role": msg.role,
            "content": msg.content
        })
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def get_stream():
        return client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=MAX_TOKENS,
            stream=True
        )
    def generate():
        answer = ""
        try:
            stream = get_stream()
            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    answer += content
                    yield content
            input_tokens = sum(m.tokens for m in history)
            output_tokens = max(1, len(answer) // 4)
            total_tokens = input_tokens + output_tokens
            input_cost = float(os.getenv("INPUT_COST_PER_MILLION", "0"))
            output_cost = float(os.getenv("OUTPUT_COST_PER_MILLION", "0"))
            cost = (
                input_tokens * input_cost +
                output_tokens * output_cost
            ) / 1_000_000
            stream_db = SessionLocal()
            try:
                assistant_message = Message(
                    session_id=session_id,
                    role="assistant",
                    content=answer,
                    tokens=output_tokens
                )
                chat_session = stream_db.query(ChatSession).filter_by(
                    id=session_id
                ).first()
                if chat_session:
                    chat_session.total_tokens += total_tokens
                    chat_session.total_cost += cost
                    stream_db.add(assistant_message)
                    stream_db.commit()
            finally:
                stream_db.close()
        except Exception:
            yield "\nSorry, something went wrong. Please try again."
    return StreamingResponse(
        generate(),
        media_type="text/plain"
    )
@app.get("/usage")
def get_usage(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    sessions = db.query(ChatSession).filter_by(
        api_key_hash=api_key
    ).all()
    return {
        "total_sessions": len(sessions),
        "total_tokens": sum(s.total_tokens for s in sessions),
        "total_cost": round(sum(s.total_cost for s in sessions), 6)
    }
