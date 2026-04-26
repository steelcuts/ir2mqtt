#!/usr/bin/env python3
"""
Lightweight HTTP control server for the IR2MQTT Simulator.
Used exclusively by Playwright integration tests to control the simulator
without needing the interactive CLI.

Endpoints:
  POST /spawn          - Spawn a new simulated bridge
  POST /inject         - Inject an IR signal from a bridge receiver
  POST /loopback       - Enable/disable loopback (send → re-receive)
  DELETE /bridges/{id} - Delete a specific bridge
  DELETE /bridges      - Delete all bridges
  GET  /bridges        - List current bridges
  GET  /health         - Health check
"""

import argparse
import os
import sys
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Make sure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.simulator.engine import BridgeConfig, SimulatorEngine  # noqa: E402
from tools.simulator.mqtt_client import CoreMqttClient  # noqa: E402

# ---------------------------------------------------------------------------
# App & globals
# ---------------------------------------------------------------------------

app = FastAPI(title="IR2MQTT Sim Control Server")

_engine: SimulatorEngine | None = None
_main_client: CoreMqttClient | None = None


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class SpawnRequest(BaseModel):
    bridge_id: str | None = None
    bridge_type: str = "mqtt"


class InjectRequest(BaseModel):
    bridge_id: str
    protocol: str = "nec"
    address: str = "0x04"
    command: str = "0x08"
    receiver_id: str | None = None


class LoopbackRequest(BaseModel):
    enabled: bool = True


class BridgeInfo(BaseModel):
    id: str
    name: str
    online: bool
    receivers: list[str]
    transmitters: list[str]
    enabled_protocols: list[str]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/bridges", response_model=list[BridgeInfo])
def list_bridges():
    assert _engine is not None
    return [
        BridgeInfo(
            id=b.id,
            name=b.name,
            online=b.online,
            receivers=[r.id for r in b.receivers],
            transmitters=[t.id for t in b.transmitters],
            enabled_protocols=b.enabled_protocols,
        )
        for b in _engine.bridges
    ]


@app.post("/spawn", response_model=BridgeInfo)
def spawn(req: SpawnRequest):
    assert _engine is not None
    bid = req.bridge_id or f"test-bridge-{uuid.uuid4().hex[:4]}"

    # Add to sim configs if not already present
    if not any(c.bid == bid for c in _engine.simulated_configs):
        _engine.simulated_configs.append(
            BridgeConfig(
                bid=bid,
                bridge_type=req.bridge_type,
                ip="192.168.1.100" if req.bridge_type == "mqtt" else None,
                protocols=["nec", "samsung", "raw", "sony", "lg"],
            )
        )

    _engine.add_bridge(bid)
    # Give MQTT time to connect, publish config+state, and for backend to ingest
    time.sleep(2.0)

    bridge = _engine.get_bridge_by_id(bid)
    if not bridge:
        raise HTTPException(500, f"Bridge {bid} failed to spawn")

    return BridgeInfo(
        id=bridge.id,
        name=bridge.name,
        online=bridge.online,
        receivers=[r.id for r in bridge.receivers],
        transmitters=[t.id for t in bridge.transmitters],
        enabled_protocols=bridge.enabled_protocols,
    )


@app.post("/inject")
def inject(req: InjectRequest):
    assert _engine is not None
    bridge = _engine.get_bridge_by_id(req.bridge_id)
    if not bridge:
        raise HTTPException(404, f"Bridge {req.bridge_id} not found")

    inner: dict = {}
    if req.protocol in ("samsung", "sony", "lg"):
        inner["data"] = req.address  # re-use address field as data
        inner["nbits"] = 32
    else:
        inner["address"] = req.address
        inner["command"] = req.command

    payload: dict = {"protocol": req.protocol, "payload": inner}
    if req.receiver_id:
        payload["receiver_id"] = req.receiver_id

    _engine.inject_signal(req.bridge_id, payload)
    return {"ok": True}


@app.post("/loopback")
def set_loopback(req: LoopbackRequest):
    assert _engine is not None
    _engine.loopback_enabled = req.enabled
    return {"ok": True, "loopback": _engine.loopback_enabled}


@app.delete("/bridges/{bridge_id}")
def delete_bridge(bridge_id: str):
    assert _engine is not None
    bridge = _engine.get_bridge_by_id(bridge_id)
    if not bridge:
        raise HTTPException(404, f"Bridge {bridge_id} not found")
    _engine.delete_bridge(bridge_id)
    time.sleep(0.3)
    return {"ok": True}


@app.delete("/bridges")
def delete_all():
    assert _engine is not None
    _engine.delete_all_bridges()
    _engine.simulated_configs.clear()
    time.sleep(0.3)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="IR2MQTT Simulator Control Server")
    parser.add_argument("--broker", default="localhost", help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--port", type=int, default=8088, help="HTTP server port")
    args = parser.parse_args()

    global _engine, _main_client

    def noop_log(_source: str, _msg: str, _level: str) -> None:
        pass

    # Use a temp config file so we don't pollute the real simulator_config.json
    config_file = "/tmp/ir2mqtt_sim_test_config.json"
    if os.path.exists(config_file):
        os.remove(config_file)

    _engine = SimulatorEngine(
        broker=args.broker,
        port=args.mqtt_port,
        on_log=noop_log,
        on_bridges_updated=lambda: None,
        config_file=config_file,
    )

    _main_client = CoreMqttClient(
        broker=args.broker,
        port=args.mqtt_port,
        on_log=noop_log,
        on_message=_engine.handle_message,
        on_connection_change=lambda _status, _err: None,
    )

    _engine.set_main_client(_main_client)
    _main_client.start()
    time.sleep(0.5)  # Let MQTT connection settle

    print(f"[sim_server] Simulator control server ready on port {args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="error")


if __name__ == "__main__":
    main()
