"""Compliance obligation lifecycle routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session
from ..errors import ApiError
from ..services.identifiers import next_identifier
from ..services.lifecycle import audit_event


router = APIRouter(prefix="/obligations", tags=["obligations"])


def _obligation_or_404(session: Session, obligation_id: str, *, include_archived: bool = False):
    obligation = session.get(models.Obligation, obligation_id)
    if not obligation or (obligation.archived_at is not None and not include_archived):
        raise ApiError(404, "not_found", f"Obligation {obligation_id} was not found")
    return obligation


@router.get("", response_model=schemas.Page[schemas.ObligationOut])
def list_obligations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    include_archived: bool = Query(False, alias="includeArchived"),
    session: Session = Depends(get_session),
):
    statement = select(models.Obligation)
    if not include_archived:
        statement = statement.where(models.Obligation.archived_at.is_(None))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    items = session.scalars(
        statement.order_by(models.Obligation.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }


@router.post("", response_model=schemas.ObligationOut, status_code=status.HTTP_201_CREATED)
def create_obligation(payload: schemas.ObligationCreate, session: Session = Depends(get_session)):
    duplicate = session.scalar(select(models.Obligation.id).where(
        func.lower(models.Obligation.name) == payload.name.casefold()
    ))
    if duplicate:
        raise ApiError(409, "duplicate_obligation", f"Obligation {payload.name} already exists")
    obligation = models.Obligation(
        id=next_identifier(session, models.Obligation, "OBL", 2),
        **payload.model_dump(),
        updated_at=datetime.now(),
    )
    session.add(obligation)
    audit_event(session, "Compliance Reviewer", "Obligation Created", "Obligation", obligation.id, obligation.name)
    session.commit()
    return obligation


@router.patch("/{obligation_id}", response_model=schemas.ObligationOut)
def update_obligation(
    obligation_id: str,
    payload: schemas.ObligationUpdate,
    session: Session = Depends(get_session),
):
    obligation = _obligation_or_404(session, obligation_id)
    if obligation.updated_at != payload.updated_at.replace(tzinfo=None):
        raise ApiError(409, "stale_record", "This obligation was changed after it was loaded")
    changes = payload.model_dump(exclude={"updated_at"}, exclude_none=True)
    for key, value in changes.items():
        setattr(obligation, key, value)
    obligation.updated_at = datetime.now()
    audit_event(session, "Compliance Reviewer", "Obligation Updated", "Obligation", obligation.id, ", ".join(sorted(changes)))
    session.commit()
    return obligation


@router.post("/{obligation_id}/archive", response_model=schemas.ObligationOut)
def archive_obligation(obligation_id: str, session: Session = Depends(get_session)):
    obligation = _obligation_or_404(session, obligation_id)
    obligation.archived_at = datetime.now()
    obligation.updated_at = datetime.now()
    audit_event(session, "Compliance Reviewer", "Obligation Archived", "Obligation", obligation.id, obligation.name)
    session.commit()
    return obligation


@router.post("/{obligation_id}/restore", response_model=schemas.ObligationOut)
def restore_obligation(obligation_id: str, session: Session = Depends(get_session)):
    obligation = _obligation_or_404(session, obligation_id, include_archived=True)
    if obligation.archived_at is None:
        raise ApiError(409, "invalid_state", f"Obligation {obligation_id} is not archived")
    obligation.archived_at = None
    obligation.updated_at = datetime.now()
    audit_event(session, "Compliance Reviewer", "Obligation Restored", "Obligation", obligation.id, obligation.name)
    session.commit()
    return obligation
