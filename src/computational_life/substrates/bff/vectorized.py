"""Vectorized (batch) BFF interpreter.

Executes many independent tapes in lockstep using NumPy, one instruction
per lane per tick, so that a whole population of pairings can be advanced
without a Python-level loop over organisms. This is a *performance*
component only: its semantics are validated against
:class:`~computational_life.substrates.bff.interpreter.BffInterpreter`
(the scalar oracle) via differential tests, and it must never be treated
as a separate source of truth for BFF semantics.

Bracket matching (``[`` / ``]``) is data-dependent per lane, which made it
the initial Phase 1 implementation's dominant cost: cProfile on a
population of 32,768 showed the naive per-lane Python bracket scan
consuming ~60% of per-epoch time. It is vectorized here using the
classic prefix-sum trick for matching brackets: scoring ``[`` as +1 and
``]`` as -1 and taking a cumulative sum turns "find the matching bracket"
into "find the nearest position (in the right direction) whose prefix
sum equals a target value," which is a handful of elementwise NumPy ops
over the whole batch rather than a per-lane scan loop. See
docs/bff_semantics.md for the full derivation.
"""

from __future__ import annotations

import numpy as np

from .instruction_set import BYTE_TO_OP_TABLE, Op, encode

DEFAULT_MAX_STEPS = 8192

_LOOP_START_BYTE = encode(Op.LOOP_START)
_LOOP_END_BYTE = encode(Op.LOOP_END)


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
        """Vectorized ``[``: skip forward to just past the matching ``]``
        for every lane where tape[head0] is NULL.

        For a lane whose ``[`` sits at position ``p``, define
        ``signed(k) = +1`` if tape[k] is ``[``, ``-1`` if ``]``, else 0, and
        ``depth = cumsum(signed)`` (inclusive). Since depth(p) already
        counts the ``[`` at p itself, the matching ``]`` is the first
        position q > p with depth(q) == depth(p) - 1 (the local nesting
        level returns to what it was just before the ``[``).
        """
        n = self.length
        rows = np.arange(self.num_lanes)
        mask = active & (op == int(Op.LOOP_START))
        if not mask.any():
            return next_pc
        h0 = self.head0[mask] % n
        is_null = self.tapes[rows[mask], h0] == 0
        skip_rows = rows[mask][is_null]
        if skip_rows.size == 0:
            return next_pc

        p = self.pc[skip_rows]
        tape_sub = self.tapes[skip_rows]
        signed = (tape_sub == _LOOP_START_BYTE).astype(np.int32) - (
            tape_sub == _LOOP_END_BYTE
        ).astype(np.int32)
        depth = np.cumsum(signed, axis=1)

        k = np.arange(n)
        target = depth[np.arange(len(skip_rows)), p] - 1
        candidate = (depth == target[:, None]) & (k[None, :] > p[:, None])
        # Smallest matching column, using n (out of range) as "not found".
        first_match = np.where(candidate, k[None, :], n).min(axis=1)
        next_pc[skip_rows] = np.where(first_match < n, first_match + 1, n)
        return next_pc

    def _resolve_loop_end(
        self, active: np.ndarray, op: np.ndarray, next_pc: np.ndarray
    ) -> np.ndarray:
        """Vectorized ``]``: jump back to just past the matching ``[`` for
        every lane where tape[head0] is non-NULL.

        Mirrors :meth:`_resolve_loop_start` using a suffix sum instead of a
        prefix sum: for a ``]`` at position p, the matching ``[`` is the
        nearest position q < p with suffix_sum(q) == suffix_sum(p) + 1.
        """
        n = self.length
        rows = np.arange(self.num_lanes)
        mask = active & (op == int(Op.LOOP_END))
        if not mask.any():
            return next_pc
        h0 = self.head0[mask] % n
        is_nonnull = self.tapes[rows[mask], h0] != 0
        jump_rows = rows[mask][is_nonnull]
        if jump_rows.size == 0:
            return next_pc

        p = self.pc[jump_rows]
        tape_sub = self.tapes[jump_rows]
        signed = (tape_sub == _LOOP_START_BYTE).astype(np.int32) - (
            tape_sub == _LOOP_END_BYTE
        ).astype(np.int32)
        suffix = signed[:, ::-1].cumsum(axis=1)[:, ::-1]

        k = np.arange(n)
        target = suffix[np.arange(len(jump_rows)), p] + 1
        candidate = (suffix == target[:, None]) & (k[None, :] < p[:, None])
        # Largest matching column, using -1 as "not found".
        last_match = np.where(candidate, k[None, :], -1).max(axis=1)
        next_pc[jump_rows] = np.where(last_match >= 0, last_match + 1, -1)
        return next_pc
