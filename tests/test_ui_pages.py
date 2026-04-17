"""Tests for the HTML UI pages (/, /login, /flights-ui)."""
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError

import app.main as main_module
from app.models import Flight, FlightNote

app = main_module.app


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_index_returns_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Flight Management" in response.text


def test_index_links_present(client):
    response = client.get("/")
    assert response.status_code == 200
    for href in ["/docs", "/redoc", "/login", "/flights-ui"]:
        assert href in response.text, f"Expected link to {href} on index page"


def test_login_returns_html(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<form" in response.text


def test_login_page_has_fields(client):
    response = client.get("/login")
    assert "username" in response.text
    assert "password" in response.text


def test_flights_ui_returns_html(client):
    response = client.get("/flights-ui")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Flights" in response.text


def test_flights_ui_unauthenticated_shows_placeholder(client):
    """Unauthenticated visit should show a helpful message, not an error."""
    response = client.get("/flights-ui")
    assert response.status_code == 200
    # Should show a message guiding the user to log in
    assert "Log in" in response.text or "login" in response.text.lower()


def test_health_still_returns_json(client):
    """Existing /health JSON endpoint must remain unaffected."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_static_css_served(client):
    response = client.get("/static/styles.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_flight_detail_renders_when_notes_table_missing(monkeypatch):
    flight = SimpleNamespace(
        id=6,
        flight_no="TK100",
        flight_date=date(2026, 1, 1),
        departure_airport="IST",
        arrival_airport="ADB",
        sched_dep=datetime(2026, 1, 1, 12, 0, 0),
        sched_arr=datetime(2026, 1, 1, 13, 0, 0),
    )
    sessions = []

    class _FlightQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return flight

    class _NotesQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            raise ProgrammingError("SELECT * FROM flight_notes", {}, Exception('relation "flight_notes" does not exist'))

    class _FakeSession:
        def __init__(self):
            self.rolled_back = False

        def query(self, model):
            if model is Flight:
                return _FlightQuery()
            if model is FlightNote:
                return _NotesQuery()
            raise AssertionError(f"Unexpected model queried: {model}")

        def rollback(self):
            self.rolled_back = True

        def close(self):
            return None

    def _session_factory():
        s = _FakeSession()
        sessions.append(s)
        return s

    monkeypatch.setattr(main_module, "SessionLocal", _session_factory)

    with TestClient(app, raise_server_exceptions=True) as test_client:
        response = test_client.get("/flight-detail/6")

    assert response.status_code == 200
    assert "No notes available" in response.text
    assert any(s.rolled_back for s in sessions)


def test_create_note_redirects_gracefully_when_notes_table_missing(monkeypatch):
    flight = SimpleNamespace(id=6)
    sessions = []

    class _FlightQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return flight

    class _FakeSession:
        def __init__(self):
            self.rolled_back = False

        def query(self, model):
            if model is Flight:
                return _FlightQuery()
            raise AssertionError(f"Unexpected model queried: {model}")

        def add(self, _obj):
            return None

        def commit(self):
            raise ProgrammingError("INSERT INTO flight_notes ...", {}, Exception('relation "flight_notes" does not exist'))

        def rollback(self):
            self.rolled_back = True

        def close(self):
            return None

    def _session_factory():
        s = _FakeSession()
        sessions.append(s)
        return s

    monkeypatch.setattr(main_module, "SessionLocal", _session_factory)

    with TestClient(app, raise_server_exceptions=True) as test_client:
        response = test_client.post("/flight-detail/6/notes", data={"note": "test note"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/flight-detail/6?note_status=unavailable"
    assert any(s.rolled_back for s in sessions)
