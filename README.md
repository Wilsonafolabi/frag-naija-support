# Frag Naija AI Support Engine

> **Secure, RAG-powered AI customer support API for Frag Naija**

Frag Naija AI Support Engine is a production-oriented customer support backend designed to provide accurate, contextual, and secure answers to Frag Naija customers.

The system combines **Retrieval-Augmented Generation (RAG)**, **Groq-hosted LLM inference**, **vector search**, **AI guardrails**, **application security**, and **observability** to create a customer-support engine that can answer questions using official Frag Naija knowledge without requiring model retraining whenever the platform's information changes.

---

## Overview

The system is designed to answer customer questions about:

* Frag Naija
* Supported esports games
* Tournaments
* Wagering rules
* Participation requirements
* Platform features
* Community information
* Frequently asked questions
* Other official customer-facing information

Instead of relying solely on the LLM's internal knowledge, the system retrieves relevant information from an official Frag Naija knowledge base before generating a response.

This significantly reduces unsupported answers and allows the knowledge base to evolve independently of the LLM.

---

# Architecture

```text
                         ┌─────────────────────┐
                         │   Frag Naija User   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │      FastAPI        │
                         │     /chat/ API      │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Security / Guards   │
                         │                     │
                         │ • Validation        │
                         │ • Rate Limiting     │
                         │ • Injection Defense │
                         │ • Authorization     │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Intent Classification│
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Qdrant Vector DB  │
                         │                     │
                         │ Official Knowledge  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Retrieval Security  │
                         │                     │
                         │ Untrusted Context   │
                         │ Injection Protection │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │     Groq LLM        │
                         │                     │
                         │ Customer Response   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Output Guards    │
                         │                     │
                         │ • Safety            │
                         │ • Sensitive Data    │
                         │ • Prompt Leakage    │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Support Response  │
                         └─────────────────────┘

                    ┌────────────────────────────┐
                    │          Langfuse          │
                    │                            │
                    │ Tracing • Evaluation       │
                    │ Latency • Tokens • Cost    │
                    │ Security Events            │
                    └────────────────────────────┘
```

---

# Key Features

## 1. Retrieval-Augmented Generation

The application uses RAG rather than relying exclusively on the LLM.

```text
Customer Question
       ↓
Embedding
       ↓
Vector Search
       ↓
Relevant Official Documents
       ↓
Context Construction
       ↓
Groq LLM
       ↓
Customer Answer
```

This allows the system to answer using Frag Naija-specific information.

---

## 2. Official Knowledge Base

The knowledge layer contains official Frag Naija information such as:

* Product information
* Supported games
* Tournament information
* Wagering information
* Platform features
* Customer-facing policies
* Company information

Retrieved sources are returned with the API response for traceability.

Example:

```json
{
  "title": "Frag Naija Investor Pitch Deck 2026",
  "source": "data/knowledge/fragnaija_pitch_deck.md",
  "status": "official",
  "score": 0.82
}
```

---

# 3. Knowledge Base Updates

The LLM does **not** need to be retrained whenever Frag Naija information changes.

New or updated knowledge can be:

```text
New/Updated Document
        ↓
Text Processing
        ↓
Chunking
        ↓
Embedding Generation
        ↓
Vector Database
        ↓
Available to RAG
```

This makes the system suitable for continuously changing customer-support information.

Future versions can automate this process through:

* CMS integration
* Admin dashboards
* Scheduled ingestion
* Website/document crawlers
* Webhooks
* Automatic document versioning

---

# 4. AI Security

The system uses layered security rather than relying solely on the LLM system prompt.

Security boundaries include:

### Direct Prompt Injection

Attempts to override system behavior are detected and handled safely.

### Indirect Prompt Injection

Retrieved documents are treated as **untrusted data**, not executable instructions.

### Jailbreak Protection

The system can identify attempts to bypass support and safety policies.

### System Prompt Protection

Internal system instructions are not exposed to users.

### Sensitive Information Protection

The system is designed to prevent exposure of:

* API keys
* Credentials
* Secrets
* Private customer information
* Internal security information

### Authorization Boundaries

The LLM does not determine whether a user is authorized to perform sensitive actions.

Authorization belongs to the backend/application layer.

---

# 5. AI Guardrails

The application uses a dedicated guardrail layer to separate security decisions from ordinary LLM generation.

Guardrails can operate around:

```text
INPUT
  ↓
RETRIEVAL
  ↓
LLM GENERATION
  ↓
OUTPUT
```

This makes it possible to distinguish between:

* legitimate customer questions
* prompt injection
* malicious retrieved content
* sensitive requests
* unsafe output

Security events are observable through application logs and Langfuse.

---

# 6. Customer Support Behavior

### Normal question

```text
User:
What is Frag Naija?
```

The system retrieves relevant official knowledge and generates a customer-facing answer.

### Knowledge-based question

```text
User:
What esports games do you support?
```

The system retrieves relevant game information from the knowledge base.

### Unsupported question

If the knowledge base does not contain sufficient information, the assistant should not fabricate an answer.

Instead:

```text
I don't have that information in my current knowledge base.
Please contact our human support team for assistance.
```

---

# 7. Sensitive Requests

The system does not pretend to perform actions it cannot perform.

Examples include:

* Account-specific wager information
* Refund requests
* Withdrawals
* Private account information
* Transaction disputes

These should be routed to authorized backend systems or human support.

The LLM is never treated as an authorization authority.

---

# Technology Stack

| Component         | Technology                     |
| ----------------- | ------------------------------ |
| API               | FastAPI                        |
| LLM               | Groq API                       |
| RAG               | Retrieval-Augmented Generation |
| Vector Database   | Qdrant                         |
| Embeddings        | Sentence Transformers          |
| Validation        | Pydantic                       |
| Guardrails        | NVIDIA NeMo Guardrails         |
| Observability     | Langfuse                       |
| Containerization  | Docker                         |
| Language          | Python                         |
| API Documentation | OpenAPI / Swagger              |
| Deployment        | Hugging Face Spaces            |
| Version Control   | Git / GitHub                   |

---

# API

## Health Check

```http
GET /health
```

Used to verify that the service is running.

---

## Customer Chat

```http
POST /chat/
```

### Request

```json
{
  "message": "What is Frag Naija?",
  "session_id": "customer-session",
  "user_id": "customer-id"
}
```

### Response

```json
{
  "response": "Frag Naija is ...",
  "provider": "groq",
  "session_id": "customer-session",
  "sources": [],
  "intent": "general_inquiry",
  "confidence": 0.98,
  "requires_human": false,
  "ticket_id": null
}
```

---

# Running Locally

## 1. Clone the repository

```bash
git clone https://github.com/Wilsonafolabi/frag-naija-support.git
cd frag-naija-support
```

## 2. Create a virtual environment

```bash
python -m venv .venv
```

### Windows

```powershell
.venv\Scripts\Activate.ps1
```

### Linux/macOS

```bash
source .venv/bin/activate
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Configure environment variables

Create:

```text
.env
```

Example:

```env
GROQ_API_KEY=your_groq_api_key

LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=your_langfuse_host

QDRANT_URL=your_qdrant_url
QDRANT_API_KEY=your_qdrant_api_key
```

Never commit `.env` to Git.

---

# Run the API

```bash
uvicorn app.main:app --reload
```

The API will be available at:

```text
http://localhost:8000
```

Swagger documentation:

```text
http://localhost:8000/docs
```

OpenAPI specification:

```text
http://localhost:8000/openapi.json
```

---

# Docker

The project can also run inside Docker.

Build:

```bash
docker build -t frag-naija-support .
```

Run:

```bash
docker run --env-file .env -p 8000:8000 frag-naija-support
```

The application can therefore be packaged consistently across development and deployment environments.

---

# Example API Request

### PowerShell

```powershell
$body = @{
    message = "What is Frag Naija?"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://localhost:8000/chat/ `
    -ContentType "application/json" `
    -Body $body
```

---

# Observability

Langfuse is used to monitor the AI pipeline.

The system can trace:

```text
Request
   ↓
Security Guard
   ↓
Intent Classification
   ↓
RAG Retrieval
   ↓
LLM Generation
   ↓
Output Validation
   ↓
Final Response
```

Useful observability metrics include:

* Latency
* Input tokens
* Output tokens
* Total tokens
* Model usage
* Cost
* Retrieval results
* Security events
* LLM generations
* Request traces
* Session traces

This allows the support engine to be evaluated and improved over time.

---

# Security Design

The security model follows a defense-in-depth approach.

```text
                    USER
                      │
                      ▼
              Pydantic Validation
                      │
                      ▼
               Rate Limiting
                      │
                      ▼
              Input Guardrails
                      │
                      ▼
                RAG Retrieval
                      │
                      ▼
             Retrieval Guardrails
                      │
                      ▼
                    Groq
                      │
                      ▼
             Output Guardrails
                      │
                      ▼
              Response Validation
                      │
                      ▼
                   USER
```

The system does not depend on a single security mechanism.

---

# Design Principles

### Grounded Responses

The assistant should prefer official Frag Naija knowledge over unsupported model knowledge.

### No Fabrication

If information is unavailable, the system should say so.

### Data ≠ Instructions

Retrieved documents are treated as data and cannot override application instructions.

### LLM ≠ Authorization

The LLM cannot grant permissions or authorize sensitive operations.

### Security ≠ Prompt

Security controls are implemented at the application and guardrail layers rather than relying exclusively on a system prompt.

### Knowledge Without Retraining

Changing Frag Naija information should require updating the knowledge base rather than retraining the LLM.

---

# Future Improvements

Potential future development includes:

* Automatic website knowledge synchronization
* Admin knowledge-base dashboard
* Automatic document ingestion
* Knowledge versioning
* Human-support ticket integration
* Customer conversation analytics
* Feedback-driven retrieval improvements
* Automated evaluation datasets
* Multi-language customer support
* Voice support
* Streaming responses
* Advanced fraud/abuse detection
* Account-aware support through authorized backend APIs
* Automated guardrail evaluation
* Continuous RAG evaluation

---

# Production Deployment

The API is deployed as a containerized FastAPI service.

Production deployment should provide:

```text
Customer Website
       ↓
Chat UI
       ↓
Production API
       ↓
Security / Guardrails
       ↓
RAG
       ↓
Qdrant
       ↓
Groq
```

The frontend only needs to communicate with the `/chat/` API endpoint.

The customer does not need to know whether the backend uses:

* Groq
* Qdrant
* embeddings
* guardrails
* Langfuse
* FastAPI

Those remain implementation details of the AI support engine.

---

# Project Status

**Status: Successfully implemented and deployed.**

Core functionality includes:

* [x] FastAPI customer-support API
* [x] RAG pipeline
* [x] Official Frag Naija knowledge base
* [x] Vector retrieval
* [x] Groq LLM integration
* [x] Pydantic validation
* [x] Security layer
* [x] Prompt-injection protection
* [x] Retrieved-context isolation
* [x] Output validation
* [x] Rate limiting
* [x] Security event logging
* [x] Langfuse observability
* [x] Docker support
* [x] OpenAPI documentation
* [x] Production deployment

---

# Repository

GitHub:

https://github.com/Wilsonafolabi/frag-naija-support

---

## Built For Frag Naija

This project provides the AI backend required to power a customer-facing support experience while maintaining a separation between:

**Customer Support → Knowledge → Retrieval → LLM → Security → Observability**

The architecture is designed so the knowledge layer can evolve continuously without requiring the underlying language model to be retrained.
