"""
This file contains load asset from dagster pipeline

"""

import pandas as pd
from dagster import asset
from sqlmodel import Session

from dagster_pipeline.models.database import (
    Discipline,
    Institution,
    Program,
    ProgramDescription,
    ProgramEmbedding,
    get_engine,
)


@asset(
    group_name="load",
    description="Load 37 disciplines into PostgreSQL",
)
def db_disciplines(stg_disciplines: pd.DataFrame) -> None:
    """Insert disciplines into the database."""
    engine = get_engine()

    with Session(engine) as session:
        # Must delete in reverse FK order
        session.query(ProgramEmbedding).delete()
        session.query(ProgramDescription).delete()
        session.query(Program).delete()
        session.query(Institution).delete()
        session.query(Discipline).delete()

        session.commit()

        records = [
            Discipline(id=int(row["id"]), name=row["name"])
            for _, row in stg_disciplines.iterrows()
        ]
        session.add_all(records)
        session.commit()

        print(f"Loaded {len(records)} disciplines")


@asset(
    group_name="load",
    description="Load 18 institutions into PostgreSQL",
    deps=["db_disciplines"],
)
def db_institutions(stg_institutions: pd.DataFrame) -> None:
    """Insert institutions into the database."""
    engine = get_engine()

    with Session(engine) as session:
        # Must delete in reverse FK order
        session.query(ProgramEmbedding).delete()
        session.query(ProgramDescription).delete()
        session.query(Program).delete()
        session.query(Institution).delete()
        session.commit()

        records = [
            Institution(
                id=int(row["id"]),
                name=row["name"],
                language=row["language"],
            )
            for _, row in stg_institutions.iterrows()
        ]
        session.add_all(records)
        session.commit()

        print(f"Loaded {len(records)} institutions")

@asset(
    group_name="load",
    description="Load 815 programs into PostgreSQL",
    deps=["db_disciplines", "db_institutions"],
)
def db_programs(stg_programs: pd.DataFrame) -> None:
    """Insert programs into the database."""
    engine = get_engine()

    with Session(engine) as session:
        # Must delete descriptions first (FK constraint)
        session.query(ProgramEmbedding).delete()
        session.query(ProgramDescription).delete()
        session.query(Program).delete()
        session.commit()

        records = []
        for _, row in stg_programs.iterrows():
            program = Program(
                id=int(row["id"]),
                discipline_id=int(row["discipline_id"]),
                institution_id=int(row["institution_id"]),
                name=row["name"],
                site=row["site"],
                stream=row["stream"],
                stream_category=row["stream_category"],
                quota=int(row["quota"]) if pd.notna(row["quota"]) else None,
                accreditation=row["accreditation"] if pd.notna(row["accreditation"]) else None,
                source_url=row["source_url"],
            )
            records.append(program)

        session.add_all(records)
        session.commit()

        print(f"Loaded {len(records)} programs")


@asset(
    group_name="load",
    description="Load program descriptions (long format) into PostgreSQL",
    deps=["db_programs"],
)
def db_descriptions(stg_sections: pd.DataFrame) -> None:
    """Insert program descriptions into the database."""
    engine = get_engine()

    with Session(engine) as session:
        session.query(ProgramDescription).delete()
        session.commit()

        records = []
        for _, row in stg_sections.iterrows():
            desc = ProgramDescription(
                program_id=int(row["program_id"]),
                section_name=row["section_name"],
                content=row["content"],
            )
            records.append(desc)

        # Bulk insert in batches of 1000 for memory efficiency
        batch_size = 1000
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            session.add_all(batch)
            session.commit()

        print(f"Loaded {len(records)} program description sections")
