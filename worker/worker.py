import os
import time
import uuid
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

# SMB Protocol
from smbprotocol.connection import Connection
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect
from smbprotocol.file import FileOpen, FileAttributes, CreateOptions, FilePipePrinterAccessMask, ShareAccess

# Document Parsing & Chunking
from langchain_text_splitters import RecursiveCharacterTextSplitter
import pypdf
import docx2txt

# LLM & Vector Store
from litellm import embedding
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
SMB_HOST = os.getenv("SMB_HOST", "192.168.1.100")
SMB_USER = os.getenv("SMB_USERNAME", "user")
SMB_PASS = os.getenv("SMB_PASSWORD", "password")
SMB_SHARE = os.getenv("SMB_SHARE_NAME", "engineering-docs")
SMB_DOMAIN = os.getenv("SMB_DOMAIN", "DOMAIN")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "engineering_docs")

# Initialize Clients
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

class SMBWorker:
    def __init__(self):
        self.state_conn = self.init_state_db()
        self.connection = None
        self.session = None
        self.tree = None

    def init_state_db(self):
        conn = sqlite3.connect("ingestion_state.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_files (
                file_path TEXT PRIMARY KEY,
                last_modified REAL,
                file_hash TEXT
            )
        """)
        conn.commit()
        return conn

    def connect_smb(self):
        """Establish or re-establish SMB connection."""
        try:
            if self.tree:
                try: self.tree.disconnect()
                except: pass
            
            logger.info(f"Connecting to SMB share \\\\{SMB_HOST}\\{SMB_SHARE}...")
            self.connection = Connection(uuid.uuid4(), SMB_HOST, 445)
            self.connection.connect()
            self.session = Session(self.connection, SMB_USER, SMB_PASS, domain=SMB_DOMAIN)
            self.session.connect()
            self.tree = TreeConnect(self.session, f"\\\\{SMB_HOST}\\{SMB_SHARE}")
            self.tree.connect()
            logger.info("SMB Connection established.")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to SMB: {e}")
            return False

    def list_files_recursive(self, path=""):
        """Recursively list files on the SMB share."""
        files = []
        try:
            # Query directory
            search_results = self.tree.query_directory(path, "*")
            for result in search_results:
                filename = result['file_name'].get_value().decode('utf-16-le')
                if filename in [".", ".."]:
                    continue
                
                full_path = f"{path}\\{filename}" if path else filename
                is_dir = result['file_attributes'].get_value() & FileAttributes.FILE_ATTRIBUTE_DIRECTORY
                
                if is_dir:
                    files.extend(self.list_files_recursive(full_path))
                else:
                    if any(filename.lower().endswith(ext) for ext in [".pdf", ".docx", ".txt"]):
                        files.append({
                            "path": full_path,
                            "last_modified": result['last_write_time'].get_value()
                        })
        except Exception as e:
            logger.error(f"Error listing files in {path}: {e}")
            # Potential disconnect, trigger reconnect
            self.connect_smb()
        return files

    def process_file(self, file_info):
        file_path = file_info["path"]
        last_mod = file_info["last_modified"]
        
        try:
            # Check state
            cursor = self.state_conn.cursor()
            cursor.execute("SELECT last_modified FROM processed_files WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            
            if row and row[0] >= last_mod:
                return # Skip unchanged

            logger.info(f"Processing {file_path}...")
            
            # Read file
            file_handle = FileOpen(self.tree, file_path)
            file_handle.create(
                ImpersonationLevel=2,
                DesiredAccess=FilePipePrinterAccessMask.FILE_READ_DATA,
                FileAttributes=0,
                ShareAccess=ShareAccess.FILE_SHARE_READ,
                CreateDisposition=CreateOptions.FILE_OPEN,
                CreateOptions=0
            )
            content = file_handle.read(0, file_handle.get_information(FileAttributes.FILE_ATTRIBUTE_NORMAL)['standard']['end_of_file'].get_value())
            file_handle.close()

            # Parse -> Chunk -> Vectorize
            ext = os.path.splitext(file_path)[1].lower()
            text = parse_document(content, ext)
            if not text: return

            chunks = chunk_text(text, {"file_path": file_path, "last_modified": last_mod})
            upsert_to_qdrant(chunks)

            # Update state
            cursor.execute("INSERT OR REPLACE INTO processed_files (file_path, last_modified) VALUES (?, ?)", (file_path, last_mod))
            self.state_conn.commit()
            logger.info(f"Successfully vectorized {file_path}")

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")

    def run(self):
        if not self.connect_smb():
            return

        while True:
            try:
                files = self.list_files_recursive()
                logger.info(f"Found {len(files)} relevant files. Checking for updates...")
                
                with ThreadPoolExecutor(max_workers=4) as executor:
                    executor.map(self.process_file, files)
                
                time.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(10)
                self.connect_smb()

# Document Processing Functions
def parse_document(file_content: bytes, file_ext: str) -> str:
    import io
    try:
        if file_ext == ".pdf":
            pdf = pypdf.PdfReader(io.BytesIO(file_content))
            return "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        elif file_ext == ".docx":
            return docx2txt.process(io.BytesIO(file_content))
        elif file_ext == ".txt":
            return file_content.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.error(f"Parsing error for {file_ext}: {e}")
    return ""

def chunk_text(text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = splitter.split_text(text)
    return [{"content": chunk, "metadata": metadata} for chunk in chunks]

def upsert_to_qdrant(chunks: List[Dict[str, Any]]):
    if not qdrant_client.collection_exists(COLLECTION_NAME):
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qmodels.VectorParams(size=1536, distance=qmodels.Distance.COSINE)
        )

    points = []
    for chunk in chunks:
        try:
            resp = embedding(model=os.getenv("LITELLM_EMBEDDING_MODEL", "openai/text-embedding-3-small"), input=[chunk["content"]])
            vector = resp["data"][0]["embedding"]
            points.append(qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"text": chunk["content"], **chunk["metadata"]}
            ))
        except Exception as e:
            logger.error(f"Embedding error: {e}")

    if points:
        qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)

if __name__ == "__main__":
    worker = SMBWorker()
    worker.run()
