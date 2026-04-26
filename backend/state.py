import asyncio
from typing import Any

from .models import IRCode, IRDevice


class StateManager:
    def __init__(self):
        self.devices: list[IRDevice] = []
        self.learning_bridges: list[str] = []
        self.last_learned_code: dict[str, Any] | None = None
        self.input_states: dict[str, bool] = {}
        # Smart Learn
        self.learning_type: str = "simple"
        self.smart_samples: list[list[dict[str, Any]]] = []
        self.current_burst: list[dict[str, Any]] = []
        self.burst_timer: Any = None

        # Loopback Test
        self.test_mode: bool = False
        self.test_queue: asyncio.Queue | None = None
        self.test_task: asyncio.Task | None = None
        self.test_rx_bridge: str | None = None
        self.test_rx_channel: str | None = None

        # Echo Suppression
        self.sent_codes_history: list[tuple[float, IRCode, list[str]]] = []
