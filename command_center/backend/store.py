"""
Disaster Response Command Center — In-Memory Data Store + Live Simulation
=========================================================================
Holds the full operational picture (robots, missions, victims, alerts,
resources, activity log, zones) and advances it every tick so the web
dashboards update in real time. No external database required.

All access happens inside the FastAPI asyncio event loop (the simulator is
an asyncio task), so this is intentionally lock-free.
"""

from __future__ import annotations

import itertools
import random
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

# Metro operating area (co-located with the drone SITL home in Bangalore so the
# command center and the real GarudaOne swarm share one coordinate frame).
CENTER_LAT = 12.9716
CENTER_LON = 77.5946

WEATHER_STATES = [
    "Heavy Rain", "Thunderstorm", "Overcast", "Flood Warning", "Smoke Haze",
]
ROBOT_NAMES = [
    "Rescuer Alpha", "Skyeye One", "Medic Vortex", "Ground Warden", "Aegis Scout",
    "Lifeline Bravo", "Falcon Recon", "Medic Halo", "Terra Breaker", "Nimbus Watch",
    "Path Clearer", "Relief Carrier",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jitter(value: float, amount: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value + random.uniform(-amount, amount)))


class Store:
    def __init__(self) -> None:
        self._log_ids = itertools.count(1)
        self._mission_ids = itertools.count(1)
        self._victim_ids = itertools.count(1)
        self._alert_ids = itertools.count(1)

        self.started_at = time.time()
        self.severity = "CRITICAL"
        self.weather = "Heavy Rain"
        self.tick_count = 0

        # Historical series for analytics (rolling).
        self.rescued_series: list[int] = [4, 9, 12, 18, 23, 31, 38]
        self.completion_series: list[int] = [2, 5, 6, 9, 11, 14, 17]

        self.zones = self._seed_zones()
        self.robots = self._seed_robots()
        self.missions = self._seed_missions()
        self.victims = self._seed_victims()
        self.alerts = self._seed_alerts()
        self.resources = self._seed_resources()
        self.activity: deque[dict] = deque(maxlen=200)

        self.victims_rescued = 38
        self.medical_deliveries = 21

        for msg, level, source in [
            ("Command center online — all zones linked", "success", "System"),
            ("Drone-02 (Skyeye One) detected 3 survivors in Zone B", "warning", "Skyeye One"),
            ("Mission #3 completed — 5 civilians evacuated from Zone A", "success", "Ground Warden"),
            ("Flood level rising in Zone D — reroute advised", "critical", "Sensor Grid"),
            ("Medic Vortex delivered medical supplies to Zone C", "info", "Medic Vortex"),
        ]:
            self.log(msg, level, source)

    # ---------------------------------------------------------------- seed
    def _seed_zones(self) -> list[dict]:
        specs = [
            ("Zone A", "Downtown Core", "critical", 0.010, 0.008),
            ("Zone B", "Riverside District", "critical", -0.012, 0.010),
            ("Zone C", "Industrial Belt", "high", 0.014, -0.011),
            ("Zone D", "Old Town (Flooded)", "critical", -0.010, -0.013),
            ("Zone E", "North Suburbs", "medium", 0.004, 0.016),
        ]
        zones = []
        for zid, name, sev, dlat, dlon in specs:
            zones.append({
                "id": zid, "name": name, "severity": sev,
                "lat": CENTER_LAT + dlat, "lon": CENTER_LON + dlon,
                "radius_m": random.randint(350, 700),
            })
        return zones

    def _seed_robots(self) -> list[dict]:
        types = (["ground"] * 5) + (["drone"] * 4) + (["medical"] * 3)
        prefix = {"ground": "GR", "drone": "DR", "medical": "MB"}
        counters = {"ground": 0, "drone": 0, "medical": 0}
        statuses = ["active", "active", "active", "charging", "idle", "offline"]
        robots = []
        for i, rtype in enumerate(types):
            counters[rtype] += 1
            zone = random.choice(self.zones)
            status = random.choice(statuses) if i > 2 else "active"
            battery = (random.randint(20, 45) if status == "charging"
                       else 0 if status == "offline"
                       else random.randint(45, 100))
            robots.append({
                "id": f"{prefix[rtype]}-{counters[rtype]:02d}",
                "name": ROBOT_NAMES[i],
                "type": rtype,
                "status": status,
                "battery": battery,
                "signal": 0 if status == "offline" else random.randint(55, 99),
                "speed": 0.0 if status in ("charging", "idle", "offline") else round(random.uniform(1.5, 8.0), 1),
                "temperature": round(random.uniform(32, 58), 1),
                "mission_id": None,
                "operator": None,
                "eta_min": None,
                "location": {"lat": _jitter(zone["lat"], 0.002, -90, 90),
                             "lon": _jitter(zone["lon"], 0.002, -180, 180),
                             "zone": zone["id"]},
                "last_updated": now_iso(),
            })
        return robots

    def _seed_missions(self) -> list[dict]:
        cats = ["search_rescue", "medical", "supply", "surveillance", "evacuation"]
        prios = ["critical", "high", "medium", "low"]
        statuses = ["in_progress", "assigned", "pending", "completed", "delayed"]
        missions = []
        for i in range(8):
            mid = next(self._mission_ids)
            zone = random.choice(self.zones)
            status = statuses[i % len(statuses)]
            robot = random.choice(self.robots) if status in ("in_progress", "assigned", "delayed") else None
            if robot and status != "completed":
                robot["mission_id"] = f"#{mid}"
                robot["operator"] = random.choice(["Cmdr. Rao", "Op. Mehta", "Op. Diaz"])
            missions.append({
                "id": f"#{mid}",
                "title": f"{random.choice(['Search', 'Evacuate', 'Deliver to', 'Survey', 'Secure'])} {zone['name']}",
                "zone": zone["id"],
                "robot_id": robot["id"] if robot else None,
                "priority": prios[i % len(prios)],
                "category": cats[i % len(cats)],
                "medical_team": random.choice(["Team Red", "Team Blue", None]),
                "eta_min": random.randint(4, 40),
                "status": status,
                "progress": 100 if status == "completed" else (random.randint(10, 85) if status == "in_progress" else 0),
                "created_at": now_iso(),
            })
        return missions

    def _seed_victims(self) -> list[dict]:
        names = ["A. Sharma", "M. Osei", "L. Fernandez", "K. Tanaka", "R. Silva",
                 "D. Ali", "P. Novak", "S. Reddy"]
        trapped = ["none", "partial", "severe"]
        sev = ["critical", "high", "medium", "low"]
        victims = []
        for i in range(8):
            vid = next(self._victim_ids)
            zone = random.choice(self.zones)
            victims.append({
                "id": f"REQ-{vid:03d}",
                "name": names[i],
                "location": {"zone": zone["id"], "lat": _jitter(zone["lat"], 0.003, -90, 90),
                             "lon": _jitter(zone["lon"], 0.003, -180, 180)},
                "people_count": random.randint(1, 12),
                "medical_required": random.random() < 0.6,
                "food_required": random.random() < 0.7,
                "water_required": random.random() < 0.8,
                "trapped_level": random.choice(trapped),
                "severity": sev[i % len(sev)],
                "status": "pending",
                "assigned_robot": None,
                "request_time": now_iso(),
            })
        return victims

    def _seed_alerts(self) -> list[dict]:
        kinds = ["building_collapse", "fire", "flood", "aftershock",
                 "gas_leak", "road_blocked", "comms_failure"]
        sev = ["critical", "high", "medium"]
        alerts = []
        for i, kind in enumerate(kinds):
            aid = next(self._alert_ids)
            zone = random.choice(self.zones)
            alerts.append({
                "id": f"ALT-{aid:03d}",
                "type": kind,
                "zone": zone["id"],
                "severity": sev[i % len(sev)],
                "status": "active" if i % 3 else "acknowledged",
                "time": now_iso(),
            })
        return alerts

    def _seed_resources(self) -> list[dict]:
        specs = [
            ("Medical Kits", 500, 214), ("Food Packs", 2000, 860),
            ("Water Supplies", 3000, 1450), ("Ambulances", 24, 15),
            ("Fuel (L)", 5000, 2600), ("Power Stations", 40, 18),
        ]
        return [{"name": n, "total": t, "used": u, "remaining": t - u} for n, t, u in specs]

    # --------------------------------------------------------------- helpers
    def log(self, message: str, level: str = "info", source: str = "System") -> dict:
        entry = {"id": next(self._log_ids), "time": now_iso(),
                 "message": message, "level": level, "source": source}
        self.activity.appendleft(entry)
        return entry

    def robot(self, rid: str) -> Optional[dict]:
        return next((r for r in self.robots if r["id"] == rid), None)

    def mission(self, mid: str) -> Optional[dict]:
        return next((m for m in self.missions if m["id"] == mid), None)

    def victim(self, vid: str) -> Optional[dict]:
        return next((v for v in self.victims if v["id"] == vid), None)

    # ---------------------------------------------------------------- stats
    def overview(self) -> dict:
        robots = self.robots
        drones = [r for r in robots if r["type"] == "drone"]
        active = [r for r in robots if r["status"] == "active"]
        charging = [r for r in robots if r["status"] == "charging"]
        offline = [r for r in robots if r["status"] == "offline"]
        online = [r for r in robots if r["status"] != "offline"]
        avg_batt = round(sum(r["battery"] for r in online) / max(1, len(online)))
        emergency = [m for m in self.missions if m["status"] in ("in_progress", "assigned", "delayed")]
        completed = [m for m in self.missions if m["status"] == "completed"]
        return {
            "total_robots": len(robots),
            "active_robots": len(active),
            "charging_robots": len(charging),
            "offline_robots": len(offline),
            "emergency_missions": len(emergency),
            "completed_missions": len(completed),
            "victims_rescued": self.victims_rescued,
            "medical_deliveries": self.medical_deliveries,
            "available_drones": len([d for d in drones if d["status"] in ("active", "idle") and d["battery"] > 20]),
            "avg_battery": avg_batt,
            "severity": self.severity,
            "weather": self.weather,
            "time": now_iso(),
            "active_zones": len(self.zones),
            "pending_victims": len([v for v in self.victims if v["status"] == "pending"]),
            "active_alerts": len([a for a in self.alerts if a["status"] == "active"]),
        }

    def analytics(self) -> dict:
        by_status: dict[str, int] = {}
        for m in self.missions:
            by_status[m["status"]] = by_status.get(m["status"], 0) + 1
        return {
            "mission_status": by_status,
            "battery_by_robot": [{"id": r["id"], "battery": r["battery"], "type": r["type"]}
                                 for r in self.robots],
            "utilization": {
                "on_mission": len([r for r in self.robots if r["mission_id"]]),
                "idle": len([r for r in self.robots if r["status"] == "idle"]),
                "charging": len([r for r in self.robots if r["status"] == "charging"]),
                "offline": len([r for r in self.robots if r["status"] == "offline"]),
            },
            "rescued_trend": self.rescued_series[-12:],
            "completion_trend": self.completion_series[-12:],
        }

    def snapshot(self) -> dict:
        return {
            "overview": self.overview(),
            "robots": self.robots,
            "missions": self.missions,
            "victims": self.victims,
            "alerts": self.alerts,
            "resources": self.resources,
            "activity": list(itertools.islice(self.activity, 0, 40)),
            "zones": self.zones,
            "analytics": self.analytics(),
        }

    # ----------------------------------------------------------------- tick
    def tick(self) -> dict:
        """Advance the simulation one step. Returns a light update payload."""
        self.tick_count += 1
        new_logs: list[dict] = []

        for r in self.robots:
            r["last_updated"] = now_iso()
            if r["status"] == "active":
                r["battery"] = round(max(0, r["battery"] - random.uniform(0.2, 0.9)), 1)
                r["signal"] = int(_jitter(r["signal"], 4, 20, 100))
                r["speed"] = round(_jitter(r["speed"], 0.6, 0.0, 12.0), 1)
                r["temperature"] = round(_jitter(r["temperature"], 0.8, 28, 75), 1)
                # Drift location slightly (movement).
                r["location"]["lat"] = _jitter(r["location"]["lat"], 0.0006, -90, 90)
                r["location"]["lon"] = _jitter(r["location"]["lon"], 0.0006, -180, 180)
                if r["battery"] <= 15:
                    r["status"] = "charging"
                    r["speed"] = 0.0
                    old = r["mission_id"]
                    r["mission_id"] = None
                    new_logs.append(self.log(
                        f"{r['name']} ({r['id']}) battery low ({r['battery']:.0f}%) — returning to charge",
                        "warning", r["id"]))
                    if old:
                        m = self.mission(old)
                        if m and m["status"] == "in_progress":
                            m["status"] = "delayed"
            elif r["status"] == "charging":
                r["battery"] = round(min(100, r["battery"] + random.uniform(1.5, 3.5)), 1)
                if r["battery"] >= 98:
                    r["status"] = "idle"
                    new_logs.append(self.log(f"{r['name']} ({r['id']}) fully charged — ready", "success", r["id"]))

        # Advance in-progress missions.
        for m in self.missions:
            if m["status"] == "in_progress":
                m["progress"] = min(100, m["progress"] + random.randint(2, 9))
                if m["progress"] >= 100:
                    m["status"] = "completed"
                    self.completion_series.append(self.completion_series[-1] + 1)
                    if m["category"] == "medical":
                        self.medical_deliveries += 1
                    if m["category"] in ("search_rescue", "evacuation"):
                        self.victims_rescued += random.randint(1, 4)
                        self.rescued_series.append(self.victims_rescued)
                    rb = self.robot(m["robot_id"]) if m["robot_id"] else None
                    if rb:
                        rb["mission_id"] = None
                        rb["status"] = "idle" if rb["status"] == "active" else rb["status"]
                    new_logs.append(self.log(f"Mission {m['id']} completed — {m['title']}", "success", m["robot_id"] or "System"))

        # Occasionally emit a fresh disaster alert.
        if random.random() < 0.14:
            kind = random.choice(["fire", "flood", "aftershock", "gas_leak", "road_blocked", "building_collapse"])
            zone = random.choice(self.zones)
            aid = next(self._alert_ids)
            alert = {"id": f"ALT-{aid:03d}", "type": kind, "zone": zone["id"],
                     "severity": random.choice(["critical", "high", "medium"]),
                     "status": "active", "time": now_iso()}
            self.alerts.insert(0, alert)
            self.alerts[:] = self.alerts[:30]
            new_logs.append(self.log(
                f"{kind.replace('_', ' ').title()} reported in {zone['id']} ({zone['name']})",
                "critical", "Sensor Grid"))

        # Occasionally a new victim request.
        if random.random() < 0.10:
            vid = next(self._victim_ids)
            zone = random.choice(self.zones)
            v = {"id": f"REQ-{vid:03d}", "name": f"Survivor {vid}",
                 "location": {"zone": zone["id"], "lat": _jitter(zone["lat"], 0.003, -90, 90),
                              "lon": _jitter(zone["lon"], 0.003, -180, 180)},
                 "people_count": random.randint(1, 8),
                 "medical_required": random.random() < 0.6,
                 "food_required": random.random() < 0.7,
                 "water_required": random.random() < 0.8,
                 "trapped_level": random.choice(["none", "partial", "severe"]),
                 "severity": random.choice(["critical", "high", "medium", "low"]),
                 "status": "pending", "assigned_robot": None, "request_time": now_iso()}
            self.victims.insert(0, v)
            self.victims[:] = self.victims[:40]
            new_logs.append(self.log(f"New SOS request {v['id']} in {zone['id']} — {v['people_count']} people", "warning", "SOS Line"))

        if self.tick_count % 20 == 0:
            self.weather = random.choice(WEATHER_STATES)

        return {"type": "tick", "overview": self.overview(), "robots": self.robots,
                "new_logs": new_logs, "analytics": self.analytics()}


store = Store()
