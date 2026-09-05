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

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from rendering import population_to_cluster_grid, select_display_sample

from computational_life.experiments.base import load_bff_soup_config
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
    st.session_state.history = [st.session_state.universe.summary()]
    st.session_state.playing = False


def _step(num_epochs: int) -> None:
    universe: BffSoupUniverse = st.session_state.universe
    for _ in range(num_epochs):
        universe.step_epoch()
    st.session_state.history.append(universe.summary())


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
        "replicator or species classifications. Replication detection is a "
        "separate analysis step (spec section 13), not yet implemented."
    )

if st.session_state.get("playing"):
    _step(int(epochs_per_step))
    time.sleep(0.05)
    st.rerun()
