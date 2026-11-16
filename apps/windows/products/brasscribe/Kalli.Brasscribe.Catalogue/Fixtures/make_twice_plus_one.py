"""Writes twice-plus-one.onnx: y = 2 x + 1 for x of shape [1, 4] (float), two ONNX operators (Mul, Add, opset 13)
that every execution provider has. Standard library only: the protobuf is written by hand.

    python3 make_twice_plus_one.py
"""
import struct
from pathlib import Path


def varint(n: int) -> bytes:
    out = b""
    while True:
        b, n = n & 0x7F, n >> 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def field(number: int, wire: int, payload: bytes) -> bytes:
    return varint(number << 3 | wire) + payload


def num(number: int, value: int) -> bytes:
    return field(number, 0, varint(value))


def msg(number: int, body: bytes) -> bytes:
    return field(number, 2, varint(len(body)) + body)


def text(number: int, s: str) -> bytes:
    return msg(number, s.encode())


FLOAT = 1
shape = msg(2, msg(1, num(1, 1)) + msg(1, num(1, 4)))  # TensorShapeProto: dims 1 and 4
tensor_type = msg(2, msg(1, num(1, FLOAT) + shape))  # TypeProto.tensor_type
x = msg(11, text(1, "x") + tensor_type)
y = msg(12, text(1, "y") + tensor_type)
two = msg(5, num(1, 1) + num(2, FLOAT) + msg(4, struct.pack("<f", 2.0)) + text(8, "two"))
one = msg(5, num(1, 1) + num(2, FLOAT) + msg(4, struct.pack("<f", 1.0)) + text(8, "one"))
mul = msg(1, text(1, "x") + text(1, "two") + text(2, "twice") + text(3, "mul") + text(4, "Mul"))
add = msg(1, text(1, "twice") + text(1, "one") + text(2, "y") + text(3, "add") + text(4, "Add"))
graph = msg(7, mul + add + text(2, "twice-plus-one") + two + one + x + y)
model = num(1, 8) + text(2, "brasscribe") + msg(8, text(1, "") + num(2, 13)) + graph
Path(__file__).with_name("twice-plus-one.onnx").write_bytes(model)
