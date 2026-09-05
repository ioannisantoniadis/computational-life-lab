"""Complexity proxies.

Per spec section 14: "Do not label any one proxy 'the complexity of the
organism'. Call them explicitly 'complexity proxies'." None of the
functions here measure complexity in any absolute sense -- they are
cheap, well-defined statistics that may *correlate* with interesting
structure, nothing more.

``compressed_bits_per_byte`` and ``structural_redundancy`` are adapted
directly from the reference cubff implementation's own instrumentation
(``RunSimulation`` in ``common_language.h`` computes a Brotli-compressed
size and ``higher_entropy = h0 - brotli_bpb`` every ``callback_interval``
epochs). This project uses ``zlib`` (Python's standard library) instead
of Brotli to avoid adding a new dependency (spec section 4: "keep
dependencies minimal") -- the qualitative interpretation is the same,
the absolute numbers are not comparable between the two compressors.
"""

from __future__ import annotations

import zlib

import numpy as np

from .entropy import byte_entropy


def compressed_bits_per_byte(population: np.ndarray) -> float:
    """Compressed size of the whole population, in bits per original byte.

    A population that is mostly random bytes compresses poorly (close to
    8 bits/byte); a population containing many repeated genomes or
    repeated substrings (e.g. from copying) compresses much better. This
    is a proxy for redundancy/structure in the population as a whole, not
    a measurement of any single organism.
    """
    raw = population.tobytes()
    if len(raw) == 0:
        return 0.0
    compressed = zlib.compress(raw, level=6)
    return len(compressed) * 8.0 / len(raw)


def structural_redundancy(population: np.ndarray) -> float:
    """byte_entropy(population) - compressed_bits_per_byte(population).

    Byte-frequency entropy alone only sees *which* byte values are common,
    not repeated *patterns* (e.g. the same 64-byte genome appearing many
    times, or a substring copied across genomes). A real compressor
    exploits those patterns too, so a large positive gap between the two
    numbers suggests structure beyond a flat byte-value distribution --
    worth a closer look, not proof of anything. Can be negative for tiny
    populations where compression overhead dominates.
    """
    return byte_entropy(population) - compressed_bits_per_byte(population)
