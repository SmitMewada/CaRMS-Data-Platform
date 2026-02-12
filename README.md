# CaRMS Data Platform

An end-to-end data platform for exploring Canadian medical residency programs, built with the CaRMS tech stack: **PostgreSQL + pgvector**, **SQLAlchemy/SQLModel**, **Dagster**, **FastAPI**, and **LangChain**.

Ingests public-facing CaRMS data from the [2025 R-1 Main Residency Match](https://github.com/dnokes/Junior-Data-Scientist), transforms it through a 14-asset Dagster ETL pipeline, loads it into a normalized PostgreSQL database with vector embeddings, and serves it via a FastAPI REST API with semantic search and retrieval-augmented generation (RAG) Q&A.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Docker Compose                              │
│                                                                      │
│  ┌───────────────┐    ┌───────────────────┐    ┌───────────────┐    │
│  │    Dagster     │    │    PostgreSQL      │    │    FastAPI     │    │
│  │               │───▶│    + pgvector      │◀───│               │    │
│  │  ETL Pipeline  │    │                   │    │   REST API     │    │
│  │  Port 3000     │    │   Port 5433       │    │   Port 8000    │    │
│  └───────────────┘    └───────────────────┘    └───────────────┘    │
│       WRITES               STORES                   READS            │
└──────────────────────────────────────────────────────────────────────┘
```

**Dagster** (write path) — Batch ETL orchestration. Ingests raw data from 4 source files, transforms and enriches it, generates vector embeddings via LangChain, and loads everything into PostgreSQL. Asset-based pipeline with 14 assets across 4 layers.

**PostgreSQL + pgvector** (single source of truth) — Stores all structured data (programs, disciplines, institutions, descriptions) and vector embeddings in a single database. pgvector enables cosine similarity search on 384-dimensional embeddings alongside standard relational queries.

**FastAPI** (read path) — Thin serving layer. Reads pre-computed results from PostgreSQL and serves them via 9 REST endpoints, including filtered program listings, semantic search, and RAG-powered Q&A. Never does heavy computation.

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (6GB+ memory recommended)
- Git

### 1. Clone and download data

```bash
git clone https://github.com/YOUR_USERNAME/carms-data-platform.git
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

| Service | URL | Purpose |
|---------|-----|---------|
| PostgreSQL | `localhost:5433` | Database with pgvector |
| Dagster UI | [localhost:3000](http://localhost:3000) | Pipeline orchestration |
| FastAPI | [localhost:8000](http://localhost:8000) | REST API |

The Dagster container automatically creates all database tables on startup.

### 3. Run the ETL pipeline

1. Open [http://localhost:3000](http://localhost:3000) (Dagster UI)
2. Navigate to **Assets** → Click **"Materialize All"**
3. Wait for all 14 assets to complete (~5–10 minutes; embedding generation takes the most time)

### 4. Explore the API

Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive Swagger documentation.

```bash
# List all programs (paginated)
curl "http://localhost:8000/programs"

# Filter by stream category and location
curl "http://localhost:8000/programs?stream_category=IMG&site=Toronto"

# Keyword search
curl "http://localhost:8000/programs/search?q=pediatrics"

# Semantic search — find programs by meaning, not just keywords
curl "http://localhost:8000/semantic-search?q=research+opportunities+in+pediatrics"

# Discipline and institution summaries
curl "http://localhost:8000/disciplines"
curl "http://localhost:8000/institutions"

# Aggregate match statistics
curl "http://localhost:8000/statistics"
```

### 5. Optional: Q&A with RAG (Retrieval-Augmented Generation)

The `/qa` endpoint answers natural language questions using retrieved program descriptions as context. It requires [Ollama](https://ollama.ai) running locally with Mistral:

```bash
# Install Ollama from https://ollama.ai, then:
ollama pull mistral

# Ask a question (Ollama auto-serves on port 11434)
curl "http://localhost:8000/qa?q=What+are+the+research+opportunities+in+pediatrics"
```

The RAG pipeline:
1. Encodes the question using LangChain `HuggingFaceEmbeddings` (same model as the pipeline)
2. Retrieves the top-k most relevant program description chunks via pgvector cosine similarity
3. Constructs a prompt with retrieved context using LangChain `PromptTemplate`
4. Sends to Ollama/Mistral (local LLM — no external API keys, suitable for sensitive medical data)
5. Returns a synthesized answer with source citations

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check and endpoint directory |
| GET | `/programs` | List programs with filtering and pagination |
| GET | `/programs/search?q=` | Keyword search across program names and descriptions |
| GET | `/programs/{id}` | Single program with all description sections |
| GET | `/semantic-search?q=` | Semantic search using LangChain embeddings + pgvector |
| GET | `/qa?q=` | RAG Q&A — natural language answers with source citations |
| GET | `/disciplines` | All 37 disciplines with program counts |
| GET | `/institutions` | All 18 institutions with program counts |
| GET | `/statistics` | Aggregate match statistics (programs, seats, distributions) |

### Program Filters

The `/programs` endpoint supports combining multiple filters:

| Parameter | Example | Description |
|-----------|---------|-------------|
| `discipline_id` | `27` | Filter by discipline (e.g., 27 = Family Medicine) |
| `institution_id` | `4` | Filter by institution |
| `stream_category` | `CMG`, `IMG`, `All` | Applicant stream category |
| `site` | `Toronto` | City/location (partial match) |
| `language` | `en`, `fr` | Program language |
| `page` | `1` | Page number (default: 1) |
| `page_size` | `20` | Results per page (default: 20) |

### Semantic Search

The `/semantic-search` endpoint goes beyond keyword matching — it encodes the query into a 384-dimensional vector and finds programs with the most semantically similar descriptions using pgvector cosine similarity.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `q` | required | Natural language query |
| `top_k` | 10 | Number of results (1–50) |
| `stream_category` | null | Optional structured filter (CMG/IMG/All) |

**Example:** Searching `"working with children in hospitals"` returns Pediatrics programs even though those exact words don't appear in the descriptions.

---

## Dagster Pipeline

14 assets organized across 4 layers, following the asset-based paradigm (Dagster's modern approach):

```
Layer 1 — Raw Ingestion (4 assets)
  raw_disciplines     ← 1503_discipline.xlsx (37 disciplines)
  raw_programs        ← 1503_program_master.xlsx (815 programs)
  raw_sections        ← 1503_program_descriptions_x_section.csv (815 × 15 sections)
  raw_markdown        ← 1503_markdown_program_descriptions_v2.json (815 full descriptions)

Layer 2 — Transform & Enrich (4 assets)
  stg_disciplines     ← Clean and validate discipline names
  stg_institutions    ← Deduplicate 398 school_ids → 18 unique universities, detect language
  stg_programs        ← Enrich with quota (regex), accreditation, stream_category
  stg_sections        ← Pivot 15 wide columns → long format (section_name, content)

Layer 3 — Load to PostgreSQL (4 assets)
  db_disciplines      → disciplines table (37 rows)
  db_institutions     → institutions table (18 rows)
  db_programs         → programs table (815 rows)
  db_descriptions     → program_descriptions table (10,716 rows)

Layer 4 — Embeddings (2 assets)
  chunked_documents   ← LangChain RecursiveCharacterTextSplitter (1000 chars, 200 overlap)
  db_embeddings       → program_embeddings table (35,270 vectors, IVFFlat indexed)
```

### Key Transformations

- **Institution deduplication:** 398 `school_id` values in the source data mapped to 18 unique universities using minimum ID per school name.
- **Language detection:** French-language institutions identified by name pattern (Université Laval, Université de Sherbrooke, Université de Montréal) → `language` field on institutions table.
- **Stream categorization:** 14 raw stream type values → 3 clean categories (`CMG` / `IMG` / `All`) based on string pattern matching.
- **Quota extraction:** Approximate quota parsed from markdown text using regex, stored as a structured integer field on the programs table.
- **Accreditation extraction:** Accreditation status parsed from markdown and stored as a structured field.
- **Section pivoting:** Wide CSV format (815 rows × 15 nullable text columns) → long format (10,716 rows of `program_id`, `section_name`, `content`). More flexible, extensible, and queryable.
- **Text chunking:** 815 full markdown documents → 35,270 overlapping chunks using LangChain `RecursiveCharacterTextSplitter` (1000-character chunks with 200-character overlap).
- **Embedding generation:** `sentence-transformers/all-MiniLM-L6-v2` model (384 dimensions, runs on CPU). Embeddings indexed with IVFFlat for fast approximate nearest neighbor search.

### Idempotent Loads

All Layer 3 assets use a truncate-then-insert strategy with FK-safe deletion order (`embeddings → descriptions → programs → institutions → disciplines`). The pipeline can be re-materialized at any time without manual cleanup.

---

## Database Schema

5 normalized SQLModel tables with enforced foreign key relationships:

```
disciplines (37 rows)
├── id (PK)           — CaRMS discipline_id (not auto-increment)
├── name              — e.g., "Family Medicine", "Neurosurgery"
└── created_at

institutions (18 rows)
├── id (PK)           — Deduplicated school_id (min per university)
├── name (unique)     — e.g., "University of Toronto"
├── language          — "en" or "fr"
└── created_at

programs (815 rows)
├── id (PK)           — program_stream_id (universal join key across all source files)
├── discipline_id     → FK disciplines.id
├── institution_id    → FK institutions.id
├── name              — Full program name
├── site              — City/location
├── stream            — Raw stream type (14 values)
├── stream_category   — Derived: "CMG" / "IMG" / "All"
├── quota             — Extracted from markdown (nullable)
├── accreditation     — Extracted from markdown (nullable)
├── source_url        — Original CaRMS program page
└── created_at

program_descriptions (10,716 rows)
├── id (PK, auto)
├── program_id        → FK programs.id
├── section_name      — "selection_criteria", "program_curriculum", etc.
├── content (TEXT)     — Full section text
└── created_at

program_embeddings (35,270 rows)
├── id (PK, auto)
├── program_id        → FK programs.id
├── chunk_index       — Position within the parent document
├── chunk_text (TEXT)  — Source text chunk
├── embedding         — vector(384), IVFFlat indexed
└── created_at
```

### Design Decisions

- **Real IDs from source data** for `disciplines`, `institutions`, and `programs` (not auto-increment) — preserves referential integrity with CaRMS source data and enables direct lookups.
- **Normalized `institutions` table** extracted from denormalized `school_name` column — 18 unique universities were repeated across 815 program rows.
- **Long-format descriptions** (pivoted from wide CSV) — 15 nullable text columns become clean `(program_id, section_name, content)` rows. More flexible for querying, filtering, and extending.
- **pgvector inside PostgreSQL** — vector embeddings stored alongside relational data in the same database, not in a separate vector store. Enables JOINs between embedding similarity results and structured program metadata.
- **Separate embeddings table** — isolates vector operations from relational queries. Can be rebuilt independently without affecting other tables.

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Database | PostgreSQL 16 + pgvector | Relational data + vector embeddings in one database |
| ORM | SQLModel / SQLAlchemy | Type-safe Python database models with Pydantic validation |
| ETL Pipeline | Dagster (asset-based) | Batch orchestration — ingestion, transformation, loading, embedding |
| API | FastAPI | REST endpoints with auto-generated OpenAPI/Swagger docs |
| Semantic Search | LangChain `HuggingFaceEmbeddings` + pgvector | Encode queries → cosine similarity retrieval |
| Q&A (RAG) | LangChain `PromptTemplate` + Ollama (Mistral 7B) | Retrieval-Augmented Generation with local LLM |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) | 384-dimensional vectors, runs locally on CPU |
| Text Splitting | LangChain `RecursiveCharacterTextSplitter` | Document chunking with configurable overlap |
| Containerization | Docker Compose | 3-service orchestration (DB, pipeline, API) |
| Language | Python 3.12 | All application code |

---

## Local Development

For faster iteration without full Docker builds:

```bash
# 1. Start only PostgreSQL in Docker
docker compose up db -d

# 2. Set up Python virtual environment
python -m venv .venv
source .venv/bin/activate
pip install -r dagster_pipeline/requirements.txt
pip install -r api/requirements.txt

# 3. Create .env file
echo "DATABASE_URL=postgresql://carms_user:carms_pass@127.0.0.1:5433/carms" > .env

# 4. Create database tables
python -m dagster_pipeline.models.database

# 5. Run Dagster pipeline (terminal 1)
dagster dev -m dagster_pipeline

# 6. Run FastAPI server (terminal 2)
uvicorn api.main:app --reload --port 8000

# 7. Optional: Start Ollama for Q&A (terminal 3)
ollama pull mistral
# Ollama auto-serves on port 11434
```

---

## Project Structure

```
carms-data-platform/
├── docker-compose.yml              # Orchestrates 3 services (db, dagster, api)
├── init.sql                        # Enables pgvector extension on database creation
├── .env                            # Local dev: DATABASE_URL
├── .gitignore
│
├── dagster_pipeline/
│   ├── Dockerfile                  # Python 3.12 + pre-downloaded ML model
│   ├── __init__.py                 # Dagster Definitions — registers all 14 assets
│   ├── requirements.txt
│   ├── models/
│   │   ├── __init__.py
│   │   └── database.py             # 5 SQLModel table definitions + pgvector column
│   └── assets/
│       ├── __init__.py
│       ├── ingestion.py            # Layer 1: Raw file readers (xlsx, csv, json)
│       ├── transform.py            # Layer 2: Clean, deduplicate, enrich, pivot
│       ├── load.py                 # Layer 3: FK-safe truncate + bulk insert to PostgreSQL
│       └── embeddings.py           # Layer 4: LangChain text splitting + embedding generation
│
├── api/
│   ├── Dockerfile                  # Python 3.12 + pre-downloaded ML model
│   ├── __init__.py
│   ├── main.py                     # FastAPI app — registers all routers
│   ├── database.py                 # SQLModel session dependency injection
│   ├── schemas.py                  # Pydantic response models
│   ├── requirements.txt
│   └── routes/
│       ├── __init__.py
│       ├── programs.py             # /programs — list, filter, search, detail
│       ├── disciplines.py          # /disciplines — with program counts
│       ├── institutions.py         # /institutions — with program counts
│       ├── statistics.py           # /statistics — aggregate match stats
│       └── semantic_search.py      # /semantic-search + /qa — LangChain + Ollama RAG
│
└── data/                           # Source files (not committed — download from GitHub)
    ├── 1503_discipline.xlsx
    ├── 1503_program_master.xlsx
    ├── 1503_program_descriptions_x_section.csv
    └── 1503_markdown_program_descriptions_v2.json
```

---

## Data Source

All data is from the [dnokes/Junior-Data-Scientist](https://github.com/dnokes/Junior-Data-Scientist) repository — public-facing CaRMS data scraped from the CaRMS website for the **2025 R-1 Main Residency Match** (match iteration ID: 1503).

| Metric | Count |
|--------|-------|
| Residency programs | 815 |
| Medical disciplines | 37 |
| Canadian universities | 18 |
| Total approximate seats | 3,936 |
| Applicant stream categories | 14 |
| Program description sections | 10,716 |
| Vector embedding chunks | 35,270 |

All source files maintain perfect referential integrity: `discipline.discipline_id` → `program_master.discipline_id` → `csv.program_description_id` → `json.id.split("|")[1]`. Zero orphaned records across all four files.