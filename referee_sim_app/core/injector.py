"""错误注入：坏 CRC、超大长度、短帧、洪泛、半帧、乱序、多帧拼接。"""

from __future__ import annotations

import struct

from ..protocol.crc import crc8, crc16
from ..protocol.frame import HEADER_LEN, SOF


def _rebuild(frame: bytes, data_len: int | None = None, seq: int | None = None) -> bytes:
    """按新参数重建帧（CRC 重新计算，保证“合法帧”语义）。"""
    body = bytearray(frame[HEADER_LEN:-2])
    if data_len is None:
        data_len = len(body) - 2
    if seq is None:
        seq = frame[3]
    header = bytes([SOF]) + struct.pack("<H", data_len) + bytes([seq & 0xFF])
    header += bytes([crc8(header)])
    payload = header + bytes(body)
    return payload + struct.pack("<H", crc16(payload))


def corrupt_crc8(frame: bytes) -> bytes:
    """翻转帧头 CRC8 字节，制造帧头校验失败。"""
    out = bytearray(frame)
    out[HEADER_LEN - 1] ^= 0xFF
    return bytes(out)


def corrupt_crc16(frame: bytes) -> bytes:
    """翻转帧尾 CRC16 低字节，制造整包校验失败。"""
    out = bytearray(frame)
    out[-1] ^= 0xFF
    return bytes(out)


def oversize_length(frame: bytes, declared: int = 0xFFFF) -> bytes:
    """声明超大 data_length（CRC 合法），触发长度边界保护。"""
    return _rebuild(frame, data_len=declared)


def zero_length(frame: bytes) -> bytes:
    """data_length=0（CRC 合法），触发按命令码的数据段长度保护。"""
    cmd_id = struct.unpack_from("<H", frame, HEADER_LEN)[0]
    body = struct.pack("<H", cmd_id)
    header = bytes([SOF]) + struct.pack("<H", 0) + bytes([frame[3] & 0xFF])
    header += bytes([crc8(header)])
    payload = header + body
    return payload + struct.pack("<H", crc16(payload))


def flood_prefix(data: bytes, count: int = 200) -> bytes:
    """0xA5 洪泛前缀。"""
    return bytes([0xA5]) * count + data


def truncate_frame(frame: bytes, keep: int | None = None) -> bytes:
    """半帧截断（保留前 keep 字节，默认 5~10 字节）。"""
    if keep is None:
        keep = min(max(5, len(frame) // 2), 10)
    return frame[:keep]


def rebuild_seq(frame: bytes, seq: int) -> bytes:
    """重写包序号（CRC 合法），用于乱序/序号测试。"""
    return _rebuild(frame, seq=seq)


def concat_frames(*frames: bytes) -> bytes:
    """多帧拼接一次发送。"""
    return b"".join(frames)
