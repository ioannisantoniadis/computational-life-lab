"""The BFF primordial-soup universe: population state + the per-epoch
interaction loop described in the project spec:

    random pairing -> concatenation -> BFF execution -> split -> replacement

One epoch = one full random perfect matching of the population (every
organism interacts with exactly one partner), executed in lockstep via
the vectorized batch interpreter. See docs/bff_semantics.md for why
"epoch" (not "single pairing") is the unit of simulated time -- it
mirrors the reference implementation this spec is derived from and is
what makes the whole population vectorizable.

This module knows nothing about replication, fitness, or species: it only
implements the mechanism (state, interaction, mutation, replacement). Any
classification of what happened belongs in the analysis layer (Phase 3).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...core.organism import Organism
from ...core.rng import RngStreams
from .vectorized import BatchBffInterpreter


@dataclass(frozen=True)
class BffSoupConfig:
    population_size: int = 131_072
    genome_length: int = 64
    max_steps: int = 8192
    mutation_enabled: bool = False
    mutation_rate: float = 0.0
    head_init: str = "zero"
    seed: int = 0

    def __post_init__(self):
        if self.population_size % 2 != 0:
            raise ValueError("population_size must be even (organisms interact in pairs)")
        if not (0.0 <= self.mutation_rate <= 1.0):
            raise ValueError("mutation_rate must be in [0, 1]")


class BffSoupUniverse:
    """State and dynamics for the BFF primordial-soup experiment."""

    def __init__(self, config: BffSoupConfig):
        self.config = config
        self.rng = RngStreams(config.seed)
        n, length = config.population_size, config.genome_length

        self.population = np.empty((n, length), dtype=np.uint8)
        self.organism_id = np.empty(n, dtype=np.int64)
        self.generation = np.zeros(n, dtype=np.int32)
        self.birth_epoch = np.zeros(n, dtype=np.int32)
        self.parent_ids = np.full((n, 2), -1, dtype=np.int64)
        self._next_organism_id = 0
        self.epoch = 0

        self._initialize_population()

    def _initialize_population(self) -> None:
        n, length = self.config.population_size, self.config.genome_length
        init_rng = self.rng.stream("init")
        self.population[...] = init_rng.integers(0, 256, size=(n, length), dtype=np.uint8)
        self.organism_id[:] = np.arange(n, dtype=np.int64)
        self._next_organism_id = n
        self.generation[:] = 0
        self.birth_epoch[:] = 0
        self.parent_ids[:] = -1

    def step_epoch(self) -> None:
        """Advance the universe by exactly one epoch."""
        n, length = self.config.population_size, self.config.genome_length
        pairing_rng = self.rng.stream("pairing")

        permutation = pairing_rng.permutation(n)
        left_idx = permutation[0::2]
        right_idx = permutation[1::2]

        combined = np.concatenate(
            (self.population[left_idx], self.population[right_idx]), axis=1
        )

        if self.config.mutation_enabled and self.config.mutation_rate > 0:
            self._apply_mutation(combined)

        interpreter = BatchBffInterpreter(combined, head_init=self.config.head_init)
        interpreter.run(max_steps=self.config.max_steps)

        new_left = interpreter.tapes[:, :length]
        new_right = interpreter.tapes[:, length:]

        parent_left_id = self.organism_id[left_idx]
        parent_right_id = self.organism_id[right_idx]
        offspring_generation = (
            np.maximum(self.generation[left_idx], self.generation[right_idx]) + 1
        )

        num_pairs = len(left_idx)
        new_ids_left = np.arange(
            self._next_organism_id, self._next_organism_id + num_pairs, dtype=np.int64
        )
        new_ids_right = np.arange(
            self._next_organism_id + num_pairs,
            self._next_organism_id + 2 * num_pairs,
            dtype=np.int64,
        )
        self._next_organism_id += 2 * num_pairs

        self.population[left_idx] = new_left
        self.population[right_idx] = new_right
        self.organism_id[left_idx] = new_ids_left
        self.organism_id[right_idx] = new_ids_right
        self.generation[left_idx] = offspring_generation
        self.generation[right_idx] = offspring_generation
        self.birth_epoch[left_idx] = self.epoch
        self.birth_epoch[right_idx] = self.epoch
        self.parent_ids[left_idx, 0] = parent_left_id
        self.parent_ids[left_idx, 1] = parent_right_id
        self.parent_ids[right_idx, 0] = parent_left_id
        self.parent_ids[right_idx, 1] = parent_right_id

        self.epoch += 1

    def _apply_mutation(self, combined: np.ndarray) -> None:
        """Replace each byte independently with a uniform random byte value,
        with probability ``mutation_rate``. Applied before execution.
        """
        mutation_rng = self.rng.stream("mutation")
        mask = mutation_rng.random(combined.shape) < self.config.mutation_rate
        replacements = mutation_rng.integers(0, 256, size=combined.shape, dtype=np.uint8)
        combined[mask] = replacements[mask]

    def get_organism(self, index: int) -> Organism:
        return Organism(
            organism_id=int(self.organism_id[index]),
            genome=bytes(self.population[index]),
            generation=int(self.generation[index]),
            birth_epoch=int(self.birth_epoch[index]),
            parent_ids=(int(self.parent_ids[index, 0]), int(self.parent_ids[index, 1])),
        )

    def summary(self) -> dict:
        """A minimal, purely descriptive population snapshot.

        This is bookkeeping, not analysis: it does not classify anything
        as a replicator, a species, or a fitness peak. See spec section 3.2.
        """
        genomes = self.population
        _, inverse, counts = np.unique(genomes, axis=0, return_inverse=True, return_counts=True)
        dominant_count = int(counts.max())
        return {
            "epoch": self.epoch,
            "population_size": int(self.config.population_size),
            "unique_genomes": int(len(counts)),
            "dominant_genome_count": dominant_count,
            "dominant_genome_frequency": dominant_count / self.config.population_size,
        }
