import json
import uuid
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.dependencies import get_current_user
from app.security.permissions import require_roles

router = APIRouter(prefix="/governance", tags=["Model and Evaluation Governance"])
MODEL_REVIEW_ROLES = ("PLATFORM_OWNER",)
MODEL_PROPOSAL_ROLES = ("WORKFORCE_MANAGER", "PLATFORM_OWNER")
PROVIDERS = {
    "Azure OpenAI": "AZURE_OPENAI",
    "OpenAI": "OPENAI",
    "Google": "GOOGLE",
    "Google Vertex": "GOOGLE_VERTEX",
    "Anthropic": "ANTHROPIC",
}


class ModelProposal(BaseModel):
    provider: Literal["Azure OpenAI", "OpenAI", "Google", "Google Vertex", "Anthropic"]
    model: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=10, max_length=2000)
    evidence: str = Field(min_length=20, max_length=4000)


class ModelDecision(BaseModel):
    decision: Literal["Approved", "Rejected"]
    reason: str = Field(min_length=10, max_length=2000)
    evidence: str = Field(min_length=20, max_length=4000)


def _audit(db, user, action, resource_id, details):
    db.execute(text("""
        INSERT dbo.AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
        VALUES(:correlation,'User',:actor,:action,'AIModelCatalog',:resource,'Success',:details)
    """), {
        "correlation": uuid.uuid4(), "actor": user["sub"], "action": action,
        "resource": str(resource_id), "details": json.dumps(details, ensure_ascii=True),
    })


@router.get("/models/approved", dependencies=[Depends(require_roles(*MODEL_PROPOSAL_ROLES))])
def list_approved_models(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT m.ModelCatalogID,m.ModelName,m.ModelVersion,p.ProviderCode,p.ProviderName,
               m.ApprovedAtUtc,m.ApprovedByUserID
        FROM dbo.AIModelCatalog m JOIN dbo.AIModelProvider p ON p.ProviderID=m.ProviderID
        WHERE m.Status='Approved' AND p.Status='Active'
        ORDER BY p.ProviderName,m.ModelName,m.ModelVersion
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.get("/models/catalog", dependencies=[Depends(require_roles(*MODEL_REVIEW_ROLES))])
def list_model_catalog(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT m.ModelCatalogID,m.ModelName,m.ModelVersion,m.Status,m.CreatedAtUtc,m.CreatedByUserID,
               m.ApprovedAtUtc,m.ApprovedByUserID,p.ProviderCode,p.ProviderName,
               latest.Decision AS LatestDecision,latest.Reason AS LatestReason,latest.Evidence AS LatestEvidence
        FROM dbo.AIModelCatalog m JOIN dbo.AIModelProvider p ON p.ProviderID=m.ProviderID
        OUTER APPLY (
            SELECT TOP 1 a.Decision,a.Reason,a.Evidence
            FROM dbo.AIModelApproval a WHERE a.ModelCatalogID=m.ModelCatalogID
            ORDER BY a.DecidedAtUtc DESC,a.ModelApprovalID DESC
        ) latest
        ORDER BY CASE m.Status WHEN 'Pending' THEN 0 WHEN 'Approved' THEN 1 WHEN 'Rejected' THEN 2 ELSE 3 END,
                 p.ProviderName,m.ModelName,m.ModelVersion
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.post("/models/proposals", status_code=201, dependencies=[Depends(require_roles(*MODEL_PROPOSAL_ROLES))])
def propose_model(
    body: ModelProposal,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    provider_code = PROVIDERS[body.provider]
    provider = db.execute(text("""
        SELECT ProviderID,Status FROM dbo.AIModelProvider WITH (UPDLOCK,HOLDLOCK)
        WHERE ProviderCode=:code
    """), {"code": provider_code}).mappings().first()
    if provider and provider["Status"] != "Active":
        raise HTTPException(status_code=409, detail="This model provider is inactive")
    if not provider:
        provider_id = uuid.uuid4()
        db.execute(text("""
            INSERT dbo.AIModelProvider(ProviderID,ProviderCode,ProviderName,Status,CreatedByUserID)
            VALUES(:id,:code,:name,'Active',:creator)
        """), {"id": provider_id, "code": provider_code, "name": body.provider, "creator": user["sub"]})
    else:
        provider_id = provider["ProviderID"]

    existing = db.execute(text("""
        SELECT ModelCatalogID,Status FROM dbo.AIModelCatalog WITH (UPDLOCK,HOLDLOCK)
        WHERE ProviderID=:provider AND ModelName=:model AND ModelVersion=:version
    """), {"provider": provider_id, "model": body.model.strip(), "version": body.version.strip()}).mappings().first()
    if existing:
        raise HTTPException(status_code=409, detail=f"This provider/model/version already exists with status {existing['Status']}")
    model_id = uuid.uuid4()
    db.execute(text("""
        INSERT dbo.AIModelCatalog(ModelCatalogID,ProviderID,ModelName,ModelVersion,Status,ApprovalRequired,CreatedByUserID)
        VALUES(:id,:provider,:model,:version,'Pending',1,:creator)
    """), {
        "id": model_id, "provider": provider_id, "model": body.model.strip(),
        "version": body.version.strip(), "creator": user["sub"],
    })
    _audit(db, user, "AIModelProposed", model_id, {
        "provider": body.provider, "model": body.model.strip(), "version": body.version.strip(),
        "reason": body.reason.strip(), "evidence": body.evidence.strip(),
    })
    db.commit()
    return {"model_catalog_id": str(model_id), "provider": body.provider, "model": body.model.strip(),
            "version": body.version.strip(), "status": "Pending"}


@router.post("/models/{model_catalog_id}/decision", dependencies=[Depends(require_roles(*MODEL_REVIEW_ROLES))])
def decide_model(
    model_catalog_id: UUID,
    body: ModelDecision,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    item = db.execute(text("""
        SELECT m.ModelCatalogID,m.Status,m.CreatedByUserID,p.Status AS ProviderStatus
        FROM dbo.AIModelCatalog m WITH (UPDLOCK,ROWLOCK)
        JOIN dbo.AIModelProvider p ON p.ProviderID=m.ProviderID
        WHERE m.ModelCatalogID=:id
    """), {"id": model_catalog_id}).mappings().first()
    if not item:
        raise HTTPException(status_code=404, detail="Model proposal not found")
    if item["Status"] != "Pending":
        raise HTTPException(status_code=409, detail=f"Model proposal is already {item['Status']}")
    if body.decision == "Approved" and str(item["CreatedByUserID"]) == str(user["sub"]):
        raise HTTPException(status_code=403, detail="A model proposer cannot approve their own model proposal")
    if body.decision == "Approved" and item["ProviderStatus"] != "Active":
        raise HTTPException(status_code=409, detail="Cannot approve a model under an inactive provider")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(text("""
        UPDATE dbo.AIModelCatalog SET Status=:decision,
            ApprovedAtUtc=CASE WHEN :decision='Approved' THEN :now ELSE NULL END,
            ApprovedByUserID=CASE WHEN :decision='Approved' THEN :actor ELSE NULL END
        WHERE ModelCatalogID=:id AND Status='Pending'
    """), {"decision": body.decision, "now": now, "actor": user["sub"], "id": model_catalog_id})
    db.execute(text("""
        INSERT dbo.AIModelApproval(ModelApprovalID,ModelCatalogID,Decision,Reason,Evidence,DecidedByUserID)
        VALUES(:approval,:catalog,:decision,:reason,:evidence,:reviewer)
    """), {
        "approval": uuid.uuid4(), "catalog": model_catalog_id, "decision": body.decision,
        "reason": body.reason.strip(), "evidence": body.evidence.strip(), "reviewer": user["sub"],
    })
    _audit(db, user, f"AIModel{body.decision}", model_catalog_id, {
        "reason": body.reason.strip(), "evidence": body.evidence.strip(),
    })
    db.commit()
    return {"model_catalog_id": str(model_catalog_id), "status": body.decision,
            "approved_by": user["sub"] if body.decision == "Approved" else None,
            "approved_at_utc": now.isoformat() if body.decision == "Approved" else None}


@router.get("/evaluation-templates", dependencies=[Depends(require_roles(*MODEL_PROPOSAL_ROLES))])
def list_evaluation_templates(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT t.TemplateID,t.TemplateCode,t.TemplateName,t.Version,
               c.CriterionCode,c.CriterionName,c.Description,c.SequenceNumber,c.IsRequired
        FROM dbo.EvaluationTemplate t
        LEFT JOIN dbo.EvaluationTemplateCriterion c ON c.TemplateID=t.TemplateID
        WHERE t.Status='Active'
        ORDER BY t.TemplateCode,c.SequenceNumber
    """)).mappings().all()
    templates = {}
    for row in rows:
        code = row["TemplateCode"]
        item = templates.setdefault(code, {
            "template_id": str(row["TemplateID"]), "template_code": code,
            "name": row["TemplateName"], "version": row["Version"], "criteria": [],
        })
        if row["CriterionCode"]:
            item["criteria"].append({
                "code": row["CriterionCode"], "name": row["CriterionName"],
                "description": row["Description"], "sequence": row["SequenceNumber"],
                "required": bool(row["IsRequired"]),
            })
    return list(templates.values())