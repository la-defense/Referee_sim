"""0x0301 机器人交互数据中的 UI 图形编解码（官方 V2.0.0 表 1-25 ~ 1-34）。"""

from __future__ import annotations

import struct
from dataclasses import dataclass

FIGURE_TYPES: dict[int, str] = {
    0: "直线", 1: "矩形", 2: "正圆", 3: "椭圆", 4: "圆弧",
    5: "浮点数", 6: "整型数", 7: "字符",
}
OPERATE_TYPES: dict[int, str] = {0: "空操作", 1: "增加", 2: "修改", 3: "删除"}
COLORS: dict[int, str] = {
    0: "红/蓝(己方)", 1: "黄色", 2: "绿色", 3: "橙色", 4: "紫红色",
    5: "粉色", 6: "青色", 7: "黑色", 8: "白色",
}

SUB_CONTENT_NAMES: dict[int, str] = {
    0x0100: "删除图层", 0x0101: "绘制1个图形", 0x0102: "绘制2个图形",
    0x0103: "绘制5个图形", 0x0104: "绘制7个图形", 0x0110: "绘制字符",
    0x0120: "哨兵自主决策指令", 0x0121: "雷达自主决策指令",
}


@dataclass
class Figure:
    name: bytes
    operate: int
    figure_type: int
    layer: int
    color: int
    width: int
    start_x: int
    start_y: int
    details_a: int
    details_b: int
    details_c: int
    details_d: int
    details_e: int

    @property
    def name_str(self) -> str:
        return self.name.decode("utf-8", errors="replace").rstrip("\x00")

    @property
    def type_name(self) -> str:
        return FIGURE_TYPES.get(self.figure_type, f"未知({self.figure_type})")

    @property
    def operate_name(self) -> str:
        return OPERATE_TYPES.get(self.operate, f"未知({self.operate})")

    @property
    def color_name(self) -> str:
        return COLORS.get(self.color, f"未知({self.color})")

    @property
    def int_value(self) -> int:
        """details_c/d/e 组合的 32 位整型值（浮点数显示为 value/1000）。"""
        v = self.details_c | (self.details_d << 10) | (self.details_e << 21)
        if v & (1 << 31):
            v -= 1 << 32
        return v

    @property
    def float_value(self) -> float:
        return self.int_value / 1000.0

    def summary(self) -> str:
        base = (f"{self.type_name}[{self.name_str}] op={self.operate_name} "
                f"layer={self.layer} color={self.color_name} width={self.width} "
                f"start=({self.start_x},{self.start_y})")
        if self.figure_type == 5:
            base += f" value={self.float_value}"
        elif self.figure_type == 6:
            base += f" value={self.int_value}"
        elif self.figure_type in (0, 1):
            base += f" end=({self.details_d},{self.details_e})"
        elif self.figure_type == 2:
            base += f" radius={self.details_c}"
        elif self.figure_type == 3:
            base += f" rx={self.details_d} ry={self.details_e}"
        elif self.figure_type == 4:
            base += f" arc={self.details_a}..{self.details_b} rx={self.details_d} ry={self.details_e}"
        elif self.figure_type == 7:
            base += f" font={self.details_a} len={self.details_b}"
        return base

    def to_bytes(self) -> bytes:
        cfg1 = (self.operate & 0x7) | ((self.figure_type & 0x7) << 3) | \
               ((self.layer & 0xF) << 6) | ((self.color & 0xF) << 10) | \
               ((self.details_a & 0x1FF) << 14) | ((self.details_b & 0x1FF) << 23)
        cfg2 = (self.width & 0x3FF) | ((self.start_x & 0x7FF) << 10) | \
               ((self.start_y & 0x7FF) << 21)
        cfg3 = (self.details_c & 0x3FF) | ((self.details_d & 0x7FF) << 10) | \
               ((self.details_e & 0x7FF) << 21)
        return (bytes(self.name[:3]).ljust(3, b"\x00") +
                struct.pack("<III", cfg1, cfg2, cfg3))

    @classmethod
    def from_bytes(cls, data: bytes) -> "Figure":
        if len(data) < 15:
            data = data + b"\x00" * (15 - len(data))
        name = data[:3]
        cfg1, cfg2, cfg3 = struct.unpack_from("<III", data, 3)
        return cls(
            name=name,
            operate=cfg1 & 0x7,
            figure_type=(cfg1 >> 3) & 0x7,
            layer=(cfg1 >> 6) & 0xF,
            color=(cfg1 >> 10) & 0xF,
            details_a=(cfg1 >> 14) & 0x1FF,
            details_b=(cfg1 >> 23) & 0x1FF,
            width=cfg2 & 0x3FF,
            start_x=(cfg2 >> 10) & 0x7FF,
            start_y=(cfg2 >> 21) & 0x7FF,
            details_c=cfg3 & 0x3FF,
            details_d=(cfg3 >> 10) & 0x7FF,
            details_e=(cfg3 >> 21) & 0x7FF,
        )


def figure_count_for(data_cmd_id: int) -> int | None:
    return {0x0101: 1, 0x0102: 2, 0x0103: 5, 0x0104: 7}.get(data_cmd_id)


def decode_figure(data: bytes) -> Figure:
    return Figure.from_bytes(data)


def build_figures_content(data_cmd_id: int, figures: list[Figure] | None = None,
                          char_data: bytes | None = None,
                          delete_type: int | None = None, layer: int | None = None,
                          sentry_cmd: int | None = None,
                          radar_cmd: bytes | None = None,
                          raw: bytes | None = None) -> bytes:
    """按子内容 ID 构建 0x0301 的内容数据段。"""
    if raw is not None:
        return bytes(raw)
    if data_cmd_id == 0x0100:
        return bytes([delete_type or 0, layer or 0])
    n = figure_count_for(data_cmd_id)
    if n is not None:
        if len(figures) < n:
            raise ValueError(f"0x{data_cmd_id:04X} 需要 {n} 个图形，实际 {len(figures)}")
        out = b"".join(x.to_bytes() for x in figures)
        return out[: n * 15]
    if data_cmd_id == 0x0110:
        if not figures:
            raise ValueError("0x0110 需要 1 个字符图形")
        text = char_data or b""
        if isinstance(text, str):
            text = text.encode("utf-8")
        text = text[:30]
        return figures[0].to_bytes() + text.ljust(30, b"\x00")
    if data_cmd_id == 0x0120:
        return struct.pack("<I", sentry_cmd or 0)
    if data_cmd_id == 0x0121:
        data = (radar_cmd or b"")[:8]
        return data.ljust(8, b"\x00")
    if 0x0200 <= data_cmd_id <= 0x02FF:
        return bytes(raw or b"")
    raise ValueError(f"未知子内容 ID: 0x{data_cmd_id:04X}")


def decode_interactive_content(data_cmd_id: int, content: bytes) -> dict:
    """解析 0x0301 内容数据段，返回便于展示/绘制的结构化字典。"""
    result: dict = {"data_cmd_id": data_cmd_id, "name": SUB_CONTENT_NAMES.get(data_cmd_id, "机器人间通信")}
    if data_cmd_id == 0x0100:
        result["delete_type"] = content[0] if len(content) > 0 else 0
        result["layer"] = content[1] if len(content) > 1 else 0
    elif (n := figure_count_for(data_cmd_id)) is not None:
        figures = []
        for i in range(n):
            fig = Figure.from_bytes(content[i * 15: (i + 1) * 15])
            figures.append(fig)
        result["figures"] = figures
    elif data_cmd_id == 0x0110:
        result["figure"] = Figure.from_bytes(content[:15])
        result["char_data"] = content[15:45]
    elif data_cmd_id == 0x0120:
        result["sentry_cmd"] = int.from_bytes(content[:4], "little") if len(content) >= 4 else 0
    elif data_cmd_id == 0x0121:
        result["radar_cmd"] = content[:8]
    elif 0x0200 <= data_cmd_id <= 0x02FF:
        result["data"] = bytes(content)
    else:
        result["data"] = bytes(content)
    return result
