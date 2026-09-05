from computational_life.substrates.bff.instruction_set import (
    BYTE_TO_OP_TABLE,
    Op,
    decode,
    encode,
    parse,
)


def test_all_ten_instruction_bytes_decode_correctly():
    expected = {
        ord("["): Op.LOOP_START,
        ord("]"): Op.LOOP_END,
        ord("+"): Op.INC_CELL,
        ord("-"): Op.DEC_CELL,
        ord("."): Op.COPY_0_TO_1,
        ord(","): Op.COPY_1_TO_0,
        ord("<"): Op.DEC_HEAD0,
        ord(">"): Op.INC_HEAD0,
        ord("{"): Op.DEC_HEAD1,
        ord("}"): Op.INC_HEAD1,
    }
    for byte, op in expected.items():
        assert decode(byte) is op


def test_null_byte_is_distinct_from_generic_nop():
    assert decode(0) is Op.NULL
    # A byte value with no assigned meaning is a NOP, not NULL.
    nop_byte = 1
    while decode(nop_byte) is not Op.NOP:
        nop_byte += 1
    assert decode(nop_byte) is Op.NOP
    assert decode(nop_byte) is not Op.NULL


def test_exactly_eleven_bytes_are_not_generic_nop():
    non_nop = [b for b in range(256) if decode(b) is not Op.NOP]
    # 10 instructions + the NULL sentinel.
    assert len(non_nop) == 11


def test_encode_decode_roundtrip_for_instructions():
    for op in [
        Op.LOOP_START,
        Op.LOOP_END,
        Op.INC_CELL,
        Op.DEC_CELL,
        Op.COPY_0_TO_1,
        Op.COPY_1_TO_0,
        Op.DEC_HEAD0,
        Op.INC_HEAD0,
        Op.DEC_HEAD1,
        Op.INC_HEAD1,
        Op.NULL,
    ]:
        assert decode(encode(op)) is op


def test_byte_to_op_table_matches_decode():
    for byte in range(256):
        assert BYTE_TO_OP_TABLE[byte] == int(decode(byte))


def test_parse_source_string():
    genome = parse("[+-.,<>{}]0")
    assert genome == bytes(
        [
            ord("["),
            ord("+"),
            ord("-"),
            ord("."),
            ord(","),
            ord("<"),
            ord(">"),
            ord("{"),
            ord("}"),
            ord("]"),
            0,
        ]
    )


def test_parse_rejects_unknown_characters():
    import pytest

    with pytest.raises(ValueError):
        parse("abc")
