# Enterprise RAG Application Infrastructure

## Docker Services
- **Frontend**: React (Vite) + Nginx
- **Backend**: FastAPI (Python 3.10+)
- **Worker**: Python (SMB Polling + Ingestion)
- **Vector Database**: Qdrant
- **Relational Database**: PostgreSQL (Chat History)

## Host Configuration
- **Host OS**: Windows Server
- **Storage**: External Windows SMB Share (via CIFS driver)

## Routing & Orchestration
- **LLM Routing**: LiteLLM
- **Containerization**: Docker Compose
