import threading
import traceback
import uuid
from collections.abc import Callable

from paho.mqtt import client as mqtt_client


class CoreMqttClient:
    """
    Independent MQTT client that uses callbacks instead of PyQt signals.
    """

    def __init__(
        self,
        broker: str,
        port: int,
        user: str | None = None,
        password: str | None = None,
        will_topic: str | None = None,
        will_payload: str | None = None,
        bid: str | None = None,
        on_log: Callable[[str, str, str], None] | None = None,
        on_message: Callable[[str, str, bool], None] | None = None,
        on_connection_change: Callable[[bool, str | None], None] | None = None,
    ):
        self.broker = broker
        self.port = port
        self.user = user
        self.password = password
        self.bid = bid

        # Callbacks
        self.on_log_cb = on_log or (lambda src, msg, lvl: None)
        self.on_message_cb = on_message or (lambda top, pay, ret: None)
        self.on_connection_change_cb = on_connection_change or (lambda status, err: None)

        self._lock = threading.Lock()
        self.publish_on_connect: list[tuple[str, str, bool]] = []
        self._connected_flag = False

        self.client_id = f"ir2mqtt-sim-bridge-{self.bid}" if self.bid else f"ir2mqtt-sim-main-{uuid.uuid4().hex[:8]}"
        self.client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, self.client_id)

        if will_topic and will_payload:
            self.client.will_set(will_topic, will_payload, retain=True)
            self.on_log_cb("MQTT", f"LWT set for topic: {will_topic}", "DEBUG")

        self.client.on_message = self._on_message
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.on_log_cb("MQTT", f"Connected to {self.broker}:{self.port}", "INFO")
            if not self.bid:
                self.client.subscribe("ir2mqtt/#")
                self.on_connection_change_cb(True, None)

            with self._lock:
                self._connected_flag = True
                try:
                    for topic, payload, retain in self.publish_on_connect:
                        self.publish(topic, payload, retain)
                except Exception as e:
                    self.on_log_cb("MQTT", f"Error publishing queued messages: {e}", "ERROR")
                finally:
                    self.publish_on_connect.clear()
        else:
            self.on_log_cb("MQTT", f"Connection failed for {self.client_id} with code {rc}", "ERROR")
            if not self.bid:
                self.on_connection_change_cb(False, f"Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        self.on_log_cb("MQTT", f"Client {self.client_id} disconnected", "WARN")
        with self._lock:
            self._connected_flag = False
        if not self.bid:
            self.on_connection_change_cb(False, None)

    def _on_message(self, client, userdata, msg):
        payload = "<payload could not be decoded>"
        try:
            payload = msg.payload.decode("utf-8")
            self.on_message_cb(msg.topic, payload, msg.retain)
        except Exception:
            error_message = f"""Error processing MQTT message on topic '{msg.topic}'. Payload: '{payload}'.
{traceback.format_exc()}"""
            self.on_log_cb("MQTT", error_message, "ERROR")

    def start(self):
        try:
            if self.user and self.password:
                self.client.username_pw_set(self.user, self.password)
            self.client.connect_async(self.broker, self.port, 60)
            self.client.loop_start()
        except Exception as e:
            self.on_log_cb("MQTT", f"Connection Error: {e}", "ERROR")
            self.on_connection_change_cb(False, str(e))

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, topic: str, payload: str, retain: bool = False):
        try:
            self.client.publish(topic, payload, retain=retain)
        except Exception as e:
            self.on_log_cb("MQTT", f"Publish failed: {e}", "ERROR")

    def queue_publish(self, topic: str, payload: str, retain: bool = False):
        with self._lock:
            if self._connected_flag:
                self.publish(topic, payload, retain)
            else:
                self.publish_on_connect.append((topic, payload, retain))

    def is_connected(self) -> bool:
        return self.client.is_connected()
