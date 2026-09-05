"""Scalar (single-tape) BFF interpreter.

This is the correctness oracle: a plain, easy-to-read, exhaustively tested
reference implementation of BFF execution over one tape. It is also the
backend for the execution debugger (spec section 12), since it exposes a
fully inspectable state and a single-instruction ``step()``.

It is intentionally not optimized: the vectorized batch interpreter used
by the actual soup experiment (substrates/bff/vectorized.py) is validated
against this implementation via differential testing, never trusted on
its own. See docs/bff_semantics.md for the semantic decisions encoded
here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .instruction_set import Op, decode

DEFAULT_MAX_STEPS = 8192


@dataclass(frozen=True)
class ExecutionState:
    """An inspectable snapshot of interpreter state."""

    tape: bytes
    instruction_pointer: int
    head0: int
    head1: int
    step_count: int
    halted: bool
    current_instruction: Op | None


class BffInterpreter:
    """Executes one BFF tape, instruction by instruction.

    Parameters
    ----------
    tape:
        The combined program/data tape. Mutated in place as execution
        proceeds (BFF is self-modifying by construction).
    head_init:
        ``"zero"`` (the "bff_noheads" reference variant, used as the
        Phase 1 default): head0 = head1 = 0, instruction pointer starts
        at 0. ``"from_tape"`` (the "bff" reference variant): head0 and
        head1 are read from tape[0] and tape[1] respectively (wrapped
        into range), and the instruction pointer starts at 2 so those
        two bytes are not themselves executed.
    """

    def __init__(self, tape: bytearray | bytes, *, head_init: str = "zero"):
        if head_init not in ("zero", "from_tape"):
            raise ValueError(f"Unknown head_init strategy: {head_init!r}")
        self._initial_tape = bytes(tape)
        self._head_init = head_init
        self.tape = bytearray(tape)
        self.head0 = 0
        self.head1 = 0
        self.pc = 0
        self.step_count = 0
        self.halted = False
        self.reset()

    def reset(self) -> None:
        """Restore the tape to its initial contents and rewind execution."""
        self.tape = bytearray(self._initial_tape)
        n = len(self.tape)
        if self._head_init == "zero":
            self.head0 = 0
            self.head1 = 0
            self.pc = 0
        else:
            self.head0 = self.tape[0] % n
            self.head1 = self.tape[1] % n
            self.pc = 2
        self.step_count = 0
        self.halted = False

    @property
    def state(self) -> ExecutionState:
        current = decode(self.tape[self.pc]) if not self.halted else None
        return ExecutionState(
            tape=bytes(self.tape),
            instruction_pointer=self.pc,
            head0=self.head0,
            head1=self.head1,
            step_count=self.step_count,
            halted=self.halted,
            current_instruction=current,
        )

    def step(self) -> bool:
        """Execute exactly one instruction.

        Returns True if an instruction was executed, False if the
        interpreter was already halted (a no-op in that case).
        """
        if self.halted:
            return False

        n = len(self.tape)
        cmd = self.tape[self.pc]
        op = decode(cmd)
        next_pc = self.pc + 1  # default: advance by one, as in plain BF

        if op is Op.DEC_HEAD0:
            self.head0 -= 1
        elif op is Op.INC_HEAD0:
            self.head0 += 1
        elif op is Op.DEC_HEAD1:
            self.head1 -= 1
        elif op is Op.INC_HEAD1:
            self.head1 += 1
        elif op is Op.INC_CELL:
            self.tape[self.head0 % n] = (self.tape[self.head0 % n] + 1) % 256
        elif op is Op.DEC_CELL:
            self.tape[self.head0 % n] = (self.tape[self.head0 % n] - 1) % 256
        elif op is Op.COPY_0_TO_1:
            self.tape[self.head1 % n] = self.tape[self.head0 % n]
        elif op is Op.COPY_1_TO_0:
            self.tape[self.head0 % n] = self.tape[self.head1 % n]
        elif op is Op.LOOP_START:
            if decode(self.tape[self.head0 % n]) is Op.NULL:
                match = self._scan_forward(self.pc)
                next_pc = (match + 1) if match is not None else n  # halt: out of range
        elif op is Op.LOOP_END:
            if decode(self.tape[self.head0 % n]) is not Op.NULL:
                match = self._scan_backward(self.pc)
                # Landing position is just *after* the matching '[' (it is
                # not re-executed), mirroring the reference implementation.
                next_pc = (match + 1) if match is not None else -1  # halt: unmatched
        # Op.NULL and Op.NOP: no effect on state beyond advancing pc.

        self.head0 %= n
        self.head1 %= n
        self.pc = next_pc
        self.step_count += 1
        if self.pc < 0 or self.pc >= n:
            self.halted = True
        return True

    def run(self, max_steps: int = DEFAULT_MAX_STEPS) -> int:
        """Execute up to ``max_steps`` further instructions.

        Stops early if the tape halts (instruction pointer runs off
        either end, including via an unmatched loop bracket). Returns
        the number of instructions actually executed.
        """
        executed = 0
        while executed < max_steps and self.step():
            executed += 1
        return executed

    def _scan_forward(self, loop_start_pc: int) -> int | None:
        """Find the index of the ``]`` matching the ``[`` at loop_start_pc.

        Scans forward without wraparound; returns None if the tape ends
        before a match is found (an unmatched bracket halts execution,
        it is not treated as a NOP and does not search past the tape end).
        """
        depth = 1
        pc = loop_start_pc + 1
        n = len(self.tape)
        while pc < n:
            op = decode(self.tape[pc])
            if op is Op.LOOP_END:
                depth -= 1
                if depth == 0:
                    return pc
            elif op is Op.LOOP_START:
                depth += 1
            pc += 1
        return None

    def _scan_backward(self, loop_end_pc: int) -> int | None:
        """Find the index of the ``[`` matching the ``]`` at loop_end_pc."""
        depth = 1
        pc = loop_end_pc - 1
        while pc >= 0:
            op = decode(self.tape[pc])
            if op is Op.LOOP_START:
                depth -= 1
                if depth == 0:
                    return pc
            elif op is Op.LOOP_END:
                depth += 1
            pc -= 1
        return None
