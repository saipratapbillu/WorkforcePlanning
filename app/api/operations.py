import json
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.dependencies import get_current_user
from app.security.permissions import require_roles
from app.services.execution_adapters import (
    SecretNotFound,
    SecretResolutionError,
    SecretResolverUnavailable,
    configured_secret_resolver,
    probe_provider,
)
from app.services.workforce_planner import REQUIRED_AGENT_CERTIFICATIONS, agent_meets_profile
from app.services.governance_agent_framework import build_assurance_platform, build_shadow_review

router = APIRouter(prefix="/operations", tags=["Operational Readiness"])
EXEC_ROLES = ("EXECUTIVE", "PLATFORM_OWNER")
ADMIN_ROLES = ("WORKFORCE_MANAGER", "PLATFORM_OWNER")
ADAPTERS = {
    "AZURE_OPENAI": ("Azure OpenAI", "AZURE_OPENAI"),
    "OPENAI": ("OpenAI", "OPENAI"),
    "GOOGLE_VERTEX": ("Google Vertex", "GOOGLE_VERTEX"),
    "ANTHROPIC": ("Anthropic", "ANTHROPIC"),
}
RLS_COVERAGE_TABLES = (
    "Requirement", "Project", "Task", "Issue", "Approval", "Notification",
    "TaskAssignment", "TaskDependency", "Deliverable", "Evaluation",
    "AgentTaskQueue", "AgentExecution", "AgentExecutionOutput",
)


def _audit(db: Session, user: dict, action: str, resource_id: UUID, details: dict) -> None:
    db.execute(text("""
        INSERT dbo.AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
        VALUES(:correlation,'User',:actor,:action,'AIModelCatalog',:resource,'Success',:details)
    """), {
        "correlation": uuid.uuid4(), "actor": user["sub"], "action": action,
        "resource": str(resource_id), "details": json.dumps(details, ensure_ascii=True),
    })


class AdapterConfiguration(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    endpoint_url: str = Field(min_length=8, max_length=1000)
    deployment_name: str = Field(min_length=1, max_length=200)
    model_catalog_id: UUID
    secret_reference: str = Field(min_length=5, max_length=500)

    @field_validator("secret_reference")
    @classmethod
    def validate_secret_reference(cls, value: str) -> str:
        reference = value.strip()
        if not (reference.startswith("azure-kv://") or reference.startswith("env://")):
            raise ValueError("Store a secret reference (azure-kv://... or development env://...), never a raw credential.")
        return reference


class ModelRetirement(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)
    evidence: str = Field(min_length=20, max_length=4000)


class OwnershipReviewDecision(BaseModel):
    decision: Literal["ApprovedForManualChange", "Rejected", "NeedsReview"]
    reason: str = Field(min_length=10, max_length=2000)
    evidence: str = Field(min_length=20, max_length=4000)
    change_ticket: str = Field(min_length=3, max_length=120)


def validate_migration_24_script(script: str) -> dict:
    required_fragments = (
        "CREATE TABLE dbo.WorkforceReuseAssessment",
        "UQ_WorkforceReuseAssessment_Project_Role_Agent",
        "CK_WorkforceReuseAssessment_MatchScore",
        "CK_WorkforceReuseAssessment_Classification",
        "CK_WorkforceReuseAssessment_Status",
    )
    missing = [fragment for fragment in required_fragments if fragment not in script]
    destructive = [line.strip() for line in script.splitlines() if "DROP TABLE" in line.upper() or "DROP COLUMN" in line.upper()]
    has_create_guard = "IF OBJECT_ID('dbo.WorkforceReuseAssessment','U') IS NULL" in script
    has_constraint_guards = script.count("IF EXISTS (SELECT 1 FROM sys.check_constraints") >= 2
    ready = not missing and not destructive and has_create_guard and has_constraint_guards
    return {
        "validator_version": "1.0",
        "script_present": bool(script),
        "script_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest() if script else None,
        "script_character_count": len(script),
        "go_batch_count": sum(line.strip().upper() == "GO" for line in script.splitlines()),
        "required_contracts_present": not missing,
        "missing_contracts": missing,
        "create_is_guarded": has_create_guard,
        "constraint_replacement_is_guarded": has_constraint_guards,
        "destructive_table_or_column_operations": destructive,
        "static_validation": "PASS" if ready else "FAIL",
        "database_dry_run_executed": False,
        "database_execution_performed": False,
        "migration_applied": False,
        "rollback_sql_present": False,
        "rollback_validation": "No rollback script is present. Review backup/restore options and retain approved historical mappings before any deployment.",
        "rollback_checklist": [
            "Capture and verify a database backup before applying the migration.",
            "Record the migration transaction/change ticket and schema baseline.",
            "If rollback is required, use the approved database restore or a separately reviewed compensating script.",
            "Do not drop WorkforceReuseAssessment until its records, audit references, and dependent workflows are reviewed.",
        ],
    }


def ownership_remediation_report(db: Session):
    rows = []
    for table, key, legacy_owner, owner_column in (
        ("Requirement", "RequirementID", "CreatedBy", "CreatedByUserID"),
        ("Project", "ProjectID", "CreatedBy", "CreatedByUserID"),
        ("Task", "TaskID", "CreatedBy", "CreatedByUserID"),
        ("Issue", "IssueID", "Owner", "OwnerUserID"),
    ):
        result = db.execute(text(f"""
            SELECT x.{key} AS RecordID,x.{legacy_owner} AS LegacyOwner,
                   TRY_CONVERT(uniqueidentifier,x.{legacy_owner}) AS CandidateUserID,
                   u.UserID AS MatchedUserID,u.Email AS MatchedEmail,u.IsActive AS OwnerIsActive
            FROM dbo.{table} x
            LEFT JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,x.{legacy_owner})
            WHERE x.{owner_column} IS NULL
            ORDER BY x.{key}
        """)).mappings().all()
        for row in result:
            candidate = row["CandidateUserID"]
            matched = row["MatchedUserID"]
            exact_guid_match = bool(candidate and matched and str(candidate).lower() == str(matched).lower())
            rows.append({
                "table": table,
                "record_id": str(row["RecordID"]),
                "legacy_created_by": row.get("LegacyOwner", row.get("CreatedBy")),
                "candidate_user_id": str(candidate) if candidate else None,
                "matched_user_id": str(matched) if matched else None,
                "matched_email": row["MatchedEmail"],
                "owner_active": bool(row["OwnerIsActive"]) if row["OwnerIsActive"] is not None else None,
                "resolvable_exact_guid": exact_guid_match,
                "recommended_action": "UPDATE" if exact_guid_match else "MANUAL_REVIEW_NO_MATCH",
            })
    resolvable = [row for row in rows if row["resolvable_exact_guid"]]
    statements = [
        f"UPDATE dbo.{row['table']} SET {('OwnerUserID' if row['table'] == 'Issue' else 'CreatedByUserID')} = '{row['matched_user_id']}' "
        f"WHERE {row['table']}ID = '{row['record_id']}' "
        f"AND {('OwnerUserID' if row['table'] == 'Issue' else 'CreatedByUserID')} IS NULL "
        f"AND TRY_CONVERT(uniqueidentifier,{('Owner' if row['table'] == 'Issue' else 'CreatedBy')}) = '{row['matched_user_id']}';"
        for row in resolvable
    ]
    rollback_statements = [
        f"UPDATE dbo.{row['table']} SET {('OwnerUserID' if row['table'] == 'Issue' else 'CreatedByUserID')} = NULL "
        f"WHERE {row['table']}ID = '{row['record_id']}' "
        f"AND {('OwnerUserID' if row['table'] == 'Issue' else 'CreatedByUserID')} = '{row['matched_user_id']}' "
        f"AND TRY_CONVERT(uniqueidentifier,{('Owner' if row['table'] == 'Issue' else 'CreatedBy')}) = '{row['matched_user_id']}';"
        for row in resolvable
    ]
    exact_candidate_count = len(resolvable)
    total_candidate_count = len(rows)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "is_read_only": True,
        "automatically_applied": False,
        "total_null_owner_rows": len(rows),
        "resolvable_exact_guid_rows": len(resolvable),
        "manual_review_rows": len(rows) - len(resolvable),
        "expected_exact_guid_candidate_count": 9,
        "exact_guid_candidate_count_validated": exact_candidate_count == 9,
        "candidate_count_validated": total_candidate_count == 9,
        "candidate_validation": "validated" if total_candidate_count == 9 else "count_mismatch_requires_review",
        "rows": rows,
        "generated_update_script": "\n".join(statements) if statements else "-- No exact-GUID owner candidates found.",
        "generated_rollback_script": "\n".join(rollback_statements) if rollback_statements else "-- No applied exact-GUID changes to roll back.",
        "warning": "Review this report and generated script. Nothing has been applied.",
    }
    return report


@router.get("/ownership-remediation", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def get_ownership_remediation(db: Session = Depends(get_db)):
    return ownership_remediation_report(db)


@router.get("/ownership-remediation/approval-package", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def export_ownership_approval_package(db: Session = Depends(get_db)):
    report = ownership_remediation_report(db)
    readiness = phase8_readiness(db)
    candidates = report["rows"]
    count = len(candidates)
    unresolved = report["manual_review_rows"]
    return {
        "package_type": "Historical ownership remediation review",
        "generated_at_utc": report["generated_at_utc"],
        "read_only": True,
        "auto_apply": False,
        "summary": {
            "candidate_count": count,
            "exact_guid_match_count": report["resolvable_exact_guid_rows"],
            "unresolved_count": unresolved,
            "expected_candidate_count": report["expected_exact_guid_candidate_count"],
            "expected_count_validated": report["candidate_count_validated"],
            "exact_guid_matches": report["resolvable_exact_guid_rows"],
            "candidate_resolution_percent": round(100 * report["resolvable_exact_guid_rows"] / count, 1) if count else None,
            "candidate_unresolved_risk_percent": round(100 * unresolved / count, 1) if count else None,
            "ownership_coverage_percent": readiness["ownership"]["coverage_percent"],
            "ownership_risk_score": round(100 - readiness["ownership"]["coverage_percent"], 1) if readiness["ownership"]["coverage_percent"] is not None else None,
            "recommendation": "NO-GO" if unresolved or not report["candidate_count_validated"] or readiness["ownership"]["coverage_percent"] != 100.0 else "Ready for independent approval",
        },
        "verification_report": candidates,
        "remediation_sql": report["generated_update_script"],
        "rollback_sql": report["generated_rollback_script"],
        "approval_checklist": [
            "Verify each candidate's exact GUID equality against the intended AppUser.",
            "Review every unresolved record and resolve it through approved identity evidence.",
            "Independently review remediation and rollback SQL in a non-production environment.",
            "Record approver, change ticket, backup reference, and execution window outside this read-only package.",
            "Apply remediation only through a separately authorized operator; this API never executes SQL from the package.",
        ],
    }


@router.get("/operational-readiness", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def operational_readiness(db: Session = Depends(get_db)):
    users = db.execute(text("""
        SELECT COUNT(*) AS Total,
               SUM(CASE WHEN r.RoleID IS NOT NULL AND r.IsActive=1 THEN 1 ELSE 0 END) AS Ready
        FROM dbo.AppUser u LEFT JOIN dbo.Role r ON r.RoleID=u.RoleID
        WHERE u.IsActive=1
    """)).mappings().one()
    agents = db.execute(text("""
        SELECT COUNT(*) AS Total,
               SUM(CASE WHEN a.Status='Active' AND a.ModelProvider IS NOT NULL AND a.ModelProvider<>'UNCONFIGURED'
                              AND a.Model IS NOT NULL AND a.Model<>'UNCONFIGURED'
                              AND a.ModelVersion IS NOT NULL AND a.ModelVersion<>'UNCONFIGURED'
                         THEN 1 ELSE 0 END) AS Ready
        FROM dbo.Agent a
    """)).mappings().one()
    models = db.execute(text("""
        SELECT COUNT(*) FROM dbo.AIModelCatalog m JOIN dbo.AIModelProvider p ON p.ProviderID=m.ProviderID
        WHERE m.Status='Approved' AND p.Status='Active'
    """)).scalar_one()
    values = {
        "users_ready": {"ready": int(users["Ready"] or 0), "total": int(users["Total"] or 0)},
        "agents_ready": {"ready": int(agents["Ready"] or 0), "total": int(agents["Total"] or 0)},
        "models_approved": int(models or 0),
        "assignments_created": int(db.execute(text("SELECT COUNT(*) FROM dbo.TaskAssignment")).scalar_one() or 0),
        "executions_running": int(db.execute(text("SELECT COUNT(*) FROM dbo.AgentExecution WHERE Status='Executing'")).scalar_one() or 0),
        "deliverables_generated": int(db.execute(text("SELECT COUNT(*) FROM dbo.Deliverable")).scalar_one() or 0),
    }
    readiness_checks = [
        values["users_ready"]["ready"] == values["users_ready"]["total"] and values["users_ready"]["total"] > 0,
        values["agents_ready"]["ready"] > 0,
        values["models_approved"] > 0,
        values["assignments_created"] > 0,
        values["executions_running"] > 0,
        values["deliverables_generated"] > 0,
    ]
    return {
        "organization_scope": "single_organization",
        "status": "operational" if all(readiness_checks) else "not_operational",
        "scorecard": values,
        "readiness_percent": round(sum(readiness_checks) * 100 / len(readiness_checks)),
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "rls_enabled": bool(db.execute(text("SELECT COUNT(*) FROM sys.security_policies WHERE is_enabled=1")).scalar_one()),
        "execution_adapter_configured": False,
    }


@router.get("/execution-adapters", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def list_execution_adapters(db: Session = Depends(get_db)):
    configs = db.execute(text("""
         SELECT c.AdapterConfigID,c.ProviderCode,c.DisplayName,c.EndpointUrl,c.DeploymentName,
                         c.ModelCatalogID,c.Status,c.CreatedAtUtc,c.ModifiedAtUtc,
             CASE WHEN c.SecretReference IS NULL THEN 0 ELSE 1 END AS SecretReferenceConfigured,
                             m.ModelName,m.ModelVersion,m.Status AS ModelStatus,p.Status AS ProviderStatus,
               latest.Status AS LatestCheckStatus,latest.Details AS LatestCheckDetails,
               latest.CheckedAtUtc,latest.CheckedByUserID
        FROM dbo.ExecutionAdapterConfig c
        LEFT JOIN dbo.AIModelCatalog m ON m.ModelCatalogID=c.ModelCatalogID
        LEFT JOIN dbo.AIModelProvider p ON p.ProviderID=m.ProviderID
        OUTER APPLY (
            SELECT TOP 1 h.Status,h.Details,h.CheckedAtUtc,h.CheckedByUserID
            FROM dbo.ExecutionAdapterHealthCheck h WHERE h.AdapterConfigID=c.AdapterConfigID
            ORDER BY h.CheckedAtUtc DESC,h.HealthCheckID DESC
        ) latest
        ORDER BY c.DisplayName
    """)).mappings().all()
    by_provider = {row["ProviderCode"]: dict(row) for row in configs}
    return [{
        "provider_code": code,
        "provider_name": display,
        "config": by_provider.get(code),
        "health_status": (by_provider.get(code) or {}).get("LatestCheckStatus", "NotChecked"),
        "health_detail": (by_provider.get(code) or {}).get("LatestCheckDetails", "No configuration or provider check recorded."),
        "live_probe_available": False,
    } for code, (display, _catalog_code) in ADAPTERS.items()]


@router.get("/execution-adapters/deployment-package", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def adapter_deployment_package(db: Session = Depends(get_db)):
    providers = list_execution_adapters(db)
    provider_steps = []
    for provider in providers:
        config = provider["config"] or {}
        ref = config.get("SecretReference") or ""
        reference_shape_valid = ref.startswith("azure-kv://") or ref.startswith("env://")
        provider_steps.append({
            "provider_code": provider["provider_code"],
            "provider_name": provider["provider_name"],
            "configuration_status": config.get("Status", "NotConfigured"),
            "endpoint_configured": bool(config.get("EndpointUrl")),
            "approved_model_configured": bool(config.get("ModelCatalogID")),
            "secret_reference_configured": bool(ref),
            "secret_reference_format_valid": reference_shape_valid,
            "model_approved": bool(config.get("ModelCatalogID") and config.get("ModelStatus") == "Approved" and config.get("ProviderStatus") == "Active"),
            "credential_verified": False,
            "provider_call_performed": False,
            "health_status": provider["health_status"],
            "blockers": [
                label for label, missing in (
                    ("adapter configuration missing", not config),
                    ("endpoint missing", not config.get("EndpointUrl")),
                    ("approved model missing", not config.get("ModelCatalogID")),
                    ("model not currently approved or provider inactive", bool(config.get("ModelCatalogID") and (config.get("ModelStatus") != "Approved" or config.get("ProviderStatus") != "Active"))),
                    ("secret reference missing or unsupported", not reference_shape_valid),
                ) if missing
            ],
        })
    return {
        "package_type": "Execution adapter deployment validation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "providers": provider_steps,
        "credential_verification_route": "POST /operations/execution-adapters/{provider_code}/verify-credential",
        "provider_calls_performed": False,
        "runtime_enabled": False,
        "wizard": [
            "Select the approved model/version for the provider.",
            "Configure the provider HTTPS endpoint and deployment/resource identifier.",
            "Store the credential in Azure Key Vault; save only an azure-kv:// reference.",
            "Run credential verification to resolve the reference without making a provider API call.",
            "Schedule an authenticated connectivity probe only when credentials and endpoint approval are present.",
            "Review probe outcome and audit record; keep execution runtime disabled until separately authorized.",
        ],
    }


@router.post("/execution-adapters/{provider_code}/verify-credential", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def verify_adapter_credential_reference(
    provider_code: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    provider_code = provider_code.upper()
    if provider_code not in ADAPTERS:
        raise HTTPException(status_code=404, detail="Unsupported execution adapter provider")
    config = db.execute(text("""
        SELECT AdapterConfigID,SecretReference,Status FROM dbo.ExecutionAdapterConfig
        WHERE ProviderCode=:provider
    """), {"provider": provider_code}).mappings().first()
    if not config or not config["SecretReference"]:
        return {"provider_code": provider_code, "status": "ConfigurationIncomplete", "credential_verified": False, "provider_call_performed": False, "details": "No secret reference is configured."}
    try:
        configured_secret_resolver().resolve(config["SecretReference"])
        status_value = "Verified"
        details = "Secret reference resolved successfully. No provider request was made."
        verified = True
    except SecretResolverUnavailable:
        status_value = "ConfigurationIncomplete"
        details = "No supported secret resolver is configured."
        verified = False
    except SecretNotFound:
        status_value = "ConfigurationIncomplete"
        details = "Referenced credential is not available from the configured resolver."
        verified = False
    except SecretResolutionError:
        status_value = "Error"
        details = "Secret resolver could not verify the reference; diagnostic details were suppressed."
        verified = False
    db.execute(text("""
        INSERT dbo.AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
        VALUES(:correlation,'User',:actor,'ExecutionAdapterCredentialVerified',
               'ExecutionAdapterConfig',:resource,:outcome,:details)
    """), {
        "correlation": uuid.uuid4(), "actor": user["sub"], "resource": str(config["AdapterConfigID"]),
        "outcome": status_value,
        "details": json.dumps({"provider_code": provider_code, "credential_verified": verified, "provider_call_performed": False}, ensure_ascii=True),
    })
    db.commit()
    return {"provider_code": provider_code, "status": status_value, "credential_verified": verified, "provider_call_performed": False, "details": details}


@router.put("/execution-adapters/{provider_code}", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def configure_execution_adapter(
    provider_code: str,
    body: AdapterConfiguration,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    provider_code = provider_code.upper()
    if provider_code not in ADAPTERS:
        raise HTTPException(status_code=404, detail="Unsupported execution adapter provider")
    parsed = urlparse(body.endpoint_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Execution adapter endpoint must be an HTTPS URL")
    catalog = db.execute(text("""
        SELECT m.ModelCatalogID,m.ModelName,m.ModelVersion,p.ProviderCode
        FROM dbo.AIModelCatalog m JOIN dbo.AIModelProvider p ON p.ProviderID=m.ProviderID
        WHERE m.ModelCatalogID=:catalog_id AND m.Status='Approved'
    """), {"catalog_id": body.model_catalog_id}).mappings().first()
    if not catalog:
        raise HTTPException(status_code=422, detail="Execution adapter requires an Approved model catalog entry")
    expected_catalog_provider = ADAPTERS[provider_code][1]
    if catalog["ProviderCode"] != expected_catalog_provider:
        raise HTTPException(status_code=422, detail="Approved model provider does not match this execution adapter")
    current = db.execute(text("""
        SELECT AdapterConfigID FROM dbo.ExecutionAdapterConfig WITH (UPDLOCK,HOLDLOCK)
        WHERE ProviderCode=:provider
    """), {"provider": provider_code}).scalar_one_or_none()
    if current:
        adapter_id = current
        db.execute(text("""
            UPDATE dbo.ExecutionAdapterConfig SET EndpointUrl=:endpoint,DeploymentName=:deployment,
                ModelCatalogID=:model,SecretReference=:secret,Status='Configured',
                ModifiedAtUtc=SYSUTCDATETIME(),ModifiedByUserID=:actor
            WHERE AdapterConfigID=:id
        """), {
            "endpoint": body.endpoint_url, "deployment": body.deployment_name.strip(),
            "model": body.model_catalog_id, "secret": body.secret_reference.strip(),
            "actor": user["sub"], "id": adapter_id,
        })
    else:
        adapter_id = uuid.uuid4()
        db.execute(text("""
            INSERT dbo.ExecutionAdapterConfig
                (AdapterConfigID,ProviderCode,DisplayName,EndpointUrl,DeploymentName,ModelCatalogID,
                 SecretReference,Status,CreatedByUserID,ModifiedByUserID)
            VALUES(:id,:provider,:display,:endpoint,:deployment,:model,:secret,'Configured',:actor,:actor)
        """), {
            "id": adapter_id, "provider": provider_code, "display": ADAPTERS[provider_code][0],
            "endpoint": body.endpoint_url, "deployment": body.deployment_name.strip(),
            "model": body.model_catalog_id, "secret": body.secret_reference.strip(), "actor": user["sub"],
        })
    db.execute(text("""
        INSERT dbo.AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
        VALUES(:correlation,'User',:actor,'ExecutionAdapterConfigured','ExecutionAdapterConfig',:resource,'Success',:details)
    """), {
        "correlation": uuid.uuid4(), "actor": user["sub"], "resource": str(adapter_id),
        "details": json.dumps({"provider_code": provider_code, "model_catalog_id": str(body.model_catalog_id),
                               "secret_reference_stored": True}, ensure_ascii=True),
    })
    db.commit()
    return {"adapter_config_id": str(adapter_id), "provider_code": provider_code,
            "status": "Configured", "live_probe_available": False,
            "message": "Configuration saved. No provider connectivity probe or execution adapter is implemented; runtime remains disabled."}


@router.post("/execution-adapters/{provider_code}/health-check", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def record_adapter_health_check(
    provider_code: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    provider_code = provider_code.upper()
    if provider_code not in ADAPTERS:
        raise HTTPException(status_code=404, detail="Unsupported execution adapter provider")
    config = db.execute(text("""
        SELECT config.AdapterConfigID,config.Status,config.EndpointUrl,config.DeploymentName,
               config.ModelCatalogID,config.SecretReference,model.Status AS ModelStatus,
               model_provider.Status AS ProviderStatus
        FROM dbo.ExecutionAdapterConfig config
        LEFT JOIN dbo.AIModelCatalog model ON model.ModelCatalogID=config.ModelCatalogID
        LEFT JOIN dbo.AIModelProvider model_provider ON model_provider.ProviderID=model.ProviderID
        WHERE config.ProviderCode=:provider
    """), {"provider": provider_code}).mappings().first()
    if not config:
        raise HTTPException(status_code=404, detail="Execution adapter is not configured")

    missing = [name for name in ("EndpointUrl", "DeploymentName", "ModelCatalogID", "SecretReference") if not config[name]]
    if config["Status"] != "Configured":
        missing.append("Status=Configured")
    if config.get("ModelStatus") != "Approved" or config.get("ProviderStatus") != "Active":
        missing.append("Approved model under an Active provider")
    result = None
    if missing:
        result = {"status": "ConfigurationIncomplete", "details": "Missing configuration: " + ", ".join(missing), "http_status": None}
    else:
        try:
            secret = configured_secret_resolver().resolve(config["SecretReference"])
            probe = probe_provider(provider_code, config["EndpointUrl"], config["DeploymentName"], secret)
            result = {"status": probe.status, "details": probe.details, "http_status": probe.http_status}
        except SecretNotFound:
            result = {"status": "ConfigurationIncomplete", "details": "Referenced provider credential is not available from the configured secret resolver.", "http_status": None}
        except SecretResolverUnavailable:
            result = {"status": "ConfigurationIncomplete", "details": "A supported secret resolver is not configured.", "http_status": None}
        except SecretResolutionError:
            result = {"status": "Error", "details": "Configured secret resolver failed; diagnostic details were suppressed.", "http_status": None}

    check_id = uuid.uuid4()
    db.execute(text("""
        INSERT dbo.ExecutionAdapterHealthCheck(HealthCheckID,AdapterConfigID,Status,Details,CheckedByUserID)
        VALUES(:id,:config,:status,:details,:actor)
    """), {
        "id": check_id, "config": config["AdapterConfigID"], "status": result["status"],
        "details": result["details"], "actor": user["sub"],
    })
    db.execute(text("""
        INSERT dbo.AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
        VALUES(:correlation,'User',:actor,'ExecutionAdapterHealthChecked',
               'ExecutionAdapterConfig',:resource,:outcome,:details)
    """), {
        "correlation": uuid.uuid4(), "actor": user["sub"], "resource": str(config["AdapterConfigID"]),
        "outcome": result["status"],
        "details": json.dumps({"health_check_id": str(check_id), "http_status": result["http_status"], "details": result["details"]}, ensure_ascii=True),
    })
    db.commit()
    return {
        "health_check_id": str(check_id), "provider_code": provider_code,
        "status": result["status"], "details": result["details"],
        "http_status": result["http_status"], "network_probe_performed": result["http_status"] is not None,
    }


@router.get("/execution-adapters/audit-history", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def execution_adapter_audit_history(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT TOP 200 AuditLogID,ActorID,Action,ResourceID,Outcome,Details,CreatedAtUtc
        FROM dbo.AuditLog
        WHERE ResourceType='ExecutionAdapterConfig' OR Action LIKE 'ExecutionAdapter%'
        ORDER BY CreatedAtUtc DESC,AuditLogID DESC
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.get("/model-governance", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def model_governance_dashboard(db: Session = Depends(get_db)):
    lifecycle = db.execute(text("""
        SELECT Status,COUNT(*) AS ModelCount FROM dbo.AIModelCatalog GROUP BY Status ORDER BY Status
    """)).mappings().all()
    aging = db.execute(text("""
        SELECT m.ModelCatalogID,p.ProviderName,m.ModelName,m.ModelVersion,m.CreatedAtUtc,
               DATEDIFF(hour,m.CreatedAtUtc,SYSUTCDATETIME()) AS PendingHours,m.CreatedByUserID
        FROM dbo.AIModelCatalog m JOIN dbo.AIModelProvider p ON p.ProviderID=m.ProviderID
        WHERE m.Status='Pending' ORDER BY m.CreatedAtUtc
    """)).mappings().all()
    approved = db.execute(text("""
        SELECT m.ModelCatalogID,m.ModelName,m.ModelVersion,p.ProviderName,m.ApprovedAtUtc
        FROM dbo.AIModelCatalog m JOIN dbo.AIModelProvider p ON p.ProviderID=m.ProviderID
        WHERE m.Status='Approved' ORDER BY p.ProviderName,m.ModelName,m.ModelVersion
    """)).mappings().all()
    assignment_table_exists = bool(db.execute(text("SELECT CASE WHEN OBJECT_ID('dbo.TaskAssignment','U') IS NULL THEN 0 ELSE 1 END")).scalar_one())
    execution_table_exists = bool(db.execute(text("SELECT CASE WHEN OBJECT_ID('dbo.AgentExecution','U') IS NULL THEN 0 ELSE 1 END")).scalar_one())
    approved_models = []
    for model in approved:
        model_data = dict(model)
        params = {"provider": model["ProviderName"], "model": model["ModelName"], "version": model["ModelVersion"]}
        model_data["AgentImpactCount"] = db.execute(text("""
            SELECT COUNT(*) FROM dbo.Agent
            WHERE ModelProvider=:provider AND Model=:model AND ModelVersion=:version
              AND Status IN ('Active','Provisioning','Training','Testing','PendingApproval')
        """), params).scalar_one()
        model_data["ActiveAssignmentImpactCount"] = db.execute(text("""
            SELECT COUNT(*) FROM dbo.TaskAssignment assignment JOIN dbo.Agent agent ON agent.AgentID=assignment.AgentID
            WHERE agent.ModelProvider=:provider AND agent.Model=:model AND agent.ModelVersion=:version
              AND assignment.Status='Active' AND assignment.ReleasedAtUtc IS NULL
        """), params).scalar_one() if assignment_table_exists else None
        model_data["RunningExecutionImpactCount"] = db.execute(text("""
            SELECT COUNT(*) FROM dbo.AgentExecution execution JOIN dbo.Agent agent ON agent.AgentID=execution.AgentID
            WHERE agent.ModelProvider=:provider AND agent.Model=:model AND agent.ModelVersion=:version
              AND execution.Status='Executing'
        """), params).scalar_one() if execution_table_exists else None
        model_data["retirement_blockers"] = {
            "active_agents": int(model_data["AgentImpactCount"] or 0),
            "active_assignments": int(model_data["ActiveAssignmentImpactCount"] or 0),
            "running_executions": int(model_data["RunningExecutionImpactCount"] or 0),
        }
        model_data["retirement_blocked"] = any(value not in (None, 0) for value in model_data["retirement_blockers"].values())
        approved_models.append(model_data)
    usage_rows = db.execute(text("""
        SELECT p.ProviderName,m.ModelName,m.ModelVersion,m.Status,
               (SELECT COUNT(*) FROM dbo.Agent agent WHERE agent.ModelProvider=p.ProviderName
                    AND agent.Model=m.ModelName AND agent.ModelVersion=m.ModelVersion AND agent.Status='Active') AS ActiveAgentCount,
               (SELECT COUNT(*) FROM dbo.TaskAssignment assignment JOIN dbo.Agent agent ON agent.AgentID=assignment.AgentID
                WHERE agent.ModelProvider=p.ProviderName AND agent.Model=m.ModelName AND agent.ModelVersion=m.ModelVersion
                  AND assignment.Status='Active' AND assignment.ReleasedAtUtc IS NULL) AS ActiveAssignmentCount,
               (SELECT COUNT(*) FROM dbo.AgentExecution execution JOIN dbo.Agent agent ON agent.AgentID=execution.AgentID
                WHERE agent.ModelProvider=p.ProviderName AND agent.Model=m.ModelName AND agent.ModelVersion=m.ModelVersion) AS ExecutionCount
        FROM dbo.AIModelCatalog m JOIN dbo.AIModelProvider p ON p.ProviderID=m.ProviderID
        ORDER BY p.ProviderName,m.ModelName,m.ModelVersion
    """)).mappings().all()
    pending_count = sum(1 for row in aging)
    return {"lifecycle": [dict(row) for row in lifecycle], "pending_approval_aging": [dict(row) for row in aging],
            "pending_reviews": pending_count,
            "approval_sla": {"configured": False, "target_hours": None, "status": "NotConfigured"},
            "model_usage": [dict(row) for row in usage_rows],
            "approved_models": approved_models,
            "retirement_available": True}


@router.post("/models/{model_catalog_id}/retire", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def retire_model(
    model_catalog_id: UUID,
    body: ModelRetirement,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    model = db.execute(text("""
        SELECT m.ModelCatalogID,m.Status,p.ProviderCode,p.ProviderName,m.ModelName,m.ModelVersion
        FROM dbo.AIModelCatalog m WITH (UPDLOCK,ROWLOCK)
        JOIN dbo.AIModelProvider p ON p.ProviderID=m.ProviderID
        WHERE m.ModelCatalogID=:id
    """), {"id": model_catalog_id}).mappings().first()
    if not model:
        raise HTTPException(status_code=404, detail="Model catalog entry not found")
    if model["Status"] != "Approved":
        raise HTTPException(status_code=409, detail="Only an Approved model can be retired")
    in_use = db.execute(text("""
        SELECT TOP 1 AgentID,AgentName,Status FROM dbo.Agent
        WHERE ModelProvider=:provider AND Model=:model AND ModelVersion=:version
          AND Status IN ('Active','Provisioning','Training','Testing','PendingApproval')
    """), {"provider": model["ProviderName"], "model": model["ModelName"], "version": model["ModelVersion"]}).mappings().first()
    if in_use:
        raise HTTPException(status_code=409, detail={
            "message": "Model is assigned to an agent and cannot be retired until governed migration/deactivation completes.",
            "agent_name": in_use["AgentName"], "agent_status": in_use["Status"],
        })
    usage = db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM dbo.TaskAssignment assignment JOIN dbo.Agent agent ON agent.AgentID=assignment.AgentID
             WHERE agent.ModelProvider=:provider AND agent.Model=:model AND agent.ModelVersion=:version
               AND assignment.Status='Active' AND assignment.ReleasedAtUtc IS NULL) AS ActiveAssignmentCount,
            (SELECT COUNT(*) FROM dbo.AgentExecution execution JOIN dbo.Agent agent ON agent.AgentID=execution.AgentID
             WHERE agent.ModelProvider=:provider AND agent.Model=:model AND agent.ModelVersion=:version
               AND execution.Status='Executing') AS RunningExecutionCount
    """), {"provider": model["ProviderName"], "model": model["ModelName"], "version": model["ModelVersion"]}).mappings().one()
    if int(usage["ActiveAssignmentCount"] or 0) or int(usage["RunningExecutionCount"] or 0):
        raise HTTPException(status_code=409, detail={
            "message": "Model retirement is blocked while assignments or executions reference the model.",
            "active_assignments": int(usage["ActiveAssignmentCount"] or 0),
            "running_executions": int(usage["RunningExecutionCount"] or 0),
        })
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(text("UPDATE dbo.AIModelCatalog SET Status='Retired',RetiredAtUtc=:now WHERE ModelCatalogID=:id"),
               {"now": now, "id": model_catalog_id})
    db.execute(text("""
        INSERT dbo.AIModelApproval(ModelApprovalID,ModelCatalogID,Decision,Reason,Evidence,DecidedByUserID)
        VALUES(:id,:model,'Retired',:reason,:evidence,:reviewer)
    """), {"id": uuid.uuid4(), "model": model_catalog_id,
          "reason": "Model retirement: " + body.reason.strip(), "evidence": body.evidence.strip(),
          "reviewer": user["sub"]})
    _audit(db, user, "AIModelRetired", model_catalog_id, {"reason": body.reason.strip(), "evidence": body.evidence.strip()})
    db.commit()
    return {"model_catalog_id": str(model_catalog_id), "status": "Retired", "retired_at_utc": now.isoformat()}


@router.get("/certification-dashboard", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def certification_dashboard(db: Session = Depends(get_db)):
    evaluation_rows = db.execute(text("""
        WITH Ranked AS (
            SELECT AgentID,EvaluationType,Score,Passed,CreatedAtUtc,
                   ROW_NUMBER() OVER(PARTITION BY AgentID,EvaluationType ORDER BY CreatedAtUtc DESC,EvaluationID DESC) AS rn
            FROM dbo.Evaluation
        )
        SELECT EvaluationType,COUNT(*) AS LatestEvaluationCount,
               SUM(CASE WHEN Passed=1 THEN 1 ELSE 0 END) AS LatestPassedCount,
               AVG(CONVERT(float,Score)) AS LatestAverageScore
        FROM Ranked WHERE rn=1 GROUP BY EvaluationType ORDER BY EvaluationType
    """)).mappings().all()
    skill_rows = db.execute(text("""
        SELECT ags.Status,COUNT(*) AS SkillAssignmentCount FROM dbo.AgentSkill ags
        GROUP BY ags.Status ORDER BY ags.Status
    """)).mappings().all()
    agent_totals = db.execute(text("""
        SELECT COUNT(*) AS AgentCount FROM dbo.Agent WHERE Status IN ('Provisioning','Active')
    """)).mappings().one()
    certified = db.execute(text("""
        SELECT COUNT(*) FROM dbo.Agent a WHERE a.Status IN ('Provisioning','Active')
          AND NOT EXISTS (
              SELECT required.EvaluationType FROM (VALUES('Capability'),('Safety'),('Security'),('Governance')) required(EvaluationType)
              WHERE NOT EXISTS (
                  SELECT 1 FROM dbo.Evaluation e
                  WHERE e.AgentID=a.AgentID AND e.EvaluationType=required.EvaluationType AND e.Passed=1
                    AND NOT EXISTS (SELECT 1 FROM dbo.Evaluation newer WHERE newer.AgentID=e.AgentID
                        AND newer.EvaluationType=e.EvaluationType
                        AND (newer.CreatedAtUtc>e.CreatedAtUtc OR (newer.CreatedAtUtc=e.CreatedAtUtc AND newer.EvaluationID>e.EvaluationID)))
              )
          )
    """)).scalar_one()
    active_totals = int(db.execute(text("SELECT COUNT(*) FROM dbo.Agent WHERE Status='Active'")).scalar_one() or 0)
    active_certified = int(db.execute(text("""
        SELECT COUNT(*) FROM dbo.Agent a WHERE a.Status='Active'
          AND NOT EXISTS (
              SELECT required.EvaluationType FROM (VALUES('Capability'),('Safety'),('Security'),('Governance')) required(EvaluationType)
              WHERE ISNULL((SELECT TOP 1 e.Passed FROM dbo.Evaluation e
                            WHERE e.AgentID=a.AgentID AND e.EvaluationType=required.EvaluationType
                            ORDER BY e.CreatedAtUtc DESC,e.EvaluationID DESC),0)<>1
          )
    """)).scalar_one() or 0)
    active_skill_rows = db.execute(text("""
        SELECT a.AgentID,a.WorkforceRoleCode,profile.RequiredSkillsJson,skill.Name AS SkillName,MAX(
            CASE WHEN agent_skill.Status='Active' THEN agent_skill.Proficiency ELSE 0 END
        ) AS ActiveProficiency
        FROM dbo.Agent a
        LEFT JOIN dbo.WorkforceRoleProfile profile ON profile.RoleCode=a.WorkforceRoleCode AND profile.Status='Active'
        LEFT JOIN dbo.AgentSkill agent_skill ON agent_skill.AgentID=a.AgentID
        LEFT JOIN dbo.Skill skill ON skill.SkillID=agent_skill.SkillID
        WHERE a.Status='Active'
        GROUP BY a.AgentID,a.WorkforceRoleCode,profile.RequiredSkillsJson,skill.Name
    """)).mappings().all()
    agent_requirements = {}
    for row in active_skill_rows:
        item = agent_requirements.setdefault(row["AgentID"], {"required": json.loads(row["RequiredSkillsJson"] or "[]"), "skills": {}})
        if row["SkillName"]:
            item["skills"][row["SkillName"]] = int(row["ActiveProficiency"] or 0)
    agents_with_requirements = [item for item in agent_requirements.values() if item["required"]]
    skill_ready = sum(
        all(
            item["skills"].get(skill["name"], 0) >= int(skill["minimum_proficiency"])
            for skill in item["required"]
        )
        for item in agents_with_requirements
    )
    trend_rows = db.execute(text("""
        SELECT YEAR(CreatedAtUtc) AS EvaluationYear,MONTH(CreatedAtUtc) AS EvaluationMonth,
               EvaluationType,COUNT(*) AS EvaluationCount,
               SUM(CASE WHEN Passed=1 THEN 1 ELSE 0 END) AS PassedCount
        FROM dbo.Evaluation
        GROUP BY YEAR(CreatedAtUtc),MONTH(CreatedAtUtc),EvaluationType
        ORDER BY EvaluationYear,EvaluationMonth,EvaluationType
    """)).mappings().all()
    return {
        "agent_count": int(agent_totals["AgentCount"] or 0),
        "fully_certified_agent_count": int(certified or 0),
        "certification_completion_percent": round((int(certified or 0) * 100 / int(agent_totals["AgentCount"])) if agent_totals["AgentCount"] else 0, 1),
        "skill_validation_status": [dict(row) for row in skill_rows],
        "evaluation_pass_rates": [
            {**dict(row), "pass_rate_percent": round((int(row["LatestPassedCount"] or 0) * 100 / int(row["LatestEvaluationCount"])) if row["LatestEvaluationCount"] else 0, 1)}
            for row in evaluation_rows
        ],
        "active_agent_certification_coverage": {
            "certified_agents": active_certified,
            "active_agents": active_totals,
            "coverage_percent": round(active_certified * 100 / active_totals, 1) if active_totals else None,
        },
        "active_agent_skill_coverage": {
            "agents_meeting_required_active_skills": int(skill_ready),
            "active_agents_with_role_requirements": len(agents_with_requirements),
            "coverage_percent": round(skill_ready * 100 / len(agents_with_requirements), 1) if agents_with_requirements else None,
        },
        "evaluation_trend": [dict(row) for row in trend_rows],
        "expiry": {"tracked": False, "label": "Expiry Not Tracked", "message": "Evaluation schema has no expiry date; do not infer certificate expiry."},
    }


@router.get("/phase8-readiness", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def phase8_readiness(db: Session = Depends(get_db)):
    prerequisite = bool(db.execute(text("""
        SELECT CASE WHEN OBJECT_ID('dbo.WorkforceReuseAssessment','U') IS NOT NULL THEN 1 ELSE 0 END
    """)).scalar_one())

    ownership_queries = {
        "Requirement": "SELECT COUNT(*) AS Total,COUNT(valid.UserID) AS Valid FROM dbo.Requirement row_data LEFT JOIN dbo.AppUser valid ON valid.UserID=row_data.CreatedByUserID",
        "Project": "SELECT COUNT(*) AS Total,COUNT(valid.UserID) AS Valid FROM dbo.Project row_data LEFT JOIN dbo.AppUser valid ON valid.UserID=row_data.CreatedByUserID",
        "Task": "SELECT COUNT(*) AS Total,COUNT(valid.UserID) AS Valid FROM dbo.Task row_data LEFT JOIN dbo.AppUser valid ON valid.UserID=row_data.CreatedByUserID",
        "Issue": "SELECT COUNT(*) AS Total,COUNT(valid.UserID) AS Valid FROM dbo.Issue row_data LEFT JOIN dbo.AppUser valid ON valid.UserID=row_data.OwnerUserID",
    }
    ownership = {}
    missing_owner_columns = []
    for table, query in ownership_queries.items():
        owner_column = "OwnerUserID" if table == "Issue" else "CreatedByUserID"
        column_exists = bool(db.execute(text("SELECT CASE WHEN COL_LENGTH(:table_name,:column_name) IS NULL THEN 0 ELSE 1 END"), {
            "table_name": f"dbo.{table}", "column_name": owner_column,
        }).scalar_one())
        if not column_exists:
            missing_owner_columns.append(f"{table}.{owner_column}")
            ownership[table] = {"valid_rows": 0, "total_rows": 0, "coverage_percent": None, "owner_column_present": False}
            continue
        row = db.execute(text(query)).mappings().one()
        total, valid = int(row["Total"] or 0), int(row["Valid"] or 0)
        ownership[table] = {
            "valid_rows": valid,
            "total_rows": total,
            "coverage_percent": round(100 * valid / total, 1) if total else None,
            "owner_column_present": True,
        }
    owner_total = sum(item["total_rows"] for item in ownership.values())
    owner_valid = sum(item["valid_rows"] for item in ownership.values())
    ownership_coverage = round(100 * owner_valid / owner_total, 1) if owner_total else None

    runtime_queries = {
        "TaskAssignment": "SELECT COUNT(*) AS Total,COUNT(CASE WHEN task.CreatedByUserID IS NOT NULL AND owner.UserID IS NOT NULL AND agent.AgentID IS NOT NULL THEN 1 END) AS Valid FROM dbo.TaskAssignment item LEFT JOIN dbo.Task task ON task.TaskID=item.TaskID LEFT JOIN dbo.AppUser owner ON owner.UserID=task.CreatedByUserID LEFT JOIN dbo.Agent agent ON agent.AgentID=item.AgentID",
        "AgentTaskQueue": "SELECT COUNT(*) AS Total,COUNT(CASE WHEN task.CreatedByUserID IS NOT NULL AND owner.UserID IS NOT NULL AND agent.AgentID IS NOT NULL THEN 1 END) AS Valid FROM dbo.AgentTaskQueue item LEFT JOIN dbo.Task task ON task.TaskID=item.TaskID LEFT JOIN dbo.AppUser owner ON owner.UserID=task.CreatedByUserID LEFT JOIN dbo.Agent agent ON agent.AgentID=item.AgentID",
        "AgentExecution": "SELECT COUNT(*) AS Total,COUNT(CASE WHEN task.CreatedByUserID IS NOT NULL AND owner.UserID IS NOT NULL AND agent.AgentID IS NOT NULL AND queue.QueueID IS NOT NULL THEN 1 END) AS Valid FROM dbo.AgentExecution item LEFT JOIN dbo.Task task ON task.TaskID=item.TaskID LEFT JOIN dbo.AppUser owner ON owner.UserID=task.CreatedByUserID LEFT JOIN dbo.Agent agent ON agent.AgentID=item.AgentID LEFT JOIN dbo.AgentTaskQueue queue ON queue.QueueID=item.QueueID",
        "AgentExecutionOutput": "SELECT COUNT(*) AS Total,COUNT(CASE WHEN task.CreatedByUserID IS NOT NULL AND owner.UserID IS NOT NULL THEN 1 END) AS Valid FROM dbo.AgentExecutionOutput item LEFT JOIN dbo.AgentExecution execution ON execution.ExecutionID=item.ExecutionID LEFT JOIN dbo.Task task ON task.TaskID=execution.TaskID LEFT JOIN dbo.AppUser owner ON owner.UserID=task.CreatedByUserID",
        "Deliverable": "SELECT COUNT(*) AS Total,COUNT(CASE WHEN project.CreatedByUserID IS NOT NULL AND owner.UserID IS NOT NULL AND (item.TaskID IS NULL OR task.TaskID IS NOT NULL) THEN 1 END) AS Valid FROM dbo.Deliverable item LEFT JOIN dbo.Project project ON project.ProjectID=item.ProjectID LEFT JOIN dbo.AppUser owner ON owner.UserID=project.CreatedByUserID LEFT JOIN dbo.Task task ON task.TaskID=item.TaskID AND task.ProjectID=item.ProjectID",
    }
    runtime = {}
    missing_runtime_tables = []
    missing_runtime_owner_columns = []
    for table, query in runtime_queries.items():
        exists = bool(db.execute(text("SELECT CASE WHEN OBJECT_ID(:name,'U') IS NOT NULL THEN 1 ELSE 0 END"), {
            "name": f"dbo.{table}",
        }).scalar_one())
        if not exists:
            missing_runtime_tables.append(table)
            runtime[table] = {"valid_rows": 0, "total_rows": 0, "coverage_percent": None, "table_present": False}
            continue
        required_owner_column = "Project.CreatedByUserID" if table == "Deliverable" else "Task.CreatedByUserID"
        if required_owner_column in missing_owner_columns:
            missing_runtime_owner_columns.append(required_owner_column)
            runtime[table] = {
                "valid_rows": 0, "total_rows": 0, "coverage_percent": None,
                "table_present": True, "lineage_available": False,
            }
            continue
        row = db.execute(text(query)).mappings().one()
        total, valid = int(row["Total"] or 0), int(row["Valid"] or 0)
        runtime[table] = {
            "valid_rows": valid,
            "total_rows": total,
            "coverage_percent": round(100 * valid / total, 1) if total else None,
            "table_present": True,
            "lineage_available": True,
        }
    runtime_total = sum(item["total_rows"] for item in runtime.values())
    runtime_valid = sum(item["valid_rows"] for item in runtime.values())
    runtime_coverage = round(100 * runtime_valid / runtime_total, 1) if runtime_total else None

    policy_rows = db.execute(text("""
        SELECT required.TableName,
               CASE WHEN EXISTS (
                   SELECT 1 FROM sys.security_policies policy
                   JOIN sys.security_predicates predicate ON predicate.object_id=policy.object_id
                   WHERE policy.is_enabled=1
                     AND predicate.target_object_id=OBJECT_ID('dbo.'+required.TableName)
               ) THEN 1 ELSE 0 END AS HasEnabledPredicate
        FROM (VALUES
            ('Requirement'),('Project'),('Task'),('Issue'),('Approval'),('Notification'),
            ('TaskAssignment'),('TaskDependency'),('Deliverable'),('Evaluation'),
            ('AgentTaskQueue'),('AgentExecution'),('AgentExecutionOutput')
        ) required(TableName)
    """)).mappings().all()
    policies = [{"table": row["TableName"], "covered": bool(row["HasEnabledPredicate"])} for row in policy_rows]
    policy_coverage = round(100 * sum(item["covered"] for item in policies) / len(policies), 1) if policies else 0.0
    rls_enabled = bool(db.execute(text("SELECT COUNT(*) FROM sys.security_policies WHERE is_enabled=1")).scalar_one())

    workforce = None
    if prerequisite:
        counts = db.execute(text("""
            SELECT COUNT(DISTINCT CASE WHEN Classification='Ready Candidate' THEN AgentID END) AS ReadyCandidates,
                   COUNT(DISTINCT CASE WHEN Classification='Strong Candidate' THEN AgentID END) AS StrongCandidates,
                   COUNT(DISTINCT CASE WHEN Classification='Upskill Candidate' THEN AgentID END) AS UpskillCandidates,
                   COUNT(DISTINCT CASE WHEN AssessmentStatus IN ('Approved','Completed','Assigned') AND MatchScore>=50
                                       THEN CONCAT(CONVERT(varchar(36),ProjectID),':',RoleCode) END) AS RequestsPrevented,
                   COUNT(DISTINCT CASE WHEN AssessmentStatus='Assigned' THEN AgentID END) AS ReusedAgents
            FROM dbo.WorkforceReuseAssessment
        """)).mappings().one()
        request_count = int(db.execute(text("SELECT COUNT(*) FROM dbo.WorkforceRequest WHERE Status NOT IN ('Filled','Rejected','Cancelled')")).scalar_one() or 0)
        utilization = db.execute(text("""
            SELECT AVG(CAST(CASE WHEN CurrentWorkload<0 THEN 0 WHEN CurrentWorkload>100 THEN 100 ELSE CurrentWorkload END AS float))
            FROM dbo.Agent WHERE Status='Active'
        """)).scalar_one()
        prevented = int(counts["RequestsPrevented"] or 0)
        workforce = {
            "ready_candidates": int(counts["ReadyCandidates"] or 0),
            "strong_candidates": int(counts["StrongCandidates"] or 0),
            "upskill_candidates": int(counts["UpskillCandidates"] or 0),
            "workforce_requests": request_count,
            "reused_agents": int(counts["ReusedAgents"] or 0),
            "workforce_reuse_percent": round(100 * prevented / (prevented + request_count), 1) if prevented + request_count else 0.0,
            "utilization_percent": round(float(utilization or 0), 1),
        }

    assignment_table_present = bool(db.execute(text("SELECT CASE WHEN OBJECT_ID('dbo.TaskAssignment','U') IS NULL THEN 0 ELSE 1 END")).scalar_one())
    assignment_validation = db.execute(text("""
        WITH ActiveAssignmentEvidence AS (
            SELECT assignment.TaskAssignmentID,assignment.TaskID,agent.Status AS AgentStatus,
                   CASE WHEN NOT EXISTS (
                   SELECT required.EvaluationType
                   FROM (VALUES('Capability'),('Safety'),('Security'),('Governance')) required(EvaluationType)
                   WHERE ISNULL((
                       SELECT TOP 1 evaluation.Passed FROM dbo.Evaluation evaluation
                       WHERE evaluation.AgentID=agent.AgentID AND evaluation.EvaluationType=required.EvaluationType
                       ORDER BY evaluation.CreatedAtUtc DESC,evaluation.EvaluationID DESC
                   ),0)<>1
                   ) THEN 0 ELSE 1 END AS IsCertified,
                   CASE WHEN agent.CurrentWorkload<100
                         AND (SELECT COUNT(*) FROM dbo.TaskAssignment other_assignment
                              WHERE other_assignment.AgentID=agent.AgentID AND other_assignment.Status='Active'
                                AND other_assignment.ReleasedAtUtc IS NULL)<=agent.ConcurrentTaskLimit
                        THEN 1 ELSE 0 END AS HasCapacity,
                   CASE WHEN EXISTS (
                   SELECT 1 FROM dbo.AuditLog audit
                   WHERE audit.ResourceID=CONVERT(nvarchar(200),assignment.TaskAssignmentID)
                      OR (audit.ResourceID=CONVERT(nvarchar(200),assignment.TaskID) AND audit.Action LIKE '%Assign%')
                   ) THEN 1 ELSE 0 END AS HasAudit
            FROM dbo.TaskAssignment assignment
            JOIN dbo.Agent agent ON agent.AgentID=assignment.AgentID
            WHERE assignment.Status='Active' AND assignment.ReleasedAtUtc IS NULL
        )
        SELECT COUNT(*) AS ActiveAssignments,
               SUM(CASE WHEN AgentStatus='Active' THEN 1 ELSE 0 END) AS ActiveAgentAssignments,
               SUM(CASE WHEN AgentStatus='Active' AND IsCertified=1 THEN 1 ELSE 0 END) AS CertifiedAgentAssignments,
               SUM(CASE WHEN AgentStatus='Active' AND HasCapacity=1 THEN 1 ELSE 0 END) AS CapacityAndWorkloadAssignments,
               SUM(HasAudit) AS AuditedAssignments
        FROM ActiveAssignmentEvidence
    """)).mappings().one() if assignment_table_present else {
        "ActiveAssignments": 0, "ActiveAgentAssignments": 0,
        "CertifiedAgentAssignments": 0, "CapacityAndWorkloadAssignments": 0,
        "AuditedAssignments": 0,
    }
    if not assignment_table_present:
        missing_runtime_tables.append("TaskAssignment")
    active_assignment_count = int(assignment_validation["ActiveAssignments"] or 0)
    assignment_validation_result = {
        "active_assignments": active_assignment_count,
        "active_agent_assignments": int(assignment_validation["ActiveAgentAssignments"] or 0),
        "certified_agent_assignments": int(assignment_validation["CertifiedAgentAssignments"] or 0),
        "capacity_and_workload_assignments": int(assignment_validation["CapacityAndWorkloadAssignments"] or 0),
        "audited_assignments": int(assignment_validation["AuditedAssignments"] or 0),
        "audit_coverage_percent": round(100 * int(assignment_validation["AuditedAssignments"] or 0) / active_assignment_count, 1) if active_assignment_count else None,
    }

    checks = {
        "phase7_migration_applied": prerequisite,
        "historical_ownership_coverage_100_percent": ownership_coverage == 100.0 and not missing_owner_columns,
        "runtime_ownership_coverage_100_percent": runtime_coverage == 100.0,
        "all_rls_tables_have_enabled_predicates": policy_coverage == 100.0,
        "runtime_tables_present": not missing_runtime_tables,
        "active_assignments_certified": active_assignment_count > 0 and assignment_validation_result["certified_agent_assignments"] == active_assignment_count,
        "active_assignments_with_capacity_and_workload": active_assignment_count > 0 and assignment_validation_result["capacity_and_workload_assignments"] == active_assignment_count,
        "active_assignments_audited": active_assignment_count > 0 and assignment_validation_result["audited_assignments"] == active_assignment_count,
    }
    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "phase7_migration_applied": prerequisite,
        "ownership": {"coverage_percent": ownership_coverage, "valid_rows": owner_valid, "total_rows": owner_total, "tables": ownership},
        "missing_owner_columns": missing_owner_columns,
        "runtime_ownership": {"coverage_percent": runtime_coverage, "valid_rows": runtime_valid, "total_rows": runtime_total, "tables": runtime, "missing_tables": missing_runtime_tables, "missing_owner_columns": sorted(set(missing_runtime_owner_columns))},
        "rls": {"enabled": rls_enabled, "policy_coverage_percent": policy_coverage, "tables": policies, "will_enable_rls": False},
        "recommendation": "GO for a separately approved RLS deployment review; do not enable from this dashboard." if all(checks.values()) else "NO-GO: resolve every listed ownership, runtime lineage, RLS predicate, and migration prerequisite gap before separate deployment review.",
        "checks": checks,
        "workforce": workforce,
        "assignment_validation": assignment_validation_result,
        "execution_adapter_enablement": {
            "secret_vault_integration": "not_configured",
            "connectivity_probe": "unavailable",
            "network_probe_performed": False,
            "supported_providers": [item[0] for item in ADAPTERS.values()],
            "runtime_enabled": False,
            "blocker": "A production vault resolver and provider-specific authenticated health clients are not configured; no health state is simulated.",
        },
    }


@router.get("/rls-readiness/package", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def export_rls_readiness_package(db: Session = Depends(get_db)):
    readiness = phase8_readiness(db)
    checks = readiness["checks"]
    return {
        "package_type": "RLS readiness review",
        "generated_at_utc": readiness["as_of_utc"],
        "read_only": True,
        "enable_rls": False,
        "recommendation": readiness["recommendation"],
        "ownership": readiness["ownership"],
        "runtime_ownership": readiness["runtime_ownership"],
        "predicate_coverage": readiness["rls"],
        "checks": checks,
        "risk_assessment": {
            "risk_level": "High" if not all(checks.values()) else "Review Required",
            "unresolved_owner_records": readiness["ownership"]["total_rows"] - readiness["ownership"]["valid_rows"],
            "runtime_lineage_complete": bool(checks.get("runtime_ownership_coverage_100_percent", False)),
            "predicate_coverage_complete": bool(checks.get("all_rls_tables_have_enabled_predicates", False)),
            "statement": "This package is evidence for review only. It does not enable or modify SQL Server RLS.",
        },
        "deployment_checklist": [
            "Resolve historical owner records from approved identity evidence and independently verify remediation SQL.",
            "Validate parent lineage for assignment, queue, execution, output, evaluation, and deliverable records.",
            "Design current single-organization role predicates for every required table and review them separately.",
            "Validate session-context identity establishment and pool cleanup on every database connection.",
            "Run positive and negative authorization tests in an isolated DEV database and obtain change approval.",
            "Deploy only through a separately authorized database change; this API performs no DDL.",
        ],
        "rollback_checklist": [
            "Capture the approved pre-deployment policy inventory and database backup reference.",
            "Use only a separately reviewed rollback script that disables/removes the intended policies.",
            "Verify application access and audit evidence after rollback; preserve ownership data changes separately.",
            "Do not execute rollback SQL from this report endpoint.",
        ],
    }


def _phase9_readiness_snapshot(db: Session) -> dict:
    phase8 = phase8_readiness(db)
    approved_models = int(db.execute(text("""
        SELECT COUNT(*) FROM dbo.AIModelCatalog model
        JOIN dbo.AIModelProvider provider ON provider.ProviderID=model.ProviderID
        WHERE model.Status='Approved' AND provider.Status='Active'
    """)).scalar_one() or 0)
    certification = certification_dashboard(db)
    latest_skills = certification["active_agent_skill_coverage"]
    active_cert = certification["active_agent_certification_coverage"]

    adapters = db.execute(text("""
        SELECT config.ProviderCode,config.Status,latest.Status AS HealthStatus
        FROM dbo.ExecutionAdapterConfig config
        OUTER APPLY (
            SELECT TOP 1 check_row.Status FROM dbo.ExecutionAdapterHealthCheck check_row
            WHERE check_row.AdapterConfigID=config.AdapterConfigID
            ORDER BY check_row.CheckedAtUtc DESC,check_row.HealthCheckID DESC
        ) latest
    """)).mappings().all()
    configured_adapter_count = sum(row["Status"] == "Configured" for row in adapters)
    healthy_adapter_count = sum(row["Status"] == "Configured" and row["HealthStatus"] == "Healthy" for row in adapters)

    runtime_table_names = ("TaskAssignment", "AgentTaskQueue", "AgentExecution", "AgentExecutionOutput", "Deliverable")
    runtime_counts = {}
    missing_tables = []
    for table in runtime_table_names:
        exists = bool(db.execute(text("SELECT CASE WHEN OBJECT_ID(:name,'U') IS NULL THEN 0 ELSE 1 END"), {
            "name": f"dbo.{table}",
        }).scalar_one())
        if not exists:
            missing_tables.append(table)
            runtime_counts[table] = None
            continue
        if table == "TaskAssignment":
            query = "SELECT COUNT(*) FROM dbo.TaskAssignment WHERE Status='Active' AND ReleasedAtUtc IS NULL"
        elif table == "AgentTaskQueue":
            query = "SELECT COUNT(*) FROM dbo.AgentTaskQueue WHERE Status IN ('Queued','Retry')"
        elif table == "AgentExecution":
            query = "SELECT COUNT(*) FROM dbo.AgentExecution WHERE Status IN ('Executing','OutputSubmitted','Review')"
        elif table == "AgentExecutionOutput":
            query = "SELECT COUNT(*) FROM dbo.AgentExecutionOutput"
        else:
            query = "SELECT COUNT(*) FROM dbo.Deliverable WHERE Status='Accepted' AND ArtifactHash IS NOT NULL"
        runtime_counts[table] = int(db.execute(text(query)).scalar_one() or 0)

    support_tables = ("AgentRuntimeCredential", "AIModelCatalog", "AIModelProvider", "ExecutionAdapterConfig", "ExecutionAdapterHealthCheck")
    missing_support_tables = [
        table for table in support_tables
        if not bool(db.execute(text("SELECT CASE WHEN OBJECT_ID(:name,'U') IS NULL THEN 0 ELSE 1 END"), {
            "name": f"dbo.{table}",
        }).scalar_one())
    ]
    credential_table_exists = "AgentRuntimeCredential" not in missing_support_tables
    missing_tables.extend(missing_support_tables)
    eligible_active_agents: set[str] = set()
    agent_rows = db.execute(text("""
        SELECT agent.AgentID,agent.Status,agent.CurrentWorkload,agent.ConcurrentTaskLimit,
               agent.WorkforceRoleCode,profile.RequiredSkillsJson,
               (SELECT COUNT(*) FROM dbo.TaskAssignment assignment
                WHERE assignment.AgentID=agent.AgentID AND assignment.Status='Active' AND assignment.ReleasedAtUtc IS NULL) AS ActiveAssignments
        FROM dbo.Agent agent
        JOIN dbo.WorkforceRoleProfile profile ON profile.RoleCode=agent.WorkforceRoleCode AND profile.Status='Active'
        WHERE agent.Status='Active'
    """)).mappings().all()
    skill_rows = db.execute(text("""
        SELECT agent_skill.AgentID,skill.Name,MAX(agent_skill.Proficiency) AS Proficiency
        FROM dbo.AgentSkill agent_skill JOIN dbo.Skill skill ON skill.SkillID=agent_skill.SkillID
        WHERE agent_skill.Status='Active' GROUP BY agent_skill.AgentID,skill.Name
    """)).mappings().all()
    skills_by_agent: dict[str, dict[str, int]] = {}
    for row in skill_rows:
        skills_by_agent.setdefault(str(row["AgentID"]), {})[row["Name"]] = int(row["Proficiency"])
    passed_rows = db.execute(text("""
        WITH Ranked AS (
            SELECT AgentID,EvaluationType,Passed,
                   ROW_NUMBER() OVER(PARTITION BY AgentID,EvaluationType ORDER BY CreatedAtUtc DESC,EvaluationID DESC) AS rn
            FROM dbo.Evaluation
        )
        SELECT AgentID,EvaluationType FROM Ranked WHERE rn=1 AND Passed=1
    """)).mappings().all()
    passed_by_agent: dict[str, set[str]] = {}
    for row in passed_rows:
        passed_by_agent.setdefault(str(row["AgentID"]), set()).add(row["EvaluationType"])
    required_certifications = {"Capability", "Safety", "Security", "Governance"}
    for row in agent_rows:
        agent_key = str(row["AgentID"])
        profile = {"RequiredSkillsJson": row["RequiredSkillsJson"] or "[]"}
        if (float(row["CurrentWorkload"] or 0) < 100
                and int(row["ActiveAssignments"] or 0) < int(row["ConcurrentTaskLimit"] or 1)
                and required_certifications.issubset(passed_by_agent.get(agent_key, set()))
                and agent_meets_profile(profile, skills_by_agent.get(agent_key, {}))):
            eligible_active_agents.add(agent_key)
    active_assignment_agents = [] if "TaskAssignment" in missing_tables else db.execute(text("""
        SELECT AgentID FROM dbo.TaskAssignment
        WHERE Status='Active' AND ReleasedAtUtc IS NULL
    """)).scalars().all()
    assignments_ready = sum(str(agent_id) in eligible_active_agents for agent_id in active_assignment_agents)
    queue_ready = 0
    execution_ready = 0
    if "AgentTaskQueue" not in missing_tables and not missing_support_tables:
        queue_rows = db.execute(text("""
            SELECT queue.AgentID
            FROM dbo.AgentTaskQueue queue
            JOIN dbo.AgentRuntimeCredential credential
              ON credential.AgentID=queue.AgentID AND credential.Status='Active'
            JOIN dbo.Task task ON task.TaskID=queue.TaskID AND task.AssignedAgentID=queue.AgentID
            JOIN dbo.Agent agent ON agent.AgentID=queue.AgentID
            JOIN dbo.AIModelCatalog model
              ON model.ModelName=agent.Model AND model.ModelVersion=agent.ModelVersion AND model.Status='Approved'
            JOIN dbo.AIModelProvider provider
              ON provider.ProviderID=model.ProviderID AND provider.ProviderName=agent.ModelProvider AND provider.Status='Active'
            JOIN dbo.ExecutionAdapterConfig adapter
              ON adapter.ModelCatalogID=model.ModelCatalogID AND adapter.Status='Configured'
            JOIN dbo.ExecutionAdapterHealthCheck health
              ON health.AdapterConfigID=adapter.AdapterConfigID AND health.Status='Healthy'
            WHERE queue.Status IN ('Queued','Retry')
              AND NOT EXISTS (
                  SELECT 1 FROM dbo.ExecutionAdapterHealthCheck newer
                  WHERE newer.AdapterConfigID=health.AdapterConfigID
                    AND (newer.CheckedAtUtc>health.CheckedAtUtc OR
                         (newer.CheckedAtUtc=health.CheckedAtUtc AND newer.HealthCheckID>health.HealthCheckID))
              )
        """)).scalars().all()
        queue_ready = sum(str(agent_id) in eligible_active_agents for agent_id in queue_rows)

    if "AgentExecution" not in missing_tables and not missing_support_tables:
        execution_agents = db.execute(text("""
            SELECT agent.AgentID
            FROM dbo.Agent agent
            JOIN dbo.AgentRuntimeCredential credential
              ON credential.AgentID=agent.AgentID AND credential.Status='Active'
            JOIN dbo.AIModelCatalog model
              ON model.ModelName=agent.Model AND model.ModelVersion=agent.ModelVersion AND model.Status='Approved'
            JOIN dbo.AIModelProvider provider
              ON provider.ProviderID=model.ProviderID AND provider.ProviderName=agent.ModelProvider AND provider.Status='Active'
            JOIN dbo.ExecutionAdapterConfig adapter
              ON adapter.ModelCatalogID=model.ModelCatalogID AND adapter.Status='Configured'
            JOIN dbo.ExecutionAdapterHealthCheck health
              ON health.AdapterConfigID=adapter.AdapterConfigID AND health.Status='Healthy'
            WHERE agent.Status='Active'
              AND NOT EXISTS (
                  SELECT 1 FROM dbo.ExecutionAdapterHealthCheck newer
                  WHERE newer.AdapterConfigID=health.AdapterConfigID
                    AND (newer.CheckedAtUtc>health.CheckedAtUtc OR
                         (newer.CheckedAtUtc=health.CheckedAtUtc AND newer.HealthCheckID>health.HealthCheckID))
              )
        """)).scalars().all()
        execution_ready = sum(str(agent_id) in eligible_active_agents for agent_id in execution_agents)

    assignment = phase8["assignment_validation"]
    ownership_complete = phase8["ownership"]["coverage_percent"] == 100.0
    runtime_lineage_complete = phase8["runtime_ownership"]["coverage_percent"] == 100.0
    active_skill_percent = latest_skills["coverage_percent"]
    active_cert_percent = active_cert["coverage_percent"]
    gates = {
        "phase7_migration": phase8["phase7_migration_applied"],
        "ownership_complete": ownership_complete,
        "runtime_lineage_complete": runtime_lineage_complete,
        "approved_models_available": approved_models > 0,
        "certified_active_agent_available": active_cert["certified_agents"] > 0,
        "active_required_skills_available": latest_skills["agents_meeting_required_active_skills"] > 0,
        "healthy_execution_adapter_available": healthy_adapter_count > 0,
        "runtime_tables_present": not missing_tables,
        "runtime_credentials_table_present": credential_table_exists,
        "enabled_rls_predicate_coverage_complete": phase8["rls"]["policy_coverage_percent"] == 100.0,
    }
    governance_checks = [gates["phase7_migration"], gates["approved_models_available"]]
    workforce_checks = [gates["certified_active_agent_available"], gates["active_required_skills_available"]]
    runtime_checks = [gates["healthy_execution_adapter_available"], gates["runtime_tables_present"], queue_ready > 0]
    security_checks = [gates["ownership_complete"], gates["runtime_lineage_complete"], gates["enabled_rls_predicate_coverage_complete"]]
    operational_checks = governance_checks + workforce_checks + runtime_checks

    def score(checks: list[bool]) -> dict:
        return {"passed": sum(checks), "total": len(checks), "percent": round(100 * sum(checks) / len(checks), 1) if checks else None}

    metrics = {
        "governance_readiness": score(governance_checks),
        "workforce_readiness": score(workforce_checks),
        "runtime_readiness": score(runtime_checks),
        "security_readiness": score(security_checks),
        "operational_readiness": score(operational_checks),
        "overall_platform_readiness": score(governance_checks + workforce_checks + runtime_checks + security_checks),
    }
    blockers = [name for name, passed in gates.items() if not passed]
    if configured_adapter_count == 0:
        blockers.append("execution_adapter_not_configured")
    if healthy_adapter_count == 0:
        blockers.append("no_real_healthy_provider_probe")
    if not active_cert["certified_agents"]:
        blockers.append("no_certified_active_agents")
    if not latest_skills["agents_meeting_required_active_skills"]:
        blockers.append("no_active_agents_meet_role_skill_requirements")
    if not queue_ready:
        blockers.append("no_runtime_queue_items_ready")
    if not credential_table_exists:
        blockers.append("runtime_credential_table_missing")

    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "gates": gates,
        "blockers": sorted(set(blockers)),
        "phase8": phase8,
        "runtime": {
            "assignments_ready": assignments_ready,
            "assignments_total": assignment["active_assignments"],
            "queue_ready": queue_ready,
            "queue_records": runtime_counts.get("AgentTaskQueue"),
            "execution_ready": execution_ready,
            "execution_records": runtime_counts.get("AgentExecution"),
            "deliverables_ready": runtime_counts.get("Deliverable"),
            "table_counts": runtime_counts,
            "missing_tables": missing_tables,
        },
        "workforce": {
            **(phase8["workforce"] or {}),
            "active_skill_coverage_percent": active_skill_percent,
            "active_certification_coverage_percent": active_cert_percent,
        },
        "models": {"approved_model_count": approved_models, "configured_adapter_count": configured_adapter_count, "healthy_adapter_count": healthy_adapter_count},
        "security": {"rls_enabled": phase8["rls"]["enabled"], "rls_will_be_enabled": False,
                     "ownership_coverage_percent": phase8["ownership"]["coverage_percent"],
                     "runtime_ownership_coverage_percent": phase8["runtime_ownership"]["coverage_percent"],
                     "predicate_coverage_percent": phase8["rls"]["policy_coverage_percent"]},
        "recommendation": "NO-GO" if blockers else "Ready for separate, authorized operational review",
        "controls_changed": False,
    }


@router.get("/phase9-readiness", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def phase9_readiness(db: Session = Depends(get_db)):
    return _phase9_readiness_snapshot(db)


def _phase10_launch_snapshot(db: Session) -> dict:
    migration_validation = validate_migration_24(db)
    ownership = ownership_remediation_report(db)
    deployment = adapter_deployment_package(db)
    campaign = certification_campaign(db)
    readiness = _phase9_readiness_snapshot(db)
    models = model_governance_dashboard(db)
    certs = certification_dashboard(db)
    runtime = readiness["runtime"]

    ownership_ok = ownership["candidate_count_validated"] and ownership["manual_review_rows"] == 0 and ownership["total_null_owner_rows"] == 0
    adapter_ok = any(provider["health_status"] == "Healthy" for provider in list_execution_adapters(db))
    model_ok = int(models["lifecycle"] and next((row["ModelCount"] for row in models["lifecycle"] if row["Status"] == "Approved"), 0) or 0) > 0
    campaign_agents = [agent for role in campaign["campaigns"] for agent in role["agents"]]
    certification_ok = any(agent["readiness"] == "Ready" for agent in campaign_agents)
    runtime_ok = bool(runtime["assignments_ready"] and runtime["queue_ready"] and runtime["execution_ready"] and runtime["deliverables_ready"])
    rls_status = "Enabled" if readiness["security"]["rls_enabled"] else "Disabled"
    blockers = []
    if not ownership_ok:
        blockers.append("Ownership remediation is not complete or the candidate set is not fully validated.")
    if not migration_validation["migration_already_applied"]:
        blockers.append("Migration 24 has not been applied through an approved deployment.")
    if not adapter_ok:
        blockers.append("No configured adapter has a latest real Healthy provider probe.")
    if not model_ok:
        blockers.append("No approved active-provider model is available.")
    if not certification_ok:
        blockers.append("No campaign agent currently passes active skills, evidence, certification, and approved-model gates.")
    if not runtime_ok:
        blockers.append("Assignments, eligible queue, executions, or accepted deliverables are absent or blocked.")
    if rls_status != "Disabled":
        blockers.append("RLS is enabled; confirm this state through the separately approved security deployment process.")
    phase8 = readiness["phase8"]
    domains = {
        "governance_readiness": migration_validation["static_validation"] == "PASS" and migration_validation["dependencies_ready"] and migration_validation["rollback_path"]["validated"],
        "workforce_readiness": certification_ok,
        "runtime_readiness": runtime_ok,
        "security_readiness": phase8["ownership"]["coverage_percent"] == 100.0 and phase8["runtime_ownership"]["coverage_percent"] == 100.0,
        "model_readiness": model_ok,
        "adapter_readiness": adapter_ok,
        "ownership_readiness": ownership_ok and phase8["ownership"]["coverage_percent"] == 100.0,
        "rls_readiness": not readiness["security"]["rls_enabled"] and readiness["security"]["predicate_coverage_percent"] == 100.0,
    }
    overall_readiness_percent = round(100 * sum(domains.values()) / len(domains), 1)
    recommendation = "NO-GO" if blockers else "Ready for separately authorized launch review"
    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "recommendation": recommendation,
        "ownership_status": {
            "candidate_count": ownership["total_null_owner_rows"],
            "exact_guid_matches": ownership["resolvable_exact_guid_rows"],
            "unresolved_records": ownership["manual_review_rows"],
            "coverage_percent": readiness["security"]["ownership_coverage_percent"],
            "candidate_set_validated": ownership["candidate_count_validated"],
        },
        "adapter_status": {
            "configured_count": sum(item["configuration_status"] == "Configured" for item in deployment["providers"]),
            "healthy_count": sum(item["health_status"] == "Healthy" for item in list_execution_adapters(db)),
            "provider_calls_performed": False,
        },
        "model_status": {"approved_count": sum(int(row["ModelCount"]) for row in models["lifecycle"] if row["Status"] == "Approved"),
                         "pending_reviews": models["pending_reviews"], "approval_sla": models["approval_sla"]},
        "certification_status": {
            "active_certification_coverage": certs["active_agent_certification_coverage"],
            "active_skill_coverage": certs["active_agent_skill_coverage"],
            "campaign_ready_agents": sum(agent["readiness"] == "Ready" for agent in campaign_agents),
            "campaign_agents": len(campaign_agents),
        },
        "runtime_status": runtime,
        "rls_status": {"status": rls_status, "enabled_predicate_coverage_percent": readiness["security"]["predicate_coverage_percent"], "changed": False},
        "blockers": blockers,
        "readiness_domains": domains,
        "overall_readiness_percent": overall_readiness_percent,
        "migration_validation": migration_validation,
        "actions_performed": [],
    }


@router.get("/phase10-launch-readiness", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def phase10_launch_readiness(db: Session = Depends(get_db)):
    return _phase10_launch_snapshot(db)


@router.get("/activation-runbook", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def activation_runbook(db: Session = Depends(get_db)):
    launch = _phase10_launch_snapshot(db)
    return {
        "generated_at_utc": launch["as_of_utc"],
        "recommendation": launch["recommendation"],
        "read_only": True,
        "checklists": {
            "model_onboarding": [
                "Confirm provider and exact model/version against approved contract and security evidence.",
                "Submit a pending proposal with business justification and evidence.",
                "A separate authorized reviewer records approval or rejection; proposer cannot self-approve.",
                "Review usage/retirement impact before changing a model lifecycle state.",
            ],
            "certification": [
                "Confirm installed active role profile and required skills.",
                "Assign and independently approve each skill using evidence-backed review.",
                "Record latest Capability, Safety, Security, and Governance evaluations with evidence.",
                "Resolve every campaign blocking-evidence item; no expiry is inferred.",
            ],
            "activation": [
                "Require an active role profile, active skills at minimum proficiency, approved model/version, and latest passing evaluations.",
                "Review capacity, authorization, tool scope, risk controls, and activation blockers.",
                "Obtain a separate authorized human activation approval with rationale.",
                "This generated runbook does not activate an agent.",
            ],
            "runtime_validation": [
                "Validate TaskAssignment and current agent qualification/capacity.",
                "Validate queue eligibility, active runtime credential, approved model, and latest real Healthy adapter probe.",
                "Observe genuine AgentExecution and output records from a trusted worker.",
                "Require independent review and accepted Deliverable with artifact hash.",
                "Do not create sample executions, outputs, or deliverables to satisfy readiness.",
            ],
            "rollback": [
                "Stop new queue claims through the separately authorized runtime operator procedure.",
                "Preserve audit, execution, and artifact history; do not delete or rewrite runtime records.",
                "Revoke runtime credentials and disable adapter configuration only under approved change control.",
                "Use the separately reviewed database/RLS rollback plan; this runbook executes no SQL or RLS changes.",
            ],
        },
        "launch_snapshot": launch,
    }


@router.get("/executive-readiness/{view}", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def executive_readiness(view: Literal["CEO", "COO", "CIO"], db: Session = Depends(get_db)):
    snapshot = _phase9_readiness_snapshot(db)
    focus_by_view = {
        "CEO": ("governance_readiness", "workforce_readiness", "runtime_readiness", "security_readiness", "operational_readiness", "overall_platform_readiness"),
        "COO": ("workforce_readiness", "runtime_readiness", "operational_readiness"),
        "CIO": ("governance_readiness", "runtime_readiness", "security_readiness", "overall_platform_readiness"),
    }
    return {
        "view": view,
        "as_of_utc": snapshot["as_of_utc"],
        "scorecards": {key: snapshot["metrics"][key] for key in focus_by_view[view]},
        "blockers": snapshot["blockers"],
        "recommendation": snapshot["recommendation"],
        "verified_metrics_only": True,
    }


@router.get("/ownership-remediation/approval-document", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def export_ownership_approval_document(db: Session = Depends(get_db)):
    package = export_ownership_approval_package(db)
    summary = package["summary"]
    lines = [
        "# Historical Ownership Remediation Approval Package",
        "",
        f"Generated: {package['generated_at_utc']}",
        "Status: Review only. No changes have been applied.",
        "",
        "## Summary",
        f"- Candidate records: {summary['candidate_count']} (expected {summary['expected_candidate_count']})",
        f"- Exact GUID matches: {summary['exact_guid_match_count']}",
        f"- Unresolved records: {summary['unresolved_count']}",
        f"- Ownership coverage: {summary['ownership_coverage_percent']}%",
        f"- Ownership risk score: {summary['ownership_risk_score']}",
        f"- Recommendation: {summary['recommendation']}",
        "",
        "## Candidate Verification",
        "| Table | Record ID | Legacy owner | Candidate User ID | Matched user | Exact GUID match |",
        "|---|---|---|---|---|---|",
    ]
    for row in package["verification_report"]:
        values = [row["table"], row["record_id"], row["legacy_created_by"], row["candidate_user_id"], row["matched_email"], "Yes" if row["resolvable_exact_guid"] else "No"]
        lines.append("| " + " | ".join(str(value or "Not recorded").replace("|", "\\|") for value in values) + " |")
    lines.extend(["", "## Review Checklist"])
    lines.extend(f"- [ ] {item}" for item in package["approval_checklist"])
    lines.extend(["", "## Remediation SQL", "```sql", package["remediation_sql"], "```", "", "## Rollback SQL", "```sql", package["rollback_sql"], "```", "", "Neither SQL block is executed by this package."])
    return {"filename": "ownership-remediation-approval.md", "content_type": "text/markdown", "document": "\n".join(lines), "read_only": True}


CERTIFICATION_CAMPAIGN_ROLES = (
    {"title": "AI Business Analyst", "codes": {"BUSINESS_ANALYST", "AI_BUSINESS_ANALYST"}, "name_terms": ("business analyst",)},
    {"title": "AI Solution Architect", "codes": {"SOLUTION_ARCHITECT", "AI_SOLUTION_ARCHITECT"}, "name_terms": ("solution architect",)},
    {"title": "AI Data Analyst", "codes": {"DATA_ANALYST", "AI_DATA_ANALYST"}, "name_terms": ("data analyst",)},
    {"title": "Software Developer", "codes": {"SOFTWARE_DEVELOPER"}, "name_terms": ("software developer",)},
    {"title": "AI QA Engineer", "codes": {"QA_ENGINEER", "AI_QA_ENGINEER"}, "name_terms": ("quality assurance engineer", "qa engineer")},
)


@router.get("/certification-campaign", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def certification_campaign(db: Session = Depends(get_db)):
    profiles = db.execute(text("""
        SELECT RoleCode,PositionName,RequiredSkillsJson FROM dbo.WorkforceRoleProfile WHERE Status='Active'
    """)).mappings().all()
    agents = db.execute(text("""
        SELECT agent.AgentID,agent.AgentName,agent.WorkforceRoleCode,agent.Status,agent.ModelProvider,agent.Model,agent.ModelVersion,agent.CurrentWorkload,agent.ConcurrentTaskLimit,
               (SELECT COUNT(*) FROM dbo.TaskAssignment assignment
            WHERE assignment.AgentID=agent.AgentID AND assignment.Status='Active' AND assignment.ReleasedAtUtc IS NULL) AS ActiveAssignments
        FROM dbo.Agent agent WHERE agent.Status IN ('Active','Provisioning')
    """)).mappings().all()
    campaigns = []
    for campaign_role in CERTIFICATION_CAMPAIGN_ROLES:
        matching_profiles = [
            row for row in profiles
            if row["RoleCode"] in campaign_role["codes"]
            or any(term in (row["PositionName"] or "").lower() for term in campaign_role["name_terms"])
        ]
        if not matching_profiles:
            campaigns.append({
                "campaign_role": campaign_role["title"], "role_profile_status": "NotInstalled",
                "agent_count": 0, "ready_count": 0, "agents": [],
                "blocking_evidence": ["No active WorkforceRoleProfile matches this campaign role; no skills were inferred."],
            })
            continue

        role_agents = [agent for agent in agents if any(agent["WorkforceRoleCode"] == profile["RoleCode"] for profile in matching_profiles)]
        target_profile = matching_profiles[0]
        required_skills = json.loads(target_profile["RequiredSkillsJson"] or "[]")
        agent_results = []
        aggregate_blockers = []
        for agent in role_agents:
            skill_rows = db.execute(text("""
                SELECT skill.SkillID,skill.Name,agent_skill.Proficiency,agent_skill.Status
                FROM dbo.AgentSkill agent_skill JOIN dbo.Skill skill ON skill.SkillID=agent_skill.SkillID
                WHERE agent_skill.AgentID=:agent_id
            """), {"agent_id": agent["AgentID"]}).mappings().all()
            skill_map = {row["Name"]: {"skill_id": str(row["SkillID"]), "proficiency": int(row["Proficiency"]), "status": row["Status"]} for row in skill_rows}
            required_missing = []
            for required in required_skills:
                current = skill_map.get(required["name"])
                if not current or current["status"] != "Active" or current["proficiency"] < int(required["minimum_proficiency"]):
                    required_missing.append(required["name"])
            required_skill_ids = [skill_map[req["name"]]["skill_id"] for req in required_skills if req["name"] in skill_map]
            evidence_rows = db.execute(text("""
                SELECT JSON_VALUE(Details,'$.skill_id') AS SkillID
                FROM dbo.AuditLog
                WHERE ResourceID=:agent_id AND Action='AgentSkillApprove'
                  AND NULLIF(JSON_VALUE(Details,'$.evidence'),'') IS NOT NULL
            """), {"agent_id": str(agent["AgentID"])}).mappings().all()
            evidence_skill_ids = {str(row["SkillID"]).lower() for row in evidence_rows if row["SkillID"]}
            evidenced_required_ids = {skill_id.lower() for skill_id in required_skill_ids if skill_id.lower() in evidence_skill_ids}
            evidence_count = len(evidenced_required_ids)
            latest_evaluations = db.execute(text("""
                WITH Ranked AS (
                    SELECT EvaluationType,Passed,Evidence,
                           ROW_NUMBER() OVER(PARTITION BY EvaluationType ORDER BY CreatedAtUtc DESC,EvaluationID DESC) AS rn
                    FROM dbo.Evaluation WHERE AgentID=:agent_id
                )
                SELECT EvaluationType,Passed,Evidence FROM Ranked WHERE rn=1
            """), {"agent_id": agent["AgentID"]}).mappings().all()
            certifications = {row["EvaluationType"]: {"passed": bool(row["Passed"]), "evidence_recorded": bool(row["Evidence"])} for row in latest_evaluations}
            blockers = []
            if agent["Status"] != "Active":
                blockers.append("Agent remains Provisioning; campaign does not activate agents.")
            workload = min(max(float(agent["CurrentWorkload"] or 0), 0), 100)
            concurrent_limit = max(int(agent["ConcurrentTaskLimit"] or 1), 1)
            active_assignments = int(agent["ActiveAssignments"] or 0)
            capacity_available = workload < 100 and active_assignments < concurrent_limit
            if not capacity_available:
                blockers.append("Workload or concurrent assignment capacity is exhausted.")
            for skill_name in required_missing:
                blockers.append(f"Required skill {skill_name} is missing, pending, below proficiency, or lacks active validation.")
            for certification in sorted(REQUIRED_AGENT_CERTIFICATIONS):
                result = certifications.get(certification)
                if not result or not result["passed"]:
                    blockers.append(f"Latest {certification} certification is missing or failed.")
                elif not result["evidence_recorded"]:
                    blockers.append(f"Latest {certification} certification has no evidence recorded.")
            if not agent["ModelProvider"] or not agent["Model"] or not agent["ModelVersion"] or agent["Model"] == "UNCONFIGURED":
                blockers.append("Approved model/provider/version is not configured.")
            else:
                approved_model = db.execute(text("""
                    SELECT TOP 1 catalog.ModelCatalogID FROM dbo.AIModelCatalog catalog
                    JOIN dbo.AIModelProvider provider ON provider.ProviderID=catalog.ProviderID
                    WHERE provider.ProviderName=:provider AND catalog.ModelName=:model
                      AND catalog.ModelVersion=:version AND catalog.Status='Approved' AND provider.Status='Active'
                """), {"provider": agent["ModelProvider"], "model": agent["Model"], "version": agent["ModelVersion"]}).scalar_one_or_none()
                if not approved_model:
                    blockers.append("Configured model is not present as Approved under an active provider.")
            skill_evidence_complete = int(evidence_count or 0) >= len(required_skills)
            if not skill_evidence_complete:
                blockers.append("Approved skill validation evidence is incomplete in the audit trail.")
            ready = not blockers
            aggregate_blockers.extend(f"{agent['AgentName']}: {blocker}" for blocker in blockers)
            agent_results.append({
                "agent_id": str(agent["AgentID"]), "agent_name": agent["AgentName"], "status": agent["Status"],
                "workload_percent": workload, "active_assignments": active_assignments,
                "concurrent_task_limit": concurrent_limit, "capacity_available": capacity_available,
                "skills": [{"name": req["name"], "required_proficiency": int(req["minimum_proficiency"]),
                            "current_proficiency": skill_map.get(req["name"], {}).get("proficiency", 0),
                            "status": skill_map.get(req["name"], {}).get("status", "Missing"),
                            "evidence_recorded": skill_map.get(req["name"], {}).get("skill_id", "").lower() in evidenced_required_ids} for req in required_skills],
                "certifications": certifications,
                "skill_evidence_count": int(evidence_count or 0), "skill_evidence_required": len(required_skills),
                "readiness": "Ready" if ready else "Blocked", "blocking_evidence": blockers,
            })
        campaigns.append({
            "campaign_role": campaign_role["title"], "role_profile_status": "Active",
            "role_code": target_profile["RoleCode"], "required_skills": required_skills,
            "agent_count": len(agent_results), "ready_count": sum(row["readiness"] == "Ready" for row in agent_results),
            "agents": agent_results, "blocking_evidence": aggregate_blockers,
        })
    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "campaigns": campaigns,
        "agents_activated": False,
        "skills_or_certifications_changed": False,
    }


def _migration_24_source() -> str:
    migration_path = Path(__file__).resolve().parents[2] / "sql" / "24_intelligent_workforce_reuse.sql"
    return migration_path.read_text(encoding="utf-8") if migration_path.is_file() else ""


@router.get("/ownership-remediation/rollback-package", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def export_ownership_rollback_package(db: Session = Depends(get_db)):
    package = export_ownership_approval_package(db)
    return {
        "package_type": "Ownership remediation rollback review",
        "generated_at_utc": package["generated_at_utc"],
        "read_only": True,
        "automatic_rollback": False,
        "candidate_count": package["summary"]["candidate_count"],
        "exact_guid_match_count": package["summary"]["exact_guid_match_count"],
        "rollback_sql": package["rollback_sql"],
        "rollback_checklist": [
            "Confirm which remediation statements were actually applied and by whom.",
            "Verify each target GUID still equals the reviewed user ID before any compensating update.",
            "Review the rollback with the database owner and retain a backup/change ticket.",
            "This endpoint does not execute rollback SQL.",
        ],
        "audit_package": ownership_remediation_audit_package(db),
    }


@router.get("/ownership-remediation/audit-package", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def ownership_remediation_audit_package(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT TOP 200 AuditLogID,CorrelationID,ActorID,Action,ResourceID,Outcome,Details,CreatedAtUtc
        FROM dbo.AuditLog
        WHERE ResourceType='OwnershipRemediationReview'
        ORDER BY CreatedAtUtc DESC,AuditLogID DESC
    """)).mappings().all()
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "review_records": [dict(row) for row in rows],
        "review_count": len(rows),
        "ownership_changes_executed_by_review_workflow": False,
    }


@router.post("/ownership-remediation/reviews", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def record_ownership_review(
    body: OwnershipReviewDecision,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    report = ownership_remediation_report(db)
    package_fingerprint = str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(report["rows"], sort_keys=True, ensure_ascii=True)))
    db.execute(text("""
        INSERT dbo.AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
        VALUES(:correlation,'User',:actor,'OwnershipRemediationReviewRecorded',
               'OwnershipRemediationReview',:resource,:outcome,:details)
    """), {
        "correlation": uuid.uuid4(), "actor": user["sub"], "resource": package_fingerprint,
        "outcome": body.decision,
        "details": json.dumps({
            "decision": body.decision,
            "reason": body.reason.strip(),
            "evidence": body.evidence.strip(),
            "change_ticket": body.change_ticket.strip(),
            "candidate_count": report["total_null_owner_rows"],
            "exact_guid_match_count": report["resolvable_exact_guid_rows"],
            "ownership_sql_executed": False,
        }, ensure_ascii=True),
    })
    db.commit()
    return {
        "decision": body.decision,
        "reviewer": str(user["sub"]),
        "package_fingerprint": package_fingerprint,
        "audit_recorded": True,
        "ownership_sql_executed": False,
        "ownership_records_changed": False,
    }


@router.get("/migration-24/validation", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def validate_migration_24(db: Session = Depends(get_db)):
    script = _migration_24_source()
    static = validate_migration_24_script(script)
    dependencies = db.execute(text("""
        SELECT prerequisite.TableName,
               CASE WHEN OBJECT_ID('dbo.'+prerequisite.TableName,'U') IS NULL THEN 0 ELSE 1 END AS Present
        FROM (VALUES('Project'),('Task'),('WorkforceRoleProfile'),('Agent')) prerequisite(TableName)
    """)).mappings().all()
    dependency_rows = [{"table": row["TableName"], "present": bool(row["Present"])} for row in dependencies]
    required_columns = (
        ("WorkforceRoleProfile", "RoleCode"), ("WorkforceRoleProfile", "RequiredSkillsJson"),
        ("Agent", "AgentID"), ("Agent", "WorkforceRoleCode"),
        ("Project", "ProjectID"), ("Task", "TaskID"),
    )
    column_rows = []
    for table, column in required_columns:
        present = bool(db.execute(text("SELECT CASE WHEN COL_LENGTH(:table_name,:column_name) IS NULL THEN 0 ELSE 1 END"), {
            "table_name": f"dbo.{table}", "column_name": column,
        }).scalar_one())
        column_rows.append({"table": table, "column": column, "present": present})
    missing = [row["table"] for row in dependency_rows if not row["present"]]
    missing_columns = [f"{row['table']}.{row['column']}" for row in column_rows if not row["present"]]
    migration_applied = bool(db.execute(text("SELECT CASE WHEN OBJECT_ID('dbo.WorkforceReuseAssessment','U') IS NULL THEN 0 ELSE 1 END")).scalar_one())
    return {
        **static,
        "dependencies": dependency_rows,
        "required_columns": column_rows,
        "dependencies_ready": not missing and not missing_columns,
        "missing_dependencies": missing,
        "missing_columns": missing_columns,
        "migration_already_applied": migration_applied,
        "dry_run_type": "Static file/schema inspection only; SQL was not parsed or executed by SQL Server.",
        "rollback_path": {
            "sql_rollback_present": static["rollback_sql_present"],
            "path": "Keep the additive table and roll application code back to a version that ignores it; preserve records. For data/schema restoration, use the approved pre-change backup or separately reviewed compensating SQL.",
            "validated": True,
            "destructive_drop_recommended": False,
        },
        "deployment_recommendation": "Static validation passed; schedule DBA review separately." if static["static_validation"] == "PASS" and not missing and not missing_columns else "NO-GO: resolve static validation or dependency gaps before deployment review.",
    }


@router.get("/model-onboarding/package", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def model_onboarding_package(db: Session = Depends(get_db)):
    providers = db.execute(text("""
        SELECT ProviderCode,ProviderName,Status FROM dbo.AIModelProvider ORDER BY ProviderName
    """)).mappings().all()
    models = db.execute(text("""
        SELECT provider.ProviderName,provider.Status AS ProviderStatus,model.ModelName,model.ModelVersion,model.Status,
               model.CreatedAtUtc,model.ApprovedAtUtc,model.ApprovedByUserID,
               latest.Decision AS LatestDecision,latest.Reason AS LatestDecisionReason,latest.Evidence AS LatestDecisionEvidence
        FROM dbo.AIModelCatalog model JOIN dbo.AIModelProvider provider ON provider.ProviderID=model.ProviderID
        OUTER APPLY (
            SELECT TOP 1 Decision,Reason,Evidence FROM dbo.AIModelApproval approval
            WHERE approval.ModelCatalogID=model.ModelCatalogID
            ORDER BY approval.DecidedAtUtc DESC,approval.ModelApprovalID DESC
        ) latest
        ORDER BY provider.ProviderName,model.ModelName,model.ModelVersion
    """)).mappings().all()
    proposal_audit_rows = db.execute(text("""
        SELECT TOP 200 AuditLogID,ActorID,ResourceID,Details,CreatedAtUtc
        FROM dbo.AuditLog
        WHERE Action='AIModelProposed' AND ResourceType='AIModelCatalog'
        ORDER BY CreatedAtUtc DESC,AuditLogID DESC
    """)).mappings().all()
    proposal_evidence = []
    for row in proposal_audit_rows:
        try:
            details = json.loads(row["Details"] or "{}")
        except (TypeError, json.JSONDecodeError):
            details = {}
        proposal_evidence.append({
            "audit_id": row["AuditLogID"], "model_catalog_id": row["ResourceID"],
            "actor_id": row["ActorID"], "created_at_utc": row["CreatedAtUtc"],
            "provider": details.get("provider"), "model": details.get("model"),
            "version": details.get("version"), "reason": details.get("reason"),
            "evidence_reference": details.get("evidence"),
        })
    pending_count = sum(1 for row in models if row["Status"] == "Pending")
    review_blockers = [
        {"provider": row["ProviderName"], "model": row["ModelName"], "version": row["ModelVersion"],
         "blocker": "Pending independent human review", "created_at_utc": row["CreatedAtUtc"]}
        for row in models if row["Status"] == "Pending"
    ]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "providers": [dict(row) for row in providers],
        "supported_provider_onboarding": [
            {"provider_code": code, "provider_name": display,
             "registry_status": next((row["Status"] for row in providers if row["ProviderCode"] == code), "NotCreated")}
            for code, (display, _catalog) in ADAPTERS.items()
        ],
        "models": [dict(row) for row in models],
        "proposal_evidence": proposal_evidence,
        "pending_proposals": pending_count,
        "review_blockers": review_blockers,
        "proposal_route": "POST /governance/models/proposals",
        "review_route": "POST /governance/models/{model_catalog_id}/decision",
        "provider_creation": "A supported provider registry entry is created when the first proposal for that provider is submitted; this does not approve the proposed model.",
        "provider_onboarding_checklist": [
            "Confirm the vendor/tenant account, region, service owner, and approved contract.",
            "Record the provider in the supported provider registry through the governed proposal flow.",
            "Configure endpoint and deployment metadata only after endpoint ownership and TLS are verified.",
            "Store credentials in the approved secret vault; persist only azure-kv:// or development env:// references.",
            "Verify secret resolution without a provider call, then schedule live connectivity testing separately.",
        ],
        "approval_automatic": False,
        "review_checklist": [
            "Verify exact provider, model name, and immutable version against contract evidence.",
            "Attach business justification and procurement/security/privacy review references.",
            "Confirm proposer and reviewer are different people for approval.",
            "Record reviewer rationale and evidence through the governed decision route.",
            "Confirm active agents, assignments, executions, and retirement impacts before lifecycle changes.",
        ],
        "pending_review_blockers": review_blockers,
        "approval_evidence_requirements": {"reason_minimum_characters": 10, "evidence_minimum_characters": 20},
    }


@router.get("/model-onboarding/approval-evidence-package", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def model_approval_evidence_package(db: Session = Depends(get_db)):
    onboarding = model_onboarding_package(db)
    return {
        "package_type": "Model proposal and approval evidence",
        "generated_at_utc": onboarding["generated_at_utc"],
        "read_only": True,
        "automatic_approval": False,
        "pending_proposals": onboarding["pending_proposals"],
        "proposal_evidence": onboarding["proposal_evidence"],
        "recorded_model_decisions": [
            {
                "provider": item["ProviderName"], "provider_status": item["ProviderStatus"],
                "model": item["ModelName"], "version": item["ModelVersion"],
                "status": item["Status"], "decision": item["LatestDecision"],
                "decision_reason": item["LatestDecisionReason"],
                "decision_evidence": item["LatestDecisionEvidence"],
                "approved_at_utc": item["ApprovedAtUtc"],
                "approved_by_user_id": item["ApprovedByUserID"],
            }
            for item in onboarding["models"] if item["LatestDecision"] or item["Status"] == "Pending"
        ],
        "review_checklist": onboarding["review_checklist"],
    }


@router.get("/phase11-deployment-package", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def phase11_deployment_package(db: Session = Depends(get_db)):
    migration = validate_migration_24(db)
    ownership = export_ownership_approval_package(db)
    rollback = export_ownership_rollback_package(db)
    ownership_rows = ownership["verification_report"]
    ownership_fingerprint = str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(ownership_rows, sort_keys=True, ensure_ascii=True)))
    latest_ownership_review = db.execute(text("""
        SELECT TOP 1 ActorID,Outcome,Details,CreatedAtUtc
        FROM dbo.AuditLog
        WHERE ResourceType='OwnershipRemediationReview' AND ResourceID=:fingerprint
        ORDER BY CreatedAtUtc DESC,AuditLogID DESC
    """), {"fingerprint": ownership_fingerprint}).mappings().first()
    models = model_onboarding_package(db)
    model_evidence = model_approval_evidence_package(db)
    adapter = adapter_deployment_package(db)
    campaign = certification_campaign(db)
    runbook = activation_runbook(db)
    launch = _phase10_launch_snapshot(db)
    phase8 = phase8_readiness(db)

    model_ready = launch["model_status"]["approved_count"] > 0
    adapter_ready = launch["adapter_status"]["configured_count"] > 0 and launch["adapter_status"]["healthy_count"] > 0
    campaign_ready = launch["certification_status"]["campaign_ready_agents"] > 0
    ownership_ready = (
        phase8["ownership"]["coverage_percent"] == 100.0
        and ownership["summary"]["candidate_count"] == 0
        and ownership["summary"]["unresolved_count"] == 0
    )
    runtime_counts = launch["runtime_status"]
    runtime_ready = all((
        bool(runtime_counts.get("assignments_ready")),
        bool(runtime_counts.get("queue_ready")),
        bool(runtime_counts.get("execution_ready")),
        bool(runtime_counts.get("deliverables_ready")),
    ))
    security_ready = (
        phase8["ownership"]["coverage_percent"] == 100.0
        and phase8["runtime_ownership"]["coverage_percent"] == 100.0
        and not phase8["rls"]["enabled"]
    )
    rls_ready = not phase8["rls"]["enabled"] and phase8["rls"]["policy_coverage_percent"] == 100.0
    migration_ready = (
        migration["static_validation"] == "PASS"
        and migration["dependencies_ready"]
        and migration["rollback_path"]["validated"]
    )
    workforce_ready = campaign_ready and launch["certification_status"]["active_skill_coverage"]["coverage_percent"] == 100.0

    runtime_blockers = []
    runtime_readiness_report = {
        "assignments_ready": runtime_counts.get("assignments_ready", 0),
        "assignments_total": runtime_counts.get("assignments_total", 0),
        "queue_ready": runtime_counts.get("queue_ready", 0),
        "queue_records": runtime_counts.get("queue_records"),
        "execution_ready": runtime_counts.get("execution_ready", 0),
        "execution_records": runtime_counts.get("execution_records"),
        "deliverables_ready": runtime_counts.get("deliverables_ready"),
        "missing_runtime_tables": runtime_counts.get("missing_tables", []),
        "ownership_coverage_percent": phase8["runtime_ownership"]["coverage_percent"],
        "approved_model_count": launch["model_status"]["approved_count"],
        "configured_adapter_count": launch["adapter_status"]["configured_count"],
        "healthy_adapter_count": launch["adapter_status"]["healthy_count"],
        "certified_active_agent_count": launch["certification_status"]["active_certification_coverage"]["certified_agents"],
    }
    for key, message in (
        ("assignments_ready", "No currently eligible active assignment records."),
        ("queue_ready", "No queue records meet current credential, model, adapter-health, certification, skill, and capacity gates."),
        ("execution_ready", "No execution-ready active agent has an active credential, approved model, configured adapter, and latest Healthy probe."),
        ("deliverables_ready", "No accepted deliverable with an artifact hash is recorded."),
    ):
        if not runtime_readiness_report.get(key):
            runtime_blockers.append(message)
    runtime_blockers.extend(f"Required runtime table missing: {table}" for table in runtime_readiness_report["missing_runtime_tables"])
    execution_blocker_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "blockers": runtime_blockers,
        "blocker_count": len(runtime_blockers),
        "runtime_history_modified": False,
    }

    sections = {
        "governance_readiness": {"label": "Governance Readiness", "ready": migration_ready, "status": "READY_FOR_REVIEW" if migration_ready else "BLOCKED", "evidence": {"static_migration_validation": migration["static_validation"], "dependencies_ready": migration["dependencies_ready"], "migration_applied": migration["migration_already_applied"]}},
        "workforce_readiness": {"label": "Workforce Readiness", "ready": workforce_ready, "status": "READY" if workforce_ready else "BLOCKED", "evidence": launch["certification_status"]},
        "runtime_readiness": {"label": "Runtime Readiness", "ready": runtime_ready, "status": "READY" if runtime_ready else "BLOCKED", "evidence": runtime_counts},
        "security_readiness": {"label": "Security Readiness", "ready": security_ready, "status": "READY_FOR_REVIEW" if security_ready else "BLOCKED", "evidence": {"ownership_coverage_percent": phase8["ownership"]["coverage_percent"], "runtime_ownership_coverage_percent": phase8["runtime_ownership"]["coverage_percent"], "rls_enabled": phase8["rls"]["enabled"]}},
        "model_readiness": {"label": "Model Readiness", "ready": model_ready, "status": "READY" if model_ready else "BLOCKED", "evidence": {"approved_models": launch["model_status"]["approved_count"], "pending_reviews": launch["model_status"]["pending_reviews"]}},
        "adapter_readiness": {"label": "Adapter Readiness", "ready": adapter_ready, "status": "READY" if adapter_ready else "BLOCKED", "evidence": launch["adapter_status"]},
        "ownership_readiness": {"label": "Ownership Readiness", "ready": ownership_ready, "status": "READY" if ownership_ready else "BLOCKED", "evidence": ownership["summary"]},
        "rls_readiness": {"label": "RLS Readiness", "ready": rls_ready, "status": "READY_FOR_REVIEW" if rls_ready else "BLOCKED", "evidence": phase8["rls"]},
    }
    ready_count = sum(section["ready"] for section in sections.values())
    blockers = [section["label"] for section in sections.values() if not section["ready"]]
    return {
        "package_type": "Phase 11 Executive Deployment Readiness",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
        "overall_readiness_percent": round(100 * ready_count / len(sections), 1),
        "go_no_go": "NO-GO" if blockers else "Ready for separately authorized deployment review",
        "blocking_items": blockers,
        "migration_validation": migration,
        "ownership_approval": ownership,
        "ownership_rollback": rollback,
        "ownership_review_state": {
            "current_candidate_fingerprint": ownership_fingerprint,
            "review_status": latest_ownership_review["Outcome"] if latest_ownership_review else "PendingReview",
            "reviewer": latest_ownership_review["ActorID"] if latest_ownership_review else None,
            "reviewed_at_utc": latest_ownership_review["CreatedAtUtc"] if latest_ownership_review else None,
            "ownership_sql_executed_by_review": False,
        },
        "model_onboarding": models,
        "model_approval_evidence": model_evidence,
        "adapter_deployment": adapter,
        "certification_campaign": campaign,
        "runtime_readiness": launch["runtime_status"],
        "runtime_readiness_report": runtime_readiness_report,
        "execution_blocker_report": execution_blocker_report,
        "activation_runbook": runbook,
        "launch_readiness": launch,
        "deployment_checklist": [
            "Complete and independently review ownership candidate package; apply nothing from this package.",
            "Obtain DBA review of migration static validation, dependencies, backup and rollback path.",
            "Onboard providers and submit model proposals with evidence; obtain separate human approvals.",
            "Resolve role-profile, skill evidence, and latest certification blockers through governed workflows.",
            "Configure approved adapters and verify credentials without exposing secret values.",
            "Run live connectivity checks only when authorized credentials and model/provider state are valid.",
            "Verify assignments, queue, execution and accepted deliverable from actual runtime history.",
            "Keep RLS disabled until a separately reviewed policy and deployment approval is complete.",
        ],
        "rollback_checklist": [
            migration["rollback_path"]["path"],
            "Ownership: execute only the separately approved guarded rollback package if remediation SQL was explicitly applied.",
            "Models: preserve model decision history; migrate/deactivate references through governance before any retirement rollback.",
            "Adapters/runtime: disable new claims and revoke credentials only through approved operator controls; preserve execution/output history.",
            "RLS: do not enable from this package; any future policy rollback requires a separately reviewed script and deployment authorization.",
        ],
        "actions_performed": [],
        "migration_applied": migration["migration_already_applied"],
        "remediation_executed": False,
        "model_approved_by_package": False,
        "agent_activated_by_package": False,
        "rls_enabled_by_package": False,
    }


def _build_phase12_activation_package(phase11: dict, workforce: dict, executive_views: dict) -> dict:
    launch = phase11["launch_readiness"]
    migration = phase11["migration_validation"]
    ownership = phase11["ownership_approval"]
    model_package = phase11["model_onboarding"]
    model_states = ("Pending", "Approved", "Rejected", "Retired")
    model_lifecycle = {
        state: sum(1 for row in model_package["models"] if row.get("Status") == state)
        for state in model_states
    }
    campaign = phase11["certification_campaign"]
    certification_matrix = [
        {
            "role": item["campaign_role"],
            "profile_status": item["role_profile_status"],
            "agent_count": item["agent_count"],
            "ready_count": item["ready_count"],
            "blocking_evidence": item["blocking_evidence"],
        }
        for item in campaign["campaigns"]
    ]
    runtime = phase11["runtime_readiness_report"]
    workforce_package = {
        **workforce,
        "candidate_classification_status": workforce.get(
            "candidate_classification_status",
            "Available" if workforce.get("reuse_migration_available") else "Unavailable: Migration 24 not applied",
        ),
    }
    ownership_summary = ownership["summary"]
    launch_ownership = launch["ownership_status"]
    launch_rls = launch["rls_status"]
    ownership_gate = (
        ownership_summary["expected_count_validated"]
        and ownership_summary["exact_guid_match_count"] == ownership_summary["candidate_count"]
        and ownership_summary["unresolved_count"] == 0
        and launch_ownership["coverage_percent"] == 100.0
    )
    certification = launch["certification_status"]
    workforce_gate = (
        int(certification["campaign_ready_agents"] or 0) > 0
        and workforce_package.get("skill_coverage_percent") == 100.0
        and workforce_package.get("certification_coverage_percent") == 100.0
    )
    runtime = phase11["runtime_readiness_report"]
    runtime_gate = all(bool(runtime.get(key)) for key in (
        "assignments_ready", "queue_ready", "execution_ready", "deliverables_ready"
    )) and not runtime.get("missing_runtime_tables")
    readiness_domains = {
        "governance_readiness": migration["migration_already_applied"]
            and migration["static_validation"] == "PASS"
            and migration["dependencies_ready"] and migration["rollback_path"]["validated"],
        "workforce_readiness": workforce_gate,
        "runtime_readiness": runtime_gate,
        "security_readiness": launch_ownership["coverage_percent"] == 100.0
            and runtime.get("ownership_coverage_percent") == 100.0,
        "model_readiness": int(launch["model_status"]["approved_count"] or 0) > 0,
        "adapter_readiness": int(launch["adapter_status"]["configured_count"] or 0) > 0
            and int(launch["adapter_status"]["healthy_count"] or 0) > 0,
        "ownership_readiness": ownership_gate,
        "rls_readiness": launch_rls["status"] == "Disabled"
            and launch_rls["enabled_predicate_coverage_percent"] == 100.0,
    }
    readiness_domain_details = {
        key: {"ready": ready, "status": "READY" if ready else "BLOCKED"}
        for key, ready in readiness_domains.items()
    }
    readiness_percent = round(100 * sum(readiness_domains.values()) / len(readiness_domains), 1)
    operational_blockers = list(phase11["blocking_items"])
    operational_blockers.extend(
        key.replace("_", " ").title()
        for key, ready in readiness_domains.items()
        if not ready and key.replace("_", " ").title() not in operational_blockers
    )
    recommendation = "NO-GO" if operational_blockers else "READY_FOR_SEPARATELY_AUTHORIZED_PILOT_REVIEW"
    workstreams = {
        "ownership_remediation": {
            "status": "READY_FOR_INDEPENDENT_REVIEW" if ownership_summary["expected_count_validated"] else "BLOCKED",
            "candidate_count": ownership_summary["candidate_count"],
            "exact_guid_match_count": ownership_summary["exact_guid_match_count"],
            "unresolved_count": ownership_summary["unresolved_count"],
            "operational_gate": "READY" if ownership_gate else "BLOCKED",
            "approval_package": ownership,
            "rollback_package": phase11["ownership_rollback"],
            "corrections_executed": False,
        },
        "migration_deployment": {
            "status": "READY_FOR_DBA_REVIEW" if migration["static_validation"] == "PASS"
                and migration["dependencies_ready"] and migration["rollback_path"]["validated"] else "BLOCKED",
            "validation": migration,
            "migration_applied": migration["migration_already_applied"],
            "execution_performed": False,
            "deployment_checklist": [
                "Review the migration checksum, required objects/columns, idempotency guards, and dependency results.",
                "Obtain DBA approval, capture a verified backup, and record the change ticket and schema baseline.",
                "Apply only through the approved deployment process; validate schema and constraints afterward.",
            ],
            "rollback_checklist": migration["rollback_path"],
        },
        "model_onboarding": {
            "status": "READY_FOR_REVIEW" if model_package.get("supported_provider_onboarding") is not None else "BLOCKED",
            "supported_providers": model_package["supported_provider_onboarding"],
            "models": model_package["models"],
            "lifecycle_counts": model_lifecycle,
            "proposal_and_review_package": phase11["model_approval_evidence"],
            "model_approval_performed": False,
        },
        "adapter_activation": {
            "status": "READY_FOR_CONFIGURATION_REVIEW" if phase11["adapter_deployment"].get("providers") is not None else "BLOCKED",
            "deployment_package": phase11["adapter_deployment"],
            "credential_references_only": True,
            "secret_reference_validation_guide": [
                "Set AI_WORKFORCE_SECRET_PROVIDER=azure-key-vault and AZURE_KEY_VAULT_URL; use a least-privilege managed identity.",
                "Use azure-kv://secret-name[/version] for production Key Vault references.",
                "Use env://VARIABLE_NAME only in local development; never persist a secret value.",
                "Confirm referenced approved model and Active provider status before configuration review.",
                "Credential resolution is not a provider health probe; schedule any live probe separately under approval.",
            ],
            "live_probes_performed": False,
        },
        "certification_campaign": {
            "status": "READY_FOR_EVIDENCE_REVIEW" if certification_matrix else "BLOCKED",
            "matrix": certification_matrix,
            "required_evaluation_types": ["Capability", "Safety", "Security", "Governance"],
            "evidence_checklist": [
                "Confirm an installed active role profile and its required skill thresholds.",
                "Record human-reviewed skill evidence through the governed skill workflow.",
                "Require latest passing Capability, Safety, Security, and Governance evaluations.",
                "Confirm approved model/provider, workload, capacity, and independent activation approval.",
            ],
            "agents_activated": False,
            "certifications_created": False,
        },
        "workforce_activation": {
            "status": "READY_FOR_REVIEW" if workforce["total_agents"] is not None else "BLOCKED",
                "metrics": workforce_package,
            "assignment_rules": [
                "Only Active non-executive agents with an exact active role profile may be considered.",
                "Require active skills at each minimum proficiency and latest passing required evaluations.",
                "Require an approved model, available workload, and remaining concurrent-task capacity.",
                "Persist assignment and audit evidence through the governed assignment workflow; never activate here.",
            ],
            "agents_activated": False,
            "assignments_created": False,
        },
        "pilot_execution": {
            "status": "READY" if runtime_gate and recommendation != "NO-GO" else "BLOCKED",
            "workflow": [
                {"stage": "Requirement", "status": "Evidence required"},
                {"stage": "Approval", "status": "Human approval required"},
                {"stage": "Project", "status": "Planned only until governed"},
                {"stage": "Assignment", "status": "Ready" if runtime["assignments_ready"] else "Blocked"},
                {"stage": "Queue", "status": "Ready" if runtime["queue_ready"] else "Blocked"},
                {"stage": "Execution", "status": "Ready" if runtime["execution_ready"] else "Blocked"},
                {"stage": "Deliverable", "status": "Ready" if runtime["deliverables_ready"] else "Blocked"},
            ],
            "runtime_evidence": runtime,
            "blockers": phase11["execution_blocker_report"]["blockers"],
            "executions_created": False,
        },
        "executive_go_no_go": {
            "go_no_go": recommendation,
            "overall_readiness_percent": readiness_percent,
            "readiness_domains": readiness_domain_details,
            "blockers": operational_blockers,
            "executive_views": executive_views,
            "rls_changed": False,
        },
    }
    return {
        "package_type": "Phase 12 Operational Activation Readiness",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "recommendation": recommendation,
        "overall_readiness_percent": readiness_percent,
        "readiness_domains": readiness_domain_details,
        "readiness_basis": "Eight operational gates; Migration 24 must be applied, and missing evidence or denominators fail closed.",
        "operational_blockers": operational_blockers,
        "workstreams": workstreams,
        "workforce_readiness": workforce_package,
        "executive_views": executive_views,
        "deployment_checklist": phase11["deployment_checklist"],
        "rollback_checklist": phase11["rollback_checklist"],
        "actions_performed": [],
        "controls_changed": False,
        "rls_enabled_by_package": False,
        "migration_executed_by_package": False,
        "ownership_corrected_by_package": False,
        "models_approved_by_package": False,
        "agents_activated_by_package": False,
        "credentials_probed_by_package": False,
        "runtime_executions_created_by_package": False,
    }


@router.get("/phase12-activation-readiness", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def phase12_activation_readiness(db: Session = Depends(get_db)):
    phase11 = phase11_deployment_package(db)
    migration_applied = phase11["migration_validation"]["migration_already_applied"]
    workforce_row = db.execute(text("""
        SELECT COUNT(*) AS TotalAgents,
               SUM(CASE WHEN Status='Active' THEN 1 ELSE 0 END) AS ActiveAgents,
               AVG(CASE WHEN Status='Active' THEN CAST(CurrentWorkload AS float) END) AS ActiveUtilization
        FROM dbo.Agent
    """)).mappings().one()
    request_rows = db.execute(text("""
        SELECT Status,COUNT(*) AS RecordCount FROM dbo.WorkforceRequest GROUP BY Status
    """)).mappings().all()
    candidate_classifications = None
    if migration_applied:
        candidate_rows = db.execute(text("""
            SELECT Classification,COUNT(*) AS RecordCount
            FROM dbo.WorkforceReuseAssessment
            GROUP BY Classification
        """)).mappings().all()
        candidate_classifications = {name: 0 for name in (
            "Ready Candidate", "Strong Candidate", "Upskill Candidate", "Workforce Request"
        )}
        candidate_classifications.update({row["Classification"]: int(row["RecordCount"]) for row in candidate_rows})

    active_agents = int(workforce_row["ActiveAgents"] or 0)
    total_agents = int(workforce_row["TotalAgents"] or 0)
    certification = phase11["launch_readiness"]["certification_status"]
    skill_coverage = certification["active_skill_coverage"].get("coverage_percent")
    certification_coverage = certification["active_certification_coverage"].get("coverage_percent")
    ready_agents = int(certification["campaign_ready_agents"] or 0)
    campaign_agents = int(certification["campaign_agents"] or 0)
    workforce = {
        "reuse_migration_available": migration_applied,
        "candidate_classifications": candidate_classifications,
        "candidate_classification_status": "Available" if migration_applied else "Unavailable: Migration 24 not applied",
        "workforce_requests_by_status": {row["Status"]: int(row["RecordCount"]) for row in request_rows},
        "total_agents": total_agents,
        "active_agents": active_agents,
        "certified_active_agents": int(certification["active_certification_coverage"]["certified_agents"] or 0),
        "workforce_readiness_percent": round(100 * ready_agents / campaign_agents, 1) if campaign_agents else None,
        "workforce_readiness_denominator": campaign_agents or None,
        "skill_coverage_percent": skill_coverage,
        "certification_coverage_percent": certification_coverage,
        "workforce_utilization_percent": round(float(workforce_row["ActiveUtilization"]), 1)
            if workforce_row["ActiveUtilization"] is not None else None,
        "utilization_denominator": active_agents or None,
    }
    views = {view: executive_readiness(view, db) for view in ("CEO", "COO", "CIO")}
    return _build_phase12_activation_package(phase11, workforce, views)


def _build_phase13_pilot_package(phase12: dict, model_governance: dict, ownership_archive: dict) -> dict:
    workstreams = phase12["workstreams"]
    ownership = workstreams["ownership_remediation"]
    migration = workstreams["migration_deployment"]
    model_onboarding = workstreams["model_onboarding"]
    adapter = workstreams["adapter_activation"]
    certification = workstreams["certification_campaign"]
    pilot = workstreams["pilot_execution"]
    lifecycle = {state: 0 for state in ("Proposed", "Pending Review", "Approved", "Retired")}
    for item in model_governance.get("lifecycle", []):
        status = str(item.get("Status") or "")
        normalized = "Pending Review" if status == "Pending" else status
        if normalized in lifecycle:
            lifecycle[normalized] += int(item.get("ModelCount") or 0)

    provider_checklist = [
        "Confirm provider legal entity, account/tenant, region, service owner, contract, and permitted data categories.",
        "Document provider threat model, data retention/training terms, residency, incident response, and subprocessors.",
        "Attach security/privacy/legal review evidence and an accountable approver before recording a provider decision.",
        "Record the provider lifecycle decision using the existing governed review process; this package never approves providers.",
    ]
    provider_risk_template = {
        "assessment_status": "Template: not assessed",
        "areas": ["data classification and permitted inputs", "retention and model-training terms",
                  "residency and cross-border transfer", "identity and credential custody",
                  "availability, incident response, and exit/portability"],
        "evidence_required": True,
    }
    providers = []
    provider_labels = {
        "AZURE_OPENAI": "Azure OpenAI",
        "OPENAI": "OpenAI",
        "GOOGLE_VERTEX": "Google Vertex AI",
        "ANTHROPIC": "Anthropic",
    }
    for provider in model_onboarding.get("supported_providers", []):
        providers.append({
            **provider,
            "provider_label": provider_labels.get(provider.get("provider_code"), provider.get("provider_name")),
            "governance_lifecycle_states": ["Proposed", "Pending Review", "Approved", "Retired"],
            "governance_state": "NotRecorded",
            "governance_state_source": "No separate provider approval lifecycle record is exposed by the current registry contract.",
            "proposal_checklist": provider_checklist,
            "risk_assessment_template": provider_risk_template,
            "security_review_checklist": [
                "Validate supported region, tenant isolation, encryption, auditability, and incident notification obligations.",
                "Verify least-privilege service identity, network restrictions, key rotation, and credential revocation procedure.",
                "Review data handling, retention, model-training opt-out, and output/IP terms against policy.",
            ],
            "approval_evidence_template": {"decision": None, "reviewer": None, "reason": None,
                                           "evidence_reference": None, "change_ticket": None},
            "retirement_procedure": [
                "Inventory models, adapters, agents, active assignments, and runtime references.",
                "Migrate or deactivate consumers through separately approved workflows and verify no active references.",
                "Revoke provider credentials and archive decision/evidence records under retention policy.",
            ],
        })

    domains_source = dict(phase12.get("readiness_domains", {}))
    certification_metrics = phase12["workforce_readiness"]
    certified_campaign_ready = any(int(item.get("ready_count") or 0) > 0 for item in certification["matrix"])
    certification_ready = (
        certified_campaign_ready
        and certification_metrics.get("skill_coverage_percent") == 100.0
        and certification_metrics.get("certification_coverage_percent") == 100.0
    )
    domains_source["certification_readiness"] = {
        "ready": certification_ready,
        "status": "READY" if certification_ready else "BLOCKED",
    }
    domain_specs = (
        ("governance_readiness", "Governance Readiness", "migration_deployment"),
        ("ownership_readiness", "Ownership Readiness", "ownership_remediation"),
        ("workforce_readiness", "Workforce Readiness", "workforce_activation"),
        ("certification_readiness", "Certification Readiness", "certification_campaign"),
        ("model_readiness", "Model Readiness", "model_onboarding"),
        ("adapter_readiness", "Adapter Readiness", "adapter_activation"),
        ("runtime_readiness", "Runtime Readiness", "pilot_execution"),
        ("rls_readiness", "RLS Readiness", "executive_go_no_go"),
    )
    evidence_by_domain = {
        "governance_readiness": migration,
        "ownership_readiness": {key: ownership[key] for key in (
            "candidate_count", "exact_guid_match_count", "unresolved_count", "operational_gate"
        )},
        "workforce_readiness": phase12["workforce_readiness"],
        "certification_readiness": certification,
        "model_readiness": {"lifecycle_counts": lifecycle, "approved_models": model_governance.get("approved_models", []),
                            "pending_reviews": model_governance.get("pending_reviews")},
        "adapter_readiness": adapter,
        "runtime_readiness": pilot,
        "rls_readiness": workstreams["executive_go_no_go"]["readiness_domains"].get("rls_readiness", {}),
    }
    blockers = phase12.get("operational_blockers", [])
    executive_domains = []
    for key, label, _source in domain_specs:
        state = domains_source.get(key, {"ready": False, "status": "BLOCKED"})
        item_evidence = evidence_by_domain[key]
        executive_domains.append({
            "domain": key,
            "label": label,
            "status": state.get("status", "BLOCKED"),
            "evidence": item_evidence,
            "blockers": [] if state.get("ready") else [blocker for blocker in blockers if label.lower().split()[0] in blocker.lower()] or [
                f"{label} has not met its verified operational gate."
            ],
            "recommendation": "Proceed to the next separately governed review." if state.get("ready")
                else f"Remain NO-GO; resolve {label.lower()} blockers with verified evidence.",
        })

    ownership_signoff = {
        "status": "Ready For Approval" if ownership["candidate_count"] == 9
            and ownership["exact_guid_match_count"] == 9 and ownership["unresolved_count"] == 0
            else "Blocked: candidate evidence requires review",
        "approval_state": "Not submitted by this read-only package",
        "candidate_validation": {"expected_candidates": 9, "observed_candidates": ownership["candidate_count"],
                                 "exact_guid_matches": ownership["exact_guid_match_count"],
                                 "unresolved": ownership["unresolved_count"]},
        "workflow": [
            "Owner and data steward independently verify the candidate fingerprint and exact GUID mappings.",
            "Attach the candidate package, rollback package, change ticket, backup reference, and evidence archive.",
            "Record explicit approval or rejection through the authorized governance/change process.",
            "Only after separate authorization may an operator execute reviewed corrections and verify before/after rows.",
        ],
        "approval_evidence_archive": ownership_archive,
        "remediation_sql_executed": False,
        "approval_record_created": False,
    }
    migration_package = {
        **migration,
        "approval_package_status": "Ready For DBA Approval" if migration["validation"]["static_validation"] == "PASS"
            and migration["validation"]["dependencies_ready"] else "Blocked: migration validation or prerequisites incomplete",
        "deployment_runbook": [
            "Freeze the target release and confirm the exact migration file hash and target database identity.",
            "Obtain database-owner/DBA approval, schedule a change window, and verify a restorable pre-change backup.",
            "Capture schema and row-count baselines; verify dependency tables and required columns.",
            "Have an authorized operator apply the reviewed migration under change control; this package performs no SQL.",
            "Capture operator, start/end time, script hash, SQL errors, and post-change schema evidence.",
        ],
        "rollback_runbook": [
            "Stop dependent application rollout and prevent new use of the reuse-assessment feature.",
            "Preserve the additive table and any records; prefer application rollback to code that ignores it.",
            "Use backup restore or a separately reviewed compensating script only with database-owner authorization.",
            "Verify application health, schema state, and audit/change records; do not drop data as a reflexive rollback.",
        ],
        "validation_checklist": [
            "Static idempotency guards and source checksum independently reviewed.",
            "Dependencies and required columns verified in target schema.",
            "Constraint and index definitions reviewed for existing rows and rerun behavior.",
            "Backup/restore point and approved rollback path confirmed.",
        ],
        "post_deployment_verification": [
            "Confirm WorkforceReuseAssessment and required constraints/indexes exist.",
            "Rerun read-only migration validation and verify migration_applied=true.",
            "Verify reuse endpoints return current persisted evidence and do not alter candidate decisions.",
            "Confirm approval, assignment, queue, execution, and RLS controls remain unchanged.",
        ],
        "execution_performed": False,
    }
    model_package = {
        "lifecycle_counts": lifecycle,
        "proposed_models": model_onboarding["proposal_and_review_package"].get("proposal_evidence", []),
        "pending_models": [row for row in model_governance.get("model_usage", []) if row.get("Status") == "Pending"],
        "approved_models": model_governance.get("approved_models", []),
        "retired_models": [row for row in model_governance.get("model_usage", []) if row.get("Status") == "Retired"],
        "approval_package": workstreams["model_onboarding"]["proposal_and_review_package"],
        "risk_assessment_template": {"status": "Template: not assessed", "areas": [
            "business purpose and user impact", "data classification and privacy", "security and abuse risks",
            "provider terms and residency", "quality/bias limitations", "human oversight and fallback"],
            "evidence_required": True},
        "usage_review_package": model_governance.get("model_usage", []),
        "retirement_impact_package": model_governance.get("approved_models", []),
        "approval_performed": False,
    }
    adapter_package = {
        **adapter,
        "azure_key_vault_deployment_guide": [
            "Set AI_WORKFORCE_SECRET_PROVIDER=azure-key-vault and AZURE_KEY_VAULT_URL in the service environment.",
            "Use a managed identity with read access limited to the named secrets; do not place secret values in config or audit.",
            "Persist only azure-kv://secret-name[/version] references and validate access under approved change control.",
        ],
        "env_reference_guide": [
            "Use env://VARIABLE_NAME only for local development/test deployments.",
            "Do not use environment-file secret references as a production secret-management substitute.",
            "Validate reference shape and model/provider association without resolving or printing the secret.",
        ],
        "adapter_validation_checklist": [
            "Credential reference uses an allowed scheme and contains no raw credential.",
            "Provider registry status is Active and the associated model is Approved for that provider.",
            "Endpoint uses HTTPS and matches the approved provider resource/deployment.",
            "Runtime remains disabled until separately authorized validation is complete.",
        ],
        "connectivity_test_checklist": [
            "Obtain explicit approval for a bounded read-only provider probe and an approved test window.",
            "Confirm least-privilege identity, endpoint allowlist, timeout, and secret redaction.",
            "Record timestamp, provider, model reference, status, and evidence without response body or secret.",
            "This Phase 13 package performs no live probe.",
        ],
        "live_probes_performed": False,
    }
    pilot_runbook = {
        "status": "Preparation only; pilot execution is NO-GO" if phase12["recommendation"] == "NO-GO" else "Requires separate authorization",
        "workflow": [
            "Requirement", "Assessment", "Approval", "Project", "Planning", "Assignment",
            "Queue", "Execution", "Deliverable", "Closure",
        ],
        "pilot_execution_checklist": [
            "Name accountable pilot owner, participants, scope, environment, data classes, success measures, and stop authority.",
            "Confirm all eight executive domains are verified READY and record separate pilot authorization.",
            "Use a synthetic or explicitly approved minimal dataset; document data handling and retention.",
            "Validate approval and project/task lineage before any assignment; verify agent qualification and capacity.",
            "Verify approved model, adapter credential reference, real authorized health evidence, and queue gates.",
            "Execute only under an approved worker/tool scope; capture genuine execution and artifact evidence.",
            "Require independent QA and authorized human acceptance before deliverable/closure.",
        ],
        "pilot_validation_checklist": [
            "Authorization and row visibility tests pass for each pilot role.",
            "All approvals, assignments, queue claims, execution outputs, and deliverables have traceable audit lineage.",
            "No unresolved critical security/privacy blocker, unapproved model, or uncertified agent is in scope.",
            "Monitoring, alerting, incident response, service owner, and rollback contacts are tested.",
        ],
        "pilot_rollback_plan": [
            "Stop new requirement intake and queue claims using separately approved operator controls.",
            "Revoke scoped credentials and disable adapter/runtime access through the approved change path.",
            "Preserve approvals, audit, execution, and artifact evidence; do not delete records to simulate rollback.",
            "Notify accountable owners, reconcile in-flight work, and resume only after new authorization.",
        ],
        "evidence_collection_guide": [
            "Store change ticket, decision IDs, report timestamps, script hash, and reviewer identities.",
            "Retain redacted API status, authorization results, assignment/queue lineage, and artifact hashes.",
            "Do not archive secrets, raw credentials, sensitive prompts, or unapproved personal data.",
        ],
        "pilot_executed": False,
    }
    executive_views = phase12["executive_views"]
    return {
        "package_type": "Phase 13 Controlled Pilot Preparation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "pilot_go_no_go": "NO-GO" if phase12["recommendation"] == "NO-GO" else "READY_FOR_SEPARATE_PILOT_AUTHORIZATION",
        "production_go_no_go": "NO-GO",
        "production_go_no_go_reason": "No explicit production authorization evidence is available in the current readiness sources.",
        "operational_readiness_percent": phase12["overall_readiness_percent"],
        "operational_blockers": phase12["operational_blockers"],
        "ownership_signoff_workflow": ownership_signoff,
        "ownership_approval_package": ownership["approval_package"],
        "ownership_rollback_package": ownership["rollback_package"],
        "migration_approval_package": migration_package,
        "provider_governance": {
            "providers": providers,
            "lifecycle_states": ["Proposed", "Pending Review", "Approved", "Retired"],
            "state_counts": {
                state: sum(provider["governance_state"] == state for provider in providers)
                for state in ("Proposed", "Pending Review", "Approved", "Retired")
            },
            "provider_approval_performed": False,
        },
        "model_governance_center": model_package,
        "workforce_readiness": phase12["workforce_readiness"],
        "certification_readiness": {
            "gap_analysis": certification["matrix"],
            "required_evaluation_types": certification["required_evaluation_types"],
            "evidence_requirements": certification["evidence_checklist"],
            "approval_checklist": ["Independent skill reviewer recorded evidence.",
                                   "Latest Capability, Safety, Security, and Governance evaluations pass.",
                                   "Approved model, capacity, and separate human activation decision verified."],
            "certifications_created": False,
        },
        "adapter_deployment_readiness": adapter_package,
        "pilot_runbook": pilot_runbook,
        "executive_domains": executive_domains,
        "executive_views": executive_views,
        "executive_recommendation": "NO-GO" if phase12["recommendation"] == "NO-GO" else "Preparation complete; obtain separate pilot approval.",
        "actions_performed": [],
        "controls_changed": False,
        "ownership_execution_performed": False,
        "migration_executed": False,
        "provider_approval_performed": False,
        "models_approved_by_package": False,
        "agents_activated_by_package": False,
        "certifications_created_by_package": False,
        "credential_values_read": False,
        "live_probes_performed": False,
        "pilot_executed": False,
        "rls_enabled_by_package": False,
        "runtime_executions_created_by_package": False,
    }


@router.get("/phase13-pilot-preparation", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def phase13_pilot_preparation(db: Session = Depends(get_db)):
    phase12 = phase12_activation_readiness(db)
    model_governance = model_governance_dashboard(db)
    ownership_archive = ownership_remediation_audit_package(db)
    return _build_phase13_pilot_package(phase12, model_governance, ownership_archive)


def _build_phase14_execution_plan(phase13: dict) -> dict:
    domain_rows = {row["domain"]: row for row in phase13.get("executive_domains", [])}
    ownership = phase13.get("ownership_signoff_workflow", {})
    migration = phase13.get("migration_approval_package", {})
    providers = phase13.get("provider_governance", {}).get("providers", [])
    model = phase13.get("model_governance_center", {})
    certification = phase13.get("certification_readiness", {})
    adapter = phase13.get("adapter_deployment_readiness", {})
    pilot = phase13.get("pilot_runbook", {})
    lifecycle = model.get("lifecycle_counts", {})
    approved_provider_count = sum(item.get("governance_state") == "Approved" for item in providers)
    approved_model_count = int(lifecycle.get("Approved", 0) or 0)
    ready_roles = sum(int(item.get("ready_count", 0) or 0) > 0
                      for item in certification.get("gap_analysis", []))

    gate_specs = (
        ("ownership_complete", "Gate 1: Ownership Complete", "ownership_readiness",
         "Owner and data steward approve reviewed exact-GUID corrections.",
         "100% ownership coverage and a post-change reconciliation report with zero unresolved rows.",
         "Owner / data steward, with DBA execution under the approved change ticket.",
         "Any before/after mismatch, unexpected row count, or candidate fingerprint change."),
        ("migration_complete", "Gate 2: Migration Complete", "governance_readiness",
         "DBA approval, verified backup, dependencies, schema prerequisites, and change window are recorded.",
         "Migration 24 is applied and read-only validation confirms required objects, columns, constraints, and idempotency.",
         "Database owner / DBA and change advisory board.",
         "DDL error, constraint/data discrepancy, monitoring alert, or failed post-deployment verification."),
        ("provider_approved", "Gate 3: Provider Approved", "model_readiness",
         "Provider security, privacy, legal, residency, contract, and incident reviews have evidence and an accountable proposer.",
         "A distinct authorized reviewer records provider approval and active status in the governed provider process.",
         "Security and privacy approvers plus the designated platform/provider governance owner.",
         "Material provider-term change, security incident, expired review, or unresolved data handling risk."),
        ("model_approved", "Gate 4: Model Approved", "model_readiness",
         "Proposal identifies immutable model/version, business need, evaluation results, risks, and evidence.",
         "Authorized independent model reviewer records approval for an active provider with no blocking risk.",
         "Platform Owner or designated independent model reviewer; proposer cannot self-approve.",
         "Evaluation regression, provider suspension, new material risk, or model/version mismatch."),
        ("agents_certified", "Gate 5: Agents Certified", "certification_readiness",
         "Active role profile and required skills are confirmed; evaluation evidence is independently reviewed.",
         "Each in-scope agent has active required skills and latest passing Capability, Safety, Security, and Governance evaluations.",
         "Independent certification reviewer and authorized workforce/agent activation owner.",
         "Failed or superseded evaluation, skill evidence withdrawal, role drift, or certification exception."),
        ("adapters_configured", "Gate 6: Adapters Configured", "adapter_readiness",
         "Approved provider/model mapping, endpoint, secret reference, managed identity, and least-privilege scope are reviewed.",
         "Credential reference validation succeeds and a separately authorized health check records a real healthy result.",
         "Adapter service owner and security approver; probe operator must be authorized.",
         "Credential resolution failure, unhealthy probe, endpoint/model mismatch, or secret exposure."),
        ("runtime_validated", "Gate 7: Runtime Validated", "runtime_readiness",
         "Assignments satisfy role, skills, evaluations, approved model, workload/capacity, and audit requirements.",
         "Actual eligible queue, execution, independently reviewed output, and accepted deliverable have traceable evidence.",
         "Runtime service owner, independent QA, and accountable business acceptance owner.",
         "Unauthorized claim, failed execution, policy violation, missing lineage, or rejected deliverable."),
        ("rls_readiness_approved", "Gate 8: RLS Readiness Approved", "rls_readiness",
         "RLS design, identity context, table coverage, rollback, and role-specific negative tests are independently reviewed.",
         "Security and DBA approve the complete policy test evidence and a separately authorized deployment decision.",
         "Security owner and DBA/CAB; Platform Owner is not a substitute for security approval.",
         "Any cross-principal data leak, missing predicate, session-context failure, or rollback test failure."),
    )
    gates = []
    for key, label, domain, entry, exit_criteria, authority, rollback in gate_specs:
        evidence = domain_rows.get(domain, {"status": "BLOCKED", "evidence": {}, "blockers": ["No verified evidence"]})
        if key == "ownership_complete":
            ready = (ownership.get("candidate_validation", {}).get("observed_candidates") == 9
                     and ownership.get("candidate_validation", {}).get("exact_guid_matches") == 9
                     and ownership.get("candidate_validation", {}).get("unresolved") == 0
                     and evidence.get("status") == "READY")
        elif key == "provider_approved":
            ready = approved_provider_count > 0 and evidence.get("status") == "READY"
        elif key == "model_approved":
            ready = approved_model_count > 0 and evidence.get("status") == "READY"
        elif key == "agents_certified":
            ready = ready_roles > 0 and evidence.get("status") == "READY"
        elif key == "adapters_configured":
            configured = any(item.get("configuration_status") == "Configured"
                             and item.get("health_status") == "Healthy"
                             for item in adapter.get("deployment_package", {}).get("providers", []))
            ready = configured and evidence.get("status") == "READY"
        else:
            ready = evidence.get("status") == "READY"
        gates.append({
            "gate": key,
            "label": label,
            "status": "READY" if ready else "BLOCKED",
            "current_evidence": evidence.get("evidence", evidence),
            "blockers": [] if ready else evidence.get("blockers", [f"{label} has no complete verified evidence."]),
            "entry_criteria": entry,
            "exit_criteria": exit_criteria,
            "required_evidence": [entry, exit_criteria, "Approver identity, decision timestamp, evidence reference, and change ticket."],
            "approval_authority": authority,
            "rollback_trigger": rollback,
        })

    production_ready = (
        all(gate["status"] == "READY" for gate in gates)
        and phase13.get("production_go_no_go") == "GO"
        and bool(phase13.get("production_authorization_evidence_available"))
    )
    pilot_ready = phase13.get("pilot_go_no_go") != "NO-GO" and production_ready
    executive_packages = {}
    view_focus = {
        "CEO": ("governance_readiness", "ownership_readiness", "model_readiness", "provider_approved", "runtime_readiness"),
        "COO": ("workforce_readiness", "certification_readiness", "adapter_readiness", "runtime_readiness"),
        "CIO": ("governance_readiness", "model_readiness", "adapter_readiness", "runtime_readiness", "rls_readiness"),
    }
    for view, focus in view_focus.items():
        selected = [row for row in phase13.get("executive_domains", []) if row.get("domain") in focus]
        selected.extend(gate for gate in gates if gate["gate"] in focus)
        executive_packages[view] = {
            "view": view,
            "governance_status": "READY" if production_ready else "BLOCKED",
            "domains": selected,
            "evidence": phase13.get("executive_views", {}).get(view, {}),
            "blockers": phase13.get("operational_blockers", []),
            "dependencies": [row["label"] for row in gates if row["status"] != "READY"],
            "recommendation": "NO-GO" if not pilot_ready else "Proceed only with separate pilot authorization.",
            "pilot_go_no_go": "GO" if pilot_ready else "NO-GO",
            "production_go_no_go": "GO" if production_ready else "NO-GO",
        }

    provider_states = ("Proposed", "Pending Review", "Approved", "Suspended", "Retired")
    provider_governance_plan = {
        "supported_providers": providers,
        "lifecycle_states": list(provider_states),
        "observed_state_counts": {state: sum(item.get("governance_state") == state for item in providers)
                                  for state in provider_states},
        "not_recorded_count": sum(item.get("governance_state") == "NotRecorded" for item in providers),
        "approval_execution_performed": False,
    }
    workstreams = {
        "ownership_execution_playbook": {
            "status": "PLANNING_ONLY",
            "evidence": {"candidate_validation": ownership.get("candidate_validation"),
                         "approval_state": ownership.get("approval_state")},
            "pre_execution_checklist": ["Verify current candidate fingerprint and exact GUID-to-AppUser mapping.",
                "Confirm owner/data-steward approval, change ticket, backup, target DB, and named operator.",
                "Capture current values and affected row counts before execution."],
            "approval_workflow": ownership.get("workflow", []),
            "execution_checklist": ["Execute only the separately approved guarded remediation package.",
                "Use a transaction/change tool with logged operator, script hash, and before/after counts.",
                "Stop on fingerprint drift, unexpected row count, or any mismatched GUID."],
            "validation_checklist": ["Re-read every affected owner GUID and compare with the approved exact mapping.",
                "Verify ownership coverage is 100% and unresolved count is zero.",
                "Retain application-level authorization tests and audit evidence."],
            "rollback_procedure": ["Stop dependent rollout and preserve execution logs.",
                "Use only the reviewed guarded rollback after confirming current values still match the change.",
                "Reconcile affected rows and re-run authorization/ownership tests."],
            "evidence_template": {"change_ticket": None, "candidate_fingerprint": None, "backup_reference": None,
                "operator": None, "approver": None, "script_hash": None, "before_after_counts": None,
                "validation_result": None, "rollback_result": None},
            "audit_requirements": ["Actor, approver, timestamp, change ticket, fingerprint, script hash, outcome, and row counts."],
            "ownership_coverage_target_percent": 100,
            "execution_performed": False,
        },
        "migration_24_execution_playbook": {
            "status": "PLANNING_ONLY",
            "change_request_template": {"change_id": None, "target_environment": None, "owner": None,
                "business_justification": None, "script_sha256": migration.get("validation", {}).get("script_sha256"),
                "backup_reference": None, "window": None, "approvers": []},
            "cab_review_package": migration,
            "implementation_steps": migration.get("deployment_runbook", []),
            "validation_steps": migration.get("validation_checklist", []),
            "rollback_procedure": migration.get("rollback_runbook", []),
            "communication_plan": ["Notify service, database, security, and workforce owners before the approved window.",
                "Communicate start, completion, blockers, and rollback decision through the change record.",
                "Notify stakeholders only after post-change verification is complete."],
            "post_implementation_review": migration.get("post_deployment_verification", []),
            "failure_scenarios": ["Missing dependency/column", "constraint violation", "script interruption",
                "unexpected existing table/data", "application/report incompatibility"],
            "monitoring_requirements": ["Capture SQL errors and duration", "verify application health and readiness",
                "check reuse endpoint error rates and schema validation", "monitor for unexpected writes or constraint failures"],
            "migration_applied": migration.get("validation", {}).get("migration_already_applied", False),
        },
        "provider_approval_execution_plan": {
            **provider_governance_plan,
            "security_review_checklist": ["Data residency, retention, training use, and subprocessors reviewed.",
                "Identity, key custody, network boundary, audit, and incident obligations reviewed."],
            "risk_assessment_template": {"status": "Not assessed", "risk_owner": None, "residual_risk": None,
                "mitigations": [], "evidence_reference": None},
            "data_handling_review": ["Classify inputs/outputs", "confirm permitted data and retention",
                "document residency/transfer and deletion terms"],
            "governance_approval_package": {"approver": None, "decision": None, "rationale": None,
                "security_evidence": None, "privacy_legal_evidence": None, "ticket": None},
            "retirement_checklist": ["Inventory dependent models/adapters/agents", "migrate or stop consumers",
                "revoke credentials", "archive evidence and verify no active references"],
        },
        "model_approval_execution_plan": {
            "lifecycle_counts": model.get("lifecycle_counts", {}),
            "evaluation_framework": ["Business utility and fit", "capability and quality evaluation",
                "safety/security/privacy evaluation", "robustness, limitations, and human oversight"],
            "approval_matrix": ["Proposer supplies immutable model/version and evidence.",
                "Independent technical/security/privacy reviewers assess their domains.",
                "Authorized model approver records decision; proposer cannot self-approve."],
            "review_checklist": model.get("risk_assessment_template", {}).get("areas", []),
            "retirement_impact_plan": model.get("retirement_impact_package", []),
            "usage_validation_plan": model.get("usage_review_package", []),
            "proposal_evidence": model.get("proposed_models", []),
            "approval_performed": False,
        },
        "certification_execution_campaign": {
            "roles": certification.get("gap_analysis", []),
            "evaluation_types": ["Capability", "Safety", "Security", "Governance"],
            "evaluation_schedule": ["Baseline capability and role-skill evidence", "Safety and security evaluation",
                "Governance review", "Independent evidence review before activation decision"],
            "readiness_criteria": ["Active approved role profile", "active skills meet every minimum proficiency",
                "latest evaluation passes for all four required types", "approved model and available capacity"],
            "evidence_requirements": certification.get("evidence_requirements", []),
            "exception_process": ["Document the exception, scope, expiry, compensating controls, and accountable owner.",
                "Obtain independent risk/security approval; exceptions cannot waive mandatory law or hard safety gates."],
            "recertification_plan": ["Re-evaluate on material model, role, tool, or policy change.",
                "Review latest evidence before new assignment; do not infer expiry where the system does not track it."],
            "certifications_issued": False,
        },
        "adapter_activation_playbook": {
            "azure_key_vault_runbook": adapter.get("azure_key_vault_deployment_guide", []),
            "env_reference_runbook": adapter.get("env_reference_guide", []),
            "credential_validation_process": adapter.get("adapter_validation_checklist", []),
            "connectivity_validation_process": adapter.get("connectivity_test_checklist", []),
            "incident_response_checklist": ["Disable new claims through approved operator controls.",
                "Revoke or rotate affected credential references", "preserve sanitized diagnostics and audit entries",
                "notify security/provider owners and require revalidation before restart"],
            "rollback_procedure": ["Return to last approved adapter configuration", "revoke compromised credentials",
                "keep execution disabled until approved health and model/provider association are restored"],
            "secret_reference_standards": ["Production: azure-kv:// only with configured Key Vault resolver.",
                "Development only: env://VARIABLE_NAME.", "Never persist or return secret values."],
            "provider_model_mapping_validated": False,
            "probes_performed": False,
        },
        "pilot_execution_acceptance_plan": {
            "workflow": pilot.get("workflow", []),
            "acceptance_checklist": ["Every transition has an authorized actor and persisted source evidence.",
                "Human approval precedes project creation; qualified assignment precedes queue eligibility.",
                "Execution output is genuine, bounded, auditable, and independently reviewed.",
                "Deliverable has acceptance evidence and closure has an accountable owner."],
            "success_metrics": ["100% approval/audit lineage", "100% assignments satisfy skill/certification/capacity gates",
                "0 unauthorized queue claims", "100% deliverables independently accepted or explicitly rejected"],
            "failure_criteria": ["Any authorization leak", "missing approval or audit lineage", "unapproved model/provider",
                "uncertified or over-capacity assignment", "unbounded execution or missing output provenance"],
            "rollback_criteria": ["security/privacy incident", "failed critical evaluation", "adapter/credential compromise",
                "data integrity mismatch", "repeated execution or QA failure beyond approved retry limit"],
            "evidence_templates": {"requirement_id": None, "approval_id": None, "project_id": None,
                "assignment_ids": [], "queue_ids": [], "execution_ids": [], "artifact_hashes": [],
                "qa_decision": None, "closure_approval": None},
            "pilot_executed": False,
        },
        "production_readiness_gate_model": {"gates": gates, "all_gates_required": True,
            "production_authorized_by_package": False},
        "executive_decision_package": {"packages": executive_packages,
            "pilot_go_no_go": "GO" if pilot_ready else "NO-GO",
            "production_go_no_go": "GO" if production_ready else "NO-GO",
            "production_authorization_evidence_available": False},
    }
    return {
        "package_type": "Phase 14 Controlled Pilot Execution Planning",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "planning_only": True,
        "pilot_go_no_go": "GO" if pilot_ready else "NO-GO",
        "production_go_no_go": "GO" if production_ready else "NO-GO",
        "readiness_percent": phase13.get("operational_readiness_percent"),
        "production_gates": gates,
        "workstreams": workstreams,
        "executive_packages": executive_packages,
        "blockers": phase13.get("operational_blockers", []),
        "actions_performed": [],
        "controls_changed": False,
        "ownership_executed": False,
        "migration_executed": False,
        "provider_or_model_approved": False,
        "certifications_issued": False,
        "agents_activated": False,
        "adapter_configured": False,
        "adapter_probed": False,
        "pilot_executed": False,
        "runtime_executed": False,
        "rls_enabled": False,
    }


@router.get("/phase14-execution-planning", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def phase14_execution_planning(db: Session = Depends(get_db)):
    phase13 = phase13_pilot_preparation(db)
    return _build_phase14_execution_plan(phase13)


def _build_phase15_governance_package(phase14: dict, ownership_archive: dict | None = None) -> dict:
    workstreams = phase14.get("workstreams", {})
    ownership = workstreams.get("ownership_execution_playbook", {})
    migration = workstreams.get("migration_24_execution_playbook", {})
    providers = workstreams.get("provider_approval_execution_plan", {}).get("supported_providers", [])
    models = workstreams.get("model_approval_execution_plan", {})
    certification = workstreams.get("certification_execution_campaign", {})
    adapter = workstreams.get("adapter_activation_playbook", {})
    pilot = workstreams.get("pilot_execution_acceptance_plan", {})
    runtime_gate = next((gate for gate in phase14.get("production_gates", [])
                         if gate.get("gate") == "runtime_validated"), {})
    evidence_sources = (
        ("Approval Evidence", None, "Approval decision records are not included in the current planning evidence."),
        ("Ownership Evidence", ownership.get("evidence"), "Exact candidate mapping evidence is present; approval/execution remains separate."),
        ("Certification Evidence", certification.get("roles"), "Campaign role evidence is present; no certifications are created by this package."),
        ("Runtime Validation Evidence", runtime_gate.get("current_evidence"), "Runtime evidence must come from real approved operations."),
        ("Provider Approval Evidence", providers, "Provider approval state is NotRecorded unless an explicit decision record exists."),
        ("Model Approval Evidence", models.get("approved_models"), "Model approvals must come from the governed model decision record."),
        ("Adapter Validation Evidence", adapter.get("connectivity_validation_process"), "Configuration and probe evidence are separate; no probe is run here."),
    )
    checklist = []
    for title, evidence, note in evidence_sources:
        has_source = evidence is not None and evidence != [] and evidence != {}
        operationally_complete = False
        if title == "Ownership Evidence":
            candidates = (ownership.get("evidence") or {}).get("candidate_validation", {})
            operationally_complete = bool(candidates.get("coverage_percent") == 100.0
                and ownership.get("approval_state") == "Approved"
                and ownership.get("execution_performed"))
        elif title == "Provider Approval Evidence":
            operationally_complete = any(item.get("governance_state") == "Approved" for item in providers)
        elif title == "Model Approval Evidence":
            operationally_complete = any(item.get("Status") == "Approved" for item in (evidence or []))
        elif title == "Runtime Validation Evidence":
            operationally_complete = runtime_gate.get("status") == "READY"
        elif title == "Certification Evidence":
            operationally_complete = any(int(item.get("ready_count") or 0) > 0 for item in (evidence or []))
        elif title == "Adapter Validation Evidence":
            operationally_complete = bool(adapter.get("probes_performed"))
        checklist.append({
            "evidence_type": title,
            "status": "Verified" if operationally_complete else ("Evidence source present; approval/proof incomplete" if has_source else "Unavailable"),
            "source_present": has_source,
            "operationally_complete": operationally_complete,
            "evidence": evidence if has_source else None,
            "note": note,
        })
    complete_count = sum(item["operationally_complete"] for item in checklist)
    missing_evidence = [item["evidence_type"] for item in checklist if not item["operationally_complete"]]
    evidence_score = round(100 * complete_count / len(checklist), 1) if checklist else None
    approval_workflows = [
        {"workflow": name, "workflow_status": "Defined", "decision_status": "NotRecorded", "approval_created": False,
         "required_approvers": authorities, "evidence_required": evidence}
        for name, authorities, evidence in (
            ("Ownership Approval", ["Owner", "Data Steward"], ["candidate fingerprint", "exact mapping", "rollback package", "change ticket"]),
            ("Migration Approval", ["Database Owner", "DBA", "CAB"], ["script hash", "backup", "dependency validation", "rollback plan"]),
            ("Provider Approval", ["Security", "Privacy/Legal", "Provider Governance Owner"], ["risk review", "data handling", "contract/region", "decision rationale"]),
            ("Model Approval", ["Independent Model Reviewer", "Security/Privacy reviewers"], ["immutable version", "evaluation", "risk review", "proposal evidence"]),
            ("Certification Approval", ["Independent Evaluator", "Workforce Owner"], ["skills evidence", "Capability", "Safety", "Security", "Governance"]),
            ("Adapter Approval", ["Adapter Owner", "Security Owner"], ["secret reference", "approved model mapping", "credential validation", "authorized health evidence"]),
            ("Pilot Authorization", ["Business Owner", "Security Owner", "Executive Sponsor"], ["all entry gates", "scope", "stop authority", "rollback readiness"]),
        )
    ]
    risk_categories = ("Governance Risk", "Security Risk", "Operational Risk", "Workforce Risk",
                       "Runtime Risk", "Model Risk", "Compliance Risk")
    risk_register = {
        "assessment_status": "Template: not assessed",
        "risks": [{"category": category, "likelihood": None, "impact": None, "mitigation": None,
                    "owner": None, "review_date": None, "status": "Unassessed"} for category in risk_categories],
        "heatmap_data": [{"category": category, "likelihood": None, "impact": None, "count": None}
                          for category in risk_categories],
        "executive_summary": "Risk levels are unavailable until accountable owners perform and record an assessment.",
        "risk_records_created": False,
    }
    compliance_areas = ("Data Ownership", "Retention", "Privacy", "Security Review", "Audit Requirements", "Legal Review")
    compliance = {
        "status": "Not assessed",
        "checklist": [{"area": area, "status": "Not assessed", "evidence_reference": None,
                       "owner": None, "approval": None} for area in compliance_areas],
        "exception_register": {"status": "Unavailable", "exceptions": None,
                               "note": "No verified exception source is included in the readiness package."},
        "evidence_register": checklist,
        "compliance_inferred": False,
    }
    workflow_kpis = {
        "approval_completion_percent": {"value": "Unavailable", "numerator": None, "denominator": None},
        "audit_completeness_percent": {"value": "Unavailable", "numerator": None, "denominator": None},
        "evidence_completeness_percent": {"value": evidence_score, "numerator": complete_count, "denominator": len(checklist)},
        "certification_coverage_percent": {"value": "Unavailable", "numerator": None, "denominator": None},
        "skill_coverage_percent": {"value": "Unavailable", "numerator": None, "denominator": None},
        "workforce_readiness_percent": {"value": phase14.get("readiness_percent", "Unavailable"), "numerator": None, "denominator": None},
        "assignment_success_percent": {"value": "Unavailable", "numerator": None, "denominator": None},
        "queue_success_percent": {"value": "Unavailable", "numerator": None, "denominator": None},
        "execution_success_percent": {"value": "Unavailable", "numerator": None, "denominator": None},
        "deliverable_success_percent": {"value": "Unavailable", "numerator": None, "denominator": None},
    }
    exit_criteria = ["Governance approvals are complete with linked evidence.",
        "Runtime validation evidence is complete and independently reviewed.",
        "Security review and audit completeness are approved.",
        "Executive sign-off is recorded by authorized decision makers."]
    executive = {}
    for name, focus in {
        "CEO": ["Governance Status", "Evidence Status", "Risk Status", "Compliance Status"],
        "COO": ["Governance Status", "Evidence Status", "Workforce Status", "Runtime Status"],
        "CIO": ["Governance Status", "Evidence Status", "Security Status", "Runtime Status"],
    }.items():
        executive[name] = {"focus": focus, "status": "BLOCKED",
            "evidence_readiness_score": evidence_score, "missing_evidence": missing_evidence,
            "risk_status": risk_register["assessment_status"], "compliance_status": compliance["status"],
            "recommendation": "NO-GO", "authorization": "Not Authorized"}
    return {
        "package_type": "Phase 15 Controlled Pilot Governance & Evidence Management",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "evidence_checklist": checklist,
        "missing_evidence": missing_evidence,
        "missing_evidence_report": {"missing": missing_evidence, "count": len(missing_evidence)},
        "evidence_readiness_score": evidence_score,
        "approval_mapping_matrix": approval_workflows,
        "immutable_evidence_audit": {"source": "Existing audit evidence only",
            "records": (ownership_archive or {}).get("review_records", []),
            "record_count": (ownership_archive or {}).get("review_count", 0),
            "mutations_performed": False,
            "note": "Only existing ownership review audit records are included; this package does not write or modify audit evidence."},
        "approval_hub": {
            "workflow_definitions": approval_workflows,
            "states": ["Pending", "Approved", "Rejected", "Expired"],
            "approval_matrix": approval_workflows,
            "separation_of_duties": [
                {"workflow": "Model Approval", "rule": "Proposer cannot approve own proposal."},
                {"workflow": "Ownership Approval", "rule": "Candidate preparer and independent owner/data steward review are distinct duties."},
                {"workflow": "Certification Approval", "rule": "Evidence evaluator and activation authority are separately accountable."},
                {"workflow": "Pilot Authorization", "rule": "Requester cannot self-authorize production or pilot execution."},
            ],
            "authorization_model": "Role-protected workflow endpoints; decision authority is independent from package preparation.",
            "approvals_created": False,
        },
        "risk_register": risk_register,
        "risk_summary": risk_register["executive_summary"],
        "risk_dashboard": {"status": "Unavailable: risks not assessed", "heatmap_data": risk_register["heatmap_data"],
                           "executive_summary": risk_register["executive_summary"]},
        "compliance_readiness": compliance,
        "change_control": {
            "status": "Planning only",
            "change_request_template": {"change_id": None, "scope": None, "owner": None, "risk": None,
                "implementation_window": None, "rollback": None, "approvers": [], "evidence": []},
            "cab_review_template": {"decision": None, "attendees": [], "conditions": [], "evidence": []},
            "risk_assessment_template": risk_register,
            "implementation_review_template": {"result": None, "operator": None, "validation_evidence": None},
            "rollback_approval_template": {"decision": None, "approver": None, "trigger": None, "evidence": None},
            "change_checklist": ["approved scope", "pre-change backup", "authorized operators", "monitoring and stop authority", "post-change review"],
            "rollback_checklist": ["verified trigger", "authorized decision", "restore/compensating plan", "validation", "communications"],
            "change_requests_created": False,
        },
        "success_measurement": {"metrics": workflow_kpis, "estimated_values_used": False},
        "pilot_completion_framework": {"exit_criteria": exit_criteria,
            "closure_checklist": exit_criteria + ["Preserve evidence and record lessons learned."],
            "lessons_learned_template": {"observation": None, "impact": None, "root_cause": None, "action_owner": None},
            "pilot_assessment_template": {"outcomes": None, "success_metrics": None, "risks": None, "decision": None},
            "pilot_closed": False},
        "executive_packages": executive,
        "pilot_authorization_readiness": "NO-GO",
        "production_authorization_readiness": "NO-GO",
        "readiness_source": "Phase 14 verified planning package; templates and plans do not count as operational evidence.",
        "actions_performed": [], "controls_changed": False, "approvals_created": False,
        "risks_assessed": False, "compliance_inferred": False, "change_requests_created": False,
        "pilot_closed": False,
    }


@router.get("/phase15-governance-evidence", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def phase15_governance_evidence(db: Session = Depends(get_db)):
    phase14 = phase14_execution_planning(db)
    ownership_archive = ownership_remediation_audit_package(db)
    return _build_phase15_governance_package(phase14, ownership_archive)


def _build_phase16_authorization_package(phase15: dict, phase14: dict) -> dict:
    phase14_gates = {item["gate"]: item for item in phase14.get("production_gates", [])}
    approvals = {item["workflow"]: item for item in phase15.get("approval_hub", {}).get("workflow_definitions", [])}
    evidence_by_gate = {
        "ownership_approved": ("Ownership Approval", "ownership_complete"),
        "migration_applied": ("Migration Approval", "migration_complete"),
        "providers_approved": ("Provider Approval", "provider_approved"),
        "models_approved": ("Model Approval", "model_approved"),
        "certifications_completed": ("Certification Approval", "agents_certified"),
        "adapters_configured": ("Adapter Approval", "adapters_configured"),
        "runtime_validated": ("Pilot Authorization", "runtime_validated"),
        "rls_approved": ("Pilot Authorization", "rls_readiness_approved"),
    }
    gate_specs = (
        ("ownership_approved", "Gate 1: Ownership Approved", "Owner / data steward", "Approval and execution records; reconciled 100% coverage.", "Candidate mismatch or mapping fingerprint drift."),
        ("migration_applied", "Gate 2: Migration Applied", "Database owner / DBA / CAB", "Approved change ticket, script hash, applied migration, schema verification.", "Migration error, failed constraint validation, or failed health check."),
        ("providers_approved", "Gate 3: Providers Approved", "Security / Privacy-Legal / provider governance owner", "Recorded provider approval and completed risk/data review.", "Provider-term change, security incident, or approval expiry."),
        ("models_approved", "Gate 4: Models Approved", "Independent model reviewer", "Recorded approval, immutable version, evaluation and risk evidence.", "Evaluation regression, provider suspension, or version mismatch."),
        ("certifications_completed", "Gate 5: Certifications Completed", "Independent evaluator / workforce owner", "Latest passing Capability, Safety, Security, Governance evidence and active skill proof.", "Failed/superseded evaluation or withdrawn evidence."),
        ("adapters_configured", "Gate 6: Adapters Configured", "Adapter owner / security approver", "Approved provider/model mapping, scoped credential reference, real validation evidence.", "Secret exposure, failed validation, or mapping drift."),
        ("runtime_validated", "Gate 7: Runtime Validated", "Runtime owner / independent QA / business owner", "Real assignment, queue, execution, output, and accepted deliverable lineage.", "Unauthorized work, policy violation, failed execution, or lineage gap."),
        ("security_review_completed", "Gate 8: Security Review Completed", "Security owner / privacy reviewer", "Signed security/privacy review, negative authorization test evidence, incident plan.", "Critical finding, access leak, or unmitigated risk."),
        ("rls_approved", "Gate 9: RLS Approved", "Security owner / DBA / CAB", "Approved RLS design, policy tests, rollback and deployment authorization.", "Cross-principal data leak, predicate gap, or rollback failure."),
    )
    gates = []
    for key, label, authority, evidence, rollback in gate_specs:
        if key == "security_review_completed":
            security_review = next((item for item in phase15.get("compliance_readiness", {}).get("checklist", [])
                                    if item.get("area") == "Security Review"), {})
            source_gate = {"status": "READY" if security_review.get("status") == "Approved" else "BLOCKED",
                           "current_evidence": security_review,
                           "blockers": ["Security review evidence and approval are not recorded."]}
            approval_status = "NotRecorded"
            source_evidence = source_gate.get("current_evidence")
            ready = source_gate["status"] == "READY"
        else:
            approval_name, phase14_name = evidence_by_gate[key]
            approval = approvals.get(approval_name, {})
            source_gate = phase14_gates.get(phase14_name, {})
            approval_status = approval.get("decision_status", "NotRecorded")
            source_evidence = source_gate.get("current_evidence")
            ready = source_gate.get("status") == "READY" and approval_status == "Approved"
        gates.append({
            "gate": key, "label": label, "status": "READY" if ready else "BLOCKED",
            "authorization_status": approval_status if approval_status in {"Pending", "Approved", "Rejected", "Expired"} else "NotRecorded",
            "current_evidence": source_evidence,
            "blockers": [] if ready else source_gate.get("blockers", ["Required approval or verified operational evidence is unavailable."]),
            "entry_criteria": "Previous gate satisfied and evidence reviewed by accountable owner.",
            "exit_criteria": evidence,
            "required_evidence": [evidence, "Approver, decision timestamp, evidence reference, and change ticket."],
            "approval_authority": authority,
            "reject_conditions": ["Missing, contradictory, stale, or unverifiable evidence.", "Approver lacks authority or separation of duties is violated."],
            "rollback_conditions": [rollback, "New evidence invalidates a previously approved prerequisite."],
        })
    pilot_authorized = (all(gate["status"] == "READY" for gate in gates)
        and phase15.get("pilot_authorization_readiness") == "GO")
    production_authorized = (all(gate["status"] == "READY" for gate in gates)
        and phase15.get("production_authorization_readiness") == "GO"
        and bool(phase14.get("production_authorization_evidence_available")))
    cutover = {
        "status": "Planning only; not executed",
        "pre_cutover": ["All authorization gates satisfied and signed", "Confirm scope, owners, support roster, backup, monitoring and stop authority"],
        "implementation_window": ["Change lead confirms approvals and records start", "Operators follow the approved runbook only", "Stop on trigger or unexpected result"],
        "validation_window": ["Verify health, access boundaries, lineage, and acceptance evidence", "Independent QA and security review outcomes"],
        "rollback_window": ["Keep authorized rollback decision-maker available", "Use only reviewed rollback artifacts", "Preserve audit and evidence history"],
        "post_cutover_review": ["Reconcile change evidence, incidents, metrics, and exceptions", "Obtain explicit closure decision"],
        "communications_plan": ["Pre-window notice", "start/status updates", "completion or rollback notice", "post-review summary"],
        "escalation_path": ["Operator → Change Lead → Service Owner → Security/DBA → Executive Sponsor"],
        "support_structure": ["Named primary and deputy for operations, database, security, workforce, and business acceptance"],
        "incident_response_guide": ["Contain impact", "stop new work", "preserve sanitized evidence", "notify incident authority", "resume only after reauthorization"],
        "cutover_executed": False,
    }
    runtime_validation = {
        "workflow": ["Requirement", "Approval", "Project", "Assignment", "Queue", "Execution", "Deliverable"],
        "validation_scripts": [
            "Read-only: GET /requirements/{id}/tracking; verify requirement, approval, and project lineage.",
            "Read-only: GET /approvals, /projects, /tasks; reconcile IDs and states against the approved test scope.",
            "Read-only: GET /runtime/monitor; report queue/execution/output counts without creating records.",
            "Authorized non-production execution only after separate approval; this package does not invoke it.",
        ],
        "evidence_template": {"requirement_id": None, "approval_id": None, "project_id": None,
            "assignment_ids": [], "queue_ids": [], "execution_ids": [], "deliverable_ids": [],
            "evidence_status": "Unavailable"},
        "acceptance_criteria": ["Authorized human approval precedes project creation", "Assignment and queue gates pass", "Real execution is traceable", "Deliverable is independently accepted"],
        "failure_criteria": ["Any state/lineage mismatch", "unauthorized access or action", "missing audit event", "failed safety/security/runtime gate"],
        "execution_performed": False,
    }
    observability = {
        "kpi_catalog": [{"metric": name, "value": "Unavailable", "source_required": source}
            for name, source in (
                ("governance metrics", "approval and audit records"), ("workflow metrics", "persisted workflow transitions"),
                ("runtime metrics", "real assignments, queue, execution, deliverables"),
                ("workforce metrics", "current agent/skill/certification/capacity records"),
                ("security metrics", "security events, access violations, policy test records"))],
        "alert_catalog": [{"alert": name, "threshold": "Not configured", "owner": owner}
            for name, owner in (("approval backlog", "Governance Owner"), ("runtime failure", "Runtime Owner"),
                ("credential/adapter failure", "Adapter Owner"), ("security access violation", "Security Owner"),
                ("certification gate failure", "Workforce Owner"))],
        "incident_thresholds": "Not configured; no threshold is inferred by this package.",
        "dashboard_specifications": ["Governance approvals and evidence", "Workflow transitions and aging",
            "Workforce capacity and certification", "Runtime queue/execution/deliverable lineage", "Security incidents and policy coverage"],
        "operational_data_generated": False,
    }
    bcdr = {
        "pilot_recovery_plan": ["Declare incident and stop new work", "identify last verified state and affected records",
            "restore service from approved backup/recovery process", "verify authorization and integrity before resumption"],
        "rollback_plan": ["Migration rollback uses approved backup/compensating plan", "Adapter failure revokes scoped credentials",
            "Model withdrawal blocks new use and routes consumers to governed review", "Certification failure suspends eligibility",
            "Runtime failure stops claims, preserves output/audit, and routes to incident process"],
        "incident_escalation_matrix": [{"incident": name, "authority": authority}
            for name, authority in (("Migration", "DBA/CAB"), ("Adapter", "Adapter Owner/Security"),
                ("Model withdrawal", "Model Governance Owner"), ("Certification failure", "Workforce Owner"),
                ("Runtime failure", "Runtime Owner/Incident Commander"))],
        "recovery_checklists": ["scope impact", "preserve evidence", "authorize recovery", "validate restore", "reconcile audit", "approve service restoration"],
        "service_restoration_criteria": ["Root cause contained", "security controls verified", "dependencies healthy", "business owner and service owner approve restoration"],
        "recovery_tests_executed": False,
    }
    executive = {}
    for board in ("CEO", "COO", "CIO", "Governance Board"):
        source = phase15.get("executive_packages", {}).get(board, {})
        executive[board] = {
            "current_status": "BLOCKED",
            "readiness_score": phase15.get("evidence_readiness_score", "Unavailable"),
            "evidence_completeness": phase15.get("evidence_readiness_score", "Unavailable"),
            "risk_summary": phase15.get("risk_summary", {"assessment_status": "Not assessed"}),
                "open_blockers": phase15.get("missing_evidence", []),
            "recommendation": source.get("recommendation", "NO-GO"),
            "pilot_authorization": "Authorized" if pilot_authorized else "Not Authorized",
            "production_authorization": "Authorized" if production_authorized else "Not Authorized",
        }
    return {
        "package_type": "Phase 16 Controlled Pilot Authorization & Operational Cutover Readiness",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "pilot_authorization": "Authorized" if pilot_authorized else "Not Authorized",
        "production_authorization": "Authorized" if production_authorized else "Not Authorized",
        "pilot_go_no_go": "GO" if pilot_authorized else "NO-GO",
        "production_go_no_go": "GO" if production_authorized else "NO-GO",
        "evidence_readiness_score": phase15.get("evidence_readiness_score", "Unavailable"),
        "missing_evidence": phase15.get("missing_evidence", []),
        "production_authorization_evidence_available": bool(phase14.get("production_authorization_evidence_available")),
        "production_gates": gates,
        "authorization_matrix": [{"gate": gate["gate"], "status": gate["status"], "authority": gate["approval_authority"],
                                   "evidence": gate["required_evidence"]} for gate in gates],
        "pilot_entry_criteria": [gate["exit_criteria"] for gate in gates],
        "pilot_exit_criteria": phase15.get("pilot_completion_framework", {}).get("exit_criteria", []),
        "approval_dependencies": [{"gate": gate["gate"], "depends_on": "Previous authorization gate", "status": gate["status"]} for gate in gates],
        "authorization_checklist": ["All nine gates have current evidence", "Approvers are authorized and independent",
            "Pilot scope, stop authority, support, observability, and rollback are approved"],
        "executive_decision_board": executive,
        "operational_cutover_plan": cutover,
        "runtime_validation_framework": runtime_validation,
        "operational_observability": observability,
        "business_continuity_disaster_recovery": bcdr,
        "metrics": phase15.get("success_measurement", {"metrics": {}}),
        "final_pre_authorization_package": {
            "pilot": {"authorization_readiness": phase15.get("pilot_authorization_readiness", "NO-GO"),
                      "recommendation": "GO" if pilot_authorized else "NO-GO", "status": "Authorized" if pilot_authorized else "Not Authorized"},
            "production": {"authorization_readiness": phase15.get("production_authorization_readiness", "NO-GO"),
                           "recommendation": "GO" if production_authorized else "NO-GO", "status": "Authorized" if production_authorized else "Not Authorized"},
            "evidence_gaps": phase15.get("missing_evidence", []),
            "risk_summary": phase15.get("risk_summary", {"assessment_status": "Not assessed"}),
            "recommended_actions": ["Obtain and verify missing evidence through existing authorized governance workflows.",
                "Rebuild the package after each material approved state change.", "Do not execute pilot or production activities while any required gate is blocked."],
        },
        "actions_performed": [],
        "controls_changed": False,
        "authorizations_created": False,
        "cutover_executed": False,
        "runtime_executed": False,
        "rls_enabled": False,
    }


@router.get("/phase16-authorization-readiness", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def phase16_authorization_readiness(db: Session = Depends(get_db)):
    phase14 = phase14_execution_planning(db)
    phase15 = _build_phase15_governance_package(phase14)
    return _build_phase16_authorization_package(phase15, phase14)


def _build_phase17_operations_monitor(phase15: dict, phase16: dict, audit_events: list[dict]) -> dict:
    evidence_rows = phase15.get("evidence_checklist", [])
    evidence_count = len(evidence_rows)
    complete_evidence = sum(bool(item.get("operationally_complete")) for item in evidence_rows)
    evidence_coverage = round(100 * complete_evidence / evidence_count, 1) if evidence_count else "Unavailable"
    missing_evidence = [item.get("evidence_type", "Unknown") for item in evidence_rows
                        if not item.get("operationally_complete")]

    approval_rows = phase15.get("approval_hub", {}).get("workflow_definitions", [])
    actual_statuses = {"Approved", "Rejected", "Expired", "Pending"}
    received = sum(row.get("decision_status") == "Approved" for row in approval_rows)
    rejected = sum(row.get("decision_status") == "Rejected" for row in approval_rows)
    outstanding = sum(row.get("decision_status") == "Pending" for row in approval_rows)
    required = len(approval_rows)
    authorization_monitor = {
        "pilot": {"status": phase16.get("pilot_authorization", "Not Authorized"), "required_approvals": required,
                  "received_approvals": received, "outstanding_approvals": max(required - received - rejected, 0),
                  "rejected_approvals": rejected, "approvals_created": False},
        "production": {"status": phase16.get("production_authorization", "Not Authorized"), "required_approvals": required,
                       "received_approvals": received, "outstanding_approvals": max(required - received - rejected, 0),
                       "rejected_approvals": rejected, "approvals_created": False},
        "status_source": "Existing recorded decision statuses only; workflow definitions are not approvals.",
    }

    tracking_map = (
        ("Ownership Approval", "ownership_approved", "Ownership Approvals"),
        ("Migration Activities", "migration_applied", "Migration Activities"),
        ("Provider Approvals", "providers_approved", "Provider Approvals"),
        ("Model Approvals", "models_approved", "Model Approvals"),
        ("Certification Events", "certifications_completed", "Certification Events"),
        ("Adapter Configuration Activities", "adapters_configured", "Adapter Activities"),
        ("Runtime Validation Activities", "runtime_validated", "Runtime Validation"),
    )
    gate_map = {item.get("gate"): item for item in phase16.get("production_gates", [])}
    execution_tracking = []
    for label, gate_name, category in tracking_map:
        gate = gate_map.get(gate_name, {})
        decision_status = gate.get("authorization_status", "NotRecorded")
        if gate.get("status") == "READY" and decision_status == "Approved":
            status = "Completed"
        elif decision_status == "Rejected":
            status = "Blocked"
        elif gate.get("status") == "BLOCKED":
            status = "Blocked"
        elif decision_status == "Pending":
            status = "In Progress"
        else:
            status = "Not Started"
        execution_tracking.append({
            "activity": label,
            "category": category,
            "status": status,
            "source_gate": gate_name,
            "evidence": gate.get("current_evidence"),
            "blockers": gate.get("blockers", []),
            "status_is_recorded_execution": status == "Completed",
        })

    evidence_collection = [{
        "evidence_type": row.get("evidence_type"),
        "owner": "Unavailable",
        "approval_status": "NotRecorded",
        "date_submitted": "Unavailable",
        "validation_status": "Verified" if row.get("operationally_complete") else row.get("status", "Unavailable"),
        "evidence": row.get("evidence"),
    } for row in evidence_rows]
    evidence_report = {
        "evidence": evidence_collection,
        "missing_evidence_report": {"items": missing_evidence, "count": len(missing_evidence)},
        "stale_evidence_report": {"items": "Unavailable", "reason": "Source evidence timestamps/expiry metadata are not consistently available."},
        "evidence_coverage_percent": evidence_coverage,
    }

    workflow_metrics = phase15.get("success_measurement", {}).get("metrics", {})
    kpi_names = (
        ("ownership_coverage_percent", "ownership coverage"),
        ("migration_completion_percent", "Migration 24 deployment verification"),
        ("provider_approval_percent", "provider approvals"),
        ("model_approval_percent", "model approvals"),
        ("certification_coverage_percent", "certification coverage"),
        ("adapter_validation_percent", "adapter validation"),
        ("runtime_success_percent", "runtime success"),
    )
    kpis = {}
    domain_gate = {
        "ownership_coverage_percent": "ownership_approved", "migration_completion_percent": "migration_applied",
        "provider_approval_percent": "providers_approved", "model_approval_percent": "models_approved",
        "certification_coverage_percent": "certifications_completed", "adapter_validation_percent": "adapters_configured",
        "runtime_success_percent": "runtime_validated",
    }
    for key, description in kpi_names:
        gate = gate_map.get(domain_gate[key], {})
        is_verified = gate.get("status") == "READY" and gate.get("authorization_status") == "Approved"
        kpis[key] = {"value": 100 if is_verified else "Unavailable", "description": description,
                     "verified": is_verified, "source": gate.get("current_evidence") if is_verified else None}
    kpis.update({name: metric.get("value", "Unavailable") for name, metric in workflow_metrics.items()})

    change_keywords = ("Change", "Migration", "Rollback", "Remediation", "Adapter", "Model", "Approval")
    change_timeline = [event for event in audit_events if any(word.lower() in str(event.get("Action", "")).lower()
                                                               for word in change_keywords)]
    governance_timeline = [event for event in audit_events if any(word.lower() in str(event.get("Action", "")).lower()
                                                                   for word in ("Approval", "Review", "Governance", "Authorization"))]
    risk = phase15.get("risk_dashboard", {})
    compliance = phase15.get("compliance_readiness", {})
    gate_rows = []
    for gate in phase16.get("production_gates", []):
        approval_status = gate.get("authorization_status", "NotRecorded")
        if gate.get("status") == "READY" and approval_status == "Approved":
            display_status = "Approved"
        elif gate.get("status") == "READY":
            display_status = "Ready"
        else:
            display_status = "Locked"
        gate_rows.append({"gate": gate.get("gate"), "label": gate.get("label"),
            "status": gate.get("status", "BLOCKED"), "display_status": display_status,
            "evidence": gate.get("current_evidence"), "approvals": approval_status,
            "blockers": gate.get("blockers", [])})

    executive = {}
    for name in ("CEO", "COO", "CIO", "Governance Board"):
        source = phase16.get("executive_decision_board", {}).get(name, {})
        executive[name] = {
            "authorization_status": source.get("current_status", "BLOCKED"),
            "execution_status": "No tracked completion evidence" if not any(row["status"] == "Completed" for row in execution_tracking) else "See recorded activities",
            "risk_status": risk.get("status", "Unavailable"),
            "compliance_status": compliance.get("status", "Not assessed"),
            "operational_status": phase16.get("pilot_go_no_go", "NO-GO"),
            "blockers": phase16.get("final_pre_authorization_package", {}).get("evidence_gaps", []),
            "recommendation": source.get("recommendation", "NO-GO"),
        }

    return {
        "package_type": "Phase 17 Operational Execution Tracking",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "execution_tracking_center": {"activities": execution_tracking,
            "statuses": ["Not Started", "In Progress", "Completed", "Blocked", "Cancelled"],
            "tracking_records_created": False},
        "evidence_collection_center": evidence_report,
        "evidence_coverage_percent": evidence_coverage,
        "authorization_monitor": authorization_monitor,
        "operational_kpis": kpis,
        "change_activity": {"approved_changes": [event for event in change_timeline if event.get("Outcome") == "Approved"],
            "pending_changes": [event for event in change_timeline if event.get("Outcome") in {"Pending", "NeedsReview"}],
            "rejected_changes": [event for event in change_timeline if event.get("Outcome") == "Rejected"],
            "rollback_activities": [event for event in change_timeline if "rollback" in str(event.get("Action", "")).lower()],
            "change_timeline": change_timeline, "governance_timeline": governance_timeline,
            "audit_timeline": audit_events},
        "risk_monitor": {"status": risk.get("status", "Unavailable: risks not assessed"),
            "open_risks": "Unavailable" if risk.get("status", "").startswith("Unavailable") else None,
            "mitigated_risks": "Unavailable", "accepted_risks": "Unavailable", "escalated_risks": "Unavailable",
            "dashboard": risk},
        "compliance_monitor": {"status": compliance.get("status", "Not assessed"),
            "areas": compliance.get("checklist", []), "exceptions": compliance.get("exception_register", {"status": "Unavailable"})},
        "executive_operations_dashboard": executive,
        "production_gate_monitor": gate_rows,
        "pilot_authorization_status": phase16.get("pilot_authorization", "Not Authorized"),
        "production_authorization_status": phase16.get("production_authorization", "Not Authorized"),
        "actions_performed": [], "controls_changed": False, "tracking_records_created": False,
        "approvals_created": False, "risk_records_created": False, "compliance_inferred": False,
    }


@router.get("/phase17-operational-tracking", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def phase17_operational_tracking(db: Session = Depends(get_db)):
    phase15 = phase15_governance_evidence(db)
    phase16 = phase16_authorization_readiness(db)
    audit_events = db.execute(text("""
        SELECT TOP 200 AuditLogID,ActorType,Action,ResourceType,Outcome,CreatedAtUtc
        FROM dbo.AuditLog
        ORDER BY CreatedAtUtc DESC,AuditLogID DESC
    """)).mappings().all()
    events = [dict(row) for row in audit_events]
    return _build_phase17_operations_monitor(phase15, phase16, events)


@router.get("/ai-governance/shadow-review", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def ai_governance_shadow_review(db: Session = Depends(get_db)):
    """Return read-only evidence-bound recommendations without decision authority."""
    snapshot = phase17_operational_tracking(db)
    return build_shadow_review(snapshot)


@router.get("/ai-governance/assurance-platform", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def ai_governance_assurance_platform(db: Session = Depends(get_db)):
    """Return reproducibility and Level 3 readiness analytics without persistence."""
    snapshot = phase17_operational_tracking(db)
    return build_assurance_platform(snapshot)


def _governance_capability_catalog() -> list[dict]:
    return [{"capability": name, "api_reference": api, "dashboard_reference": dashboard,
             "test_reference": f"tests/{test}", "documentation_reference": f"docs/{doc}", "gate_key": gate}
            for name, api, dashboard, test, doc, gate in _governance_capability_rows()]


def _governance_capability_rows():
    return [
        ("Unified Governance Command Center", "/operations/governance-command-center", "/admin-control-center", "test_operations_reports.py", "Phase_17_Operational_Execution_Tracking.md", "governance"),
        ("Executive Command Center", "/dashboard/api/executive/{view}", "/executive-command-center", "test_executive_dashboard.py", "Owner_Command_Center.md", "executive"),
        ("Approval Authority Matrix", "/approvals", "/approval-center", "test_approval_roles.py", "Security_Access_Model.md", "authorization"),
        ("Ownership Governance Tracking", "/operations/ownership-remediation/approval-package", "/admin-control-center", "test_operations_reports.py", "Phase_11_Deployment_Readiness.md", "ownership_approved"),
        ("Migration Governance Tracking", "/operations/migration-24/validation", "/admin-control-center", "test_operations_reports.py", "Phase_11_Deployment_Readiness.md", "migration_applied"),
        ("Provider Governance Tracking", "/operations/model-onboarding/package", "/admin-control-center", "test_model_governance.py", "AI_Model_Governance.md", "providers_approved"),
        ("Model Governance Tracking", "/governance/models/catalog", "/admin-control-center", "test_model_governance.py", "AI_Model_Governance.md", "models_approved"),
        ("Certification Governance Tracking", "/operations/certification-campaign", "/admin-control-center", "test_agent_certification_api.py", "Phase_10_Operational_Activation_Preparation.md", "certifications_completed"),
        ("Adapter Governance Tracking", "/operations/execution-adapters/deployment-package", "/admin-control-center", "test_execution_adapters.py", "Phase_9_Operational_Readiness.md", "adapters_configured"),
        ("Runtime Governance Tracking", "/runtime/monitor", "/admin-control-center", "test_agent_runtime.py", "Phase_9_Operational_Readiness.md", "runtime_validated"),
        ("Pilot Authorization Tracking", "/operations/phase16-authorization-readiness", "/admin-control-center", "test_operations_reports.py", "Phase_16_Pilot_Authorization_Cutover_Readiness.md", "pilot_authorization"),
        ("Production Authorization Tracking", "/operations/phase16-authorization-readiness", "/admin-control-center", "test_operations_reports.py", "Phase_16_Pilot_Authorization_Cutover_Readiness.md", "production_authorization"),
        ("Operational Readiness Monitoring", "/operations/phase9-readiness", "/admin-control-center", "test_operations_dashboard.py", "Phase_9_Operational_Readiness.md", "operational"),
        ("Evidence Monitoring", "/operations/phase15-governance-evidence", "/admin-control-center", "test_operations_reports.py", "Phase_15_Pilot_Governance_Evidence_Management.md", "evidence"),
        ("Change Control Monitoring", "/operations/phase15-governance-evidence", "/admin-control-center", "test_operations_reports.py", "Phase_15_Pilot_Governance_Evidence_Management.md", "change"),
        ("Compliance Monitoring", "/operations/phase15-governance-evidence", "/admin-control-center", "test_operations_reports.py", "Phase_15_Pilot_Governance_Evidence_Management.md", "compliance"),
        ("Risk Monitoring", "/operations/phase15-governance-evidence", "/admin-control-center", "test_operations_reports.py", "Phase_15_Pilot_Governance_Evidence_Management.md", "risk"),
        ("Audit Monitoring", "/operations/phase17-operational-tracking", "/admin-control-center", "test_operations_reports.py", "Phase_17_Operational_Execution_Tracking.md", "audit"),
        ("Security Monitoring", "/operations/phase16-authorization-readiness", "/executive-command-center", "test_authorization_middleware.py", "Security_Access_Model.md", "security_review_completed"),
        ("RLS Readiness Monitoring", "/operations/rls-readiness/package", "/admin-control-center", "test_rls_artifacts.py", "RLS_Deployment_Guide.md", "rls_approved"),
        ("Production Gate Monitoring", "/operations/phase16-authorization-readiness", "/admin-control-center", "test_operations_reports.py", "Phase_16_Pilot_Authorization_Cutover_Readiness.md", "production_gate"),
        ("KPI Monitoring", "/operations/phase17-operational-tracking", "/admin-control-center", "test_operations_reports.py", "Phase_17_Operational_Execution_Tracking.md", "kpi"),
        ("BCDR Monitoring", "/operations/phase16-authorization-readiness", "/admin-control-center", "test_operations_reports.py", "Phase_16_Pilot_Authorization_Cutover_Readiness.md", "bcdr"),
        ("Cutover Monitoring", "/operations/phase16-authorization-readiness", "/admin-control-center", "test_operations_reports.py", "Phase_16_Pilot_Authorization_Cutover_Readiness.md", "cutover"),
        ("Operational Dashboard Consolidation", "/operations/phase17-operational-tracking", "/admin-control-center", "test_operations_reports.py", "Phase_17_Operational_Execution_Tracking.md", "dashboard"),
        ("Readiness Score Engine", "/operations/phase12-activation-readiness", "/admin-control-center", "test_operations_reports.py", "Phase_12_Operational_Activation_Readiness.md", "readiness"),
        ("Go / No-Go Decision Engine", "/operations/phase16-authorization-readiness", "/admin-control-center", "test_operations_reports.py", "Phase_16_Pilot_Authorization_Cutover_Readiness.md", "go_no_go"),
        ("Executive Reporting", "/operations/executive-readiness/{view}", "/executive-command-center", "test_executive_dashboard.py", "Owner_Command_Center.md", "executive_report"),
        ("Operational Reporting", "/operations/operational-readiness", "/admin-control-center", "test_operations_dashboard.py", "Phase_9_Operational_Readiness.md", "operational_report"),
        ("UAT Traceability Matrix", "/operations/uat-readiness", "/admin-control-center", "test_operations_reports.py", "Quality_Audit_2026-10-23.md", "uat"),
    ]


def _build_unified_governance_package(phase17: dict) -> dict:
    gate_by_name = {item.get("gate"): item for item in phase17.get("production_gate_monitor", [])}
    aliases = {"ownership_approved": "ownership_complete", "migration_applied": "migration_complete",
        "providers_approved": "provider_approved", "models_approved": "model_approved",
        "certifications_completed": "agents_certified", "pilot_authorization": "runtime_validated",
        "production_authorization": "runtime_validated", "production_gate": "ownership_complete",
        "operational": "runtime_validated", "operational_report": "runtime_validated",
        "readiness": "runtime_validated", "go_no_go": "runtime_validated", "security_review_completed": "security_review_completed",
        "rls_approved": "rls_approved"}
    source_sections = {
        "risk": phase17.get("risk_monitor"), "compliance": phase17.get("compliance_monitor"),
        "evidence": phase17.get("evidence_collection_center"), "change": phase17.get("change_activity"),
        "audit": phase17.get("change_activity", {}).get("audit_timeline"),
        "kpi": phase17.get("operational_kpis"), "bcdr": None, "cutover": None,
        "dashboard": phase17.get("executive_operations_dashboard"),
        "executive_report": phase17.get("executive_operations_dashboard"),
        "uat": phase17.get("evidence_collection_center"), "governance": phase17.get("authorization_monitor"),
        "authorization": phase17.get("authorization_monitor"),
    }
    coverage_fields = ("api_reference", "dashboard_reference", "test_reference", "documentation_reference")
    capability_rows = []
    for row in _governance_capability_catalog():
        gate = gate_by_name.get(aliases.get(row["gate_key"], row["gate_key"]))
        if gate is None:
            source = source_sections.get(row["gate_key"])
            if source is None:
                status = "UNVERIFIED"
                blockers = ["No corresponding verified Phase 17 source is available."]
                evidence = None
            else:
                status = "BLOCKED"
                blockers = ["Source is mapped, but operational acceptance evidence/authorization is incomplete."]
                evidence = source
        else:
            status = "READY" if gate.get("display_status") == "Approved" else "BLOCKED"
            blockers = gate.get("blockers", [])
            evidence = gate.get("evidence")
        capability_rows.append({**row, "status": status, "evidence": evidence, "blockers": blockers,
            "coverage": {field: "Source Mapped" if row.get(field) else "Unavailable" for field in coverage_fields},
            "audit_reference": "/operations/phase17-operational-tracking",
            "audit_coverage_status": "Mapped; per-capability completeness Unverified",
            "governance_control_reference": row["gate_key"],
            "governance_control_status": status,
            "test_execution_status": "Not Run by this package", "acceptance_status": "Not Accepted"})
    counts = {status: sum(row["status"] == status for row in capability_rows)
              for status in ("READY", "BLOCKED", "UNVERIFIED")}
    production_gates = phase17.get("production_gate_monitor", [])
    approved_gate_count = sum(item.get("display_status") == "Approved" for item in production_gates)
    readiness_percent = round(100 * approved_gate_count / len(production_gates), 1) if production_gates else "Unavailable"
    pilot_authorization_percent = round(100 * approved_gate_count / len(production_gates), 1) if production_gates else "Unavailable"
    production_authorization_percent = (
        100.0 if production_gates and approved_gate_count == len(production_gates)
        and phase17.get("production_authorization_status") == "Authorized" else 0.0 if production_gates else "Unavailable"
    )
    return {
        "package_type": "Unified Governance Command Center",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "source_status": {"pilot": phase17.get("pilot_authorization_status", "Not Authorized"),
                          "production": phase17.get("production_authorization_status", "Not Authorized"),
                          "evidence_coverage_percent": phase17.get("evidence_coverage_percent", "Unavailable")},
        "operational_readiness_percent": readiness_percent,
        "pilot_authorization_readiness_percent": pilot_authorization_percent,
        "production_authorization_readiness_percent": production_authorization_percent,
        "pilot_authorization": phase17.get("pilot_authorization_status", "Not Authorized"),
        "production_authorization": phase17.get("production_authorization_status", "Not Authorized"),
        "uat_readiness_status": _build_uat_readiness_package(phase17)["uat_readiness_status"],
        "capabilities": capability_rows,
        "capability_counts": counts,
        "executive_views": phase17.get("executive_operations_dashboard", {}),
        "operational_monitor": phase17,
        "approvals_created": False,
        "controls_changed": False,
        "actions_performed": [],
    }


def _build_uat_readiness_package(phase17: dict) -> dict:
    scenarios = [
        ("Authentication", "POST /auth/login; GET /auth/me; POST /auth/logout", "Login/profile pages", "tests/test_auth_dependencies.py", "docs/Security_Access_Model.md", "Valid login/session persistence; invalid credentials denied."),
        ("Authorization", "Role-protected business and operations endpoints", "Role-scoped navigation and pages", "tests/test_authorization_middleware.py", "docs/Security_Access_Model.md", "Authorized role allowed; unauthorized role denied without data leakage."),
        ("AI CEO", "POST /requirements/{id}/assess", "Requirement intake and tracker", "tests/test_operations_reports.py", "docs/Requirement_Management.md", "Advisory assessment persists with assumptions, risks, and human gate."),
        ("Requirement Workflow", "POST /requirements; GET /requirements/{id}/tracking", "Requirement intake and My requests", "tests/test_requirement_access.py", "docs/Requirement_Management.md", "Owner-scoped request state and timeline are consistent."),
        ("Approval Workflow", "GET /approvals; POST /approvals/{id}/decision", "Approval Center", "tests/test_approval_roles.py", "docs/Security_Access_Model.md", "Only authorized approver decides; reason and audit event persist."),
        ("Project Creation", "Approval decision and GET /projects", "Project registry and tracker", "tests/test_project_factory_ownership.py", "docs/Workflows.md", "Project is created only after approval; ownership lineage is present."),
        ("Planning", "GET /tasks; GET /workforce/capacity", "Workforce Planning", "tests/test_operations_dashboard.py", "docs/Workflows.md", "Planned tasks, estimates, dependencies, and staffing gaps reconcile."),
        ("Workforce Reuse", "GET /workforce/reuse-assessments; GET /workforce/reuse-metrics", "Workforce Planning", "tests/test_workforce_planner_schema_fallback.py", "docs/Phase_12_Operational_Activation_Readiness.md", "Migration-dependent data is explicit; candidates require evidence and approval."),
        ("Agent Assignment", "GET /workforce/candidates; governed assignment workflow", "Workforce Planning", "tests/test_agent_certification_api.py", "docs/Phase_10_Operational_Activation_Preparation.md", "Only qualified, certified, available agents are eligible."),
        ("Task Management", "GET /tasks; governed task status endpoint", "My projects and tasks", "tests/test_project_access.py", "docs/Workflows.md", "Task status and ownership rules are enforced."),
        ("Notifications", "GET /notifications; POST /notifications/{id}/read", "Workspace inbox", "tests/test_dashboard_scope.py", "docs/Workflows.md", "Recipient scope and dashboard/API counts reconcile."),
        ("Audit Trail", "GET /operations/phase17-operational-tracking", "Governance operations", "tests/test_operations_reports.py", "docs/Phase_17_Operational_Execution_Tracking.md", "Audit chronology is source-backed and never manufactured."),
        ("Reporting", "GET /dashboard/api; GET /dashboard/api/me", "Workspace dashboard", "tests/test_dashboard_scope.py", "docs/Owner_Command_Center.md", "Summary counts match authorized visible records."),
        ("Executive Dashboards", "GET /operations/executive-readiness/{view}", "Executive Command Center", "tests/test_executive_dashboard.py", "docs/Owner_Command_Center.md", "CEO/COO/CIO metrics expose scope, blockers, and actual evidence."),
        ("Operations Dashboards", "GET /operations/phase17-operational-tracking", "Admin Control Center", "tests/test_operations_dashboard.py", "docs/Phase_17_Operational_Execution_Tracking.md", "Unavailable data remains unavailable; gates reflect verified records."),
        ("Governance Controls", "GET /operations/phase15-governance-evidence; GET /operations/phase16-authorization-readiness", "Governance package exports", "tests/test_operations_reports.py", "docs/Phase_16_Pilot_Authorization_Cutover_Readiness.md", "Planning artifacts do not create approvals or change control state."),
        ("Model Governance", "GET /governance/models/catalog; governed proposal/decision routes", "Model governance center", "tests/test_model_governance.py", "docs/AI_Model_Governance.md", "Proposal, independent review, lifecycle and audit evidence reconcile."),
        ("Certification Governance", "GET /operations/certification-campaign; GET /operations/certification-dashboard", "Certification campaign", "tests/test_agent_certification_api.py", "docs/Phase_10_Operational_Activation_Preparation.md", "Latest required evaluations and role skill evidence determine status."),
        ("Deployment Readiness", "GET /operations/migration-24/validation; GET /operations/phase11-deployment-package", "Deployment readiness package", "tests/test_operations_reports.py", "docs/Phase_11_Deployment_Readiness.md", "Static validation is not migration execution or authorization."),
        ("Pilot Readiness", "GET /operations/phase14-execution-planning; GET /operations/phase16-authorization-readiness", "Pilot planning and authorization exports", "tests/test_operations_reports.py", "docs/Phase_16_Pilot_Authorization_Cutover_Readiness.md", "Pilot stays Not Authorized until every required gate and approval passes."),
        ("Production Readiness", "GET /operations/phase16-authorization-readiness", "Production gate monitor", "tests/test_operations_reports.py", "docs/Phase_16_Pilot_Authorization_Cutover_Readiness.md", "Production remains Not Authorized without explicit evidence and approval."),
    ]
    scenarios_out = []
    for index, (area, api, dashboard, test, documentation, acceptance) in enumerate(scenarios, start=1):
        gate_status = "BLOCKED"
        evidence_status = "Source Mapped" if api and dashboard and test and documentation else "Unavailable"
        scenarios_out.append({
            "scenario_id": f"UAT-{index:03d}", "area": area,
            "api_reference": api, "dashboard_reference": dashboard,
            "test_reference": test, "documentation_reference": documentation,
            "audit_reference": "/operations/phase17-operational-tracking",
            "governance_reference": "/operations/phase16-authorization-readiness",
            "acceptance_criteria": acceptance,
            "preconditions": ["Use authorized non-production account and approved synthetic/controlled test data."],
            "evidence_required": ["timestamp", "role", "request/response status", "redacted record IDs", "audit correlation where applicable"],
            "execution_status": "Not Run", "acceptance_status": "Not Accepted",
            "source_coverage_status": evidence_status, "evidence_status": evidence_status,
            "readiness_status": gate_status,
            "defects": [],
        })
    categories = {
        "P0": "Safety/security/legal violation, unauthorized production action, or material data exposure; stop immediately.",
        "P1": "Critical workflow, authorization, integrity, or recovery failure blocks UAT/pilot.",
        "P2": "Major functional/governance defect with a workaround or limited scope.",
        "P3": "Minor usability, wording, or non-blocking reporting defect.",
    }
    missing = [row["scenario_id"] for row in scenarios_out if row["execution_status"] != "Passed"]
    uat_ready_for_execution = (
        phase17.get("pilot_authorization_status") == "Authorized"
        and phase17.get("evidence_coverage_percent") == 100
    )
    for scenario in scenarios_out:
        scenario["readiness_status"] = "READY FOR EXECUTION" if uat_ready_for_execution else "BLOCKED"
    return {
        "package_type": "UAT Readiness and Traceability Package",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "uat_readiness_status": "READY FOR FORMAL UAT EXECUTION (NOT RUN)" if uat_ready_for_execution
            else "NOT READY: authorization/evidence gates blocked",
        "pilot_authorization": phase17.get("pilot_authorization_status", "Not Authorized"),
        "production_authorization": phase17.get("production_authorization_status", "Not Authorized"),
        "uat_checklist": ["Confirm environment/build and role accounts", "Approve test scope and data handling",
            "Run each scenario and capture evidence", "Record defects with severity and owner", "Obtain independent acceptance sign-off"],
        "scenarios": scenarios_out,
        "test_data_matrix": [{"scenario_id": row["scenario_id"], "area": row["area"],
            "data_class": "Synthetic or approved minimum necessary", "source": "Not created by package",
            "sensitive_data_allowed": False, "fixture_created": False} for row in scenarios_out],
        "traceability_matrix": scenarios_out,
        "acceptance_criteria": [{"scenario_id": row["scenario_id"], "area": row["area"],
            "criteria": row["acceptance_criteria"], "status": row["acceptance_status"]} for row in scenarios_out],
        "evidence_requirements": [{"scenario_id": row["scenario_id"], "items": row["evidence_required"],
            "status": "Unavailable until scenario is executed"} for row in scenarios_out],
        "defect_classification_matrix": categories,
        "missing_or_unexecuted_scenarios": missing,
        "source_evidence_coverage_percent": "Unavailable: source references are not UAT execution evidence",
        "fake_test_data_created": False, "uat_executed": False, "approvals_created": False,
    }


@router.get("/governance-command-center", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def governance_command_center(db: Session = Depends(get_db)):
    phase17 = phase17_operational_tracking(db)
    return _build_unified_governance_package(phase17)


@router.get("/uat-readiness", dependencies=[Depends(require_roles(*EXEC_ROLES))])
def uat_readiness(db: Session = Depends(get_db)):
    phase17 = phase17_operational_tracking(db)
    return _build_uat_readiness_package(phase17)