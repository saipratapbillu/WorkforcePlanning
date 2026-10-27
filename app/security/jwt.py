import os
from datetime import datetime, timedelta, timezone

from jose import jwt

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 480

if len(SECRET_KEY.encode("utf-8")) < 32 or SECRET_KEY == "REPLACE_WITH_A_RANDOM_SECRET_AT_LEAST_32_CHARACTERS":
    raise RuntimeError("JWT_SECRET_KEY must be configured with at least 32 random characters")


def create_access_token(data: dict):

    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({
        "exp": expire,
        "iss": "ai-workforce-os",
        "aud": "ai-workforce-os-web",
    })

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )
