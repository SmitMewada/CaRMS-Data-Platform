"""
   This file contains the code for the transformation of data in the data pipeline.
"""

import re
from typing import Dict, List

import pandas as pd
from dagster import asset

# French-language universities in CaRMS
FRENCH_SCHOOLS = {
    "Université Laval",
    "Université de Sherbrooke",
    "Université de Montréal",
}

# Sections to extract from the wide CSV (skip index, IDs, metadata columns)
SECTION_COLUMNS = [
    "program_name",
    "match_iteration_name",
    "program_contracts",
    "general_instructions",
    "supporting_documentation_information",
    "review_process",
    "interviews",
    "selection_criteria",
    "program_highlights",
    "program_curriculum",
    "training_sites",
    "additional_information",
    "return_of_service",
    "faq",
    "summary_of_changes",
]

def derive_stream_category(stream: str) -> str:
    """ Maps 14 stream types to 3 categories."""
    stream_upper = stream.upper()
    
    if "IMG" in stream_upper:
        return "IMG"
    elif "CMG" in stream_upper:
        return "CMG"
    else:
        return "All"
    
    
def extract_quota(markdown_text: str) -> int | None:
    """ Extract appropriate quota from markdown text. """
    match = re.search(
        r"Approximate Quota[:\s]*\n+\s*(?:##)?\s*(\d+)",
        markdown_text, 
        re.IGNORECASE
    )
    
    if match: 
        return int(match.group(1))
    return None


def extract_accreditation(markdown_text: str) -> str | None:
    """ Extract accreditation status from markdown text. """
    
    match = re.search(
        r"(?:##)?\s*(?:Accreditation status|Statut d['\u2019]agr[ée]ment)\s*:\s*(.+?)(?:\n|$)",
        markdown_text, 
        re.IGNORECASE
    )
    
    if match: 
        return match.group(1).strip().strip("#").strip("*").strip()
    return None


## ------------------- ASSETS ------------------- ##

@asset(
    group_name="transform",
    description="Cleaned discipline dimension table"
)
def stg_disciplines(raw_disciplines: pd.DataFrame) -> pd.DataFrame:
    """Clean and validate disciplines"""
    df = raw_disciplines.copy()
    
    df = df.rename(columns={"discipline_id": "id", "discipline": "name"})
    
    assert df["id"].notna().all(), "Found null discipline_id"
    assert df["id"].is_unique, "Found duplicate discipline_id"
    assert df["name"].notna().all(), "Found null discipline name"
    
    df = df[["id", "name"]]
    
    return df

@asset(
    group_name="transform",
    description="Deduplicated institution table"
)
def stg_institutions(raw_programs: pd.DataFrame) -> pd.DataFrame:
    """ Extract unique institutions from the program master table """
    df = raw_programs.copy()
    
    institutions = (
        df.groupby("school_name")["school_id"].min().reset_index().rename(
            columns={"school_id": "id", "school_name": "name"}
        ) 
    )
    
    institutions["language"] = institutions["name"].apply(
        lambda x: "fr" if x in FRENCH_SCHOOLS else "en"
    )
    
    # Validate
    assert len(institutions) == 18, f"Expected 18 institutions, got {len(institutions)}"
    assert institutions["id"].is_unique, "Duplicate institution IDs"

    return institutions[["id", "name", "language"]]

@asset(
    group_name="transform",
    description="Enriched programs with quota, accreditation, and stream_category"
)
def stg_programs(
    raw_programs: pd.DataFrame, 
    raw_markdown: list,
    stg_institutions: pd.DataFrame           
) -> pd.DataFrame:
    """ Transform programs: map institution IDs, derive stream_category, extract quota and accreditation from markdown. """
    
    df = raw_programs.copy()
    
    # Build markdown lookup: program_stream_id -> page_content
    markdown_lookup: Dict[int, str] = {}
    for entry in raw_markdown:
        
        program_stream_id = int(entry["id"].split("|")[1])
        markdown_lookup[program_stream_id] = entry["page_content"]
        
    inst_map = dict(zip(stg_institutions["name"], stg_institutions["id"]))
    
    df["institution_id"] = df["school_name"].map(inst_map)
    assert df["institution_id"].notna().all(), "Some schools didn't map to institutions"
    
    df["stream_category"] = df["program_stream"].apply(derive_stream_category)

      # Extract quota and accreditation from markdown
    df["quota"] = df["program_stream_id"].apply(
        lambda pid: extract_quota(markdown_lookup.get(pid, ""))
    )
    df["accreditation"] = df["program_stream_id"].apply(
        lambda pid: extract_accreditation(markdown_lookup.get(pid, ""))
    )
    
    
    # Drop the pandas index column artifact if present
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])

    # Rename and select final columns matching our schema
    result = df.rename(
        columns={
            "program_stream_id": "id",
            "program_name": "name",
            "program_site": "site",
            "program_stream": "stream",
            "program_url": "source_url",
        }
    )[
        [
            "id",
            "discipline_id",
            "institution_id",
            "name",
            "site",
            "stream",
            "stream_category",
            "quota",
            "accreditation",
            "source_url",
        ]
    ]

    # Validate
    assert len(result) == 815, f"Expected 815 programs, got {len(result)}"
    assert result["id"].is_unique, "Duplicate program IDs"

    return result


@asset(
    group_name="transform",
    description="Program descriptions pivoted from wide."
)
def stg_sections(raw_sections: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot the wide CSV into long format.

    """
    df = raw_sections.copy()

    # Melt the wide columns into long format
    melted = df.melt(
        id_vars=["program_description_id"],
        value_vars=SECTION_COLUMNS,
        var_name="section_name",
        value_name="content",
    )

    melted = melted.dropna(subset=["content"])
    melted = melted.rename(columns={"program_description_id": "program_id"})

    result = melted[["program_id", "section_name", "content"]].reset_index(drop=True)

    return result
