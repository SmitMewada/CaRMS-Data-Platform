"""
    This file contains the code for the ingestion of data into the data pipeline.
"""

import json
from pathlib import Path
import pandas as pd
from dagster import asset, MaterializeResult, MetadataValue

DATA_DIR = Path(__file__).parent.parent.parent / "data"

@asset(
    group_name="ingestion",
    description="Raw discipline look up table from 1503_discipline.xlsx"
)
def raw_disciplines() -> pd.DataFrame:
    """Loads the discipline dimension table"""
    filepath = DATA_DIR / "1503_discipline.xlsx"
    df = pd.read_excel(filepath)
    
    return df


@asset(
    group_name="ingestion",
    description="Raw program master table from 1503_program_master.xlsx"
)
def raw_programs() -> pd.DataFrame:
    """Loads the program master table"""
    filepath = DATA_DIR / "1503_program_master.xlsx"
    df = pd.read_excel(filepath)
    
    return df


@asset(
    group_name="ingestion",
    description="Raw program description by section from 1503_program_description_by_section.xlsx"
)
def raw_sections() -> pd.DataFrame:
    """Loads structured program descriptions (wide format)"""
    filepath = DATA_DIR / "1503_program_descriptions_x_section.csv"
    df = pd.read_csv(filepath)
    
    return df


@asset(
    group_name="ingestion",
    description="Raw markdown program descriptions"
)
def raw_markdown() -> list:
    """Load the fulll markdown program descriptions for each program"""
    filepath = DATA_DIR / "1503_markdown_program_descriptions_v2.json"
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return data