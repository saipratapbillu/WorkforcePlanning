<<<<<<< HEAD
# AI Company Phase 2 with User-Friendly UI

Start with **[STEP_BY_STEP_GUIDE.md](STEP_BY_STEP_GUIDE.md)** for the complete installation, administration and business-user process.

## Quick start

1. Run `sql/03_phase2_assessment.sql` against the existing `AICompany` database.
2. Copy `.env.example` to `.env`.
3. Generate a random signing key with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and set it as `JWT_SECRET_KEY` in `.env`. Do not commit or share the value.
4. Create and activate `.venv`.
5. Run `pip install -r requirements.txt`.
6. Run `run_local.bat`.
7. Open `http://127.0.0.1:8000/`.

The public website contains only marketing information and synthetic UI artwork. Workspace pages and business-data APIs require an authenticated session. Browser-delivered frontend code is always inspectable; secrets and private data must stay server-side. See [STEP_BY_STEP_GUIDE.md](STEP_BY_STEP_GUIDE.md) for current access controls and production security gaps.
=======
# AI Company Local MVP

Implementation-ready control-plane starter for a governed AI Company. It uses SQL Server on `localhost` and a FastAPI API.

## Prerequisites
- Windows with local SQL Server / SQL Server Developer Edition
- SQL Server Management Studio
- Python 3.11+
- Microsoft ODBC Driver 18 for SQL Server

## 1. Create database
Open SSMS against `localhost` with Windows authentication and run:
1. `sql/01_create_database.sql`
2. `sql/02_seed.sql`

## 2. Configure
Copy `.env.example` to `.env`. Defaults already use `localhost`, database `AICompany`, Windows integrated authentication, and local non-encrypted SQL connectivity.

## 3. Run API
From the project directory on Windows:
`run_local.bat`

Then open:
- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## MVP endpoints
- `POST /requirements`: creates and classifies a requirement
- `POST /projects`: creates a project
- `POST /tasks`: creates a controlled task
- `GET /agents`: lists registered AI employees

## Example requirement
POST `/requirements`
```json
{
  "title": "Supplier Compliance Platform",
  "description": "Build a supplier compliance system using SharePoint, SQL Server and Power BI",
  "requested_by": "HumanOwner",
  "priority": "High"
}
```

## Important
This is a local MVP/control-plane foundation, not production. Agent execution/model-provider calls are intentionally left unconfigured. Production requires Entra workload identities, secret management, API/MCP policy enforcement, approval services, message bus, immutable audit/evidence storage, evaluation gates, and environment separation.
>>>>>>> 3e08d0de30e4b712c5b3c8c50b4f61e4d04df639
