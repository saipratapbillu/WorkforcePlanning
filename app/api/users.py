# users api blueprint
import uuid

from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException

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
        select(Role).where(Role.RoleCode == "USER", Role.IsActive == True)
    ).scalars().first()
    if not user_role:
        raise HTTPException(
            status_code=503,
            detail="Account roles are not initialized. Ask an administrator to apply the user-role setup migration.",
        )

    existing = db.execute(
        select(AppUser).where(AppUser.Email == body.email.strip().lower())
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = AppUser(

        UserID=uuid.uuid4(),

        Email=body.email.strip().lower(),

        PasswordHash=hash_password(body.password),

        DisplayName=
        f"{body.first_name} {body.last_name}",

        Department=body.department,

        IsActive=True,

        RoleID=user_role.RoleID
    )

    db.add(user)

    db.commit()

    return {
        "message":"User registered successfully"
    }