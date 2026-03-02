import os
import uuid
import datetime
import json
import logging
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from litellm import embedding, acompletion
from pydantic_settings import BaseSettings

from .models import ChatSession, ChatMessage, get_db, init_db, SessionLocal
from .auth import verify_microsoft_sso

# Configuration via Pydantic Settings
class Settings(BaseSettings):
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "engineering_docs"
    LITELLM_EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    LITELLM_MODEL: str = "gpt-4"
    AZURE_TENANT_ID: str = "common"
    AZURE_CLIENT_ID: str = ""
    DATABASE_URL: str = "postgresql://user:password@db:5432/chat_history"

    class Config:
        env_file = ".env"

settings = Settings()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Enterprise RAG Backend - Production Hardened")

qdrant_client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

@app.on_event("startup")
def on_startup():
    init_db()

async def get_rag_context(query: str):
    """Hybrid Retrieval: Embed query and search Qdrant for document chunks."""
    try:
        resp = embedding(model=settings.LITELLM_EMBEDDING_MODEL, input=[query])
        vector = resp["data"][0]["embedding"]

        # Search with threshold to avoid irrelevant noise
        search_result = qdrant_client.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=vector,
            limit=5,
            score_threshold=0.7 # Minimum similarity
        )

        context_parts = []
        for hit in search_result:
            source = hit.payload.get("file_path", "Unknown Source")
            content = hit.payload.get("text", "")
            context_parts.append(f"SOURCE: {source}\nCONTENT: {content}\n---\n")
            
        return "\n".join(context_parts)
    except Exception as e:
        logger.error(f"RAG Retrieval Error: {e}")
        return ""

@app.post("/chat")
async def chat(
    message: str = Body(..., embed=True),
    session_id: Optional[str] = Body(None, embed=True),
    current_user: dict = Depends(verify_microsoft_sso),
    db: Session = Depends(get_db)
):
    # 1. Session resolution
    if not session_id:
        session_id = str(uuid.uuid4())
        new_session = ChatSession(id=session_id, user_id=current_user["user_id"], user_email=current_user["email"])
        db.add(new_session)
    else:
        session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user["user_id"]).first()
        if not session: raise HTTPException(status_code=404, detail="Session not found.")

    db.add(ChatMessage(session_id=session_id, role="user", content=message))
    db.commit()

    # 2. RAG & History
    context = await get_rag_context(message)
    history = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    
    messages = [
        {"role": "system", "content": f"You are a Senior Engineering Assistant. Use the provided context to answer accurately. Always cite your SOURCE file paths.\n\nCONTEXT:\n{context}"}
    ]
    for h in history[-11:-1]:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": message})

    async def stream_response():
        full_content = ""
        try:
            response = await acompletion(model=settings.LITELLM_MODEL, messages=messages, stream=True)
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    full_content += content
                    yield f"data: {json.dumps({'content': content})}\n\n"
            
            # Background persistence
            with SessionLocal() as db_stream:
                db_stream.add(ChatMessage(session_id=session_id, role="assistant", content=full_content))
                db_stream.commit()
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Streaming Error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")

@app.get("/history/{session_id}")
async def get_history(session_id: str, current_user: dict = Depends(verify_microsoft_sso), db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user["user_id"]).first()
    if not session: raise HTTPException(status_code=404, detail="Session not found.")
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    return {"session_id": session_id, "history": [{"role": m.role, "content": m.content, "timestamp": m.created_at} for m in messages]}

@app.get("/sessions")
async def get_sessions(current_user: dict = Depends(verify_microsoft_sso), db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).filter(ChatSession.user_id == current_user["user_id"]).order_by(ChatSession.created_at.desc()).all()
    return [{"id": s.id, "email": s.user_email, "created_at": s.created_at} for s in sessions]
