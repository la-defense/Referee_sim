"""模拟器主窗口：连接管理、收发中枢、标签页。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QWidget,
)

from ..core.recorder import Recorder
from ..core.settings import AppSettings, load_settings, save_settings
from ..core.transport import LoopbackTransport, SerialTransport, list_serial_ports
from ..protocol.frame import FrameParser
from .client_tab import ClientTab
from .tabs import MatchTab, ReceiveTab, ReplayTab, SchedulerTab, SendTab


class RxBridge(QObject):
    """把后台读线程收到的字节安全投递到 Qt 主线程。"""

    data_received = Signal(bytes)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RoboMaster 裁判系统模拟器")
        self.resize(1440, 900)

        self.transport = None
        self.parser = FrameParser()
        self.recorder = Recorder()
        self._rx_bridge = RxBridge(self)
        self._rx_bridge.data_received.connect(self._on_rx)
        self.seq = 0
        self.tx_count = 0
        self.rx_count = 0
        self._settings = load_settings()

        self._build_connection_bar()
        self.receive_tab = ReceiveTab()
        self.send_tab = SendTab(self.send_bytes, self.next_seq)
        self.scheduler_tab = SchedulerTab(self.send_bytes, self.next_seq)
        self.match_tab = MatchTab(self.send_bytes, self.next_seq)
        self.replay_tab = ReplayTab(self.recorder, self.send_bytes)
        self.client_tab = ClientTab()

        tabs = QTabWidget()
        tabs.addTab(self.send_tab, "发送")
        tabs.addTab(self.scheduler_tab, "周期发送")
        tabs.addTab(self.match_tab, "比赛流程")
        tabs.addTab(self.receive_tab, "接收/解析")
        tabs.addTab(self.replay_tab, "记录回放")
        tabs.addTab(self.client_tab, "自定义客户端")
        self.setCentralWidget(tabs)

        self.statusBar().addWidget(QLabel("裁判系统模拟器 v0.1"))
        self.tx_label = QLabel("TX: 0")
        self.rx_label = QLabel("RX: 0")
        self.conn_label = QLabel("未连接")
        self.statusBar().addPermanentWidget(self.tx_label)
        self.statusBar().addPermanentWidget(self.rx_label)
        self.statusBar().addPermanentWidget(self.conn_label)
        self._apply_settings()

    def _build_connection_bar(self) -> None:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.addWidget(QLabel("模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["串口", "回环(无硬件)"])
        layout.addWidget(self.mode_combo)
        layout.addWidget(QLabel("端口:"))
        self.port_combo = QComboBox()
        self.refresh_ports()
        layout.addWidget(self.port_combo)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh_ports)
        layout.addWidget(refresh)
        layout.addWidget(QLabel("波特率:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200", "921600", "57600", "460800", "1000000"])
        layout.addWidget(self.baud_combo)
        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self._toggle_connect)
        layout.addWidget(self.connect_btn)
        layout.addStretch(1)
        self.setMenuWidget(bar)

    def refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = list_serial_ports()
        self.port_combo.addItems(ports)
        if not ports:
            self.port_combo.addItem("COM4")
        if current:
            idx = self.port_combo.findText(current)
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)

    def _apply_settings(self) -> None:
        s = self._settings
        if s.mode and self.mode_combo.findText(s.mode) >= 0:
            self.mode_combo.setCurrentText(s.mode)
        if s.port:
            if self.port_combo.findText(s.port) < 0:
                self.port_combo.addItem(s.port)
            self.port_combo.setCurrentText(s.port)
        if s.baud:
            if self.baud_combo.findText(str(s.baud)) < 0:
                self.baud_combo.addItem(str(s.baud))
            self.baud_combo.setCurrentText(str(s.baud))
        if 0 <= s.scenario < self.scheduler_tab.scenario_combo.count():
            self.scheduler_tab.scenario_combo.setCurrentIndex(s.scenario)
        ridx = self.scheduler_tab.robot_combo.findData(s.robot_id)
        if ridx >= 0:
            self.scheduler_tab.robot_combo.setCurrentIndex(ridx)
        ridx = self.match_tab.robot_combo.findData(s.robot_id)
        if ridx >= 0:
            self.match_tab.robot_combo.setCurrentIndex(ridx)
        self.match_tab.match_duration.setValue(s.match_duration)
        self.match_tab.shoot_interval.setValue(s.shoot_interval)
        self.client_tab.host_ed.setText(s.mqtt_host)
        self.client_tab.port_spin.setValue(s.mqtt_port)
        self.client_tab.client_id_ed.setText(s.mqtt_client_id)
        self.replay_tab.rec_path.setText(s.record_path or self.replay_tab.rec_path.text())
        self.replay_tab.rep_path.setText(s.replay_path)
        self.replay_tab.speed_spin.setValue(s.replay_speed)
        if len(s.window) == 4 and min(s.window) >= 0:
            self.setGeometry(*s.window)

    def _collect_settings(self) -> None:
        s = self._settings
        s.mode = self.mode_combo.currentText()
        s.port = self.port_combo.currentText()
        s.baud = int(self.baud_combo.currentText())
        s.scenario = self.scheduler_tab.scenario_combo.currentIndex()
        s.robot_id = self.scheduler_tab.robot_combo.currentData()
        s.match_duration = self.match_tab.match_duration.value()
        s.shoot_interval = self.match_tab.shoot_interval.value()
        s.mqtt_host = self.client_tab.host_ed.text().strip()
        s.mqtt_port = self.client_tab.port_spin.value()
        s.mqtt_client_id = self.client_tab.client_id_ed.text().strip()
        s.record_path = self.replay_tab.rec_path.text()
        s.replay_path = self.replay_tab.rep_path.text()
        s.replay_speed = self.replay_tab.speed_spin.value()
        g = self.geometry()
        s.window = (g.x(), g.y(), g.width(), g.height())

    def next_seq(self) -> int:
        seq = self.seq
        self.seq = (self.seq + 1) & 0xFF
        return seq

    def _toggle_connect(self) -> None:
        if self.transport is not None:
            self._disconnect()
            return
        try:
            if self.mode_combo.currentText() == "串口":
                self.transport = SerialTransport(
                    self.port_combo.currentText(), int(self.baud_combo.currentText()),
                    self._rx_bridge.data_received.emit,
                )
            else:
                self.transport = LoopbackTransport(self._rx_bridge.data_received.emit)
            self.transport.open()
        except Exception as exc:
            self.transport = None
            QMessageBox.critical(self, "连接失败", str(exc))
            return
        self.connect_btn.setText("断开")
        self.mode_combo.setEnabled(False)
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)
        mode = "回环" if isinstance(self.transport, LoopbackTransport) else \
            f"{self.transport.port}@{self.transport.baud}"
        self.conn_label.setText(f"已连接: {mode}")
        self.statusBar().showMessage(f"已连接 {mode}", 3000)

    def _disconnect(self) -> None:
        if self.transport is not None:
            try:
                self.transport.close()
            finally:
                self.transport = None
        self.connect_btn.setText("连接")
        self.mode_combo.setEnabled(True)
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)
        self.conn_label.setText("未连接")

    def send_bytes(self, data: bytes, note: str = "") -> None:
        if self.transport is None or not self.transport.is_open():
            self.statusBar().showMessage("未连接，无法发送", 3000)
            return
        try:
            self.transport.write(data)
        except Exception as exc:
            self.statusBar().showMessage(f"发送失败: {exc}", 5000)
            return
        self.recorder.record("TX", data, {"note": note})
        self.tx_count += 1
        frames = FrameParser().feed(data)
        if frames:
            for f in frames:
                self.receive_tab.add_event("TX", f, note=note)
        else:
            self.receive_tab.add_event("TX", None, raw=data, note=note or "异常帧")
        self._update_counts()

    def _on_rx(self, data: bytes) -> None:
        frames = self.parser.feed(data)
        for f in frames:
            self.recorder.record("RX", f.raw)
            self.receive_tab.add_event("RX", f)
            self.rx_count += 1
        self._update_counts()

    def _update_counts(self) -> None:
        self.tx_label.setText(f"TX: {self.tx_count}")
        self.rx_label.setText(f"RX: {self.rx_count}")

    def closeEvent(self, event) -> None:  # noqa: N802
        self._collect_settings()
        save_settings(self._settings)
        self._disconnect()
        self.recorder.stop()
        super().closeEvent(event)
