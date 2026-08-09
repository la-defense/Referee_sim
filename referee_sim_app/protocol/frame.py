"""裁判系统帧封装与流式解析。

帧格式：frame_header(5B) | cmd_id(2B) | data(nB) | frame_tail(2B, CRC16)
frame_header: SOF(0xA5) + data_length(2B, 小端) + seq(1B) + CRC8(1B)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .crc import crc8, crc16

SOF = 0xA5
HEADER_LEN = 5
CMD_ID_LEN = 2
TAIL_LEN = 2
FRAME_OVERHEAD = HEADER_LEN + CMD_ID_LEN + TAIL_LEN

# 解析器认为 data_length 超过该值时判定为非法长度（防 0xFFFF 超大长度导致缓冲区挂起）
MAX_DATA_LEN = 4096


def build_frame(cmd_id: int, data: bytes, seq: int = 0) -> bytes:
    """构建一帧完整裁判系统数据包。"""
    if not 0 <= cmd_id <= 0xFFFF:
        raise ValueError(f"cmd_id 超出范围: {cmd_id:#x}")
    if not 0 <= seq <= 0xFF:
        raise ValueError(f"seq 超出范围: {seq}")
    header = bytes([SOF]) + struct.pack("<H", len(data)) + bytes([seq & 0xFF])
    header += bytes([crc8(header)])
    body = header + struct.pack("<H", cmd_id) + data
    return body + struct.pack("<H", crc16(body))


@dataclass
class ParsedFrame:
    cmd_id: int
    seq: int
    data: bytes
    raw: bytes

    @property
    def name(self) -> str:
        return COMMAND_NAMES.get(self.cmd_id, f"未知(0x{self.cmd_id:04X})")


COMMAND_NAMES: dict[int, str] = {}


def register_names(names: dict[int, str]) -> None:
    COMMAND_NAMES.update(names)


class FrameParser:
    """流式帧解析器。

    行为与固件 rm_referee.c 的滑动解析一致：
    找 SOF -> 校验帧头 CRC8 -> 按 data_length 计算帧长 -> 校验整包 CRC16；
    任何一步失败都只前进 1 字节重新扫描，支持多帧拼接。
    """

    def __init__(self, max_data_len: int = MAX_DATA_LEN) -> None:
        self.max_data_len = max_data_len
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[ParsedFrame]:
        frames: list[ParsedFrame] = []
        self._buf.extend(chunk)
        while len(self._buf) >= HEADER_LEN:
            if self._buf[0] != SOF:
                del self._buf[0]
                continue
            if crc8(bytes(self._buf[: HEADER_LEN - 1])) != self._buf[HEADER_LEN - 1]:
                del self._buf[0]
                continue
            data_len = struct.unpack_from("<H", self._buf, 1)[0]
            frame_len = FRAME_OVERHEAD + data_len
            if data_len > self.max_data_len:
                del self._buf[0]
                continue
            if len(self._buf) < frame_len:
                break  # 半帧，等待更多数据
            body_end = frame_len - TAIL_LEN
            expected = struct.unpack_from("<H", self._buf, body_end)[0]
            if crc16(bytes(self._buf[:body_end])) != expected:
                del self._buf[0]
                continue
            cmd_id = struct.unpack_from("<H", self._buf, HEADER_LEN)[0]
            seq = self._buf[3]
            data = bytes(self._buf[HEADER_LEN + CMD_ID_LEN: HEADER_LEN + CMD_ID_LEN + data_len])
            raw = bytes(self._buf[:frame_len])
            frames.append(ParsedFrame(cmd_id=cmd_id, seq=seq, data=data, raw=raw))
            del self._buf[:frame_len]
        return frames

    @property
    def pending(self) -> bytes:
        return bytes(self._buf)
