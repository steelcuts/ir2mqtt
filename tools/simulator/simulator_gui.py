import json
import os
import sys
import threading

# --- CONSTANTS ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio  # noqa: E402
from datetime import datetime  # noqa: E402
from typing import Any  # noqa: E402

from pydantic import BaseModel  # noqa: E402
from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QBrush, QColor  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStyleFactory,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.models import IRButton, IRDevice  # noqa: E402

# noqa: E402
from tools.simulator.simulator_core import (  # noqa: E402
    ALL_PROTOCOLS,
    CoreMqttClient,
    DeviceController,
    SimulatorEngine,
)
from tools.simulator.utils import PROTOCOL_CONFIG, ProtocolDef, Topics  # noqa: E402

# --- STYLES ---
DARK_STYLESHEET = """
QMainWindow, QWidget { background-color: #2b2b2b; color: #e0e0e0; font-family: system-ui, sans-serif; font-size: 10pt; }
QGroupBox { border: 1px solid #555; border-radius: 5px; margin-top: 10px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; color: #aaa; }
QLineEdit, QSpinBox, QComboBox, QTextEdit, QTableWidget, QTreeWidget, QListWidget {
    background-color: #3c3c3c;
    border: 1px solid #555;
    border-radius: 3px;
    color: #fff;
    padding: 4px;
}
QHeaderView::section { background-color: #444; padding: 4px; border: 1px solid #555; }
QPushButton { background-color: #0d6efd; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
QPushButton:hover { background-color: #0b5ed7; }
QPushButton:pressed { background-color: #0a58ca; }
QPushButton:disabled { background-color: #555; color: #888; }
QTabWidget::pane { border: 1px solid #555; }
QTabBar::tab { background: #3c3c3c; border: 1px solid #555; padding: 8px 12px; margin-right: 2px; color: #aaa; }
QTabBar::tab:selected { background: #4c4c4c; color: #fff; border-bottom: 2px solid #0d6efd; }
QSplitter::handle { background-color: #555; }
QTableWidget::item { padding: 2px; }
"""


# --- DATA-DRIVEN CONFIGS ---
class LogEntry(BaseModel):
    time: str
    source: str
    topic: str
    payload: str
    level: str
    retained: bool


class DragDropPayload(BaseModel):
    type: str
    dev: IRDevice
    btn: IRButton


LOG_COLOR_MAP = [
    (lambda d: d.level == "ERROR", "#ff6b6b"),
    (lambda d: d.level == "WARN", "#ffd93d"),
    (lambda d: "Backend -> Bridge" in d.source, "#4dabf7"),
    (lambda d: "Bridge -> Backend" in d.source, "#ff922b"),
    (lambda d: "HA -> Backend" in d.source, "#69db7c"),
    (lambda d: "discovery" in d.topic or "/config" in d.topic, "#da77f2"),
    (lambda d: "automation" in d.topic, "#f06595"),
    (lambda d: "devices" in d.topic, "#20c997"),
]


# --- SIGNALS ---
class MqttSignals(QObject):
    message_received = pyqtSignal(str, str, bool)
    log = pyqtSignal(str, str, str)  # source, message, level
    connection_changed = pyqtSignal(bool, str)  # status, error_msg
    bridges_updated = pyqtSignal()


# --- WIDGETS ---
class LogViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.logs: list[LogEntry] = []

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter logs...")
        self.filter_input.textChanged.connect(self.apply_filter)
        self.pause_chk = QCheckBox("Pause")
        self.save_btn = QPushButton("Save Logs")
        self.save_btn.clicked.connect(self.save_logs)
        self.save_btn.setStyleSheet("background-color: #198754; color: white;")
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_logs)
        self.clear_btn.setStyleSheet("background-color: #555; color: white;")

        controls.addWidget(QLabel("Search:"))
        controls.addWidget(self.filter_input)
        controls.addWidget(self.pause_chk)
        controls.addWidget(self.save_btn)
        controls.addWidget(self.clear_btn)
        layout.addLayout(controls)

        # Legend
        legend_layout = QHBoxLayout()
        legend_items = {
            "Error": "#ff6b6b",
            "Warn": "#ffd93d",
            "Backend->Bridge": "#4dabf7",
            "Bridge->Backend": "#ff922b",
            "HA->Backend": "#69db7c",
            "Discovery": "#da77f2",
            "Automations": "#f06595",
            "Devices": "#20c997",
        }
        for name, color in legend_items.items():
            lbl = QLabel(name)
            lbl.setStyleSheet(f"color: {color}; font-weight: bold; margin-right: 8px; font-size: 9pt;")
            legend_layout.addWidget(lbl)
        legend_layout.addStretch()
        layout.addLayout(legend_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Time", "Source", "Topic", "Payload"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(2, 250)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("alternate-background-color: #333;")
        layout.addWidget(self.table)

    def add_log(self, source: str, topic: str, payload: str, level: str = "INFO", retained: bool = False):
        if self.pause_chk.isChecked():
            return
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        entry = LogEntry(time=timestamp, source=source, topic=topic, payload=payload, level=level, retained=retained)
        self.logs.append(entry)
        if len(self.logs) > 1000:
            self.logs.pop(0)
        if self.matches_filter(entry):
            self.insert_row(entry)

    def insert_row(self, entry: LogEntry):
        row = self.table.rowCount()
        self.table.insertRow(row)
        topic_display = entry.topic + (" [R]" if entry.retained else "")
        items = [QTableWidgetItem(entry.time), QTableWidgetItem(entry.source), QTableWidgetItem(topic_display), QTableWidgetItem(entry.payload)]

        color = QColor("#e0e0e0")
        for condition, c in LOG_COLOR_MAP:
            if condition(entry):
                color = QColor(c)
                break

        for i, item in enumerate(items):
            item.setForeground(QBrush(color))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, i, item)
        self.table.scrollToBottom()

    def matches_filter(self, entry: LogEntry) -> bool:
        q = self.filter_input.text().lower()
        return not q or q in entry.topic.lower() or q in entry.payload.lower() or q in entry.source.lower()

    def apply_filter(self):
        self.table.setRowCount(0)
        for log in self.logs:
            if self.matches_filter(log):
                self.insert_row(log)

    def clear_logs(self):
        self.logs.clear()
        self.table.setRowCount(0)

    def save_logs(self):
        if not self.logs:
            return
        fname, _ = QFileDialog.getSaveFileName(self, "Save Logs", "ir2mqtt_logs.txt", "Text Files (*.txt);;All Files (*)")
        if fname:
            with open(fname, "w") as f:
                for log in self.logs:
                    f.write(f"[{log.time}] [{log.level}] [{log.source}] {log.topic} {log.payload}{' [R]' if log.retained else ''}\n")


class DraggableTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def mimeData(self, items):
        mime = super().mimeData(items)
        if items and (data := items[0].data(0, Qt.ItemDataRole.UserRole)) and data.get("type") == "button":
            payload = DragDropPayload(type="button", dev=data["dev"], btn=data["btn"])
            mime.setData("application/x-ir-button", payload.model_dump_json().encode("utf-8"))
        return mime


class SequenceListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-ir-button"):
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-ir-button"):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-ir-button"):
            try:
                json_data = event.mimeData().data("application/x-ir-button").data().decode("utf-8")
                payload = DragDropPayload.model_validate_json(json_data)
                if payload.btn.code:
                    item = QListWidgetItem(f"Signal: {payload.dev.name} - {payload.btn.name}")
                    item.setData(Qt.ItemDataRole.UserRole, {"type": "signal", "payload": payload.btn.code.model_dump(exclude_none=True)})
                    self.addItem(item)
                    event.accept()
            except Exception as e:
                # Log error for easier debugging
                print(f"Error during drop event: {e}")
                event.ignore()
        else:
            event.ignore()


class DataLoaderThread(QThread):
    """Background thread to load data from SQLite without freezing the GUI."""

    finished_loading = pyqtSignal(int, int)  # num_devices, num_automations
    error_occurred = pyqtSignal(str)

    def __init__(self, controller: DeviceController, folder: str):
        super().__init__()
        self.controller = controller
        self.folder = folder

    def run(self):
        try:
            asyncio.run(self.controller.load_data(self.folder))
            self.finished_loading.emit(len(self.controller.devices), len(self.controller.automations))
        except Exception as e:
            self.error_occurred.emit(str(e))


class LoopbackMatrixDialog(QDialog):
    """
    Zeigt eine Matrix aller TX-Kanäle (Zeilen) × RX-Kanäle (Spalten) aller Bridges.
    Jede Checkbox aktiviert eine Loopback-Route TX → RX.
    """

    def __init__(self, engine: SimulatorEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle("Loopback Matrix – TX → RX Routing")
        self.setMinimumSize(600, 400)
        self.setStyleSheet(DARK_STYLESHEET)
        self._build_ui()

    def _collect_channels(self):
        tx_channels: list[tuple[str, str]] = []  # [(bridge_id, tx_id), ...]
        rx_channels: list[tuple[str, str]] = []  # [(bridge_id, rx_id), ...]
        for bridge in self.engine.bridges:
            for t in bridge.transmitters:
                tx_channels.append((bridge.id, t.id))
            for r in bridge.receivers:
                rx_channels.append((bridge.id, r.id))
        return tx_channels, rx_channels

    def _build_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel("""Check boxes to route a TX channel's signal into an RX channel (simulates physical placement).\n
                      Global loopback checkbox also echoes sends back – this matrix adds fine-grained cross-channel routing.""")
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaa; font-size: 9pt;")
        layout.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        grid_layout = QVBoxLayout(container)

        self.checkboxes: dict[tuple[str, str, str, str], QCheckBox] = {}

        tx_channels, rx_channels = self._collect_channels()

        if not tx_channels or not rx_channels:
            grid_layout.addWidget(QLabel("No bridges with channels available. Spawn some bridges first."))
        else:
            # Build table widget: rows = TX, cols = RX
            table = QTableWidget(len(tx_channels), len(rx_channels))
            table.setStyleSheet("QTableWidget { gridline-color: #444; }")

            # Headers
            h_labels = [f"{bid.split('-')[-1]}\n{rx_id}" for (bid, rx_id) in rx_channels]
            v_labels = [f"{bid.split('-')[-1]} / {tx_id}" for (bid, tx_id) in tx_channels]
            table.setHorizontalHeaderLabels(h_labels)
            table.setVerticalHeaderLabels(v_labels)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

            for row, (tx_bid, tx_id) in enumerate(tx_channels):
                for col, (rx_bid, rx_id) in enumerate(rx_channels):
                    cb = QCheckBox()
                    cb.setChecked(self.engine.get_loopback_route(tx_bid, tx_id, rx_bid, rx_id))
                    # cb.setStyleSheet("margin-left: 4px;")
                    # Highlight same-bridge diagonal in a different colour
                    if tx_bid == rx_bid:
                        cb.setStyleSheet("color: #4dabf7;")
                    self.checkboxes[(tx_bid, tx_id, rx_bid, rx_id)] = cb
                    cell_widget = QWidget()
                    cell_layout = QHBoxLayout(cell_widget)
                    cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    cell_layout.setContentsMargins(0, 0, 0, 0)
                    cell_layout.addWidget(cb)
                    table.setCellWidget(row, col, cell_widget)

            grid_layout.addWidget(table)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self._apply)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _apply(self):
        for (tx_bid, tx_id, rx_bid, rx_id), cb in self.checkboxes.items():
            self.engine.set_loopback_route(tx_bid, tx_id, rx_bid, rx_id, cb.isChecked())
        self.accept()


class BridgeSimulator(QWidget):
    def __init__(self, signals: MqttSignals, engine: SimulatorEngine):
        super().__init__()
        self.signals = signals
        self.engine = engine
        self.init_ui()
        self.signals.bridges_updated.connect(self.refresh_bridge_list)

    def init_ui(self):
        layout = QVBoxLayout(self)
        config_grp = QGroupBox("Bridge Configuration")
        form = QHBoxLayout()
        self.bridge_type_combo = QComboBox()
        self.bridge_type_combo.addItems(["MQTT", "Serial"])
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 10)
        self.count_spin.setValue(1)
        self.rx_spin = QSpinBox()
        self.rx_spin.setRange(1, 8)
        self.rx_spin.setValue(1)
        self.rx_spin.setToolTip("Number of RX (receiver) channels per bridge")
        self.tx_spin = QSpinBox()
        self.tx_spin.setRange(1, 8)
        self.tx_spin.setValue(1)
        self.tx_spin.setToolTip("Number of TX (transmitter) channels per bridge")
        self.create_btn = QPushButton("Spawn Bridges")
        self.create_btn.clicked.connect(self.spawn_bridges)
        self.loopback_chk = QCheckBox("Global Loopback")
        self.loopback_chk.setToolTip("Echo all sent codes back as received (global). Use per-bridge matrix for fine-grained routing.")
        self.loopback_chk.stateChanged.connect(self.toggle_loopback)
        form.addWidget(QLabel("Type:"))
        form.addWidget(self.bridge_type_combo)
        form.addWidget(QLabel("Count:"))
        form.addWidget(self.count_spin)
        form.addWidget(QLabel("RX:"))
        form.addWidget(self.rx_spin)
        form.addWidget(QLabel("TX:"))
        form.addWidget(self.tx_spin)
        form.addWidget(self.create_btn)
        form.addWidget(self.loopback_chk)
        form.addStretch()
        config_grp.setLayout(form)
        layout.addWidget(config_grp)

        self.bridge_list = QTreeWidget()
        self.bridge_list.setHeaderLabels(["Bridge ID", "Type / IP", "Status"])
        self.bridge_list.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bridge_list.currentItemChanged.connect(self.update_protocol_ui)
        self.bridge_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.bridge_list.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.bridge_list)

        btn_layout = QHBoxLayout()
        del_btn = QPushButton("Delete Selected")
        del_btn.setObjectName("delete_bridge_btn")
        del_btn.clicked.connect(self.delete_bridge)
        del_btn.setStyleSheet("background-color: #dc3545; color: white;")
        btn_layout.addWidget(del_btn)

        del_all_btn = QPushButton("Delete All")
        del_all_btn.clicked.connect(self.delete_all_bridges)
        del_all_btn.setStyleSheet("background-color: #b02a37; color: white;")
        btn_layout.addWidget(del_all_btn)

        matrix_btn = QPushButton("Loopback Matrix…")
        matrix_btn.setObjectName("loopback_matrix_btn")
        matrix_btn.setToolTip("Configure per-bridge TX→RX loopback routing")
        matrix_btn.clicked.connect(self.open_loopback_matrix)
        matrix_btn.setStyleSheet("background-color: #198754; color: white;")
        btn_layout.addWidget(matrix_btn)

        layout.addLayout(btn_layout)

        inject_grp = QGroupBox("Inject IR Signal (Simulate Remote)")
        self.inject_layout = QFormLayout()

        self.receiver_combo = QComboBox()
        self.inject_layout.addRow("Receiver:", self.receiver_combo)

        self.proto_combo = QComboBox()
        self.proto_combo.addItems(ALL_PROTOCOLS)
        self.proto_combo.currentTextChanged.connect(self.update_fields)
        self.inject_layout.addRow("Protocol:", self.proto_combo)

        self.inputs = {}
        for key, label in [
            ("address", "Address:"),
            ("command", "Command:"),
            ("data", "Data:"),
            ("nbits", "N-Bits:"),
            ("rc_code_1", "RC Code 1:"),
            ("rc_code_2", "RC Code 2:"),
            ("first", "First:"),
            ("second", "Second:"),
        ]:
            inp = QLineEdit()
            self.inputs[key] = inp
            self.inject_layout.addRow(label, inp)

        btn_layout = QHBoxLayout()
        self.send_btn = QPushButton("Inject Signal")
        self.send_btn.clicked.connect(self.inject_signal)
        self.rand_btn = QPushButton("Random NEC")
        self.rand_btn.clicked.connect(self.inject_random)
        btn_layout.addWidget(self.send_btn)
        btn_layout.addWidget(self.rand_btn)
        self.inject_layout.addRow(btn_layout)
        inject_grp.setLayout(self.inject_layout)
        layout.addWidget(inject_grp)
        self.update_fields(self.proto_combo.currentText())

        test_tx_grp = QGroupBox("Test Transmitter (Simulate Backend)")
        tx_layout = QHBoxLayout()
        self.transmitter_combo = QComboBox()
        self.test_tx_btn = QPushButton("Send Test Command")
        self.test_tx_btn.clicked.connect(self.test_transmitter)
        tx_layout.addWidget(QLabel("Transmitter:"))
        tx_layout.addWidget(self.transmitter_combo)
        tx_layout.addWidget(self.test_tx_btn)
        tx_layout.addStretch()
        test_tx_grp.setLayout(tx_layout)
        layout.addWidget(test_tx_grp)

    def toggle_loopback(self, state):
        self.engine.loopback_enabled = state == Qt.CheckState.Checked.value

    def refresh_bridge_list(self):
        self.bridge_list.clear()
        for bridge in self.engine.bridges:
            # Display bridge type and IP/Port info
            bridge_info = bridge.bridge_type.upper()
            if bridge.bridge_type == "mqtt" and bridge.ip:
                bridge_info += f" ({bridge.ip})"
            elif bridge.bridge_type == "serial" and bridge.port:
                bridge_info += f" ({bridge.port})"

            # Add RX/TX capabilities
            if bridge.capabilities:
                bridge_info += f" [RX:{bridge.rx}, TX:{bridge.tx}]"

            status = "Online" if bridge.online else "Offline"
            item = QTreeWidgetItem([bridge.name, bridge_info, status])
            item.setData(0, Qt.ItemDataRole.UserRole, bridge.id)
            self.bridge_list.addTopLevelItem(item)

    def spawn_bridges(self):
        bridge_type = self.bridge_type_combo.currentText().lower()
        rx = self.rx_spin.value()
        tx = self.tx_spin.value()
        if bridge_type == "mqtt":
            self.engine.spawn_bridges(self.count_spin.value(), rx_count=rx, tx_count=tx)
        elif bridge_type == "serial":
            for _ in range(self.count_spin.value()):
                self.engine.spawn_serial_bridge("auto", rx_count=rx, tx_count=tx)

    def delete_bridge(self):
        if item := self.bridge_list.currentItem():
            self.engine.delete_bridge(item.data(0, Qt.ItemDataRole.UserRole))

    def delete_all_bridges(self):
        reply = QMessageBox.question(
            self, "Delete All", "Are you sure you want to delete ALL bridges?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.engine.delete_all_bridges()

    def open_loopback_matrix(self):
        dlg = LoopbackMatrixDialog(self.engine, parent=self)
        dlg.exec()

    def show_context_menu(self, pos):
        if item := self.bridge_list.itemAt(pos):
            menu = QMenu()
            menu.addAction("Rename Bridge", lambda: self.rename_bridge(item))
            menu.addSeparator()
            menu.addAction("Loopback Matrix…", self.open_loopback_matrix)
            menu.exec(self.bridge_list.viewport().mapToGlobal(pos))

    def rename_bridge(self, item):
        bid = item.data(0, Qt.ItemDataRole.UserRole)
        if bridge := self.engine.get_bridge_by_id(bid):
            new_name, ok = QInputDialog.getText(self, "Rename Bridge", "New Name:", text=bridge.name)
            if ok and new_name:
                self.engine.rename_bridge(bid, new_name)

    def get_selected_bridge_id(self) -> str | None:
        item = self.bridge_list.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else (self.engine.bridges[0].id if self.engine.bridges else None)

    def update_protocol_ui(self):
        bid = self.get_selected_bridge_id()
        if not bid or not (bridge := self.engine.get_bridge_by_id(bid)):
            return

        self.receiver_combo.clear()
        for r in bridge.receivers:
            self.receiver_combo.addItem(r.get("id") if isinstance(r, dict) else r.id)

        self.transmitter_combo.clear()
        for t in bridge.transmitters:
            self.transmitter_combo.addItem(t.get("id") if isinstance(t, dict) else t.id)

        enabled = bridge.enabled_protocols
        for i in range(self.proto_combo.count()):
            if item := self.proto_combo.model().item(i):
                is_en = self.proto_combo.itemText(i) in enabled
                item.setEnabled(is_en)
                font = item.font()
                font.setStrikeOut(not is_en)
                item.setFont(font)
        self.rand_btn.setEnabled("nec" in enabled)

    def test_transmitter(self):
        if not (bid := self.get_selected_bridge_id()):
            QMessageBox.warning(self, "No Bridge", "No bridge selected.")
            return

        tx_id = self.transmitter_combo.currentText()
        if not tx_id:
            return

        payload = {"command": "send", "request_id": "gui-test", "transmitter_id": tx_id, "code": {"protocol": "nec", "payload": {"address": "0x1234", "command": "0x5678"}}}

        bridge = self.engine.get_bridge_by_id(bid)
        if bridge and bridge.bridge_type == "mqtt":
            self.engine.clients[bid].publish(Topics.bridge_command(bid), json.dumps(payload))
        elif bridge and bridge.bridge_type == "serial":
            self.engine._serial_write(bid, payload)

    def update_fields(self, proto: str):
        config = PROTOCOL_CONFIG.get(proto, ProtocolDef(fields=[]))
        visible_keys = set(config.fields)
        for key, widget in self.inputs.items():
            is_visible = key in visible_keys
            self.inject_layout.labelForField(widget).setVisible(is_visible)
            widget.setVisible(is_visible)

    def get_current_payload(self) -> dict[str, Any]:
        proto = self.proto_combo.currentText()
        config = PROTOCOL_CONFIG.get(proto, ProtocolDef(fields=[]))
        inner: dict[str, Any] = {}
        fields = config.fields
        hex_fields = config.hex_fields
        defaults = config.defaults

        def v_hex(k, label):
            v = self.inputs[k].text().strip()
            if not v:
                return "0x0"
            try:
                int(v, 16)
                return f"0x{v.lstrip('0x')}"
            except ValueError:
                raise ValueError(f"{label} for {k} must be a hex value.")

        for key in fields:
            value = self.inputs[key].text().strip() or defaults.get(key)
            if not value:
                raise ValueError(f"Field '{key}' cannot be empty for protocol '{proto}'.")

            if key in hex_fields:
                inner[key] = v_hex(key, self.inject_layout.labelForField(self.inputs[key]).text())
            elif config.is_json:
                try:
                    inner[key] = json.loads(value)
                except json.JSONDecodeError:
                    raise ValueError(f"Field '{key}' must be valid JSON.")
            else:
                inner[key] = value
        return {"protocol": proto, "payload": inner}

    def inject_signal(self) -> bool:
        if not (bid := self.get_selected_bridge_id()):
            QMessageBox.warning(self, "No Bridge", "No bridge selected.")
            return False
        try:
            payload = self.get_current_payload()
            if self.receiver_combo.currentText():
                payload["receiver_id"] = self.receiver_combo.currentText()
            self.engine.inject_signal(bid, payload)
            return True
        except ValueError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
            return False

    def inject_random(self):
        if bid := self.get_selected_bridge_id():
            self.engine.inject_random_nec(bid)


class Controller(QWidget):
    def __init__(self, signals: MqttSignals, engine: SimulatorEngine, device_ctrl: DeviceController):
        super().__init__()
        self.signals = signals
        self.engine = engine
        self.device_ctrl = device_ctrl
        self.init_ui()
        self.signals.bridges_updated.connect(self.refresh_bridges)

    def init_ui(self):
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        load_folder_btn = QPushButton("Load Project Data (data/)")
        load_folder_btn.clicked.connect(self.load_data_folder)
        toolbar.addWidget(load_folder_btn)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("Source Bridge:"))
        self.bridge_combo = QComboBox()
        self.bridge_combo.setMinimumWidth(200)
        toolbar.addWidget(self.bridge_combo)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        dev_grp = QGroupBox("Devices & Buttons")
        dev_layout = QVBoxLayout()
        self.dev_tree = DraggableTreeWidget()
        self.dev_tree.setHeaderLabels(["Name", "Type/Code"])
        self.dev_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.dev_tree.customContextMenuRequested.connect(self.show_context_menu)
        dev_layout.addWidget(self.dev_tree)
        dev_grp.setLayout(dev_layout)
        splitter.addWidget(dev_grp)

        auto_grp = QGroupBox("Automations")
        auto_layout = QVBoxLayout()
        self.auto_tree = QTreeWidget()
        self.auto_tree.setHeaderLabels(["Name", "Trigger"])
        self.auto_tree.itemDoubleClicked.connect(self.trigger_automation)
        self.auto_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.auto_tree.customContextMenuRequested.connect(self.show_auto_context_menu)
        auto_layout.addWidget(self.auto_tree)
        auto_grp.setLayout(auto_layout)
        splitter.addWidget(auto_grp)
        layout.addWidget(splitter)

        seq_grp = QGroupBox("Sequence Builder (Drag buttons from Devices tree)")
        seq_layout = QVBoxLayout()
        self.seq_list = SequenceListWidget()
        seq_layout.addWidget(self.seq_list)
        seq_controls = QHBoxLayout()
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(10, 10000)
        self.delay_spin.setValue(500)
        self.delay_spin.setSuffix(" ms")
        self.add_delay_btn = QPushButton("Add Delay")
        self.add_delay_btn.clicked.connect(self.add_sequence_delay)
        seq_controls.addWidget(QLabel("Delay:"))
        seq_controls.addWidget(self.delay_spin)
        seq_controls.addWidget(self.add_delay_btn)
        seq_controls.addStretch()

        self.run_seq_btn = QPushButton("Run Sequence")
        self.run_seq_btn.clicked.connect(self.run_sequence)
        self.run_seq_btn.setStyleSheet("background-color: #198754; color: white;")
        self.clear_seq_btn = QPushButton("Clear")
        self.clear_seq_btn.clicked.connect(self.seq_list.clear)
        seq_controls.addWidget(self.run_seq_btn)
        seq_controls.addWidget(self.clear_seq_btn)
        seq_layout.addLayout(seq_controls)
        seq_grp.setLayout(seq_layout)
        layout.addWidget(seq_grp)

    def refresh_bridges(self):
        current_id = self.bridge_combo.currentData()
        self.bridge_combo.clear()
        if not self.engine.bridges:
            self.bridge_combo.addItem("No active bridges", None)
            self.bridge_combo.setEnabled(False)
        else:
            self.bridge_combo.setEnabled(True)
            for b in self.engine.bridges:
                self.bridge_combo.addItem(f"{b.name} ({b.id})", b.id)
            if current_id and (idx := self.bridge_combo.findData(current_id)) >= 0:
                self.bridge_combo.setCurrentIndex(idx)

    def load_data_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Data Directory", DATA_DIR)
        if folder:
            try:
                self.start_data_loading(folder)
            except Exception as e:
                self.signals.log.emit("System", f"Failed to load data from DB: {e}", "ERROR")

    def start_data_loading(self, folder):
        self.loader_thread = DataLoaderThread(self.device_ctrl, folder)
        self.loader_thread.finished_loading.connect(self.on_data_loaded)
        self.loader_thread.error_occurred.connect(lambda e: self.signals.log.emit("System", f"Failed to load data: {e}", "ERROR"))
        self.loader_thread.start()

    def on_data_loaded(self, n_dev, n_auto):
        self.populate_trees()
        self.signals.log.emit("System", f"Loaded {n_dev} devices and {n_auto} automations from DB.", "INFO")

    def populate_trees(self):
        self.dev_tree.clear()
        for dev in self.device_ctrl.devices:
            if not dev:
                continue
            root = QTreeWidgetItem([dev.name, "Device"])
            root.setData(0, Qt.ItemDataRole.UserRole, {"type": "device", "data": dev})
            self.dev_tree.addTopLevelItem(root)
            for btn in dev.buttons:
                if not btn or not btn.code:
                    continue
                child = QTreeWidgetItem([btn.name, btn.code.protocol])
                child.setData(0, Qt.ItemDataRole.UserRole, {"type": "button", "dev": dev, "btn": btn})
                root.addChild(child)
        self.dev_tree.expandAll()

        self.auto_tree.clear()
        for auto in self.device_ctrl.automations:
            trigger_info = "None"
            if auto.triggers:
                trigger_info = auto.triggers[0].type
            item = QTreeWidgetItem([auto.name, trigger_info])
            item.setData(0, Qt.ItemDataRole.UserRole, auto)
            self.auto_tree.addTopLevelItem(item)

    def show_context_menu(self, pos):
        if not (item := self.dev_tree.itemAt(pos)) or (data := item.data(0, Qt.ItemDataRole.UserRole))["type"] != "button":
            return
        menu = QMenu()
        menu.addAction("Simulate Physical Remote Press", lambda: self.simulate_physical(data))
        menu.addAction("Send Home Assistant Command", lambda: self.send_ha_cmd(data))
        menu.addAction("Send Standalone Command", lambda: self.send_sa_cmd(data))
        menu.exec(self.dev_tree.viewport().mapToGlobal(pos))

    def show_auto_context_menu(self, pos):
        if not (item := self.auto_tree.itemAt(pos)) or not (auto := item.data(0, Qt.ItemDataRole.UserRole)):
            return
        menu = QMenu()
        menu.addAction("Trigger by ID (HA Mode)", lambda: self.trigger_auto(auto, "id"))
        menu.addAction("Trigger by Name (Standalone)", lambda: self.trigger_auto(auto, "name"))
        menu.exec(self.auto_tree.viewport().mapToGlobal(pos))

    def simulate_physical(self, data):
        bid = self.bridge_combo.currentData()
        btn = data["btn"]
        if bid and btn.code:
            self.engine.inject_signal(bid, btn.code.model_dump(exclude_none=True))

    def send_ha_cmd(self, data):
        if self.engine.main_mqtt_client:
            self.engine.main_mqtt_client.publish(Topics.cmd_ha(data["dev"].id, data["btn"].id), "PRESS")

    def send_sa_cmd(self, data):
        if self.engine.main_mqtt_client:
            self.engine.main_mqtt_client.publish(Topics.cmd_sa(data["dev"].name, data["btn"].name), "PRESS")

    def trigger_automation(self, item, col):
        if auto := item.data(0, Qt.ItemDataRole.UserRole):
            self.trigger_auto(auto, "id")

    def trigger_auto(self, auto, mode):
        if not self.engine.main_mqtt_client:
            return
        topic = Topics.automation_trigger_id(auto.id) if mode == "id" else Topics.automation_trigger_name(auto.name)
        self.engine.main_mqtt_client.publish(topic, "PRESS")

    def add_sequence_delay(self):
        ms = self.delay_spin.value()
        item = QListWidgetItem(f"Delay: {ms} ms")
        item.setData(Qt.ItemDataRole.UserRole, {"type": "delay", "value": ms})
        self.seq_list.addItem(item)

    def run_sequence(self):
        bid = self.bridge_combo.currentData()
        if not bid:
            QMessageBox.warning(self, "No Bridge", "Please select a source bridge.")
            return
        steps = [self.seq_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.seq_list.count())]
        self._run_seq_step(bid, steps, 0)

    def _run_seq_step(self, bid, steps, idx):
        if idx >= len(steps) or not self.engine.get_bridge_by_id(bid):
            return
        step = steps[idx]
        delay = 0
        if step["type"] == "signal":
            self.engine.inject_signal(bid, step["payload"])
        elif step["type"] == "delay":
            delay = step["value"]
        QTimer.singleShot(delay, lambda: self._run_seq_step(bid, steps, idx + 1))


class Tools(QWidget):
    def __init__(self, engine: SimulatorEngine):
        super().__init__()
        self.engine = engine
        self.retained_topics = set()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        grp_manual = QGroupBox("Manual Topic Clear")
        l_manual = QHBoxLayout()
        self.topic_input = QLineEdit()
        self.topic_input.setPlaceholderText("Topic to clear...")
        btn_clear = QPushButton("Clear (Retained)")
        btn_clear.setObjectName("clear_manual_btn")
        btn_clear.clicked.connect(self.clear_manual)
        l_manual.addWidget(self.topic_input)
        l_manual.addWidget(btn_clear)
        grp_manual.setLayout(l_manual)
        layout.addWidget(grp_manual)

        grp_list = QGroupBox("Detected Retained Topics")
        l_list = QVBoxLayout()
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setObjectName("refresh_btn")
        btn_refresh.clicked.connect(self.refresh_retained)
        l_list.addWidget(btn_refresh)
        self.topic_list = QTreeWidget()
        self.topic_list.setHeaderLabels(["Topic", "Payload Preview"])
        self.topic_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        l_list.addWidget(self.topic_list)
        btn_clear_sel = QPushButton("Clear Selected Topics")
        btn_clear_sel.setObjectName("clear_selected_btn")
        btn_clear_sel.clicked.connect(self.clear_selected)
        l_list.addWidget(btn_clear_sel)
        grp_list.setLayout(l_list)
        layout.addWidget(grp_list)

    def handle_message(self, topic, payload, retained):
        if retained and payload and topic not in self.retained_topics:
            self.retained_topics.add(topic)
            self.topic_list.addTopLevelItem(QTreeWidgetItem([topic, payload[:100]]))

    def clear_manual(self):
        if (t := self.topic_input.text().strip()) and self.engine.main_mqtt_client:
            self.engine.main_mqtt_client.publish(t, "", retain=True)

    def clear_selected(self):
        if not self.engine.main_mqtt_client:
            return
        for item in self.topic_list.selectedItems():
            topic = item.text(0)
            self.engine.main_mqtt_client.publish(topic, "", retain=True)
            self.topic_list.takeTopLevelItem(self.topic_list.indexOfTopLevelItem(item))
            self.retained_topics.discard(topic)

    def refresh_retained(self):
        self.topic_list.clear()
        self.retained_topics.clear()
        if self.engine.main_mqtt_client and self.engine.main_mqtt_client.is_connected():
            self.engine.main_mqtt_client.client.unsubscribe("#")
            self.engine.main_mqtt_client.client.subscribe("#")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IR2MQTT Simulator")
        self.resize(1200, 800)
        self.setStyleSheet(DARK_STYLESHEET)
        self.signals = MqttSignals()
        self.device_ctrl = DeviceController(on_log=lambda src, msg, lvl: self.signals.log.emit(src, msg, lvl))
        self.engine = SimulatorEngine(
            broker="localhost",
            port=1883,
            on_log=lambda src, msg, lvl: self.signals.log.emit(src, msg, lvl),
            on_bridges_updated=lambda: self.signals.bridges_updated.emit(),
        )
        self.init_ui()
        self.connect_signals()
        QTimer.singleShot(0, self.auto_load_data)
        QTimer.singleShot(500, self.toggle_connection)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        conn_layout = QHBoxLayout()
        self.broker_input = QLineEdit(os.getenv("MQTT_BROKER", "localhost"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(int(os.getenv("MQTT_PORT", "1883")))
        self.conn_btn = QPushButton("Connect")
        self.status_lbl = QLabel("Disconnected")
        self.status_lbl.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        conn_layout.addWidget(QLabel("Broker:"))
        conn_layout.addWidget(self.broker_input)
        conn_layout.addWidget(QLabel("Port:"))
        conn_layout.addWidget(self.port_input)
        conn_layout.addWidget(self.conn_btn)
        conn_layout.addWidget(self.status_lbl)
        conn_layout.addStretch()
        main_layout.addLayout(conn_layout)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.tabs = QTabWidget()
        self.bridge_sim = BridgeSimulator(self.signals, self.engine)
        self.controller = Controller(self.signals, self.engine, self.device_ctrl)
        self.tools = Tools(self.engine)
        self.tabs.addTab(self.bridge_sim, "Bridge Simulator")
        self.tabs.addTab(self.controller, "Controller / Tester")
        self.tabs.addTab(self.tools, "Tools")
        splitter.addWidget(self.tabs)

        self.logs = LogViewer()
        splitter.addWidget(self.logs)
        splitter.setSizes([500, 300])
        main_layout.addWidget(splitter)

    def connect_signals(self):
        self.conn_btn.clicked.connect(self.toggle_connection)
        self.signals.log.connect(self.logs.add_log)
        self.signals.message_received.connect(self.handle_mqtt_message)
        self.signals.connection_changed.connect(self.update_conn_ui)

    def auto_load_data(self):
        if os.path.exists(DATA_DIR):
            self.controller.start_data_loading(DATA_DIR)

    def toggle_connection(self):
        if self.engine.main_mqtt_client and self.engine.main_mqtt_client.is_connected():
            self.conn_btn.setEnabled(False)
            self.conn_btn.setText("Disconnecting...")
            threading.Thread(target=self._disconnect_worker, daemon=True).start()
        else:
            self.conn_btn.setEnabled(False)
            self.conn_btn.setText("Connecting...")
            broker, port = self.broker_input.text(), self.port_input.value()
            self.engine.broker, self.engine.port = broker, port
            main_client = CoreMqttClient(
                broker=broker,
                port=port,
                on_log=lambda src, msg, lvl: self.signals.log.emit(src, msg, lvl),
                on_message=lambda t, p, r: self.signals.message_received.emit(t, p, r),
                on_connection_change=lambda status, err: self.signals.connection_changed.emit(status, err or ""),
            )
            self.engine.set_main_client(main_client)
            main_client.start()

    def _disconnect_worker(self):
        if self.engine.main_mqtt_client:
            self.engine.main_mqtt_client.stop()
        self.engine.shutdown()
        QTimer.singleShot(0, lambda: self.update_conn_ui(False, ""))

    def update_conn_ui(self, connected: bool, err_msg: str):
        self.conn_btn.setEnabled(True)
        if connected:
            self.conn_btn.setText("Disconnect")
            self.conn_btn.setStyleSheet("background-color: #dc3545;")
            self.status_lbl.setText("Connected")
            self.status_lbl.setStyleSheet("color: #51cf66; font-weight: bold;")
        else:
            self.conn_btn.setText("Connect")
            self.conn_btn.setStyleSheet("background-color: #0d6efd;")
            self.status_lbl.setText("Disconnected")
            self.status_lbl.setStyleSheet("color: #ff6b6b; font-weight: bold;")
            if err_msg:
                QMessageBox.critical(self, "Connection Error", err_msg)

    def handle_mqtt_message(self, topic, payload, retained):
        source = "MQTT"
        if "command" in topic or "send" in topic:
            source = "Backend -> Bridge"
        elif "received" in topic or "response" in topic or "state" in topic:
            source = "Bridge -> Backend"
        elif "cmd" in topic:
            source = "HA -> Backend"

        self.logs.add_log(source, topic, payload, retained=retained)
        self.tools.handle_message(topic, payload, retained)
        self.engine.handle_message(topic, payload)

    def closeEvent(self, event):
        if self.engine.main_mqtt_client:
            self.engine.main_mqtt_client.stop()
        self.engine.shutdown()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())
