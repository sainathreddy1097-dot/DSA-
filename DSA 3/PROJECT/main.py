"""FastAPI application and typed local API endpoints."""

from contextlib import asynccontextmanager
from datetime import datetime
import json
import math
import os
from typing import Literal

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .algorithms.alignment import analyze_version_diff
from .algorithms.assignment import propose_assignments as run_assignment
from .algorithms.coverage import greedy_set_cover
from .algorithms.search import InvertedIndex
from .algorithms.similarity import build_threshold_graph, connected_components, similarity_matrix
from .database import engine, get_session
from . import models, schemas
from .api.contracts import router as contract_mutation_router
from .api.clauses import router as clause_mutation_router, version_router as version_clause_router
from .api.obligations import router as obligation_router
from .api.playbooks import router as playbook_router
from .api.reviewers import router as reviewer_mutation_router
from .api.versions import router as version_mutation_router
from .errors import ApiError
from .seed import seed_if_empty
from .services.lifecycle import audit_event as _audit, contract_or_404 as _contract_or_404
from .services.access import MUTATION_METHODS, current_actor, require_mutation_role, reset_current_actor, resolve_actor, set_current_actor


ASSIGNMENT_OBJECTIVE = "maximize valid assignments first, then minimize workload/expertise cost"


def _error_payload(code: str, message: str, details=None) -> dict:
    body = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return {"error": body}


def _pagination(items: list, page: int, page_size: int, total: int) -> dict:
    return {"items": items, "page": page, "page_size": page_size, "total": total,
            "total_pages": math.ceil(total / page_size) if total else 0}


def _version_dict(version: models.ContractVersion) -> dict:
    return {"id": version.id, "contract_id": version.contract_id, "label": version.label,
            "version_date": version.version_date, "author": version.author, "note": version.note,
            "sequence": version.sequence}


def _clause_dict(clause: models.Clause, version_label: str | None = None, matched: str | None = None,
                 matched_terms: list[str] | None = None, term_frequency: dict[str, int] | None = None) -> dict:
    label = version_label or clause.version.label
    return {
        "id": clause.clause_key, "clause_key": clause.clause_key, "contract_id": clause.contract_id,
        "version_id": clause.version_id, "title": clause.title, "text": clause.text, "version": label,
        "status": clause.status, "tags": sorted(item.tag.name for item in clause.tags),
        "page_number": clause.page_number, "tier": clause.tier, "guidance": clause.guidance,
        "source_section": clause.source_section, "matched_text": clause.text if matched else None, "match": matched,
        "matched_terms": matched_terms or [], "term_frequency": term_frequency or {},
        "archived_at": clause.archived_at, "updated_at": clause.updated_at,
    }


def _current_version(session: Session, contract: models.Contract) -> models.ContractVersion | None:
    return session.scalar(select(models.ContractVersion).where(
        models.ContractVersion.contract_id == contract.id,
        models.ContractVersion.label == contract.current_version,
        models.ContractVersion.archived_at.is_(None),
    ))


def _current_clauses(session: Session, contract: models.Contract) -> list[models.Clause]:
    version = _current_version(session, contract)
    if version is None:
        return []
    return list(session.scalars(select(models.Clause).where(
                                    models.Clause.version_id == version.id,
                                    models.Clause.archived_at.is_(None),
                                )
                                .options(selectinload(models.Clause.tags).selectinload(models.ClauseTag.tag),
                                         selectinload(models.Clause.obligations).selectinload(models.ClauseObligation.obligation))
                                .order_by(models.Clause.position)))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed_if_empty()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Contract & Compliance Platform API",
        version="1.0.0",
        description="Local-only contract analysis API. Algorithm results are decision support, not legal advice or compliance certification.",
        lifespan=lifespan,
    )
    default_origins = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5181", "http://127.0.0.1:5181",
    ]
    origins = [value.strip() for value in os.getenv("CORS_ORIGINS", ",".join(default_origins)).split(",") if value.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"], allow_headers=["*"])

    @app.middleware("http")
    async def authorize_mutations(request: Request, call_next):
        if request.method not in MUTATION_METHODS or request.url.path in {
            "/clause-search", "/version-comparisons", "/similarity/graph", "/compliance/coverage", "/reviewer-assignments/propose",
        }:
            return await call_next(request)
        try:
            with next(get_session()) as session:
                actor = resolve_actor(session, request.headers.get("X-Actor-Id"))
                require_mutation_role(actor, request.url.path)
        except ApiError as error:
            return JSONResponse(status_code=error.status_code,
                                content=_error_payload(error.code, error.message, error.details))
        token = set_current_actor(actor)
        try:
            return await call_next(request)
        finally:
            reset_current_actor(token)
    app.include_router(contract_mutation_router)
    app.include_router(version_mutation_router)
    app.include_router(clause_mutation_router)
    app.include_router(version_clause_router)
    app.include_router(obligation_router)
    app.include_router(reviewer_mutation_router)
    app.include_router(playbook_router)

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, error: ApiError):
        return JSONResponse(status_code=error.status_code,
                            content=_error_payload(error.code, error.message, error.details))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, error: RequestValidationError):
        details = [{"location": list(item["loc"]), "message": item["msg"], "type": item["type"]}
                   for item in error.errors()]
        return JSONResponse(status_code=422,
                            content=_error_payload("validation_error", "Request validation failed", details))

    @app.get("/health", response_model=schemas.Health, tags=["system"])
    def health(session: Session = Depends(get_session)):
        session.execute(select(1))
        return {"status": "ok", "database": "ok"}

    @app.get("/dashboard/summary", response_model=schemas.DashboardSummary, tags=["dashboard"])
    def dashboard_summary(session: Session = Depends(get_session)):
        contracts = list(session.scalars(select(models.Contract).order_by(models.Contract.last_modified.desc())))
        reviews = list(session.scalars(select(models.Review).order_by(models.Review.due_date).limit(5)))
        contract_names = {contract.id: contract.name for contract in contracts}
        return {
            "portfolio": {
                "total_contracts": len(contracts),
                "compliance_exceptions": sum(item.compliance == "Exception" for item in contracts),
                "needs_review": sum(item.compliance == "Needs Review" for item in contracts),
                "open_reviews": sum(item.status != "Completed" for item in reviews),
            },
            "recent_contracts": contracts[:4],
            "review_queue": [{"id": review.id, "contractId": review.contract_id,
                              "contract": contract_names[review.contract_id], "issue": review.issue,
                              "priority": review.priority, "due": review.due_date.isoformat(), "status": review.status}
                             for review in reviews],
        }

    @app.get("/contracts", response_model=schemas.Page[schemas.ContractSummary], tags=["contracts"])
    def list_contracts(
        page: int = Query(1, ge=1), page_size: int = Query(20, alias="pageSize", ge=1, le=100),
        query: str | None = None, compliance: str | None = None, department: str | None = None,
        review_status: str | None = Query(None, alias="reviewStatus"),
        sort: Literal["name", "lastModified", "risk", "id"] = "lastModified",
        direction: Literal["asc", "desc"] = "desc",
        include_archived: bool = Query(False, alias="includeArchived"),
        session: Session = Depends(get_session),
    ):
        statement = select(models.Contract)
        filters = [] if include_archived else [models.Contract.archived_at.is_(None)]
        if query:
            pattern = f"%{query}%"
            filters.append(or_(models.Contract.id.ilike(pattern), models.Contract.name.ilike(pattern),
                               models.Contract.contract_type.ilike(pattern)))
        if compliance:
            filters.append(models.Contract.compliance == compliance)
        if department:
            filters.append(models.Contract.department == department)
        if review_status:
            filters.append(models.Contract.review_status == review_status)
        if filters:
            statement = statement.where(*filters)
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        sort_columns = {
            "name": models.Contract.name,
            "lastModified": models.Contract.last_modified,
            "risk": models.Contract.risk,
            "id": models.Contract.id,
        }
        order_column = sort_columns[sort]
        order_expression = order_column.asc() if direction == "asc" else order_column.desc()
        items = list(session.scalars(
            statement.order_by(order_expression, models.Contract.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ))
        return _pagination(items, page, page_size, total)

    @app.get("/contracts/{contract_id}", response_model=schemas.ContractDetail, tags=["contracts"])
    def contract_detail(contract_id: str, session: Session = Depends(get_session)):
        contract = _contract_or_404(session, contract_id)
        versions = list(session.scalars(select(models.ContractVersion).where(models.ContractVersion.contract_id == contract_id)
                                        .order_by(models.ContractVersion.sequence.desc())))
        clauses = _current_clauses(session, contract)
        payload = schemas.ContractSummary.model_validate(contract).model_dump()
        payload.update(versions=[_version_dict(item) for item in versions],
                       clauses=[_clause_dict(item, contract.current_version) for item in clauses])
        return payload

    @app.get("/contracts/{contract_id}/clauses", response_model=schemas.Page[schemas.ClauseOut], tags=["clauses"])
    def contract_clauses(
        contract_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, alias="pageSize", ge=1, le=100),
        version_id: str | None = Query(None, alias="versionId"),
        include_archived: bool = Query(False, alias="includeArchived"),
        session: Session = Depends(get_session),
    ):
        contract = _contract_or_404(session, contract_id)
        version = session.get(models.ContractVersion, version_id) if version_id else _current_version(session, contract)
        if not version and not version_id:
            return _pagination([], page, page_size, 0)
        if not version or version.contract_id != contract_id:
            raise ApiError(404, "not_found", f"Version {version_id} was not found for {contract_id}")
        clause_statement = select(models.Clause).where(models.Clause.version_id == version.id)
        if not include_archived:
            clause_statement = clause_statement.where(models.Clause.archived_at.is_(None))
        clauses = list(session.scalars(
            clause_statement.options(selectinload(models.Clause.tags).selectinload(models.ClauseTag.tag))
            .order_by(models.Clause.position)
        ))
        total = len(clauses)
        items = clauses[(page - 1) * page_size:page * page_size]
        return _pagination([_clause_dict(item, version.label) for item in items], page, page_size, total)

    @app.get("/contracts/{contract_id}/versions", response_model=schemas.Page[schemas.VersionOut], tags=["contracts"])
    def contract_versions(
        contract_id: str, page: int = Query(1, ge=1),
        page_size: int = Query(20, alias="pageSize", ge=1, le=100), session: Session = Depends(get_session),
    ):
        _contract_or_404(session, contract_id)
        statement = select(models.ContractVersion).where(
            models.ContractVersion.contract_id == contract_id,
            models.ContractVersion.archived_at.is_(None),
        )
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = list(session.scalars(statement.order_by(models.ContractVersion.sequence.desc())
                                    .offset((page - 1) * page_size).limit(page_size)))
        return _pagination([_version_dict(item) for item in rows], page, page_size, total)

    @app.get("/clauses", response_model=schemas.Page[schemas.ClauseOut], tags=["clauses"])
    def list_clauses(
        page: int = Query(1, ge=1), page_size: int = Query(20, alias="pageSize", ge=1, le=100),
        contract_id: str | None = Query(None, alias="contractId"), status_filter: str | None = Query(None, alias="status"),
        tier: str | None = None, session: Session = Depends(get_session),
    ):
        contracts = list(session.scalars(select(models.Contract).where(
            models.Contract.archived_at.is_(None)
        ).order_by(models.Contract.id)))
        if contract_id:
            contracts = [item for item in contracts if item.id == contract_id]
            if not contracts:
                _contract_or_404(session, contract_id)
        clauses = [clause for contract in contracts for clause in _current_clauses(session, contract)]
        if status_filter:
            clauses = [item for item in clauses if item.status == status_filter]
        if tier:
            clauses = [item for item in clauses if item.tier == tier]
        total = len(clauses)
        sliced = clauses[(page - 1) * page_size:page * page_size]
        versions = {contract.id: contract.current_version for contract in contracts}
        return _pagination([_clause_dict(item, versions[item.contract_id]) for item in sliced], page, page_size, total)

    @app.get("/clauses/search", response_model=schemas.Page[schemas.ClauseOut], tags=["clauses"])
    def search_clauses(
        q: str = Query(min_length=1), mode: str = Query("AND", pattern="^(?i:AND|OR)$"),
        page: int = Query(1, ge=1), page_size: int = Query(20, alias="pageSize", ge=1, le=100),
        contract_id: str | None = Query(None, alias="contractId"), status_filter: str | None = Query(None, alias="status"),
        tier: str | None = None, session: Session = Depends(get_session),
    ):
        q = q.strip()
        if not q:
            raise ApiError(422, "validation_error", "Query must contain at least one non-whitespace character")
        contracts = list(session.scalars(select(models.Contract).where(
            models.Contract.archived_at.is_(None)
        ).order_by(models.Contract.id)))
        clauses = [clause for contract in contracts for clause in _current_clauses(session, contract)]
        by_id = {clause.id: clause for clause in clauses}
        index = InvertedIndex({clause.id: f"{clause.title} {clause.text} {' '.join(item.tag.name for item in clause.tags)}"
                               for clause in clauses})
        hits = [hit for hit in index.search_with_terms(q, mode)
                if (contract_id is None or by_id[hit["id"]].contract_id == contract_id)
                and (status_filter is None or by_id[hit["id"]].status == status_filter)
                and (tier is None or by_id[hit["id"]].tier == tier)]
        total = len(hits)
        versions = {contract.id: contract.current_version for contract in contracts}
        sliced = hits[(page - 1) * page_size:page * page_size]
        return _pagination([_clause_dict(by_id[hit["id"]], versions[by_id[hit["id"]].contract_id], q,
                                         hit["matched_terms"], hit["term_frequency"]) for hit in sliced],
                           page, page_size, total)

    @app.post("/clause-search", response_model=schemas.Page[schemas.ClauseOut], tags=["clauses"])
    def search_clauses_post(payload: schemas.ClauseSearchRequest, session: Session = Depends(get_session)):
        return search_clauses(q=payload.query, mode=payload.mode, page=payload.page, page_size=payload.page_size,
                              contract_id=payload.contract_id, status_filter=payload.status, tier=payload.tier,
                              session=session)

    @app.get("/contracts/{contract_id}/compare", response_model=schemas.ComparisonOut, tags=["analysis"])
    def compare_versions(contract_id: str, base_version_id: str = Query(alias="baseVersionId"),
                         target_version_id: str = Query(alias="targetVersionId"), session: Session = Depends(get_session)):
        _contract_or_404(session, contract_id)
        base = session.get(models.ContractVersion, base_version_id)
        target = session.get(models.ContractVersion, target_version_id)
        if not base or base.contract_id != contract_id or not target or target.contract_id != contract_id:
            raise ApiError(404, "not_found", "One or both comparison versions were not found for this contract")
        def sequence(version_id: str):
            return [{"key": item.clause_key, "text": item.text, "title": item.title}
                    for item in session.scalars(select(models.Clause).where(
                                                    models.Clause.version_id == version_id,
                                                    models.Clause.archived_at.is_(None),
                                                )
                                                .order_by(models.Clause.position))]
        analysis = analyze_version_diff(sequence(base.id), sequence(target.id))
        return {"contract_id": contract_id, "base_version": _version_dict(base), "target_version": _version_dict(target),
                "changes": analysis["changes"], "summary": analysis["summary"]}

    @app.post("/version-comparisons", response_model=schemas.ComparisonOut, tags=["analysis"])
    def compare_versions_post(payload: schemas.VersionComparisonRequest, session: Session = Depends(get_session)):
        return compare_versions(payload.contract_id, payload.base_version_id, payload.target_version_id, session)

    @app.get("/similarity-graph", response_model=schemas.SimilarityGraphOut, tags=["analysis"])
    def similarity_graph(threshold: float = Query(0.35, ge=0, le=1), session: Session = Depends(get_session)):
        contracts = list(session.scalars(select(models.Contract).where(
            models.Contract.archived_at.is_(None)
        ).order_by(models.Contract.id)))
        documents = {contract.id: " ".join(f"{clause.title} {clause.text}" for clause in _current_clauses(session, contract))
                     for contract in contracts}
        ids, matrix = similarity_matrix(documents)
        graph, edges = build_threshold_graph(ids, matrix, threshold)
        components = connected_components(graph)
        cluster_by_id = {node: index + 1 for index, component in enumerate(components) for node in component}
        names = {contract.id: contract.name for contract in contracts}
        return {"threshold": threshold, "nodes": [{"id": item, "name": names[item], "cluster": cluster_by_id[item]}
                                                      for item in ids], "edges": edges, "components": components,
                "isolated_contract_ids": [item for item in ids if not graph.get(item)],
                "compared_pairs": len(ids) * (len(ids) - 1) // 2}

    @app.post("/similarity/graph", response_model=schemas.SimilarityGraphOut, tags=["analysis"])
    def similarity_graph_post(payload: schemas.SimilarityGraphRequest, session: Session = Depends(get_session)):
        return similarity_graph(payload.threshold, session)

    @app.get("/compliance/coverage", response_model=schemas.CoverageOut, tags=["analysis"])
    def compliance_coverage(contract_id: str = Query(alias="contractId"), session: Session = Depends(get_session)):
        contract = _contract_or_404(session, contract_id)
        obligations = list(session.scalars(select(models.Obligation).where(
            models.Obligation.archived_at.is_(None)
        ).order_by(models.Obligation.id)))
        clauses = _current_clauses(session, contract)
        candidates = {clause.clause_key: {link.obligation_id for link in clause.obligations} for clause in clauses}
        result = greedy_set_cover({item.id for item in obligations}, candidates)
        mapped = {item.id: [] for item in obligations}
        for clause in clauses:
            for link in clause.obligations:
                mapped[link.obligation_id].append(clause.clause_key)
        return {
            "contract_id": contract_id,
            "obligations": [{"id": item.id, "name": item.name, "category": item.category,
                             "description": item.description, "clauses": sorted(mapped[item.id])} for item in obligations],
            "selected_clauses": result["selected"], "covered": len(result["covered"]), "total": len(obligations),
            "status": result["coverage_status"],
            "uncovered_obligation_ids": result["uncovered"],
            "steps": result["steps"],
            "clause_coverage": result["clause_coverage"],
            "method": "Greedy Set Cover approximation (not guaranteed optimal)",
        }

    @app.post("/compliance/coverage", response_model=schemas.CoverageOut, tags=["analysis"])
    def compliance_coverage_post(payload: schemas.CoverageRequest, session: Session = Depends(get_session)):
        return compliance_coverage(payload.contract_id, session)

    @app.get("/reviewers", response_model=schemas.Page[schemas.ReviewerOut], tags=["reviewers"])
    def reviewers(
        page: int = Query(1, ge=1), page_size: int = Query(20, alias="pageSize", ge=1, le=100),
        query: str | None = None, expertise: str | None = None, session: Session = Depends(get_session),
    ):
        people = list(session.scalars(select(models.Reviewer).options(
            selectinload(models.Reviewer.expertise).selectinload(models.ReviewerExpertise.expertise)).order_by(models.Reviewer.id)))
        confirmed = dict(session.execute(select(models.Assignment.reviewer_id, func.count()).group_by(models.Assignment.reviewer_id)).all())
        items = [{"id": person.id, "name": person.name, "role": person.role,
                  "assigned": person.workload + confirmed.get(person.id, 0), "capacity": person.capacity,
                  "expertise": sorted(item.expertise.name for item in person.expertise),
                  "active": person.active, "archived_at": person.archived_at,
                  "updated_at": person.updated_at} for person in people]
        if query:
            folded = query.casefold()
            items = [item for item in items if folded in f"{item['id']} {item['name']} {item['role']}".casefold()]
        if expertise:
            folded = expertise.casefold()
            items = [item for item in items if any(skill.casefold() == folded for skill in item["expertise"])]
        total = len(items)
        return _pagination(items[(page - 1) * page_size:page * page_size], page, page_size, total)

    @app.get("/reviewer-assignments", response_model=schemas.Page[schemas.AssignmentOut], tags=["reviewers"])
    def assignments(page: int = Query(1, ge=1), page_size: int = Query(20, alias="pageSize", ge=1, le=100),
                    session: Session = Depends(get_session)):
        total = session.scalar(select(func.count()).select_from(models.Assignment))
        rows = list(session.scalars(select(models.Assignment).order_by(models.Assignment.contract_id)
                                    .offset((page - 1) * page_size).limit(page_size)))
        return _pagination([{"id": row.id, "contract_id": row.contract_id, "reviewer_id": row.reviewer_id,
                             "confidence": row.confidence, "cost": row.cost, "created_at": row.created_at}
                            for row in rows], page, page_size, total)

    @app.post(
        "/reviewer-assignments/propose", response_model=schemas.ProposalOut, tags=["reviewers"],
        description=f"Uses a handwritten min-cost max-flow algorithm. Objective: {ASSIGNMENT_OBJECTIVE}.",
    )
    def propose_reviewer_assignments(payload: schemas.ProposalRequest, session: Session = Depends(get_session)):
        statement = select(models.Contract).outerjoin(models.Assignment).where(models.Assignment.id.is_(None))
        if payload.contract_ids is not None:
            found = set(session.scalars(select(models.Contract.id).where(models.Contract.id.in_(payload.contract_ids))))
            missing = sorted(set(payload.contract_ids) - found)
            if missing:
                raise ApiError(404, "not_found", "One or more contracts were not found", {"contractIds": missing})
            statement = statement.where(models.Contract.id.in_(payload.contract_ids))
        contracts = list(session.scalars(statement.order_by(models.Contract.id)))
        people = list(session.scalars(select(models.Reviewer).where(models.Reviewer.active.is_(True)).options(
            selectinload(models.Reviewer.expertise).selectinload(models.ReviewerExpertise.expertise)).order_by(models.Reviewer.id)))
        confirmed = dict(session.execute(select(models.Assignment.reviewer_id, func.count()).group_by(models.Assignment.reviewer_id)).all())
        tasks = [{"id": item.id, "requiredExpertise": [item.contract_type, item.department]} for item in contracts]
        reviewer_data = [{"id": person.id, "expertise": [item.expertise.name for item in person.expertise],
                          "capacity": person.capacity, "workload": person.workload + confirmed.get(person.id, 0)} for person in people]
        result = run_assignment(tasks, reviewer_data)
        result["objective"] = ASSIGNMENT_OBJECTIVE
        return result

    @app.post("/reviewer-assignments/confirm", response_model=schemas.ConfirmedAssignments,
              status_code=status.HTTP_201_CREATED, tags=["reviewers"])
    def confirm_assignments(payload: schemas.ConfirmAssignments, session: Session = Depends(get_session)):
        contract_ids = [item.contract_id for item in payload.assignments]
        if len(contract_ids) != len(set(contract_ids)):
            raise ApiError(409, "assignment_conflict", "A contract may be assigned only once")
        existing = list(session.scalars(select(models.Assignment.contract_id).where(models.Assignment.contract_id.in_(contract_ids))))
        if existing:
            raise ApiError(409, "assignment_conflict", "One or more contracts are already assigned", {"contractIds": sorted(existing)})
        contracts = {item.id: item for item in session.scalars(select(models.Contract).where(models.Contract.id.in_(contract_ids)))}
        reviewer_ids = {item.reviewer_id for item in payload.assignments}
        people = {item.id: item for item in session.scalars(select(models.Reviewer).where(models.Reviewer.id.in_(reviewer_ids)).options(
            selectinload(models.Reviewer.expertise).selectinload(models.ReviewerExpertise.expertise)))}
        missing_contracts = sorted(set(contract_ids) - contracts.keys())
        missing_reviewers = sorted(reviewer_ids - people.keys())
        if missing_contracts or missing_reviewers:
            raise ApiError(404, "not_found", "Assignment references were not found",
                           {"contractIds": missing_contracts, "reviewerIds": missing_reviewers})
        current_counts = dict(session.execute(select(models.Assignment.reviewer_id, func.count()).group_by(models.Assignment.reviewer_id)).all())
        inactive = sorted(reviewer_id for reviewer_id, person in people.items() if not person.active)
        if inactive:
            raise ApiError(409, "inactive_reviewer", "Inactive reviewers cannot receive assignments",
                           {"reviewerIds": inactive})
        incoming: dict[str, int] = {}
        for item in payload.assignments:
            incoming[item.reviewer_id] = incoming.get(item.reviewer_id, 0) + 1
        exceeded = [reviewer_id for reviewer_id, count in incoming.items()
                    if people[reviewer_id].workload + current_counts.get(reviewer_id, 0) + count > people[reviewer_id].capacity]
        if exceeded:
            raise ApiError(409, "capacity_exceeded", "Reviewer capacity would be exceeded", {"reviewerIds": sorted(exceeded)})
        incompatible = []
        normalized_assignments = []
        for item in payload.assignments:
            contract = contracts[item.contract_id]
            reviewer = people[item.reviewer_id]
            required = {contract.contract_type, contract.department}
            expertise = {link.expertise.name for link in reviewer.expertise}
            if required and not (required & expertise):
                incompatible.append({"contractId": contract.id, "reviewerId": reviewer.id})
                continue
            expertise_gap = len(required - expertise)
            normalized_assignments.append((item, reviewer.workload * 10 + expertise_gap * 100,
                                           "Strong fit" if required <= expertise else "Good fit"))
        if incompatible:
            raise ApiError(409, "incompatible_assignment", "Reviewer expertise does not match the contract",
                           {"assignments": incompatible})
        created = []
        start_count = session.scalar(select(func.count()).select_from(models.Assignment)) or 0
        for index, (item, computed_cost, computed_confidence) in enumerate(normalized_assignments, 1):
            row = models.Assignment(id=f"ASN-{start_count + index:06d}", contract_id=item.contract_id,
                                    reviewer_id=item.reviewer_id, confidence=computed_confidence, cost=computed_cost,
                                    created_at=datetime.now())
            session.add(row)
            _audit(session, "System", "Review Assigned", "Contract", item.contract_id,
                   f"Assigned to {item.reviewer_id}")
            created.append({"id": row.id, "contract_id": row.contract_id, "reviewer_id": row.reviewer_id,
                            "confidence": row.confidence, "cost": row.cost, "created_at": row.created_at})
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise ApiError(409, "assignment_conflict", "One or more contracts are already assigned")
        return {"assignments": created}

    @app.get("/reviews", response_model=schemas.Page[schemas.ReviewOut], tags=["reviews"])
    @app.get("/review-queue", response_model=schemas.Page[schemas.ReviewOut], tags=["reviews"])
    def review_queue(
        page: int = Query(1, ge=1), page_size: int = Query(20, alias="pageSize", ge=1, le=100),
        query: str | None = None, status_filter: str | None = Query(None, alias="status"),
        priority: str | None = None, session: Session = Depends(get_session),
    ):
        statement = select(models.Review)
        if status_filter:
            statement = statement.where(models.Review.status == status_filter)
        if priority:
            statement = statement.where(models.Review.priority == priority)
        if query:
            pattern = f"%{query}%"
            statement = statement.join(models.Contract).where(or_(models.Review.issue.ilike(pattern), models.Contract.name.ilike(pattern)))
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = list(session.scalars(statement.order_by(models.Review.due_date, models.Review.id)
                                    .offset((page - 1) * page_size).limit(page_size)))
        contracts = {item.id: item.name for item in session.scalars(select(models.Contract))}
        people = {item.id: item.name for item in session.scalars(select(models.Reviewer))}
        items = [{"id": row.id, "contract_id": row.contract_id, "contract": contracts[row.contract_id],
                  "reviewer_id": row.reviewer_id, "reviewer": people.get(row.reviewer_id, "Unassigned"),
                  "priority": row.priority, "issue": row.issue, "due": row.due_date,
                  "status": row.status, "updated_at": row.updated_at} for row in rows]
        return _pagination(items, page, page_size, total)

    @app.patch("/reviews/{review_id}", response_model=schemas.ReviewOut, tags=["reviews"])
    @app.patch("/review-queue/{review_id}", response_model=schemas.ReviewOut, tags=["reviews"])
    def update_review(review_id: str, payload: schemas.ReviewStatusUpdate, session: Session = Depends(get_session)):
        review = session.get(models.Review, review_id)
        if not review:
            raise ApiError(404, "not_found", f"Review {review_id} was not found")
        review.status = payload.status
        review.updated_at = datetime.now()
        _audit(session, "Compliance Reviewer", "Review Status Changed", "Review", review.id, payload.status)
        session.commit()
        contract = session.get(models.Contract, review.contract_id)
        reviewer = session.get(models.Reviewer, review.reviewer_id) if review.reviewer_id else None
        return {"id": review.id, "contract_id": review.contract_id, "contract": contract.name,
                "reviewer_id": review.reviewer_id, "reviewer": reviewer.name if reviewer else "Unassigned",
                "priority": review.priority, "issue": review.issue, "due": review.due_date,
                "status": review.status, "updated_at": review.updated_at}

    @app.post("/reviews/{review_id}/decision", response_model=schemas.DecisionOut,
              status_code=status.HTTP_201_CREATED, tags=["reviews"])
    @app.post("/reviews/{review_id}/decisions", response_model=schemas.DecisionOut,
              status_code=status.HTTP_201_CREATED, tags=["reviews"])
    def create_decision(review_id: str, payload: schemas.DecisionCreate, session: Session = Depends(get_session)):
        review = session.get(models.Review, review_id)
        if not review:
            raise ApiError(404, "not_found", f"Review {review_id} was not found")
        if session.scalar(select(models.ReviewDecision).where(models.ReviewDecision.review_id == review_id)):
            raise ApiError(409, "decision_conflict", "A decision already exists for this review")
        number = (session.scalar(select(func.count()).select_from(models.ReviewDecision)) or 0) + 1
        actor = current_actor()
        decision = models.ReviewDecision(id=f"DEC-{number:06d}", review_id=review_id,
                                         decision=payload.decision, notes=payload.notes,
                                          decided_by=actor.name if actor else payload.decided_by, decided_at=datetime.now())
        session.add(decision)
        review.status = "Completed" if payload.decision in {"Approved", "Rejected"} else "Needs Clarification"
        review.updated_at = decision.decided_at
        _audit(session, decision.decided_by, "Review Decision", "Review", review_id, payload.decision,
               "Approved" if payload.decision == "Approved" else "Completed")
        session.commit()
        return decision

    @app.get("/reviews/{review_id}/decisions", response_model=schemas.Page[schemas.DecisionOut], tags=["reviews"])
    def list_decisions(
        review_id: str, page: int = Query(1, ge=1),
        page_size: int = Query(20, alias="pageSize", ge=1, le=100), session: Session = Depends(get_session),
    ):
        if not session.get(models.Review, review_id):
            raise ApiError(404, "not_found", f"Review {review_id} was not found")
        statement = select(models.ReviewDecision).where(models.ReviewDecision.review_id == review_id)
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = list(session.scalars(statement.order_by(models.ReviewDecision.decided_at.desc())
                                    .offset((page - 1) * page_size).limit(page_size)))
        return _pagination(rows, page, page_size, total)

    @app.get("/audit-events", response_model=schemas.Page[schemas.AuditEventOut], tags=["audit"])
    def audit_events(
        page: int = Query(1, ge=1), page_size: int = Query(20, alias="pageSize", ge=1, le=100),
        query: str | None = None, status_filter: str | None = Query(None, alias="status"),
        session: Session = Depends(get_session),
    ):
        statement = select(models.AuditEvent)
        if query:
            pattern = f"%{query}%"
            statement = statement.where(or_(models.AuditEvent.actor.ilike(pattern), models.AuditEvent.action.ilike(pattern),
                                             models.AuditEvent.entity_id.ilike(pattern), models.AuditEvent.detail.ilike(pattern)))
        if status_filter:
            statement = statement.where(models.AuditEvent.status == status_filter)
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = list(session.scalars(statement.order_by(models.AuditEvent.occurred_at.desc(), models.AuditEvent.id.desc())
                                    .offset((page - 1) * page_size).limit(page_size)))
        items = [{"id": row.id, "timestamp": row.occurred_at, "user": row.actor, "actor_id": row.actor_id,
                  "actor_role": row.actor_role, "action": row.action,
                  "entity": row.entity_id, "entity_type": row.entity_type, "detail": row.detail,
                  "status": row.status} for row in rows]
        return _pagination(items, page, page_size, total)

    @app.get("/settings", response_model=schemas.SettingsOut, tags=["settings"])
    def get_settings(session: Session = Depends(get_session)):
        row = session.get(models.Setting, "workspace")
        return json.loads(row.value_json)

    @app.put("/settings", response_model=schemas.SettingsOut, tags=["settings"])
    def update_settings(payload: schemas.SettingsUpdate, session: Session = Depends(get_session)):
        row = session.get(models.Setting, "workspace")
        values = json.loads(row.value_json)
        updates = payload.model_dump(by_alias=True, exclude_none=True)
        values.update(updates)
        row.value_json = json.dumps(values, sort_keys=True)
        _audit(session, values["displayName"], "Settings Updated", "Settings", "workspace",
               ", ".join(sorted(updates)) or "No changes")
        session.commit()
        return values

    return app


app = create_app()
