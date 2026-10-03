"""Stable local identifier generation."""

from sqlalchemy import select
from sqlalchemy.orm import Session


def next_identifier(session: Session, model, prefix: str, width: int = 3) -> str:
    identifiers = session.scalars(select(model.id).where(model.id.like(f"{prefix}-%"))).all()
    numbers = []
    for identifier in identifiers:
        suffix = identifier.removeprefix(f"{prefix}-")
        if suffix.isdigit():
            numbers.append(int(suffix))
    return f"{prefix}-{(max(numbers, default=0) + 1):0{width}d}"
