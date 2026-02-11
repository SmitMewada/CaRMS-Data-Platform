"""
This file containes SQLModel database models for the CaRMS Dagster pipeline. 

"""
    
import os
from datetime import datetime
from typing import Optional, List

from dotenv import load_dotenv
from dotenv import load_dotenv
from sqlmodel import SQLModel, Field, Relationship, create_engine
from sqlalchemy import Column, Text
from pgvector.sqlalchemy import Vector


# Load env variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


# Table 1: Discipline
class Discipline(SQLModel, table=True):
    __tablename__ = "disciplines"
    __table_args__ = {"extend_existing": True}

    id: int = Field(primary_key=True)  # From discipline_id (not auto-increment)
    name: str

    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    programs: List["Program"] = Relationship(back_populates="discipline")
    
    
# Table 2: Institution
class Institution(SQLModel, table=True):
    __tablename__ = 'institutions'
    __table_args__ = {"extend_existing": True}
    
    id: int = Field(primary_key=True)
    name: str = Field(unique=True)
    language: str = Field(default="en")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Setup up relationships
    programs: List["Program"] = Relationship(back_populates="institution")
    
# Table 3: Program
class Program(SQLModel, table=True):
    __tablename__ = 'programs'
    __table_args__ = {"extend_existing": True}
    
    id: int = Field(primary_key=True)
    discipline_id: int = Field(foreign_key="disciplines.id")
    institution_id: int = Field(foreign_key="institutions.id")
    
    name: str
    site: str
    stream: str
    stream_category: str
    quota: Optional[int] = None
    accreditation: Optional[str] = None
    source_url: str
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    discipline: Optional[Discipline] = Relationship(back_populates="programs")
    institution: Optional[Institution] = Relationship(back_populates="programs")
    descriptions: List["ProgramDescription"] = Relationship(back_populates="program")
    embeddings: List["ProgramEmbedding"] = Relationship(back_populates="program")
    
# Table 4: Program Description
class ProgramDescription(SQLModel, table=True):
    __tablename__ = 'program_descriptions'
    __table_args__ = {"extend_existing": True}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    program_id: int = Field(foreign_key="programs.id")
    
    section_name: str
    content: str = Field(sa_column=Column(Text))
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    program: Optional[Program] = Relationship(back_populates="descriptions")
    
# Table 5: Program Embeddings
class ProgramEmbedding(SQLModel, table=True):
    __tablename__ = 'program_embeddings'
    __table_args__ = {"extend_existing": True}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    program_id: int = Field(foreign_key="programs.id")
    
    chunk_index: int
    chunk_text: str = Field(sa_column=Column(Text))
    embedding: Optional[List[float]] = Field(sa_column=Column(Vector(384)), default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    program: Optional[Program] = Relationship(back_populates="embeddings")
    
# Engine + Table Creation
def get_engine(echo: bool = False):
    return create_engine(DATABASE_URL, echo=echo)


def create_all_tables():
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    print("All tables created successfully.")
    
if __name__ == "__main__":
    create_all_tables()