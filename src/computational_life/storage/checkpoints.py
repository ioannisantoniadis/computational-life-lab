"""Checkpointing: save and restore a BffSoupUniverse exactly (spec
section 24).

A checkpoint captures everything needed to continue a run as if it had
never stopped: population state, ancestry bookkeeping, the exact RNG
substream state (not just the seed -- position matters), the
configuration, and simulation time. Restoring a checkpoint and
continuing must produce the same subsequent trajectory as an
uninterrupted run.

Stored as a single ``.npz`` file: the bulky per-organism arrays as
native numpy arrays (compressed), plus a small JSON blob (config, RNG
state, counters, software version) embedded as a 0-d array, so a
checkpoint is one self-contained file rather than a pair of files that
could drift apart.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np

from .. import __version__
from ..substrates.bff.universe import BffSoupConfig, BffSoupUniverse


def checkpoint_file_path(path: str | Path) -> Path:
    """The actual filename a checkpoint will be saved/loaded under.

    ``np.savez`` silently appends .npz if missing; normalizing up front
    (and exposing it publicly) means save/load/checkpoint_metadata and
    any caller that needs to know the real on-disk name -- e.g. to record
    it in an event log -- all agree, rather than each re-deriving it (or
    naively concatenating ".npz", which double-appends when the given
    path already ends in .npz).
    """
    path = Path(path)
    return path if path.suffix == ".npz" else path.with_suffix(path.suffix + ".npz")


def save_checkpoint(universe: BffSoupUniverse, path: str | Path) -> None:
    metadata = {
        "software_version": __version__,
        "epoch": universe.epoch,
        "next_organism_id": universe._next_organism_id,
        "config": dataclasses.asdict(universe.config),
        "rng_state": universe.rng.state(),
    }
    np.savez_compressed(
        checkpoint_file_path(path),
        population=universe.population,
        organism_id=universe.organism_id,
        generation=universe.generation,
        birth_epoch=universe.birth_epoch,
        parent_ids=universe.parent_ids,
        metadata=np.array(json.dumps(metadata)),
    )


def load_checkpoint(path: str | Path) -> BffSoupUniverse:
    with np.load(checkpoint_file_path(path), allow_pickle=False) as data:
        metadata = json.loads(str(data["metadata"]))
        config = BffSoupConfig(**metadata["config"])
        return BffSoupUniverse.from_state(
            config,
            population=data["population"].copy(),
            organism_id=data["organism_id"].copy(),
            generation=data["generation"].copy(),
            birth_epoch=data["birth_epoch"].copy(),
            parent_ids=data["parent_ids"].copy(),
            next_organism_id=int(metadata["next_organism_id"]),
            epoch=int(metadata["epoch"]),
            rng_state=metadata["rng_state"],
        )


def checkpoint_metadata(path: str | Path) -> dict:
    """Read a checkpoint's metadata without loading the full population."""
    with np.load(checkpoint_file_path(path), allow_pickle=False) as data:
        return json.loads(str(data["metadata"]))
