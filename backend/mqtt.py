import asyncio
import json
import time
import uuid
from collections import Counter, deque
from collections.abc import Callable
from typing import Any

from paho.mqtt import client as mqtt_client

try:
    from paho.mqtt.enums import CallbackAPIVersion
except ImportError:
    CallbackAPIVersion = None

from .bridge_manager import BridgeManager, BridgeTransport
from .models import IRCode
from .state import StateManager
from .utils import match_ir_code
from .websockets import broadcast_ws


class MQTTManager(BridgeTransport):
    def __init__(self, state_manager: StateManager, automation_manager: Any):
        self.client: mqtt_client.Client | None = None
        self.connected = False
        self.loop: asyncio.AbstractEventLoop | None = None
        self.bridge_manager = BridgeManager()
        self.bridge_manager.register_transport("mqtt", self)
        self.on_connect_cb: Callable | None = None
        self.state_manager = state_manager
        self.automation_manager = automation_manager
        self.integration = None
        self.settings: Any | None = None
        self.logger: Any | None = None
        # For awaiting command responses
        self.pending_requests: dict[str, asyncio.Event] = {}
        self.pending_responses: dict[str, dict] = {}

    @property
    def bridges(self):
        return self.bridge_manager.bridges

    @bridges.setter
    def bridges(self, value):
        self.bridge_manager.bridges = value

    def set_integration(self, integration):
        self.integration = integration

    def _update_last_seen(self, bridge_id):
        self.bridge_manager.update_last_seen(bridge_id)

    def _broadcast_bridges(self):
        self.bridge_manager._broadcast_bridges()

    def _get_bridges_list_for_broadcast(self):
        return self.bridge_manager.get_bridges_list_for_broadcast()

    def setup(
        self,
        loop: asyncio.AbstractEventLoop,
        settings,
        logger,
        on_connect_cb: Callable | None = None,
    ):
        self.loop = loop
        self.on_connect_cb = on_connect_cb
        self.settings = settings
        self.logger = logger

        async def broadcast_wrapper(data):
            await broadcast_ws({"type": "bridges_updated", "bridges": data})

        self.bridge_manager.set_loop(loop, broadcast_wrapper)
        self.logger.info("Setting up MQTT manager.")
        self.connect()

    def connect(self):
        try:
            broker = self.settings.mqtt_broker
            port = self.settings.mqtt_port
            user = self.settings.mqtt_user
            password = self.settings.mqtt_pass

            if not broker:
                self.logger.warning("No MQTT broker configured. Cannot connect.")
                return

            client_id = f"ir2mqtt-backend-{uuid.uuid4()}"
            self.logger.info(
                "Attempting to connect to MQTT broker at %s:%s with client ID '%s'",
                broker,
                port,
                client_id,
            )
            if CallbackAPIVersion:
                self.client = mqtt_client.Client(CallbackAPIVersion.VERSION2, client_id)
            else:
                self.client = mqtt_client.Client(client_id=client_id)
            if user:
                self.client.username_pw_set(user, password)
                self.logger.info("Using username '%s' for MQTT connection.", user)
            else:
                self.logger.info("No username configured for MQTT connection.")

            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message

            self.client.connect_async(broker, int(port), 60)
            self.client.loop_start()
            self.logger.info("MQTT client loop started.")
        except Exception as e:
            self.logger.error("Error during MQTT connection setup: %s", e, exc_info=True)
            self.connected = False

    def disconnect(self):
        if self.client:
            self.logger.info("Disconnecting from MQTT broker.")
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None
            self.connected = False
            self.logger.info("MQTT Client disconnected.")
        else:
            self.logger.info("Request to disconnect MQTT client, but no client was connected.")

    async def reload(self):
        self.logger.info("Reloading MQTT connection...")
        self.disconnect()
        # Add a small delay to allow for clean disconnection before reconnecting
        await asyncio.sleep(1)
        self.connect()
        self.logger.info("MQTT reload complete.")

    def on_connect(self, client: mqtt_client.Client, _userdata, _flags, rc, _properties=None):
        if rc == 0:
            self.connected = True
            self.logger.info("Successfully connected to MQTT broker.")

            # New topic structure
            base_topics = [
                "ir2mqtt/bridge/+/config",
                "ir2mqtt/bridge/+/state",
                "ir2mqtt/bridge/+/response",
                "ir2mqtt/bridge/+/received",
            ]
            for topic in base_topics:
                client.subscribe(topic)
                self.logger.debug("Subscribed to topic: %s", topic)

            if self.integration:
                integration_topics = self.integration.get_subscribe_topics()
                self.logger.info(
                    "Subscribing to %d topics for '%s' integration.",
                    len(integration_topics),
                    self.integration.NAME,
                )
                for topic in integration_topics:
                    client.subscribe(topic)
                    self.logger.debug("Subscribed to integration topic: %s", topic)

                if self.loop and self.loop.is_running():
                    self.logger.info("Running on_mqtt_connect handler for integration.")
                    asyncio.run_coroutine_threadsafe(self.integration.on_mqtt_connect(self), self.loop)

            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(broadcast_ws({"type": "mqtt_status", "connected": True}), self.loop)
                if self.on_connect_cb:
                    asyncio.run_coroutine_threadsafe(self.on_connect_cb(), self.loop)
        else:
            self.connected = False
            self.logger.error(
                "MQTT connection failed with code %s. See https://mid.as/paho-mqtt-python/callbacks.html#on-connect for details.",
                rc,
            )
            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(broadcast_ws({"type": "mqtt_status", "connected": False}), self.loop)

    def _analyze_smart_samples(self, samples: list) -> dict[str, Any] | None:
        if not samples:
            return None

        code_counts = Counter()
        for burst in samples:
            # Use set to count a code only once per burst
            burst_codes = set()
            for code in burst:
                burst_codes.add(json.dumps(code, sort_keys=True))

            for c in burst_codes:
                code_counts[c] += 1

        if not code_counts:
            return None

        most_common_json, _ = code_counts.most_common(1)[0]
        return json.loads(most_common_json)

    def _process_burst(self):
        burst = self.state_manager.current_burst
        self.state_manager.current_burst = []
        self.state_manager.burst_timer = None

        if not burst:
            return

        self.state_manager.smart_samples.append(burst)
        count = len(self.state_manager.smart_samples)
        target = 5

        self.logger.info("Smart Learn Burst %s/%s captured (%s codes)", count, target, len(burst))

        asyncio.create_task(
            broadcast_ws(
                {
                    "type": "smart_learn_progress",
                    "current": count,
                    "target": target,
                    "latest_sample": burst[-1],
                }
            )
        )

        if count >= target:
            best_code = self._analyze_smart_samples(self.state_manager.smart_samples)
            self.logger.info("Smart Learn Finished. Result: %s", best_code)
            self.state_manager.last_learned_code = best_code
            self.state_manager.learning_bridges = []

            asyncio.create_task(
                broadcast_ws(
                    {
                        "type": "learned_code",
                        "code": best_code,
                        "bridge": self.state_manager.last_code_bridge or "smart",
                    }
                )
            )
            asyncio.create_task(broadcast_ws({"type": "learning_status", "active": False}))

    def _handle_smart_data(self, data, bridge_name):
        self.state_manager.current_burst.append(data)
        self.state_manager.last_code_bridge = bridge_name
        if self.state_manager.burst_timer:
            self.state_manager.burst_timer.cancel()
        self.state_manager.burst_timer = self.loop.call_later(0.5, self._process_burst)

    def on_message(self, _client: mqtt_client.Client, _userdata, msg: mqtt_client.MQTTMessage):
        try:
            payload_str = msg.payload.decode()
            topic = msg.topic
            topic_parts = topic.split("/")

            self.logger.debug("MQTT message received on topic '%s': %s", topic, payload_str)

            if len(topic_parts) < 3 or topic_parts[0] != "ir2mqtt":
                return  # Not a topic for us

            # Delegate to integration first
            if self.integration and self.integration.handle_message(topic, payload_str, self):
                self.logger.debug("Message handled by '%s' integration.", self.integration.NAME)
                return

            # New Topic Structure Handling
            if topic_parts[1] == "bridge" and len(topic_parts) >= 4:
                bridge_id = topic_parts[2]
                msg_type = topic_parts[3]

                try:
                    payload = json.loads(payload_str) if payload_str else {}
                except json.JSONDecodeError:
                    self.logger.warning("Received malformed JSON on topic '%s': %s", topic, payload_str)
                    return

                if msg_type == "config":
                    if not payload_str:  # Empty retained message means bridge removed
                        if bridge_id in self.bridges:
                            self.logger.warning("Bridge '%s' config has been cleared.", bridge_id)
                            del self.bridges[bridge_id]
                            self._broadcast_bridges()
                        return
                    self.logger.info("Received config for bridge '%s'.", bridge_id)
                    if bridge_id not in self.bridges:
                        self.bridges[bridge_id] = {}

                    # Update fields carefully to avoid overwriting specific arrays with partial payloads
                    for key, value in payload.items():
                        self.bridges[bridge_id][key] = value

                    self._update_last_seen(bridge_id)
                    self._broadcast_bridges()

                elif msg_type == "state":
                    if not payload_str:  # Empty retained message means bridge removed
                        if bridge_id in self.bridges:
                            self.logger.warning("Bridge '%s' state has been cleared.", bridge_id)
                            del self.bridges[bridge_id]
                            self._broadcast_bridges()
                        return

                    self.logger.debug("Received state for bridge '%s'.", bridge_id)
                    if bridge_id not in self.bridges:
                        # We haven't seen a config message yet, but we can create a placeholder
                        self.bridges[bridge_id] = {}

                    # If status changes, log it
                    old_online_status = self.bridges[bridge_id].get("online", False)
                    new_online_status = payload.get("online", False)
                    if old_online_status != new_online_status:
                        self.logger.info(
                            "Bridge '%s' status changed to '%s'.",
                            bridge_id,
                            "online" if new_online_status else "offline",
                        )

                    # Update fields carefully
                    for key, value in payload.items():
                        self.bridges[bridge_id][key] = value

                    self._update_last_seen(bridge_id)
                    self._broadcast_bridges()

                elif msg_type == "response":
                    if not payload_str:
                        return
                    request_id = payload.get("request_id")
                    if request_id in self.pending_requests:
                        self.logger.debug("Received response for request_id: %s", request_id)
                        self.pending_responses[request_id] = payload
                        if self.loop:
                            self.loop.call_soon_threadsafe(self.pending_requests[request_id].set)

                elif msg_type == "received":
                    if not payload_str:
                        return
                    self._handle_ir_received(bridge_id, payload)

                return  # Message was handled

            # Handle HA automation triggers: ir2mqtt/automation/{auto_id}/trigger
            if len(topic_parts) == 4 and topic_parts[1] == "automation" and topic_parts[3] == "trigger":
                if payload_str == "PRESS":
                    auto_id = topic_parts[2]
                    self.logger.info("Received Home Assistant trigger for automation ID: %s", auto_id)
                    if self.loop and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(self.automation_manager.trigger_from_ha(auto_id), self.loop)
                return

        except Exception as e:
            self.logger.error("Unhandled error in on_message: %s", e, exc_info=True)

    def _handle_ir_received(self, bridge_name: str, payload: dict):
        if bridge_name in self.bridge_manager.ignored_bridge_ids:
            return

        self._update_last_seen(bridge_name)

        # --- Loopback Test Interception ---
        # Must happen before history tracking so test-mode captures the raw signal.
        if self.state_manager.test_mode and self.state_manager.test_queue:
            self.logger.debug("Received code on bridge '%s' during loopback test.", bridge_name)
            # Filter by RX bridge if set
            if self.state_manager.test_rx_bridge and bridge_name != self.state_manager.test_rx_bridge:
                return
            # Filter by RX channel if set
            if self.state_manager.test_rx_channel and payload.get("receiver_id") != self.state_manager.test_rx_channel:
                return
            if self.loop:
                self.loop.call_soon_threadsafe(self.state_manager.test_queue.put_nowait, payload)
            return  # End processing for this message

        is_ignored = False

        # --- Echo Suppression ---
        # Must run before history tracking so suppressed codes never reach last_received.
        b_settings = self.settings.bridge_settings.get(bridge_name)

        timeout = 0
        smart = True
        ignore_self = True
        ignore_others = False

        if b_settings is not None and b_settings.echo_enabled:
            timeout = b_settings.echo_timeout
            smart = b_settings.echo_smart
            ignore_self = b_settings.echo_ignore_self
            ignore_others = b_settings.echo_ignore_others

        if timeout > 0:
            now = time.time()
            suppression_sec = timeout / 1000.0
            # Filter history to keep it clean and relevant
            self.state_manager.sent_codes_history = [
                (ts, c, t)
                for ts, c, t in self.state_manager.sent_codes_history
                if now - ts < 5.0  # Keep a bit longer than strictly needed
            ]

            for ts, sent_code, sent_targets in self.state_manager.sent_codes_history:
                if now - ts < suppression_sec:
                    is_self = bridge_name in sent_targets or any(t.startswith(f"{bridge_name}:") for t in sent_targets)
                    should_check = (is_self and ignore_self) or (not is_self and ignore_others)

                    if should_check:
                        matched = True if not smart else match_ir_code(sent_code, payload)
                        if matched:
                            self.logger.info(
                                "Ignored echo on '%s' (Source: %s, Smart: %s, Timeout: %dms)",
                                bridge_name,
                                "Self" if is_self else "Other",
                                smart,
                                timeout,
                            )
                            is_ignored = True
                            break

        # --- History Tracking ---
        if bridge_name not in self.bridges:
            self.bridges[bridge_name] = {}

        if "last_received" not in self.bridges[bridge_name]:
            self.bridges[bridge_name]["last_received"] = deque(maxlen=10)

        entry = payload.copy()
        entry["timestamp"] = time.time()
        if is_ignored:
            entry["ignored"] = True

        self.bridges[bridge_name]["last_received"].appendleft(entry)

        self._broadcast_bridges()

        is_learning_target = False
        if self.state_manager.learning_bridges:
            if "any" in self.state_manager.learning_bridges:
                is_learning_target = True
            else:
                for target in self.state_manager.learning_bridges:
                    parts = target.split(":", 1)
                    if parts[0] == bridge_name:
                        if len(parts) == 1 or payload.get("receiver_id") == parts[1]:
                            is_learning_target = True
                            break
        if is_learning_target and not is_ignored:
            self.logger.debug("Received code on bridge '%s' during learning mode.", bridge_name)
            data = payload
            if data.get("protocol") != "raw" and "raw_tolerance" in data:
                del data["raw_tolerance"]

            if self.state_manager.learning_type == "smart":
                if self.loop and self.loop.is_running():
                    self.loop.call_soon_threadsafe(self._handle_smart_data, data, bridge_name)
            else:
                self.logger.info("Learned new (simple) code from '%s': %s", bridge_name, data)
                self.state_manager.last_learned_code = data
                self.state_manager.last_code_bridge = bridge_name
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        broadcast_ws(
                            {
                                "type": "learned_code",
                                "code": data,
                                "bridge": bridge_name,
                            }
                        ),
                        self.loop,
                    )
        elif not is_learning_target:
            received_code = payload
            if received_code.get("protocol") != "raw" and "raw_tolerance" in received_code:
                del received_code["raw_tolerance"]

            match_found = False
            matched_buttons = []
            for dev in self.state_manager.devices:
                # Check if this device allows receiving from this bridge
                if dev.allowed_bridges:
                    allowed = False
                    for ab in dev.allowed_bridges:
                        if ab == "any":
                            allowed = True
                            break
                        parts = ab.split(":", 1)
                        if parts[0] == bridge_name:
                            if len(parts) == 1 or payload.get("receiver_id") == parts[1]:
                                allowed = True
                                break
                    if not allowed:
                        continue

                for btn in dev.buttons:
                    if not btn.code or not match_ir_code(btn.code, received_code):
                        continue

                    match_found = True
                    matched_buttons.append((dev, btn))
                    protocol = received_code.get("protocol", "unknown")
                    rp = received_code.get("payload") or {}
                    code_val = rp.get("data") or rp.get("command") or "N/A"
                    self.logger.info(
                        "Received known code on '%s' matching button '%s/%s' (Proto: %s, Val: %s)",
                        bridge_name,
                        dev.name,
                        btn.name,
                        protocol,
                        code_val,
                    )
                    if self.loop and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            broadcast_ws({"type": "known_code_received", "button_id": btn.id, "ignored": is_ignored}),
                            self.loop,
                        )

                    if not is_ignored:
                        if self.integration:
                            self.integration.publish_button_event(dev, btn, self)

                        if btn.is_input:
                            self.logger.info(
                                "Processing input state for button: %s/%s",
                                dev.name,
                                btn.name,
                            )
                            input_mode = getattr(btn, "input_mode", "momentary")
                            if input_mode == "toggle":
                                current_state = self.state_manager.input_states.get(btn.id, False)
                                new_state = not current_state
                                self.state_manager.input_states[btn.id] = new_state
                                if self.integration:
                                    self.integration.publish_input_state(
                                        dev,
                                        btn,
                                        "ON" if new_state else "OFF",
                                        self,
                                    )
                            else:  # momentary
                                if self.integration:
                                    self.integration.publish_input_state(dev, btn, "ON", self)

            # Trigger automations for matched buttons and notify inactivity triggers
            if match_found and self.loop and not is_ignored:
                matches = [(d.id, b.id) for d, b in matched_buttons]
                self.logger.info("Triggering automations for %d matched button(s).", len(matches))
                asyncio.run_coroutine_threadsafe(
                    self.automation_manager.process_ir_event(matches, self.state_manager, self.send_ir_code),
                    self.loop,
                )
                # Notify device_inactivity triggers about the received activity
                for dev, btn in matched_buttons:
                    asyncio.run_coroutine_threadsafe(
                        self.automation_manager.notify_device_activity(
                            device_id=dev.id,
                            button_id=btn.id,
                            source="received",
                        ),
                        self.loop,
                    )

            if not match_found and not is_ignored:
                self.logger.info(
                    "Received IR code on '%s' that did not match any known buttons: %s",
                    bridge_name,
                    received_code,
                )

    def publish(self, topic: str, payload: str, retain: bool = False):
        if self.client and self.connected:
            self.client.publish(topic, payload, retain=retain)

    def subscribe(self, topic: str):
        if self.client and self.connected:
            self.client.subscribe(topic)

    def unsubscribe(self, topic: str):
        if self.client and self.connected:
            self.client.unsubscribe(topic)

    async def send_command(
        self,
        bridge_id: str,
        command: str,
        payload: dict | None = None,
        timeout: int = 5,
    ) -> dict | None:
        if not self.connected:
            self.logger.warning("Cannot send command, MQTT is not connected.")
            return None

        request_id = str(uuid.uuid4())
        command_payload = {
            "command": command,
            "request_id": request_id,
            **(payload or {}),
        }

        topic = f"ir2mqtt/bridge/{bridge_id}/command"

        event = asyncio.Event()
        self.pending_requests[request_id] = event

        self.logger.info(
            "Sending command '%s' to bridge '%s' (request_id: %s)",
            command,
            bridge_id,
            request_id,
        )
        self.publish(topic, json.dumps(command_payload))

        try:
            await asyncio.wait_for(event.wait(), timeout)
            response = self.pending_responses.get(request_id)
            self.logger.debug("Command response received for %s: %s", request_id, response)
            return response
        except TimeoutError:
            self.logger.error(
                "Timeout waiting for response from bridge '%s' for command '%s'.",
                bridge_id,
                command,
            )
            return None
        finally:
            self.pending_requests.pop(request_id, None)
            self.pending_responses.pop(request_id, None)

    async def send_ir_code(self, code_dict: dict, target: str | list[str] | None = None):
        targets_list = []
        if isinstance(target, str):
            if target != "broadcast":
                targets_list = [target]
        elif isinstance(target, list):
            targets_list = target

        bridge_targets = {}
        if not targets_list and (target == "broadcast" or not target):
            for bid, b in self.bridges.items():
                if b.get("online"):
                    bridge_targets[bid] = None
        else:
            for t in targets_list:
                if ":" in t:
                    b_id, ch = t.split(":", 1)
                    if b_id in self.bridges and self.bridges[b_id].get("online"):
                        if b_id not in bridge_targets:
                            bridge_targets[b_id] = []
                        if bridge_targets[b_id] is not None:
                            bridge_targets[b_id].append(ch)
                else:
                    if t in self.bridges and self.bridges[t].get("online"):
                        bridge_targets[t] = None

        if not bridge_targets:
            self.logger.warning("No target bridge(s) specified or available for sending IR code.")
            return

        code_payload = code_dict.copy()
        if "raw_tolerance" in code_payload:
            del code_payload["raw_tolerance"]

        # Record for echo suppression
        sent_targets = []
        for bid, channels in bridge_targets.items():
            if channels is None:
                sent_targets.append(bid)
            else:
                sent_targets.extend([f"{bid}:{ch}" for ch in channels])
        try:
            code_obj = IRCode(**code_dict)
            self.state_manager.sent_codes_history.append((time.time(), code_obj, sent_targets))
            if len(self.state_manager.sent_codes_history) > 20:
                self.state_manager.sent_codes_history.pop(0)
        except Exception:
            pass

        tasks = []
        history_updated = False
        for bridge_id, channels in bridge_targets.items():
            # --- History Tracking ---
            if bridge_id in self.bridges:
                if "last_sent" not in self.bridges[bridge_id]:
                    self.bridges[bridge_id]["last_sent"] = deque(maxlen=10)

                entry = code_payload.copy()
                entry["timestamp"] = time.time()
                if channels:
                    entry["channel"] = channels if len(channels) > 1 else channels[0]
                self.bridges[bridge_id]["last_sent"].appendleft(entry)
                history_updated = True

            cmd_payload = {"code": code_payload}
            if channels is not None:
                cmd_payload["transmitter_id"] = channels

            tasks.append((bridge_id, self.bridge_manager.send_command(bridge_id, "send", cmd_payload)))

        if history_updated:
            self._broadcast_bridges()

        results = await asyncio.gather(*(t[1] for t in tasks), return_exceptions=True)

        for (bridge_id, _), res in zip(tasks, results):
            if isinstance(res, Exception) or not res or not res.get("success"):
                self.logger.warning("Failed to send IR code to bridge %s", bridge_id)
            else:
                self.logger.debug("IR code successfully sent to bridge %s", bridge_id)

    async def test_connection(self, settings: dict[str, Any]) -> dict[str, Any]:
        future = self.loop.create_future()

        self.logger.info(
            "Testing MQTT connection to %s:%s",
            settings.get("broker"),
            settings.get("port"),
        )

        def on_test_connect(_client, _userdata, _flags, rc, _properties=None):
            if not future.done():
                if rc == 0:
                    self.logger.info("MQTT test connection successful.")
                    future.set_result({"status": "ok", "message": "Connected successfully."})
                else:
                    self.logger.error("MQTT test connection failed with code %s.", rc)
                    future.set_result(
                        {
                            "status": "error",
                            "message": f"Connection failed with code {rc}. Check credentials and broker address.",
                        }
                    )

        client_id = f"ir2mqtt-test-{uuid.uuid4()}"
        self.logger.debug("Using client ID '%s' for test connection.", client_id)
        if CallbackAPIVersion:
            client = mqtt_client.Client(CallbackAPIVersion.VERSION2, client_id)
        else:
            client = mqtt_client.Client(client_id=client_id)
        if settings.get("user"):
            client.username_pw_set(settings["user"], settings["password"])

        client.on_connect = on_test_connect

        try:
            client.connect(settings["broker"], int(settings["port"]), 5)
            client.loop_start()
            try:
                result = await asyncio.wait_for(future, timeout=5.0)
            except TimeoutError:
                self.logger.error("MQTT test connection timed out.")
                result = {"status": "error", "message": "Connection timed out."}
            finally:
                client.loop_stop()
                client.disconnect()
            return result
        except Exception as e:
            self.logger.error("Exception during MQTT test connection: %s", e, exc_info=True)
            return {"status": "error", "message": str(e)}
