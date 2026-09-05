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
from metrics import compute_metrics_record

from rendering import (
    instruction_distribution,
    population_to_cluster_grid,
    render_tape_html,
    select_display_sample,
)

from computational_life.analysis.lineage import LineageRecorder
from computational_life.analysis.replication import classify, replication_score, replication_scores
from computational_life.experiments.base import load_bff_soup_config
from computational_life.substrates.bff.interpreter import BffInterpreter
from computational_life.substrates.bff.universe import BffSoupUniverse

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIGS_DIR = REPO_ROOT / "experiments" / "configs"

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
    st.session_state.universe = BffSoupUniverse(config.universe)
    st.session_state.history = [compute_metrics_record(st.session_state.universe)]
    st.session_state.playing = False
    st.session_state.scan_results = None
    if st.session_state.get("track_lineage"):
        recorder = LineageRecorder()
        recorder.record(st.session_state.universe)
        st.session_state.lineage_recorder = recorder
    else:
        st.session_state.lineage_recorder = None


def _step(num_epochs: int) -> None:
    universe: BffSoupUniverse = st.session_state.universe
    for _ in range(num_epochs):
        universe.step_epoch()
        recorder: LineageRecorder | None = st.session_state.get("lineage_recorder")
        if recorder is not None:
            recorder.record(universe)
    st.session_state.history.append(compute_metrics_record(universe))


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

universe: BffSoupUniverse = st.session_state.universe
config = st.session_state.config

status_cols = st.columns(4)
status_cols[0].metric("Epoch", universe.epoch)
status_cols[1].metric("Population size", config.universe.population_size)
status_cols[2].metric("Genome length", config.universe.genome_length)
status_cols[3].metric("Seed", config.universe.seed)

left, right = st.columns([2, 1])

with left:
    st.subheader("Population (colored by genome identity)")
    display_indices = select_display_sample(
        config.universe.population_size, max_displayed=max_displayed
    )
    if len(display_indices) < config.universe.population_size:
        st.caption(
            f"Showing a fixed random sample of {len(display_indices):,} of "
            f"{config.universe.population_size:,} organisms."
        )
    grid, num_unique = population_to_cluster_grid(universe.population[display_indices])
    fig = go.Figure(
        data=go.Heatmap(
            z=grid,
            colorscale="Turbo",
            zmin=-1,
            showscale=False,
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, autorange="reversed"),
        height=500,
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Each cell is one organism; identical color (within this snapshot) "
        "means byte-identical genomes. Colors are reassigned every redraw "
        "and carry no meaning across snapshots or between organisms of "
        "different colors."
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

if st.session_state.get("playing"):
    _step(int(epochs_per_step))
    time.sleep(0.05)
    st.rerun()
