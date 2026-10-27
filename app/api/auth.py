from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import AppUser

from app.security.jwt import create_access_token
from app.security.passwords import hash_password, verify_password
from app.security.dependencies import get_current_user
from app.security.roles import canonical_role
from app.schemas.schemas import LoginRequest

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):

    user = db.execute(
        select(AppUser)
        .where(AppUser.Email == body.email.strip().lower())
    ).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    valid, needs_rehash = verify_password(body.password, user.PasswordHash)
    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"


        )

    if not user.Role or not user.Role.IsActive:
        raise HTTPException(
            status_code=403,
            detail="This account has no active role. Ask an administrator to apply the user-role setup migration.",
        )

    if needs_rehash:
        user.PasswordHash = hash_password(body.password)
        db.commit()

    role_code = canonical_role(user.Role.RoleCode)

    token = create_access_token({

        "sub": str(user.UserID),

        "email": user.Email,

        "name": user.DisplayName,

        "department": user.Department,

        "role": role_code

    })

    response.set_cookie(
        key="ai_workforce_session",
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=8 * 60 * 60,
        path="/",
    )

    return {
        "display_name": user.DisplayName,

        "email": user.Email,

        "department": user.Department,

        "role": role_code
    }


@router.get("/me")
def current_profile(user=Depends(get_current_user)):
    return {
        "display_name": user["name"],
        "email": user["email"],
        "department": user["department"],
        "role": user["role"],
    }


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie("ai_workforce_session", path="/", httponly=True, samesite="strict")
    return response