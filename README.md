init

## Running the application

```bash
uvicorn app.main:app --reload
```

## Accessing the UI

| URL | Description |
|-----|-------------|
| `http://127.0.0.1:8000/` | JSON health check (`{"status": "ok"}`) |
| `http://127.0.0.1:8000/ui` | HTML landing page |
| `http://127.0.0.1:8000/login` | HTML login form |
| `http://127.0.0.1:8000/ui/flights` | HTML flights list (login required) |
| `http://127.0.0.1:8000/health` | API health check |
| `http://127.0.0.1:8000/docs` | Swagger UI (interactive API docs) |
| `http://127.0.0.1:8000/redoc` | ReDoc (API docs) |
