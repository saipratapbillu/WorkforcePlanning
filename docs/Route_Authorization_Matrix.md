# Route Authorization Matrix

This matrix covers every registered FastAPI `APIRoute` in `app.main:app`. The
regression tests derive and check the route inventory from the running app;
the access classes below reflect both middleware checks and route dependencies.

**Scope limitation:** this is an HTTP authorization matrix, not a SQL Server RLS
verification. Reviewer and worker database row isolation remains unimplemented
or unverified; see [Runtime_Execution_Evidence.md](./Runtime_Execution_Evidence.md).
Do not infer database isolation from a route being denied or allowed here.

| Route class | Anonymous | BUSINESS_USER | WORKFORCE_MANAGER | PLATFORM_OWNER | RUNTIME_REVIEWER | RUNTIME_REAPER | Agent worker credential |
|---|---:|---:|---:|---:|---:|---:|---:|
| Public pages and login (`/`, `/login`, `/register`, `/auth/login`, `/health`) | Allow | Allow | Allow | Allow | Allow | Public routes only | Deny |
| General authenticated user APIs/pages (including `/auth/me`, `/auth/logout`, profile, requirements, projects, tasks, approvals, notifications, self-dashboard) | Deny | Allow | Allow | Allow | Deny, except `/auth/me` and logout | Deny, except logout | Deny |
| Workforce management APIs/pages and agent directory | Deny | Deny | Allow | Allow | Deny | Deny | Deny |
| Execution planning APIs/pages | Deny | Deny | Allow | Allow | Deny | Deny | Deny |
| Executive dashboards | Deny | Deny | Deny | Allow | Deny | Deny | Deny |
| User administration and organization mapping | Deny | Deny | Deny | Allow | Deny | Deny | Deny |
| Runtime monitoring, defects, escalations, enqueue, credentials and reaping | Deny | Deny | Read-only monitor/defect/escalation access | Allow (owner-only mutations) | Deny | Deny | Deny |
| Independent runtime review (`/runtime/reviews/claim`, review-package GET, decision POST) | Deny | Deny | Deny | Deny | Allow for assigned lease only | Deny | Deny |
| Worker runtime (`/runtime/worker/*`) | Deny | Deny | Deny | Deny | Deny | Deny | Allow only with active agent credential and a matching lease |
| Static HTML pages | Deny except public pages | Only role-mapped pages | Only role-mapped pages | Only role-mapped pages | Deny | Deny | Deny |
| Public CSS, JavaScript, images, fonts | Allow | Allow | Allow | Allow | Allow | Allow | Allow |

Notes:

- The reviewer middleware allowlist is intentionally limited to review APIs,
  `/auth/me`, and logout. Review-package reads additionally require the current
  unexpired review lease owner.
- The `RUNTIME_REAPER` identity is blocked from all HTTP application routes and
  is used only by the standalone scheduled process, apart from the harmless
  authenticated logout endpoint.
- Worker paths bypass web-session authentication only; every registered worker
  endpoint must depend on `_worker_agent`, which validates the active credential.
- Role checks use canonical role aliases. `RUNTIME_REVIEWER` is not an alias of
  an administrative, manager, executive, or business role.
- `/ready` and health/login/static assets remain intentionally public; no
  business data is returned by those endpoints.
