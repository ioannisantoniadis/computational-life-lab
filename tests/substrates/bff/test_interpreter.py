import pytest

from computational_life.substrates.bff.instruction_set import parse
from computational_life.substrates.bff.interpreter import BffInterpreter


def make(source: str, length: int = 16, head_init: str = "zero") -> BffInterpreter:
    genome = bytearray(length)
    parsed = parse(source)
    genome[: len(parsed)] = parsed
    return BffInterpreter(genome, head_init=head_init)


def test_head0_moves_right_and_left():
    interp = make(">>><")
    interp.step()
    assert interp.head0 == 1
    interp.step()
    assert interp.head0 == 2
    interp.step()
    assert interp.head0 == 3
    interp.step()
    assert interp.head0 == 2


def test_head1_moves_right_and_left():
    interp = make("}}}{")
    interp.step()
    assert interp.head1 == 1
    interp.step()
    assert interp.head1 == 2
    interp.step()
    assert interp.head1 == 3
    interp.step()
    assert interp.head1 == 2


def test_head0_wraps_around_tape_bounds():
    interp = make("<", length=8)
    interp.step()
    assert interp.head0 == 7  # wrapped from 0 to length-1


def test_head0_wraps_forward_past_end():
    interp = make(">" * 8, length=8, head_init="zero")
    for _ in range(8):
        interp.step()
    assert interp.head0 == 0  # wrapped back to 0 after 8 increments


def test_increment_wraps_byte_value_at_255():
    # index0 is the data cell head0 points at (kept separate from pc=0's
    # own instruction byte, which would otherwise be clobbered by the write).
    genome = bytearray([0, ord("+")])
    interp = BffInterpreter(genome)
    interp.tape[0] = 255
    interp.step()  # pc=0: NULL data byte -> no-op, pc -> 1
    interp.step()  # pc=1: '+' -> tape[head0=0] 255 -> 0
    assert interp.tape[0] == 0


def test_decrement_wraps_byte_value_at_0():
    genome = bytearray([0, ord("-")])
    interp = BffInterpreter(genome)
    interp.step()  # pc=0: NULL data byte -> no-op, pc -> 1
    interp.step()  # pc=1: '-' -> tape[head0=0] 0 -> 255
    assert interp.tape[0] == 255


def test_copy_head0_to_head1():
    # index0: data value (byte 42 is unassigned -> also a harmless NOP when
    # executed as pc's first instruction). head0 stays here the whole time.
    # index1: '}' moves head1 to index1. index2: '.' copies head0 -> head1.
    genome = bytearray([42, ord("}"), ord(".")])
    interp = BffInterpreter(genome)
    interp.step()  # pc=0: NOP
    interp.step()  # '}': head1 -> 1
    assert interp.head1 == 1
    interp.step()  # '.': tape[head1=1] = tape[head0=0] = 42
    assert interp.tape[1] == 42


def test_copy_head1_to_head0():
    # index0: data value. head1 stays here. index1: '>' moves head0 to
    # index1. index2: ',' copies head1 -> head0.
    genome = bytearray([99, ord(">"), ord(",")])
    interp = BffInterpreter(genome)
    interp.step()  # pc=0: NOP
    interp.step()  # '>': head0 -> 1
    assert interp.head0 == 1
    interp.step()  # ',': tape[head0=1] = tape[head1=0] = 99
    assert interp.tape[1] == 99


def test_nop_bytes_advance_pc_without_side_effects():
    genome = bytearray([5, 5, 5])  # byte value 5 is unassigned -> NOP
    interp = BffInterpreter(genome)
    state_before = bytes(interp.tape)
    interp.step()
    assert bytes(interp.tape) == state_before
    assert interp.pc == 1
    assert interp.head0 == 0 and interp.head1 == 0


def test_loop_skips_forward_when_head0_byte_is_null():
    # index0: NULL data cell that head0 points at for the whole program.
    # index1..5: '[' '+' '+' ']' '+'
    genome = bytearray(8)
    genome[1] = ord("[")
    genome[2] = ord("+")
    genome[3] = ord("+")
    genome[4] = ord("]")
    genome[5] = ord("+")
    interp = BffInterpreter(genome)
    interp.step()  # pc=0: tape[0]==NULL -> no-op, pc -> 1
    assert interp.pc == 1
    interp.step()  # '[' with tape[head0=0]==NULL -> skip to just after ']'
    assert interp.pc == 5  # index of the '+' right after ']'
    assert interp.tape[0] == 0  # the two '+' inside the loop never ran (head0 untouched)


def test_loop_enters_body_when_head0_byte_is_nonzero():
    # head0 stays at index 0, which holds '>' itself (nonzero byte) -> loop entered.
    genome = parse("[+]")
    interp = BffInterpreter(genome)
    interp.step()  # '[' ; tape[head0=0] == ord('[') != NULL -> enter body
    assert interp.pc == 1


def test_loop_end_jumps_back_when_condition_holds_then_falls_through():
    # index0: data cell that head0 points at for the whole program (starts NULL).
    # index1..4: '+' '[' '-' ']'
    genome = bytearray(5)
    genome[1] = ord("+")
    genome[2] = ord("[")
    genome[3] = ord("-")
    genome[4] = ord("]")
    interp = BffInterpreter(genome)
    interp.step()  # pc=0: tape[0]==NULL -> no-op, pc -> 1
    assert interp.pc == 1
    interp.step()  # '+': tape[head0=0] 0 -> 1
    assert interp.tape[0] == 1
    assert interp.pc == 2
    interp.step()  # '[': tape[head0]=1 != NULL -> enter body, pc -> 3
    assert interp.pc == 3
    interp.step()  # '-': tape[0] 1 -> 0
    assert interp.tape[0] == 0
    assert interp.pc == 4
    interp.step()  # ']': tape[head0]=0 == NULL -> do NOT jump back, fall through
    assert interp.pc == 5
    assert interp.halted is True  # pc == len(tape) -> halted


def test_unmatched_loop_start_halts_execution():
    genome = bytearray([0, ord("[")])  # tape[head0]==0 (NULL) -> tries to skip, no ']'
    interp = BffInterpreter(genome)
    interp.step()  # NOP (byte 0 as instruction is NULL -> also a no-effect op)
    executed = interp.step()
    assert executed is True
    assert interp.halted is True


def test_unmatched_loop_end_halts_execution():
    genome = bytearray([ord("+"), ord("]")])  # tape[head0] becomes nonzero -> tries to jump back
    interp = BffInterpreter(genome)
    interp.step()  # '+'
    interp.step()  # ']': no matching '[' -> halt
    assert interp.halted is True


def test_self_modification_changes_upcoming_instruction():
    interp = BffInterpreter(bytearray(4))
    # Manually drive a self-modification: head0 at 0 holds the NEXT instruction (index 1).
    interp.head0 = 1
    interp.tape[2] = ord(">")  # source of the copy
    interp.head1 = 2
    interp.tape[0] = ord(",")  # ',' copies tape[head1] -> tape[head0] = tape[1]
    assert interp.tape[1] == 0
    interp.step()  # executes ',' at pc=0: tape[1] = tape[2] = '>'
    assert interp.tape[1] == ord(">")
    interp.step()  # now executes the '>' we just wrote
    assert interp.head0 == 2


def test_run_executes_up_to_max_steps_then_stops_without_halting():
    interp = make(">" * 100, length=200)
    executed = interp.run(max_steps=10)
    assert executed == 10
    assert interp.halted is False
    assert interp.head0 == 10


def test_run_stops_early_on_halt():
    # Single-byte tape holding ']' itself: tape[head0] is the ']' byte, which
    # is non-NULL, so a backward jump is attempted; with no '[' present the
    # scan runs off the tape and execution halts on the very first step.
    genome = bytearray([ord("]")])
    interp = BffInterpreter(genome)
    executed = interp.run(max_steps=100)
    assert executed == 1
    assert interp.halted is True


def test_reset_restores_initial_tape_and_zeroes_counters():
    interp = make(">>>")
    interp.run(max_steps=3)
    assert interp.step_count == 3
    interp.reset()
    assert interp.step_count == 0
    assert interp.head0 == 0
    assert interp.head1 == 0
    assert interp.pc == 0
    assert interp.halted is False


def test_head_init_from_tape_reads_first_two_bytes_and_skips_them():
    genome = bytearray(8)
    genome[0] = 3  # head0 initial position
    genome[1] = 5  # head1 initial position
    interp = BffInterpreter(genome, head_init="from_tape")
    assert interp.head0 == 3
    assert interp.head1 == 5
    assert interp.pc == 2


def test_head_init_from_tape_wraps_large_values():
    genome = bytearray(8)
    genome[0] = 250  # 250 % 8 == 2
    interp = BffInterpreter(genome, head_init="from_tape")
    assert interp.head0 == 2


def test_state_snapshot_reports_current_instruction():
    interp = make(">")
    assert interp.state.current_instruction is not None
    assert interp.state.step_count == 0
    interp.step()
    assert interp.state.step_count == 1


def test_step_on_halted_interpreter_is_a_noop_and_returns_false():
    genome = bytearray([ord("]")])
    interp = BffInterpreter(genome)
    interp.step()
    assert interp.halted is True
    result = interp.step()
    assert result is False
    assert interp.step_count == 1  # did not advance further


def test_unknown_head_init_strategy_rejected():
    with pytest.raises(ValueError):
        BffInterpreter(bytearray(4), head_init="bogus")
