from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


RiskLevel = Literal["Low", "Medium", "High", "Critical"]
Priority = Literal["Low", "Medium", "High", "Critical"]

Complexity = Literal[
    "Low",
    "Medium",
    "High",
    "Critical"
]

Feasibility = Literal[
    "Feasible",
    "FeasibleWithConditions",
    "MoreInformationRequired",
    "NotFeasible"
]


class DepartmentRecommendation(BaseModel):
    department_name: str = Field(
        min_length=2,
        max_length=150
    )

    responsibility: str = Field(
        min_length=5,
        max_length=1000
    )

    is_lead_department: bool = False
    priority: Priority = "Medium"


class SkillRecommendation(BaseModel):
    skill_name: str = Field(
        min_length=2,
        max_length=150
    )

    priority: Priority = "Medium"

    minimum_proficiency: int = Field(
        default=3,
        ge=1,
        le=5
    )

    purpose: str = Field(
        min_length=5,
        max_length=1000
    )

    estimated_effort_hours: Decimal | None = Field(
        default=None,
        ge=0,
        le=100000
    )

    is_mandatory: bool = True


class RiskRecommendation(BaseModel):
    title: str = Field(
        min_length=3,
        max_length=250
    )

    risk_level: RiskLevel

    description: str = Field(
        min_length=5,
        max_length=2000
    )

    mitigation: str = Field(
        min_length=5,
        max_length=2000
    )


class CEOAssessmentResult(BaseModel):
    classification: str = Field(
        min_length=3,
        max_length=100
    )

    business_domain: str | None = Field(
        default=None,
        max_length=150
    )

    complexity: Complexity
    risk_level: RiskLevel
    feasibility: Feasibility

    feasibility_score: Decimal | None = Field(
        default=None,
        ge=0,
        le=100
    )

    confidence_score: Decimal | None = Field(
        default=None,
        ge=0,
        le=100
    )

    executive_summary: str = Field(
        min_length=20,
        max_length=2000
    )

    departments: list[DepartmentRecommendation] = Field(
        min_length=1,
        max_length=20
    )

    required_skills: list[SkillRecommendation] = Field(
        min_length=1,
        max_length=50
    )

    risks: list[RiskRecommendation] = Field(
        default_factory=list,
        max_length=50
    )

    assumptions: list[str] = Field(
        default_factory=list,
        max_length=50
    )

    constraints: list[str] = Field(
        default_factory=list,
        max_length=50
    )

    human_approval_required: bool

    @field_validator("departments")
    @classmethod
    def ensure_single_lead_department(
        cls,
        departments: list[DepartmentRecommendation]
    ):
        lead_count = sum(
            department.is_lead_department
            for department in departments
        )

        if lead_count != 1:
            raise ValueError(
                "Exactly one lead department is required."
            )

        return departments


class RequirementAssessmentResponse(BaseModel):
    requirement_id: UUID
    assessment_id: UUID
    correlation_id: UUID
    status: str
    assessment: CEOAssessmentResult