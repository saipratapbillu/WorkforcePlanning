<<<<<<< HEAD
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.approvals import router as approvals_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.model_governance import router as model_governance_router
from app.api.org_mappings import router as org_mappings_router
from app.api.projects import router as projects_router
from app.api.notifications import router as notifications_router
from app.api.operations import router as operations_router
from app.api.requirements import router as requirements_router
from app.api.users import router as users_router
from app.api.workforce import router as workforce_router
from app.api.runtime import router as runtime_router
from app.api.tasks import router as tasks_router
from app.db.session import SessionLocal, get_db
from app.security.dependencies import bearer_scheme, get_current_user
from app.security.middleware import AuthorizationMiddleware
from app.security.permissions import require_roles
from app.security.roles import has_role

STATIC_DIR = Path(__file__).resolve().parent / "static"
PUBLIC_HTML = {"landing.html", "login.html", "register.html"}
PUBLIC_ASSET_EXTENSIONS = {".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".woff", ".woff2"}
STATIC_HTML_ROLES = {
    "workforce-center.html": {"WORKFORCE_MANAGER", "PLATFORM_OWNER"},
    "owner-command-center.html": {"EXECUTIVE", "PLATFORM_OWNER"},
    "executive-command-center.html": {"EXECUTIVE", "PLATFORM_OWNER"},
    "admin-control-center.html": {"PLATFORM_OWNER"},
}


@asynccontextmanager
async def lifespan(_app):
    yield


def authorize_static_html(filename: str, user: dict):
    allowed_roles = STATIC_HTML_ROLES.get(filename)
    if allowed_roles and not has_role(user.get("role"), *allowed_roles):
        raise HTTPException(status_code=403, detail="Access denied")

app = FastAPI(
    title="AI Workforce OS",
    version="3.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.add_middleware(AuthorizationMiddleware)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(requirements_router)
app.include_router(approvals_router)
app.include_router(projects_router)
app.include_router(dashboard_router)
app.include_router(model_governance_router)
app.include_router(org_mappings_router)
app.include_router(notifications_router)
app.include_router(operations_router)
app.include_router(workforce_router)
app.include_router(runtime_router)
app.include_router(tasks_router)


@app.middleware("http")
async def same_origin_mutations(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
            return JSONResponse(status_code=403, content={"detail": "Cross-origin request denied"})
    return await call_next(request)


@app.get("/", include_in_schema=False)
def public_home():
    return FileResponse(STATIC_DIR / "landing.html")


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
def readiness(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/agents", include_in_schema=False)
def agents(db: Session = Depends(get_db), _user=Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))):
    rows = db.execute(text("""
        SELECT AgentID, AgentName, AgentType, Grade, AutonomyLevel,
               RiskLevel, Status, CurrentWorkload
        FROM Agent ORDER BY AgentName
    """)).mappings().all()
    return [dict(row) for row in rows]


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/register", include_in_schema=False)
def register_page():
    return FileResponse(STATIC_DIR / "register.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard_page(_user=Depends(get_current_user)):
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/requests", include_in_schema=False)
def request_tracker_page(_user=Depends(get_current_user)):
    return FileResponse(STATIC_DIR / "request-tracker.html")


@app.get("/approval-center", include_in_schema=False)
def approval_center_page(_user=Depends(get_current_user)):
    return FileResponse(STATIC_DIR / "approval-center.html")


@app.get("/workforce-center", include_in_schema=False)
def workforce_center_page(_user=Depends(require_roles("ADMIN", "OWNER", "SUPER_ADMIN"))):
    return FileResponse(STATIC_DIR / "workforce-center.html")


@app.get("/executive-command-center", include_in_schema=False)
def executive_command_center_page(_user=Depends(require_roles("EXECUTIVE", "PLATFORM_OWNER"))):
    return FileResponse(STATIC_DIR / "executive-command-center.html")


@app.get("/admin-control-center", include_in_schema=False)
def admin_control_center_page(_user=Depends(require_roles("PLATFORM_OWNER"))):
    return FileResponse(STATIC_DIR / "admin-control-center.html")


@app.get("/profile", include_in_schema=False)
def profile_page(_user=Depends(get_current_user)):
    return FileResponse(STATIC_DIR / "profile.html")


@app.get("/static/{asset_path:path}", include_in_schema=False)
def static_asset(
    asset_path: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    requested = (STATIC_DIR / asset_path).resolve()
    if not requested.is_relative_to(STATIC_DIR) or not requested.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    if requested.suffix.lower() == ".html":
        if requested.name not in PUBLIC_HTML:
            user = get_current_user(request=request, credentials=credentials, db=db)
            authorize_static_html(requested.name, user)
            if requested.name == "owner-command-center.html":
                return RedirectResponse("/executive-command-center")
    elif requested.suffix.lower() not in PUBLIC_ASSET_EXTENSIONS:
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(requested)
=======
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.schemas import RequirementCreate, ProjectCreate, TaskCreate
from app.services.orchestrator import classify_requirement
import uuid, json

app = FastAPI(title="AI Company Control Plane", version="0.1.0")

def uid(): return str(uuid.uuid4())

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status":"ok","database":"AICompany","server":"localhost"}

@app.post("/requirements")
def create_requirement(req: RequirementCreate, db: Session = Depends(get_db)):
    rid = uid(); analysis = classify_requirement(req.description)
    db.execute(text("""INSERT INTO Requirement
      (RequirementID,Title,Description,RequestedBy,Priority,RiskLevel,Status,CreatedAtUtc,CreatedBy,ModifiedAtUtc,ModifiedBy)
      VALUES (:id,:t,:d,:rb,:p,:risk,'Assessed',SYSUTCDATETIME(),:rb,SYSUTCDATETIME(),:rb)"""),
      {"id":rid,"t":req.title,"d":req.description,"rb":req.requested_by,"p":req.priority,"risk":analysis["risk_level"]})
    db.commit()
    return {"requirement_id":rid,"ceo_analysis":analysis}

@app.post("/projects")
def create_project(p: ProjectCreate, db: Session = Depends(get_db)):
    pid = uid()
    db.execute(text("""INSERT INTO Project
      (ProjectID,ProjectName,Objective,BusinessOwner,BudgetAmount,Status,CreatedAtUtc,CreatedBy,ModifiedAtUtc,ModifiedBy)
      VALUES (:id,:n,:o,:bo,:b,'Planning',SYSUTCDATETIME(),:bo,SYSUTCDATETIME(),:bo)"""),
      {"id":pid,"n":p.name,"o":p.objective,"bo":p.business_owner,"b":p.budget})
    db.commit(); return {"project_id":pid,"status":"Planning"}

@app.post("/tasks")
def create_task(t: TaskCreate, db: Session = Depends(get_db)):
    tid = uid()
    db.execute(text("""INSERT INTO Task
      (TaskID,ProjectID,Description,Priority,AssignedAgentID,RiskLevel,BudgetLimit,TokenLimit,Status,CreatedAtUtc,CreatedBy,ModifiedAtUtc,ModifiedBy)
      VALUES (:id,:pid,:d,:p,:a,:r,:b,:tok,'Created',SYSUTCDATETIME(),'API',SYSUTCDATETIME(),'API')"""),
      {"id":tid,"pid":t.project_id,"d":t.description,"p":t.priority,"a":t.assigned_agent_id,"r":t.risk_level,"b":t.budget_limit,"tok":t.token_limit})
    db.commit(); return {"task_id":tid,"status":"Created"}

@app.get("/agents")
def agents(db: Session = Depends(get_db)):
    rows=db.execute(text("SELECT AgentID,AgentName,AgentType,Grade,AutonomyLevel,RiskLevel,Status,CurrentWorkload FROM Agent ORDER BY AgentName")).mappings().all()
    return [dict(r) for r in rows]
>>>>>>> 3e08d0de30e4b712c5b3c8c50b4f61e4d04df639
