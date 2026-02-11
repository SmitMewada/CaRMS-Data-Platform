"""
   This file contains the code for generating embeddings for program descriptions.
"""

from typing import List, Dict

from dagster import asset
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from sqlmodel import Session, text as sql_text

from dagster_pipeline.models.database import (
    ProgramEmbedding,
    get_engine,
)

# Chunking config
CHUNK_SIZE = 1000       
CHUNK_OVERLAP = 200  


@asset(
    group_name="embeddings",
    description="Chunk 815 markdown documents into ~1000 char segments with overlap",
)
def chunked_documents(raw_markdown: list) -> List[Dict]:
    """ Split each program's markdown text into overlapping chunks. """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    all_chunks = []

    for entry in raw_markdown:
        # Extract program_stream_id from JSON id format "1503|27447"
        program_id = int(entry["id"].split("|")[1])
        content = entry["page_content"]

        # Split into chunks
        chunks = splitter.split_text(content)

        for i, chunk_text in enumerate(chunks):
            all_chunks.append({
                "program_id": program_id,
                "chunk_index": i,
                "chunk_text": chunk_text,
            })

    print(f"Chunked programs into {len(all_chunks)} chunks")
    print(f"Avg chunks per program: {len(all_chunks) / 815:.1f}")

    return all_chunks


@asset(
    group_name="embeddings",
    description="Generate embeddings with all-MiniLM-L6-v2 and store in pgvector",
    deps=["db_programs"],
)
def db_embeddings(chunked_documents: List[Dict]) -> None:
    """ Generate vector embeddings for all chunks and insert into program_embeddings.  """
    engine = get_engine()

    # Drop and recreate program_embeddings table to handle dimension changes
    with engine.connect() as conn:
        conn.execute(sql_text("DROP TABLE IF EXISTS program_embeddings CASCADE"))
        conn.execute(sql_text("""
            CREATE TABLE program_embeddings (
                id SERIAL PRIMARY KEY,
                program_id INTEGER NOT NULL REFERENCES programs(id),
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT,
                embedding vector(384),
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
            )
        """))
        conn.commit()
    print("Recreated program_embeddings table with vector(384)")

    # Load the embedding model
    print("Loading sentence-transformers model (first run downloads ~80MB)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("Model loaded")

    # Extract all chunk texts for batch encoding
    texts = [chunk["chunk_text"] for chunk in chunked_documents]

    # Generate embeddings in one batch (much faster than one-by-one)
    print(f"Generating embeddings for {len(texts)} chunks...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=128)
    print("Embeddings generated")

    # Insert into database in batches
    with Session(engine) as session:
        batch_size = 500
        for i in range(0, len(chunked_documents), batch_size):
            batch_chunks = chunked_documents[i : i + batch_size]
            batch_embeddings = embeddings[i : i + batch_size]

            records = []
            for chunk, embedding in zip(batch_chunks, batch_embeddings):
                record = ProgramEmbedding(
                    program_id=chunk["program_id"],
                    chunk_index=chunk["chunk_index"],
                    chunk_text=chunk["chunk_text"],
                    embedding=embedding.tolist(),
                )
                records.append(record)

            session.add_all(records)
            session.commit()

            loaded = min(i + batch_size, len(chunked_documents))
            print(f"   Inserted {loaded}/{len(chunked_documents)} embeddings...")

    # Create an index for faster similarity search
    with engine.connect() as conn:
        conn.execute(sql_text("""
            CREATE INDEX IF NOT EXISTS idx_program_embeddings_vector
            ON program_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 50)
        """))
        conn.commit()
    print("Created IVFFlat index for cosine similarity search")

    print(f"Loaded {len(chunked_documents)} embeddings into program_embeddings")
