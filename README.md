# Enterprise RAG Infra: SMB Document Intelligence

A production-grade Retrieval-Augmented Generation (RAG) application designed for engineering teams. It polls a Windows SMB share for documents, vectorizes them into Qdrant, and serves a streaming React frontend via a FastAPI backend—all secured with Microsoft Azure AD SSO.

## 🚀 Architecture Overview

- **Frontend**: React (Vite) + Tailwind CSS + MSAL (Microsoft SSO) + SSE Streaming.
- **Backend**: FastAPI (Python 3.10) + SQLAlchemy (PostgreSQL) + LiteLLM (Routing).
- **Worker**: Python daemon using `smbprotocol` for polling, LangChain for chunking, and Qdrant for vectorization.
- **Vector Store**: Qdrant (High-performance similarity search).
- **Database**: PostgreSQL (Chat session and message history).
- **LLM Routing**: LiteLLM (Supports Azure OpenAI, Anthropic, OpenAI, etc.).

---

## 🛠️ Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/ankurCES/enterprise-rag-infra.git
cd enterprise-rag-infra
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```
Key variables to configure:
- **Azure AD**: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` for SSO.
- **SMB Share**: `SMB_SHARE_PATH`, `SMB_USERNAME`, `SMB_PASSWORD`.
- **LLM**: `LITELLM_MODEL`, `LITELLM_API_KEY`.

### 3. Deploy with Docker Compose
The infrastructure is optimized for **Windows Server** hosts but runs on any Docker-enabled machine. Ensure the `cifs-utils` package is installed on the host if using the SMB volume driver.

```bash
docker-compose up -d --build
```

---

## 📂 Project Structure

- `frontend/`: React application (Vite/TS).
- `backend/`: FastAPI server and database models.
- `worker/`: SMB polling and ingestion logic.
- `docker-compose.yml`: Multi-container orchestration.

---

## 🔒 Security Features

- **Microsoft SSO**: Every request to the backend is validated via Azure AD JWT tokens.
- **Persistent Storage**: Uses PostgreSQL for chat history and a local SQLite database in the worker for delta-ingestion tracking.
- **SMB CIFS Driver**: Securely mounts Windows shares directly into the worker container as a read-only volume.

---

## 📖 Usage

1. **Ingestion**: Drop PDF, DOCX, or TXT files into your configured SMB share. The worker will automatically detect, chunk, and vectorize them.
2. **Chat**: Log in via the React frontend using your corporate Microsoft account.
3. **Reference**: Ask questions about your engineering docs. The AI will respond with real-time streaming and cite the exact file paths from the SMB share.

---

## 👨‍💻 Author
**Ankur** (ankurCES) - *AI Solution Architect*
