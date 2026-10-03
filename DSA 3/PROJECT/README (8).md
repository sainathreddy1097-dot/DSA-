# Contract & Compliance backend

Local FastAPI, SQLAlchemy 2, Pydantic v2, and SQLite backend. It has no authentication, cloud service, LLM call, external API, export endpoint, or document generator. The contract-summary JSON download is a browser-only frontend responsibility.

## Python 3.14.4 compatibility preflight

Run from the project root in PowerShell. Do not install, switch, or downgrade Python.

```powershell
C:\Python314\python.exe --version
C:\Python314\python.exe -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import sys; assert sys.version_info[:3] == (3, 14, 4); print(sys.executable)"
Set-Location backend
..\.venv\Scripts\python.exe -m pip install --dry-run --disable-pip-version-check -r requirements.txt
..\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt
```

The resolver preflight must succeed immediately before installation. `requirements.txt` pins FastAPI 0.141.1, SQLAlchemy 2.0.54, Pydantic 2.13.5, Uvicorn 0.53.0, pytest 9.1.1, and httpx 0.28.1.

## Database commands

Commands are deterministic and use `backend/data/contracts.db` unless `DATABASE_URL` is set.

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m app.seed seed
..\.venv\Scripts\python.exe -m app.seed reset
..\.venv\Scripts\python.exe -m app.seed counts
```

`seed` initializes an empty database without overwriting it. `reset` recreates it and seeds 12 contracts, 36 versions, 276 clause-version rows (7–8 clauses per version), 10 obligations, and 6 reviewers. The corpus contains domain-specific contract families plus added, removed, and modified clauses for meaningful deterministic comparisons and clusters.

## Test and run

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -c "from app.main import app; print(app.title)"
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for the typed OpenAPI UI. Configure the frontend with `VITE_API_BASE_URL=http://127.0.0.1:8000`.

Default CORS origins are `localhost` and `127.0.0.1` on ports 5173 and 5181. Override them with a comma-separated `CORS_ORIGINS` environment variable.

All list endpoints use `{ items, page, pageSize, total, totalPages }`. Errors use `{ "error": { "code", "message", "details"? } }`. See [algorithm notes](docs/algorithms.md) for formulas, complexity, deterministic tie-breaking, and limitations.
