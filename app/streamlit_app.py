"""Computational Life Lab -- live experiment dashboard (Phase 2, first slice).

Watches a BffSoupUniverse evolve: a population grid colored by genome
identity, and basic population/diversity metrics over time. This page
contains no simulation logic of its own -- it only calls the same
headless engine the CLI uses (computational_life.substrates.bff.universe),
so a run started here and a run started via `life run` with the same
config and seed produce identical trajectories (spec section 3.4).
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from rendering import (
    instruction_distribution,
    lineage_graph,
    population_to_highlight_grid,
    render_tape_html,
    select_display_sample,
)

from computational_life.analysis.lineage import LineageRecorder
from computational_life.analysis.replication import classify, replication_score, replication_scores
from computational_life.experiments.base import BffSoupExperimentConfig, load_bff_soup_config
from computational_life.experiments.bff_soup import compute_metrics
from computational_life.storage.checkpoints import checkpoint_file_path, load_checkpoint, save_checkpoint
from computational_life.storage.database import RunStore
from computational_life.substrates.bff.interpreter import BffInterpreter
from computational_life.substrates.bff.universe import BffSoupUniverse

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIGS_DIR = REPO_ROOT / "experiments" / "configs"
RUNS_DIR = REPO_ROOT / "runs"

st.set_page_config(page_title="Computational Life Lab", layout="wide")


def _available_configs() -> list[str]:
    return sorted(p.name for p in CONFIGS_DIR.glob("*.yaml"))


def _init_universe(config_name: str, seed_override: int | None) -> None:
    config = load_bff_soup_config(CONFIGS_DIR / config_name)
    if seed_override is not None:
        import dataclasses

        config = dataclasses.replace(
            config, universe=dataclasses.replace(config.universe, seed=seed_override)
        )
    st.session_state.config = config
    st.session_state.config_name = config_name
    st.session_state.universe = BffSoupUniverse(config.universe)
    st.session_state.history = [compute_metrics(st.session_state.universe)]
    st.session_state.playing = False
    st.session_state.scan_results = None
    st.session_state.loaded_run_info = None
    st.session_state.inspector_index = 0
    st.session_state.auto_scan_last_result = None
    st.session_state.auto_scan_first_detected_epoch = None
    st.session_state.auto_checkpoint_run_info = None
    st.session_state.auto_checkpoint_last_epoch = None
    if st.session_state.get("track_lineage"):
        recorder = LineageRecorder()
        recorder.record(st.session_state.universe)
        st.session_state.lineage_recorder = recorder
    else:
        st.session_state.lineage_recorder = None


def _load_stored_run(db_path: Path, run_id: int) -> None:
    """Load a previously saved run's full metrics history and, if it has
    one, its latest checkpoint -- so a run started via `life run`/`life
    sweep` hours or days ago can be inspected and continued here, not
    just read back as text (spec section 26's "compare historical runs").
    """
    with RunStore(db_path) as store:
        run = store.get_run(run_id)
        events = store.get_events(run_id)
        history = store.get_metrics_history(run_id)

    checkpoint_events = [e for e in events if e["kind"] == "checkpoint_saved"]
    if not checkpoint_events:
        raise LookupError(
            f"Run {run_id} ({run['experiment_name']}) has no saved checkpoint -- only its "
            "metrics history can be shown, not its population. Re-run with --checkpoint-dir "
            "or --save-checkpoint to make it fully loadable here."
        )
    latest = max(checkpoint_events, key=lambda e: e["epoch"])
    universe = load_checkpoint(latest["payload"]["path"])

    st.session_state.universe = universe
    st.session_state.config = BffSoupExperimentConfig(
        name=run["experiment_name"],
        seed=universe.config.seed,
        universe=universe.config,
        epochs=0,
        report_interval=1,
    )
    st.session_state.history = history if history else [compute_metrics(universe)]
    st.session_state.playing = False
    st.session_state.scan_results = None
    st.session_state.lineage_recorder = None
    st.session_state.inspector_index = 0
    st.session_state.auto_scan_last_result = None
    st.session_state.auto_scan_first_detected_epoch = None
    st.session_state.auto_checkpoint_run_info = None
    st.session_state.auto_checkpoint_last_epoch = None
    st.session_state.loaded_run_info = {
        "db_path": str(db_path),
        "run_id": run_id,
        "experiment_name": run["experiment_name"],
        "checkpoint_epoch": latest["epoch"],
        "checkpoint_path": latest["payload"]["path"],
    }


def _maybe_auto_scan(universe: BffSoupUniverse) -> None:
    """If auto-scan is enabled and this epoch is due, run the same
    replication-consistency check `life run --replication-scan-interval`
    does, record the result, and flag the first epoch a candidate is
    seen. If this session was loaded from a stored run (so a database
    and run id are known), also persist the scan and any first-detection
    as real events -- otherwise it's shown live but not written anywhere,
    same as the manual "Scan for candidate replicators" section below.
    """
    if not st.session_state.get("auto_scan"):
        return
    interval = st.session_state.get("auto_scan_interval", 100)
    if universe.epoch % interval != 0:
        return

    population_size = universe.config.population_size
    sample_size = min(st.session_state.get("auto_scan_sample_size", 200), population_size)
    scan_seed = universe.config.seed ^ universe.epoch
    sample_idx = np.random.default_rng(scan_seed).choice(
        population_size, size=sample_size, replace=False
    )
    scores = replication_scores(
        universe.population[sample_idx], seed=scan_seed, max_steps=universe.config.max_steps
    )
    best_score = int(scores.max())
    genome_length = universe.config.genome_length
    label = classify(best_score, genome_length)
    st.session_state.auto_scan_last_result = {
        "epoch": universe.epoch,
        "best_score": best_score,
        "genome_length": genome_length,
        "classification": label,
    }

    loaded_run_info = st.session_state.get("loaded_run_info")
    if loaded_run_info is not None:
        with RunStore(loaded_run_info["db_path"]) as store:
            store.record_metrics(
                loaded_run_info["run_id"],
                universe.epoch,
                {"best_replication_score": float(best_score)},
            )
            store.record_event(
                loaded_run_info["run_id"],
                universe.epoch,
                "replication_scan",
                {"best_score": best_score, "sample_size": int(sample_size), "classification": label},
            )

    if label != "no replication signal" and st.session_state.get(
        "auto_scan_first_detected_epoch"
    ) is None:
        st.session_state.auto_scan_first_detected_epoch = universe.epoch
        if loaded_run_info is not None:
            with RunStore(loaded_run_info["db_path"]) as store:
                store.record_event(
                    loaded_run_info["run_id"],
                    universe.epoch,
                    "candidate_replicator_detected",
                    {"best_score": best_score, "classification": label},
                )


def _maybe_auto_checkpoint(universe: BffSoupUniverse) -> None:
    """If auto-checkpoint is enabled and this epoch is due, save a
    checkpoint + a `checkpoint_saved` event -- the dashboard's own
    equivalent of `life run --db --checkpoint-dir --checkpoint-interval`.

    A run started here (Reset / (Re)initialize, not loaded from a stored
    run) lives only in this browser session's memory; if that session is
    ever lost -- a closed tab, an overnight disconnect -- there is
    otherwise no way to get it back, since nothing was ever written to
    disk. If this session was loaded via "Load stored run", checkpoints
    continue into that run's existing database and checkpoint directory
    (derived from its latest checkpoint's own path) so they interleave
    naturally with whatever `life run` already saved. Otherwise a new
    database is created under runs/, auto-discoverable by "Load stored
    run" after a reload -- the write side of this feature deliberately
    reuses that existing read path rather than inventing a second one.
    """
    if not st.session_state.get("auto_checkpoint"):
        return
    interval = st.session_state.get("auto_checkpoint_interval", 500)
    if universe.epoch == 0 or universe.epoch % interval != 0:
        return

    loaded_run_info = st.session_state.get("loaded_run_info")
    if loaded_run_info is not None:
        db_path = Path(loaded_run_info["db_path"])
        run_id = loaded_run_info["run_id"]
        checkpoint_dir = Path(loaded_run_info["checkpoint_path"]).parent
    else:
        autosave = st.session_state.get("auto_checkpoint_run_info")
        if autosave is None:
            db_path = RUNS_DIR / "dashboard_autosave.db"
            config_name = st.session_state.get("config_name", "unknown.yaml")
            with RunStore(db_path) as store:
                run_id = store.start_run(
                    experiment_name=st.session_state.config.name,
                    config_text=(CONFIGS_DIR / config_name).read_text(),
                    seed=universe.config.seed,
                )
            checkpoint_dir = RUNS_DIR / "dashboard_checkpoints" / f"run_{run_id}"
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            autosave = {
                "db_path": str(db_path),
                "run_id": run_id,
                "checkpoint_dir": str(checkpoint_dir),
            }
            st.session_state.auto_checkpoint_run_info = autosave
        db_path = Path(autosave["db_path"])
        run_id = autosave["run_id"]
        checkpoint_dir = Path(autosave["checkpoint_dir"])

    checkpoint_path = checkpoint_dir / f"epoch_{universe.epoch:010d}"
    save_checkpoint(universe, checkpoint_path)
    saved_path = checkpoint_file_path(checkpoint_path)
    with RunStore(db_path) as store:
        store.record_metrics(run_id, universe.epoch, compute_metrics(universe))
        store.record_event(run_id, universe.epoch, "checkpoint_saved", {"path": str(saved_path)})
    st.session_state.auto_checkpoint_last_epoch = universe.epoch


def _step(num_epochs: int) -> None:
    universe: BffSoupUniverse = st.session_state.universe
    for _ in range(num_epochs):
        universe.step_epoch()
        recorder: LineageRecorder | None = st.session_state.get("lineage_recorder")
        if recorder is not None:
            recorder.record(universe)
        _maybe_auto_scan(universe)
        _maybe_auto_checkpoint(universe)
    st.session_state.history.append(compute_metrics(universe))


st.title("Computational Life Lab")
st.caption(
    "Random 64-byte genomes -> random pairing -> BFF execution -> split -> "
    "replacement -> repeat. No fitness function, no selection: whatever "
    "structure appears has to come from the dynamics themselves."
)

with st.sidebar:
    st.header("Experiment")
    configs = _available_configs()
    config_name = st.selectbox("Configuration", configs, index=configs.index("bff_dev.yaml")
                                if "bff_dev.yaml" in configs else 0)
    seed_text = st.text_input("Seed override (blank = use config's seed)", value="")
    seed_override = int(seed_text) if seed_text.strip() else None

    if st.button("Reset / (Re)initialize", width="stretch"):
        _init_universe(config_name, seed_override)

    if "universe" not in st.session_state:
        _init_universe(config_name, seed_override)

    st.divider()
    st.header("Load stored run")
    st.caption(
        "Open a run saved via `life run --db ...` or `life sweep --db ...` -- "
        "including one that ran for hours -- and continue it from its last "
        "checkpoint."
    )
    discovered_dbs = sorted(str(p.relative_to(REPO_ROOT)) for p in RUNS_DIR.glob("*.db")) if RUNS_DIR.is_dir() else []
    db_path_text = st.text_input(
        "Database path", value=discovered_dbs[0] if discovered_dbs else "", key="load_db_path"
    )
    db_path = Path(db_path_text) if db_path_text.strip() else None
    if db_path is not None and db_path.is_file():
        with RunStore(db_path) as browse_store:
            stored_runs = browse_store.list_runs()
        if not stored_runs:
            st.caption("This database has no runs.")
        else:
            run_labels = {
                f"#{r['id']} {r['experiment_name']} (seed={r['seed']}, "
                f"epoch={r['final_epoch']}, {r['status']})": r["id"]
                for r in stored_runs
            }
            selected_label = st.selectbox("Run", list(run_labels.keys()), key="load_run_label")
            if st.button("Load this run", width="stretch"):
                try:
                    _load_stored_run(db_path, run_labels[selected_label])
                except (LookupError, FileNotFoundError) as exc:
                    st.error(str(exc))
    elif db_path is not None:
        st.caption("No database found at that path.")

    st.divider()
    st.header("Time controls")
    epochs_per_step = st.number_input("Epochs per step", min_value=1, value=10, step=1)
    cols = st.columns(2)
    if cols[0].button("Step", width="stretch"):
        _step(int(epochs_per_step))
    play_label = "Pause" if st.session_state.get("playing") else "Play"
    if cols[1].button(play_label, width="stretch"):
        st.session_state.playing = not st.session_state.get("playing", False)

    st.divider()
    max_displayed = st.slider(
        "Max organisms drawn in grid",
        min_value=256,
        max_value=20_000,
        value=4_000,
        step=256,
        help="Larger populations are subsampled for display; the simulation "
        "itself always runs on the full population.",
    )

    st.divider()
    st.header("Analysis")
    track_lineage = st.checkbox("Track lineage (memory-heavy)", key="track_lineage")
    if track_lineage and st.session_state.get("lineage_recorder") is None:
        recorder = LineageRecorder()
        recorder.record(st.session_state.universe)
        st.session_state.lineage_recorder = recorder
        st.caption("Recording started now -- ancestry from before this point isn't available.")
    elif not track_lineage:
        st.session_state.lineage_recorder = None

    st.divider()
    auto_scan = st.checkbox("Auto-scan for replicators", key="auto_scan")
    if auto_scan:
        st.number_input(
            "Scan interval (epochs)", min_value=1, value=100, step=10, key="auto_scan_interval"
        )
        st.number_input(
            "Sample size", min_value=10, max_value=2000, value=200, step=10, key="auto_scan_sample_size"
        )
        st.caption(
            "Runs the replication-consistency check (65 BFF executions per "
            "candidate) automatically every N epochs during Step/Play, and "
            "flags the first epoch a candidate replicator is seen -- same "
            "method as `life run --replication-scan-interval`."
        )

    st.divider()
    auto_checkpoint = st.checkbox(
        "Auto-checkpoint to disk (recover after disconnect)", key="auto_checkpoint"
    )
    if auto_checkpoint:
        st.number_input(
            "Checkpoint interval (epochs)",
            min_value=10,
            value=500,
            step=50,
            key="auto_checkpoint_interval",
        )
        st.caption(
            "Saves a checkpoint + `checkpoint_saved` event every N epochs "
            "during Step/Play -- same as `life run --db --checkpoint-dir "
            "--checkpoint-interval`. A run started here otherwise lives "
            "only in this browser session's memory; if that session is "
            "ever lost (closed tab, disconnect overnight, ...), the run "
            "is gone with no way back. With this on, reload the dashboard "
            "and use \"Load stored run\" above to resume from the last "
            "checkpoint instead. Writes to this run's existing database "
            "if loaded via \"Load stored run\", otherwise creates "
            "`runs/dashboard_autosave.db`."
        )

universe: BffSoupUniverse = st.session_state.universe
config = st.session_state.config

loaded_run_info = st.session_state.get("loaded_run_info")
if loaded_run_info:
    st.info(
        f"Viewing run #{loaded_run_info['run_id']} ({loaded_run_info['experiment_name']}) "
        f"from `{loaded_run_info['db_path']}`, resumed from its checkpoint at epoch "
        f"{loaded_run_info['checkpoint_epoch']}. Stepping/playing from here continues "
        "this run forward; it does not modify the saved files."
    )

if st.session_state.get("auto_scan"):
    first_detected = st.session_state.get("auto_scan_first_detected_epoch")
    if first_detected is not None:
        st.success(f"Candidate replicator first detected at epoch {first_detected}.")
    last = st.session_state.get("auto_scan_last_result")
    if last is not None:
        st.caption(
            f"Last auto-scan: epoch {last['epoch']}, best score "
            f"{last['best_score']}/{last['genome_length']} ({last['classification']})."
        )

if st.session_state.get("auto_checkpoint"):
    last_checkpoint_epoch = st.session_state.get("auto_checkpoint_last_epoch")
    if last_checkpoint_epoch is not None:
        autosave = st.session_state.get("auto_checkpoint_run_info")
        checkpoint_db = loaded_run_info["db_path"] if loaded_run_info else autosave["db_path"]
        st.caption(f"Last auto-checkpoint: epoch {last_checkpoint_epoch} (saved to `{checkpoint_db}`).")

status_cols = st.columns(4)
status_cols[0].metric("Epoch", universe.epoch)
status_cols[1].metric("Population size", config.universe.population_size)
status_cols[2].metric("Genome length", config.universe.genome_length)
status_cols[3].metric("Seed", config.universe.seed)

left, right = st.columns([2, 1])

# A qualitative, maximally-distinguishable palette (a subset of the
# well-known "Kelly colors" set) for the population grid's highlighted
# (repeated-genome) clusters. Background/overflow/padding use neutral
# grays/white so real clusters visually pop out rather than blending
# into rainbow noise -- see rendering.population_to_highlight_grid's
# docstring for why every unique genome no longer gets its own color.
_HIGHLIGHT_RGB = [
    (230, 25, 75), (60, 180, 75), (255, 195, 0), (0, 130, 200),
    (245, 130, 48), (145, 30, 180), (70, 200, 200), (240, 50, 230),
    (170, 200, 40), (250, 150, 175), (0, 128, 128), (200, 180, 255),
]
_BACKGROUND_RGB = (229, 231, 235)  # unique/unrepeated genomes
_OVERFLOW_RGB = (156, 163, 175)  # repeated, but below the highlight cap
_PADDING_RGB = (255, 255, 255)  # grid padding cells (not a real organism)

with left:
    st.subheader("Population (repeated genomes highlighted)")
    display_indices = select_display_sample(
        config.universe.population_size, max_displayed=max_displayed
    )
    if len(display_indices) < config.universe.population_size:
        st.caption(
            f"Showing a fixed random sample of {len(display_indices):,} of "
            f"{config.universe.population_size:,} organisms."
        )
    max_highlighted = len(_HIGHLIGHT_RGB)
    grid, highlight_legend = population_to_highlight_grid(
        universe.population[display_indices], max_highlighted=max_highlighted
    )
    palette = np.array(
        [_PADDING_RGB, _BACKGROUND_RGB, *_HIGHLIGHT_RGB, _OVERFLOW_RGB], dtype=np.uint8
    )
    rgb_image = palette[grid + 1]  # shifts -1/0/1..K/K+1 to valid palette indices

    fig = go.Figure(data=go.Image(z=rgb_image, hoverinfo="skip"))
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        height=500,
    )
    st.plotly_chart(fig, width="stretch")

    if highlight_legend:
        badges = " ".join(
            f'<span style="background-color:rgb{_HIGHLIGHT_RGB[e["rank"] - 1]}; '
            f'color:#111827; padding:2px 8px; border-radius:3px; margin-right:4px; '
            f'font-size:0.85em;">#{e["rank"]}: {e["count"]} ({e["frequency"]:.1%})</span>'
            for e in highlight_legend
        )
        st.markdown(badges, unsafe_allow_html=True)
        st.caption(
            "Each badge is one repeated genome (rank = most frequent first). "
            "Gray cells are unique genomes -- with 256^genome_length possible "
            "values, an exact duplicate arising by chance is astronomically "
            "unlikely, so any repeat shown here is a real signal, not noise. "
            "Darker gray (if visible) means 'repeated, but outside the "
            f"top {max_highlighted}'."
        )
    else:
        st.caption(
            "Every displayed organism currently has a unique genome -- "
            "nothing has repeated (by chance or otherwise) yet."
        )

with right:
    st.subheader("Population metrics")
    history_df = pd.DataFrame(st.session_state.history)
    fig_unique = px.line(
        history_df,
        x="epoch",
        y="unique_genomes",
        labels={"epoch": "Epoch", "unique_genomes": "Unique genomes (count)"},
        title="Genome diversity",
    )
    st.plotly_chart(fig_unique, width="stretch")

    fig_dominant = px.line(
        history_df,
        x="epoch",
        y="dominant_genome_frequency",
        labels={
            "epoch": "Epoch",
            "dominant_genome_frequency": "Dominant genome frequency (fraction)",
        },
        title="Dominant genome frequency",
    )
    fig_dominant.update_yaxes(range=[0, 1])
    st.plotly_chart(fig_dominant, width="stretch")

    st.caption(
        "These are raw, purely descriptive population statistics -- not "
        "replicator or species classifications. See 'Scan for candidate "
        "replicators' below for an actual replication-detection pass "
        "(spec section 13)."
    )

st.divider()
st.subheader("Diversity, entropy & complexity")
st.caption(
    "Three distinct 'entropy' quantities, easy to conflate: genome-level "
    "(spread over distinct 64-byte genomes), byte-level (spread over raw "
    "byte values, matching the reference implementation's own metric), "
    "and instruction-level (spread over decoded operations)."
)
analysis_cols = st.columns(2)
with analysis_cols[0]:
    fig_simpson = px.line(
        history_df,
        x="epoch",
        y="simpson_diversity",
        labels={"epoch": "Epoch", "simpson_diversity": "Simpson's diversity index"},
        title="Genotype diversity",
    )
    fig_simpson.update_yaxes(range=[0, 1])
    st.plotly_chart(fig_simpson, width="stretch")

    fig_entropy = go.Figure()
    fig_entropy.add_scatter(x=history_df["epoch"], y=history_df["genome_entropy_bits"], name="Genome-level")
    fig_entropy.add_scatter(x=history_df["epoch"], y=history_df["byte_entropy_bits"], name="Byte-level")
    fig_entropy.add_scatter(
        x=history_df["epoch"], y=history_df["instruction_entropy_bits"], name="Instruction-level"
    )
    fig_entropy.update_layout(
        title="Entropy at three levels", xaxis_title="Epoch", yaxis_title="Entropy (bits)"
    )
    st.plotly_chart(fig_entropy, width="stretch")

with analysis_cols[1]:
    fig_complexity = go.Figure()
    fig_complexity.add_scatter(
        x=history_df["epoch"], y=history_df["compressed_bits_per_byte"], name="Compressed bits/byte"
    )
    fig_complexity.add_scatter(
        x=history_df["epoch"],
        y=history_df["structural_redundancy_bits"],
        name="Structural redundancy",
    )
    fig_complexity.update_layout(
        title="Complexity proxies", xaxis_title="Epoch", yaxis_title="Bits"
    )
    st.plotly_chart(fig_complexity, width="stretch")
    st.caption(
        "Complexity *proxies*, not measurements of 'the complexity' of "
        "anything (spec section 14). Structural redundancy is byte "
        "entropy minus compressed bits/byte: a large positive gap "
        "suggests repeated patterns (e.g. copied genomes) beyond what a "
        "flat byte-frequency count alone would predict."
    )

st.divider()
inspector_col, debugger_col = st.columns(2)

with inspector_col:
    st.subheader("Genome inspector")
    if "inspector_index" not in st.session_state:
        st.session_state.inspector_index = 0
    organism_index = st.number_input(
        "Organism index",
        min_value=0,
        max_value=config.universe.population_size - 1,
        step=1,
        key="inspector_index",
    )
    organism = universe.get_organism(int(organism_index))
    info_cols = st.columns(3)
    info_cols[0].metric("Organism ID", organism.organism_id)
    info_cols[1].metric("Generation", organism.generation)
    info_cols[2].metric("Age (epochs)", universe.epoch - organism.birth_epoch)
    st.caption(
        f"Parents: {organism.parent_ids[0]}, {organism.parent_ids[1]}  |  "
        f"Birth epoch: {organism.birth_epoch}  |  Genome length: "
        f"{len(organism.genome)}"
    )
    st.markdown(render_tape_html(organism.genome), unsafe_allow_html=True)
    st.caption("Bold = active instruction, faint '0' = NULL sentinel, small hex = NOP byte.")

    dist = instruction_distribution(organism.genome)
    dist_df = pd.DataFrame(
        sorted(dist.items(), key=lambda kv: -kv[1]), columns=["instruction", "count"]
    )
    fig_dist = px.bar(
        dist_df,
        x="instruction",
        y="count",
        labels={"instruction": "Decoded instruction", "count": "Byte count"},
        title="Instruction distribution (this genome)",
    )
    st.plotly_chart(fig_dist, width="stretch")

    st.markdown("**Lineage**")
    recorder: LineageRecorder | None = st.session_state.get("lineage_recorder")
    if recorder is None:
        st.caption("Lineage tracking is off -- enable it in the sidebar to see ancestry here.")
    elif organism.organism_id not in recorder:
        st.caption(
            "This organism predates when lineage tracking was enabled, so its "
            "ancestry wasn't recorded."
        )
    else:
        lineage_cols = st.columns(2)
        lineage_cols[0].metric("Recorded ancestors", len(recorder.ancestors(organism.organism_id)))
        lineage_cols[1].metric(
            "Recorded descendants", len(recorder.descendants(organism.organism_id))
        )

        positions, edges = lineage_graph(recorder, organism.organism_id)
        if len(positions) > 1:
            fig_lineage = go.Figure()
            edge_x, edge_y = [], []
            for parent_id, child_id in edges:
                edge_x += [positions[parent_id][0], positions[child_id][0], None]
                edge_y += [positions[parent_id][1], positions[child_id][1], None]
            fig_lineage.add_scatter(
                x=edge_x, y=edge_y, mode="lines", line=dict(color="#cbd5e1", width=1),
                hoverinfo="skip", showlegend=False,
            )
            other_ids = [oid for oid in positions if oid != organism.organism_id]
            fig_lineage.add_scatter(
                x=[positions[oid][0] for oid in other_ids],
                y=[positions[oid][1] for oid in other_ids],
                mode="markers",
                marker=dict(size=10, color="#93c5fd"),
                text=[f"organism {oid}" for oid in other_ids],
                hoverinfo="text",
                name="ancestor/descendant",
            )
            fig_lineage.add_scatter(
                x=[positions[organism.organism_id][0]],
                y=[positions[organism.organism_id][1]],
                mode="markers",
                marker=dict(size=16, color="#ef4444"),
                text=[f"organism {organism.organism_id} (selected)"],
                hoverinfo="text",
                name="selected",
            )
            fig_lineage.update_layout(
                title="Lineage graph (x = generation)",
                xaxis_title="Generation",
                yaxis=dict(visible=False),
                showlegend=False,
                height=300,
                margin=dict(l=0, r=0, t=40, b=0),
            )
            st.plotly_chart(fig_lineage, width="stretch")
            st.caption(
                "Each organism has two parents, so this is a DAG, not a strict "
                "tree -- lineages can merge. Truncated to the nearest 40 "
                "ancestors/descendants for legibility."
            )

    st.markdown("**Replication check**")
    st.caption(
        "On demand only -- pairs this genome against 13 independent random "
        "partners across 5 chained generations and checks how consistent "
        "the output is (spec section 13; see analysis/replication.py)."
    )
    if st.button("Compute replication score", key="compute_replication"):
        score = replication_score(
            organism.genome, seed=config.universe.seed, max_steps=config.universe.max_steps
        )
        st.session_state.replication_result = (organism.organism_id, score)
    result = st.session_state.get("replication_result")
    if result is not None and result[0] == organism.organism_id:
        _, score = result
        label = classify(score, config.universe.genome_length)
        st.metric("Replication score", f"{score} / {config.universe.genome_length}")
        st.caption(f"Classification: {label} (heuristic, not proof of self-replication).")

with debugger_col:
    st.subheader("Execution debugger")
    st.caption(
        "Pairs two organisms' *current* genomes into a 128-byte tape and "
        "lets you step through BFF execution by hand, using the same "
        "interpreter the simulator itself uses. This is exploratory: it is "
        "not necessarily the pairing that actually happened in the "
        "simulation history."
    )
    partner_index = st.number_input(
        "Partner organism index",
        min_value=0,
        max_value=config.universe.population_size - 1,
        value=min(int(organism_index) + 1, config.universe.population_size - 1),
        step=1,
        key="debugger_partner_index",
    )

    if st.button("Load pair into debugger", width="stretch"):
        left_genome = universe.get_organism(int(organism_index)).genome
        right_genome = universe.get_organism(int(partner_index)).genome
        combined = bytearray(left_genome + right_genome)
        st.session_state.debug_interp = BffInterpreter(
            combined, head_init=config.universe.head_init
        )

    interp: BffInterpreter | None = st.session_state.get("debug_interp")
    if interp is None:
        st.info("Load a pair to start stepping through its execution.")
    else:
        control_cols = st.columns(3)
        if control_cols[0].button("Step", key="debug_step", width="stretch"):
            interp.step()
        if control_cols[1].button("Run to halt", key="debug_run", width="stretch"):
            interp.run(max_steps=config.universe.max_steps)
        if control_cols[2].button("Reset", key="debug_reset", width="stretch"):
            interp.reset()

        # Read state *after* applying any button action above, so the
        # displayed metrics/tape reflect this click's effect immediately
        # rather than lagging one click behind.
        state = interp.state
        debug_cols = st.columns(4)
        debug_cols[0].metric("Step", state.step_count)
        debug_cols[1].metric("PC", state.instruction_pointer if not state.halted else "-")
        debug_cols[2].metric("head0", state.head0)
        debug_cols[3].metric("head1", state.head1)

        st.markdown(
            render_tape_html(
                state.tape,
                head0=None if state.halted else state.head0,
                head1=None if state.halted else state.head1,
                pc=None if state.halted else state.instruction_pointer,
            ),
            unsafe_allow_html=True,
        )
        if state.halted:
            st.caption(f"Halted after {state.step_count} steps.")
        else:
            st.caption(
                f"Current instruction: {state.current_instruction.name} | "
                "blue = head0, red = head1, green = program counter."
            )

st.divider()
st.subheader("Scan for candidate replicators")
st.caption(
    "Runs the same replication-consistency check as the genome inspector "
    "across a sample of the population. Expensive: each candidate costs "
    "13 x 5 = 65 BFF executions, so this only scans a sample, not the "
    "whole population."
)
scan_cols = st.columns(3)
sample_size = scan_cols[0].number_input(
    "Sample size", min_value=10, max_value=2000, value=200, step=10
)
scan_max_steps = scan_cols[1].number_input(
    "Max steps per execution",
    min_value=100,
    max_value=config.universe.max_steps,
    value=min(2000, config.universe.max_steps),
    step=100,
)
if scan_cols[2].button("Run scan", width="stretch"):
    sample_idx = select_display_sample(
        config.universe.population_size, max_displayed=int(sample_size), seed=universe.epoch
    )
    candidates = universe.population[sample_idx]
    scores = replication_scores(
        candidates, seed=config.universe.seed ^ universe.epoch, max_steps=int(scan_max_steps)
    )
    order = np.argsort(-scores)[:20]
    st.session_state.scan_results = pd.DataFrame(
        {
            "population_index": sample_idx[order],
            "score": scores[order],
            "classification": [
                classify(int(s), config.universe.genome_length) for s in scores[order]
            ],
        }
    )

scan_results = st.session_state.get("scan_results")
if scan_results is not None:
    st.dataframe(scan_results, width="stretch", hide_index=True)
    if scan_results["score"].max() == 0:
        st.caption("No candidates in this sample showed any replication signal.")
    else:
        jump_target = int(scan_results.iloc[0]["population_index"])
        if st.button(f"Load top result (index {jump_target}) into genome inspector"):
            st.session_state.inspector_index = jump_target
            st.rerun()

st.divider()
st.subheader("Compare stored runs")
st.caption(
    "Overlay a metric's history across several stored runs -- e.g. different "
    "seeds, or points from the same sweep -- without leaving the dashboard "
    "(spec section 26)."
)
compare_discovered_dbs = (
    sorted(str(p.relative_to(REPO_ROOT)) for p in RUNS_DIR.glob("*.db")) if RUNS_DIR.is_dir() else []
)
compare_db_text = st.text_input(
    "Database path",
    value=compare_discovered_dbs[0] if compare_discovered_dbs else "",
    key="compare_db_path",
)
compare_db_path = Path(compare_db_text) if compare_db_text.strip() else None
if compare_db_path is not None and compare_db_path.is_file():
    with RunStore(compare_db_path) as compare_store:
        comparable_runs = compare_store.list_runs()
    if not comparable_runs:
        st.caption("This database has no runs.")
    else:
        compare_labels = {
            f"#{r['id']} {r['experiment_name']} (seed={r['seed']}, "
            f"epoch={r['final_epoch']}, {r['status']})": r["id"]
            for r in comparable_runs
        }
        selected_run_labels = st.multiselect(
            "Runs to compare", list(compare_labels.keys()), key="compare_run_labels"
        )
        metric_choice = st.selectbox(
            "Metric",
            [
                "unique_genomes",
                "dominant_genome_frequency",
                "simpson_diversity",
                "genome_entropy_bits",
                "byte_entropy_bits",
                "instruction_entropy_bits",
                "compressed_bits_per_byte",
                "structural_redundancy_bits",
                "best_replication_score",
            ],
            key="compare_metric",
        )
        if selected_run_labels:
            fig_compare = go.Figure()
            with RunStore(compare_db_path) as compare_store:
                for label in selected_run_labels:
                    run_history = compare_store.get_metrics_history(compare_labels[label])
                    run_df = pd.DataFrame(run_history)
                    if metric_choice in run_df.columns:
                        fig_compare.add_scatter(
                            x=run_df["epoch"], y=run_df[metric_choice], name=label, mode="lines"
                        )
            fig_compare.update_layout(
                title=f"{metric_choice} across selected runs",
                xaxis_title="Epoch",
                yaxis_title=metric_choice,
            )
            st.plotly_chart(fig_compare, width="stretch")
elif compare_db_path is not None:
    st.caption("No database found at that path.")

if st.session_state.get("playing"):
    _step(int(epochs_per_step))
    time.sleep(0.05)
    st.rerun()
