"""A read-only view of a single organism's state.

The population itself is stored as plain NumPy arrays (see
substrates/bff/universe.py) so that a population of hundreds of thousands
of organisms does not require hundreds of thousands of Python objects.
:class:`Organism` is a lightweight, on-demand snapshot of one slot,
constructed only when something (a debugger, a genome inspector, a test)
needs to look at a single organism -- never stored in bulk.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Organism:
    organism_id: int
    genome: bytes
    generation: int
    birth_epoch: int
    parent_ids: tuple[int, int]
