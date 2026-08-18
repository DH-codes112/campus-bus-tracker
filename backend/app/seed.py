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

    route = models.Route(name="Route 1: Hostel -> Main Gate")
    db.add(route)
    db.flush()

    demo_stops = [
        ("Hostel Gate", 26.5123, 80.2329, 1),
        ("Boys Hostel Circle", 26.5089, 80.2361, 2),
        ("Academic Block", 26.5041, 80.2398, 3),
        ("Main Gate", 26.4998, 80.2432, 4),
    ]
    for name, lat, lon, seq in demo_stops:
        db.add(models.Stop(route_id=route.id, name=name,
                            latitude=lat, longitude=lon, sequence=seq))

    bus1 = models.Bus(code="BUS-01", route_id=route.id)
    bus2 = models.Bus(code="BUS-02", route_id=route.id)
    db.add_all([bus1, bus2])

    db.commit()
    print(f"Seeded route '{route.name}' with buses BUS-01 and BUS-02.")
    db.close()


if __name__ == "__main__":
    run()
