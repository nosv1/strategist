from datetime import datetime
from statistics import mean
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import seaborn as sns
from Car import Hero, Villan
from Lap import Segment
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from PyAccWrapper import CarLocation, PositionEntry
from Session import Session
from Stint import Stint
from util import ms_to_m_ss_000

# Set default seaborn style for all plots
sns.set_theme(style="darkgrid")
sns.set_palette("husl")

# Color scheme constants
DARK_BG = "#2e2e2e"
DARKER_BG = "#3a3a3a"
TEXT_COLOR = "white"

# Consistent color palette for plots
COLORS = {
    "rain": "#FF6B6B",  # Red for rain
    "track_grip": "#4ECDC4",  # Teal for track grip
    "lap_time": "#45B7D1",  # Blue for lap times
    "fuel_remaining": "#FFA07A",  # Light salmon for fuel remaining
    "fuel_used": "#98D8C8",  # Mint for fuel used
    "track_temp": "#F7B731",  # Yellow/gold for track temp
    "air_temp": "#5F27CD",  # Purple for air temp
    "delta": "#EE5A6F",  # Pink/red for delta
    "reference": "#95A5A6",  # Gray for reference lines
    "villan": "#FF9F43",  # Orange for villan
}


def plot_weather_conditions(
    session_history: list[Session],
    ax: Optional[Axes] = None,
    sample_step: int = 60,
    figsize: Tuple[int, int] = (10, 6),
) -> Axes:
    """
    Plot rain intensity and track grip status over time.

    Args:
        session_history: List of Session objects containing weather data
        ax: Matplotlib axes to plot on. If None, creates new figure
        sample_step: Sampling rate to reduce data points (default 60)
        figsize: Figure size if creating new figure (width, height)

    Returns:
        Matplotlib axes with the plot
    """
    # Extract rain data from session history
    times: list[float] = []
    rain_values: list[int] = []
    rain_names: list[str] = []
    track_grip_values: list[int] = []
    track_grip_names: list[str] = []

    for s in session_history:
        if not s.rain_now:
            continue
        times.append(s.time_remaining.total_seconds() / 60)
        rain_values.append(s.rain_now.rain_intensity.value)
        rain_names.append(s.rain_now.rain_intensity.name)
        track_grip_values.append(
            s.track_grip_status.value if s.track_grip_status is not None else -1
        )
        track_grip_names.append(
            s.track_grip_status.name if s.track_grip_status is not None else "Unknown"
        )

    # Sample data to reduce plot density
    sampled_times = times[::sample_step]
    sampled_rain_values = rain_values[::sample_step]
    sampled_rain_names = rain_names[::sample_step]
    sampled_track_grip_values = track_grip_values[::sample_step]
    sampled_track_grip_names = track_grip_names[::sample_step]

    # Create figure if not provided
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(DARKER_BG)
    else:
        ax.set_facecolor(DARKER_BG)

    # Rain state plot (left y-axis)
    ax.plot(
        sampled_times,
        sampled_rain_values,
        color=COLORS["rain"],
        label="Rain State",
        linewidth=2,
    )
    ax.set_ylabel("Rain State", color=COLORS["rain"])
    ax.tick_params(axis="y", labelcolor=COLORS["rain"])

    # Set y-axis labels for rain intensity using names
    unique_rain_values = sorted(set(sampled_rain_values))
    rain_value_to_name = {val: name for val, name in zip(rain_values, rain_names)}
    ax.set_yticks(unique_rain_values)
    ax.set_yticklabels([rain_value_to_name[val] for val in unique_rain_values])

    ax.set_xlabel("Time", color=TEXT_COLOR)
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)

    # Track grip status plot (right y-axis)
    ax2 = ax.twinx()
    # ax2.invert_xaxis()
    ax2.plot(
        sampled_times,
        sampled_track_grip_values,
        color=COLORS["track_grip"],
        label="Track Grip",
        linewidth=2,
    )
    ax2.set_ylabel("Track Grip Status", color=COLORS["track_grip"])
    ax2.tick_params(axis="y", labelcolor=COLORS["track_grip"])

    # Set y-axis labels for track grip using names
    unique_grip_values = sorted(set(sampled_track_grip_values))
    grip_value_to_name = {
        val: name for val, name in zip(track_grip_values, track_grip_names)
    }
    ax2.set_yticks(unique_grip_values)
    ax2.set_yticklabels([grip_value_to_name[val] for val in unique_grip_values])

    ax.set_title("Rain State and Track Grip Status", color=TEXT_COLOR)
    ax.tick_params(axis="x", colors=TEXT_COLOR)

    return ax


def plot_track_temperature(
    session_history: list[Session],
    ax: Optional[Axes] = None,
    sample_step: int = 60,
    figsize: Tuple[int, int] = (10, 6),
) -> Axes:
    """
    Plot track and air temperature over time.

    Args:
        session_history: List of Session objects containing temperature data
        ax: Matplotlib axes to plot on. If None, creates new figure
        sample_step: Sampling rate to reduce data points (default 60)
        figsize: Figure size if creating new figure (width, height)

    Returns:
        Matplotlib axes with the plot
    """
    # Create figure if not provided
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(DARKER_BG)
    else:
        ax.set_facecolor(DARKER_BG)

    # Extract temperature data
    times = [(s.time_remaining.total_seconds() / 60) for s in session_history]
    track_temps = [s.track_temp for s in session_history]
    air_temps = [s.air_temp for s in session_history]

    # Sample data
    sampled_times = times[::sample_step]
    sampled_track_temps = track_temps[::sample_step]
    sampled_air_temps = air_temps[::sample_step]

    ax.plot(
        sampled_times,
        sampled_track_temps,
        color=COLORS["track_temp"],
        label="Track Temp",
        linewidth=2,
    )
    ax.plot(
        sampled_times,
        sampled_air_temps,
        color=COLORS["air_temp"],
        label="Air Temp",
        linewidth=2,
    )

    ax.set_xlabel("Time Remaining (minutes)", color=TEXT_COLOR)
    ax.invert_xaxis()
    ax.set_ylabel("Temperature (°C)", color=TEXT_COLOR)
    ax.set_title("Track & Air Temperature", color=TEXT_COLOR)
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.tick_params(colors=TEXT_COLOR)

    return ax


def plot_lap_times(
    hero_history: list[Hero],
    ax: Optional[Axes] = None,
    figsize: Tuple[int, int] = (10, 6),
    show_valid_only: bool = True,
) -> Axes:
    """
    Plot lap times throughout the session.

    Args:
        hero_history: List of Hero objects containing lap data
        ax: Matplotlib axes to plot on. If None, creates new figure
        figsize: Figure size if creating new figure (width, height)
        show_valid_only: If True, only show valid laps

    Returns:
        Matplotlib axes with the plot
    """
    # Create figure if not provided
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(DARKER_BG)
    else:
        ax.set_facecolor(DARKER_BG)

    # Extract lap times from hero history
    lap_numbers = []
    lap_times = []

    for i, hero in enumerate(hero_history):
        lap_time = hero.entry.last_lap.lap_time_ms
        if lap_time == 0:
            continue
        lap_numbers.append(hero.entry.lap - 1)
        lap_times.append(lap_time / 1000)

    if lap_numbers:
        ax.plot(
            lap_numbers,
            lap_times,
            marker="o",
            color=COLORS["lap_time"],
            linewidth=2,
            markersize=4,
        )
        ax.set_xlabel("Lap Number", color=TEXT_COLOR)
        ax.set_ylabel("Lap Time (seconds)", color=TEXT_COLOR)
        ax.set_title("Lap Times", color=TEXT_COLOR)
        ax.grid(True, alpha=0.3)
        ax.tick_params(colors=TEXT_COLOR)

    return ax


def plot_fuel_usage(
    hero_history: list[Hero],
    ax: Optional[Axes] = None,
    figsize: Tuple[int, int] = (10, 6),
) -> Axes:
    """
    Plot fuel levels throughout the session.

    Args:
        hero_history: List of Hero objects containing fuel data
        ax: Matplotlib axes to plot on. If None, creates new figure
        figsize: Figure size if creating new figure (width, height)

    Returns:
        Matplotlib axes with the plot
    """
    # Create figure if not provided
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(DARKER_BG)
    else:
        ax.set_facecolor(DARKER_BG)

    # Extract fuel data
    lap_numbers = []
    fuel_levels = []
    delta_fuel_per_lap = []

    for hero in hero_history:
        if not hero.fuel_remaining:
            continue

        if lap_numbers and hero.entry.lap == lap_numbers[-1]:
            continue

        if fuel_levels:
            delta_fuel_per_lap.append(fuel_levels[-1] - hero.fuel_remaining)

        lap_numbers.append(hero.entry.lap)
        fuel_levels.append(hero.fuel_remaining)

    if lap_numbers:
        # Plot fuel remaining on primary y-axis
        ax.plot(
            lap_numbers,
            fuel_levels,
            marker="o",
            color=COLORS["fuel_remaining"],
            label="Fuel Remaining",
            linewidth=2,
            markersize=4,
        )

        ax.set_xlabel("Lap Number", color=TEXT_COLOR)
        ax.set_ylabel("Fuel Remaining (L)", color=COLORS["fuel_remaining"])
        ax.tick_params(axis="y", labelcolor=COLORS["fuel_remaining"])
        ax.set_title("Fuel Usage", color=TEXT_COLOR)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="x", colors=TEXT_COLOR)

        # Plot delta fuel on secondary y-axis
        if delta_fuel_per_lap:
            ax2 = ax.twinx()
            ax2.plot(
                lap_numbers[1:],  # Delta starts from second lap
                delta_fuel_per_lap,
                marker="s",
                color=COLORS["fuel_used"],
                label="Fuel Used per Lap",
                linewidth=2,
                markersize=4,
            )
            ax2.set_ylabel("Fuel Used per Lap (L)", color=COLORS["fuel_used"])
            ax2.tick_params(axis="y", labelcolor=COLORS["fuel_used"])

    return ax


def plot_deltas_to_hero(
    hero_history: list[Hero],
    sample_step: int = 1,
    ax: Optional[Axes] = None,
    figsize: Tuple[int, int] = (10, 6),
) -> Axes:
    """
    Plot position delta between hero and a specific opponent over time.

    Args:
        hero_history: List of Hero objects
        villan_history: List of lists containing Villan objects
        villan_index: Index of the opponent to track (default 0)
        ax: Matplotlib axes to plot on. If None, creates new figure
        figsize: Figure size if creating new figure (width, height)

    Returns:
        Matplotlib axes with the plot
    """
    # Create figure if not provided
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(DARKER_BG)
    else:
        ax.set_facecolor(DARKER_BG)

    # Extract delta data
    deltas: dict[int, dict[str, list[float]]] = {}

    for h in hero_history[::sample_step]:
        if h.entry.lap == 0:
            continue

        for v_id, v in h.villans.items():
            gap_to_hero = v.gap_to_hero(h).total_seconds()
            if v_id not in deltas:
                deltas[v_id] = {"name": v.entry.driver_full_name, "deltas": []}
            deltas[v_id]["deltas"].append(gap_to_hero)

    if deltas:
        for v_id, delta_info in deltas.items():
            line = ax.plot(
                range(len(delta_info["deltas"])),
                delta_info["deltas"],
                linewidth=2,
            )
            # Add text label at the final point
            final_x = len(delta_info["deltas"]) - 1
            final_y = delta_info["deltas"][-1]
            ax.text(
                final_x,
                final_y,
                f" {delta_info['name']}",
                color=line[0].get_color(),
                verticalalignment="center",
                fontsize=9,
            )
        # ax.axhline(y=0, color=COLORS["reference"], linestyle="--", alpha=0.5)
        ax.set_xlabel("Time", color=TEXT_COLOR)
        ax.set_ylabel("Delta (seconds)", color=TEXT_COLOR)
        ax.set_title("Delta to Opponent", color=TEXT_COLOR)
        ax.grid(True, alpha=0.3)
        ax.tick_params(colors=TEXT_COLOR)

    return ax


# Convenience function to create a dashboard layout
def create_dashboard(
    session_history: list[Session],
    hero_history: list[Hero],
    villan_history: list[list[Villan]],
    layout: str = "3x2",
    sample_step: int = 60,
) -> Figure:
    """
    Create a dashboard with multiple plots arranged in a grid.

    Args:
        session_history: List of Session objects
        hero_history: List of Hero objects
        villan_history: List of lists containing Villan objects
        layout: Grid layout as string (e.g., "2x2", "3x2", "1x3")

    Returns:
        Matplotlib figure with all plots
    """
    rows, cols = map(int, layout.split("x"))
    fig = plt.figure(figsize=(cols * 6, rows * 5))
    fig.patch.set_facecolor(DARK_BG)

    # Create subplots
    ax1, ax2, ax3, ax4, ax5, ax6 = None, None, None, None, None, None
    if layout == "2x2":
        ax1 = plt.subplot(2, 2, 1)
        ax2 = plt.subplot(2, 2, 2)
        ax3 = plt.subplot(2, 2, 3)
        ax4 = plt.subplot(2, 2, 4)
    elif layout == "3x2":
        ax1 = plt.subplot(3, 2, 1)
        ax2 = plt.subplot(3, 2, 2)
        ax3 = plt.subplot(3, 2, 3)
        ax4 = plt.subplot(3, 2, 4)
        ax5 = plt.subplot(3, 2, 5)
        ax6 = plt.subplot(3, 2, 6)
    elif layout == "1x1":
        ax5 = plt.subplot(1, 1, 1)

    plot_weather_conditions(session_history, sample_step=sample_step, ax=ax1)
    plot_track_temperature(session_history, sample_step=sample_step, ax=ax3)
    plot_lap_times(hero_history, ax=ax2)
    plot_fuel_usage(hero_history, ax=ax4)
    plot_deltas_to_hero(hero_history, ax=ax5)

    plt.tight_layout()
    return fig


def _plot_violin_segment_times(
    hero: Hero,
    segment_type: str,
    figsize: Tuple[int, int] = (10, 6),
) -> None:
    """
    Plot segment times as violin plots alongside a track map.

    Args:
        hero: Hero object containing stint data
        segment_type: Either 'mini_sector' or 'sector'
        figsize: Figure size (width, height)
    """
    # Create figure with GridSpec for custom sizing
    fig = plt.figure(figsize=figsize)
    fig.patch.set_facecolor(DARK_BG)

    # Create grid: violin plot gets 3 units, track gets 1 unit
    gs = fig.add_gridspec(1, 2, width_ratios=[3, 1])
    ax = fig.add_subplot(gs[0, 0])
    ax_track = fig.add_subplot(gs[0, 1])

    ax.set_facecolor(DARKER_BG)
    ax_track.set_facecolor(DARKER_BG)

    if segment_type == "mini_sector":
        segment_history_attr = "mini_sector_history"
        num_segments = hero.session.num_mini_sectors
        title = "Mini Sector Times Distribution"
        xlabel = "Mini Sector Index"
    else:  # sector
        segment_history_attr = "sector_history"
        num_segments = 3
        title = "Sector Times Distribution"
        xlabel = "Sector Index"

    # Collect segment times for each segment index
    segment_times_data = [[] for _ in range(num_segments)]

    for stint in hero.stints:
        segment_history: list[list[Segment]] = getattr(stint, segment_history_attr)
        for seg_idx, segment in enumerate(segment_history):
            if seg_idx < num_segments:
                segment_times = [
                    seg.time_ms / 1000
                    for l_idx, seg in enumerate(segment)
                    if (
                        seg.time_ms > 0
                        and l_idx < len(stint.laps)
                        and not stint.laps[l_idx].lap_info.is_invalid
                    )
                ]
                segment_times_data[seg_idx].extend(segment_times)

    # Filter out empty segments
    positions = []
    data_to_plot = []
    for seg_idx, times in enumerate(segment_times_data):
        if times:
            positions.append(seg_idx)
            data_to_plot.append(times)

    if data_to_plot:
        parts = ax.violinplot(
            data_to_plot,
            positions=positions,
            widths=0.7,
            showmeans=True,
            showmedians=True,
        )

        # Customize violin plot colors
        for pc in parts["bodies"]:
            pc.set_facecolor(COLORS["lap_time"])
            pc.set_alpha(0.7)

    ax.set_xlabel(xlabel, color=TEXT_COLOR)
    ax.set_ylabel("Segment Time (seconds)", color=TEXT_COLOR)
    ax.set_title(title, color=TEXT_COLOR)
    ax.tick_params(colors=TEXT_COLOR)
    ax.grid(True, alpha=0.3, axis="y")

    # Plot track on the right subplot with mini sector markers
    best_lap = hero.best_lap
    x_positions = [-pos.x for pos in best_lap.pos_history]
    y_positions = [pos.y for pos in best_lap.pos_history]

    ax_track.plot(
        x_positions,
        y_positions,
        color=COLORS["lap_time"],
        linewidth=2,
    )

    # Add mini sector markers
    prev_mini_sector_idx = -1
    for pos in best_lap.pos_history:
        mini_sector_idx = int(pos.spline_pos * hero.session.num_mini_sectors)
        if mini_sector_idx != prev_mini_sector_idx:
            prev_mini_sector_idx = mini_sector_idx
            ax_track.plot(
                -pos.x,
                pos.y,
                marker="o",
                color="yellow",
                markersize=3,
            )
            ax_track.text(
                -pos.x,
                pos.y,
                f"{mini_sector_idx}",
                color="yellow",
                verticalalignment="center",
                fontsize=10,
            )

    ax_track.set_xlabel("X", color=TEXT_COLOR, fontsize=8)
    ax_track.set_ylabel("Y", color=TEXT_COLOR, fontsize=8)
    ax_track.set_title("Track", color=TEXT_COLOR, fontsize=9)
    ax_track.tick_params(colors=TEXT_COLOR, labelsize=7)
    ax_track.axis("equal")
    ax_track.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


def plot_mini_sectors(hero: Hero, figsize: Tuple[int, int] = (10, 6)) -> None:
    """Plot spline position deltas for mini sectors."""
    _plot_violin_segment_times(hero, "mini_sector", figsize)


def plot_sectors(hero: Hero, figsize: Tuple[int, int] = (10, 6)) -> None:
    """Plot spline position deltas for sectors."""
    _plot_violin_segment_times(hero, "sector", figsize)


def plot_stint(stint: Stint, figsize: Tuple[int, int] = (10, 6)) -> None:
    """Plot stint lap times as violin plots alongside a track map."""
    # Create figure with GridSpec for custom sizing
    fig = plt.figure(figsize=figsize)
    fig.patch.set_facecolor(DARK_BG)

    # Create grid: violin plot gets 3 units, track gets 1 unit
    gs = fig.add_gridspec(1, 2, width_ratios=[3, 1])
    ax = fig.add_subplot(gs[0, 0])
    ax_track = fig.add_subplot(gs[0, 1])

    ax.set_facecolor(DARKER_BG)
    ax_track.set_facecolor(DARKER_BG)

    # Collect lap times for the stint
    lap_times = []
    for lap in stint.laps:
        if not lap.lap_info.is_invalid and lap.lap_info.lap_time_ms > 0:
            lap_times.append(lap.lap_info.lap_time_ms / 1000)

    if lap_times:
        parts = ax.violinplot(
            [lap_times],
            positions=[0],
            widths=0.7,
            showmeans=True,
            showmedians=True,
        )

        # Customize violin plot colors
        for pc in parts["bodies"]:
            pc.set_facecolor(COLORS["lap_time"])
            pc.set_alpha(0.7)

    ax.set_xlabel("Stint", color=TEXT_COLOR)
    ax.set_ylabel("Lap Time (seconds)", color=TEXT_COLOR)
    ax.set_title("Stint Lap Times Distribution", color=TEXT_COLOR)
    ax.tick_params(colors=TEXT_COLOR)
    ax.grid(True, alpha=0.3, axis="y")

    # Plot track on the right subplot with mini sector markers
    best_lap = stint.best_lap
    x_positions = [-pos.x for pos in best_lap.pos_history]
    y_positions = [pos.y for pos in best_lap.pos_history]

    ax_track.plot(
        x_positions,
        y_positions,
        color=COLORS["lap_time"],
        linewidth=2,
    )

    # Add mini sector markers
    prev_mini_sector_idx = -1
    for pos in best_lap.pos_history:
        mini_sector_idx = int(pos.spline_pos * stint.session.num_mini_sectors)
        if mini_sector_idx != prev_mini_sector_idx:
            prev_mini_sector_idx = mini_sector_idx
            ax_track.plot(
                -pos.x,
                pos.y,
                marker="o",
                color="yellow",
                markersize=3,
            )
            ax_track.text(
                -pos.x,
                pos.y,
                f"{mini_sector_idx}",
                color="yellow",
                verticalalignment="center",
                fontsize=10,
            )

    ax_track.set_xlabel("X", color=TEXT_COLOR, fontsize=8)
    ax_track.set_ylabel("Y", color=TEXT_COLOR, fontsize=8)
    ax_track.set_title("Track", color=TEXT_COLOR, fontsize=9)
    ax_track.tick_params(colors=TEXT_COLOR, labelsize=7)
    ax_track.axis("equal")
    ax_track.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def plot_track(
    hero: Hero,
    figsize: Tuple[int, int] = (10, 6),
) -> None:
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARKER_BG)

    best_lap = hero.best_lap

    x_positions = [-pos.x for pos in best_lap.pos_history]
    y_positions = [pos.y for pos in best_lap.pos_history]
    prev_mini_sector_idx = 0
    for pos in best_lap.pos_history:
        mini_sector_idx = int(pos.spline_pos * hero.session.num_mini_sectors)
        if mini_sector_idx != prev_mini_sector_idx:
            prev_mini_sector_idx = mini_sector_idx
            ax.plot(
                -pos.x,
                pos.y,
                marker="o",
                color="yellow",
                markersize=5,
            )
            ax.text(
                -pos.x + 15.11,
                pos.y + 15.11,
                f"{mini_sector_idx}: {ms_to_m_ss_000(pos.lap_time_at_pos_ms)}",
                color="yellow",
                verticalalignment="center",
                fontsize=10,
            )

    ax.plot(
        -best_lap.pos_history[-1].x,
        best_lap.pos_history[-1].y,
        marker="o",
        color="red",
        markersize=5,
    )
    ax.text(
        -best_lap.pos_history[-1].x - 15.11,
        best_lap.pos_history[-1].y - 15.11,
        f"Lap: {ms_to_m_ss_000(best_lap.lap_info.lap_time_ms)}",
        color="#C061FF",
        verticalalignment="center",
        fontsize=10,
    )

    ax.plot(
        x_positions,
        y_positions,
        color=COLORS["lap_time"],
        linewidth=2,
    )
    ax.set_xlabel("X Position", color=TEXT_COLOR)
    ax.set_ylabel("Y Position", color=TEXT_COLOR)
    ax.set_title("Track Position", color=TEXT_COLOR)
    ax.tick_params(colors=TEXT_COLOR)
    ax.axis("equal")  # Equal aspect ratio for better track visualization
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


def plot_predicted_race_times(
    hero_history: list[Hero], villan_history: list[Hero]
) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    ax2 = ax.twinx()
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARKER_BG)

    vX_ahead = []
    vy_ahead = []
    vX_behind = []
    vy_behind = []
    vX_leader = []
    vy_leader = []

    prev_villan_ahead = None
    prev_villan_behind = None
    prev_leader = None

    time_remainingX = []
    hero_car_locationsY = []

    for h_idx, hero in enumerate(hero_history):
        time_remaining = hero.session.time_remaining.total_seconds() / 60
        predicted_race_time = hero.predicted_race_time_ms
        if predicted_race_time is None:
            continue

        time_remainingX.append(time_remaining)
        hero_car_locationsY.append(hero.entry.car_location.value)

        villan_ahead = hero.get_villan_from_pos(max(hero.entry.position - 1, 1))
        villan_behind = hero.get_villan_from_pos(
            min(hero.entry.position + 1, len(hero.villans))
        )
        leader = hero.get_villan_from_pos(1)

        if villan_ahead and villan_ahead.predicted_race_time_ms:
            vX_ahead.append(time_remaining)
            delta = (villan_ahead.predicted_race_time_ms - predicted_race_time) / 1000
            vy_ahead.append(delta)

            if not prev_villan_ahead or villan_ahead != prev_villan_ahead:
                prev_villan_ahead = villan_ahead
                ax.text(
                    time_remaining,
                    delta + 5,
                    f"{villan_ahead.entry.driver_last_name}",
                    color=COLORS["villan"],
                    fontsize=8,
                )

        if villan_behind and villan_behind.predicted_race_time_ms:
            vX_behind.append(time_remaining)
            delta = (villan_behind.predicted_race_time_ms - predicted_race_time) / 1000
            vy_behind.append(delta)

            if not prev_villan_behind or villan_behind != prev_villan_behind:
                prev_villan_behind = villan_behind
                ax.text(
                    time_remaining,
                    delta - 5,
                    f"{villan_behind.entry.driver_last_name}",
                    color=COLORS["track_grip"],
                    fontsize=8,
                )

        # if leader and leader.predicted_race_time_ms and hero.entry.position > 1:
        if leader and leader.predicted_race_time_ms:
            vX_leader.append(time_remaining)
            delta = (leader.predicted_race_time_ms - predicted_race_time) / 1000
            vy_leader.append(delta)

            if not prev_leader or leader != prev_leader:
                prev_leader = leader
                ax.text(
                    time_remaining,
                    delta + 5,
                    f"{leader.entry.driver_last_name} (P1)",
                    color=COLORS["delta"],
                    fontsize=8,
                )

    # Plot car location on secondary axis
    ax2.plot(
        time_remainingX,
        hero_car_locationsY,
        linewidth=2,
        label="Car Location",
        alpha=0.7,
        color=COLORS["reference"],
    )
    ax2.set_ylabel("Car Location", color=TEXT_COLOR, rotation=270, labelpad=15)
    ax2.tick_params(axis="y", labelcolor=TEXT_COLOR)
    ax2.set_yticks([v.value for v in CarLocation.__members__.values()])
    ax2.set_yticklabels([k for k in CarLocation.__members__.keys()])

    # Plot delta lines
    ax.plot(
        vX_ahead,
        vy_ahead,
        linewidth=2,
        label="Opponent Ahead",
        color=COLORS["villan"],
    )
    ax.plot(
        vX_behind,
        vy_behind,
        linewidth=2,
        label="Opponent Behind",
        color=COLORS["track_grip"],
    )

    if vX_leader:
        ax.plot(
            vX_leader,
            vy_leader,
            linewidth=2,
            label="Leader",
            color=COLORS["delta"],
        )

    ax.axhline(y=0, color=COLORS["reference"], linestyle="--", alpha=0.5)
    ax.set_xlabel("Time Remaining (minutes)", color=TEXT_COLOR)
    ax.set_ylabel("Delta to Hero (seconds)", color=TEXT_COLOR)
    ax.set_title("Predicted Race Time Deltas", color=TEXT_COLOR)
    ax.legend(loc="best")
    ax.tick_params(colors=TEXT_COLOR)
    ax2.tick_params(colors=TEXT_COLOR)
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


# Legacy function for backwards compatibility
def plot_logs(
    session_history: list[Session],
    hero_history: list[Hero],
    villan_history: list[list[Villan]],
):
    """Legacy function - creates and displays a 2x2 dashboard."""
    session_duration = session_history[-1].now - session_history[0].now
    session_n = len(session_history)
    sample_step = int(session_n / session_duration.total_seconds() * 60)  # n per minute
    fig = create_dashboard(
        session_history,
        hero_history,
        villan_history,
        layout="1x1",
        sample_step=sample_step,
    )
    plt.show()
