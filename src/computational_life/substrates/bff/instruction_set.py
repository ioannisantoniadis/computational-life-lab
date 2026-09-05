"""The BFF instruction set.

Semantics are taken from the reference implementation accompanying
Aguera y Arcas et al., "Computational Life: How Well-formed, Self-replicating
Programs Emerge from Simple Interaction" (arXiv:2406.19108), specifically
``bff.inc.h`` in https://github.com/paradigms-of-intelligence/cubff.
See docs/bff_semantics.md for the full rationale and the deviations from
the (incomplete) instruction table in the project specification.

Byte values are literal ASCII codes for the ten instruction characters.
Byte value 0 is a reserved NULL sentinel used as the loop-condition test
target. Every other byte value is a NOP when executed as an instruction,
but is "truthy" (non-zero) when tested as data by ``[`` / ``]``.
"""

from __future__ import annotations

import enum

import numpy as np


class Op(enum.IntEnum):
    """Symbolic BFF operations, distinct from their byte encoding."""

    LOOP_START = 0  # [
    LOOP_END = 1  # ]
    INC_CELL = 2  # +   increment byte at head0
    DEC_CELL = 3  # -   decrement byte at head0
    COPY_0_TO_1 = 4  # .   tape[head1] = tape[head0]
    COPY_1_TO_0 = 5  # ,   tape[head0] = tape[head1]
    DEC_HEAD0 = 6  # <   move head0 left
    INC_HEAD0 = 7  # >   move head0 right
    DEC_HEAD1 = 8  # {   move head1 left
    INC_HEAD1 = 9  # }   move head1 right
    NULL = 10  # the reserved zero byte
    NOP = 11  # any other unrecognized byte


# Byte encoding: literal ASCII codes, matching the reference implementation
# exactly so that genomes/traces are comparable to published BFF material.
_OP_TO_BYTE: dict[Op, int] = {
    Op.LOOP_START: ord("["),
    Op.LOOP_END: ord("]"),
    Op.INC_CELL: ord("+"),
    Op.DEC_CELL: ord("-"),
    Op.COPY_0_TO_1: ord("."),
    Op.COPY_1_TO_0: ord(","),
    Op.DEC_HEAD0: ord("<"),
    Op.INC_HEAD0: ord(">"),
    Op.DEC_HEAD1: ord("{"),
    Op.INC_HEAD1: ord("}"),
    Op.NULL: 0,
}

BYTE_TO_OP: tuple[Op, ...] = tuple(
    next((op for op, byte in _OP_TO_BYTE.items() if byte == value), Op.NOP)
    for value in range(256)
)

# Lookup table for vectorized (numpy) decoding: byte value -> Op as int.
BYTE_TO_OP_TABLE = np.array([int(op) for op in BYTE_TO_OP], dtype=np.uint8)

OP_TO_BYTE: dict[Op, int] = dict(_OP_TO_BYTE)

INSTRUCTION_CHARS = "[]+-.,<>{}"


def decode(byte: int) -> Op:
    """Return the :class:`Op` a raw byte value decodes to."""
    return BYTE_TO_OP[byte]


def encode(op: Op) -> int:
    """Return the canonical byte value for an instruction :class:`Op`.

    Only defined for the ten instruction ops and NULL; NOP has no single
    canonical byte (any of the ~245 unassigned byte values is a NOP).
    """
    return OP_TO_BYTE[op]


def parse(source: str) -> bytes:
    """Parse a human-written BFF source string into raw genome bytes.

    Each character in ``source`` must be one of the ten instruction
    characters or ``'0'`` (mapped to the NULL byte, 0x00); any other
    character raises ``ValueError``. This is a convenience for writing
    test fixtures and hand-crafted genomes, not used by the simulator
    on randomly generated populations.
    """
    result = bytearray()
    for ch in source:
        if ch == "0":
            result.append(0)
        elif ch in INSTRUCTION_CHARS:
            result.append(ord(ch))
        else:
            raise ValueError(f"Unrecognized BFF source character: {ch!r}")
    return bytes(result)
