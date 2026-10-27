from pydantic import BaseModel, Field
from typing import Optional

class RequirementCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str
    requested_by: str = "HumanOwner"
    priority: str = "Medium"

class ProjectCreate(BaseModel):
    name: str
    objective: str
    business_owner: str = "HumanOwner"
    budget: float = 0

class TaskCreate(BaseModel):
    project_id: str
    description: str
    priority: str = "Medium"
    assigned_agent_id: Optional[str] = None
    risk_level: str = "Low"
    budget_limit: float = 0
    token_limit: int = 10000
