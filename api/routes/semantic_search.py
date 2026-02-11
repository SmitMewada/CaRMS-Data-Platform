"""
Semantic Search & Q&A API Router (LangChain + Ollama).

Endpoints:
    GET /semantic-search?q=  — Find programs by meaning using LangChain embeddings + pgvector
    GET /qa?q=               — Ask natural language questions, get RAG answers (Ollama/Mistral)
"""

import os
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlmodel import Session
from sqlalchemy import text as sql_text

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate

from api.database import get_session

load_dotenv()

router = APIRouter(tags=["Semantic Search & Q&A"])

# ========================
# Lazy-loaded singletons
# ========================
_embeddings = None
_llm = None


def get_embeddings() -> HuggingFaceEmbeddings:
    """Lazy-load the HuggingFace embedding model (same model used in Dagster pipeline)."""
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
        )
    return _embeddings


def get_llm() -> OllamaLLM:
    """Lazy-load the Ollama LLM (Mistral 7B running locally)."""
    global _llm
    if _llm is None:
        _llm = OllamaLLM(
            model="mistral",
            base_url="http://localhost:11434",
            temperature=0.1,
        )
    return _llm


# ========================
# Response Schemas
# ========================
class SemanticSearchResult(BaseModel):
    program_id: Optional[int] = None
    chunk_text: str
    similarity_score: Optional[float] = None
    metadata: dict = {}

    model_config = {"from_attributes": True}


class SemanticSearchResponse(BaseModel):
    query: str
    results: List[SemanticSearchResult]
    total: int


class QAResponse(BaseModel):
    query: str
    answer: str
    source_chunks: List[str]
    num_sources: int


# ========================
# RAG Prompt
# ========================
RAG_PROMPT_TEMPLATE = """You are a helpful assistant for the Canadian Resident Matching Service (CaRMS).
Use the following context from residency program descriptions to answer the question.
If you don't know the answer based on the context, say so — do not make up information.
Be specific and reference program names, universities, and locations when relevant.

Context:
{context}

Question: {question}

Answer:"""

RAG_PROMPT = PromptTemplate(
    template=RAG_PROMPT_TEMPLATE,
    input_variables=["context", "question"],
)


# ========================
# Semantic Search Endpoint (LangChain Embeddings + pgvector)
# ========================
@router.get("/semantic-search", response_model=SemanticSearchResponse)
def semantic_search(
    q: str = Query(..., min_length=2, description="Natural language search query"),
    top_k: int = Query(10, ge=1, le=50, description="Number of results to return"),
    stream_category: Optional[str] = Query(
        None, description="Filter by stream category: CMG, IMG, or All"
    ),
    session: Session = Depends(get_session),
):
    """
    Semantic search across program descriptions using LangChain embeddings + pgvector.

    Finds programs by MEANING, not just keywords.
    Example: "working with children in hospitals" → finds Pediatrics programs.
    """
    # Use LangChain's HuggingFaceEmbeddings to encode the query
    embeddings = get_embeddings()
    query_vector = embeddings.embed_query(q)

    # Query pgvector using cosine similarity
    sql = """
        SELECT
            pe.program_id,
            pe.chunk_text,
            1 - (pe.embedding <=> cast(:query_embedding as vector)) as similarity_score,
            p.name as program_name,
            p.site,
            d.name as discipline_name,
            i.name as institution_name,
            p.stream_category
        FROM program_embeddings pe
        JOIN programs p ON pe.program_id = p.id
        JOIN disciplines d ON p.discipline_id = d.id
        JOIN institutions i ON p.institution_id = i.id
        {where_clause}
        ORDER BY pe.embedding <=> cast(:query_embedding as vector)
        LIMIT :top_k
    """

    where_clause = ""
    params = {"query_embedding": str(query_vector), "top_k": top_k}

    if stream_category:
        where_clause = "WHERE p.stream_category = :stream_category"
        params["stream_category"] = stream_category

    sql = sql.format(where_clause=where_clause)
    results = session.exec(sql_text(sql).bindparams(**params)).all()

    # Deduplicate by program_id (keep highest similarity per program)
    seen = {}
    for row in results:
        pid = row[0]
        if pid not in seen:
            seen[pid] = SemanticSearchResult(
                program_id=row[0],
                chunk_text=row[1],
                similarity_score=round(float(row[2]), 4),
                metadata={
                    "program_name": row[3],
                    "site": row[4],
                    "discipline_name": row[5],
                    "institution_name": row[6],
                    "stream_category": row[7],
                },
            )

    unique_results = list(seen.values())

    return SemanticSearchResponse(
        query=q,
        results=unique_results,
        total=len(unique_results),
    )


# ========================
# Q&A Endpoint (RAG: LangChain + Ollama)
# ========================
@router.get("/qa", response_model=QAResponse)
def question_answer(
    q: str = Query(..., min_length=5, description="Natural language question about CaRMS programs"),
    top_k: int = Query(5, ge=1, le=20, description="Number of source chunks to retrieve"),
    session: Session = Depends(get_session),
):
    """
    Ask a natural language question about CaRMS residency programs.

    Uses Retrieval-Augmented Generation (RAG):
        1. Encodes the question using LangChain HuggingFaceEmbeddings
        2. Retrieves the most relevant program description chunks via pgvector
        3. Feeds them as context to a local LLM (Ollama/Mistral) via LangChain
        4. Returns a synthesized natural language answer with source citations

    Requires Ollama running locally with Mistral model:
        ollama pull mistral
        ollama serve

    Example questions:
        - "Which programs in Ontario offer rural medicine training?"
        - "What are the research opportunities in pediatrics?"
        - "Which universities have the highest quotas for family medicine?"
    """
    # Step 1: Retrieve relevant chunks using LangChain embeddings + pgvector
    embeddings = get_embeddings()
    query_vector = embeddings.embed_query(q)

    sql = """
        SELECT pe.chunk_text, p.name as program_name, i.name as institution_name
        FROM program_embeddings pe
        JOIN programs p ON pe.program_id = p.id
        JOIN institutions i ON p.institution_id = i.id
        ORDER BY pe.embedding <=> cast(:query_embedding as vector)
        LIMIT :top_k
    """

    params = {"query_embedding": str(query_vector), "top_k": top_k}
    results = session.exec(sql_text(sql).bindparams(**params)).all()

    if not results:
        raise HTTPException(status_code=404, detail="No relevant program data found.")

    # Step 2: Build context from retrieved chunks
    source_chunks = []
    context_parts = []
    for row in results:
        chunk_text, program_name, institution_name = row[0], row[1], row[2]
        source_chunks.append(f"[{program_name} — {institution_name}]: {chunk_text[:200]}...")
        context_parts.append(f"Program: {program_name} ({institution_name})\n{chunk_text}")

    context = "\n\n---\n\n".join(context_parts)

    # Step 3: Generate answer using LangChain + Ollama
    try:
        llm = get_llm()
        prompt = RAG_PROMPT.format(context=context, question=q)
        answer = llm.invoke(prompt)
    except Exception as e:
        error_msg = str(e)
        if "Connection" in error_msg or "refused" in error_msg:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Ollama is not running. Start it with: "
                    "1) Install: https://ollama.ai  "
                    "2) Pull model: ollama pull mistral  "
                    "3) Serve: ollama serve"
                ),
            )
        raise HTTPException(status_code=500, detail=f"LLM error: {error_msg}")

    return QAResponse(
        query=q,
        answer=answer.strip(),
        source_chunks=source_chunks,
        num_sources=len(source_chunks),
    )
