import os
import uuid
import datetime
import json
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from litellm import embedding, acompletion

from .models import ChatSession, ChatMessage, get_db, init_db
from .auth import verify_microsoft_sso

app = FastAPI(title="Enterprise RAG Backend - RAG & Streaming")

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "engineering_docs")
EMBEDDING_MODEL = os.getenv("LITELLM_EMBEDDING_MODEL", "openai/text-embedding-3-small")
LLM_MODEL = os.getenv("LITELLM_MODEL", "gpt-4")

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

@app.on_event("startup")
def on_startup():
    init_db()

async def get_rag_context(query: str):
    """Embed query and search Qdrant for relevant engineering document chunks."""
    try:
        # 1. Embed user query
        resp = embedding(model=EMBEDDING_MODEL, input=[query])
        vector = resp["data"][0]["embedding"]

        # 2. Search Qdrant
        search_result = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            limit=5
        )

        # 3. Assemble context with metadata citations
        context_parts = []
        for hit in search_result:
            source = hit.payload.get("file_path", "Unknown Source")
            content = hit.payload.get("text", "")
            context_parts.append(f"SOURCE: {source}\nCONTENT: {content}\n---\n")
            
        return "\n".join(context_parts)
    except Exception as e:
        print(f"RAG Retrieval Error: {e}")
        return ""

@app.post("/chat")
async def chat(
    message: str = Body(..., embed=True),
    session_id: Optional[str] = Body(None, embed=True),
    current_user: dict = Depends(verify_microsoft_sso),
    db: Session = Depends(get_db)
):
    """
    RAG-Enabled Streaming Chat Endpoint.
    Uses LiteLLM for retrieval and generation.
    Returns a Server-Sent Events (SSE) stream.
    """
    # 1. Resolve or create session
    if not session_id:
        session_id = str(uuid.uuid4())
        new_session = ChatSession(
            id=session_id,
            user_id=current_user["user_id"],
            user_email=current_user["email"]
        )
        db.add(new_session)
        db.commit()
    else:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user["user_id"]
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")

    # 2. Persist user message
    user_msg = ChatMessage(session_id=session_id, role="user", content=message)
    db.add(user_msg)
    db.commit()

    # 3. Retrieve context and history
    context = await get_rag_context(message)
    history = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    
    # 4. Prepare message payload
    messages = [
        {"role": "system", "content": f"You are a helpful engineering assistant. Use the following context to answer. If the context is empty, answer to the best of your knowledge but specify no internal docs were found.\n\nCONTEXT:\n{context}"}
    ]
    # Add previous chat history (last 10 messages)
    for h in history[-11:-1]: # exclude current user message added above
        messages.append({"role": h.role, "content": h.content})
    # Add current user message
    messages.append({"role": "user", "content": message})

    async def stream_response():
        full_content = ""
        try:
            response = await acompletion(
                model=LLM_MODEL,
                messages=messages,
                stream=True
            )

            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    full_content += content
                    # SSE Format
                    yield f"data: {json.dumps({'content': content})}\n\n"
            
            # 5. After streaming complete, persist assistant message
            db_stream = SessionLocal() # Use fresh session for background persistence
            assistant_msg = ChatMessage(session_id=session_id, role="assistant", content=full_content)
            db_stream.add(assistant_msg)
            db_stream.commit()
            db_stream.close()

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")

@app.get("/history/{session_id}")
async def get_history(
    session_id: str,
    current_user: dict = Depends(verify_microsoft_sso),
    db: Session = Depends(get_db)
):
    """Retrieves chat history for a session."""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user["user_id"]
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    return {
        "session_id": session_id,
        "history": [{"role": m.role, "content": m.content, "timestamp": m.created_at} for m in messages]
    }

@app.get("/sessions")
async def get_sessions(
    current_user: dict = Depends(verify_microsoft_sso),
    db: Session = Depends(get_db)
):
    """Retrieves all chat sessions for the authenticated user."""
    sessions = db.query(ChatSession).filter(
        ChatSession.user_id == current_user["user_id"]
    ).order_by(ChatSession.created_at.desc()).all()
    return [{"id": s.id, "email": s.user_email, "created_at": s.created_at} for s in sessions]

# Needed for stream persistence session
from .models import SessionLocal
