"""Positive control for replication detection: real BFF self-replicators.

The other replication tests show the detector says *no* to inert genomes. These show it
says *yes* to genuine self-replicators that emerged in a primordial soup, so a negative
result from a run means "no replicators", not "a detector or engine bug".

Provenance of the fixtures: the paper authors' reference implementation, cubff
(https://github.com/paradigms-of-intelligence/cubff, commit f212e84, 2025-08-17), built for
CPU (`make CUDA=0`), which reproduced its own `testdata/bff_noheads.txt` golden log exactly.
Run: `--lang bff_noheads --seed 2` with cubff defaults (131,072 programs, mutation 2^-12).
The state transition happened between epochs 11,521 (3 self-replicators by cubff's
CheckSelfRep) and 11,585 (20,462). The three genomes below were drawn from the epoch-11,585
soup and scored 64/64 by this project's detector. Of 3,000 random genomes from that soup,
16.3% (95% CI 15.0-17.7%) scored >= 5 here versus cubff's own 20,462/131,072 = 15.6% at
cubff's threshold (kSelfrepThreshold = 5): the two detectors agree on the population.
"""

import numpy as np
import pytest

from computational_life.analysis.replication import classify, replication_score, replication_scores

CUBFF_SEED2_REPLICATORS = [
    "3c40000000123b6e5b2ca1b6a1a13c367d5d4c4c7dff0a26283636f2dcdcf2363628260ae67d4c4c5d7d363ca1a1b6a12c5b2c002b2f2930008afafa3c3d4f4f",
    "08f63c62624fff123b6e5b2ca1b6a1a13c367d5d4c4c7de60a26283636f2dcdcf2363628260ae67d4c4c5d7d363ca1a1b6a12c5b6e00bf006e00000000003c3b",
    "233c0034005b5b3b6e5b2ca1b6a1a13c367d5d4c4c7de60a26283636f2dcdcf2363628260ae67d4c4c5d7d363ca1a1b6a12c5b6e3b12ff12003cc82020200038",
]


@pytest.mark.parametrize("hex_genome", CUBFF_SEED2_REPLICATORS)
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_real_replicators_score_as_high_fidelity(hex_genome, seed):
    genome = bytes.fromhex(hex_genome)
    assert len(genome) == 64
    score = replication_score(genome, seed=seed)
    assert score >= 58, score
    assert classify(score, 64) == "high-fidelity replicator candidate"


def test_random_genomes_score_zero_where_replicators_score_high():
    rng = np.random.default_rng(0)
    random_scores = replication_scores(rng.integers(0, 256, (20, 64), dtype=np.uint8), seed=0)
    replicators = np.array([list(bytes.fromhex(h)) for h in CUBFF_SEED2_REPLICATORS], dtype=np.uint8)
    replicator_scores = replication_scores(replicators, seed=0)
    assert random_scores.max() < 5 <= replicator_scores.min()
