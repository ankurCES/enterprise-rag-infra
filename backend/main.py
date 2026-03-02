from fastapi import FastAPI, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
import datetime

from .models import ChatSession, ChatMessage, get_db, init_db
from .auth import verify_microsoft_sso

app = FastAPI(title="Enterprise RAG Backend - FastAPI Foundation")

@app.on_event("startup")
def on_startup():
    init_db()

@app.post("/chat")
async def chat(
    message: str = Body(..., embed=True),
    session_id: Optional[str] = Body(None, embed=True),
    current_user: dict = Depends(verify_microsoft_sso),
    db: Session = Depends(get_db)
):
    """
    Accepts a user message and an optional session_id.
    If no session_id is provided, a new session is created.
    """
    # 1. Resolve or create a new session
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
        # Verify the session exists and belongs to the user
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id, 
            ChatSession.user_id == current_user["user_id"]
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or unauthorized.")

    # 2. Store the user's message
    user_msg = ChatMessage(session_id=session_id, role="user", content=message)
    db.add(user_msg)
    db.commit()

    # 3. Generate a mock assistant response (LiteLLM/RAG logic will go here)
    mock_assistant_content = f"Mock response to: {message}. (RAG logic pending implementation)"
    assistant_msg = ChatMessage(session_id=session_id, role="assistant", content=mock_assistant_content)
    db.add(assistant_msg)
    db.commit()

    return {
        "session_id": session_id,
        "response": mock_assistant_content,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

@app.get("/history/{session_id}")
async def get_history(
    session_id: str,
    current_user: dict = Depends(verify_microsoft_sso),
    db: Session = Depends(get_db)
):
    """Retrieves the chat history for a specific session."""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, 
        ChatSession.user_id == current_user["user_id"]
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or unauthorized.")
        
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
    
    return [
        {"id": s.id, "email": s.user_email, "created_at": s.created_at} 
        for s in sessions
    ]
