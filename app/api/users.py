import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.models.entities import AppUser, Role
from app.schemas.schemas import UserRegister
from app.security.passwords import hash_password

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

@router.post("/register")
def register_user(
    body: UserRegister,
    db: Session = Depends(get_db)
):
    user_role = db.execute(
        select(Role).where(Role.RoleCode == "BUSINESS_USER", Role.IsActive == True)
    ).scalars().first()
    if not user_role:
        user_role = db.execute(
            select(Role).where(Role.RoleCode == "USER", Role.IsActive == True)
        ).scalars().first()
    if not user_role:
        raise HTTPException(
            status_code=503,
            detail="Account roles are not initialized. Ask an administrator to apply the user-role setup migration.",
        )

    normalized_email = body.email.strip().lower()
    existing = db.execute(
        select(AppUser).where(func.lower(AppUser.Email) == normalized_email)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = AppUser(
        UserID=uuid.uuid4(),
        Email=normalized_email,
        PasswordHash=hash_password(body.password),
        DisplayName=f"{body.first_name.strip()} {body.last_name.strip()}",
        Department=body.department,
        IsActive=True,
        RoleID=user_role.RoleID,
    )

    db.add(user)
    try:
        db.flush()
        db.execute(text("""
            INSERT dbo.AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
            VALUES(:correlation,'User',:actor,'UserRegistered','AppUser',:resource,'Success','{}')
        """), {
            "correlation": uuid.uuid4(),
            "actor": str(user.UserID),
            "resource": str(user.UserID),
        })
        db.commit()
    except IntegrityError as error:
        db.rollback()
        duplicate = db.execute(
            select(AppUser).where(func.lower(AppUser.Email) == normalized_email)
        ).scalar_one_or_none()
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists",
            ) from error
        raise

    return {
        "message": "User registered successfully"
    }