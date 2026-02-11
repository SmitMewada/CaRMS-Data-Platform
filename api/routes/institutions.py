"""
Institutions API Router.

"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, func

from dagster_pipeline.models.database import Institution, Program
from api.database import get_session
from api.schemas import InstitutionResponse

router = APIRouter(prefix="/institutions", tags=["Institutions"])


@router.get("", response_model=List[InstitutionResponse])
def list_institutions(
    language: Optional[str] = Query(None, description="Filter by language: en or fr"),
    session: Session = Depends(get_session),
):
    """
    List all institutions with the count of programs at each.

    """
    query = (
        select(
            Institution.id,
            Institution.name,
            Institution.language,
            func.count(Program.id).label("program_count"),
        )
        .outerjoin(Program, Institution.id == Program.institution_id)
        .group_by(Institution.id, Institution.name, Institution.language)
        .order_by(func.count(Program.id).desc())
    )

    if language is not None:
        query = query.where(Institution.language == language)

    results = session.exec(query).all()

    return [
        InstitutionResponse(
            id=r[0], name=r[1], language=r[2], program_count=r[3]
        )
        for r in results
    ]
