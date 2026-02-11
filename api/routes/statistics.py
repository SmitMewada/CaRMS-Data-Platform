"""
Statistics API Router.

Endpoints:
    GET /statistics — Aggregate match statistics (totals, breakdowns)
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func

from dagster_pipeline.models.database import Program, Discipline, Institution
from api.database import get_session
from api.schemas import (
    MatchStatisticsResponse,
    StreamCategoryStats,
    DisciplineStats,
)

router = APIRouter(prefix="/statistics", tags=["Statistics"])


@router.get("", response_model=MatchStatisticsResponse)
def get_statistics(session: Session = Depends(get_session)):
    """
    Get aggregate statistics for the R-1 match.

    """
    # Totals
    total_programs = session.exec(select(func.count(Program.id))).one()
    total_disciplines = session.exec(select(func.count(Discipline.id))).one()
    total_institutions = session.exec(select(func.count(Institution.id))).one()
    total_quota = session.exec(select(func.sum(Program.quota))).one()

    # By stream category
    stream_results = session.exec(
        select(
            Program.stream_category,
            func.count(Program.id),
        )
        .group_by(Program.stream_category)
        .order_by(func.count(Program.id).desc())
    ).all()

    by_stream = [
        StreamCategoryStats(stream_category=r[0], count=r[1])
        for r in stream_results
    ]

    # Top disciplines
    disc_results = session.exec(
        select(
            Discipline.name,
            func.count(Program.id),
            func.sum(Program.quota),
        )
        .join(Program, Discipline.id == Program.discipline_id)
        .group_by(Discipline.name)
        .order_by(func.count(Program.id).desc())
        .limit(10)
    ).all()

    top_disciplines = [
        DisciplineStats(
            discipline_name=r[0],
            program_count=r[1],
            total_quota=r[2],
        )
        for r in disc_results
    ]

    return MatchStatisticsResponse(
        total_programs=total_programs,
        total_disciplines=total_disciplines,
        total_institutions=total_institutions,
        total_quota=total_quota,
        by_stream_category=by_stream,
        top_disciplines=top_disciplines,
    )
