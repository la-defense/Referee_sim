"""按命令定义动态生成字段编辑表单。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from ..protocol.commands import BitGroup, CommandSpec, Field

INT_RANGES = {
    "u8": (0, 0xFF),
    "u16": (0, 0xFFFF),
    "u32": (0, 0xFFFFFFFF),
    "i8": (-0x80, 0x7F),
    "i16": (-0x8000, 0x7FFF),
    "i32": (-0x80000000, 0x7FFFFFFF),
}


def _make_hex_line(value: int, width: int) -> QLineEdit:
    ed = QLineEdit(f"0x{int(value) & ((1 << (width * 8)) - 1):0{width * 2}X}")
    ed.setMaximumWidth(180)
    return ed


class FieldEditor(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._widgets: dict[str, QWidget] = {}
        self._line_kinds: dict[str, str] = {}
        self._spec: CommandSpec | None = None

    def set_spec(self, spec: CommandSpec | None) -> None:
        self._spec = spec
        while self._form.rowCount():
            self._form.removeRow(0)
        self._widgets.clear()
        self._line_kinds.clear()
        if spec is None:
            return
        for chunk in spec.chunks:
            if isinstance(chunk, BitGroup):
                for bit in chunk.bits:
                    self._add_bitfield(chunk, bit)
            else:
                self._add_field(chunk)

    def _add_bitfield(self, group: BitGroup, bit) -> None:
        name = bit.name
        if bit.width == 1:
            cb = QCheckBox(bit.label or name)
            cb.setChecked(bool(bit.default))
            self._widgets[name] = cb
            self._form.addRow(group.label or "", cb)
        elif bit.choices:
            box = QComboBox()
            for value, label in bit.choices.items():
                box.addItem(label, value)
            idx = box.findData(bit.default)
            box.setCurrentIndex(max(0, idx))
            self._widgets[name] = box
            self._form.addRow(f"{group.label} - {bit.label or name}", box)
        else:
            spin = QSpinBox()
            spin.setRange(0, (1 << bit.width) - 1)
            spin.setValue(int(bit.default))
            self._widgets[name] = spin
            self._form.addRow(f"{group.label} - {bit.label or name}", spin)

    def _add_field(self, field: Field) -> None:
        label = f"{field.label or field.name}" + (f" [{field.unit}]" if field.unit else "")
        if field.ctype == "bytes":
            hint = f"≤{field.size}B" if field.size else "动态≤112B"
            ed = QLineEdit()
            ed.setPlaceholderText(f"十六进制，{hint}")
            ed.setToolTip(field.note or "以十六进制输入原始字节")
            self._widgets[field.name] = ed
            self._line_kinds[field.name] = "bytes"
            self._form.addRow(f"{label} ({hint})", ed)
        elif field.choices:
            box = QComboBox()
            for value, text in field.choices.items():
                box.addItem(text, value)
            idx = box.findData(field.default)
            box.setCurrentIndex(max(0, idx))
            self._widgets[field.name] = box
            self._form.addRow(label, box)
        elif field.ctype == "f32":
            spin = QDoubleSpinBox()
            spin.setRange(-1e9, 1e9)
            spin.setDecimals(3)
            spin.setValue(float(field.default))
            self._widgets[field.name] = spin
            self._form.addRow(label, spin)
        elif field.ctype == "u64":
            ed = QLineEdit(str(int(field.default)))
            ed.setToolTip(field.note)
            self._widgets[field.name] = ed
            self._line_kinds[field.name] = "u64"
            self._form.addRow(label, ed)
        elif field.hex:
            ed = _make_hex_line(int(field.default), int(field.ctype[1:]) // 8)
            ed.setToolTip(field.note)
            self._widgets[field.name] = ed
            self._line_kinds[field.name] = "hex"
            self._form.addRow(label, ed)
        else:
            lo, hi = INT_RANGES[field.ctype]
            spin = QSpinBox()
            spin.setRange(lo, hi)
            spin.setValue(int(field.default))
            self._widgets[field.name] = spin
            self._form.addRow(label, spin)

    def get_values(self) -> dict:
        values: dict = {}
        for name, w in self._widgets.items():
            if isinstance(w, QCheckBox):
                values[name] = 1 if w.isChecked() else 0
            elif isinstance(w, QComboBox):
                values[name] = w.currentData()
            elif isinstance(w, QSpinBox):
                values[name] = w.value()
            elif isinstance(w, QDoubleSpinBox):
                values[name] = w.value()
            elif isinstance(w, QLineEdit):
                text = w.text().strip()
                kind = self._line_kinds.get(name, "bytes")
                if kind == "bytes":
                    values[name] = b""
                    if text:
                        try:
                            values[name] = bytes.fromhex(text)
                        except ValueError as exc:
                            raise ValueError(f"{name} 不是合法十六进制: {exc}") from exc
                elif kind == "u64":
                    values[name] = int(text, 0) if text else 0
                else:  # hex
                    values[name] = int(text, 16) if text else 0
        return values

    def set_value(self, name: str, value) -> None:
        w = self._widgets.get(name)
        if w is None:
            return
        if isinstance(w, QCheckBox):
            w.setChecked(bool(value))
        elif isinstance(w, QComboBox):
            idx = w.findData(int(value))
            w.setCurrentIndex(max(0, idx))
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.setValue(value)
        elif isinstance(w, QLineEdit):
            if isinstance(value, bytes):
                w.setText(value.hex())
            else:
                w.setText(str(value))

    def set_content_hex(self, hex_text: str) -> None:
        w = self._widgets.get("content")
        if isinstance(w, QLineEdit):
            w.setText(hex_text)
