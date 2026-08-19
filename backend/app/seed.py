"""
Seeds one demo route with stops and two buses, so there's something real
to check in to and show on the map. Run with: uv run python -m app.seed

Coordinates default to a straight-line demo path near Kanpur — replace
with real coordinates for your actual campus/hostel/city route before
the demo.
"""
from .db import SessionLocal, init_db
from . import models


def run():
    init_db()
    db = SessionLocal()

    if db.query(models.Route).first():
        print("Already seeded, skipping.")
        return

    # Route 1: Hostel -> Main Gate, served by BUS-01
    route1 = models.Route(name="Route 1")
    db.add(route1)
    db.flush()
    route1_stops = [
        ("RAWATPUR", 26.480684735962225, 80.27795722192468, 1),
        ("PSIT", 26.44897291463449, 80.19029330993578, 2),
    ]
    for name, lat, lon, seq in route1_stops:
        db.add(models.Stop(route_id=route1.id, name=name,
                            latitude=lat, longitude=lon, sequence=seq))
    db.add(models.Bus(code="BUS-01", route_id=route1.id))

    # Route 2: a separate example route, served by BUS-02 —
    # replace these coordinates with your college's second route
    route2 = models.Route(name="Route 2")
    db.add(route2)
    db.flush()
    route2_stops = [
        ("AHIRWAN",26.395602286681306, 80.4037466181346, 1),
        ("PSIT", 26.44897291463449, 80.19029330993578, 2),
    ]
    for name, lat, lon, seq in route2_stops:
        db.add(models.Stop(route_id=route2.id, name=name,
                            latitude=lat, longitude=lon, sequence=seq))
    db.add(models.Bus(code="BUS-02", route_id=route2.id))

    db.commit()
    print(f"Seeded '{route1.name}' (BUS-01) and '{route2.name}' (BUS-02).")
    db.close()


if __name__ == "__main__":
    run()
