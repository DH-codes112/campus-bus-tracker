"""
Database models for the campus bus tracker.

Core idea: students who are riding a bus check in (via QR scan), then their
phone silently pings its GPS location every few seconds. The backend never
trusts a single student's ping — it aggregates all recent pings for a bus
into one confident location (see aggregation.py).
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Boolean
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)          # e.g. "Route 1: Hostel -> Main Gate"

    stops = relationship("Stop", back_populates="route", order_by="Stop.sequence")
    buses = relationship("Bus", back_populates="route")


class Stop(Base):
    __tablename__ = "stops"

    id = Column(Integer, primary_key=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    sequence = Column(Integer, nullable=False)      # order of stop along the route

    route = relationship("Route", back_populates="stops")


class Bus(Base):
    __tablename__ = "buses"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)   # e.g. "BUS-01", printed on the QR code
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=True)

    route = relationship("Route", back_populates="buses")
    checkins = relationship("CheckIn", back_populates="bus")


class CheckIn(Base):
    """A student's active session of riding a specific bus."""
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False)
    student_token = Column(String, nullable=False)   # anonymous device/session id, not a real identity
    checked_in_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)     # auto check-out time
    active = Column(Boolean, default=True)

    bus = relationship("Bus", back_populates="checkins")
    pings = relationship("LocationPing", back_populates="checkin")

    DEFAULT_WINDOW_MINUTES = 45

    @classmethod
    def new_expiry(cls):
        return utcnow() + timedelta(minutes=cls.DEFAULT_WINDOW_MINUTES)


class LocationPing(Base):
    """A single GPS reading from one student's phone."""
    __tablename__ = "location_pings"

    id = Column(Integer, primary_key=True)
    checkin_id = Column(Integer, ForeignKey("checkins.id"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy_m = Column(Float, nullable=True)   # GPS accuracy reported by the browser, if available
    recorded_at = Column(DateTime, default=utcnow)

    checkin = relationship("CheckIn", back_populates="pings")


class BusLocationHistory(Base):
    """
    A timestamped snapshot of each bus's *aggregated* location (not raw
    student pings). This is the training data for ETA prediction: over time
    it builds a record of "where was this bus, at what time, moving how
    fast" that a model can learn from.
    """
    __tablename__ = "bus_location_history"

    id = Column(Integer, primary_key=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed_mps = Column(Float, nullable=True)   # derived speed, meters/second, if computable
    recorded_at = Column(DateTime, default=utcnow)
