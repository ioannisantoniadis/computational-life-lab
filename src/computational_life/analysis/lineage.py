"""Lineage tracking: parent/child ancestry across epochs.

BffSoupUniverse only ever holds the *current* generation's immediate
parent ids (spec section 7: "do not store unnecessary per-step organism
history in memory"). Reconstructing ancestry across many epochs therefore
requires an explicit, opt-in recorder that snapshots the universe after
each epoch -- this module is that recorder plus the (read-only) queries
over what it has recorded. It never influences the simulation.

Memory cost is O(population_size * epochs_recorded): every organism ever
created gets one entry, because every population slot gets a fresh
organism id every epoch (spec section 9's "epoch = full random
matching"). This is deliberately explicit rather than hidden -- enable
it (spec's ``analysis.lineage_tracking`` config flag) only for runs where
following ancestry is actually worth the memory.
"""

from __future__ import annotations

from ..substrates.bff.universe import BffSoupUniverse


class LineageRecorder:
    def __init__(self) -> None:
        self._parent_of: dict[int, tuple[int, int] | None] = {}
        self._generation_of: dict[int, int] = {}
        self._birth_epoch_of: dict[int, int] = {}
        self._children_of: dict[int, list[int]] | None = None

    def record(self, universe: BffSoupUniverse) -> None:
        """Snapshot every organism currently in ``universe``.

        Safe to call after every :meth:`BffSoupUniverse.step_epoch`, or
        less often (e.g. every checkpoint interval) if full per-epoch
        fidelity isn't needed -- ancestry for organisms born between
        recordings simply won't be captured.
        """
        organism_ids = universe.organism_id.tolist()
        generations = universe.generation.tolist()
        birth_epochs = universe.birth_epoch.tolist()
        parent_pairs = universe.parent_ids.tolist()

        added = False
        for oid, generation, birth_epoch, (p0, p1) in zip(
            organism_ids, generations, birth_epochs, parent_pairs
        ):
            if oid in self._parent_of:
                continue
            self._parent_of[oid] = None if p0 < 0 else (p0, p1)
            self._generation_of[oid] = generation
            self._birth_epoch_of[oid] = birth_epoch
            added = True

        if added:
            self._children_of = None  # invalidate the lazily-built cache

    def __len__(self) -> int:
        return len(self._parent_of)

    def __contains__(self, organism_id: int) -> bool:
        return organism_id in self._parent_of

    def generation(self, organism_id: int) -> int:
        return self._generation_of[organism_id]

    def birth_epoch(self, organism_id: int) -> int:
        return self._birth_epoch_of[organism_id]

    def parents(self, organism_id: int) -> tuple[int, int] | None:
        """Immediate parent ids, or None for an initial-population seed."""
        return self._parent_of[organism_id]

    def ancestors(self, organism_id: int) -> list[int]:
        """All recorded ancestor ids, nearest first, breadth-first."""
        seen: set[int] = set()
        order: list[int] = []
        frontier = [organism_id]
        while frontier:
            next_frontier: list[int] = []
            for oid in frontier:
                parents = self._parent_of.get(oid)
                if not parents:
                    continue
                for parent_id in parents:
                    if parent_id not in seen:
                        seen.add(parent_id)
                        order.append(parent_id)
                        next_frontier.append(parent_id)
            frontier = next_frontier
        return order

    def descendants(self, organism_id: int) -> list[int]:
        """All recorded descendant ids, breadth-first."""
        children_of = self._children_index()
        seen: set[int] = set()
        order: list[int] = []
        frontier = [organism_id]
        while frontier:
            next_frontier: list[int] = []
            for oid in frontier:
                for child_id in children_of.get(oid, ()):
                    if child_id not in seen:
                        seen.add(child_id)
                        order.append(child_id)
                        next_frontier.append(child_id)
            frontier = next_frontier
        return order

    def lineage_depth(self, organism_id: int) -> int:
        """Number of ancestor generations recorded for this organism.

        Equivalent to its generation number, exposed here (rather than
        only on the live universe) so it can be read alongside recorded
        ancestry after the organism's population slot has moved on.
        """
        return self._generation_of[organism_id]

    def _children_index(self) -> dict[int, list[int]]:
        if self._children_of is None:
            index: dict[int, list[int]] = {}
            for oid, parents in self._parent_of.items():
                if not parents:
                    continue
                for parent_id in parents:
                    index.setdefault(parent_id, []).append(oid)
            self._children_of = index
        return self._children_of
