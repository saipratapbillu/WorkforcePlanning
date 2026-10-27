from fastapi import Depends
from fastapi import HTTPException

from app.security.dependencies import get_current_user
from app.security.roles import has_role


def require_roles(*roles):

    def checker(
        user=Depends(
            get_current_user
        )
    ):

        if not has_role(user.get("role"), *roles):
            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        return user

    return checker