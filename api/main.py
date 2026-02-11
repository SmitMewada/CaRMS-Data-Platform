"""
CaRMS Data Platform API.

A thin serving layer that reads pre-computed data from PostgreSQL
(populated by the Dagster pipeline) and serves it via REST endpoints.

Run with: uvicorn api.main:app --reload --port 8000

Architecture:
    Dagster (writes) → PostgreSQL ← FastAPI (reads)
    FastAPI never does heavy computation — it just queries and serves.

Endpoints:
    GET /                       → API info + health check
    GET /programs               → List programs (filtered, paginated)
    GET /programs/search?q=     → Text search across programs
    GET /programs/{id}          → Single program with descriptions
    GET /disciplines            → List disciplines with program counts
    GET /institutions           → List institutions with program counts
    GET /statistics             → Aggregate match statistics
"""

from fastapi import FastAPI

from api.routes import programs, disciplines, institutions, statistics, semantic_search

app = FastAPI(
    title="CaRMS Data Platform API",
    description=(
        "REST API for exploring Canadian medical residency programs. "
        "Data is sourced from the 2025 R-1 Main Residency Match (iteration 1503) "
        "and loaded via a Dagster ETL pipeline into PostgreSQL."
    ),
    version="1.0.0",
)

# Register routers
app.include_router(programs.router)
app.include_router(disciplines.router)
app.include_router(institutions.router)
app.include_router(statistics.router)
app.include_router(semantic_search.router)



@app.get("/", tags=["Health"])
def root():
    """API health check and info."""
    return {
        "service": "CaRMS Data Platform API",
        "version": "1.0.0",
        "data_source": "2025 R-1 Main Residency Match (iteration 1503)",
        "endpoints": {
            "programs": "/programs",
            "search": "/programs/search?q=<query>",
            "semantic_search": "/semantic-search?q=<query>",
            "program_detail": "/programs/{program_id}",
            "disciplines": "/disciplines",
            "institutions": "/institutions",
            "statistics": "/statistics",
            "docs": "/docs",
        },
    }