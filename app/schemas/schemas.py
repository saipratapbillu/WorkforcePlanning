from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field
Priority=Literal["Low","Medium","High","Critical"]

class RequirementCreate(BaseModel):
    title:str=Field(min_length=3,max_length=200)
    description:str=Field(min_length=10)
    requested_by:str=Field(min_length=2,max_length=200)
    priority:Priority

class RequirementUpdate(BaseModel):
    title:str|None=Field(default=None,min_length=3,max_length=200)
    description:str|None=Field(default=None,min_length=10)
    requested_by:str|None=Field(default=None,min_length=2,max_length=200)
    priority:Priority|None=None
    modified_by:str=Field(default="HumanOwner",min_length=2,max_length=200)

class AssessmentRequest(BaseModel):
    requested_by:str="HumanOwner"
    force_reassessment:bool=False

class ApprovalDecisionRequest(BaseModel):
    action:Literal["approve","reject","request_information"]
    reason:str=Field(min_length=5,max_length=2000)

class DepartmentRecommendation(BaseModel):
    department_name:str
    responsibility:str
    is_lead_department:bool=False
    priority:Priority="Medium"

class SkillRecommendation(BaseModel):
    skill_name:str
    priority:Priority="Medium"
    minimum_proficiency:int=Field(default=3,ge=1,le=5)
    purpose:str
    estimated_effort_hours:float|None=Field(default=None,ge=0)
    is_mandatory:bool=True

class RiskRecommendation(BaseModel):
    title:str; risk_level:Priority; description:str; mitigation:str

class CEOAssessmentResult(BaseModel):
    classification:str
    business_domain:str|None=None
    complexity:Priority
    risk_level:Priority
    feasibility:Literal["Feasible","FeasibleWithConditions","MoreInformationRequired","NotFeasible"]
    feasibility_score:float|None=Field(default=None,ge=0,le=100)
    confidence_score:float|None=Field(default=None,ge=0,le=100)
    executive_summary:str
    departments:list[DepartmentRecommendation]
    required_skills:list[SkillRecommendation]
    risks:list[RiskRecommendation]=[]
    assumptions:list[str]=[]
    constraints:list[str]=[]
    human_approval_required:bool

class AssessmentResponse(BaseModel):
    requirement_id:UUID
    assessment_id:UUID
    correlation_id:UUID
    status:str
    assessment:CEOAssessmentResult

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    token: str
    email: str
    role: str

class UserCreate(BaseModel):
    email: str
    password: str
    display_name: str
    department: str | None = None
    role_id: UUID

class UserRegister(BaseModel):

    first_name: str
    last_name: str
    email: str

    mobile_number: str | None = None

    department: str | None = None

    position_title: str | None = None

    office_location: str | None = None

    password: str = Field(min_length=12, max_length=128)