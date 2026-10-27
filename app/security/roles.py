ROLE_ALIASES = {
    "USER": "BUSINESS_USER",
    "MANAGER": "WORKFORCE_MANAGER",
    "DEPARTMENT_HEAD": "WORKFORCE_MANAGER",
    "ADMIN": "WORKFORCE_MANAGER",
    "OWNER": "PLATFORM_OWNER",
    "SUPER_ADMIN": "PLATFORM_OWNER",
}

CANONICAL_ROLES = {
    "BUSINESS_USER",
    "APPROVER",
    "EXECUTIVE",
    "WORKFORCE_MANAGER",
    "PLATFORM_OWNER",
}


def canonical_role(role: str | None) -> str:
    normalized = str(role or "").strip().upper()
    return ROLE_ALIASES.get(normalized, normalized)


def has_role(role: str | None, *allowed_roles: str) -> bool:
    effective_role = canonical_role(role)
    return effective_role in {canonical_role(allowed) for allowed in allowed_roles}
