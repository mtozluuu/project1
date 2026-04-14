import os
import warnings

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Flight, User
from app.routers import auth, admin, flights, reports

load_dotenv()

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "")
if not SESSION_SECRET_KEY:
    warnings.warn(
        "SESSION_SECRET_KEY is not set. Using an insecure default. "
        "Set SESSION_SECRET_KEY in your environment before deploying.",
        stacklevel=1,
    )
    SESSION_SECRET_KEY = "insecure-dev-key-do-not-use-in-production"

app = FastAPI(title="Flight Management API", version="1.0.0")

# ── Static files & templates ──────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

_ui_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)


@app.middleware("http")
async def attach_user_to_request(request: Request, call_next):
    """Load the authenticated user from the session and attach to request.state."""
    
    session = request.scope.get("session")
    user_id = session.get("user_id") if session else None
    if user_id is not None:
        db: Session = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            request.state.user = user
        finally:
            db.close()
    else:
        request.state.user = None
    return await call_next(request)


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(flights.router)
app.include_router(reports.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", tags=["root"])
def root():
    return {"status": "ok"}


# ── HTML UI routes ─────────────────────────────────────────────────────────────

@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def ui_index(request: Request):
    user = getattr(request.state, "user", None)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def ui_login_get(request: Request):
    user = getattr(request.state, "user", None)
    return templates.TemplateResponse("login.html", {"request": request, "user": user})


@app.post("/login", response_class=HTMLResponse, include_in_schema=False)
def ui_login_post(
    request: Request,
    user_id: int = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    found_user: User | None = db.query(User).filter(User.id == user_id).first()
    if found_user is None or not _ui_pwd_context.verify(password, found_user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "user": None, "error": "Invalid user ID or password."},
            status_code=401,
        )
    request.session["user_id"] = found_user.id
    return RedirectResponse(url="/ui/flights", status_code=303)


@app.get("/ui/flights", response_class=HTMLResponse, include_in_schema=False)
def ui_flights(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    flight_rows = []
    if user is not None:
        flight_rows = db.query(Flight).order_by(Flight.sched_dep).all()
    return templates.TemplateResponse(
        "flights.html", {"request": request, "user": user, "flights": flight_rows}
    )
