"""
Database session management for FastAPI.

"""

import os
from dotenv import load_dotenv
from sqlmodel import Session, create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Single engine instance shared across all requests
# pool_pre_ping=True: verifies connections are alive before using them
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def get_session():
    """Yield a database session for each request, auto-close after."""
    with Session(engine) as session:
        yield session
