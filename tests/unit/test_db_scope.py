"""
Guard: every REST route gets its database session from get_db with scope="function"
(backend/app/database.py `DbSession`, docs/plans/t4-ui-restructuring.md §6.2.5 k).

With FastAPI's default scope ("request"), get_db's commit runs after the response has
been sent, so a client reading right after a write can see stale data. And because
FastAPI caches dependencies per (callable, scope), a single bare `Depends(get_db)` next
to `DbSession` gives one request two sessions. This test walks the dependency tree of
every route and fails on any get_db dependency that isn't function-scoped.

It reads FastAPI's dependency tree (`route.dependant`, `Dependant.scope`, checked
against FastAPI 0.142.2). If an upgrade changes that structure, the tripwires below fail
loudly instead of letting the guard pass vacuously.

Run with:
    cd tests/unit && pytest test_db_scope.py -v
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from app.database import get_db
from app.main import app


def _api_routes(routes) -> list[APIRoute]:
    """Every APIRoute under `routes`. FastAPI 0.142 wraps included routers in a
    private _IncludedRouter; its `original_router` is our own APIRouter."""
    found: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
        elif hasattr(route, "original_router"):
            found.extend(_api_routes(route.original_router.routes))
        elif hasattr(route, "routes"):
            found.extend(_api_routes(route.routes))
    return found


def _get_db_scopes(dependant, path: str, out: list[tuple[str, object]]) -> None:
    for sub in dependant.dependencies:
        if sub.call is get_db:
            out.append((path, sub.scope))
        _get_db_scopes(sub, path, out)


def test_walk_reaches_every_documented_operation():
    """Tripwire: the walk must find exactly the operations OpenAPI documents, so a
    change in how FastAPI stores included routes can't hide routes from the guard."""
    routes = _api_routes(app.routes)
    walked = sum(len(r.methods) for r in routes if r.include_in_schema)
    documented = sum(len(ops) for ops in app.openapi()["paths"].values())
    assert walked == documented > 0


def test_every_get_db_dependency_is_function_scoped():
    found: list[tuple[str, object]] = []
    for route in _api_routes(app.routes):
        _get_db_scopes(route.dependant, f"{sorted(route.methods)} {route.path}", found)
    # Tripwire: the app has dozens of DB-backed routes; zero means the walk broke.
    assert len(found) > 50, found
    wrong = [(path, scope) for path, scope in found if scope != "function"]
    assert not wrong, f"get_db must be used via database.DbSession: {wrong}"
