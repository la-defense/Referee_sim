"""自定义客户端（MQTT + Protobuf）标签页。"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..client.messages import MESSAGE_TOPICS, topic_schema
from ..client.mqtt_client import MqttClient
from ..client.proto import MessageSchema, decode_message, encode_message


class MqttBridge(QObject):
    message_received = Signal(str, bytes, object)  # topic, payload, schema


def _summary(schema: MessageSchema | None, payload: bytes) -> str:
    if schema is None:
        return f"未知 topic，{len(payload)}B"
    try:
        values = decode_message(schema, payload)
    except Exception:
        return f"解码失败，{len(payload)}B"
    parts = []
    for name, value in list(values.items())[:8]:
        if isinstance(value, list):
            value = f"[{len(value)}]"
        elif isinstance(value, bytes):
            value = value.hex()
        parts.append(f"{name}={value}")
    return ", ".join(parts)


class ProtoForm(QWidget):
    """按 MessageSchema 动态生成发送表单（标量/bytes/string；repeated 用逗号分隔）。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._widgets: dict[str, QWidget] = {}
        self._repeated: dict[str, bool] = {}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

    def set_schema(self, schema: MessageSchema | None) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._widgets.clear()
        self._repeated.clear()
        if schema is None:
            return
        for spec in schema.fields:
            if spec.kind == "message":
                continue
            row = QHBoxLayout()
            label = QLabel(spec.name + ("[]" if spec.repeated else ""))
            label.setMinimumWidth(160)
            row.addWidget(label)
            if spec.kind == "bool":
                w = QCheckBox()
            elif spec.kind == "f32":
                w = QDoubleSpinBox()
                w.setRange(-1e9, 1e9)
                w.setDecimals(3)
            elif spec.kind == "i32":
                w = QSpinBox()
                w.setRange(-0x7FFFFFFF, 0x7FFFFFFF)
            elif spec.kind in ("u32", "u64", "i64"):
                w = QLineEdit("0")
            elif spec.kind == "bytes":
                w = QLineEdit()
                w.setPlaceholderText("十六进制")
            else:  # string
                w = QLineEdit()
            row.addWidget(w, 1)
            self._widgets[spec.name] = w
            self._repeated[spec.name] = spec.repeated
            self._layout.addLayout(row)

    def get_values(self) -> dict:
        values: dict = {}
        for name, w in self._widgets.items():
            repeated = self._repeated[name]
            if isinstance(w, QCheckBox):
                raw = 1 if w.isChecked() else 0
                if repeated:
                    raw = [raw]
            elif isinstance(w, QSpinBox):
                raw = w.value()
                if repeated:
                    raw = [raw]
            elif isinstance(w, QDoubleSpinBox):
                raw = w.value()
                if repeated:
                    raw = [raw]
            else:
                text = w.text().strip()
                if repeated:
                    raw = []
                    for part in text.replace(" ", "").split(","):
                        if part:
                            raw.append(int(part, 0))
                elif name.endswith("_id") or text.isdigit() or text.startswith(("0x", "-")):
                    raw = int(text, 0) if text else 0
                else:
                    try:
                        raw = bytes.fromhex(text)
                    except ValueError:
                        raw = text
            if repeated and not isinstance(raw, list):
                raw = [raw]
            values[name] = raw
        return values


class ClientTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.bridge = MqttBridge(self)
        self.bridge.message_received.connect(self._on_message)
        self._client: MqttClient | None = None
        self._rows: list[tuple[str, bytes, object]] = []

        layout = QVBoxLayout(self)
        conn = QHBoxLayout()
        conn.addWidget(QLabel("服务器:"))
        self.host_ed = QLineEdit("192.168.12.1")
        conn.addWidget(self.host_ed)
        conn.addWidget(QLabel("端口:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(3333)
        conn.addWidget(self.port_spin)
        conn.addWidget(QLabel("客户端ID:"))
        self.client_id_ed = QLineEdit("7")
        self.client_id_ed.setMaximumWidth(80)
        conn.addWidget(self.client_id_ed)
        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self._toggle)
        conn.addWidget(self.connect_btn)
        self.status_label = QLabel("未连接")
        conn.addWidget(self.status_label)
        conn.addStretch(1)
        layout.addLayout(conn)

        pub_box = QGroupBox("发送（自定义客户端 → 服务器）")
        pub = QVBoxLayout(pub_box)
        top = QHBoxLayout()
        top.addWidget(QLabel("指令:"))
        self.topic_combo = QComboBox()
        for name, info in sorted(MESSAGE_TOPICS.items(), key=lambda kv: kv[1].direction):
            if info.direction == "send":
                self.topic_combo.addItem(name, name)
        self.topic_combo.currentIndexChanged.connect(self._on_topic_changed)
        top.addWidget(self.topic_combo, 1)
        self.hex_label = QLabel("")
        top.addWidget(self.hex_label, 1)
        self.publish_btn = QPushButton("发布")
        self.publish_btn.clicked.connect(self._publish)
        top.addWidget(self.publish_btn)
        pub.addLayout(top)
        self.form = ProtoForm()
        pub.addWidget(self.form)
        layout.addWidget(pub_box)

        recv_label = QLabel("接收（服务器 → 自定义客户端，自动订阅全部官方 topic）")
        layout.addWidget(recv_label)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["时间", "Topic", "长度", "解码"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_select)
        layout.addWidget(self.table, 1)
        self.hex_view = QLineEdit()
        self.hex_view.setReadOnly(True)
        layout.addWidget(self.hex_view)
        self._on_topic_changed(0)

    def _toggle(self) -> None:
        if self._client is not None:
            self._client.disconnect()
            self._client = None
            self.connect_btn.setText("连接")
            self.status_label.setText("未连接")
            return
        self._client = MqttClient(
            host=self.host_ed.text().strip() or "127.0.0.1",
            port=self.port_spin.value(),
            client_id=self.client_id_ed.text().strip() or "7",
            on_message=self.bridge.message_received.emit,
            on_connect=self._on_connected,
            on_disconnect=self._on_disconnected,
        )
        try:
            self._client.connect()
        except Exception as exc:
            self.status_label.setText(f"连接失败: {exc}")
            self._client = None
            return
        self.connect_btn.setText("断开")
        self.status_label.setText("连接中…")

    def _on_connected(self) -> None:
        self.status_label.setText("已连接")
        for name in MESSAGE_TOPICS:
            if MESSAGE_TOPICS[name].direction == "recv":
                self._client.subscribe(name)

    def _on_disconnected(self) -> None:
        self.status_label.setText("已断开")
        self.connect_btn.setText("连接")

    def _on_topic_changed(self, _idx: int) -> None:
        topic = self.topic_combo.currentData()
        self.form.set_schema(topic_schema(topic) if topic else None)
        self._refresh_hex()

    def _refresh_hex(self) -> None:
        try:
            payload = encode_message(self.form_schema(), self.form.get_values())
            self.hex_label.setText(payload.hex(" "))
        except Exception as exc:
            self.hex_label.setText(f"编码失败: {exc}")

    def form_schema(self):
        topic = self.topic_combo.currentData()
        return topic_schema(topic) if topic else None

    def _publish(self) -> None:
        if self._client is None or not self._client.connected:
            self.status_label.setText("未连接，无法发布")
            return
        topic = self.topic_combo.currentData()
        try:
            payload = self._client.publish(topic, self.form.get_values())
        except Exception as exc:
            self.status_label.setText(f"发布失败: {exc}")
            return
        self._append(topic, payload, topic_schema(topic), "发送")

    def _on_message(self, topic: str, payload: bytes, schema) -> None:
        self._append(topic, payload, schema, "接收")

    def _append(self, topic: str, payload: bytes, schema, direction: str) -> None:
        self._rows.append((direction, topic, payload, schema))
        row = self.table.rowCount()
        self.table.insertRow(row)
        items = [
            time.strftime("%H:%M:%S"),
            f"{direction} {topic}",
            str(len(payload)),
            _summary(schema, payload),
        ]
        for col, text in enumerate(items):
            self.table.setItem(row, col, QTableWidgetItem(text))
        self.table.scrollToBottom()

    def _on_select(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            self.hex_view.setText(self._rows[row][2].hex(" "))
