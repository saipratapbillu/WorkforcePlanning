import uuid
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models.entities import AppUser

from app.security.jwt import create_access_token
from app.security.passwords import hash_password, verify_password
from app.security.dependencies import get_current_user
from app.security.roles import canonical_role
from app.schemas.schemas import LoginRequest, PasswordResetRequest

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


def _audit_auth_event(db: Session, actor_id: str, action: str) -> None:
    db.execute(text("""
        INSERT dbo.AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
        VALUES(:correlation,'User',:actor,:action,'AppUser',:resource,'Success','{}')
    """), {
        "correlation": uuid.uuid4(),
        "actor": actor_id,
        "action": action,
        "resource": actor_id,
    })


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

    _audit_auth_event(db, str(user.UserID), "LoginSucceeded")
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
        "user_id": user["sub"],
        "display_name": user["name"],
        "email": user["email"],
        "department": user["department"],
        "role": user["role"],
    }


@router.post("/password-reset")
def reset_own_password(
    body: PasswordResetRequest,
    response: Response,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if body.current_password == body.new_password:
        raise HTTPException(status_code=422, detail="Choose a password different from the current password")
    account = db.get(AppUser, uuid.UUID(user["sub"]))
    if not account or not verify_password(body.current_password, account.PasswordHash)[0]:
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    account.PasswordHash = hash_password(body.new_password)
    _audit_auth_event(db, str(account.UserID), "PasswordChanged")
    db.commit()
    response.delete_cookie("ai_workforce_session", path="/", httponly=True, samesite="strict")
    return {"password_reset": True, "message": "Password updated. Sign in again to continue."}


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("ai_workforce_session")
    if token:
        try:
            user = get_current_user(request, SimpleNamespace(credentials=token), db)
            _audit_auth_event(db, user["sub"], "LogoutSucceeded")
            db.commit()
        except HTTPException:
            db.rollback()
        except SQLAlchemyError:
            db.rollback()
    response = Response(status_code=204)
    response.delete_cookie("ai_workforce_session", path="/", httponly=True, samesite="strict")
    return response