import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func
)
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RequirementAssessment(Base):
    __tablename__ = "RequirementAssessment"

    __table_args__ = (
        UniqueConstraint(
            "RequirementID",
            "AssessmentVersion",
            name="UX_RequirementAssessment_Version"
        ),
        CheckConstraint(
            "Complexity IN "
            "('Low','Medium','High','Critical')",
            name="CK_RequirementAssessment_Complexity"
        ),
        CheckConstraint(
            "RiskLevel IN "
            "('Low','Medium','High','Critical')",
            name="CK_RequirementAssessment_Risk"
        ),
    )

    RequirementAssessmentID: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER,
        primary_key=True,
        default=uuid.uuid4
    )

    RequirementID: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER,
        ForeignKey("Requirement.RequirementID"),
        nullable=False
    )

    AssessedByAgentID: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER,
        ForeignKey("Agent.AgentID"),
        nullable=False
    )

    CorrelationID: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER,
        nullable=False,
        index=True
    )

    AssessmentVersion: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1
    )

    Classification: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    BusinessDomain: Mapped[str | None] = mapped_column(
        String(150)
    )

    Complexity: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    RiskLevel: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    Feasibility: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    FeasibilityScore: Mapped[float | None] = mapped_column(
        Numeric(5, 2)
    )

    ConfidenceScore: Mapped[float | None] = mapped_column(
        Numeric(5, 2)
    )

    ExecutiveSummary: Mapped[str] = mapped_column(
        String(2000),
        nullable=False
    )

    AssumptionsJson: Mapped[str | None] = mapped_column(Text)
    ConstraintsJson: Mapped[str | None] = mapped_column(Text)
    RisksJson: Mapped[str | None] = mapped_column(Text)

    AssessmentJson: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    HumanApprovalRequired: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    AssessmentStatus: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Completed"
    )

    Model: Mapped[str | None] = mapped_column(String(100))
    ModelVersion: Mapped[str | None] = mapped_column(String(50))
    PromptVersion: Mapped[str | None] = mapped_column(String(50))

    CreatedAtUtc: Mapped[object] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.sysutcdatetime()
    )

    CreatedBy: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )

    departments = relationship(
        "RequirementAssessmentDepartment",
        cascade="all, delete-orphan"
    )


class RequirementAssessmentDepartment(Base):
    __tablename__ = "RequirementAssessmentDepartment"

    RequirementAssessmentID: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER,
        ForeignKey(
            "RequirementAssessment.RequirementAssessmentID"
        ),
        primary_key=True
    )

    DepartmentID: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER,
        ForeignKey("Department.DepartmentID"),
        primary_key=True
    )

    Responsibility: Mapped[str] = mapped_column(
        String(1000),
        nullable=False
    )

    IsLeadDepartment: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    Priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Medium"
    )

    Status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Proposed"
    )