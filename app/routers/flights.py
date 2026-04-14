from datetime import datetime, timezone, timedelta

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import CrewAssignment, Flight, MaintenanceLog, User

router = APIRouter(prefix="/flights", tags=["flights"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class CreateFlightRequest(BaseModel):
    flight_number: str
    departure_time: datetime
    arrival_time: datetime
    origin: str
    destination: str


class CrewChangeRequest(BaseModel):
    user_id: int
    seat: str


class MaintenanceLogRequest(BaseModel):
    description: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_flight_or_404(flight_id: int, db: Session) -> Flight:
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if flight is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight not found")
    return flight


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_flight(
    body: CreateFlightRequest,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    flight = Flight(
        flight_number=body.flight_number,
        departure_time=body.departure_time,
        arrival_time=body.arrival_time,
        origin=body.origin,
        destination=body.destination,
    )
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return {
        "id": flight.id,
        "flight_number": flight.flight_number,
        "departure_time": flight.departure_time,
        "arrival_time": flight.arrival_time,
        "origin": flight.origin,
        "destination": flight.destination,
    }


@router.get("")
def list_flights(
    date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Flight)
    if date is not None:
        try:
            parsed = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date must be in YYYY-MM-DD format",
            )
        next_day = parsed + timedelta(days=1)
        query = query.filter(and_(Flight.departure_time >= parsed, Flight.departure_time < next_day))
    flights = query.order_by(Flight.departure_time).all()
    return [
        {
            "id": f.id,
            "flight_number": f.flight_number,
            "departure_time": f.departure_time,
            "arrival_time": f.arrival_time,
            "origin": f.origin,
            "destination": f.destination,
        }
        for f in flights
    ]


@router.post("/{flight_id}/crew/change", status_code=status.HTTP_200_OK)
def change_crew(
    flight_id: int,
    body: CrewChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    _get_flight_or_404(flight_id, db)

    # End any active assignment for this seat on this flight
    active = (
        db.query(CrewAssignment)
        .filter(
            CrewAssignment.flight_id == flight_id,
            CrewAssignment.seat == body.seat,
            CrewAssignment.end_time.is_(None),
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    if active:
        active.end_time = now

    # Verify the target user exists
    new_user = db.query(User).filter(User.id == body.user_id).first()
    if new_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    assignment = CrewAssignment(
        flight_id=flight_id,
        user_id=body.user_id,
        seat=body.seat,
        start_time=now,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return {
        "id": assignment.id,
        "flight_id": assignment.flight_id,
        "user_id": assignment.user_id,
        "seat": assignment.seat,
        "start_time": assignment.start_time,
    }


@router.get("/{flight_id}/crew")
def get_crew(
    flight_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _get_flight_or_404(flight_id, db)
    assignments = (
        db.query(CrewAssignment)
        .filter(CrewAssignment.flight_id == flight_id)
        .order_by(CrewAssignment.start_time)
        .all()
    )
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "seat": a.seat,
            "start_time": a.start_time,
            "end_time": a.end_time,
        }
        for a in assignments
    ]


@router.get("/{flight_id}/crew/active")
def get_active_crew(
    flight_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _get_flight_or_404(flight_id, db)
    assignments = (
        db.query(CrewAssignment)
        .filter(
            CrewAssignment.flight_id == flight_id,
            CrewAssignment.end_time.is_(None),
        )
        .order_by(CrewAssignment.seat)
        .all()
    )
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "seat": a.seat,
            "start_time": a.start_time,
        }
        for a in assignments
    ]


@router.post("/{flight_id}/maintenance-logs", status_code=status.HTTP_201_CREATED)
def create_maintenance_log(
    flight_id: int,
    body: MaintenanceLogRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_flight_or_404(flight_id, db)
    log = MaintenanceLog(
        flight_id=flight_id,
        user_id=current_user.id,
        description=body.description,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {
        "id": log.id,
        "flight_id": log.flight_id,
        "user_id": log.user_id,
        "description": log.description,
        "logged_at": log.logged_at,
    }


@router.get("/{flight_id}/maintenance-logs")
def get_maintenance_logs(
    flight_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _get_flight_or_404(flight_id, db)
    logs = (
        db.query(MaintenanceLog)
        .filter(MaintenanceLog.flight_id == flight_id)
        .order_by(MaintenanceLog.logged_at)
        .all()
    )
    return [
        {
            "id": lg.id,
            "user_id": lg.user_id,
            "description": lg.description,
            "logged_at": lg.logged_at,
        }
        for lg in logs
    ]
