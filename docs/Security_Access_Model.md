# Security And Access Model

**Status:** Baseline access controls implemented; not production-certified. Current schema does not provide complete company membership/tenant ownership for all records.

## Public And Private Surfaces

| Surface | Anonymous | USER | MANAGER | ADMIN | OWNER / SUPER_ADMIN |
| --- | --- | --- | --- | --- | --- |
| `/`, `/login`, `/register` | Public | Public | Public | Public | Public |
| `/health`, `/ready` | Liveness/readiness only | Same | Same | Same | Same |
| Allowlisted static CSS/JS/image/font files | Public | Public | Public | Public | Public |
| Private HTML under `/static/*.html` | Denied | Session required except role-restricted pages | Session required except role-restricted pages | Session; Workforce Center allowed | Session; Owner pages require OWNER / SUPER_ADMIN |
| `/dashboard`, `/profile`, `/requests` | Denied | Own data | Team-scoped requests | Company view | Company view |
| Requirement APIs and tracker | Denied | Own requests | Own + assigned direct reports | All current records | All current records |
| Dashboard API | Denied | Own counts | Team counts | Company counts | Company counts |
| Project registry | Denied | Denied | Denied | Denied until tenant scope exists | OWNER / SUPER_ADMIN only |
| Approval read endpoints | Denied | Scoped assigned/own requests | Scoped assigned/own/direct reports | Company read access | Company read access |
| Agent registry | Denied | Denied | Denied | Denied pending tenant scope | Allowed |
| Approval decisions | Denied | No implicit authority | No implicit authority | No implicit Owner authority | Governed decision authority |
| `/docs`, `/redoc`, `/openapi.json` | Disabled | Disabled | Disabled | Disabled | Disabled |

## Implemented Controls

- Session cookie is HttpOnly, SameSite=Strict, path-scoped, and expires with the signed session.
- JWTs require a configured `JWT_SECRET_KEY` of at least 32 characters and validate issuer, audience, expiry, subject, active account, and current database role.
- Login no longer returns the bearer token to browser JavaScript. Dashboard/profile use the cookie-backed `/auth/me` endpoint.
- New passwords use PBKDF2. Existing plaintext passwords are upgraded after a successful login; rotate legacy credentials and complete migration before production.
- Requirement reads/updates/assessments are authenticated and scoped to the creator for normal users. Server-side identity overrides the submitted requester/editor values.
- `MANAGER` visibility uses the explicit `AppUser.ManagerUserID` direct-report relationship. A manager sees their own and assigned direct reports' requests, not peer or other-team requests.
- `ADMIN` can see all requirement records and company request counts. Visibility alone does not grant critical approval authority.
- Project registry is Owner/Super Admin-only until tenant scoping and cross-tenant denial tests exist. Approval reads allow company administrators and governance roles subject to the service's requester/assignee filtering for other users. Approval decisions require the assigned approver or OWNER/SUPER_ADMIN; ADMIN read access does not grant decision authority. Decision updates serialize on the requirement record to prevent concurrent duplicate continuation.
- Static serving rejects paths outside `app/static` and only serves allowlisted media/code asset extensions; private HTML requires a valid session, and Workforce/Owner command pages also enforce page-specific roles on direct static URLs.
- Mutating requests with a mismatched `Origin` are rejected. API docs are not publicly mounted.

## Important Limits

1. Anything delivered to a browser, including HTML, CSS, and JavaScript, can be inspected by that browser. It is impossible to both send client code and make it secret. Do not put server code, credentials, keys, or private project data in frontend files.
2. Existing project/approval records do not have a complete tenant ownership model. Project and agent registry data remain Owner/Super Admin-only. Request-level approval status is visible through scoped requirement tracking; decision authority remains role/policy controlled. Do not broaden any project data access until tenant filters and cross-tenant denial tests are complete.
3. Existing records written before this change may have human-readable names in `CreatedBy`; normal-user access is intentionally unavailable for those rows unless migrated to stable user IDs.
4. Role assignments and Owner bootstrap still require a controlled administrative process; do not allow registration to select or assign privileged roles.
5. Add production-grade CSRF tokens, MFA/step-up, rate limiting, login abuse detection, lockout policy, managed secret storage, HTTPS-only cookies, security monitoring, backup/retention, and independent penetration testing before production.

## Required Verification

- Anonymous requests to private pages, requirements, assessments, projects, approvals, agents, and dashboard APIs must return 401/403 without data.
- A USER must not enumerate another user's requirement ID or assessment.
- A USER must not read project, approval, agent-registry, or company-wide aggregate details.
- A MANAGER must not enumerate requests outside their own account and explicitly assigned direct reports.
- ADMIN company-wide request visibility must not imply permission to decide Owner-reserved critical approvals.
- A disabled account, expired token, wrong issuer/audience, malformed token, or changed signing key must fail closed.
- Static path traversal and requests for `.py`, `.env`, `.md`, `.txt`, and other non-allowlisted files must return 404.
- Cross-origin mutations must be rejected. Verify cookie flags over HTTPS in the deployed reverse-proxy configuration.

The marketing site may explain product capabilities but must not display real client names, project names, requirements, approvals, live metrics, internal policies, or architecture details. Use synthetic examples, visibly marked as illustrative.
