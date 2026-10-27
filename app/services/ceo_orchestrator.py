import uuid

from datetime import datetime, timezone

from fastapi import HTTPException

from app.schemas.schemas import CEOAssessmentResult


class CEOOrchestrator:

    def __init__(
        self,
        requirements,
        agents,
        assessments,
        audit,
        provider,
        policy,
        approval_service=None,
        project_factory=None,
        workforce_manager=None
    ):

        self.requirements = requirements
        self.agents = agents
        self.assessments = assessments
        self.audit = audit
        self.provider = provider
        self.policy = policy

        self.approval_service = approval_service
        self.project_factory = project_factory
        self.workforce_manager = workforce_manager

    def assess(
        self,
        db,
        requirement_id,
        requested_by,
        force=False
    ):

        correlation_id = uuid.uuid4()

        req = self.requirements.get_for_update(
            db,
            requirement_id
        )

        if not req:
            raise HTTPException(
                404,
                "Requirement not found"
            )

        valid_statuses = (
            {
                "Submitted",
                "Assessed",
                "AssessmentFailed"
            }
            if force
            else {
                "Submitted",
                "Assessed"
            }
        )

        if req.Status not in valid_statuses:

            raise HTTPException(
                409,
                f"Cannot assess from status {req.Status}"
            )

        ceo = self.agents.get_active_ceo(db)

        if not ceo:

            raise HTTPException(
                409,
                "No active AI CEO"
            )

        self.audit.write(
            db,
            correlation_id,
            "Agent",
            str(ceo.AgentID),
            "RequirementAssessmentStarted",
            "Requirement",
            str(requirement_id),
            "Started"
        )

        try:

            result = CEOAssessmentResult.model_validate(
                self.provider.assess(req)
            )

            result = self.policy.apply(
                req,
                result
            )

            version = self.assessments.next_version(
                db,
                requirement_id
            )

            row = self.assessments.create(
                db,
                req,
                ceo,
                correlation_id,
                version,
                result,
                requested_by
            )

            req.RiskLevel = result.risk_level

            req.ModifiedAtUtc = datetime.now(
                timezone.utc
            )

            req.ModifiedBy = ceo.AgentName

            if result.human_approval_required:

                req.Status = "PendingApproval"

                if self.approval_service:

                    self.approval_service.create_approval(
                        db,
                        req,
                        result,
                        correlation_id
                    )

            else:

                req.Status = "Approved"

                self._build_company(
                    db,
                    req,
                    result
                )

            self.audit.write(
                db,
                correlation_id,
                "Agent",
                str(ceo.AgentID),
                "RequirementAssessed",
                "Requirement",
                str(requirement_id),
                "Success",
                {
                    "assessment_id":
                        str(
                            row.RequirementAssessmentID
                        )
                }
            )

            db.commit()

            db.refresh(row)

            return row, result

        except Exception:

            db.rollback()

            raise

    def _build_company(
        self,
        db,
        requirement,
        assessment
    ):

        if not self.project_factory:
            return
        project_id = self.project_factory.create_project(db, requirement, assessment)
        return project_id