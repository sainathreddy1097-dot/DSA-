"""Deterministic database creation, seed, reset, and count commands."""

from datetime import date, datetime, time, timedelta
import argparse
import json
from pathlib import Path

from sqlalchemy import func, select

from . import models
from . import database
from .migrations import run_migrations


CONTRACTS = [
    ("Master Services Agreement", "Vendor Agreement", "v3.2", "Maya Rao", "Procurement", "Compliant", "Approved", "Low"),
    ("Data Processing Agreement", "Privacy", "v2.4", "Arjun Mehta", "Legal", "Needs Review", "Reviewing", "Medium"),
    ("Supplier Framework Agreement", "Procurement", "v5.1", "Neha Iyer", "Operations", "Exception", "Action Required", "High"),
    ("Cloud Hosting Addendum", "Technology", "v1.8", "Rohan Das", "IT", "Compliant", "Approved", "Low"),
    ("Global Distribution Agreement", "Commercial", "v4.0", "Sara Khan", "Sales", "Needs Review", "Pending", "Medium"),
    ("Employee Data Addendum", "Privacy", "v2.1", "Vikram Sen", "People", "Compliant", "Approved", "Low"),
    ("Facilities Services Contract", "Vendor Agreement", "v3.7", "Diya Patel", "Operations", "Exception", "Action Required", "High"),
    ("Marketing Agency Retainer", "Commercial", "v1.5", "Kabir Jain", "Marketing", "Compliant", "Reviewing", "Medium"),
    ("Software Licence Agreement", "Technology", "v2.6", "Isha Kapoor", "IT", "Needs Review", "Pending", "Medium"),
    ("Logistics Services Agreement", "Procurement", "v4.3", "Aman Gupta", "Operations", "Compliant", "Approved", "Low"),
    ("Research Collaboration Terms", "Research", "v1.9", "Leena Bose", "Legal", "Needs Review", "Reviewing", "Medium"),
    ("Payment Processing Addendum", "Financial", "v3.4", "Nikhil Shah", "Finance", "Exception", "Action Required", "High"),
]

CLAUSE_DEFINITIONS = [
    ("Data Protection", "Personal information shall be processed only for documented business purposes and protected by appropriate safeguards.", "Privacy", "Preferred"),
    ("Retention", "Records shall be retained for {days} days following termination and then securely deleted.", "Retention", "Acceptable"),
    ("Breach Notification", "A confirmed security incident must be reported within {hours} hours of discovery.", "Security", "Preferred"),
    ("Access Control", "Access is restricted to authorised personnel with a documented business need.", "Access Control", "Preferred"),
    ("Audit Rights", "Relevant compliance records shall be available for annual inspection with {notice} business days notice.", "Audit", "Fallback"),
    ("Subprocessor Notice", "The supplier shall provide advance notice before appointing a material subprocessor.", "Vendor Risk", "Acceptable"),
    ("Confidentiality", "Confidential information shall not be disclosed except as expressly permitted by this agreement.", "Governance", "Preferred"),
    ("Termination Assistance", "The supplier shall provide orderly transition assistance following termination.", "Operations", "Acceptable"),
]

LEGACY_CLAUSE = (
    "Legacy Paper Notice",
    "Formal notices shall be delivered by registered post to the address stated in the agreement.",
    "Governance",
    "Fallback",
)

DOMAIN_CONTEXTS = {
    "Vendor Agreement": "supplier sourcing purchase delivery quality inspection procurement vendor performance service levels",
    "Procurement": "supplier sourcing purchase delivery quality inspection procurement vendor performance service levels",
    "Privacy": "personal data controller processor privacy consent subject rights minimisation retention lawful processing",
    "Technology": "cloud software hosting uptime availability cybersecurity encryption recovery platform technical support",
    "Commercial": "sales distribution territory pricing revenue campaign customer market brand promotion commercial",
    "Research": "research collaboration publication intellectual property laboratory findings academic authorship innovation",
    "Financial": "payment transaction settlement chargeback merchant funds reconciliation banking finance processing",
}

OBLIGATIONS = [
    ("Data purpose limitation", "Privacy"), ("Secure deletion", "Records"),
    ("Incident notification", "Security"), ("Role-based access", "Security"),
    ("Auditability", "Governance"), ("Subprocessor oversight", "Privacy"),
    ("Confidentiality controls", "Governance"), ("Exit assistance", "Operations"),
    ("Data minimisation", "Privacy"), ("Evidence retention", "Records"),
]

REVIEWERS = [
    ("REV-A", "Ananya Sharma", "Senior Legal Reviewer", 7, 10, ["Privacy", "Data Processing", "Legal"]),
    ("REV-B", "Rahul Verma", "Compliance Counsel", 5, 9, ["Procurement", "Vendor Agreement", "Vendor Risk"]),
    ("REV-C", "Priya Nair", "Commercial Reviewer", 8, 10, ["Commercial", "Distribution", "Sales"]),
    ("REV-D", "Dev Malhotra", "Technology Counsel", 4, 8, ["Technology", "Cloud", "Security", "IT"]),
    ("REV-E", "Meera Joshi", "Privacy Specialist", 6, 10, ["Privacy", "Employment", "People", "Financial"]),
    ("REV-F", "Karan Bedi", "Contract Analyst", 3, 8, ["Operations", "Facilities", "Research"]),
]

DEFAULT_SETTINGS = {
    "displayName": "Compliance Reviewer", "role": "Review Team",
    "email": "reviewer@contract-intelligence.local", "defaultQueueSort": "Priority, then due date",
    "versionComparison": "Side-by-side", "showClauseComplianceTags": True,
    "confirmStatusChanges": True, "newAssignments": True, "dueDateReminders": True,
    "complianceExceptions": True, "weeklySummary": False,
}


def _older_version(label: str, offset: int) -> str:
    major, minor = (int(part) for part in label.removeprefix("v").split("."))
    minor -= offset
    while minor < 0:
        major -= 1
        minor += 10
    return f"v{major}.{minor}"


def initialize_database() -> None:
    run_migrations()


def ensure_baseline_playbook(session) -> None:
    if session.get(models.Playbook, "PBK-000001"):
        return
    playbook = models.Playbook(id="PBK-000001", name="Privacy Baseline", version="2026.1", contract_type="Privacy", status="Active")
    playbook.rules.append(models.PlaybookRule(id="PBK-000001-R01", clause_category="Breach Notification",
        required_phrases_json=json.dumps(["within 72 hours"]), prohibited_phrases_json="[]", risk="High",
        remediation="Require a 72-hour notification commitment."))
    session.add(playbook)


def ensure_local_actors(session) -> None:
    for actor_id, name, role in [
        ("USR-001", "Asha Menon", "Administrator"),
        ("USR-002", "Rahul Verma", "Legal Reviewer"),
        ("USR-003", "Priya Nair", "Read Only"),
    ]:
        if not session.get(models.User, actor_id):
            session.add(models.User(id=actor_id, name=name, role=role, active=True))


def seed_database() -> None:
    initialize_database()
    with database.SessionLocal() as session:
        if session.scalar(select(func.count()).select_from(models.Contract)):
            return

        tag_names = sorted({definition[2] for definition in CLAUSE_DEFINITIONS})
        tags = {name: models.Tag(id=f"TAG-{index:02d}", name=name) for index, name in enumerate(tag_names, 1)}
        session.add_all(tags.values())
        obligations = [
            models.Obligation(id=f"OBL-{index:02d}", name=name, category=category, description=f"Required control: {name}.")
            for index, (name, category) in enumerate(OBLIGATIONS, 1)
        ]
        session.add_all(obligations)

        authors = ["Maya Rao", "Arjun Mehta", "Ananya Sharma", "Priya Nair"]
        current_clause_ids: dict[str, list[str]] = {}
        for contract_index, data in enumerate(CONTRACTS, 1):
            name, contract_type, current_label, owner, department, compliance, review_status, risk = data
            contract_id = f"CTR-{contract_index:03d}"
            modified = date(2026, 9, 13) - timedelta(days=(contract_index - 1) * 3)
            contract = models.Contract(
                id=contract_id, name=name, contract_type=contract_type, current_version=current_label,
                last_modified=modified, owner=owner, department=department, compliance=compliance,
                review_status=review_status, effective_date=date(2025, 10, 1) + timedelta(days=contract_index * 20),
                expiry_date=date(2028, 1, 1) + timedelta(days=contract_index * 30), risk=risk,
            )
            session.add(contract)
            version_count = 2 + ((contract_index - 1) % 3)
            current_clause_ids[contract_id] = []
            for offset in range(version_count):
                label = _older_version(current_label, offset)
                version_id = f"VER-{contract_index:03d}-{version_count - offset:02d}"
                version = models.ContractVersion(
                    id=version_id, contract_id=contract_id, label=label,
                    version_date=modified - timedelta(days=offset * 45), author=authors[(contract_index + offset) % len(authors)],
                    note="Current approved draft" if offset == 0 else f"Deterministic revision {version_count - offset}",
                    sequence=version_count - offset,
                )
                session.add(version)
                if offset == 0:
                    version_definitions = CLAUSE_DEFINITIONS
                elif offset == 1:
                    version_definitions = [*CLAUSE_DEFINITIONS[:7], LEGACY_CLAUSE]
                else:
                    version_definitions = [*CLAUSE_DEFINITIONS[:6], LEGACY_CLAUSE]
                domain_context = DOMAIN_CONTEXTS.get(contract_type, "contract governance obligations evidence review controls")
                for clause_index, (title, template, tag_name, tier) in enumerate(version_definitions, 1):
                    stable_clause_number = 9 if title == LEGACY_CLAUSE[0] else clause_index
                    clause_key = f"{contract_id}-C{stable_clause_number:02d}"
                    clause_id = f"{clause_key}-V{version_count - offset:02d}"
                    base_text = template.format(days=90 + offset * 30, hours=48 + offset * 12, notice=10 + offset * 5)
                    text = f"{base_text} Domain context: {domain_context}. Agreement context: {name}."
                    clause = models.Clause(
                        id=clause_id, clause_key=clause_key, contract_id=contract_id, version_id=version_id,
                        position=clause_index, title=title, text=text,
                        status="Needs Review" if compliance != "Compliant" and clause_index in {2, 5} else "Compliant",
                        page_number=3 + clause_index * 2, tier=tier,
                        guidance=f"Verify {title.lower()} wording against the applicable obligation.",
                        source_section=f"Section {clause_index}: {title}",
                    )
                    clause.tags.append(models.ClauseTag(tag=tags[tag_name]))
                    if offset == 0:
                        current_clause_ids[contract_id].append(clause_id)
                    session.add(clause)

        session.flush()
        for clause_ids in current_clause_ids.values():
            for index, obligation in enumerate(obligations):
                clause_id = clause_ids[index % len(clause_ids)]
                session.add(models.ClauseObligation(clause_id=clause_id, obligation_id=obligation.id))

        expertise_names = sorted({name for reviewer in REVIEWERS for name in reviewer[5]})
        expertise = {name: models.Expertise(id=f"EXP-{index:02d}", name=name) for index, name in enumerate(expertise_names, 1)}
        session.add_all(expertise.values())
        ensure_local_actors(session)
        ensure_baseline_playbook(session)
        for reviewer_id, name, role, workload, capacity, skills in REVIEWERS:
            reviewer = models.Reviewer(id=reviewer_id, name=name, role=role, workload=workload, capacity=capacity)
            reviewer.expertise.extend(models.ReviewerExpertise(expertise=expertise[skill]) for skill in skills)
            session.add(reviewer)

        review_rows = [
            ("RVW-001", "CTR-003", "REV-A", "Urgent", "Breach notification period exceeds policy", date(2026, 9, 17), "Pending"),
            ("RVW-002", "CTR-002", "REV-E", "High", "Retention clause changed in current version", date(2026, 9, 18), "Needs Clarification"),
            ("RVW-003", "CTR-005", "REV-C", "High", "Territory exclusion requires approval", date(2026, 9, 19), "Pending"),
            ("RVW-004", "CTR-008", "REV-C", "Normal", "Annual review checkpoint", date(2026, 9, 20), "Pending"),
            ("RVW-005", "CTR-004", "REV-D", "Normal", "Security schedule reviewed", date(2026, 9, 16), "Completed"),
        ]
        for row in review_rows:
            review_id, contract_id, reviewer_id, priority, issue, due, status = row
            created = datetime.combine(date(2026, 9, 10), time(9, 0))
            session.add(models.Review(id=review_id, contract_id=contract_id, reviewer_id=reviewer_id, priority=priority,
                                      issue=issue, due_date=due, status=status, created_at=created, updated_at=created))

        for index, (actor, action, entity, detail, status) in enumerate([
            ("Ananya Sharma", "Version Compared", "CTR-002", "v2.3 to v2.4", "Completed"),
            ("Rahul Verma", "Clause Reviewed", "CTR-005", "Clause 7.2", "Approved"),
            ("System", "Compliance Check", "CTR-001", "v3.2", "Flagged"),
            ("Priya Nair", "Queue Reviewed", "CTR-003", "v5.1", "Completed"),
            ("Dev Malhotra", "Contract Updated", "CTR-004", "v1.7 to v1.8", "Completed"),
            ("Meera Joshi", "Exception Resolved", "CTR-006", "Clause 5.6", "Approved"),
        ], 1):
            session.add(models.AuditEvent(id=f"AUD-{index:06d}", occurred_at=datetime(2026, 9, 16, 10, 0) + timedelta(minutes=index),
                                          actor=actor, action=action, entity_type="Contract", entity_id=entity,
                                          detail=detail, status=status))
        session.add(models.Setting(key="workspace", value_json=json.dumps(DEFAULT_SETTINGS, sort_keys=True)))
        session.commit()


def reset_and_seed(database_url: str | None = None) -> dict[str, int]:
    target_url = database_url or database.current_database_url()
    database.configure_database(target_url)
    if target_url.startswith("sqlite:///"):
        database.engine.dispose()
        database_path = Path(target_url.removeprefix("sqlite:///"))
        if str(database_path) != ":memory:" and database_path.exists():
            database_path.unlink()
        database.configure_database(target_url)
    else:
        from .database import Base

        Base.metadata.drop_all(database.engine)
    run_migrations(target_url)
    seed_database()
    return database_counts()


def seed_if_empty() -> None:
    initialize_database()
    with database.SessionLocal() as session:
        empty = not session.scalar(select(func.count()).select_from(models.Contract))
    if empty:
        seed_database()
        return
    with database.SessionLocal() as session:
        ensure_baseline_playbook(session)
        ensure_local_actors(session)
        session.commit()


def database_counts() -> dict[str, int]:
    with database.SessionLocal() as session:
        return {
            "contracts": session.scalar(select(func.count()).select_from(models.Contract)),
            "versions": session.scalar(select(func.count()).select_from(models.ContractVersion)),
            "clauses": session.scalar(select(func.count()).select_from(models.Clause)),
            "obligations": session.scalar(select(func.count()).select_from(models.Obligation)),
            "reviewers": session.scalar(select(func.count()).select_from(models.Reviewer)),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the deterministic local database")
    parser.add_argument("command", choices=["seed", "reset", "counts"])
    args = parser.parse_args()
    if args.command == "reset":
        reset_and_seed()
    elif args.command == "seed":
        seed_if_empty()
    print(json.dumps(database_counts(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
