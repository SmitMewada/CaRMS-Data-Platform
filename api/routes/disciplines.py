"""
Disciplines API Router.

"""
from typing import List

from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func

from dagster_pipeline.models.database import Discipline, Program
from api.database import get_session
from api.schemas import DisciplineResponse

router = APIRouter(prefix="/disciplines", tags=["Disciplines"])


@router.get("", response_model=List[DisciplineResponse])
def list_disciplines(session: Session = Depends(get_session)):
    """ List all disciplines with the count of programs in each. """
    results = session.exec(
        select(
            Discipline.id,
            Discipline.name,
            func.count(Program.id).label("program_count"),
        )
        .outerjoin(Program, Discipline.id == Program.discipline_id)
        .group_by(Discipline.id, Discipline.name)
        .order_by(func.count(Program.id).desc())
    ).all()

    return [
        DisciplineResponse(id=r[0], name=r[1], program_count=r[2])
        for r in results
    ]