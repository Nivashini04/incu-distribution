# IncuBrix Distribution: Long-Tail Destination Network

A Python API for managing content distribution jobs across configured destinations.

## Features

- FastAPI REST API
- Asynchronous publishing jobs
- Destination-specific publishing policies
- Idempotency and conflict handling
- Mock, Discourse, Lemmy, Ghost, webhook, and assisted connectors
- SQLite persistence
- Docker support
- Automated tests using pytest

## Requirements

- Python 3.12
- Docker Desktop with Docker Compose (optional)

## Setup

Create and activate a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run the API

```powershell
uvicorn main:app --reload
```

## Docker

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d
```

Configure any required connector credentials in `.env`. Never commit secrets.

## API Documentation

- Swagger UI: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Readiness: http://localhost:8000/ready

## Example Publishing Request

```powershell
$body = @{
    destination = "open-community"
    content = "Sample test post"
    idempotency_key = "readme-example-001"
    is_self_promotional = $false
    is_ai_generated = $false
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/jobs" -Method Post -ContentType "application/json" -Body $body

$response | ConvertTo-Json -Depth 10
```

**Important:** `open-community` currently uses a mock connector. A successful result is simulated, not a real external publication.

## Run Tests

```powershell
python -m pytest -q
```

## Additional Documentation

- AI-use notes: `AI_USE.md`
- License: `LICENSE`