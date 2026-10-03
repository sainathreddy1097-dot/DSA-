"""Versioned deterministic compliance playbook routes."""

from datetime import date, datetime
import json

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_session
from ..errors import ApiError
from ..services.access import current_actor
from ..services.lifecycle import audit_event, contract_or_404


router = APIRouter(tags=["playbooks"])


def _rule_dict(rule: models.PlaybookRule) -> dict:
    return {"id": rule.id, "clause_category": rule.clause_category,
            "required_phrases": json.loads(rule.required_phrases_json),
            "prohibited_phrases": json.loads(rule.prohibited_phrases_json),
            "risk": rule.risk, "remediation": rule.remediation}


def _playbook_dict(playbook: models.Playbook) -> dict:
    return {"id": playbook.id, "name": playbook.name, "version": playbook.version,
            "contract_type": playbook.contract_type, "jurisdiction": playbook.jurisdiction,
            "status": playbook.status, "rules": [_rule_dict(rule) for rule in playbook.rules]}


def _finding_dict(finding: models.Finding) -> dict:
    return {"id": finding.id, "contract_id": finding.contract_id, "version_id": finding.version_id,
            "clause_id": finding.clause_id, "rule_id": finding.rule_id, "status": finding.status,
            "risk": finding.risk, "evidence": finding.evidence, "remediation": finding.remediation,
            "override_notes": finding.override_notes, "overridden_at": finding.overridden_at}


def _next_id(session: Session, prefix: str, model) -> str:
    number = (session.scalar(select(func.count()).select_from(model)) or 0) + sum(isinstance(item, model) for item in session.new) + 1
    return f"{prefix}-{number:06d}"


@router.get("/playbooks", response_model=schemas.Page[schemas.PlaybookOut])
def list_playbooks(session: Session = Depends(get_session)):
    items = list(session.scalars(select(models.Playbook).options(selectinload(models.Playbook.rules)).order_by(models.Playbook.id)))
    return {"items": [_playbook_dict(item) for item in items], "page": 1, "page_size": 100, "total": len(items), "total_pages": 1 if items else 0}


@router.post("/playbooks", response_model=schemas.PlaybookOut, status_code=status.HTTP_201_CREATED)
def create_playbook(payload: schemas.PlaybookCreate, session: Session = Depends(get_session)):
    if session.scalar(select(models.Playbook.id).where(models.Playbook.name == payload.name, models.Playbook.version == payload.version)):
        raise ApiError(409, "duplicate_playbook", f"Playbook {payload.name} {payload.version} already exists")
    playbook = models.Playbook(id=_next_id(session, "PBK", models.Playbook), name=payload.name, version=payload.version,
                               contract_type=payload.contract_type, jurisdiction=payload.jurisdiction, status=payload.status)
    for index, item in enumerate(payload.rules, 1):
        playbook.rules.append(models.PlaybookRule(id=f"{playbook.id}-R{index:02d}", clause_category=item.clause_category,
            required_phrases_json=json.dumps(item.required_phrases), prohibited_phrases_json=json.dumps(item.prohibited_phrases),
            risk=item.risk, remediation=item.remediation))
    session.add(playbook)
    audit_event(session, "Compliance Reviewer", "Playbook Created", "Playbook", playbook.id, f"{playbook.name} {playbook.version}")
    session.commit()
    return _playbook_dict(playbook)


@router.post("/playbooks/{playbook_id}/analyze", response_model=schemas.PlaybookAnalysisOut)
def analyze_playbook(playbook_id: str, payload: schemas.PlaybookAnalysisRequest, session: Session = Depends(get_session)):
    playbook = session.scalar(select(models.Playbook).where(models.Playbook.id == playbook_id).options(selectinload(models.Playbook.rules)))
    if not playbook:
        raise ApiError(404, "not_found", f"Playbook {playbook_id} was not found")
    if playbook.status != "Active":
        raise ApiError(409, "inactive_playbook", "Only active playbooks can be analyzed")
    contract = contract_or_404(session, payload.contract_id)
    if playbook.contract_type and playbook.contract_type.casefold() != contract.contract_type.casefold():
        raise ApiError(409, "inapplicable_playbook", "This playbook does not apply to the contract type")
    if playbook.jurisdiction and playbook.jurisdiction.casefold() != contract.jurisdiction.casefold():
        raise ApiError(409, "inapplicable_playbook", "This playbook does not apply to the contract jurisdiction")
    version = session.scalar(select(models.ContractVersion).where(models.ContractVersion.contract_id == contract.id,
                              models.ContractVersion.label == contract.current_version, models.ContractVersion.archived_at.is_(None)))
    if not version:
        raise ApiError(409, "unversioned_contract", "A contract version is required for playbook analysis")
    clauses = list(session.scalars(select(models.Clause).where(models.Clause.version_id == version.id, models.Clause.archived_at.is_(None))))
    findings: list[models.Finding] = []
    for rule in playbook.rules:
        category = rule.clause_category.casefold()
        clause = next((item for item in clauses if category in f"{item.title} {item.source_section}".casefold()), None)
        text = clause.text.casefold() if clause else ""
        required = json.loads(rule.required_phrases_json)
        prohibited = json.loads(rule.prohibited_phrases_json)
        missing = [phrase for phrase in required if phrase.casefold() not in text]
        forbidden = [phrase for phrase in prohibited if phrase.casefold() in text]
        evidence = (f"Missing required phrases: {', '.join(missing)}" if missing else f"Prohibited phrases found: {', '.join(forbidden)}") if (not clause or missing or forbidden) else "Deterministic phrase checks passed"
        finding = session.scalar(select(models.Finding).where(models.Finding.version_id == version.id, models.Finding.rule_id == rule.id))
        if not finding:
            finding = models.Finding(id=_next_id(session, "FND", models.Finding), contract_id=contract.id, version_id=version.id, rule_id=rule.id,
                                     clause_id=clause.id if clause else None, status="Compliant", risk=rule.risk, evidence=evidence, remediation=rule.remediation)
            session.add(finding)
        if finding.status != "Exception":
            finding.clause_id, finding.risk, finding.evidence, finding.remediation = (clause.id if clause else None), rule.risk, evidence, rule.remediation
            finding.status = "Compliant" if clause and not missing and not forbidden else "Needs Review"
            finding.updated_at = datetime.now()
        if finding.status == "Needs Review" and rule.risk == "High":
            issue = f"{playbook.name} {playbook.version}: {rule.clause_category} deviation"
            existing = session.scalar(select(models.Review).where(models.Review.contract_id == contract.id, models.Review.issue == issue,
                                      models.Review.status != "Completed"))
            if not existing:
                now = datetime.now()
                session.add(models.Review(id=_next_id(session, "RVW", models.Review), contract_id=contract.id, reviewer_id=None,
                    priority="High", issue=issue, due_date=date.today(), status="Pending", created_at=now, updated_at=now))
        findings.append(finding)
    audit_event(session, "Compliance Reviewer", "Playbook Analyzed", "Contract", contract.id, f"{playbook.name} {playbook.version}")
    session.commit()
    return {"playbook_id": playbook.id, "contract_id": contract.id, "version_id": version.id, "findings": [_finding_dict(item) for item in findings]}


@router.get("/contracts/{contract_id}/findings", response_model=schemas.Page[schemas.FindingOut])
def list_findings(contract_id: str, session: Session = Depends(get_session)):
    contract_or_404(session, contract_id)
    items = list(session.scalars(select(models.Finding).where(models.Finding.contract_id == contract_id).order_by(models.Finding.id)))
    return {"items": [_finding_dict(item) for item in items], "page": 1, "page_size": 100, "total": len(items), "total_pages": 1 if items else 0}


@router.post("/findings/{finding_id}/override", response_model=schemas.FindingOut)
def override_finding(finding_id: str, payload: schemas.FindingOverride, session: Session = Depends(get_session)):
    finding = session.get(models.Finding, finding_id)
    if not finding:
        raise ApiError(404, "not_found", f"Finding {finding_id} was not found")
    actor = current_actor()
    if not actor or actor.role not in {"Administrator", "Legal Reviewer"}:
        raise ApiError(403, "permission_denied", "Only a legal reviewer can record an exception")
    finding.status, finding.override_notes, finding.overridden_at, finding.updated_at = "Exception", payload.notes, datetime.now(), datetime.now()
    audit_event(session, actor.name, "Playbook Finding Overridden", "Finding", finding.id, payload.notes, "Approved")
    session.commit()
    return _finding_dict(finding)