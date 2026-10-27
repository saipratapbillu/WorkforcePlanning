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
