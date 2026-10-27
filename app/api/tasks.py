from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.dependencies import get_current_user
from app.services.security_service import SecurityService

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("")
def list_tasks(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return SecurityService(db).GetVisibleTasks(user)


@router.get("/{task_id}")
def get_task(task_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = SecurityService(db).GetVisibleTasks(user, task_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Task not found")
    return rows[0]
