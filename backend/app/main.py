import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import models
from .db import init_db, get_db
from .aggregation import get_bus_location
from . import seed as seed_module

app = FastAPI(title="Campus Bus Tracker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # fine for a college prototype; tighten for real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    seed_module.run()  # no-ops automatically if already seeded


@app.on_event("startup")
def on_startup():
    init_db()


# ---------- request/response schemas ----------

class CheckInRequest(BaseModel):
    bus_code: str
    student_token: str  # random id generated client-side, no login needed


class CheckInResponse(BaseModel):
    checkin_id: int
    bus_id: int
    bus_code: str
    expires_at: datetime


class PingRequest(BaseModel):
    checkin_id: int
    latitude: float
    longitude: float
    accuracy_m: Optional[float] = None


class BusLocationOut(BaseModel):
    bus_id: int
    bus_code: str
    latitude: float
    longitude: float
    report_count: int
    confidence: str
    updated_at: datetime


# ---------- check-in / check-out ----------

@app.post("/api/checkin", response_model=CheckInResponse)
def checkin(payload: CheckInRequest, db: Session = Depends(get_db)):
    bus = db.query(models.Bus).filter(models.Bus.code == payload.bus_code).first()
    if not bus:
        raise HTTPException(status_code=404, detail="Unknown bus code")

    checkin = models.CheckIn(
        bus_id=bus.id,
        student_token=payload.student_token,
        expires_at=models.CheckIn.new_expiry(),
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    return CheckInResponse(
        checkin_id=checkin.id,
        bus_id=bus.id,
        bus_code=bus.code,
        expires_at=checkin.expires_at,
    )


@app.post("/api/checkout/{checkin_id}")
def checkout(checkin_id: int, db: Session = Depends(get_db)):
    checkin = db.query(models.CheckIn).get(checkin_id)
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")
    checkin.active = False
    db.commit()
    return {"status": "checked_out"}


# ---------- location pings ----------

@app.post("/api/ping")
async def ping(payload: PingRequest, db: Session = Depends(get_db)):
    checkin = db.query(models.CheckIn).get(payload.checkin_id)
    if not checkin or not checkin.active:
        raise HTTPException(status_code=404, detail="Check-in not active")

    now = datetime.now(timezone.utc)
    expires_at = checkin.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        checkin.active = False
        db.commit()
        raise HTTPException(status_code=410, detail="Check-in expired, please check in again")

    reading = models.LocationPing(
        checkin_id=checkin.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_m=payload.accuracy_m,
    )
    db.add(reading)
    db.commit()

    # push the freshly-recomputed bus location to anyone watching the map
    await broadcast_bus_location(checkin.bus_id, db)

    return {"status": "ok"}


# ---------- buses / routes ----------

@app.get("/api/buses", response_model=List[BusLocationOut])
def list_bus_locations(db: Session = Depends(get_db)):
    buses = db.query(models.Bus).all()
    results = []
    for bus in buses:
        loc = get_bus_location(db, bus.id)
        if loc:
            results.append(BusLocationOut(
                bus_id=bus.id,
                bus_code=bus.code,
                latitude=loc.latitude,
                longitude=loc.longitude,
                report_count=loc.report_count,
                confidence=loc.confidence,
                updated_at=loc.updated_at,
            ))
    return results


@app.get("/api/routes")
def list_routes(db: Session = Depends(get_db)):
    routes = db.query(models.Route).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "stops": [
                {"id": s.id, "name": s.name, "latitude": s.latitude,
                 "longitude": s.longitude, "sequence": s.sequence}
                for s in r.stops
            ],
            "buses": [{"id": b.id, "code": b.code} for b in r.buses],
        }
        for r in routes
    ]


# ---------- live WebSocket broadcast ----------

class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(json.dumps(message, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def broadcast_bus_location(bus_id: int, db: Session):
    bus = db.query(models.Bus).get(bus_id)
    loc = get_bus_location(db, bus_id)
    if not bus or not loc:
        return
    await manager.broadcast({
        "type": "bus_location",
        "bus_id": bus.id,
        "bus_code": bus.code,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "report_count": loc.report_count,
        "confidence": loc.confidence,
        "updated_at": loc.updated_at.isoformat(),
    })


@app.websocket("/ws/live")
async def live_updates(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            # this socket is push-only from the server; just keep it alive
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# serve the static frontend (student check-in page + live map)
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
