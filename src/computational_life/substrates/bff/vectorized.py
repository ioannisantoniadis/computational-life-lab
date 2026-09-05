"""Vectorized (batch) BFF interpreter.

Executes many independent tapes in lockstep using NumPy, one instruction
per lane per tick, so that a whole population of pairings can be advanced
without a Python-level loop over organisms. This is a *performance*
component only: its semantics are validated against
:class:`~computational_life.substrates.bff.interpreter.BffInterpreter`
(the scalar oracle) via differential tests, and it must never be treated
as a separate source of truth for BFF semantics.

Bracket matching (``[`` / ``]``) is data-dependent per lane and is not
elementwise-vectorizable in the same way as the other instructions; it is
handled with a short Python loop restricted to the (typically small)
subset of lanes that need a bracket scan on a given tick. This is a
deliberate, documented performance compromise for Phase 1 -- see
docs/bff_semantics.md and the Phase 1 plan's "performance pitfalls"
section. Profile before attempting to vectorize it further.
"""

from __future__ import annotations

import numpy as np

from .instruction_set import BYTE_TO_OP_TABLE, Op

DEFAULT_MAX_STEPS = 8192


class BatchBffInterpreter:
    """Runs N independent BFF tapes of equal length in lockstep.

    Parameters
    ----------
    tapes:
        A ``(num_lanes, tape_length)`` uint8 array. Copied on construction
        and mutated in place by :meth:`step` / :meth:`run`.
    head_init:
        Same meaning as :class:`BffInterpreter`: ``"zero"`` (default,
        Phase 1's "bff_noheads" baseline) or ``"from_tape"``.
    """

    def __init__(self, tapes: np.ndarray, *, head_init: str = "zero"):
        if head_init not in ("zero", "from_tape"):
            raise ValueError(f"Unknown head_init strategy: {head_init!r}")
        if tapes.ndim != 2:
            raise ValueError("tapes must be a 2D (num_lanes, tape_length) array")
        self._initial_tapes = np.array(tapes, dtype=np.uint8, copy=True)
        self._head_init = head_init
        self.num_lanes, self.length = self._initial_tapes.shape
        self.tapes = np.empty_like(self._initial_tapes)
        self.head0 = np.zeros(self.num_lanes, dtype=np.int64)
        self.head1 = np.zeros(self.num_lanes, dtype=np.int64)
        self.pc = np.zeros(self.num_lanes, dtype=np.int64)
        self.step_count = np.zeros(self.num_lanes, dtype=np.int64)
        self.halted = np.zeros(self.num_lanes, dtype=bool)
        self.reset()

    def reset(self) -> None:
        self.tapes[...] = self._initial_tapes
        n = self.length
        if self._head_init == "zero":
            self.head0[:] = 0
            self.head1[:] = 0
            self.pc[:] = 0
        else:
            self.head0[:] = self._initial_tapes[:, 0].astype(np.int64) % n
            self.head1[:] = self._initial_tapes[:, 1].astype(np.int64) % n
            self.pc[:] = 2
        self.step_count[:] = 0
        self.halted[:] = False

    def step(self) -> bool:
        """Advance every non-halted lane by exactly one instruction.

        Returns True if any lane executed an instruction this tick.
        """
        active = ~self.halted
        if not active.any():
            return False

        n = self.length
        rows = np.arange(self.num_lanes)
        safe_pc = np.clip(self.pc, 0, n - 1)
        cmd = self.tapes[rows, safe_pc]
        op = BYTE_TO_OP_TABLE[cmd]

        next_pc = self.pc + 1  # default advance, overridden for taken jumps

        def lane_mask(target_op: Op) -> np.ndarray:
            return active & (op == int(target_op))

        m = lane_mask(Op.DEC_HEAD0)
        self.head0[m] -= 1
        m = lane_mask(Op.INC_HEAD0)
        self.head0[m] += 1
        m = lane_mask(Op.DEC_HEAD1)
        self.head1[m] -= 1
        m = lane_mask(Op.INC_HEAD1)
        self.head1[m] += 1

        m = lane_mask(Op.INC_CELL)
        h0 = self.head0[m] % n
        self.tapes[rows[m], h0] += 1
        m = lane_mask(Op.DEC_CELL)
        h0 = self.head0[m] % n
        self.tapes[rows[m], h0] -= 1

        m = lane_mask(Op.COPY_0_TO_1)
        h0, h1 = self.head0[m] % n, self.head1[m] % n
        self.tapes[rows[m], h1] = self.tapes[rows[m], h0]
        m = lane_mask(Op.COPY_1_TO_0)
        h0, h1 = self.head0[m] % n, self.head1[m] % n
        self.tapes[rows[m], h0] = self.tapes[rows[m], h1]

        next_pc = self._resolve_loop_start(active, op, next_pc)
        next_pc = self._resolve_loop_end(active, op, next_pc)

        self.head0 %= n
        self.head1 %= n
        self.pc = np.where(active, next_pc, self.pc)
        self.step_count += active.astype(np.int64)
        self.halted = self.halted | ((self.pc < 0) | (self.pc >= n))
        return True

    def run(self, max_steps: int = DEFAULT_MAX_STEPS) -> np.ndarray:
        """Run every lane for up to ``max_steps`` more ticks.

        Stops the whole batch early once every lane has halted. Returns
        the per-lane instruction count executed during this call.
        """
        before = self.step_count.copy()
        for _ in range(max_steps):
            if not self.step():
                break
        return self.step_count - before

    def _resolve_loop_start(
        self, active: np.ndarray, op: np.ndarray, next_pc: np.ndarray
    ) -> np.ndarray:
        n = self.length
        rows = np.arange(self.num_lanes)
        mask = active & (op == int(Op.LOOP_START))
        if not mask.any():
            return next_pc
        h0 = self.head0[mask] % n
        is_null = self.tapes[rows[mask], h0] == 0
        skip_lanes = rows[mask][is_null]
        for lane in skip_lanes:
            match = self._scan_forward(lane, int(self.pc[lane]))
            next_pc[lane] = (match + 1) if match is not None else n
        return next_pc

    def _resolve_loop_end(
        self, active: np.ndarray, op: np.ndarray, next_pc: np.ndarray
    ) -> np.ndarray:
        n = self.length
        rows = np.arange(self.num_lanes)
        mask = active & (op == int(Op.LOOP_END))
        if not mask.any():
            return next_pc
        h0 = self.head0[mask] % n
        is_nonnull = self.tapes[rows[mask], h0] != 0
        jump_lanes = rows[mask][is_nonnull]
        for lane in jump_lanes:
            match = self._scan_backward(lane, int(self.pc[lane]))
            next_pc[lane] = (match + 1) if match is not None else -1
        return next_pc

    def _scan_forward(self, lane: int, loop_start_pc: int) -> int | None:
        tape = self.tapes[lane]
        n = self.length
        depth = 1
        pc = loop_start_pc + 1
        while pc < n:
            byte_op = BYTE_TO_OP_TABLE[tape[pc]]
            if byte_op == int(Op.LOOP_END):
                depth -= 1
                if depth == 0:
                    return pc
            elif byte_op == int(Op.LOOP_START):
                depth += 1
            pc += 1
        return None

    def _scan_backward(self, lane: int, loop_end_pc: int) -> int | None:
        tape = self.tapes[lane]
        depth = 1
        pc = loop_end_pc - 1
        while pc >= 0:
            byte_op = BYTE_TO_OP_TABLE[tape[pc]]
            if byte_op == int(Op.LOOP_START):
                depth -= 1
                if depth == 0:
                    return pc
            elif byte_op == int(Op.LOOP_END):
                depth += 1
            pc -= 1
        return None
