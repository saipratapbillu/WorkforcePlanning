import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.workforce_management import MANAGEMENT_ROLES, _audit, _require_visible_project
from app.db.session import get_db
from app.security.dependencies import get_current_user
from app.security.permissions import require_roles

router = APIRouter(prefix="/execution", tags=["Development Execution"],
                   dependencies=[Depends(require_roles(*MANAGEMENT_ROLES))])

STORY_TRANSITIONS = {
    "Backlog": {"Planned", "Cancelled"},
    "Planned": {"Backlog", "InProgress", "Cancelled"},
    "InProgress": {"Completed", "Blocked", "Cancelled"},
    "Blocked": {"InProgress", "Cancelled"},
    "Completed": set(),
    "Cancelled": set(),
}
EPIC_STATUSES = ("Proposed", "Planned", "InProgress")
FEATURE_STATUSES = ("Proposed", "Planned", "InProgress", "Completed", "Cancelled")


class EpicCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    owner_user_id: UUID | None = None
    priority: int = Field(default=3, ge=1, le=5)


class EpicUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    owner_user_id: UUID | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    status: Literal["Proposed", "Planned", "InProgress"] | None = None

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class FeatureCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    priority: int = Field(default=3, ge=1, le=5)


class FeatureUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    priority: int | None = Field(default=None, ge=1, le=5)
    status: Literal["Proposed", "Planned", "InProgress", "Completed", "Cancelled"] | None = None

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class StoryCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    story_points: int = Field(default=3, ge=1, le=100)
    priority: int = Field(default=3, ge=1, le=5)


class StoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    story_points: int | None = Field(default=None, ge=1, le=100)
    priority: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class StoryTransition(BaseModel):
    status: Literal["Backlog", "Planned", "InProgress", "Completed", "Blocked", "Cancelled"]


class SprintCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    start_date: date
    end_date: date
    capacity_hours: float = Field(ge=0, le=100000)

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class SprintStoryAdd(BaseModel):
    story_id: UUID


class BacklogOrder(BaseModel):
    story_ids: list[UUID] = Field(min_length=1, max_length=2000)


class DependencyAdd(BaseModel):
    depends_on_story_id: UUID


def has_path(edges: dict, start, target) -> bool:
    """True when `target` is reachable from `start` following edges (story -> depends-on)."""
    seen, stack = set(), [start]
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(edges.get(node, ()))
    return False


def burndown_series(total_points: int, completions: list, start: date, end: date, today: date | None = None) -> list[dict]:
    """Ideal vs actual remaining points per day. `completions` is a list of (date, points)."""
    today = today or date.today()
    days = (end - start).days + 1
    series = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        ideal = total_points * (1 - offset / (days - 1)) if days > 1 else 0.0
        point = {"date": day.isoformat(), "ideal": round(ideal, 2), "actual": None}
        if day <= today:
            done = sum(points for when, points in completions if when <= day)
            point["actual"] = max(total_points - done, 0)
        series.append(point)
    return series


def sprint_health(committed_points: int, completed_points: int, committed_hours: float, capacity_hours: float,
                  start: date, end: date, status: str, today: date | None = None) -> dict:
    today = today or date.today()
    total_days = max((end - start).days + 1, 1)
    elapsed = min(max((today - start).days + 1, 0), total_days) / total_days
    done = (completed_points / committed_points) if committed_points else 0.0
    overloaded = committed_hours > capacity_hours
    if status == "Completed":
        label = "Completed"
    elif status != "Active":
        label = "Overloaded" if overloaded else "NotStarted"
    elif overloaded or done < elapsed - 0.25:
        label = "Behind"
    elif done < elapsed - 0.10:
        label = "AtRisk"
    else:
        label = "OnTrack"
    return {
        "health": label,
        "percent_complete": round(done * 100, 1),
        "percent_time_elapsed": round(elapsed * 100, 1),
        "committed_hours": round(committed_hours, 2),
        "capacity_hours": round(capacity_hours, 2),
        "capacity_utilization": round(committed_hours / capacity_hours * 100, 1) if capacity_hours else None,
        "overloaded": overloaded,
    }


def _row(db: Session, sql: str, params: dict):
    return db.execute(text(sql), params).mappings().first()


def _project_of(db: Session, actor: dict, kind: str, item_id: UUID) -> UUID:
    queries = {
        "epic": "SELECT ProjectID FROM dbo.ProjectEpic WHERE EpicID=:id",
        "feature": "SELECT e.ProjectID FROM dbo.ProjectFeature f JOIN dbo.ProjectEpic e ON e.EpicID=f.EpicID WHERE f.FeatureID=:id",
        "story": ("SELECT e.ProjectID FROM dbo.ProjectStory s JOIN dbo.ProjectFeature f ON f.FeatureID=s.FeatureID "
                  "JOIN dbo.ProjectEpic e ON e.EpicID=f.EpicID WHERE s.StoryID=:id"),
        "sprint": "SELECT ProjectID FROM dbo.ProjectSprint WHERE SprintID=:id",
    }
    row = _row(db, queries[kind], {"id": item_id})
    if not row:
        raise HTTPException(status_code=404, detail=f"{kind.capitalize()} not found")
    project_id = UUID(str(row["ProjectID"]))
    _require_visible_project(db, actor, project_id)
    return project_id


def _check_owner(db: Session, owner_id: UUID | None):
    if owner_id is None:
        return
    if not _row(db, "SELECT 1 AS ok FROM dbo.AppUser WHERE UserID=:id AND IsActive=1", {"id": owner_id}):
        raise HTTPException(status_code=422, detail="Owner must be an active user")


def _update(db: Session, table: str, key: str, item_id: UUID, values: dict):
    if not values:
        raise HTTPException(status_code=422, detail="No changes supplied")
    assignments = ", ".join(f"{col}=:{col}" for col in values)
    db.execute(text(f"UPDATE dbo.{table} SET {assignments}, UpdatedAtUtc=SYSUTCDATETIME() WHERE {key}=:item_id"),
               {**values, "item_id": item_id})


def _utcnow():
    return datetime.now(timezone.utc)


# ----------------------------- Epics -----------------------------

@router.get("/projects/{project_id}/epics")
def list_epics(project_id: UUID, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    _require_visible_project(db, actor, project_id)
    rows = db.execute(text("""
        SELECT e.EpicID, e.Title, e.Description, e.Status, e.Priority, e.OwnerUserID, e.ClosedAtUtc,
               (SELECT COUNT(*) FROM dbo.ProjectFeature f WHERE f.EpicID=e.EpicID) AS FeatureCount
        FROM dbo.ProjectEpic e WHERE e.ProjectID=:p ORDER BY e.SequenceNumber
    """), {"p": project_id}).mappings().all()
    return {"project_id": str(project_id), "epics": [dict(r) for r in rows]}


@router.post("/projects/{project_id}/epics", status_code=201)
def create_epic(project_id: UUID, body: EpicCreate, db: Session = Depends(get_db),
                actor=Depends(get_current_user)):
    _require_visible_project(db, actor, project_id)
    _check_owner(db, body.owner_user_id)
    epic_id = uuid.uuid4()
    db.execute(text("""
        INSERT INTO dbo.ProjectEpic(EpicID, ProjectID, Title, Description, SequenceNumber, Status, CreatedBy, OwnerUserID, Priority)
        SELECT :id, :p, :title, :descr, COALESCE(MAX(SequenceNumber),0)+1, 'Proposed', :by, :owner, :prio
        FROM dbo.ProjectEpic WHERE ProjectID=:p
    """), {"id": epic_id, "p": project_id, "title": body.title.strip(), "descr": body.description.strip(),
           "by": actor.get("email") or actor["sub"], "owner": body.owner_user_id, "prio": body.priority})
    _audit(db, actor, "EXECUTION_EPIC_CREATED", "ProjectEpic", str(epic_id), {"project_id": str(project_id)})
    db.commit()
    return {"epic_id": str(epic_id), "status": "Proposed"}


@router.patch("/epics/{epic_id}")
def update_epic(epic_id: UUID, body: EpicUpdate, db: Session = Depends(get_db),
                actor=Depends(get_current_user)):
    _project_of(db, actor, "epic", epic_id)
    epic = _row(db, "SELECT Status FROM dbo.ProjectEpic WHERE EpicID=:id", {"id": epic_id})
    if epic["Status"] in ("Completed", "Cancelled"):
        raise HTTPException(status_code=409, detail="Closed epics cannot be modified")
    changes = body.model_dump(exclude_unset=True)
    if "owner_user_id" in changes:
        _check_owner(db, changes["owner_user_id"])
    columns = {"title": "Title", "description": "Description", "owner_user_id": "OwnerUserID",
               "priority": "Priority", "status": "Status"}
    _update(db, "ProjectEpic", "EpicID", epic_id, {columns[k]: v for k, v in changes.items()})
    _audit(db, actor, "EXECUTION_EPIC_UPDATED", "ProjectEpic", str(epic_id), {"fields": sorted(changes)})
    db.commit()
    return {"epic_id": str(epic_id), "updated": sorted(changes)}


@router.post("/epics/{epic_id}/close")
def close_epic(epic_id: UUID, outcome: Literal["Completed", "Cancelled"] = "Completed",
               db: Session = Depends(get_db), actor=Depends(get_current_user)):
    _project_of(db, actor, "epic", epic_id)
    epic = _row(db, "SELECT Status FROM dbo.ProjectEpic WHERE EpicID=:id", {"id": epic_id})
    if epic["Status"] in ("Completed", "Cancelled"):
        raise HTTPException(status_code=409, detail="Epic is already closed")
    if outcome == "Completed":
        open_stories = _row(db, """
            SELECT COUNT(*) AS n FROM dbo.ProjectStory s JOIN dbo.ProjectFeature f ON f.FeatureID=s.FeatureID
            WHERE f.EpicID=:id AND s.Status NOT IN ('Completed','Cancelled')
        """, {"id": epic_id})["n"]
        if open_stories:
            raise HTTPException(status_code=409, detail=f"{open_stories} story(ies) are still open")
    _update(db, "ProjectEpic", "EpicID", epic_id, {"Status": outcome, "ClosedAtUtc": _utcnow()})
    _audit(db, actor, "EXECUTION_EPIC_CLOSED", "ProjectEpic", str(epic_id), {"outcome": outcome})
    db.commit()
    return {"epic_id": str(epic_id), "status": outcome}


# ----------------------------- Features -----------------------------

@router.post("/epics/{epic_id}/features", status_code=201)
def create_feature(epic_id: UUID, body: FeatureCreate, db: Session = Depends(get_db),
                   actor=Depends(get_current_user)):
    _project_of(db, actor, "epic", epic_id)
    epic = _row(db, "SELECT Status FROM dbo.ProjectEpic WHERE EpicID=:id", {"id": epic_id})
    if epic["Status"] in ("Completed", "Cancelled"):
        raise HTTPException(status_code=409, detail="Cannot add features to a closed epic")
    feature_id = uuid.uuid4()
    db.execute(text("""
        INSERT INTO dbo.ProjectFeature(FeatureID, EpicID, Title, Description, SequenceNumber, Status, CreatedBy, Priority)
        SELECT :id, :e, :title, :descr, COALESCE(MAX(SequenceNumber),0)+1, 'Proposed', :by, :prio
        FROM dbo.ProjectFeature WHERE EpicID=:e
    """), {"id": feature_id, "e": epic_id, "title": body.title.strip(), "descr": body.description.strip(),
           "by": actor.get("email") or actor["sub"], "prio": body.priority})
    _audit(db, actor, "EXECUTION_FEATURE_CREATED", "ProjectFeature", str(feature_id), {"epic_id": str(epic_id)})
    db.commit()
    return {"feature_id": str(feature_id), "status": "Proposed"}


@router.patch("/features/{feature_id}")
def update_feature(feature_id: UUID, body: FeatureUpdate, db: Session = Depends(get_db),
                   actor=Depends(get_current_user)):
    _project_of(db, actor, "feature", feature_id)
    changes = body.model_dump(exclude_unset=True)
    columns = {"title": "Title", "description": "Description", "priority": "Priority", "status": "Status"}
    _update(db, "ProjectFeature", "FeatureID", feature_id, {columns[k]: v for k, v in changes.items()})
    _audit(db, actor, "EXECUTION_FEATURE_UPDATED", "ProjectFeature", str(feature_id), {"fields": sorted(changes)})
    db.commit()
    return {"feature_id": str(feature_id), "updated": sorted(changes)}


@router.delete("/features/{feature_id}")
def delete_feature(feature_id: UUID, db: Session = Depends(get_db),
                   actor=Depends(get_current_user)):
    _project_of(db, actor, "feature", feature_id)
    if _row(db, "SELECT TOP 1 1 AS ok FROM dbo.ProjectStory WHERE FeatureID=:id", {"id": feature_id}):
        raise HTTPException(status_code=409, detail="Feature has stories; cancel it instead of deleting")
    db.execute(text("DELETE FROM dbo.ProjectFeature WHERE FeatureID=:id"), {"id": feature_id})
    _audit(db, actor, "EXECUTION_FEATURE_DELETED", "ProjectFeature", str(feature_id), {})
    db.commit()
    return {"feature_id": str(feature_id), "deleted": True}


@router.get("/projects/{project_id}/traceability")
def traceability(project_id: UUID, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    """Project -> Epic -> Feature -> Story -> Task tree with approved assignees."""
    _require_visible_project(db, actor, project_id)
    rows = db.execute(text("""
        SELECT e.EpicID, e.Title AS EpicTitle, e.Status AS EpicStatus,
               f.FeatureID, f.Title AS FeatureTitle, f.Status AS FeatureStatus,
               s.StoryID, s.Title AS StoryTitle, s.Status AS StoryStatus, s.StoryPoints, s.SprintID,
               t.ProjectTaskID, t.Title AS TaskTitle, t.Status AS TaskStatus, t.EstimatedEffortHours,
               a.UserID
        FROM dbo.ProjectEpic e
        LEFT JOIN dbo.ProjectFeature f ON f.EpicID=e.EpicID
        LEFT JOIN dbo.ProjectStory s ON s.FeatureID=f.FeatureID
        LEFT JOIN dbo.ProjectDeliveryTask t ON t.StoryID=s.StoryID
        LEFT JOIN dbo.ProjectTaskAssignment a ON a.ProjectTaskID=t.ProjectTaskID AND a.Status='Active'
        WHERE e.ProjectID=:p ORDER BY e.SequenceNumber, f.SequenceNumber, s.CreatedAtUtc, t.CreatedAtUtc
    """), {"p": project_id}).mappings().all()
    epics: dict = {}
    for r in rows:
        epic = epics.setdefault(r["EpicID"], {"epic_id": str(r["EpicID"]), "title": r["EpicTitle"],
                                              "status": r["EpicStatus"], "features": {}})
        if r["FeatureID"] is None:
            continue
        feature = epic["features"].setdefault(r["FeatureID"], {"feature_id": str(r["FeatureID"]),
                                                               "title": r["FeatureTitle"], "status": r["FeatureStatus"],
                                                               "stories": {}})
        if r["StoryID"] is None:
            continue
        story = feature["stories"].setdefault(r["StoryID"], {
            "story_id": str(r["StoryID"]), "title": r["StoryTitle"], "status": r["StoryStatus"],
            "story_points": r["StoryPoints"], "sprint_id": str(r["SprintID"]) if r["SprintID"] else None,
            "tasks": []})
        if r["ProjectTaskID"] is not None:
            story["tasks"].append({"task_id": str(r["ProjectTaskID"]), "title": r["TaskTitle"],
                                   "status": r["TaskStatus"], "hours": float(r["EstimatedEffortHours"]),
                                   "assigned_user_id": str(r["UserID"]) if r["UserID"] else None})
    tree = []
    for epic in epics.values():
        features = []
        for feature in epic["features"].values():
            features.append({**feature, "stories": list(feature["stories"].values())})
        tree.append({**epic, "features": features})
    return {"project_id": str(project_id), "epics": tree}


# ----------------------------- Stories -----------------------------

@router.post("/features/{feature_id}/stories", status_code=201)
def create_story(feature_id: UUID, body: StoryCreate, db: Session = Depends(get_db),
                 actor=Depends(get_current_user)):
    _project_of(db, actor, "feature", feature_id)
    feature = _row(db, "SELECT Status FROM dbo.ProjectFeature WHERE FeatureID=:id", {"id": feature_id})
    if feature["Status"] in ("Completed", "Cancelled"):
        raise HTTPException(status_code=409, detail="Cannot add stories to a closed feature")
    story_id = uuid.uuid4()
    db.execute(text("""
        INSERT INTO dbo.ProjectStory(StoryID, FeatureID, Title, Description, AcceptanceCriteriaJson,
                                     RequiredSkillsJson, RequiredCertificationsJson, StoryPoints, Status,
                                     CreatedBy, Priority, BacklogRank)
        SELECT :id, :f, :title, :descr, '[]', '[]', '[]', :pts, 'Backlog', :by, :prio,
               COALESCE((SELECT MAX(s2.BacklogRank) FROM dbo.ProjectStory s2
                         JOIN dbo.ProjectFeature f2 ON f2.FeatureID=s2.FeatureID
                         WHERE f2.EpicID=(SELECT EpicID FROM dbo.ProjectFeature WHERE FeatureID=:f)),0)+1
    """), {"id": story_id, "f": feature_id, "title": body.title.strip(), "descr": body.description.strip(),
           "pts": body.story_points, "by": actor.get("email") or actor["sub"], "prio": body.priority})
    _audit(db, actor, "EXECUTION_STORY_CREATED", "ProjectStory", str(story_id), {"feature_id": str(feature_id)})
    db.commit()
    return {"story_id": str(story_id), "status": "Backlog"}


@router.patch("/stories/{story_id}")
def update_story(story_id: UUID, body: StoryUpdate, db: Session = Depends(get_db),
                 actor=Depends(get_current_user)):
    _project_of(db, actor, "story", story_id)
    story = _row(db, "SELECT Status FROM dbo.ProjectStory WHERE StoryID=:id", {"id": story_id})
    if story["Status"] in ("Completed", "Cancelled"):
        raise HTTPException(status_code=409, detail="Closed stories cannot be modified")
    changes = body.model_dump(exclude_unset=True)
    columns = {"title": "Title", "description": "Description", "story_points": "StoryPoints", "priority": "Priority"}
    _update(db, "ProjectStory", "StoryID", story_id, {columns[k]: v for k, v in changes.items()})
    _audit(db, actor, "EXECUTION_STORY_UPDATED", "ProjectStory", str(story_id), {"fields": sorted(changes)})
    db.commit()
    return {"story_id": str(story_id), "updated": sorted(changes)}


@router.delete("/stories/{story_id}")
def delete_story(story_id: UUID, db: Session = Depends(get_db),
                 actor=Depends(get_current_user)):
    _project_of(db, actor, "story", story_id)
    story = _row(db, "SELECT Status FROM dbo.ProjectStory WHERE StoryID=:id", {"id": story_id})
    if story["Status"] != "Backlog":
        raise HTTPException(status_code=409, detail="Only Backlog stories can be deleted; cancel it instead")
    if _row(db, "SELECT TOP 1 1 AS ok FROM dbo.ProjectDeliveryTask WHERE StoryID=:id", {"id": story_id}):
        raise HTTPException(status_code=409, detail="Story has tasks; cancel it instead of deleting")
    db.execute(text("DELETE FROM dbo.ProjectStoryDependency WHERE StoryID=:id OR DependsOnStoryID=:id"), {"id": story_id})
    db.execute(text("DELETE FROM dbo.ProjectStory WHERE StoryID=:id"), {"id": story_id})
    _audit(db, actor, "EXECUTION_STORY_DELETED", "ProjectStory", str(story_id), {})
    db.commit()
    return {"story_id": str(story_id), "deleted": True}


@router.post("/stories/{story_id}/transition")
def transition_story(story_id: UUID, body: StoryTransition, db: Session = Depends(get_db),
                     actor=Depends(get_current_user)):
    _project_of(db, actor, "story", story_id)
    story = _row(db, "SELECT Status, SprintID FROM dbo.ProjectStory WITH (UPDLOCK, ROWLOCK) WHERE StoryID=:id",
                 {"id": story_id})
    current, target = story["Status"], body.status
    if target not in STORY_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=409, detail=f"Transition {current} -> {target} is not allowed")
    if target == "InProgress":
        blockers = _row(db, """
            SELECT COUNT(*) AS n FROM dbo.ProjectStoryDependency d
            JOIN dbo.ProjectStory p ON p.StoryID=d.DependsOnStoryID
            WHERE d.StoryID=:id AND p.Status<>'Completed'
        """, {"id": story_id})["n"]
        if blockers:
            raise HTTPException(status_code=409, detail=f"{blockers} dependency(ies) are not completed")
        # Governance: work starts only once a manager-approved assignment exists.
        approved = _row(db, """
            SELECT COUNT(*) AS n FROM dbo.ProjectDeliveryTask t
            JOIN dbo.ProjectTaskAssignment a ON a.ProjectTaskID=t.ProjectTaskID AND a.Status='Active'
            WHERE t.StoryID=:id
        """, {"id": story_id})["n"]
        if not approved:
            raise HTTPException(status_code=409, detail="A manager-approved task assignment is required to start work")
    if target == "Planned" and not story["SprintID"]:
        raise HTTPException(status_code=409, detail="Add the story to a sprint before marking it Planned")
    values = {"Status": target}
    if target == "Completed":
        values["CompletedAtUtc"] = _utcnow()
    if target == "Backlog":
        values["SprintID"] = None
    _update(db, "ProjectStory", "StoryID", story_id, values)
    _audit(db, actor, "EXECUTION_STORY_TRANSITION", "ProjectStory", str(story_id), {"from": current, "to": target})
    db.commit()
    return {"story_id": str(story_id), "from": current, "status": target}


@router.get("/stories/{story_id}/assignments")
def story_assignments(story_id: UUID, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    """Read-only. Assignment itself only happens via the manager-approved recommendation flow."""
    _project_of(db, actor, "story", story_id)
    rows = db.execute(text("""
        SELECT t.ProjectTaskID, t.Title, t.Status, a.UserID, a.Status AS AssignmentStatus
        FROM dbo.ProjectDeliveryTask t
        LEFT JOIN dbo.ProjectTaskAssignment a ON a.ProjectTaskID=t.ProjectTaskID AND a.Status='Active'
        WHERE t.StoryID=:id
    """), {"id": story_id}).mappings().all()
    return {"story_id": str(story_id), "tasks": [dict(r) for r in rows],
            "assignment_policy": "Manager approval required; no automatic assignment"}


# ----------------------------- Backlog -----------------------------

@router.get("/projects/{project_id}/backlog-items")
def ranked_backlog(project_id: UUID, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    _require_visible_project(db, actor, project_id)
    rows = db.execute(text("""
        SELECT s.StoryID, s.Title, s.Status, s.Priority, s.BacklogRank, s.StoryPoints, s.SprintID,
               f.FeatureID, e.EpicID,
               (SELECT COUNT(*) FROM dbo.ProjectStoryDependency d
                  JOIN dbo.ProjectStory p ON p.StoryID=d.DependsOnStoryID
                 WHERE d.StoryID=s.StoryID AND p.Status<>'Completed') AS OpenDependencies
        FROM dbo.ProjectStory s
        JOIN dbo.ProjectFeature f ON f.FeatureID=s.FeatureID
        JOIN dbo.ProjectEpic e ON e.EpicID=f.EpicID
        WHERE e.ProjectID=:p AND s.Status NOT IN ('Completed','Cancelled')
        ORDER BY s.Priority, s.BacklogRank
    """), {"p": project_id}).mappings().all()
    return {"project_id": str(project_id), "items": [dict(r) for r in rows]}


@router.put("/projects/{project_id}/backlog/order")
def reorder_backlog(project_id: UUID, body: BacklogOrder, db: Session = Depends(get_db),
                    actor=Depends(get_current_user)):
    _require_visible_project(db, actor, project_id)
    if len(set(body.story_ids)) != len(body.story_ids):
        raise HTTPException(status_code=422, detail="Duplicate story ids")
    for rank, sid in enumerate(body.story_ids, start=1):
        if _project_of(db, actor, "story", sid) != project_id:
            raise HTTPException(status_code=422, detail="Story does not belong to this project")
        db.execute(text("UPDATE dbo.ProjectStory SET BacklogRank=:r, UpdatedAtUtc=SYSUTCDATETIME() WHERE StoryID=:id"),
                   {"r": rank, "id": sid})
    _audit(db, actor, "EXECUTION_BACKLOG_REORDERED", "Project", str(project_id), {"count": len(body.story_ids)})
    db.commit()
    return {"project_id": str(project_id), "reordered": len(body.story_ids)}


@router.post("/stories/{story_id}/dependencies", status_code=201)
def add_dependency(story_id: UUID, body: DependencyAdd, db: Session = Depends(get_db),
                   actor=Depends(get_current_user)):
    project_id = _project_of(db, actor, "story", story_id)
    if body.depends_on_story_id == story_id:
        raise HTTPException(status_code=422, detail="A story cannot depend on itself")
    if _project_of(db, actor, "story", body.depends_on_story_id) != project_id:
        raise HTTPException(status_code=422, detail="Dependencies must be within the same project")
    rows = db.execute(text("""
        SELECT d.StoryID, d.DependsOnStoryID FROM dbo.ProjectStoryDependency d
        JOIN dbo.ProjectStory s ON s.StoryID=d.StoryID
        JOIN dbo.ProjectFeature f ON f.FeatureID=s.FeatureID
        JOIN dbo.ProjectEpic e ON e.EpicID=f.EpicID WHERE e.ProjectID=:p
    """), {"p": project_id}).mappings().all()
    edges: dict = {}
    for r in rows:
        edges.setdefault(str(r["StoryID"]).lower(), []).append(str(r["DependsOnStoryID"]).lower())
    if has_path(edges, str(body.depends_on_story_id).lower(), str(story_id).lower()):
        raise HTTPException(status_code=409, detail="Dependency would create a cycle")
    if body.depends_on_story_id in edges.get(story_id, []):
        raise HTTPException(status_code=409, detail="Dependency already exists")
    db.execute(text("""
        INSERT INTO dbo.ProjectStoryDependency(StoryID, DependsOnStoryID, CreatedBy) VALUES (:s, :d, :by)
    """), {"s": story_id, "d": body.depends_on_story_id, "by": actor.get("email") or actor["sub"]})
    _audit(db, actor, "EXECUTION_DEPENDENCY_ADDED", "ProjectStory", str(story_id),
           {"depends_on": str(body.depends_on_story_id)})
    db.commit()
    return {"story_id": str(story_id), "depends_on_story_id": str(body.depends_on_story_id)}


@router.delete("/stories/{story_id}/dependencies/{depends_on_story_id}")
def remove_dependency(story_id: UUID, depends_on_story_id: UUID, db: Session = Depends(get_db),
                      actor=Depends(get_current_user)):
    _project_of(db, actor, "story", story_id)
    result = db.execute(text("DELETE FROM dbo.ProjectStoryDependency WHERE StoryID=:s AND DependsOnStoryID=:d"),
                        {"s": story_id, "d": depends_on_story_id})
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Dependency not found")
    _audit(db, actor, "EXECUTION_DEPENDENCY_REMOVED", "ProjectStory", str(story_id),
           {"depends_on": str(depends_on_story_id)})
    db.commit()
    return {"story_id": str(story_id), "removed": True}


# ----------------------------- Sprints -----------------------------

def _sprint_totals(db: Session, sprint_id: UUID) -> dict:
    return _row(db, """
        SELECT COALESCE(SUM(s.StoryPoints),0) AS points,
               COALESCE(SUM(CASE WHEN s.Status='Completed' THEN s.StoryPoints ELSE 0 END),0) AS done_points,
               COALESCE(SUM(h.Hours),0) AS hours, COUNT(s.StoryID) AS stories
        FROM dbo.ProjectStory s
        OUTER APPLY (SELECT SUM(t.EstimatedEffortHours) AS Hours FROM dbo.ProjectDeliveryTask t
                     WHERE t.StoryID=s.StoryID AND t.Status<>'Cancelled') h
        WHERE s.SprintID=:id AND s.Status<>'Cancelled'
    """, {"id": sprint_id})


@router.get("/projects/{project_id}/sprints")
def list_sprints(project_id: UUID, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    _require_visible_project(db, actor, project_id)
    sprints = db.execute(text("""
        SELECT SprintID, SprintName, StartDate, EndDate, CapacityHours, Status
        FROM dbo.ProjectSprint WHERE ProjectID=:p ORDER BY StartDate
    """), {"p": project_id}).mappings().all()
    result = []
    for sp in sprints:
        totals = _sprint_totals(db, sp["SprintID"])
        result.append({**dict(sp), "committed_points": int(totals["points"]),
                       "committed_hours": float(totals["hours"]), "story_count": int(totals["stories"])})
    return {"project_id": str(project_id), "sprints": result}


@router.post("/projects/{project_id}/sprints", status_code=201)
def create_sprint(project_id: UUID, body: SprintCreate, db: Session = Depends(get_db),
                  actor=Depends(get_current_user)):
    _require_visible_project(db, actor, project_id)
    sprint_id = uuid.uuid4()
    db.execute(text("""
        INSERT INTO dbo.ProjectSprint(SprintID, ProjectID, SprintName, StartDate, EndDate, CapacityHours, Status, CreatedBy)
        VALUES (:id, :p, :name, :s, :e, :cap, 'Planned', :by)
    """), {"id": sprint_id, "p": project_id, "name": body.name.strip(), "s": body.start_date,
           "e": body.end_date, "cap": body.capacity_hours, "by": actor.get("email") or actor["sub"]})
    _audit(db, actor, "EXECUTION_SPRINT_CREATED", "ProjectSprint", str(sprint_id), {"project_id": str(project_id)})
    db.commit()
    return {"sprint_id": str(sprint_id), "status": "Planned"}


@router.post("/sprints/{sprint_id}/stories", status_code=201)
def plan_story_into_sprint(sprint_id: UUID, body: SprintStoryAdd, db: Session = Depends(get_db),
                           actor=Depends(get_current_user)):
    project_id = _project_of(db, actor, "sprint", sprint_id)
    if _project_of(db, actor, "story", body.story_id) != project_id:
        raise HTTPException(status_code=422, detail="Story does not belong to this project")
    sprint = _row(db, "SELECT Status, CapacityHours FROM dbo.ProjectSprint WITH (UPDLOCK, ROWLOCK) WHERE SprintID=:id",
                  {"id": sprint_id})
    if sprint["Status"] not in ("Planned", "Active"):
        raise HTTPException(status_code=409, detail="Sprint is closed")
    story = _row(db, "SELECT Status, SprintID FROM dbo.ProjectStory WHERE StoryID=:id", {"id": body.story_id})
    if story["Status"] not in ("Backlog", "Planned") or story["SprintID"]:
        raise HTTPException(status_code=409, detail="Story is not available for sprint planning")
    story_hours = float(_row(db, """
        SELECT COALESCE(SUM(EstimatedEffortHours),0) AS h FROM dbo.ProjectDeliveryTask
        WHERE StoryID=:id AND Status<>'Cancelled'
    """, {"id": body.story_id})["h"])
    committed = float(_sprint_totals(db, sprint_id)["hours"])
    if committed + story_hours > float(sprint["CapacityHours"]):
        raise HTTPException(status_code=409, detail=(
            f"Sprint capacity exceeded: {committed + story_hours:.1f}h planned vs {float(sprint['CapacityHours']):.1f}h capacity"))
    _update(db, "ProjectStory", "StoryID", body.story_id, {"SprintID": sprint_id, "Status": "Planned"})
    _audit(db, actor, "EXECUTION_STORY_PLANNED", "ProjectSprint", str(sprint_id), {"story_id": str(body.story_id)})
    db.commit()
    return {"sprint_id": str(sprint_id), "story_id": str(body.story_id), "committed_hours": committed + story_hours}


@router.delete("/sprints/{sprint_id}/stories/{story_id}")
def remove_story_from_sprint(sprint_id: UUID, story_id: UUID, db: Session = Depends(get_db),
                             actor=Depends(get_current_user)):
    _project_of(db, actor, "sprint", sprint_id)
    story = _row(db, "SELECT Status, SprintID FROM dbo.ProjectStory WHERE StoryID=:id", {"id": story_id})
    if not story or str(story["SprintID"]).lower() != str(sprint_id).lower():
        raise HTTPException(status_code=404, detail="Story is not in this sprint")
    if story["Status"] != "Planned":
        raise HTTPException(status_code=409, detail="Only Planned stories can be removed from a sprint")
    _update(db, "ProjectStory", "StoryID", story_id, {"SprintID": None, "Status": "Backlog"})
    _audit(db, actor, "EXECUTION_STORY_UNPLANNED", "ProjectSprint", str(sprint_id), {"story_id": str(story_id)})
    db.commit()
    return {"sprint_id": str(sprint_id), "story_id": str(story_id), "removed": True}


@router.post("/sprints/{sprint_id}/start")
def start_sprint(sprint_id: UUID, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    project_id = _project_of(db, actor, "sprint", sprint_id)
    sprint = _row(db, "SELECT Status FROM dbo.ProjectSprint WITH (UPDLOCK, ROWLOCK) WHERE SprintID=:id", {"id": sprint_id})
    if sprint["Status"] != "Planned":
        raise HTTPException(status_code=409, detail="Only Planned sprints can be started")
    if _row(db, "SELECT TOP 1 1 AS ok FROM dbo.ProjectSprint WHERE ProjectID=:p AND Status='Active'", {"p": project_id}):
        raise HTTPException(status_code=409, detail="Another sprint is already active")
    if not _sprint_totals(db, sprint_id)["stories"]:
        raise HTTPException(status_code=409, detail="Cannot start an empty sprint")
    _update_sprint(db, sprint_id, "Active", "StartedAtUtc")
    _audit(db, actor, "EXECUTION_SPRINT_STARTED", "ProjectSprint", str(sprint_id), {})
    db.commit()
    return {"sprint_id": str(sprint_id), "status": "Active"}


@router.post("/sprints/{sprint_id}/complete")
def complete_sprint(sprint_id: UUID, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    _project_of(db, actor, "sprint", sprint_id)
    sprint = _row(db, "SELECT Status FROM dbo.ProjectSprint WITH (UPDLOCK, ROWLOCK) WHERE SprintID=:id", {"id": sprint_id})
    if sprint["Status"] != "Active":
        raise HTTPException(status_code=409, detail="Only Active sprints can be completed")
    carried = db.execute(text("""
        UPDATE dbo.ProjectStory SET SprintID=NULL, Status='Backlog', UpdatedAtUtc=SYSUTCDATETIME()
        WHERE SprintID=:id AND Status IN ('Planned','InProgress','Blocked')
    """), {"id": sprint_id}).rowcount
    _update_sprint(db, sprint_id, "Completed", "CompletedAtUtc")
    _audit(db, actor, "EXECUTION_SPRINT_COMPLETED", "ProjectSprint", str(sprint_id), {"carried_over": carried})
    db.commit()
    return {"sprint_id": str(sprint_id), "status": "Completed", "carried_over": carried}


def _update_sprint(db: Session, sprint_id: UUID, status: str, stamp_column: str):
    column = {"StartedAtUtc": "StartedAtUtc", "CompletedAtUtc": "CompletedAtUtc"}[stamp_column]
    db.execute(text(f"UPDATE dbo.ProjectSprint SET Status=:s, {column}=SYSUTCDATETIME() WHERE SprintID=:id"),
               {"s": status, "id": sprint_id})


@router.get("/sprints/{sprint_id}/burndown")
def sprint_burndown(sprint_id: UUID, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    _project_of(db, actor, "sprint", sprint_id)
    sprint = _row(db, "SELECT SprintName, StartDate, EndDate FROM dbo.ProjectSprint WHERE SprintID=:id", {"id": sprint_id})
    totals = _sprint_totals(db, sprint_id)
    completions = [(r["CompletedAtUtc"].date(), int(r["StoryPoints"])) for r in db.execute(text("""
        SELECT StoryPoints, CompletedAtUtc FROM dbo.ProjectStory
        WHERE SprintID=:id AND Status='Completed' AND CompletedAtUtc IS NOT NULL
    """), {"id": sprint_id}).mappings().all()]
    return {"sprint_id": str(sprint_id), "name": sprint["SprintName"], "total_points": int(totals["points"]),
            "series": burndown_series(int(totals["points"]), completions, sprint["StartDate"], sprint["EndDate"])}


# ----------------------------- Dashboard -----------------------------

@router.get("/projects/{project_id}/dashboard")
def project_dashboard(project_id: UUID, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    _require_visible_project(db, actor, project_id)
    epics = db.execute(text("""
        SELECT e.EpicID, e.Title, e.Status,
               COUNT(s.StoryID) AS Stories,
               COALESCE(SUM(CASE WHEN s.Status='Completed' THEN 1 ELSE 0 END),0) AS DoneStories,
               COALESCE(SUM(s.StoryPoints),0) AS Points,
               COALESCE(SUM(CASE WHEN s.Status='Completed' THEN s.StoryPoints ELSE 0 END),0) AS DonePoints
        FROM dbo.ProjectEpic e
        LEFT JOIN dbo.ProjectFeature f ON f.EpicID=e.EpicID
        LEFT JOIN dbo.ProjectStory s ON s.FeatureID=f.FeatureID AND s.Status<>'Cancelled'
        WHERE e.ProjectID=:p GROUP BY e.EpicID, e.Title, e.Status, e.SequenceNumber ORDER BY e.SequenceNumber
    """), {"p": project_id}).mappings().all()
    stories = db.execute(text("""
        SELECT s.Status, COUNT(*) AS n FROM dbo.ProjectStory s
        JOIN dbo.ProjectFeature f ON f.FeatureID=s.FeatureID JOIN dbo.ProjectEpic e ON e.EpicID=f.EpicID
        WHERE e.ProjectID=:p GROUP BY s.Status
    """), {"p": project_id}).mappings().all()
    sprints = db.execute(text("""
        SELECT SprintID, SprintName, StartDate, EndDate, CapacityHours, Status
        FROM dbo.ProjectSprint WHERE ProjectID=:p ORDER BY StartDate
    """), {"p": project_id}).mappings().all()

    epic_progress = [{
        "epic_id": str(e["EpicID"]), "title": e["Title"], "status": e["Status"],
        "stories": int(e["Stories"]), "completed_stories": int(e["DoneStories"]),
        "percent_complete": round(e["DonePoints"] / e["Points"] * 100, 1) if e["Points"] else 0.0,
    } for e in epics]
    by_status = {r["Status"]: int(r["n"]) for r in stories}
    total = sum(by_status.values())
    sprint_rows = []
    for sp in sprints:
        totals = _sprint_totals(db, sp["SprintID"])
        sprint_rows.append({
            "sprint_id": str(sp["SprintID"]), "name": sp["SprintName"], "status": sp["Status"],
            "start_date": sp["StartDate"].isoformat(), "end_date": sp["EndDate"].isoformat(),
            "committed_points": int(totals["points"]), "completed_points": int(totals["done_points"]),
            **sprint_health(int(totals["points"]), int(totals["done_points"]), float(totals["hours"]),
                            float(sp["CapacityHours"]), sp["StartDate"], sp["EndDate"], sp["Status"]),
        })
    return {
        "project_id": str(project_id),
        "epic_progress": epic_progress,
        "story_progress": {"total": total, "by_status": by_status,
                           "percent_complete": round(by_status.get("Completed", 0) / total * 100, 1) if total else 0.0},
        "sprint_health": sprint_rows,
        "governance": "Manager approval required for every assignment; no automatic assignment",
    }
