"""
Dagster definitions for the CaRMS Data Platform.

This is the entry point Dagster uses to discover all assets.
Run with: dagster dev -m dagster_pipeline
"""

from dagster import Definitions
from dagster_pipeline.assets.ingestion import (
    raw_disciplines,
    raw_programs,
    raw_sections,
    raw_markdown,
)
from dagster_pipeline.assets.transform import (
    stg_disciplines,
    stg_institutions,
    stg_programs,
    stg_sections,
)
from dagster_pipeline.assets.load import (
    db_disciplines,
    db_institutions,
    db_programs,
    db_descriptions,
)
from dagster_pipeline.assets.embeddings import (
    chunked_documents,
    db_embeddings,
)

all_assets = [
    # Raw Ingestion
    raw_disciplines,
    raw_programs,
    raw_sections,
    raw_markdown,
    # Transform & Enrich
    stg_disciplines,
    stg_institutions,
    stg_programs,
    stg_sections,
    # Load to PostgreSQL
    db_disciplines,
    db_institutions,
    db_programs,
    db_descriptions,
    # Embeddings
    chunked_documents,
    db_embeddings,
]

defs = Definitions(assets=all_assets)
