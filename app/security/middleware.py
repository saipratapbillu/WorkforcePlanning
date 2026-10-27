from types import SimpleNamespace

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.db.session import SessionLocal
from app.security.dependencies import get_current_user
from app.security.roles import has_role


AUTHENTICATED_PREFIXES = (
    "/auth/me",
    "/dashboard/api",
    "/requirements",
    "/projects",
    "/tasks",
    "/approvals",
    "/notifications",
    "/runtime",
    "/workforce",
    "/agents",
    "/dashboard",
    "/requests",
    "/approval-center",
    "/workforce-center",
    "/profile",
    "/admin-control-center",
    "/admin/org-mappings",
    "/operations",
)

def forbidden_for_role(path: str, role: str) -> bool:
    if path in {"/workforce-center", "/static/workforce-center.html"}:
        return not has_role(role, "WORKFORCE_MANAGER", "PLATFORM_OWNER")
    if path == "/static/owner-command-center.html":
        return not has_role(role, "EXECUTIVE", "PLATFORM_OWNER")
    if path == "/static/executive-command-center.html":
        return not has_role(role, "EXECUTIVE", "PLATFORM_OWNER")
    if path == "/agents":
        return not has_role(role, "WORKFORCE_MANAGER", "PLATFORM_OWNER")
    if path.startswith("/runtime"):
        owner_only = ("/credential", "/enqueue", "/resolve", "/reap-expired-leases")
        allowed = ("PLATFORM_OWNER",) if any(part in path for part in owner_only) else ("WORKFORCE_MANAGER", "PLATFORM_OWNER")
        return not has_role(role, *allowed)
    return False


class AuthorizationMiddleware(BaseHTTPMiddleware):
    """Authenticate protected routes and enforce page/API role boundaries early."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        protected = path.startswith(AUTHENTICATED_PREFIXES) or path in {
            "/static/workforce-center.html",
            "/static/owner-command-center.html",
            "/static/requirement-chat.html",
            "/static/admin-control-center.html",
        }
        if not protected:
            return await call_next(request)

        authorization = request.headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        token = token if separator and scheme.lower() == "bearer" else request.cookies.get("ai_workforce_session")
        if not token:
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})

        db: Session = SessionLocal()
        try:
            user = get_current_user(request, SimpleNamespace(credentials=token), db)
            request.state.security_principal = user
        except HTTPException as error:
            return JSONResponse(status_code=error.status_code, content={"detail": error.detail}, headers=error.headers)
        finally:
            db.close()

        role = user["role"]
        if forbidden_for_role(path, role):
            return JSONResponse(status_code=403, content={"detail": "Access denied"})

        return await call_next(request)
