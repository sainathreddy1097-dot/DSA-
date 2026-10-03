"""Contract mutation routes."""

import csv
from datetime import date, datetime, timedelta
import json
from io import StringIO

from fastapi import APIRouter, Depends, File, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session
from ..errors import ApiError
from ..services.identifiers import next_identifier
from ..services.lifecycle import (
    archive_contract,
    audit_event,
    check_concurrency,
    contract_or_404,
    ensure_approval_has_no_high_risk_findings,
    restore_contract,
)
from .versions import _create_version


router = APIRouter(prefix="/contracts", tags=["contracts"])

MAX_DATASET_BYTES = 5 * 1024 * 1024


def _dataset_value(record: dict, *keys: str, default: str = ""):
    normalized = {"".join(character for character in str(key).lower() if character.isalnum()): value for key, value in record.items()}
    for key in keys:
        value = normalized.get("".join(character for character in key.lower() if character.isalnum()))
        if value is not None and str(value).strip():
            return value
    return default


def _dataset_records(filename: str, content: bytes) -> list[dict]:
    if len(content) > MAX_DATASET_BYTES:
        raise ApiError(413, "dataset_too_large", "Dataset files must be 5 MB or smaller")
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in {"csv", "json"}:
        raise ApiError(422, "unsupported_dataset", "Upload a .csv or .json dataset file")
    try:
        text = content.decode("utf-8-sig")
        if suffix == "csv":
            records = list(csv.DictReader(StringIO(text)))
        else:
            parsed = json.loads(text)
            records = parsed.get("contracts") if isinstance(parsed, dict) else parsed
    except (UnicodeDecodeError, csv.Error, json.JSONDecodeError) as error:
        raise ApiError(422, "invalid_dataset", "The dataset could not be read as UTF-8 CSV or JSON") from error
    if not isinstance(records, list) or not records:
        raise ApiError(422, "invalid_dataset", "Dataset must contain a non-empty list of contract records")
    if len(records) > 200:
        raise ApiError(422, "dataset_too_large", "Dataset imports are limited to 200 contract records")
    if not all(isinstance(record, dict) for record in records):
        raise ApiError(422, "invalid_dataset", "Each dataset record must be an object")
    return records


def _dataset_contract(record: dict, row_number: int) -> tuple[schemas.ContractCreate, list[dict], str, str, str]:
    today = date.today()
    effective_date = _dataset_value(record, "effectiveDate", "effective_date", "filingDate", "filing_date", "date", default=today.isoformat())
    expiry_date = _dataset_value(record, "expiryDate", "expiry_date", default=(today + timedelta(days=365)).isoformat())
    clauses = record.get("clauses", [])
    if clauses and (not isinstance(clauses, list) or not all(isinstance(item, dict) for item in clauses)):
        raise ApiError(422, "invalid_dataset", f"Row {row_number}: clauses must be a JSON array of objects")
    values = {
        "id": _dataset_value(record, "id", "contractId", "contract_id") or None,
        "name": _dataset_value(record, "name", "contractName", "contract_name", "title", "documentName", "document_name"),
        "type": _dataset_value(record, "type", "contractType", "contract_type", "category", default="Imported dataset"),
        "owner": _dataset_value(record, "owner", default="Dataset Import"),
        "department": _dataset_value(record, "department", default="Legal"),
        "compliance": _dataset_value(record, "compliance", default="Needs Review"),
        "reviewStatus": _dataset_value(record, "reviewStatus", "review_status", default="Pending"),
        "effectiveDate": effective_date,
        "expiryDate": expiry_date,
        "risk": _dataset_value(record, "risk", default="Medium"),
        "counterparty": _dataset_value(record, "counterparty", "party", default=""),
        "jurisdiction": _dataset_value(record, "jurisdiction", "governingLaw", "governing_law", default=""),
        "description": _dataset_value(record, "description", "summary", default="Imported from a contract dataset."),
    }
    try:
        payload = schemas.ContractCreate.model_validate(values)
    except ValidationError as error:
        message = "; ".join(item["msg"] for item in error.errors())
        raise ApiError(422, "invalid_dataset", f"Row {row_number}: {message}") from error
    label = str(_dataset_value(record, "versionLabel", "version_label", default="v1.0"))
    author = str(_dataset_value(record, "versionAuthor", "version_author", default=payload.owner))
    note = str(_dataset_value(record, "versionNote", "version_note", default="Imported dataset clauses"))
    return payload, clauses, label, author, note


@router.post("", response_model=schemas.ContractSummary, status_code=status.HTTP_201_CREATED)
def create_contract(payload: schemas.ContractCreate, session: Session = Depends(get_session)):
    contract_id = payload.id or next_identifier(session, models.Contract, "CTR")
    if session.get(models.Contract, contract_id):
        raise ApiError(409, "duplicate_contract", f"Contract {contract_id} already exists")
    values = payload.model_dump(exclude={"id"})
    now = datetime.now()
    contract = models.Contract(
        id=contract_id,
        current_version="Unversioned",
        last_modified=payload.effective_date,
        updated_at=now,
        **values,
    )
    session.add(contract)
    audit_event(session, payload.owner, "Contract Created", "Contract", contract.id, contract.name)
    session.commit()
    session.refresh(contract)
    return contract


@router.post("/import-dataset", response_model=schemas.DatasetImportResult, status_code=status.HTTP_201_CREATED)
async def import_dataset(file: UploadFile = File(), session: Session = Depends(get_session)):
    filename = file.filename or "dataset"
    records = _dataset_records(filename, await file.read())
    imported: list[str] = []
    supplied_ids: set[str] = set()
    try:
        for row_number, record in enumerate(records, 1):
            payload, clauses, label, author, note = _dataset_contract(record, row_number)
            if payload.id and payload.id in supplied_ids:
                raise ApiError(409, "duplicate_contract", f"Row {row_number}: duplicate contract ID {payload.id}")
            contract_id = payload.id or next_identifier(session, models.Contract, "CTR")
            if session.get(models.Contract, contract_id):
                raise ApiError(409, "duplicate_contract", f"Row {row_number}: contract {contract_id} already exists")
            supplied_ids.add(contract_id)
            now = datetime.now()
            contract = models.Contract(id=contract_id, current_version="Unversioned", last_modified=payload.effective_date,
                                       updated_at=now, **payload.model_dump(exclude={"id"}))
            session.add(contract)
            session.flush()
            if clauses:
                _create_version(session, contract, label=label, effective_date=payload.effective_date, author=author,
                                note=note, clause_values=clauses, source_filename=filename, source_media_type=file.content_type)
            audit_event(session, payload.owner, "Dataset Contract Imported", "Contract", contract.id, filename)
            imported.append(contract.id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"imported": len(imported), "contract_ids": imported, "filename": filename}


@router.patch("/{contract_id}", response_model=schemas.ContractSummary)
def update_contract(contract_id: str, payload: schemas.ContractUpdate, session: Session = Depends(get_session)):
    contract = contract_or_404(session, contract_id)
    check_concurrency(contract, payload.updated_at)
    changes = payload.model_dump(exclude={"updated_at"}, exclude_none=True)
    if changes.get("review_status") == "Approved":
        ensure_approval_has_no_high_risk_findings(session, contract.id)
    for key, value in changes.items():
        setattr(contract, key, value)
    contract.updated_at = datetime.now()
    contract.last_modified = contract.updated_at.date()
    audit_event(session, contract.owner, "Contract Updated", "Contract", contract.id, ", ".join(sorted(changes)))
    session.commit()
    session.refresh(contract)
    return contract


@router.post("/{contract_id}/archive", response_model=schemas.ContractSummary)
def archive(contract_id: str, session: Session = Depends(get_session)):
    contract = contract_or_404(session, contract_id)
    archive_contract(session, contract, actor=contract.owner)
    session.commit()
    return contract


@router.post("/{contract_id}/restore", response_model=schemas.ContractSummary)
def restore(contract_id: str, session: Session = Depends(get_session)):
    contract = contract_or_404(session, contract_id, include_archived=True)
    restore_contract(session, contract, actor=contract.owner)
    session.commit()
    return contract


@router.post("/bulk-actions", response_model=schemas.BulkActionResult)
def bulk_action(payload: schemas.ContractBulkAction, session: Session = Depends(get_session)):
    if len(set(payload.contract_ids)) != len(payload.contract_ids):
        raise ApiError(422, "validation_error", "Contract IDs must be unique")
    contracts = [contract_or_404(session, contract_id, include_archived=True) for contract_id in payload.contract_ids]
    for contract in contracts:
        if payload.action == "archive":
            archive_contract(session, contract, actor="Compliance Reviewer", action="Bulk Contract Archive")
        elif payload.action == "restore":
            restore_contract(session, contract, actor="Compliance Reviewer", action="Bulk Contract Restore")
        else:
            contract.compliance = payload.value
            contract.updated_at = datetime.now()
            audit_event(
                session,
                "Compliance Reviewer",
                "Bulk Compliance Updated",
                "Contract",
                contract.id,
                payload.value,
            )
    session.commit()
    return {"affected": len(contracts), "action": payload.action}
