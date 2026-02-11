"""
    This file contains API response schemas using Pydantic models for data validation and serialization.
"""

from pydantic import BaseModel
from typing import Optional, List


# ========================
# Discipline
# ========================
class DisciplineResponse(BaseModel):
    id: int
    name: str
    program_count: Optional[int] = None

    model_config = {"from_attributes": True}



# Institution
class InstitutionResponse(BaseModel):
    id: int
    name: str
    language: str
    program_count: Optional[int] = None

    model_config = {"from_attributes": True}



# Program (list view — compact)
class ProgramListResponse(BaseModel):
    id: int
    name: str
    site: str
    stream: str
    stream_category: str
    quota: Optional[int] = None
    accreditation: Optional[str] = None
    source_url: str
    discipline_name: str
    institution_name: str

    model_config = {"from_attributes": True}


# Program Description
class ProgramDescriptionResponse(BaseModel):
    section_name: str
    content: str

    model_config = {"from_attributes": True}



# Program (detail view — full with descriptions)
class ProgramDetailResponse(BaseModel):
    id: int
    name: str
    site: str
    stream: str
    stream_category: str
    quota: Optional[int] = None
    accreditation: Optional[str] = None
    source_url: str
    discipline_name: str
    institution_name: str
    descriptions: List[ProgramDescriptionResponse] = []

    model_config = {"from_attributes": True}


# Statistics
class StreamCategoryStats(BaseModel):
    stream_category: str
    count: int


class DisciplineStats(BaseModel):
    discipline_name: str
    program_count: int
    total_quota: Optional[int] = None


class MatchStatisticsResponse(BaseModel):
    total_programs: int
    total_disciplines: int
    total_institutions: int
    total_quota: Optional[int] = None
    by_stream_category: List[StreamCategoryStats]
    top_disciplines: List[DisciplineStats]



# Paginated Response Wrapper
class PaginatedResponse(BaseModel):
    items: List[ProgramListResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
