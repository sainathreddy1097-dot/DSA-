"""Reviewer profile and availability lifecycle routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_session
from ..errors import ApiError
from ..services.identifiers import next_identifier
from ..services.lifecycle import audit_event


router = APIRouter(prefix="/reviewers", tags=["reviewers"])


def _reviewer_or_404(session: Session, reviewer_id: str) -> models.Reviewer:
    reviewer = session.scalar(
        select(models.Reviewer)
        .where(models.Reviewer.id == reviewer_id)
        .options(selectinload(models.Reviewer.expertise).selectinload(models.ReviewerExpertise.expertise))
    )
    if not reviewer:
        raise ApiError(404, "not_found", f"Reviewer {reviewer_id} was not found")
    return reviewer


def _assigned_count(session: Session, reviewer: models.Reviewer) -> int:
    confirmed = session.scalar(
        select(func.count()).select_from(models.Assignment).where(models.Assignment.reviewer_id == reviewer.id)
    ) or 0
    return reviewer.workload + confirmed


def _payload(session: Session, reviewer: models.Reviewer) -> dict:
    return {
        "id": reviewer.id,
        "name": reviewer.name,
        "role": reviewer.role,
        "assigned": _assigned_count(session, reviewer),
        "capacity": reviewer.capacity,
        "expertise": sorted(item.expertise.name for item in reviewer.expertise),
        "active": reviewer.active,
        "archivedAt": reviewer.archived_at,
        "updatedAt": reviewer.updated_at,
    }


def _replace_expertise(session: Session, reviewer: models.Reviewer, names: list[str]) -> None:
    normalized = sorted({name.strip() for name in names if name.strip()})
    if not normalized:
        raise ApiError(422, "validation_error", "At least one expertise value is required")
    existing = {
        item.name: item
        for item in session.scalars(select(models.Expertise).where(models.Expertise.name.in_(normalized))).all()
    }
    for name in normalized:
        if name not in existing:
            expertise = models.Expertise(id=next_identifier(session, models.Expertise, "EXP", 2), name=name)
            session.add(expertise)
            session.flush()
            existing[name] = expertise
    reviewer.expertise.clear()
    reviewer.expertise.extend(models.ReviewerExpertise(expertise=existing[name]) for name in normalized)


@router.post("", response_model=schemas.ReviewerOut, status_code=status.HTTP_201_CREATED)
def create_reviewer(payload: schemas.ReviewerCreate, session: Session = Depends(get_session)):
    reviewer = models.Reviewer(
        id=next_identifier(session, models.Reviewer, "REV", 3),
        name=payload.name,
        role=payload.role,
        workload=0,
        capacity=payload.capacity,
        active=True,
        updated_at=datetime.now(),
    )
    session.add(reviewer)
    _replace_expertise(session, reviewer, payload.expertise)
    audit_event(session, "Compliance Reviewer", "Reviewer Created", "Reviewer", reviewer.id, reviewer.name)
    session.commit()
    return _payload(session, reviewer)


@router.patch("/{reviewer_id}", response_model=schemas.ReviewerOut)
def update_reviewer(
    reviewer_id: str,
    payload: schemas.ReviewerUpdate,
    session: Session = Depends(get_session),
):
    reviewer = _reviewer_or_404(session, reviewer_id)
    if reviewer.updated_at != payload.updated_at.replace(tzinfo=None):
        raise ApiError(409, "stale_record", "This reviewer was changed after it was loaded")
    if payload.capacity is not None and payload.capacity < _assigned_count(session, reviewer):
        raise ApiError(409, "capacity_conflict", "Capacity cannot be lower than active assigned work")
    changes = payload.model_dump(exclude={"updated_at", "expertise"}, exclude_none=True)
    for key, value in changes.items():
        setattr(reviewer, key, value)
    if payload.expertise is not None:
        _replace_expertise(session, reviewer, payload.expertise)
        changes["expertise"] = payload.expertise
    reviewer.updated_at = datetime.now()
    audit_event(session, "Compliance Reviewer", "Reviewer Updated", "Reviewer", reviewer.id, ", ".join(sorted(changes)))
    session.commit()
    return _payload(session, reviewer)


@router.post("/{reviewer_id}/deactivate", response_model=schemas.ReviewerOut)
def deactivate_reviewer(reviewer_id: str, session: Session = Depends(get_session)):
    reviewer = _reviewer_or_404(session, reviewer_id)
    if not reviewer.active:
        raise ApiError(409, "invalid_state", f"Reviewer {reviewer_id} is already inactive")
    confirmed = session.scalar(select(models.Assignment.id).where(models.Assignment.reviewer_id == reviewer_id))
    if confirmed:
        raise ApiError(409, "active_assignment_conflict", "Reassign confirmed contracts before deactivating this reviewer")
    reviewer.active = False
    reviewer.archived_at = datetime.now()
    reviewer.updated_at = datetime.now()
    audit_event(session, "Compliance Reviewer", "Reviewer Deactivated", "Reviewer", reviewer.id, reviewer.name)
    session.commit()
    return _payload(session, reviewer)


@router.post("/{reviewer_id}/reactivate", response_model=schemas.ReviewerOut)
def reactivate_reviewer(reviewer_id: str, session: Session = Depends(get_session)):
    reviewer = _reviewer_or_404(session, reviewer_id)
    if reviewer.active:
        raise ApiError(409, "invalid_state", f"Reviewer {reviewer_id} is already active")
    reviewer.active = True
    reviewer.archived_at = None
    reviewer.updated_at = datetime.now()
    audit_event(session, "Compliance Reviewer", "Reviewer Reactivated", "Reviewer", reviewer.id, reviewer.name)
    session.commit()
    return _payload(session, reviewer)
