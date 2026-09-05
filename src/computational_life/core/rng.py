"""Deterministic, substream-based random number generation.

Every experiment accepts a single integer seed. All randomness used
anywhere in the simulation must be drawn from a :class:`RngStreams`
instance derived from that seed -- never from the global ``numpy.random``
or ``random`` state -- so that a run is fully reproducible from
(seed, configuration).

Distinct concerns (population initialization, per-epoch pairing, mutation)
are drawn from independent substreams (via ``SeedSequence.spawn``) so that
enabling/disabling one concern (e.g. mutation) does not perturb the random
sequence used by another (e.g. pairing). This keeps experiments comparable
across configurations that differ only in one axis.
"""

from __future__ import annotations

import numpy as np


class RngStreams:
    """Holds independent, named numpy Generators derived from one seed."""

    def __init__(self, seed: int, *, names: tuple[str, ...] = ("init", "pairing", "mutation")):
        self._seed = seed
        root = np.random.SeedSequence(seed)
        children = root.spawn(len(names))
        self._generators: dict[str, np.random.Generator] = {
            name: np.random.Generator(np.random.PCG64(child))
            for name, child in zip(names, children)
        }

    @property
    def seed(self) -> int:
        return self._seed

    def stream(self, name: str) -> np.random.Generator:
        try:
            return self._generators[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown RNG stream {name!r}; available streams: "
                f"{sorted(self._generators)}"
            ) from exc

    def state(self) -> dict[str, dict]:
        """Serializable snapshot of every substream's internal state."""
        return {name: gen.bit_generator.state for name, gen in self._generators.items()}

    def restore(self, state: dict[str, dict]) -> None:
        """Restore every substream's internal state from :meth:`state`."""
        for name, bit_generator_state in state.items():
            self._generators[name].bit_generator.state = bit_generator_state
