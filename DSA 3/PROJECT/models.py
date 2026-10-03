"""Normalized database model for the local contract workspace."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    contract_type: Mapped[str] = mapped_column(String(80))
    current_version: Mapped[str] = mapped_column(String(20))
    last_modified: Mapped[date] = mapped_column(Date)
    owner: Mapped[str] = mapped_column(String(100))
    department: Mapped[str] = mapped_column(String(80), index=True)
    compliance: Mapped[str] = mapped_column(String(30), index=True)
    review_status: Mapped[str] = mapped_column(String(30), index=True)
    effective_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    risk: Mapped[str] = mapped_column(String(10))
    counterparty: Mapped[str] = mapped_column(String(200), default="")
    jurisdiction: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    versions: Mapped[list["ContractVersion"]] = relationship(back_populates="contract", cascade="all, delete-orphan")


class ContractVersion(Base):
    __tablename__ = "contract_versions"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    label: Mapped[str] = mapped_column(String(20))
    version_date: Mapped[date] = mapped_column(Date)
    author: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(String(300))
    sequence: Mapped[int] = mapped_column(Integer)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    contract: Mapped[Contract] = relationship(back_populates="versions")
    clauses: Mapped[list["Clause"]] = relationship(back_populates="version", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("contract_id", "label"),)


class Clause(Base):
    __tablename__ = "clauses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    clause_key: Mapped[str] = mapped_column(String(32), index=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("contract_versions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    tier: Mapped[str] = mapped_column(String(20), index=True)
    guidance: Mapped[str] = mapped_column(Text)
    source_section: Mapped[str] = mapped_column(String(160))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    version: Mapped[ContractVersion] = relationship(back_populates="clauses")
    tags: Mapped[list["ClauseTag"]] = relationship(back_populates="clause", cascade="all, delete-orphan")
    obligations: Mapped[list["ClauseObligation"]] = relationship(back_populates="clause", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("version_id", "clause_key"),)


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class ClauseTag(Base):
    __tablename__ = "clause_tags"
    clause_id: Mapped[str] = mapped_column(ForeignKey("clauses.id"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id"), primary_key=True)
    clause: Mapped[Clause] = relationship(back_populates="tags")
    tag: Mapped[Tag] = relationship()


class Obligation(Base):
    __tablename__ = "obligations"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ClauseObligation(Base):
    __tablename__ = "clause_obligations"
    clause_id: Mapped[str] = mapped_column(ForeignKey("clauses.id"), primary_key=True)
    obligation_id: Mapped[str] = mapped_column(ForeignKey("obligations.id"), primary_key=True)
    clause: Mapped[Clause] = relationship(back_populates="obligations")
    obligation: Mapped[Obligation] = relationship()


class Playbook(Base):
    __tablename__ = "playbooks"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    version: Mapped[str] = mapped_column(String(30))
    contract_type: Mapped[str] = mapped_column(String(80), default="")
    jurisdiction: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    rules: Mapped[list["PlaybookRule"]] = relationship(back_populates="playbook", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("name", "version"),)


class PlaybookRule(Base):
    __tablename__ = "playbook_rules"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    playbook_id: Mapped[str] = mapped_column(ForeignKey("playbooks.id"), index=True)
    clause_category: Mapped[str] = mapped_column(String(160))
    required_phrases_json: Mapped[str] = mapped_column(Text, default="[]")
    prohibited_phrases_json: Mapped[str] = mapped_column(Text, default="[]")
    risk: Mapped[str] = mapped_column(String(10))
    remediation: Mapped[str] = mapped_column(Text)
    playbook: Mapped[Playbook] = relationship(back_populates="rules")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("contract_versions.id"), index=True)
    clause_id: Mapped[str | None] = mapped_column(ForeignKey("clauses.id"), nullable=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("playbook_rules.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    risk: Mapped[str] = mapped_column(String(10), index=True)
    evidence: Mapped[str] = mapped_column(Text)
    remediation: Mapped[str] = mapped_column(Text)
    override_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    __table_args__ = (UniqueConstraint("version_id", "rule_id"),)


class Reviewer(Base):
    __tablename__ = "reviewers"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(120))
    workload: Mapped[int] = mapped_column(Integer, default=0)
    capacity: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expertise: Mapped[list["ReviewerExpertise"]] = relationship(back_populates="reviewer", cascade="all, delete-orphan")


class Expertise(Base):
    __tablename__ = "expertise"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class ReviewerExpertise(Base):
    __tablename__ = "reviewer_expertise"
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("reviewers.id"), primary_key=True)
    expertise_id: Mapped[str] = mapped_column(ForeignKey("expertise.id"), primary_key=True)
    reviewer: Mapped[Reviewer] = relationship(back_populates="expertise")
    expertise: Mapped[Expertise] = relationship()


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), unique=True, index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("reviewers.id"), index=True)
    confidence: Mapped[str] = mapped_column(String(20))
    cost: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("reviewers.id"), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), index=True)
    issue: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    decisions: Mapped[list["ReviewDecision"]] = relationship(back_populates="review", cascade="all, delete-orphan")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"), unique=True, index=True)
    decision: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(String(100))
    decided_at: Mapped[datetime] = mapped_column(DateTime)
    review: Mapped[Review] = relationship(back_populates="decisions")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(30), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    actor: Mapped[str] = mapped_column(String(100), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(32), index=True)
    detail: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20))


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def _audit_events_are_append_only(*_args):
    raise ValueError("audit events are append-only")
