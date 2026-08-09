import math

import pytest

from referee_sim_app.client.proto import (
    FieldSpec,
    MessageSchema,
    decode_message,
    encode_message,
)


def test_varint_edges():
    from referee_sim_app.client.proto import _decode_varint, _encode_varint

    for value in (0, 1, 127, 128, 300, 0xFFFFFFFF, 1 << 63, (1 << 64) - 1):
        assert _decode_varint(_encode_varint(value), 0) == (value & ((1 << 64) - 1), len(_encode_varint(value)))


def test_known_encodings():
    schema = MessageSchema("T", (
        FieldSpec(1, "a", "u32"),
        FieldSpec(2, "b", "u32"),
    ))
    assert encode_message(schema, {"a": 1}) == b"\x08\x01"
    assert encode_message(schema, {"a": 1, "b": 10}) == b"\x08\x01\x10\x0a"


def test_all_wire_types_roundtrip():
    schema = MessageSchema("T", (
        FieldSpec(1, "u", "u32"),
        FieldSpec(2, "i", "i32"),
        FieldSpec(3, "big", "u64"),
        FieldSpec(4, "neg", "i32"),
        FieldSpec(5, "f", "f32"),
        FieldSpec(6, "b", "bytes"),
        FieldSpec(7, "s", "string"),
        FieldSpec(8, "flag", "bool"),
    ))
    values = {"u": 0xFFFFFFFF, "i": -123, "big": 1 << 63, "neg": -1,
              "f": 3.5, "b": b"\x01\x02\x03", "s": "中文", "flag": True}
    data = encode_message(schema, values)
    dec = decode_message(schema, data)
    assert dec["u"] == 0xFFFFFFFF
    assert dec["i"] == -123
    assert dec["big"] == 1 << 63
    assert dec["neg"] == -1
    assert math.isclose(dec["f"], 3.5, rel_tol=1e-6)
    assert dec["b"] == b"\x01\x02\x03"
    assert dec["s"] == "中文"
    assert dec["flag"] is True


def test_repeated_and_packed():
    schema = MessageSchema("T", (
        FieldSpec(1, "plain", "u32", repeated=True),
        FieldSpec(2, "packed", "i32", repeated=True, packed=True),
    ))
    values = {"plain": [1, 2, 3], "packed": [-1, 0, 5]}
    data = encode_message(schema, values)
    dec = decode_message(schema, data)
    assert dec["plain"] == [1, 2, 3]
    assert dec["packed"] == [-1, 0, 5]


def test_nested_message():
    inner = MessageSchema("Inner", (FieldSpec(1, "x", "u32"),))
    outer = MessageSchema("Outer", (FieldSpec(1, "item", "message", repeated=True, sub=inner),))
    values = {"item": [{"x": 1}, {"x": 2}]}
    data = encode_message(outer, values)
    assert decode_message(outer, data) == {"item": [{"x": 1}, {"x": 2}]}


def test_unknown_field_skipped():
    schema = MessageSchema("T", (FieldSpec(1, "a", "u32"),))
    raw = b"\x08\x01\x10\x02"  # 字段 2 未定义
    assert decode_message(schema, raw) == {"a": 1}


def test_missing_fields_default_empty():
    schema = MessageSchema("T", (FieldSpec(1, "a", "u32"), FieldSpec(2, "b", "u32")))
    assert encode_message(schema, {"a": 1}) == b"\x08\x01"
    assert decode_message(schema, b"") == {}
