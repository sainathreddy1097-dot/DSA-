"""Local actor resolution and mutation authorization."""

from contextvars import ContextVar, Token

from sqlalchemy.orm import Session

from .. import models
from ..errors import ApiError


_current_actor: ContextVar[models.User | None] = ContextVar("current_actor", default=None)
ADMIN_ONLY_PREFIXES = ("/reviewers", "/reviewer-assignments")
MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def resolve_actor(session: Session, actor_id: str | None) -> models.User:
    if not actor_id:
        raise ApiError(401, "authentication_required", "X-Actor-Id is required for changes")
    actor = session.get(models.User, actor_id)
    if not actor or not actor.active:
        raise ApiError(401, "authentication_required", "The supplied actor is not active")
    return actor


def require_mutation_role(actor: models.User, path: str) -> None:
    allowed = {"Administrator", "Legal Reviewer"}
    if path.startswith(ADMIN_ONLY_PREFIXES):
        allowed = {"Administrator"}
    if actor.role not in allowed:
        raise ApiError(403, "permission_denied", "This role cannot perform that change")


def set_current_actor(actor: models.User) -> Token:
    return _current_actor.set(actor)


def reset_current_actor(token: Token) -> None:
    _current_actor.reset(token)


def current_actor() -> models.User | None:
    return _current_actor.get()