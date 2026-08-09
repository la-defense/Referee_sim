"""主标签页：发送、周期发送、接收、记录回放。"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.injector import (
    corrupt_crc8,
    corrupt_crc16,
    flood_prefix,
    oversize_length,
    rebuild_seq,
    truncate_frame,
    zero_length,
)
from ..core.recorder import Recorder, iter_replay
from ..core.scheduler import SchedEntry, Scheduler
from ..core.match_flow import MatchConfig, MatchFlow, PHASE_NAMES
from ..protocol.frame import FrameParser
from ..protocol.commands import COMMANDS, CommandSpec, decode_command, default_values, encode_command
from ..protocol.frame import ParsedFrame, build_frame
from ..protocol.ui_graphics import (
    COLORS,
    FIGURE_TYPES,
    OPERATE_TYPES,
    Figure,
    build_figures_content,
    decode_interactive_content,
)
from .canvas import RefereeCanvas
from .field_editor import FieldEditor


def _fmt_time(t: float | None = None) -> str:
    return time.strftime("%H:%M:%S", time.localtime(t or time.time())) + \
        f".{(t or time.time()) % 1:.3f}"[1:]


def _summary(spec: CommandSpec | None, cmd_id: int, data: bytes) -> str:
    if spec is None:
        return f"未知命令 0x{cmd_id:04X}, {len(data)}B"
    try:
        v = decode_command(spec, data)
    except Exception:
        return f"{spec.name}, {len(data)}B"
    if cmd_id == 0x0001:
        return f"阶段={v.get('game_progress')} 剩余={v.get('stage_remain_time')}s"
    if cmd_id == 0x0003:
        return f"己方HP={v.get('ally_1_robot_hp')}/{v.get('ally_2_robot_hp')}/{v.get('ally_3_robot_hp')}/{v.get('ally_4_robot_hp')}"
    if cmd_id == 0x0201:
        return f"ID={v.get('robot_id')} HP={v.get('current_hp')}/{v.get('maximum_hp')} 功率限={v.get('chassis_power_limit')}W 初速={v.get('bullet_speed_limit')}"
    if cmd_id == 0x0202:
        return f"缓冲={v.get('buffer_energy')}J 17mm热={v.get('shooter_17mm_barrel_heat')}"
    if cmd_id == 0x0207:
        return f"弹丸={v.get('bullet_type')} 射速={v.get('launching_frequency')}Hz 初速={v.get('initial_speed')}m/s"
    if cmd_id == 0x0301 and len(data) >= 6:
        sub = int.from_bytes(data[:2], "little")
        return f"子内容=0x{sub:04X} 发送={int.from_bytes(data[2:4], 'little')} 接收={int.from_bytes(data[4:6], 'little')}"
    return f"{spec.name}, {len(data)}B"


class SendTab(QWidget):
    """单帧编辑与发送。"""

    def __init__(self, send_cb: Callable[[bytes, str], None], next_seq: Callable[[], int],
                 parent=None) -> None:
        super().__init__(parent)
        self._send_cb = send_cb
        self._next_seq = next_seq
        self._custom_spec: CommandSpec | None = None
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("命令:"))
        self.cmd_combo = QComboBox()
        for spec in COMMANDS.values():
            self.cmd_combo.addItem(spec.label, spec.cmd_id)
        self.cmd_combo.addItem("自定义 (raw)", None)
        self.cmd_combo.currentIndexChanged.connect(self._on_cmd_changed)
        top.addWidget(self.cmd_combo, 1)
        self.info_label = QLabel("")
        top.addWidget(self.info_label)
        layout.addLayout(top)

        self.editor = FieldEditor()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor)
        layout.addWidget(scroll, 3)

        self.raw_widget = QWidget()
        raw_layout = QHBoxLayout(self.raw_widget)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.addWidget(QLabel("命令码:"))
        self.raw_cmd_spin = QSpinBox()
        self.raw_cmd_spin.setRange(0, 0xFFFF)
        self.raw_cmd_spin.setDisplayIntegerBase(16)
        self.raw_cmd_spin.setPrefix("0x")
        self.raw_cmd_spin.setValue(0x0201)
        raw_layout.addWidget(self.raw_cmd_spin)
        raw_layout.addWidget(QLabel("数据(hex):"))
        self.raw_data_ed = QLineEdit()
        self.raw_data_ed.setPlaceholderText("例如 07010000000000000000000000000000")
        raw_layout.addWidget(self.raw_data_ed, 1)
        layout.addWidget(self.raw_widget)

        self.composer = FigureComposer()
        self.composer.content_ready.connect(self.editor.set_content_hex)
        layout.addWidget(self.composer)

        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("帧预览:"))
        self.preview = QLineEdit()
        self.preview.setReadOnly(True)
        preview_row.addWidget(self.preview, 1)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self._refresh_preview)
        preview_row.addWidget(self.refresh_btn)
        layout.addLayout(preview_row)

        inj = QGroupBox("错误注入")
        inj_layout = QHBoxLayout(inj)
        self.ck_crc8 = QCheckBox("坏CRC8")
        self.ck_crc16 = QCheckBox("坏CRC16")
        self.ck_zero = QCheckBox("data_length=0")
        self.ck_oversize = QCheckBox("data_length=0xFFFF")
        self.ck_flood = QCheckBox("0xA5洪泛前缀")
        self.ck_trunc = QCheckBox("半帧截断")
        for ck in (self.ck_crc8, self.ck_crc16, self.ck_zero, self.ck_oversize,
                   self.ck_flood, self.ck_trunc):
            inj_layout.addWidget(ck)
        inj_layout.addStretch(1)
        layout.addWidget(inj)

        send_row = QHBoxLayout()
        send_row.addWidget(QLabel("序号:"))
        self.seq_spin = QSpinBox()
        self.seq_spin.setRange(0, 255)
        self.ck_auto_seq = QCheckBox("自动递增")
        self.ck_auto_seq.setChecked(True)
        send_row.addWidget(self.seq_spin)
        send_row.addWidget(self.ck_auto_seq)
        for text, n in (("发送 1 次", 1), ("发送 5 次", 5), ("发送 50 次", 50)):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _=False, count=n: self._send(count))
            send_row.addWidget(btn)
        send_row.addStretch(1)
        layout.addLayout(send_row)

        self.log = QTableWidget(0, 5)
        self.log.setHorizontalHeaderLabels(["时间", "命令", "序号", "长度", "说明"])
        self.log.horizontalHeader().setStretchLastSection(True)
        self.log.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.log, 2)

        self._on_cmd_changed(0)

    def _on_cmd_changed(self, _idx: int) -> None:
        cmd_id = self.cmd_combo.currentData()
        if cmd_id is None:
            self.editor.set_spec(None)
            self.raw_widget.show()
            self.composer.hide()
            self.info_label.setText("任意命令码 + 十六进制数据")
        else:
            spec = COMMANDS[cmd_id]
            self.editor.set_spec(spec)
            self.raw_widget.hide()
            self.composer.setVisible(cmd_id == 0x0301)
            freq = f"{spec.freq} Hz" if spec.freq else "触发式"
            self.info_label.setText(f"{spec.length}B · {freq} · {spec.direction} · {spec.note}")
        self._refresh_preview()

    def _build_frame(self, seq: int) -> tuple[bytes, str]:
        cmd_id = self.cmd_combo.currentData()
        if cmd_id is None:
            try:
                data = bytes.fromhex(self.raw_data_ed.text().replace(" ", ""))
            except ValueError as exc:
                raise ValueError(f"数据不是合法十六进制: {exc}") from exc
            frame = build_frame(self.raw_cmd_spin.value(), data, seq)
            note = ""
            if self.ck_crc8.isChecked():
                frame = corrupt_crc8(frame)
                note += "坏CRC8 "
            if self.ck_crc16.isChecked():
                frame = corrupt_crc16(frame)
                note += "坏CRC16 "
            if self.ck_zero.isChecked():
                frame = zero_length(frame)
                note += "短帧 "
            if self.ck_oversize.isChecked():
                frame = oversize_length(frame)
                note += "超大长度 "
            if self.ck_flood.isChecked():
                frame = flood_prefix(frame)
                note += "洪泛 "
            if self.ck_trunc.isChecked():
                frame = truncate_frame(frame)
                note += "半帧 "
            return frame, note.strip()
        spec = COMMANDS[cmd_id]
        values = self.editor.get_values()
        data = encode_command(spec, values)
        frame = build_frame(cmd_id, data, seq)
        note = ""
        if self.ck_crc8.isChecked():
            frame = corrupt_crc8(frame)
            note += "坏CRC8 "
        if self.ck_crc16.isChecked():
            frame = corrupt_crc16(frame)
            note += "坏CRC16 "
        if self.ck_zero.isChecked():
            frame = zero_length(frame)
            note += "短帧 "
        if self.ck_oversize.isChecked():
            frame = oversize_length(frame)
            note += "超大长度 "
        if self.ck_flood.isChecked():
            frame = flood_prefix(frame)
            note += "洪泛 "
        if self.ck_trunc.isChecked():
            frame = truncate_frame(frame)
            note += "半帧 "
        return frame, note.strip()

    def _refresh_preview(self) -> None:
        try:
            frame, _ = self._build_frame(self.seq_spin.value())
            self.preview.setText(frame.hex(" "))
        except Exception as exc:
            self.preview.setText(f"构建失败: {exc}")

    def _send(self, count: int) -> None:
        for _ in range(count):
            seq = self._next_seq() if self.ck_auto_seq.isChecked() else self.seq_spin.value()
            try:
                frame, note = self._build_frame(seq)
            except Exception as exc:
                self._append_log("—", "—", "—", f"错误: {exc}")
                return
            self._send_cb(frame, note or "正常")
            cmd_id = self.cmd_combo.currentData()
            cmd_text = f"0x{cmd_id:04X}" if cmd_id is not None else \
                f"0x{self.raw_cmd_spin.value():04X} raw"
            self._append_log(cmd_text, str(seq), str(len(frame)), note or "正常")
            if self.ck_auto_seq.isChecked():
                self.seq_spin.setValue(seq)

    def _append_log(self, cmd: str, seq: str, length: str, note: str) -> None:
        row = self.log.rowCount()
        self.log.insertRow(row)
        for col, text in enumerate((_fmt_time(), cmd, seq, length, note)):
            self.log.setItem(row, col, QTableWidgetItem(text))
        self.log.scrollToBottom()


class FigureComposer(QWidget):
    """0x0301 UI 图形快捷编辑器。"""

    content_ready = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        box = QGroupBox("UI 图形编辑器（0x0301 内容）")
        layout = QVBoxLayout(self)
        layout.addWidget(box)
        form = QFormLayout(box)

        self.name_ed = QLineEdit("ss0")
        self.name_ed.setMaxLength(3)
        self.op_combo = QComboBox()
        for k, v in OPERATE_TYPES.items():
            self.op_combo.addItem(v, k)
        self.op_combo.setCurrentIndex(1)
        self.type_combo = QComboBox()
        for k, v in FIGURE_TYPES.items():
            self.type_combo.addItem(v, k)
        self.layer_spin = QSpinBox()
        self.layer_spin.setRange(0, 9)
        self.color_combo = QComboBox()
        for k, v in COLORS.items():
            self.color_combo.addItem(v, k)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 1023)
        self.width_spin.setValue(3)
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 2047)
        self.x_spin.setValue(100)
        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, 2047)
        self.y_spin.setValue(900)
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(0, 1023)
        self.radius_spin.setValue(50)
        self.endx_spin = QSpinBox()
        self.endx_spin.setRange(0, 2047)
        self.endx_spin.setValue(300)
        self.endy_spin = QSpinBox()
        self.endy_spin.setRange(0, 2047)
        self.endy_spin.setValue(900)
        self.angle1_spin = QSpinBox()
        self.angle1_spin.setRange(0, 359)
        self.angle2_spin = QSpinBox()
        self.angle2_spin.setRange(0, 359)
        self.angle2_spin.setValue(90)
        self.font_spin = QSpinBox()
        self.font_spin.setRange(1, 255)
        self.font_spin.setValue(15)
        self.value_spin = QSpinBox()
        self.value_spin.setRange(-0x7FFFFFFF, 0x7FFFFFFF)
        self.value_spin.setValue(1234)
        self.text_ed = QLineEdit("chassis:")

        for label, w in (
            ("图形名(3字符)", self.name_ed), ("操作", self.op_combo),
            ("图形类型", self.type_combo), ("图层", self.layer_spin),
            ("颜色", self.color_combo), ("线宽", self.width_spin),
            ("起点/圆心 X", self.x_spin), ("起点/圆心 Y", self.y_spin),
            ("半径", self.radius_spin), ("终点/对角 X", self.endx_spin),
            ("终点/对角 Y", self.endy_spin), ("起始角度", self.angle1_spin),
            ("终止角度", self.angle2_spin), ("字号", self.font_spin),
            ("数值(浮点/整型)", self.value_spin), ("字符内容", self.text_ed),
        ):
            form.addRow(label, w)
        self.type_combo.currentIndexChanged.connect(self._sync_fields)

        btns = QHBoxLayout()
        gen = QPushButton("生成内容字节")
        gen.clicked.connect(self._generate)
        btns.addWidget(gen)
        self.hex_label = QLabel("")
        self.hex_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btns.addWidget(self.hex_label, 1)
        layout.addLayout(btns)
        self._sync_fields()

    def _sync_fields(self) -> None:
        # 各图形类型共用全部控件，未使用的字段不参与编码
        pass

    def _generate(self) -> None:
        t = self.type_combo.currentData()
        fig = Figure(
            name=self.name_ed.text().encode("utf-8")[:3],
            operate=self.op_combo.currentData(),
            figure_type=t,
            layer=self.layer_spin.value(),
            color=self.color_combo.currentData(),
            width=self.width_spin.value(),
            start_x=self.x_spin.value(),
            start_y=self.y_spin.value(),
            details_a=self.font_spin.value() if t in (5, 6, 7) else
                      (self.angle1_spin.value() if t == 4 else 0),
            details_b=len(self.text_ed.text().encode("utf-8")) if t == 7 else
                      (self.angle2_spin.value() if t == 4 else 0),
            details_c=self.value_spin.value() & 0x3FF if t in (5, 6) else
                      (self.radius_spin.value() if t == 2 else 0),
            details_d=(self.value_spin.value() >> 10) & 0x7FF if t in (5, 6) else
                      (self.endx_spin.value() if t in (0, 1, 3, 4) else 0),
            details_e=(self.value_spin.value() >> 21) & 0x7FF if t in (5, 6) else
                      (self.endy_spin.value() if t in (0, 1, 3, 4) else 0),
        )
        sub_id = 0x0110 if t == 7 else 0x0101
        content = build_figures_content(sub_id, [fig],
                                        char_data=self.text_ed.text() if t == 7 else None)
        hex_text = content.hex(" ")
        self.hex_label.setText(hex_text)
        self.content_ready.emit(hex_text.replace(" ", ""))


class SchedulerTab(QWidget):
    """按官方频率周期发送。"""

    def __init__(self, send_cb: Callable[[bytes, str], None], next_seq: Callable[[], int],
                 parent=None) -> None:
        super().__init__(parent)
        self._send_cb = send_cb
        self._next_seq = next_seq
        self._running = False
        self._last_tick = time.monotonic()
        self._scheduler = Scheduler()
        self._counts: dict[int, int] = {}
        self._stage_remain = 300.0
        self._state = {"game_type": 1, "game_progress": 4, "robot_id": 7}

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("场景:"))
        self.scenario_combo = QComboBox()
        for name in ("未开始", "准备阶段", "十五秒自检", "五秒倒计时", "比赛中", "比赛结束"):
            self.scenario_combo.addItem(name)
        self.scenario_combo.currentIndexChanged.connect(self._apply_scenario)
        top.addWidget(self.scenario_combo)
        top.addWidget(QLabel("机器人ID:"))
        self.robot_combo = QComboBox()
        for rid, label in ((1, "红英雄"), (2, "红工程"), (3, "红步兵3"), (4, "红步兵4"),
                           (5, "红步兵5"), (6, "红空中"), (7, "红哨兵"), (9, "红雷达"),
                           (101, "蓝英雄"), (102, "蓝工程"), (103, "蓝步兵3"), (104, "蓝步兵4"),
                           (105, "蓝步兵5"), (106, "蓝空中"), (107, "蓝哨兵"), (109, "蓝雷达")):
            self.robot_combo.addItem(label, rid)
        self.robot_combo.setCurrentIndex(6)
        top.addWidget(self.robot_combo)
        self.start_btn = QPushButton("启动")
        self.start_btn.clicked.connect(self._toggle)
        top.addWidget(self.start_btn)
        self.count_label = QLabel("已发送: 0")
        top.addWidget(self.count_label)
        top.addStretch(1)
        layout.addLayout(top)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["启用", "命令", "频率(Hz)", "已发送"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        self._build_table()

        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._tick)
        self._apply_scenario(4)

    def _build_table(self) -> None:
        order = sorted(
            (s for s in COMMANDS.values() if s.freq and s.direction in ("down", "both")),
            key=lambda s: s.cmd_id,
        )
        self.table.setRowCount(len(order))
        self._rows: dict[int, int] = {}
        for row, spec in enumerate(order):
            self._rows[spec.cmd_id] = row
            ck = QCheckBox()
            ck.setChecked(spec.cmd_id not in (0x0301, 0x0302, 0x0303, 0x0306, 0x0311))
            ck.stateChanged.connect(lambda _=False, c=spec.cmd_id: self._set_enabled(c))
            self.table.setCellWidget(row, 0, ck)
            self.table.setItem(row, 1, QTableWidgetItem(spec.label))
            freq = QDoubleSpinBox()
            freq.setRange(0.1, 1000.0)
            freq.setDecimals(1)
            freq.setValue(spec.freq or 1.0)
            freq.valueChanged.connect(lambda v, c=spec.cmd_id: self._set_freq(c, v))
            self.table.setCellWidget(row, 2, freq)
            self.table.setItem(row, 3, QTableWidgetItem("0"))
            entry = SchedEntry(spec.cmd_id, 1.0 / (spec.freq or 1.0), self._builder(spec))
            self._scheduler.add(entry)

    def _set_enabled(self, cmd_id: int) -> None:
        row = self._rows[cmd_id]
        ck = self.table.cellWidget(row, 0)
        self._scheduler.entries[cmd_id].enabled = ck.isChecked()

    def _set_freq(self, cmd_id: int, value: float) -> None:
        self._scheduler.entries[cmd_id].interval = 1.0 / value

    def _builder(self, spec: CommandSpec):
        def build() -> bytes:
            values = default_values(spec)
            if spec.cmd_id == 0x0001:
                values["game_type"] = self._state["game_type"]
                values["game_progress"] = self._state["game_progress"]
                values["stage_remain_time"] = max(0, int(self._stage_remain + 0.999))
            elif spec.cmd_id == 0x0201:
                values["robot_id"] = self._state["robot_id"]
            data = encode_command(spec, values)
            return build_frame(spec.cmd_id, data, self._next_seq())
        return build

    def _apply_scenario(self, idx: int) -> None:
        scenarios = {
            0: (0, 0.0),
            1: (1, 300.0),
            2: (2, 15.0),
            3: (3, 5.0),
            4: (4, 300.0),
            5: (5, 0.0),
        }
        progress, remain = scenarios[idx]
        self._state["game_progress"] = progress
        self._stage_remain = remain
        for cmd_id, entry in self._scheduler.entries.items():
            row = self._rows[cmd_id]
            if idx == 0:
                enable = cmd_id == 0x0001
            elif idx in (1, 2, 3):
                enable = cmd_id in (0x0001, 0x0201, 0x0202, 0x0203, 0x0204)
            elif idx == 4:
                enable = cmd_id not in (0x0301, 0x0302, 0x0303, 0x0306, 0x0311)
            else:  # 比赛结束：停周期帧，发一次 0x0002
                enable = False
            entry.enabled = enable
            self.table.cellWidget(row, 0).setChecked(enable)
        if idx == 5:
            self._send_cb(build_frame(0x0002, bytes([1]), self._next_seq()), "比赛结束")

    def _toggle(self) -> None:
        self._running = not self._running
        self.start_btn.setText("停止" if self._running else "启动")
        if self._running:
            self._last_tick = time.monotonic()
            self.timer.start()
        else:
            self.timer.stop()

    def _tick(self) -> None:
        now = time.monotonic()
        delta = now - self._last_tick
        self._last_tick = now
        if self._state["game_progress"] in (3, 4) and self._stage_remain > 0:
            self._stage_remain = max(0.0, self._stage_remain - delta)
        for frame in self._scheduler.tick(now):
            self._send_cb(frame, "周期")
            cmd_id = int.from_bytes(frame[5:7], "little")
            self._counts[cmd_id] = self._counts.get(cmd_id, 0) + 1
            row = self._rows.get(cmd_id)
            if row is not None:
                self.table.item(row, 3).setText(str(self._counts[cmd_id]))
        total = sum(self._counts.values())
        self.count_label.setText(f"已发送: {total}")


class ReceiveTab(QWidget):
    """接收/上行解析、UI 图形可视化。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.show_tx = QCheckBox("显示发送帧")
        self.show_tx.setChecked(True)
        top.addWidget(self.show_tx)
        self.clear_btn = QPushButton("清空")
        self.clear_btn.clicked.connect(self._clear)
        top.addWidget(self.clear_btn)
        top.addStretch(1)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["时间", "方向", "命令", "序号", "长度", "摘要"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_select)
        splitter.addWidget(self.table)

        right = QTabWidget()
        self.decode_table = QTableWidget(0, 3)
        self.decode_table.setHorizontalHeaderLabels(["字段", "值", "说明"])
        self.decode_table.horizontalHeader().setStretchLastSection(True)
        right.addTab(self.decode_table, "字段解码")
        canvas_wrap = QWidget()
        cv = QVBoxLayout(canvas_wrap)
        self.canvas = RefereeCanvas()
        cv.addWidget(self.canvas, 1)
        self.figure_list = QListWidget()
        cv.addWidget(self.figure_list, 1)
        right.addTab(canvas_wrap, "UI 图形")
        self.hex_view = QLineEdit()
        self.hex_view.setReadOnly(True)
        right.addTab(self.hex_view, "原始数据")
        splitter.addWidget(right)
        splitter.setSizes([900, 700])
        layout.addWidget(splitter, 1)

        self._frames: list[tuple[str, ParsedFrame]] = []

    def add_event(self, direction: str, frame: ParsedFrame | None, raw: bytes = b"",
                  note: str = "") -> None:
        if direction == "TX" and not self.show_tx.isChecked():
            return
        if frame is None:
            # 注入/异常帧：尽力解析，解析失败则原样展示
            frames = FrameParser().feed(raw)
            if frames:
                frame = frames[0]
                note = note or "异常帧(已恢复)"
            else:
                frame = ParsedFrame(cmd_id=0xFFFF, seq=0, data=b"", raw=raw)
                note = note or "无法解析"
        self._frames.append((direction, frame))
        row = self.table.rowCount()
        self.table.insertRow(row)
        cmd_text = f"0x{frame.cmd_id:04X} {frame.name}"
        if direction == "TX":
            cmd_text += " ↑"
        display = note if (note and note not in ("正常", "周期", "回放")) else \
            _summary(COMMANDS.get(frame.cmd_id), frame.cmd_id, frame.data)
        items = [
            _fmt_time(),
            direction,
            cmd_text,
            str(frame.seq),
            str(len(frame.raw)),
            display,
        ]
        for col, text in enumerate(items):
            self.table.setItem(row, col, QTableWidgetItem(text))
        self.table.scrollToBottom()
        if frame.cmd_id == 0x0301:
            # 收到 UI 帧自动选中并刷新右侧解析/画布
            self.table.selectRow(row)

    def _on_select(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._frames):
            return
        direction, frame = self._frames[row]
        self.hex_view.setText(frame.raw.hex(" "))
        spec = COMMANDS.get(frame.cmd_id)
        self.decode_table.setRowCount(0)
        if frame.cmd_id == 0x0301 and len(frame.data) >= 6:
            sub = int.from_bytes(frame.data[:2], "little")
            sender = int.from_bytes(frame.data[2:4], "little")
            receiver = int.from_bytes(frame.data[4:6], "little")
            content = frame.data[6:]
            self._add_decode_row("子内容ID", f"0x{sub:04X}", "")
            self._add_decode_row("发送者ID", str(sender), "")
            self._add_decode_row("接收者ID", f"0x{receiver:04X}", "")
            info = decode_interactive_content(sub, content)
            if sub == 0x0100:
                self.canvas.apply_delete(info["delete_type"], info["layer"])
                self._add_decode_row("删除操作", str(info["delete_type"]), "")
            elif "figures" in info:
                self.figure_list.clear()
                for fig in info["figures"]:
                    self.figure_list.addItem(fig.summary())
                    self.canvas.apply_figure(fig)
            elif sub == 0x0110:
                fig = info["figure"]
                text = info["char_data"].decode("utf-8", errors="replace").rstrip("\x00")
                self.figure_list.clear()
                self.figure_list.addItem(fig.summary())
                self._add_decode_row("字符", text, "")
                self.canvas.apply_figure(fig, text)
            elif sub == 0x0120:
                self._add_decode_row("哨兵指令", f"0x{info['sentry_cmd']:08X}", "")
            elif sub == 0x0121:
                self._add_decode_row("雷达指令", info["radar_cmd"].hex(" "), "")
            else:
                self._add_decode_row("内容", content.hex(" "), "机器人间通信")
        elif spec is not None:
            values = decode_command(spec, frame.data)
            for chunk in spec.chunks:
                from ..protocol.commands import BitGroup
                if isinstance(chunk, BitGroup):
                    for bit in chunk.bits:
                        self._add_decode_row(f"{chunk.label} - {bit.label or bit.name}",
                                             str(values.get(bit.name)), bit.note or "")
                elif chunk.ctype == "bytes":
                    self._add_decode_row(chunk.label or chunk.name,
                                         bytes(values[chunk.name]).hex(" "), chunk.note or "")
                else:
                    self._add_decode_row(chunk.label or chunk.name,
                                         str(values.get(chunk.name)), chunk.note or "")
        else:
            self._add_decode_row("数据", frame.data.hex(" "), "未知命令")

    def _add_decode_row(self, field: str, value: str, note: str) -> None:
        row = self.decode_table.rowCount()
        self.decode_table.insertRow(row)
        self.decode_table.setItem(row, 0, QTableWidgetItem(field))
        self.decode_table.setItem(row, 1, QTableWidgetItem(value))
        self.decode_table.setItem(row, 2, QTableWidgetItem(note))

    def _clear(self) -> None:
        self.table.setRowCount(0)
        self.decode_table.setRowCount(0)
        self._frames.clear()
        self.canvas.reset()
        self.figure_list.clear()


class ReplayTab(QWidget):
    """记录与回放。"""

    def __init__(self, recorder: Recorder, send_cb: Callable[[bytes, str], None],
                 parent=None) -> None:
        super().__init__(parent)
        self._recorder = recorder
        self._send_cb = send_cb
        self._replay_items: list[tuple[float, bytes, dict]] = []
        self._replay_idx = 0
        self._replay_t0 = 0.0
        self._replay_paused = False

        layout = QVBoxLayout(self)

        rec = QGroupBox("记录")
        rl = QHBoxLayout(rec)
        self.rec_path = QLineEdit(str(Path("referee_sim_record.jsonl").resolve()))
        rl.addWidget(self.rec_path, 1)
        browse = QPushButton("选择")
        browse.clicked.connect(self._pick_rec)
        rl.addWidget(browse)
        self.rec_btn = QPushButton("开始记录")
        self.rec_btn.clicked.connect(self._toggle_record)
        rl.addWidget(self.rec_btn)
        self.rec_label = QLabel("未记录")
        rl.addWidget(self.rec_label)
        layout.addWidget(rec)

        rep = QGroupBox("回放")
        rl2 = QHBoxLayout(rep)
        self.rep_path = QLineEdit()
        rl2.addWidget(self.rep_path, 1)
        browse2 = QPushButton("选择")
        browse2.clicked.connect(self._pick_replay)
        rl2.addWidget(browse2)
        load = QPushButton("加载")
        load.clicked.connect(self._load)
        rl2.addWidget(load)
        rl2.addWidget(QLabel("速度:"))
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 10.0)
        self.speed_spin.setValue(1.0)
        rl2.addWidget(self.speed_spin)
        self.play_btn = QPushButton("播放")
        self.play_btn.clicked.connect(self._toggle_play)
        rl2.addWidget(self.play_btn)
        layout.addWidget(rep)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._play_tick)

    def _pick_rec(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "记录文件", "referee_sim_record.jsonl",
                                              "JSONL (*.jsonl)")
        if path:
            self.rec_path.setText(path)

    def _toggle_record(self) -> None:
        if self._recorder.active:
            self._recorder.stop()
            self.rec_btn.setText("开始记录")
            self.rec_label.setText(f"已保存: {self._recorder.path}")
        else:
            self._recorder.start(self.rec_path.text())
            self.rec_btn.setText("停止记录")
            self.rec_label.setText("记录中…")

    def _pick_replay(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "回放文件", "", "JSONL (*.jsonl)")
        if path:
            self.rep_path.setText(path)

    def _load(self) -> None:
        path = self.rep_path.text()
        if not path:
            return
        self._replay_items = list(iter_replay(path, direction="TX"))
        self._replay_idx = 0
        self.status_label.setText(f"已加载 {len(self._replay_items)} 个发送帧: {path}")

    def _toggle_play(self) -> None:
        if self.timer.isActive():
            self._replay_paused = True
            self.timer.stop()
            self.play_btn.setText("继续")
            return
        if not self._replay_items:
            self._load()
        if not self._replay_items:
            self.status_label.setText("没有可回放的数据")
            return
        if self._replay_idx >= len(self._replay_items):
            self._replay_idx = 0
        self._replay_t0 = time.monotonic()
        self._replay_paused = False
        self.play_btn.setText("暂停")
        self.timer.start()

    def _play_tick(self) -> None:
        if self._replay_paused:
            return
        now = time.monotonic() - self._replay_t0
        speed = self.speed_spin.value()
        sent = 0
        while self._replay_idx < len(self._replay_items):
            delay, data, _meta = self._replay_items[self._replay_idx]
            if delay / speed > now:
                break
            self._send_cb(data, "回放")
            self._replay_idx += 1
            sent += 1
        if self._replay_idx >= len(self._replay_items):
            self.timer.stop()
            self.play_btn.setText("播放")
            self.status_label.setText(f"回放完成，共 {self._replay_idx} 帧")


class MatchTab(QWidget):
    """全流程比赛场景：按阶段推进并动态投喂裁判数据。"""

    def __init__(self, send_cb: Callable[[bytes, str], None], next_seq: Callable[[], int],
                 parent=None) -> None:
        super().__init__(parent)
        self._send_cb = send_cb
        self._next_seq = next_seq
        self.flow = MatchFlow()
        self._scheduler = Scheduler()
        self._last_tick = time.monotonic()
        self._running = False
        self._total_sent = 0

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.start_btn = QPushButton("开始比赛流程")
        self.start_btn.clicked.connect(self._toggle)
        top.addWidget(self.start_btn)
        self.reset_btn = QPushButton("重置")
        self.reset_btn.clicked.connect(self._reset)
        top.addWidget(self.reset_btn)
        self.phase_label = QLabel("阶段: 未开始")
        top.addWidget(self.phase_label)
        self.remain_label = QLabel("剩余: —")
        top.addWidget(self.remain_label)
        self.sent_label = QLabel("已发送: 0")
        top.addWidget(self.sent_label)
        top.addStretch(1)
        layout.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        layout.addWidget(self.progress)

        cfg = QHBoxLayout()
        cfg.addWidget(QLabel("机器人ID:"))
        self.robot_combo = QComboBox()
        for rid, label in ((1, "红英雄"), (2, "红工程"), (3, "红步兵3"), (4, "红步兵4"),
                           (5, "红步兵5"), (6, "红空中"), (7, "红哨兵"), (9, "红雷达"),
                           (101, "蓝英雄"), (102, "蓝工程"), (103, "蓝步兵3"), (104, "蓝步兵4"),
                           (105, "蓝步兵5"), (106, "蓝空中"), (107, "蓝哨兵"), (109, "蓝雷达")):
            self.robot_combo.addItem(label, rid)
        self.robot_combo.setCurrentIndex(6)
        cfg.addWidget(self.robot_combo)
        cfg.addWidget(QLabel("比赛时长(s):"))
        self.match_duration = QDoubleSpinBox()
        self.match_duration.setRange(10.0, 600.0)
        self.match_duration.setValue(300.0)
        cfg.addWidget(self.match_duration)
        cfg.addWidget(QLabel("射击间隔(s):"))
        self.shoot_interval = QDoubleSpinBox()
        self.shoot_interval.setRange(0.1, 5.0)
        self.shoot_interval.setDecimals(1)
        self.shoot_interval.setValue(0.6)
        cfg.addWidget(self.shoot_interval)
        cfg.addStretch(1)
        layout.addLayout(cfg)

        hint = QLabel("流程: 未开始(10s) → 准备(120s) → 十五秒自检 → 五秒倒计时 → "
                      "比赛(按设定时长) → 结算 → 结束；比赛中自动产生射击/伤害/判罚/结果事件")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._build_scheduler()
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._tick)

    def _build_scheduler(self) -> None:
        periodic = [0x0001, 0x0003, 0x0101, 0x0104, 0x0105,
                    0x0201, 0x0202, 0x0203, 0x0204, 0x0208, 0x0209, 0x020A,
                    0x020B, 0x020C, 0x020D, 0x020E]
        for cmd_id in periodic:
            spec = COMMANDS[cmd_id]
            self._scheduler.add(SchedEntry(cmd_id, 1.0 / (spec.freq or 1.0),
                                           self._builder(spec)))

    def _builder(self, spec: CommandSpec):
        def build() -> bytes:
            values = default_values(spec)
            values.update(self.flow.values())
            return build_frame(spec.cmd_id, encode_command(spec, values), self._next_seq())
        return build

    def _toggle(self) -> None:
        if self._running:
            self.timer.stop()
            self.start_btn.setText("开始比赛流程")
            self._running = False
            return
        self._reset()
        self._running = True
        self.start_btn.setText("停止")
        self._last_tick = time.monotonic()
        self.timer.start()

    def _reset(self) -> None:
        self.timer.stop()
        self.flow = MatchFlow(MatchConfig(
            robot_id=self.robot_combo.currentData(),
            match_duration=self.match_duration.value(),
            shoot_interval=self.shoot_interval.value(),
        ))
        self._build_scheduler()
        self._total_sent = 0
        self._running = False
        self.start_btn.setText("开始比赛流程")
        self._update_labels()

    def _tick(self) -> None:
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        for event in self.flow.update(dt):
            self._handle_event(event)
        for frame in self._scheduler.tick(now):
            self._send_cb(frame, "比赛流程")
            self._total_sent += 1
        if self.flow.phase >= 6:
            self.timer.stop()
            self._running = False
            self.start_btn.setText("重新开始")
        self._update_labels()

    def _handle_event(self, event: dict) -> None:
        kind = event["type"]
        if kind == "phase":
            return
        if kind == "shoot":
            values = default_values(COMMANDS[0x0207])
            values.update(self.flow.values())
            values.update({"bullet_type": event["bullet_type"],
                           "shooter_number": event["shooter_number"],
                           "launching_frequency": event["frequency"],
                           "initial_speed": event["speed"]})
            self._send_cb(build_frame(0x0207, encode_command(COMMANDS[0x0207], values),
                                      self._next_seq()), "射击事件")
            self._total_sent += 1
        elif kind == "hurt":
            values = default_values(COMMANDS[0x0206])
            values.update({"armor_id": event["armor_id"], "hurt_type": event["hurt_type"]})
            self._send_cb(build_frame(0x0206, encode_command(COMMANDS[0x0206], values),
                                      self._next_seq()), "伤害事件")
            self._total_sent += 1
        elif kind == "warning":
            values = default_values(COMMANDS[0x0104])
            values.update({"level": event["level"], "offending_robot_id": self.flow.config.robot_id,
                           "count": event["count"]})
            self._send_cb(build_frame(0x0104, encode_command(COMMANDS[0x0104], values),
                                      self._next_seq()), "判罚事件")
            self._total_sent += 1
        elif kind == "result":
            self._send_cb(build_frame(0x0002, bytes([event["winner"]]), self._next_seq()),
                          "比赛结果")
            self._total_sent += 1

    def _update_labels(self) -> None:
        self.phase_label.setText(f"阶段: {self.flow.phase_name}")
        self.remain_label.setText(f"剩余: {int(self.flow.phase_remain)}s")
        self.sent_label.setText(f"已发送: {self._total_sent}")
        duration = self.flow.phase_duration
        if duration > 0:
            self.progress.setValue(int((1.0 - self.flow.phase_elapsed / duration) * 1000))
        else:
            self.progress.setValue(0)
