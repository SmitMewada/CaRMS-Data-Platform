"""
Programs API Router.

Endpoints:
    GET /programs              — List programs with filtering + pagination
    GET /programs/{program_id} — Get single program with full descriptions
    GET /programs/search       — Text search across program names and descriptions
"""

import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func, col
from sqlalchemy import or_

# Import DB models from the shared models package
import sys
from pathlib import Path

# Add project root to path so we can import dagster_pipeline.models
sys.path.insert(0, str(Path(__file__).parent.parent))

from dagster_pipeline.models.database import (
    Program,
    Discipline,
    Institution,
    ProgramDescription,
)
from api.database import get_session
from api.schemas import (
    ProgramListResponse,
    ProgramDetailResponse,
    ProgramDescriptionResponse,
    PaginatedResponse,
)

router = APIRouter(prefix="/programs", tags=["Programs"])


@router.get("", response_model=PaginatedResponse)
def list_programs(
    # Filters
    discipline_id: Optional[int] = Query(None, description="Filter by discipline ID"),
    institution_id: Optional[int] = Query(None, description="Filter by institution ID"),
    stream_category: Optional[str] = Query(
        None, description="Filter by stream category: CMG, IMG, or All"
    ),
    site: Optional[str] = Query(None, description="Filter by city/site (partial match)"),
    language: Optional[str] = Query(
        None, description="Filter by institution language: en or fr"
    ),
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    # Session
    session: Session = Depends(get_session),
):
    """
    List all programs with optional filters and pagination.

    """
    # Base query with joins
    query = (
        select(Program, Discipline.name, Institution.name)
        .join(Discipline, Program.discipline_id == Discipline.id)
        .join(Institution, Program.institution_id == Institution.id)
    )

    # Apply filters
    if discipline_id is not None:
        query = query.where(Program.discipline_id == discipline_id)
    if institution_id is not None:
        query = query.where(Program.institution_id == institution_id)
    if stream_category is not None:
        query = query.where(Program.stream_category == stream_category)
    if site is not None:
        query = query.where(col(Program.site).ilike(f"%{site}%"))
    if language is not None:
        query = query.where(Institution.language == language)

    # Count total (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total = session.exec(count_query).one()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Program.name)

    results = session.exec(query).all()

    # Build response
    items = [
        ProgramListResponse(
            id=program.id,
            name=program.name,
            site=program.site,
            stream=program.stream,
            stream_category=program.stream_category,
            quota=program.quota,
            accreditation=program.accreditation,
            source_url=program.source_url,
            discipline_name=disc_name,
            institution_name=inst_name,
        )
        for program, disc_name, inst_name in results
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/search", response_model=PaginatedResponse)
def search_programs(
    q: str = Query(..., min_length=2, description="Search query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """
    Text search across program names, sites, and description content.

    Uses PostgreSQL ILIKE for case-insensitive partial matching.
    Searches across: program name, site, and all description sections.
    """
    search_pattern = f"%{q}%"

    # Find program IDs that match in descriptions
    desc_subquery = (
        select(ProgramDescription.program_id)
        .where(col(ProgramDescription.content).ilike(search_pattern))
        .distinct()
    )

    # Main query: match in program name, site, OR descriptions
    query = (
        select(Program, Discipline.name, Institution.name)
        .join(Discipline, Program.discipline_id == Discipline.id)
        .join(Institution, Program.institution_id == Institution.id)
        .where(
            or_(
                col(Program.name).ilike(search_pattern),
                col(Program.site).ilike(search_pattern),
                col(Program.id).in_(desc_subquery),
            )
        )
    )

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = session.exec(count_query).one()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Program.name)

    results = session.exec(query).all()

    items = [
        ProgramListResponse(
            id=program.id,
            name=program.name,
            site=program.site,
            stream=program.stream,
            stream_category=program.stream_category,
            quota=program.quota,
            accreditation=program.accreditation,
            source_url=program.source_url,
            discipline_name=disc_name,
            institution_name=inst_name,
        )
        for program, disc_name, inst_name in results
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/{program_id}", response_model=ProgramDetailResponse)
def get_program(
    program_id: int,
    session: Session = Depends(get_session),
):
    """
    Get a single program with its full descriptions.

    Returns the program details plus all description sections
    (selection_criteria, program_curriculum, etc.)
    """
    # Get program with joined discipline and institution names
    result = session.exec(
        select(Program, Discipline.name, Institution.name)
        .join(Discipline, Program.discipline_id == Discipline.id)
        .join(Institution, Program.institution_id == Institution.id)
        .where(Program.id == program_id)
    ).first()

    if not result:
        raise HTTPException(status_code=404, detail=f"Program {program_id} not found")

    program, disc_name, inst_name = result

    # Get descriptions
    descriptions = session.exec(
        select(ProgramDescription)
        .where(ProgramDescription.program_id == program_id)
        .order_by(ProgramDescription.section_name)
    ).all()

    return ProgramDetailResponse(
        id=program.id,
        name=program.name,
        site=program.site,
        stream=program.stream,
        stream_category=program.stream_category,
        quota=program.quota,
        accreditation=program.accreditation,
        source_url=program.source_url,
        discipline_name=disc_name,
        institution_name=inst_name,
        descriptions=[
            ProgramDescriptionResponse(
                section_name=d.section_name,
                content=d.content,
            )
            for d in descriptions
        ],
    )
