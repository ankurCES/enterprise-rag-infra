import os
import time
import uuid
import sqlite3
import hashlib
from datetime import datetime
from typing import List, Dict, Any

# SMB Protocol
from smbprotocol.connection import Connection
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect
from smbprotocol.file import FileOpen, FileAttributes, CreateOptions, FilePipePrinterAccessMask, ShareAccess

# Document Parsing & Chunking
from langchain.text_splitter import RecursiveCharacterTextSplitter
import pypdf
import docx2txt

# LLM & Vector Store
from litellm import embedding
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

# Configuration
SMB_HOST = os.getenv("SMB_HOST", "192.168.1.100")
SMB_USER = os.getenv("SMB_USERNAME", "user")
SMB_PASS = os.getenv("SMB_PASSWORD", "password")
SMB_SHARE = os.getenv("SMB_SHARE_NAME", "engineering-docs")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "engineering_docs")

# Initialize Clients
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# State Management (Local SQLite for Delta Tracking)
def init_state_db():
    conn = sqlite3.connect("ingestion_state.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            file_path TEXT PRIMARY KEY,
            last_modified TEXT,
            file_hash TEXT
        )
    """)
    conn.commit()
    return conn

def get_processed_files(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT file_path, last_modified FROM processed_files")
    return {row[0]: row[1] for row in cursor.fetchall()}

def update_file_state(conn, file_path, last_modified, file_hash):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO processed_files (file_path, last_modified, file_hash)
        VALUES (?, ?, ?)
    """, (file_path, last_modified, file_hash))
    conn.commit()

# Document Processing
def parse_document(file_content: bytes, file_ext: str) -> str:
    if file_ext == ".pdf":
        import io
        pdf = pypdf.PdfReader(io.BytesIO(file_content))
        return "\n".join([page.extract_text() for page in pdf.pages])
    elif file_ext == ".docx":
        import io
        return docx2txt.process(io.BytesIO(file_content))
    elif file_ext == ".txt":
        return file_content.decode("utf-8")
    return ""

def chunk_text(text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ".", "!", "?", " ", ""]
    )
    chunks = splitter.split_text(text)
    return [{"content": chunk, "metadata": metadata} for chunk in chunks]

# Vectorization
def upsert_to_qdrant(chunks: List[Dict[str, Any]]):
    # Ensure collection exists
    if not qdrant_client.collection_exists(COLLECTION_NAME):
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qmodels.VectorParams(size=1536, distance=qmodels.Distance.COSINE) # Default for OpenAI embeddings via LiteLLM
        )

    for chunk in chunks:
        # Generate Embeddings via LiteLLM
        response = embedding(
            model=os.getenv("LITELLM_EMBEDDING_MODEL", "openai/text-embedding-3-small"),
            input=[chunk["content"]]
        )
        vector = response["data"][0]["embedding"]

        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                qmodels.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "text": chunk["content"],
                        "file_path": chunk["metadata"]["file_path"],
                        "last_modified": chunk["metadata"]["last_modified"]
                    }
                )
            ]
        )

# Main Polling Loop
def run_worker():
    state_conn = init_state_db()
    
    # Establish SMB Connection
    connection = Connection(uuid.uuid4(), SMB_HOST, 445)
    connection.connect()
    session = Session(connection, SMB_USER, SMB_PASS)
    session.connect()
    tree = TreeConnect(session, f"\\\\{SMB_HOST}\\{SMB_SHARE}")
    tree.connect()

    print(f"[*] Worker started. Polling \\\\{SMB_HOST}\\{SMB_SHARE} every {POLL_INTERVAL}s...")

    while True:
        try:
            processed = get_processed_files(state_conn)
            
            # Simplified SMB File Listing (Recursive)
            # In a real enterprise app, use a proper recursive walker
            files_to_check = [] # This would be populated by tree.query_directory
            
            # Logic for delta:
            # 1. List all files on share
            # 2. Compare modified time with state_db
            # 3. If new/modified:
            #    - Read file content
            #    - Parse -> Chunk -> Vectorize
            #    - Update state_db
            # 4. If file deleted on share:
            #    - Remove from vector store (optional)
            #    - Remove from state_db

            print(f"[{datetime.now()}] Polling share...")
            # (SMB listing implementation here...)

            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"[!] Error in worker loop: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_worker()
