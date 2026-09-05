"""Differential tests: the vectorized batch interpreter must agree with the
scalar interpreter (the correctness oracle) on every lane, for both random
genomes and the hand-written edge cases already covered in
test_interpreter.py. The vectorized engine is never trusted on its own.
"""

import numpy as np
import pytest

from computational_life.substrates.bff.interpreter import BffInterpreter
from computational_life.substrates.bff.instruction_set import parse
from computational_life.substrates.bff.vectorized import BatchBffInterpreter


def run_scalar(tape: bytes, max_steps: int, head_init: str):
    interp = BffInterpreter(bytearray(tape), head_init=head_init)
    interp.run(max_steps=max_steps)
    return interp.state


@pytest.mark.parametrize("head_init", ["zero", "from_tape"])
@pytest.mark.parametrize("length", [8, 16, 64, 128])
def test_batch_matches_scalar_on_random_genomes(head_init, length):
    rng = np.random.default_rng(12345)
    num_lanes = 200
    tapes = rng.integers(0, 256, size=(num_lanes, length), dtype=np.uint8)

    batch = BatchBffInterpreter(tapes.copy(), head_init=head_init)
    batch.run(max_steps=2000)

    for lane in range(num_lanes):
        expected = run_scalar(tapes[lane].tobytes(), max_steps=2000, head_init=head_init)
        assert bytes(batch.tapes[lane]) == expected.tape, f"tape mismatch at lane {lane}"
        assert int(batch.head0[lane]) == expected.head0, f"head0 mismatch at lane {lane}"
        assert int(batch.head1[lane]) == expected.head1, f"head1 mismatch at lane {lane}"
        assert bool(batch.halted[lane]) == expected.halted, f"halted mismatch at lane {lane}"
        assert int(batch.step_count[lane]) == expected.step_count, (
            f"step_count mismatch at lane {lane}"
        )


def test_batch_matches_scalar_on_handwritten_edge_cases():
    genomes = [
        parse("[+-.,<>{}]") + bytes(6),  # every instruction once
        bytes([0, ord("["), ord("+"), ord("+"), ord("]"), ord("+")] + [0] * 10),
        bytes([ord("+"), ord("]")] + [0] * 14),  # unmatched loop end -> halt
        bytes([0, ord("[")] + [0] * 14),  # unmatched loop start -> halt
        bytes(16),  # all NULL
        bytes([1] * 16),  # all NOP (byte 1 is unassigned)
    ]
    length = 16
    tapes = np.array([list(g) + [0] * (length - len(g)) for g in genomes], dtype=np.uint8)

    batch = BatchBffInterpreter(tapes.copy())
    batch.run(max_steps=500)

    for lane, genome in enumerate(genomes):
        padded = bytes(genome) + bytes(length - len(genome))
        expected = run_scalar(padded, max_steps=500, head_init="zero")
        assert bytes(batch.tapes[lane]) == expected.tape
        assert bool(batch.halted[lane]) == expected.halted
        assert int(batch.step_count[lane]) == expected.step_count


def test_batch_reset_restores_initial_state():
    rng = np.random.default_rng(7)
    tapes = rng.integers(0, 256, size=(5, 32), dtype=np.uint8)
    batch = BatchBffInterpreter(tapes.copy())
    initial = batch.tapes.copy()
    batch.run(max_steps=100)
    assert not np.array_equal(batch.tapes, initial) or batch.halted.all()
    batch.reset()
    assert np.array_equal(batch.tapes, initial)
    assert (batch.step_count == 0).all()
    assert (~batch.halted).all()
