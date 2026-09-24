"""
Disaster Response Command Center — FastAPI application
======================================================
REST API + WebSocket (real-time dashboard) + static frontend serving.

Run:
    uvicorn command_center.backend.app:app --host 127.0.0.1 --port 8000
or:
    python -m command_center.backend.app

NOTE: authentication here is a DEMO mock (any credentials accepted, role echoed
back). There is no real access control — the server binds to localhost only and
is intended for the hackathon prototype, not production exposure.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from command_center.backend.store import store
from command_center.backend import swarm_bridge

TICK_SECONDS = 2.0
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


# ---------------------------------------------------------------- WebSocket hub
class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def _simulation_loop() -> None:
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            store.tick()
            await manager.broadcast({"type": "tick", **store.snapshot()})
        except Exception:  # noqa: BLE001 - never let the sim loop die
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_simulation_loop())
    yield
    task.cancel()


app = FastAPI(title="GarudaOne Disaster Response Command Center", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# --------------------------------------------------------------- request models
class LoginReq(BaseModel):
    username: str
    password: str
    role: str = "Operator"
    remember: bool = False


class RobotAction(BaseModel):
    action: str
    mission_id: Optional[str] = None


class MissionCreate(BaseModel):
    title: str
    zone: str
    robot_id: Optional[str] = None
    priority: str = "medium"
    category: str = "search_rescue"
    medical_team: Optional[str] = None
    eta_min: int = 15


class MissionPatch(BaseModel):
    status: str


class VictimAction(BaseModel):
    action: str
    robot_id: Optional[str] = None


# ------------------------------------------------------------------- API: auth
@app.post("/api/auth/login")
def login(req: LoginReq):
    if not req.username or not req.password:
        return JSONResponse({"detail": "Username and password required"}, status_code=400)
    store.log(f"{req.role} '{req.username}' signed in to command center", "info", "Auth")
    return {"token": uuid.uuid4().hex, "username": req.username, "role": req.role}


# --------------------------------------------------------------- API: read data
@app.get("/api/snapshot")
def snapshot():
    return store.snapshot()


@app.get("/api/overview")
def overview():
    return store.overview()


@app.get("/api/robots")
def robots():
    return store.robots


@app.get("/api/missions")
def missions():
    return store.missions


@app.get("/api/victims")
def victims():
    return store.victims


@app.get("/api/alerts")
def alerts():
    return store.alerts


@app.get("/api/resources")
def resources():
    return store.resources


@app.get("/api/activity")
def activity():
    return list(store.activity)[:60]


@app.get("/api/analytics")
def analytics():
    return store.analytics()


@app.get("/api/swarm")
def swarm():
    return swarm_bridge.swarm_status()


# ----------------------------------------------------------- API: fleet actions
@app.post("/api/robots/{rid}/action")
def robot_action(rid: str, body: RobotAction):
    r = store.robot(rid)
    if not r:
        return JSONResponse({"detail": "robot not found"}, status_code=404)

    action = body.action
    if action == "assign" and body.mission_id:
        r["mission_id"] = body.mission_id
        r["status"] = "active"
        m = store.mission(body.mission_id)
        if m:
            m["robot_id"] = rid
            m["status"] = "in_progress"
        store.log(f"{r['name']} ({rid}) assigned to mission {body.mission_id}", "info", rid)
    elif action == "pause":
        r["status"] = "idle"
        r["speed"] = 0.0
        if r["mission_id"]:
            m = store.mission(r["mission_id"])
            if m and m["status"] == "in_progress":
                m["status"] = "delayed"
        store.log(f"{r['name']} ({rid}) mission paused", "warning", rid)
    elif action == "resume":
        r["status"] = "active"
        if r["mission_id"]:
            m = store.mission(r["mission_id"])
            if m and m["status"] == "delayed":
                m["status"] = "in_progress"
        store.log(f"{r['name']} ({rid}) mission resumed", "info", rid)
    elif action == "recall":
        old = r["mission_id"]
        r["mission_id"] = None
        r["status"] = "idle"
        r["speed"] = 0.0
        if old:
            m = store.mission(old)
            if m and m["status"] in ("in_progress", "assigned"):
                m["status"] = "delayed"
        store.log(f"{r['name']} ({rid}) recalled to base", "warning", rid)
    elif action == "emergency_stop":
        r["status"] = "idle"
        r["speed"] = 0.0
        r["mission_id"] = None
        store.log(f"EMERGENCY STOP triggered on {r['name']} ({rid})", "critical", rid)
    else:
        return JSONResponse({"detail": f"unknown action '{action}'"}, status_code=400)

    return r


# -------------------------------------------------------------- API: missions
@app.post("/api/missions")
def create_mission(body: MissionCreate):
    mid = f"#{next(store._mission_ids)}"
    robot = store.robot(body.robot_id) if body.robot_id else None
    status = "assigned" if robot else "pending"
    mission = {
        "id": mid, "title": body.title, "zone": body.zone,
        "robot_id": body.robot_id, "priority": body.priority,
        "category": body.category, "medical_team": body.medical_team,
        "eta_min": body.eta_min, "status": status, "progress": 0,
        "created_at": store.overview()["time"],
    }
    store.missions.insert(0, mission)
    if robot:
        robot["mission_id"] = mid
        robot["status"] = "active"
    store.log(f"Mission {mid} created — {body.title} [{body.priority.upper()}]",
              "info", "Operator")
    return mission


@app.patch("/api/missions/{mid}")
def patch_mission(mid: str, body: MissionPatch):
    m = store.mission(mid)
    if not m:
        return JSONResponse({"detail": "mission not found"}, status_code=404)
    m["status"] = body.status
    if body.status == "in_progress":
        rb = store.robot(m["robot_id"]) if m["robot_id"] else None
        if rb:
            rb["status"] = "active"
    elif body.status == "completed":
        m["progress"] = 100
        rb = store.robot(m["robot_id"]) if m["robot_id"] else None
        if rb:
            rb["mission_id"] = None
            rb["status"] = "idle"
        if m["category"] == "medical":
            store.medical_deliveries += 1
        if m["category"] in ("search_rescue", "evacuation"):
            store.victims_rescued += 2
    store.log(f"Mission {mid} status -> {body.status}", "info", "Operator")
    return m


# --------------------------------------------------------------- API: victims
@app.post("/api/victims/{vid}/action")
def victim_action(vid: str, body: VictimAction):
    v = store.victim(vid)
    if not v:
        return JSONResponse({"detail": "victim not found"}, status_code=404)
    action = body.action
    if action == "accept":
        v["status"] = "accepted"
        store.log(f"SOS {vid} accepted ({v['name']}, {v['location']['zone']})", "info", "Operator")
    elif action == "reject":
        v["status"] = "rejected"
        store.log(f"SOS {vid} rejected", "warning", "Operator")
    elif action == "assign" and body.robot_id:
        v["status"] = "assigned"
        v["assigned_robot"] = body.robot_id
        rb = store.robot(body.robot_id)
        if rb:
            rb["status"] = "active"
        store.log(f"SOS {vid} assigned to {body.robot_id}", "info", "Operator")
    elif action == "rescued":
        v["status"] = "rescued"
        store.victims_rescued += v.get("people_count", 1)
        store.rescued_series.append(store.victims_rescued)
        store.log(f"SOS {vid} — {v.get('people_count', 1)} people rescued ({v['location']['zone']})",
                  "success", v.get("assigned_robot") or "Rescue Team")
    else:
        return JSONResponse({"detail": f"unknown action '{action}'"}, status_code=400)
    return v


@app.post("/api/alerts/{aid}/ack")
def ack_alert(aid: str):
    a = next((x for x in store.alerts if x["id"] == aid), None)
    if not a:
        return JSONResponse({"detail": "alert not found"}, status_code=404)
    a["status"] = "acknowledged"
    store.log(f"Alert {aid} acknowledged", "info", "Operator")
    return a


# ------------------------------------------------------------------- WebSocket
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        await ws.send_json({"type": "snapshot", **store.snapshot()})
        while True:
            # Keep the socket open; ignore inbound (dashboard is read-mostly).
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:  # noqa: BLE001
        manager.disconnect(ws)


# --------------------------------------------------------- static frontend (last)
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
