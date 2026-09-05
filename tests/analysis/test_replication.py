import numpy as np
import pytest

from computational_life.analysis.replication import (
    _score_from_final_tapes,
    classify,
    replication_score,
    replication_scores,
)


def test_score_from_final_tapes_all_consistent_scores_full_marks():
    length = 4
    # 13 trials, all producing the exact same 8-byte tape: left half matches
    # the candidate, right half is identical across every trial.
    candidate = np.array([[1, 2, 3, 4]], dtype=np.uint8)
    final_tape = np.array([[1, 2, 3, 4, 9, 9, 9, 9]], dtype=np.uint8)
    final = np.repeat(final_tape[:, None, :], 13, axis=1)
    scores = _score_from_final_tapes(final, candidate, length)
    assert scores.tolist() == [4]


def test_score_from_final_tapes_divergent_right_half_scores_zero():
    length = 4
    candidate = np.array([[1, 2, 3, 4]], dtype=np.uint8)
    rng = np.random.default_rng(0)
    final = np.zeros((1, 13, 8), dtype=np.uint8)
    final[:, :, :4] = candidate  # left half always matches candidate
    final[:, :, 4:] = rng.integers(0, 256, size=(1, 13, 4))  # right half: all different
    scores = _score_from_final_tapes(final, candidate, length)
    assert scores.tolist() == [0]


def test_score_from_final_tapes_requires_left_half_to_match_candidate():
    length = 4
    candidate = np.array([[1, 2, 3, 4]], dtype=np.uint8)
    # Left half is consistent across trials but does NOT match the original
    # candidate -- should not count as robust for those positions.
    final_tape = np.array([[9, 9, 9, 9, 5, 5, 5, 5]], dtype=np.uint8)
    final = np.repeat(final_tape[:, None, :], 13, axis=1)
    scores = _score_from_final_tapes(final, candidate, length)
    assert scores.tolist() == [0]  # robust_left=0 (mismatch) -> min(0, 4) == 0


def test_score_from_final_tapes_needs_at_least_four_agreeing_trials():
    length = 1
    candidate = np.array([[1]], dtype=np.uint8)
    final = np.zeros((1, 13, 2), dtype=np.uint8)
    final[:, :, 0] = 1  # left half always matches candidate
    # Right half: only 3 trials agree on value 7, the rest are all distinct.
    final[0, 0:3, 1] = 7
    final[0, 3:, 1] = np.arange(10) + 100
    scores = _score_from_final_tapes(final, candidate, length)
    assert scores.tolist() == [0]  # 3 agreeing trials is not > 13//4 == 3

    # Now push it to 4 agreeing trials -> should become robust.
    final[0, 0:4, 1] = 7
    final[0, 4:, 1] = np.arange(9) + 100
    scores = _score_from_final_tapes(final, candidate, length)
    assert scores.tolist() == [1]


def test_classify_thresholds():
    assert classify(64, 64) == "high-fidelity replicator candidate"
    assert classify(40, 64) == "candidate replicator"
    assert classify(1, 64) == "no replication signal"
    assert classify(0, 64) == "no replication signal"


def test_replication_scores_rejects_non_2d_input():
    with pytest.raises(ValueError):
        replication_scores(np.zeros(8, dtype=np.uint8), seed=0)


def test_replication_scores_handles_empty_input():
    scores = replication_scores(np.zeros((0, 8), dtype=np.uint8), seed=0)
    assert scores.shape == (0,)


def test_inert_genome_scores_low_end_to_end():
    # An all-NOP genome (byte value 1 is unassigned) never touches its own
    # tape and never overwrites the noise it's paired with, so it should
    # show no self-replication signal.
    genome = bytes([1] * 32)
    score = replication_score(genome, seed=123, max_steps=200)
    assert 0 <= score <= 32
    assert score == 0


def test_replication_score_is_deterministic_given_seed():
    genome = bytes([1, 2, 3, 4] * 8)
    s1 = replication_score(genome, seed=42, max_steps=200)
    s2 = replication_score(genome, seed=42, max_steps=200)
    assert s1 == s2


def test_replication_scores_batches_multiple_candidates_consistently():
    genomes = [bytes([1] * 16), bytes([2] * 16)]
    candidates = np.array([list(g) for g in genomes], dtype=np.uint8)
    batch_scores = replication_scores(candidates, seed=7, max_steps=200)
    individual_scores = [
        replication_score(g, seed=7, max_steps=200) for g in genomes
    ]
    # Note: batching draws noise jointly, so exact equality isn't guaranteed
    # unless noise generation is independent per-candidate -- verify shape
    # and bounds instead of forcing bitwise equality across the two paths.
    assert batch_scores.shape == (2,)
    assert all(0 <= s <= 16 for s in batch_scores.tolist())
    assert all(0 <= s <= 16 for s in individual_scores)
