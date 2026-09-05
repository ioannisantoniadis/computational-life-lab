"""Replication detection: an analysis module, not a simulation mechanism
(spec section 13). Nothing here feeds back into BffSoupUniverse.

The scoring method is adapted from the reference cubff implementation's
own operational definition of a candidate replicator (``CheckSelfRep`` in
``common_language.h``), which is how the numbers in the "Computational
Life" paper (e.g. "self-replicators emerged in ~40% of runs") were
actually produced -- this is not a method invented for this project.

## The method

For a candidate 64-byte genome, run ``num_trials`` (13, matching the
reference) independent trials. Each trial:

1. Pair the candidate with a fresh random 64-byte "noise" genome and
   execute BFF for ``max_steps``.
2. Repeat ``num_extra_generations`` (4) more times: take the resulting
   right half as the new left half, pair it with the *same* noise
   genome again, and execute again.

After all trials, for each of the 128 final byte positions, check
whether there is *some* trial whose value at that position (a) matches
the original candidate, if the position is in the left half, and
(b) recurs in at least 4 of the 13 trials. Positions satisfying this are
"robust": they come out the same regardless of which random genome the
candidate was paired against, which is what a genuinely
partner-independent self-copier should look like. The final score is
the minimum of (robust positions in the left half, robust positions in
the right half), an integer in [0, 64].

This is a heuristic consistent with the reference's own methodology, not
a proof of self-replication -- see spec section 13's instruction to
avoid claiming more than a detector actually supports.

Randomness here uses this project's own seeded NumPy generator (not a
bit-for-bit port of the reference's SplitMix64 noise stream) -- see
docs/bff_semantics.md's RNG note. Scores from this implementation are
reproducible given (genomes, seed) but are not expected to numerically
match cubff's own CheckSelfRep output for the "same" seed.
"""

from __future__ import annotations

import numpy as np

from ..substrates.bff.vectorized import BatchBffInterpreter

DEFAULT_NUM_TRIALS = 13
DEFAULT_NUM_EXTRA_GENERATIONS = 4
DEFAULT_MAX_STEPS = 8192


def replication_scores(
    candidates: np.ndarray,
    *,
    seed: int,
    max_steps: int = DEFAULT_MAX_STEPS,
    num_trials: int = DEFAULT_NUM_TRIALS,
    num_extra_generations: int = DEFAULT_NUM_EXTRA_GENERATIONS,
    head_init: str = "zero",
) -> np.ndarray:
    """Replication score (0..genome_length) for every candidate genome.

    ``candidates`` is a ``(K, genome_length)`` uint8 array. Returns an
    integer array of shape ``(K,)``.
    """
    if candidates.ndim != 2:
        raise ValueError("candidates must be a 2D (K, genome_length) array")
    num_candidates, length = candidates.shape
    if num_candidates == 0:
        return np.zeros(0, dtype=np.int64)

    rng = np.random.default_rng(seed)
    noise = rng.integers(0, 256, size=(num_candidates, num_trials, length), dtype=np.uint8)

    # Lane layout: num_candidates * num_trials independent (candidate, noise) pairs.
    left = np.repeat(candidates, num_trials, axis=0)
    right = noise.reshape(num_candidates * num_trials, length)
    tapes = np.concatenate([left, right], axis=1)

    interpreter = BatchBffInterpreter(tapes, head_init=head_init)
    interpreter.run(max_steps=max_steps)

    for _ in range(num_extra_generations):
        new_left = interpreter.tapes[:, length:]
        new_tapes = np.concatenate([new_left, right], axis=1)
        interpreter = BatchBffInterpreter(new_tapes, head_init=head_init)
        interpreter.run(max_steps=max_steps)

    final = interpreter.tapes.reshape(num_candidates, num_trials, 2 * length)
    return _score_from_final_tapes(final, candidates, length)


def replication_score(genome: bytes, *, seed: int, **kwargs) -> int:
    """Convenience wrapper of :func:`replication_scores` for one genome."""
    candidates = np.frombuffer(genome, dtype=np.uint8).reshape(1, -1)
    return int(replication_scores(candidates, seed=seed, **kwargs)[0])


def _score_from_final_tapes(
    final: np.ndarray, candidates: np.ndarray, length: int
) -> np.ndarray:
    """Vectorized version of the reference's per-position consistency scan.

    ``final`` has shape (K, num_trials, 2*length).
    """
    num_candidates, num_trials, tape_len = final.shape
    min_agreeing = num_trials // 4  # reference: "count > kNumIters / 4"

    # equal[k, a, b, i] = final[k, a, i] == final[k, b, i]
    equal = final[:, :, None, :] == final[:, None, :, :]
    upper = np.triu(np.ones((num_trials, num_trials), dtype=bool), k=1)
    # agreement_count[k, a, i] = 1 (itself) + count of b > a agreeing with a.
    agreement_count = 1 + np.count_nonzero(equal & upper[None, :, :, None], axis=2)

    matches_candidate = np.ones((num_candidates, num_trials, tape_len), dtype=bool)
    matches_candidate[:, :, :length] = final[:, :, :length] == candidates[:, None, :]

    valid = (agreement_count > min_agreeing) & matches_candidate
    position_is_robust = valid.any(axis=1)  # (K, tape_len)

    robust_left = position_is_robust[:, :length].sum(axis=1)
    robust_right = position_is_robust[:, length:].sum(axis=1)
    return np.minimum(robust_left, robust_right)


def classify(score: int, genome_length: int, *, high_fidelity_threshold: float = 0.9,
             candidate_threshold: float = 0.5) -> str:
    """Map a replication score to a human-readable label.

    Purely a labeling convenience over a configurable threshold -- an
    analytical classification, not an intrinsic simulator property (spec
    section 13). Callers needing different cutoffs should call
    :func:`replication_scores` directly rather than relying on this
    function's defaults.
    """
    fraction = score / genome_length if genome_length else 0.0
    if fraction >= high_fidelity_threshold:
        return "high-fidelity replicator candidate"
    if fraction >= candidate_threshold:
        return "candidate replicator"
    return "no replication signal"
