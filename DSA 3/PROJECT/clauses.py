"""Clause lifecycle and obligation mapping routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session
from ..errors import ApiError
from ..services.lifecycle import audit_event


router = APIRouter(prefix="/clauses", tags=["clauses"])
version_router = APIRouter(tags=["clauses"])


def _current_clause(session: Session, clause_key: str, *, include_archived: bool = False) -> models.Clause:
    statement = (
        select(models.Clause)
        .join(models.ContractVersion, models.ContractVersion.id == models.Clause.version_id)
        .where(models.Clause.clause_key == clause_key)
        .order_by(models.ContractVersion.sequence.desc())
    )
    clause = session.scalar(statement)
    if not clause or (clause.archived_at is not None and not include_archived):
        raise ApiError(404, "not_found", f"Clause {clause_key} was not found")
    return clause


def _payload(clause: models.Clause) -> dict:
    return {
        "id": clause.clause_key,
        "clauseKey": clause.clause_key,
        "contractId": clause.contract_id,
        "versionId": clause.version_id,
        "title": clause.title,
        "text": clause.text,
        "status": clause.status,
        "tier": clause.tier,
        "guidance": clause.guidance,
        "sourceSection": clause.source_section,
        "archivedAt": clause.archived_at,
        "updatedAt": clause.updated_at,
    }


@version_router.post("/versions/{version_id}/clauses", status_code=status.HTTP_201_CREATED)
def create_clause(version_id: str, payload: schemas.ClauseCreate, session: Session = Depends(get_session)):
    version = session.get(models.ContractVersion, version_id)
    if not version or version.archived_at is not None:
        raise ApiError(404, "not_found", f"Version {version_id} was not found")
    existing = session.scalars(select(models.Clause).where(models.Clause.version_id == version_id)).all()
    position = max((item.position for item in existing), default=0) + 1
    clause_key = f"{version.contract_id}-C{position:02d}"
    clause = models.Clause(
        id=f"{clause_key}-V{version.sequence:02d}",
        clause_key=clause_key,
        contract_id=version.contract_id,
        version_id=version.id,
        position=position,
        title=payload.title,
        text=payload.text,
        status=payload.status,
        page_number=1,
        tier=payload.tier,
        guidance=payload.guidance,
        source_section=payload.source_section or payload.title,
        updated_at=datetime.now(),
    )
    session.add(clause)
    audit_event(session, "Compliance Reviewer", "Clause Created", "Clause", clause_key, payload.title)
    session.commit()
    return _payload(clause)


@router.patch("/{clause_key}")
def update_clause(clause_key: str, payload: schemas.ClauseUpdate, session: Session = Depends(get_session)):
    clause = _current_clause(session, clause_key)
    if clause.updated_at != payload.updated_at.replace(tzinfo=None):
        raise ApiError(409, "stale_record", "This clause was changed after it was loaded")
    changes = payload.model_dump(exclude={"updated_at"}, exclude_none=True)
    for key, value in changes.items():
        setattr(clause, key, value)
    clause.updated_at = datetime.now()
    audit_event(session, "Compliance Reviewer", "Clause Updated", "Clause", clause_key, ", ".join(sorted(changes)))
    session.commit()
    return _payload(clause)


@router.post("/{clause_key}/archive")
def archive_clause(clause_key: str, session: Session = Depends(get_session)):
    clause = _current_clause(session, clause_key)
    clause.archived_at = datetime.now()
    clause.updated_at = datetime.now()
    audit_event(session, "Compliance Reviewer", "Clause Archived", "Clause", clause_key, clause.title)
    session.commit()
    return _payload(clause)


@router.post("/{clause_key}/restore")
def restore_clause(clause_key: str, session: Session = Depends(get_session)):
    clause = _current_clause(session, clause_key, include_archived=True)
    if clause.archived_at is None:
        raise ApiError(409, "invalid_state", f"Clause {clause_key} is not archived")
    clause.archived_at = None
    clause.updated_at = datetime.now()
    audit_event(session, "Compliance Reviewer", "Clause Restored", "Clause", clause_key, clause.title)
    session.commit()
    return _payload(clause)


@router.get("/{clause_key}/obligations", response_model=schemas.ObligationMappingOut)
def get_clause_obligations(clause_key: str, session: Session = Depends(get_session)):
    clause = _current_clause(session, clause_key, include_archived=True)
    obligation_ids = session.scalars(
        select(models.ClauseObligation.obligation_id)
        .where(models.ClauseObligation.clause_id == clause.id)
        .order_by(models.ClauseObligation.obligation_id)
    ).all()
    return {"clause_id": clause_key, "obligation_ids": obligation_ids}


@router.put("/{clause_key}/obligations", response_model=schemas.ObligationMappingOut)
def replace_clause_obligations(
    clause_key: str,
    payload: schemas.ObligationMappingUpdate,
    session: Session = Depends(get_session),
):
    clause = _current_clause(session, clause_key)
    unique_ids = sorted(set(payload.obligation_ids))
    obligations = session.scalars(select(models.Obligation).where(models.Obligation.id.in_(unique_ids))).all()
    found_ids = {item.id for item in obligations if item.archived_at is None}
    missing = [item for item in unique_ids if item not in found_ids]
    if missing:
        raise ApiError(404, "not_found", "One or more obligations were not found", {"ids": missing})
    session.execute(delete(models.ClauseObligation).where(models.ClauseObligation.clause_id == clause.id))
    session.add_all(models.ClauseObligation(clause_id=clause.id, obligation_id=item) for item in unique_ids)
    clause.updated_at = datetime.now()
    audit_event(session, "Compliance Reviewer", "Clause Obligations Updated", "Clause", clause_key, ", ".join(unique_ids))
    session.commit()
    return {"clause_id": clause_key, "obligation_ids": unique_ids}
