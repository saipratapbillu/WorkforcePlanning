# Security And Platform Roadmap

**Status date:** 2026-10-23  
**Scope:** Extends the current FastAPI, SQL Server, static UI, approval/workforce controls, and Phase 3 runtime. It does not replace the existing governance model or authorize autonomous execution.  
**Current release status:** Not production ready. Priority 1 has application-level dashboard scoping and navigation/error handling, but database-enforced RLS and tenant-complete schemas are not implemented.

## Incident Finding: Business User Dashboard

### Root cause

Three conditions appeared during the investigation and must not be conflated:

1. Database inspection showed `normal@normal.com` was active, but its `RoleID` pointed to a nonexistent role row (`00000000-0000-0000-0000-000000000001`). The actual browser `POST /auth/login` response was **403** with `{"detail":"This account has no active role. Ask an administrator to apply the user-role setup migration."}`. Authorization correctly denied the orphan role mapping. The account was assigned to the existing active `USER` role; no authentication check was weakened.
2. After role repair, the browser reached the dashboard. The client requested `GET /dashboard/api/me`; the active port-8033 server was an old system-Python Uvicorn process without that route, and returned **404** with `{"detail":"Not Found"}`. The frontend showed a generic unavailable state. Separately, the stale port-8040 browser tab had been stopped and showed `net::ERR_CONNECTION_REFUSED`; that is a transport failure, not an API authorization response.
3. The old dashboard endpoint `/dashboard/api` returned 200 but only four counts and hard-coded project/approval values to zero for non-company roles. It did not deliver the requested personal record collections.

After restarting the verified workspace server from `.venv`, the actual browser trace was:

| Request | Response | Authorization and data scope |
| --- | --- | --- |
| `GET /auth/me` | 200; role `USER` | Signed cookie validated; active account and current active role loaded from SQL. |
| `GET /dashboard/api/me` after restarting updated workspace server | 200; personal collections and counts | Authenticated; requirement owner ID is the current user ID; projects/tasks join through owned requirement; notifications filter `UserID`; approvals filter assigned user or owned requirement. |

The account currently owns zero Requirements, Projects, Tasks, Notifications, and Approvals, so the dashboard correctly shows empty states. `GET /dashboard/api/me` returned these exact keys: `my_requirements`, `my_projects`, `my_tasks`, `my_notifications`, `my_approvals`, `my_assessments`, and aggregate counts.

When a test-only browser route returned 403, the dashboard displayed exactly **“You do not have access to this feature.”** No “Failed to fetch” text was displayed. A connection-level failure is separately shown as a connection message, not mislabeled as an authorization failure.

### Authorization and RLS decision

- Authentication uses the current AppUser and Role rows, not stale role claims from the JWT.
- Dashboard endpoint authorization requires a valid session. The `me` endpoint is ownership-filtered and does not accept caller-supplied owner IDs.
- Requirements use the existing `CreatedBy` string column, written with the authenticated user UUID. The schema does **not** have `CreatedByUserID`.
- Projects and Tasks do **not** have a complete user/tenant RLS key in the current schema. The personal API scopes them by joining through a Requirement whose `CreatedBy` equals the current user. This is application-level row filtering, not database RLS.
- Notifications use `Notification.UserID = current user ID`.
- Approvals use assigned user OR a Requirement owned by current user. The ability to decide remains separately enforced by ApprovalService.
- SQL Server currently has no row-level security policies. Do not claim database RLS is complete. Do not add a permissive `SESSION_CONTEXT IS NULL => allow` policy; that would create a bypass.

### Frontend behavior

`dashboard.js` uses `/dashboard/api/me` for `USER`. A 401 or 403 is mapped to “You do not have access to this feature.” Protected workforce, project-registry, and Owner-command links are hidden based on the authenticated role, with server-side authorization remaining authoritative. The business user gets a “My projects” anchor to owned records, not the company project registry.

## Priority 1: Complete RLS

### Gap analysis

Current API guards exist for requirements, notifications, and approvals, and the new personal dashboard joins projects/tasks through owned requirements. SQL Server RLS is absent. Project, task, approval, comment, and attachment ownership is not represented consistently; `CreatedBy` is a string rather than a foreign key. Application roles currently seeded are `USER`, `MANAGER`, and `SUPER_ADMIN`; department-head, executive, Owner, and Admin account roles are not all present. The requested matrix therefore cannot yet be certified.

### Database changes

- Add `TenantID`/`CompanyID` and stable `CreatedByUserID` to Requirement, Project, Task, Comment, Attachment, and any other user-owned record; keep existing `CreatedBy` only as a backward-compatible audit/display field during migration.
- Add explicit tenant/user keys to Approval where needed; preserve `AssignedToUserID` as a separate decision authority.
- Add indexes for `(TenantID, CreatedByUserID, CreatedAtUtc)`, `(RequirementID, ...)`, `(ProjectID, ...)`, and `(UserID, CreatedAtUtc)` according to actual query plans.
- Backfill only from verified identity mappings. Quarantine ambiguous legacy names rather than assigning them to a guessed user.
- Add SQL Server inline predicate functions and filter/block security policies only after all app and worker connections set a verified session context and pooled connections clear it. Include explicit system/worker principal policy; null context must fail closed.

### API changes

- Keep `GET /dashboard/api/me` bound to authenticated identity only.
- Introduce shared tenant-scoped repository predicates for requirements/projects/tasks/comments/attachments/approvals.
- Apply identical predicates to list, detail, update, delete, search, export, relationship expansion, and counts to prevent IDOR and aggregate leakage.
- Keep approval assignment/decision authority separate from record visibility; no visibility role can approve unless existing approval policy grants it.

### UI changes

- Use role-aware navigation only for discoverability. Keep all restrictions server-enforced.
- Show “My projects” and “My tasks” separately from Owner/company dashboards.
- Render 401/403 with the required access message; render network failures as service connectivity errors.

### Security controls

- Tenant context established from verified active session, never request data.
- Fail-closed authorization, object-level checks, immutable audit for denied sensitive actions, safe pagination, and no cross-tenant response counts.
- Review all background jobs, runtime agents, migrations, and admin flows for explicit principal/context behavior.

### Testing plan

- Cross-user and cross-tenant allow/deny matrix for every supported role and every CRUD/aggregate route.
- SQL RLS tests using actual connection pools, including missing context, stale context, context reset after checkout/return, and pooled-connection reuse.
- IDOR tests using known foreign UUIDs; assert no data or count leakage.

### Deployment plan and rollout order

1. Approve role/tenant policy and migration mappings.
2. Deploy nullable ownership columns, populate/backfill, and audit unresolved records.
3. Deploy dual-read/dual-write repository predicates and tests.
4. Set verified SQL session context and verify clearing under exceptions/pool reuse.
5. Enable filter/block policies in shadow/verification environment, then production after negative tests pass.
6. Make ownership keys non-null only after legacy quarantine is signed off.

## Priority 2: Authentication Completion

### Gap analysis

Login and cookie-backed JWT validation exist. Logout only deletes a browser cookie; no revocation/refresh/device registry or password reset/change workflow exists. There is no token blacklist or forced logout control. The orphaned RoleID incident also shows referential integrity for role assignment needs verification.

### Database changes

- Add server-side `AuthSession`/refresh-token records with session ID, token hash, user, device metadata, created/expiry/revoked/last-used times, and rotation family.
- Add one-time password reset/change challenge hashes and expiry/consumed state; never store raw secrets.
- Add appropriate foreign keys/indexes and role mapping integrity checks.

### API changes

- Add forgot-password request with non-enumerating response; single-use reset token; authenticated change-password with current-password/step-up check.
- Add refresh-token rotation with reuse detection; logout current session; logout all sessions; list/revoke devices.
- Preserve current role reload and issuer/audience/expiry validation; reject inactive/missing roles.

### UI changes

- Add forgot/reset/change password screens, active session/device management, and explicit sign-out-all.
- Map 401/403 to the specified access message on feature requests; login uses a generic credential message for 401 to avoid account-enumeration disclosure, while 403 authorization failures use the required feature-access copy.

### Security controls

- Rate limits, lockout/abuse detection, single-use hashed recovery tokens, HttpOnly/SameSite cookies, CSRF protection for cookie-auth mutations, HTTPS-only production cookies, MFA/step-up for sensitive actions, secret rotation, and redacted logs.

### Testing plan

- Expired/wrong issuer/audience/signature, inactive user/role, reset replay/expiry, refresh rotation/reuse, logout replay denial, CSRF, rate-limit, and device revoke tests.

### Deployment plan and rollout order

1. Create session/recovery schema and audit policy.
2. Deploy compatible session validation and cookie migration.
3. Enable refresh/revocation before reducing access-token lifetime.
4. Roll out password recovery with delivery provider and abuse controls.
5. Revoke legacy sessions at a scheduled cutover and monitor failed auth.

## Priority 3: Defect Management System

### Gap analysis

`Issue` is project-bound and has limited fields. `AgentRuntimeDefect` only handles rejected runtime outputs. There is no general defect assignment, developer/QA/retest queue, gate evidence, or closure workflow; audit defects in reports are not operational records.

### Database changes

- Add tenant-scoped `Defect`, `DefectAssignment`, `DefectTransition`, `DefectEvidence`, `DefectRetest`, and `DefectGateApproval` tables.
- Store full requested RCA: problem, symptoms, technical/business cause, affected areas, solution, risk, expected/actual results, reproduction steps, fix evidence, and regression runs.
- Enforce valid lifecycle values and immutable transition/evidence history; support source links to requirement/project/task/runtime execution/test run.

### API changes

- Add authorized create/list/detail/assign/transition/retest/evidence/gate endpoints.
- Deterministic rules route authentication/security to Security+Identity, database to Database, API to Backend, UI to Frontend, performance to Performance Engineering, workflow to Workflow, agent to AI Agent Engineering, approvals to Governance, with QA as verifier.
- Block `Closed` unless required gates and passing retest evidence exist; Critical/Security/Architecture items require Super Admin approval.

### UI changes

- Add developer, QA, retest, and governance queues with filters, histories, evidence, owner/team assignment, blockers, and due dates.

### Security controls

- Tenant isolation, least-privilege transitions, separation of developer and QA identities, immutable append-only evidence, and audited closure.

### Testing plan

- Lifecycle state-machine tests, unauthorized transition tests, assignment routing tests, premature-close rejection, reopen/failed-retest loops, and tenant leakage tests.

### Deployment plan and rollout order

1. Migrate defect schema and import existing runtime defects without closing them.
2. Deploy APIs and team routing with all defects defaulting Open.
3. Add UI queues and notifications.
4. Require review gates for closure only after reviewer identities are provisioned.

## Priority 4: Agent Execution Worker Framework

### Gap analysis

Phase 3 persistence and pull APIs, leases, retries, escalation, and manual independent QA exist. No background AgentWorker service or trusted executor exists; no code delivery should be claimed.

### Database changes

- Existing AgentTaskQueue/Execution/Output/Event/Escalation/Defect/Credential tables are the base. Add worker registration/heartbeat, worker type/capabilities, adapter version, idempotency key, and attempt-level artifact manifest only as a reviewed migration.

### API changes

- Keep worker identity derived from per-agent credential. Add authenticated worker registration/poll/claim/heartbeat/acknowledgment and shutdown/drain health endpoints; preserve approval/security/dependency gates before claim.
- Workers must not execute code unless a trusted adapter and sandbox policy are configured.

### UI changes

- Add Owner monitoring for worker health, lease age, queue depth, adapter versions, attempt history, and kill-switch state.

### Security controls

- Per-agent credentials, secret rotation, allowlisted worker capabilities, no user-supplied AgentID, quotas, network policy, least privilege, and revocable worker identity.

### Testing plan

- Atomic concurrent claims, lease expiry, heartbeat rejection, exactly-once output acceptance, retry exhaustion, replay, credential revoke, and fault-injection tests.

### Deployment plan and rollout order

1. Deploy worker service disabled with no credentials.
2. Validate health, queue claims, and cancellation on synthetic non-production tasks.
3. Pilot one low-risk read-only worker type.
4. Expand only after independent Security/QA/Owner approvals and operational rollback.

## Priority 5: Execution Sandbox

### Gap analysis

No isolated code execution sandbox exists. A normal worker process is not an acceptable substitute.

### Database changes

- Store sandbox policy/version, resource budget, image digest, run identity, artifact hashes, and cleanup status alongside execution records; never store runtime secrets in output records.

### API changes

- Add a brokered sandbox launch interface that accepts approved task artifacts and capability policy, not arbitrary host paths or unrestricted commands.
- Support Python, SQL, documentation, and tests as separately allowlisted execution profiles.

### UI changes

- Show run profile, resource limits, test evidence, artifact hashes, sandbox image/version, and teardown status to authorized reviewers.

### Security controls

- Ephemeral isolated containers/VMs, non-root, read-only base image, bounded CPU/memory/disk/time, egress deny-by-default, secret broker, syscall restrictions, artifact scanning, and guaranteed teardown.

### Testing plan

- Escape/egress/resource abuse tests by an authorized security team, malicious dependency fixtures, timeout/kill, artifact validation, and tenant-crossing tests.

### Deployment plan and rollout order

1. Threat model and select a maintained isolation technology.
2. Build pinned signed images and policy-as-code.
3. Validate in isolated test subscription/host.
4. Enable non-production profiles; require Security and Architecture gate approval before production.

## Priority 6: QA Automation

### Gap analysis

The repository currently has focused standard-library unit tests. There is no automated end-to-end integration/regression/security matrix or defect auto-creation linkage. Runtime structural QA is explicitly not content QA.

### Database changes

- Add test-run, test-case/result, build/commit, environment, artifact, and defect-link records if durable evidence is required; keep test artifacts immutable and retention-governed.

### API changes

- Add CI ingestion for signed test reports and deterministic defect deduplication; never auto-close without approved retest gates.

### UI changes

- Show test health, failed cases, linked defects, test-run provenance, and regression history in QA queues.

### Security controls

- Protect test artifacts, mask secrets/PII, verify report signatures, scope test data, and separate test-run identities from production.

### Testing plan

- Unit, SQL integration, API integration, browser regression, role/RLS negative tests, security scans, load tests, and accessibility checks.

### Deployment plan and rollout order

1. Establish isolated test database and deterministic fixtures.
2. Add CI gates for unit/compile/schema checks.
3. Add integration/browser/security suites.
4. Add defect ingestion after result provenance and deduplication rules are approved.

## Priority 7: DevSecOps

### Gap analysis

No checked-in CI/CD pipeline, code scanning, secret scanning, dependency scanning, signing, or release gate was found in the workspace. Production security baseline is incomplete.

### Database changes

- Add deployment/release evidence only if required by audit; use CI artifact storage for scanner reports where possible.

### API changes

- Avoid runtime scanner APIs unless they are needed for an approved release evidence contract.

### UI changes

- Owner release view may show signed build provenance, required gates, approvals, and scan outcomes; do not display secrets or raw scanner dumps broadly.

### Security controls

- Secret scanning and rotation, SAST, dependency/license scanning, image scanning, SBOM, signed build artifacts, protected branches, environment separation, least-privilege deployment identity, and rollback.

### Testing plan

- CI positive/negative policy tests, seeded vulnerable fixture validation, secret-canary detection, dependency lock reproducibility, and deployment authorization tests.

### Deployment plan and rollout order

1. Add CI workflow for compile/unit tests and secret scan.
2. Add SAST/dependency/SBOM/image scan and severity gates.
3. Require protected review and signed artifacts.
4. Add staged deployment with manual Owner/security approvals and rollback evidence.

## Priority 8: Executive Command Center

### Gap analysis

An Owner command-center static preview exists but is not a governed integrated executive dashboard. Current dashboard API has only basic counts. Defect, risk, SLA, security incident, and agent operational aggregates are not joined into a unified owner view.

### Database changes

- Reuse governed source tables; add SLA/metric snapshots only where query cost or historical trend requirements justify them. All entities need tenant scope first.

### API changes

- Add Owner/Super Admin-only aggregate endpoints for requirements, projects, agents, tasks, defects, approvals, risks, incidents, and SLA breaches, with explicit time windows and tenant predicates.

### UI changes

- Replace preview with a real Owner dashboard showing freshness, counts/trends, blockers, aging, risks, security incidents, unresolved gates, and actionable drill-through links.

### Security controls

- Enforce Owner/Super Admin role on page and APIs, tenant isolation, aggregate disclosure policy, audit access, and avoid exposing detailed user data in aggregate cards.

### Testing plan

- Role-denial and direct URL tests, aggregate reconciliation against source tables, tenant isolation, stale-data indicators, query plan/load tests, and accessibility/browser checks.

### Deployment plan and rollout order

1. Complete ownership/RLS foundations and defect/security records.
2. Define metric formulas and governance owners.
3. Ship read-only aggregate API and reconcile results.
4. Replace preview UI, add role/tenant tests, then enable for Owner/Super Admin.

## Ordered Rollout

1. Repair and audit user-role mappings; ship current dashboard/API-level ownership filters and role error UX.
2. Establish tenant and stable ownership schema, backfill, and database/API RLS tests.
3. Complete revocable authentication/session lifecycle.
4. Deliver defect lifecycle and independent QA/security closure gates.
5. Establish CI/DevSecOps and isolated test environments.
6. Threat-model and deploy sandbox before enabling any code-execution worker.
7. Pilot pull workers with existing activation, approval, task, security, and QA gates preserved.
8. Build the Executive Command Center on reconciled, tenant-scoped data.

At every step, a task/defect stays open when evidence is missing. Production readiness requires zero Critical issues, no High-risk security findings, passing cross-tenant tests, verified authentication/session controls, complete approvals/workflows, no unassigned defects, and recorded independent sign-off.