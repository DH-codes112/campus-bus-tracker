"""
Turns several students' noisy GPS pings on the same bus into one trusted
location, with a confidence score.

Approach:
1. Only look at pings from the last RECENT_WINDOW_SECONDS, from checkins
   that are still active.
2. Take each contributing student's own most recent ping only (so one
   chatty phone doesn't outweigh others).
3. Compute the median lat/lon across students (median resists outliers
   better than a mean).
4. Drop any student whose ping is more than OUTLIER_RADIUS_M from that
   median, then recompute the median from the remaining "good" pings.
5. Report a confidence level based on how many students' pings agreed.
"""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Optional

from sqlalchemy.orm import Session

from . import models

RECENT_WINDOW_SECONDS = 60
OUTLIER_RADIUS_M = 150


def _haversine_m(lat1, lon1, lat2, lon2):
    """Distance in meters between two lat/lon points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


@dataclass
class BusLocation:
    bus_id: int
    latitude: float
    longitude: float
    report_count: int
    confidence: str  # "low" | "medium" | "high"
    updated_at: datetime


def _confidence_for(count: int) -> str:
    if count >= 4:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def get_bus_location(db: Session, bus_id: int) -> Optional[BusLocation]:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=RECENT_WINDOW_SECONDS)

    active_checkins = (
        db.query(models.CheckIn)
        .filter(models.CheckIn.bus_id == bus_id, models.CheckIn.active.is_(True))
        .all()
    )
    if not active_checkins:
        return None

    # latest ping per student (checkin), within the recent window
    latest_pings = []
    for checkin in active_checkins:
        ping = (
            db.query(models.LocationPing)
            .filter(
                models.LocationPing.checkin_id == checkin.id,
                models.LocationPing.recorded_at >= cutoff,
            )
            .order_by(models.LocationPing.recorded_at.desc())
            .first()
        )
        if ping:
            latest_pings.append(ping)

    if not latest_pings:
        return None

    lats = [p.latitude for p in latest_pings]
    lons = [p.longitude for p in latest_pings]
    med_lat, med_lon = median(lats), median(lons)

    # drop outliers relative to the initial median
    good_pings = [
        p for p in latest_pings
        if _haversine_m(p.latitude, p.longitude, med_lat, med_lon) <= OUTLIER_RADIUS_M
    ]

    # fall back to the full set if everything got filtered out (e.g. only 1 ping)
    final_pings = good_pings if good_pings else latest_pings

    final_lat = median(p.latitude for p in final_pings)
    final_lon = median(p.longitude for p in final_pings)

    return BusLocation(
        bus_id=bus_id,
        latitude=final_lat,
        longitude=final_lon,
        report_count=len(final_pings),
        confidence=_confidence_for(len(final_pings)),
        updated_at=datetime.now(timezone.utc),
    )
