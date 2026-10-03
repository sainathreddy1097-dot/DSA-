"""Contract version creation and local document upload routes."""

from datetime import date, datetime
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session
from ..errors import ApiError
from ..services.ingestion import IngestionError, extract_text, segment_clauses, validate_upload
from ..services.lifecycle import audit_event, contract_or_404


router = APIRouter(tags=["versions"])


def _version_payload(version: models.ContractVersion, clauses: list[models.Clause]) -> dict:
    return {
        "id": version.id,
        "contractId": version.contract_id,
        "label": version.label,
        "date": version.version_date,
        "author": version.author,
        "note": version.note,
        "sequence": version.sequence,
        "sourceFilename": version.source_filename,
        "sourceSha256": version.source_sha256,
        "sourceMediaType": version.source_media_type,
        "updatedAt": version.updated_at,
        "clauses": [
            {
                "id": clause.clause_key,
                "clauseKey": clause.clause_key,
                "title": clause.title,
                "text": clause.text,
                "status": clause.status,
                "tier": clause.tier,
                "position": clause.position,
                "updatedAt": clause.updated_at,
            }
            for clause in clauses
        ],
    }


def _next_sequence(session: Session, contract_id: str) -> int:
    return (session.scalar(select(func.max(models.ContractVersion.sequence)).where(
        models.ContractVersion.contract_id == contract_id
    )) or 0) + 1


def _create_version(
    session: Session,
    contract: models.Contract,
    *,
    label: str,
    effective_date: date,
    author: str,
    note: str,
    clause_values: list[dict],
    source_filename: str | None = None,
    source_sha256: str | None = None,
    source_media_type: str | None = None,
    source_text: str | None = None,
) -> tuple[models.ContractVersion, list[models.Clause]]:
    duplicate_label = session.scalar(select(models.ContractVersion.id).where(
        models.ContractVersion.contract_id == contract.id,
        models.ContractVersion.label == label,
    ))
    if duplicate_label:
        raise ApiError(409, "duplicate_version", f"Version {label} already exists for {contract.id}")
    sequence = _next_sequence(session, contract.id)
    version = models.ContractVersion(
        id=f"VER-{contract.id.removeprefix('CTR-')}-{sequence:02d}",
        contract_id=contract.id,
        label=label,
        version_date=effective_date,
        author=author,
        note=note,
        sequence=sequence,
        source_filename=source_filename,
        source_sha256=source_sha256,
        source_media_type=source_media_type,
        source_text=source_text,
        updated_at=datetime.now(),
    )
    session.add(version)
    clauses: list[models.Clause] = []
    for position, values in enumerate(clause_values, 1):
        clause_key = f"{contract.id}-C{position:02d}"
        clause = models.Clause(
            id=f"{clause_key}-V{sequence:02d}",
            clause_key=clause_key,
            contract_id=contract.id,
            version_id=version.id,
            position=position,
            title=values["title"],
            text=values["text"],
            status=values.get("status", "Needs Review"),
            page_number=values.get("page_number", 1),
            tier=values.get("tier", "Acceptable"),
            guidance=values.get("guidance", "Review imported wording against applicable obligations."),
            source_section=values.get("source_section", values["title"]),
            updated_at=datetime.now(),
        )
        clauses.append(clause)
        session.add(clause)
    contract.current_version = label
    contract.last_modified = effective_date
    contract.updated_at = datetime.now()
    audit_event(session, author, "Version Created", "ContractVersion", version.id, f"{contract.id} {label}")
    return version, clauses


@router.post("/contracts/{contract_id}/versions", status_code=status.HTTP_201_CREATED)
def create_structured_version(
    contract_id: str,
    payload: schemas.VersionCreate,
    session: Session = Depends(get_session),
):
    contract = contract_or_404(session, contract_id)
    version, clauses = _create_version(
        session,
        contract,
        label=payload.label,
        effective_date=payload.effective_date,
        author=payload.author,
        note=payload.note,
        clause_values=[item.model_dump() for item in payload.clauses],
    )
    session.commit()
    return _version_payload(version, clauses)


@router.post("/contracts/{contract_id}/versions/upload", status_code=status.HTTP_201_CREATED)
async def upload_version(
    contract_id: str,
    label: str = Form(min_length=1, max_length=20),
    effective_date: date = Form(alias="effectiveDate"),
    author: str = Form(min_length=2, max_length=100),
    note: str = Form(default="Imported local document", max_length=300),
    file: UploadFile = File(),
    session: Session = Depends(get_session),
):
    contract = contract_or_404(session, contract_id)
    try:
        document = validate_upload(file.filename or "document", await file.read())
        text = extract_text(document)
    except IngestionError as error:
        raise ApiError(422, error.code, str(error)) from error
    duplicate = session.scalar(select(models.ContractVersion.id).where(
        models.ContractVersion.contract_id == contract_id,
        models.ContractVersion.source_sha256 == document.sha256,
    ))
    if duplicate:
        raise ApiError(409, "duplicate_document", "This document has already been imported for the contract")
    segments = segment_clauses(text)
    upload_dir = Path(os.getenv("UPLOAD_DIR", Path(__file__).resolve().parents[2] / "data" / "uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_path = upload_dir / f"{contract.id}-{document.sha256}{document.extension}"
    created_file = not storage_path.exists()
    if created_file:
        storage_path.write_bytes(document.content)
    try:
        version, clauses = _create_version(
            session,
            contract,
            label=label,
            effective_date=effective_date,
            author=author,
            note=note,
            clause_values=[{
                "title": segment.title,
                "text": segment.text,
                "source_section": segment.title,
            } for segment in segments],
            source_filename=document.filename,
            source_sha256=document.sha256,
            source_media_type=document.media_type,
            source_text=text,
        )
        session.commit()
    except Exception:
        session.rollback()
        if created_file and storage_path.exists():
            storage_path.unlink()
        raise
    return _version_payload(version, clauses)
