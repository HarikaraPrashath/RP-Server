RP-Server (FastAPI)

Run locally:

1) Create a virtual environment and install deps.
   pip install -r requirements.txt

2) Start the API server.
   uvicorn app:app --reload --host 0.0.0.0 --port 8000

Environment:
- NEXT_PUBLIC_API_URL in RP-Client should point to this server, e.g. http://localhost:8000
- TOPJOBS_KEYWORD can override the scraping keyword (or pass keyword to /jobs/refresh)

Endpoints (summary):
- POST /parse (multipart form file) -> CV parse result
- GET /cv -> latest CV metadata
- GET /cv/file?id=... -> stream CV file
- GET/PUT /profile -> profile storage
- POST /auth/signup -> create account (local storage)
- POST /auth/login -> sign in (local storage)
- POST /auth/forgot-password -> placeholder reset flow
- GET /jobs -> job metadata + snippets
- GET /jobs/file?name=... -> job asset
- POST /jobs/refresh -> run scraper + ranking
- GET /ranked -> ranked job list
- GET /ranked/summary -> best + top matches
- POST /analyse -> run job analysis pipeline (keyword in JSON body)
