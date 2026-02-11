# CaRMS Data Platform

A miniature data platform for exploring Canadian medical residency programs, built using the CaRMS tech stack: **PostgreSQL**, **SQLAlchemy/SQLModel**, **Dagster**, and **FastAPI**.

Ingests public-facing CaRMS data from the [2025 R-1 Main Residency Match](https://github.com/dnokes/Junior-Data-Scientist), transforms it through a Dagster ETL pipeline, stores it in PostgreSQL (with pgvector for semantic search), and serves it via a FastAPI REST API.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                           │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐  │
│  │   Dagster     │    │   PostgreSQL     │    │   FastAPI     │  │
│  │              │───▶│   + pgvector     │◀───│              │  │
│  │  ETL Pipeline │    │                  │    │  REST API     │  │
│  │  Port 3000    │    │  Port 5433       │    │  Port 8000    │  │
│  └──────────────┘    └──────────────────┘    └──────────────┘  │
│       WRITES              STORES                  READS         │
└─────────────────────────────────────────────────────────────────┘
```

**Dagster** (write path) — Ingests raw data, transforms it, generates embeddings, loads into PostgreSQL.

**PostgreSQL + pgvector** (storage) — Single source of truth for all structured data and vector embeddings.

**FastAPI** (read path) — Serves pre-computed results via REST endpoints including semantic search.

---

## Quick Start

### Prerequisites
- Docker Desktop
- Git

### 1. Clone and download data

```bash
git clone <your-repo-url>
cd carms-data-platform
```

Download these 4 files from [dnokes/Junior-Data-Scientist](https://github.com/dnokes/Junior-Data-Scientist) into the `data/` directory:

```
data/
├── 1503_discipline.xlsx
├── 1503_program_master.xlsx
├── 1503_program_descriptions_x_section.csv
└── 1503_markdown_program_descriptions_v2.json
```

### 2. Start the platform

```bash
docker compose up -d --build
```

This starts 3 services:
- **PostgreSQL** on `localhost:5433`
- **Dagster UI** on `localhost:3000`
- **FastAPI** on `localhost:8000`

### 3. Run the pipeline

1. Open [http://localhost:3000](http://localhost:3000) (Dagster UI)
2. Click **"Materialize All"**
3. Wait for all 14 assets to complete (~3-5 minutes, most time is embedding generation)

### 4. Explore the API

Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive Swagger documentation.

Example queries:

```bash
# List all programs (paginated)
curl "http://localhost:8000/programs"

# Filter: IMG programs in Toronto
curl "http://localhost:8000/programs?stream_category=IMG&site=Toronto"

# Text search
curl "http://localhost:8000/programs/search?q=pediatrics"

# Semantic search (find by meaning, not just keywords)
curl "http://localhost:8000/semantic-search?q=research+opportunities+in+pediatrics"

# Q&A — ask a natural language question (requires Ollama, see below)
curl "http://localhost:8000/qa?q=Which+programs+offer+rural+medicine+training"

# Match statistics
curl "http://localhost:8000/statistics"
```

### Optional: Q&A with RAG (Retrieval-Augmented Generation)

The `/qa` endpoint uses a local LLM to answer natural language questions about programs. It requires [Ollama](https://ollama.ai):

```bash
# Install Ollama from https://ollama.ai, then:
ollama pull mistral
# Ollama auto-serves on port 11434. Then:
curl "http://localhost:8000/qa?q=What+are+the+research+opportunities+in+pediatrics"
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check and endpoint directory |
| GET | `/programs` | List programs with filtering and pagination |
| GET | `/programs/search?q=` | Text search across names and descriptions |
| GET | `/programs/{id}` | Single program with full description sections |
| GET | `/semantic-search?q=` | Semantic search using vector similarity (LangChain + pgvector) |
| GET | `/qa?q=` | Q&A with RAG — natural language answers from program data (LangChain + Ollama) |
| GET | `/disciplines` | All 37 disciplines with program counts |
| GET | `/institutions` | All 18 institutions with program counts |
| GET | `/statistics` | Aggregate match statistics |

### Program Filters

The `/programs` endpoint supports:
- `discipline_id` — Filter by discipline (e.g., 27 for Family Medicine)
- `institution_id` — Filter by institution
- `stream_category` — `CMG`, `IMG`, or `All`
- `site` — City/location (partial match)
- `language` — `en` or `fr`
- `page`, `page_size` — Pagination (default: page 1, 20 per page)

### Semantic Search

The `/semantic-search` endpoint goes beyond keyword matching. It encodes your query into a vector and finds programs with the most similar descriptions by meaning.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `q` | required | Natural language query |
| `top_k` | 10 | Number of results (1-50) |
| `stream_category` | null | Optional filter |

**Example:** Searching `"working with children in hospitals"` returns pediatrics programs even though those exact words don't appear in the descriptions.

---

## Dagster Pipeline

14 assets across 4 layers:

```
Layer 1 — Ingestion (4 assets)
  raw_disciplines    ← 1503_discipline.xlsx
  raw_programs       ← 1503_program_master.xlsx
  raw_sections       ← 1503_program_descriptions_x_section.csv
  raw_markdown       ← 1503_markdown_program_descriptions_v2.json

Layer 2 — Transform (4 assets)
  stg_disciplines    ← Clean and validate
  stg_institutions   ← Deduplicate 398 school_ids → 18 universities
  stg_programs       ← Enrich with quota, accreditation, stream_category
  stg_sections       ← Pivot 15 wide columns → long format

Layer 3 — Load (4 assets)
  db_disciplines     → disciplines table (37 rows)
  db_institutions    → institutions table (18 rows)
  db_programs        → programs table (815 rows)
  db_descriptions    → program_descriptions table (10,716 rows)

Layer 4 — Embeddings (2 assets)
  chunked_documents  ← Split markdown into 1000-char overlapping chunks
  db_embeddings      → program_embeddings table (35,270 vectors)
```

### Key Transformations

- **Institution deduplication:** 398 `school_id` values → 18 unique universities (min ID per school)
- **Language detection:** French universities identified by name (Laval, Sherbrooke, Montréal)
- **Stream categorization:** 14 stream types → 3 categories (CMG / IMG / All)
- **Quota extraction:** Regex parsing of approximate quota from markdown text
- **Section pivoting:** Wide format (815 × 15 columns) → long format (~10,716 rows)
- **Text chunking:** 815 documents → 35,270 overlapping chunks (1000 chars, 200 overlap)
- **Embedding generation:** all-MiniLM-L6-v2 model, 384 dimensions, IVFFlat index

---

## Database Schema

```
disciplines (37 rows)
├── id (PK) — from CaRMS discipline_id
└── name

institutions (18 rows)
├── id (PK) — min school_id per university
├── name (unique)
└── language — "en" or "fr"

programs (815 rows)
├── id (PK) — from program_stream_id
├── discipline_id (FK → disciplines)
├── institution_id (FK → institutions)
├── name, site, stream, stream_category
├── quota — extracted from markdown
├── accreditation — extracted from markdown
└── source_url

program_descriptions (10,716 rows)
├── id (PK, auto)
├── program_id (FK → programs)
├── section_name — "selection_criteria", "program_curriculum", etc.
└── content (TEXT)

program_embeddings (35,270 rows)
├── id (PK, auto)
├── program_id (FK → programs)
├── chunk_index
├── chunk_text (TEXT)
└── embedding — vector(384), IVFFlat indexed
```

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Database | PostgreSQL 16 + pgvector | Structured data + vector embeddings |
| ORM | SQLModel / SQLAlchemy | Type-safe database models |
| Pipeline | Dagster | ETL orchestration (asset-based) |
| API | FastAPI | REST endpoints with auto-generated docs |
| Semantic Search | LangChain + pgvector | Vector similarity retrieval |
| Q&A (RAG) | LangChain + Ollama (Mistral 7B) | Retrieval-Augmented Generation |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | 384-dim vectors, runs locally |
| Text Splitting | LangChain RecursiveCharacterTextSplitter | Chunking with overlap |
| Containerization | Docker Compose | 3-service orchestration |

---

## Local Development

For development without Docker (faster iteration):

```bash
# 1. Start only PostgreSQL in Docker
docker compose up db -d

# 2. Set up Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r dagster_pipeline/requirements.txt
pip install -r api/requirements.txt

# 3. Create .env with local connection
# DATABASE_URL=postgresql://carms_user:carms_pass@127.0.0.1:5433/carms

# 4. Create tables
python -m dagster_pipeline.models.database

# 5. Run Dagster (separate terminal)
dagster dev -m dagster_pipeline

# 6. Run FastAPI (separate terminal)
uvicorn api.main:app --reload --port 8000
```

---

## Project Structure

```
carms-data-platform/
├── docker-compose.yml           # Orchestrates all 3 services
├── init.sql                     # Enables pgvector extension
├── .env                         # Local development settings
│
├── dagster_pipeline/
│   ├── Dockerfile
│   ├── __init__.py              # Dagster Definitions (registers all assets)
│   ├── requirements.txt
│   ├── models/
│   │   ├── __init__.py
│   │   └── database.py          # SQLModel table definitions
│   └── assets/
│       ├── __init__.py
│       ├── ingestion.py         # Layer 1: Raw file ingestion
│       ├── transform.py         # Layer 2: Transform & enrich
│       ├── load.py              # Layer 3: Load to PostgreSQL
│       └── embeddings.py        # Layer 4: Chunking & embeddings
│
├── api/
│   ├── Dockerfile
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── database.py              # Session dependency
│   ├── schemas.py               # Pydantic response models
│   ├── requirements.txt
│   └── routes/
│       ├── __init__.py
│       ├── programs.py          # /programs endpoints
│       ├── disciplines.py       # /disciplines endpoint
│       ├── institutions.py      # /institutions endpoint
│       ├── statistics.py        # /statistics endpoint
│       └── semantic_search.py   # /semantic-search endpoint
│
└── data/                        # Source files (download from GitHub)
    ├── 1503_discipline.xlsx
    ├── 1503_program_master.xlsx
    ├── 1503_program_descriptions_x_section.csv
    └── 1503_markdown_program_descriptions_v2.json
```

---

## Data Source

All data is from the [dnokes/Junior-Data-Scientist](https://github.com/dnokes/Junior-Data-Scientist) repository, containing public-facing CaRMS data from the **2025 R-1 Main Residency Match** (match iteration ID: 1503).

- **815** residency programs across **37** disciplines at **18** Canadian universities
- **3,936** total approximate residency seats
- **14** applicant stream categories (CMG, IMG, All, etc.)
