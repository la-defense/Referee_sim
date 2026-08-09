"""最小 Protobuf v3 编解码（官方自定义客户端协议所需子集）。

支持 varint/fixed32/length-delimited、repeated、packed repeated、嵌套 message。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

WIRE_VARINT = 0
WIRE_FIXED64 = 1
WIRE_LENGTH = 2
WIRE_FIXED32 = 5

VARINT_KINDS = {"u32", "i32", "u64", "i64", "bool"}


@dataclass(frozen=True)
class FieldSpec:
    number: int
    name: str
    kind: str  # u32 i32 u64 i64 bool f32 bytes string message
    repeated: bool = False
    packed: bool = False
    sub: object | None = None  # 嵌套 MessageSchema


@dataclass(frozen=True)
class MessageSchema:
    name: str
    fields: tuple[FieldSpec, ...]

    def field(self, number: int) -> FieldSpec | None:
        for f in self.fields:
            if f.number == number:
                return f
        return None


def _encode_varint(value: int) -> bytes:
    value &= (1 << 64) - 1
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        b = data[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, pos
        shift += 7


def _wire_of(kind: str) -> int:
    if kind in VARINT_KINDS:
        return WIRE_VARINT
    if kind == "f32":
        return WIRE_FIXED32
    return WIRE_LENGTH


def _normalize(kind: str, value) -> int:
    if kind == "bool":
        return 1 if value else 0
    if kind in ("i32", "i64"):
        return value & ((1 << 64) - 1)
    return int(value)


def _encode_scalar(spec: FieldSpec, value) -> bytes:
    tag = _encode_varint((spec.number << 3) | _wire_of(spec.kind))
    if spec.kind in VARINT_KINDS:
        return tag + _encode_varint(_normalize(spec.kind, value))
    if spec.kind == "f32":
        return tag + struct.pack("<f", float(value))
    if spec.kind == "bytes":
        raw = bytes(value)
        return tag + _encode_varint(len(raw)) + raw
    if spec.kind == "string":
        raw = str(value).encode("utf-8")
        return tag + _encode_varint(len(raw)) + raw
    if spec.kind == "message":
        raw = encode_message(spec.sub, value)
        return tag + _encode_varint(len(raw)) + raw
    raise ValueError(f"未知字段类型: {spec.kind}")


def encode_message(schema: MessageSchema, values: dict) -> bytes:
    """按 schema 编码消息。values 以字段名为键；None/缺失字段跳过。"""
    out = bytearray()
    for spec in schema.fields:
        value = values.get(spec.name)
        if value is None:
            continue
        if spec.repeated:
            items = list(value)
            if spec.packed and spec.kind in VARINT_KINDS:
                inner = b"".join(_encode_varint(_normalize(spec.kind, v)) for v in items)
                tag = _encode_varint((spec.number << 3) | WIRE_LENGTH)
                out += tag + _encode_varint(len(inner)) + inner
            else:
                for v in items:
                    out += _encode_scalar(spec, v)
        else:
            out += _encode_scalar(spec, value)
    return bytes(out)


def _skip(wire: int, data: bytes, pos: int) -> int:
    if wire == WIRE_VARINT:
        _, pos = _decode_varint(data, pos)
    elif wire == WIRE_FIXED64:
        pos += 8
    elif wire == WIRE_LENGTH:
        ln, pos = _decode_varint(data, pos)
        pos += ln
    elif wire == WIRE_FIXED32:
        pos += 4
    else:
        raise ValueError(f"未知 wire type: {wire}")
    return pos


def _decode_scalar(spec: FieldSpec, wire: int, data: bytes, pos: int) -> tuple[object, int]:
    expected = _wire_of(spec.kind)
    if wire != expected:
        raise ValueError(f"字段 {spec.number} wire 类型不匹配: {wire} != {expected}")
    if spec.kind in ("u32", "u64", "i32", "i64", "bool"):
        raw, pos = _decode_varint(data, pos)
        if spec.kind == "u32":
            value = raw & 0xFFFFFFFF
        elif spec.kind == "u64":
            value = raw
        elif spec.kind == "i32":
            value = raw & 0xFFFFFFFF
            if value >= 0x80000000:
                value -= 0x100000000
        elif spec.kind == "i64":
            value = raw
            if value >= 1 << 63:
                value -= 1 << 64
        else:
            value = bool(raw)
        return value, pos
    if spec.kind == "f32":
        return struct.unpack_from("<f", data, pos)[0], pos + 4
    if spec.kind in ("bytes", "string", "message"):
        ln, pos = _decode_varint(data, pos)
        payload = data[pos: pos + ln]
        pos += ln
        if spec.kind == "bytes":
            return payload, pos
        if spec.kind == "string":
            return payload.decode("utf-8", errors="replace"), pos
        return decode_message(spec.sub, payload), pos
    raise ValueError(f"未知字段类型: {spec.kind}")


def decode_message(schema: MessageSchema, data: bytes) -> dict:
    """按 schema 解码消息，返回 {字段名: 值}。"""
    values: dict = {}
    pos = 0
    while pos < len(data):
        tag, pos = _decode_varint(data, pos)
        number, wire = tag >> 3, tag & 7
        spec = schema.field(number)
        if spec is None:
            pos = _skip(wire, data, pos)
            continue
        if (spec.repeated and spec.packed and spec.kind in VARINT_KINDS
                and wire == WIRE_LENGTH):
            ln, pos = _decode_varint(data, pos)
            end = pos + ln
            items = values.setdefault(spec.name, [])
            while pos < end:
                raw, pos = _decode_varint(data, pos)
                items.append(_postprocess(spec, raw))
            continue
        value, pos = _decode_scalar(spec, wire, data, pos)
        if spec.repeated:
            values.setdefault(spec.name, []).append(value)
        else:
            values[spec.name] = value
    return values


def _postprocess(spec: FieldSpec, raw: int) -> object:
    if spec.kind == "u32":
        return raw & 0xFFFFFFFF
    if spec.kind == "u64":
        return raw
    if spec.kind == "i32":
        v = raw & 0xFFFFFFFF
        return v - 0x100000000 if v >= 0x80000000 else v
    if spec.kind == "i64":
        return raw - (1 << 64) if raw >= 1 << 63 else raw
    if spec.kind == "bool":
        return bool(raw)
    return raw
