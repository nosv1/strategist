from __future__ import annotations

import os
import textwrap
from datetime import datetime
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.api as sm
from matplotlib.axes import Axes
from statsmodels.stats.outliers_influence import variance_inflation_factor


class Stint:
    def __init__(
        self,
        date: datetime,
        start: int,
        end: int,
        start_tread: float,
        end_tread: float,
        in_out_laps_count: int,
    ):
        self.date = date
        self.start = start
        self.end = end
        self.start_wear_percent = (3 - start_tread) / 3
        self.end_wear_percent = (3 - end_tread) / 3
        self.wear_percent_per_lap = (
            self.end_wear_percent - self.start_wear_percent
        ) / ((self.end - self.start) + 1 + in_out_laps_count)
        # total wear / (hot laps count + in out laps count)

        self.laps: list[Lap] = []
        self.best_lap: Optional[Lap] = None
        self.best_sectors: list[Optional[Sector]] = [None, None, None]

    @property
    def wear_per_lap_tread(self):
        return self.wear_percent_per_lap * 3  # in tread

    @property
    def fuel_per_lap_L(self):
        if not self.laps or len(self.laps) < 2:
            return 0
        second_lap = self.laps[1]
        last_lap = self.laps[-1]
        fuel_used = (
            second_lap.start_fuel_percent - last_lap.end_fuel_percent
            if second_lap.start_fuel_percent
            else 0
        )
        fuel_used *= 120  # liters
        num_laps = (last_lap.lap_number - second_lap.lap_number) + 1
        return fuel_used / num_laps

    @property
    def fuel_per_minute(self):
        if not self.laps or len(self.laps) < 2:
            return 0
        sum_time_s = sum(lap.time_s for lap in self.laps[1:])
        total_time_minutes = sum_time_s / 60.0
        second_lap = self.laps[1]
        last_lap = self.laps[-1]
        fuel_used = (
            second_lap.start_fuel_percent - last_lap.end_fuel_percent
            if second_lap.start_fuel_percent
            else 0
        )
        fuel_used *= 120  # liters
        return fuel_used / total_time_minutes


class Sector:
    def __init__(
        self,
        sector: int,
        time_s: float,
        is_valid: bool,
        start_fuel_percent: float,
        end_fuel_percent: float,
        start_tire_wear_percent: float,
        end_tire_wear_percent: float,
    ):
        self.sector = sector
        self.time_s = time_s
        self.is_valid = is_valid
        self.start_fuel_percent = start_fuel_percent
        self.end_fuel_percent = end_fuel_percent
        self.start_tire_wear_percent = start_tire_wear_percent
        self.end_tire_wear_percent = end_tire_wear_percent
        pass

    @staticmethod
    def sector_from_lap(lap: Lap, sector: int, time_s: float):
        start_fuel_percent = (
            lap.sectors[sector - 2].end_fuel_percent
            if lap.sectors
            else (lap.start_fuel_percent if lap.start_fuel_percent else None)
        )
        end_fuel_percent = (
            (start_fuel_percent - (lap.fuel_percent_per_second * time_s))
            if start_fuel_percent
            else None
        )
        start_tire_wear_percent = (
            lap.sectors[sector - 2].end_tire_wear_percent
            if lap.sectors
            else lap.start_tire_wear_percent
        )
        end_tire_wear_percent = start_tire_wear_percent + (
            time_s * lap.tire_wear_used_percent_per_second
        )
        return Sector(
            sector=(lap.lap_number - 1) + ((sector + 1) / 3),
            time_s=time_s,
            is_valid=lap.is_valid,
            start_fuel_percent=start_fuel_percent,
            end_fuel_percent=end_fuel_percent,
            start_tire_wear_percent=start_tire_wear_percent,
            end_tire_wear_percent=end_tire_wear_percent,
        )


class Lap:
    def __init__(
        self,
        lap_number: int,
        time_s: float,
        is_valid: bool,
        start_fuel_percent: float,
        end_fuel_percent: float,
        start_tire_wear_percent: float,
        end_tire_wear_percent: float,
        sector_times_s: list[float],
    ):
        self.lap_number = lap_number
        self.time_s = time_s
        self.is_valid = is_valid

        self.start_fuel_percent = start_fuel_percent
        self.end_fuel_percent = end_fuel_percent
        self.fuel_used_percent = (
            start_fuel_percent - end_fuel_percent
            if start_fuel_percent
            else None  # we don't know lap 1's start fuel
        )
        self.fuel_percent_per_second = (
            (self.fuel_used_percent / self.time_s) if start_fuel_percent else None
        )

        self.start_tire_wear_percent = start_tire_wear_percent
        self.end_tire_wear_percent = end_tire_wear_percent
        self.tire_wear_used_percent = end_tire_wear_percent - start_tire_wear_percent
        self.tire_wear_used_percent_per_second = (
            self.tire_wear_used_percent / self.time_s
        )

        self.sectors: list[Sector] = []
        for i, sector_time in enumerate(sector_times_s):
            self.sectors.append(Sector.sector_from_lap(self, i + 1, sector_time))

        self.delta_to_best_in_stint: Optional[float] = None
        self.delta_to_best_sectors_in_stint: list[Optional[float]] = [None, None, None]

    @staticmethod
    def lap_time_str_to_s(lap_time_str: str):
        minutes, seconds = lap_time_str.split(":")
        seconds = int(minutes) * 60 + float(seconds)
        return seconds

    @staticmethod
    def laps_to_sectors_df(laps: list[Lap]):
        sectors: list[dict] = []
        for lap in laps:
            if not lap.is_valid:
                continue
            if not lap.start_fuel_percent:
                continue
            for i, sector in enumerate(lap.sectors):
                sectors.append(
                    {
                        "Sector": sector.sector,
                        f"Time": sector.time_s,
                        f"%DiffToBest": lap.delta_to_best_sectors_in_stint[i],
                        "FuelStart": sector.start_fuel_percent,
                        "FuelEnd": sector.end_fuel_percent,
                        "TireStart": sector.start_tire_wear_percent,
                        "TireEnd": sector.end_tire_wear_percent,
                        "Valid": sector.is_valid,
                    }
                )
        df = pd.DataFrame(sectors)
        return df

    @staticmethod
    def laps_to_df(laps: list[Lap]):
        df = pd.DataFrame(
            [
                {
                    "Lap": lap.lap_number,
                    "Time": lap.time_s,
                    "%DiffToBest": lap.delta_to_best_in_stint,
                    "FuelStart": lap.start_fuel_percent,
                    "FuelEnd": lap.end_fuel_percent,
                    "TireStart": lap.start_tire_wear_percent,
                    "TireEnd": lap.end_tire_wear_percent,
                    "Valid": lap.is_valid,
                }
                for lap in laps
                if lap.start_fuel_percent and lap.is_valid
            ]
        )
        return df

    @staticmethod
    def parse_laps(stints: list[Stint], laps_csv: pd.DataFrame):
        def end_stint(stint: Stint):
            # set delta to best in stint
            for lap in stint.laps:
                lap.delta_to_best_in_stint = (
                    lap.time_s - stint.best_lap.time_s
                ) / stint.best_lap.time_s

                for i, sector in enumerate(lap.sectors):
                    lap.delta_to_best_sectors_in_stint[i] = (
                        sector.time_s - stint.best_sectors[i].time_s
                    ) / stint.best_sectors[i].time_s

            print(f"Stint {stint.date.date()} laps {stint.start}-{stint.end}:")
            print(f"  L/lap: {stint.fuel_per_lap_L:.2f}")
            print(f"  L/min: {stint.fuel_per_minute:.2f}")
            print(f"  Wear/lap: {stint.wear_per_lap_tread:.2f}")

            return stint

        MAX_FUEL = 120  # liters
        stint_idx = 0
        stint = stints[stint_idx]
        prev_lap_number = None
        for _, l in laps_csv.iterrows():
            # from soma
            # lap,is_invalid,lap_time_ms,sector_1_ms,sector_2_ms,sector_3_ms,lap_time_str,sector_1_str,sector_2_str,sector_3_str,track_grip,rain_intensity,air_temp,track_temp
            lap_number = l["lap"]
            lap_time_ms = l["lap_time_ms"]
            sector_1_ms = l["sector_1_ms"]
            sector_2_ms = l["sector_2_ms"]
            sector_3_ms = l["sector_3_ms"]
            lap_is_valid = not l["is_invalid"]
            tyre_set = l["tyre_set"]

            # from acc race results companion
            # lap_time_s = Lap.lap_time_str_to_s(l["Lap Time"])
            # sector1_time_s = Lap.lap_time_str_to_s(l["Sector 1"])
            # sector2_time_s = Lap.lap_time_str_to_s(l["Sector 2"])
            # sector3_time_s = Lap.lap_time_str_to_s(l["Sector 3"])
            # lap_is_valid = pd.isna(l["Penalty"])

            # try switch stints
            if prev_lap_number and (
                lap_number < prev_lap_number or lap_number > stint.end
            ):
                stints[stint_idx] = end_stint(stint)
                stint_idx += 1
                try:
                    stint = stints[stint_idx]
                except IndexError:
                    print(
                        f"Warning, defined stints do not match the laps data at lap {lap_number}."
                    )
                    return stints
            prev_lap_number = lap_number

            # percent of fuel left in tank at end of lap
            end_fuel_percent = l["fuel"] / MAX_FUEL
            start_fuel_percent = (
                stint.laps[-1].end_fuel_percent
                if stint.laps
                else None  # we don't know start fuel of first lap
            )

            start_tire_wear_percent = (
                stint.laps[-1].end_tire_wear_percent
                if stint.laps
                else stint.wear_percent_per_lap  # always one out lap
            )

            lap = Lap(
                lap_number=lap_number,
                time_s=lap_time_ms / 1000.0,
                is_valid=lap_is_valid,
                start_fuel_percent=start_fuel_percent,
                end_fuel_percent=end_fuel_percent,
                start_tire_wear_percent=start_tire_wear_percent,
                end_tire_wear_percent=((lap_number + 1) * stint.wear_percent_per_lap),
                sector_times_s=[
                    sector_1_ms / 1000.0,
                    sector_2_ms / 1000.0,
                    sector_3_ms / 1000.0,
                ],
            )
            stint.laps.append(lap)
            if lap.is_valid:
                if not stint.best_lap or stint.best_lap.time_s > lap.time_s:
                    stint.best_lap = lap

                for i, sector in enumerate(lap.sectors):
                    if (
                        not stint.best_sectors[i]
                        or stint.best_sectors[i].time_s > sector.time_s
                    ):
                        stint.best_sectors[i] = sector

        stints[stint_idx] = end_stint(stint)
        return stints


def analyze_laps(laps_df: pd.DataFrame):
    # remove rows with missing values for the features/target
    df = laps_df[["FuelEnd", "TireEnd", "%DiffToBest"]].dropna().copy()

    def _remove_outliers_iqr(df_in, cols, k: float = 0.5):
        mask = np.ones(len(df_in), dtype=bool)
        for c in cols:
            q1 = df_in[c].quantile(0.25)
            q3 = df_in[c].quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                # skip column if no spread
                continue
            lower = q1 - k * iqr
            upper = q3 + k * iqr
            mask &= df_in[c].between(lower, upper)
        return df_in.loc[mask]

    df_clean = _remove_outliers_iqr(df, ["FuelEnd", "TireEnd", "%DiffToBest"])

    # use cleaned data for modeling
    X = df_clean[["FuelEnd", "TireEnd"]]
    y = df_clean["%DiffToBest"]

    # Plot original vs cleaned data
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 10))

    # Original data distributions
    sns.histplot(
        data=df, x="FuelEnd", ax=ax1, color="blue", alpha=0.5, label="Original"
    )
    sns.histplot(
        data=df_clean, x="FuelEnd", ax=ax1, color="red", alpha=0.5, label="Cleaned"
    )
    ax1.set_title("Fuel Distribution")
    ax1.legend()

    sns.histplot(
        data=df, x="TireEnd", ax=ax2, color="blue", alpha=0.5, label="Original"
    )
    sns.histplot(
        data=df_clean, x="TireEnd", ax=ax2, color="red", alpha=0.5, label="Cleaned"
    )
    ax2.set_title("Tire Distribution")
    ax2.legend()

    sns.histplot(
        data=df, x="%DiffToBest", ax=ax3, color="blue", alpha=0.5, label="Original"
    )
    sns.histplot(
        data=df_clean, x="%DiffToBest", ax=ax3, color="red", alpha=0.5, label="Cleaned"
    )
    ax3.set_title("Delta Distribution")
    ax3.legend()

    # Boxplot comparison
    comparison_data = pd.concat(
        [df.assign(Dataset="Original"), df_clean.assign(Dataset="Cleaned")]
    )
    sns.boxplot(data=comparison_data, x="Dataset", y="%DiffToBest", ax=ax4)
    ax4.set_title("Delta Boxplot Comparison")

    plt.tight_layout()

    # # Create polynomial features
    # X_fuel = np.polynomial.polynomial.polyvander(laps_df["FuelEnd"], deg=1)
    # X_tire = np.polynomial.polynomial.polyvander(laps_df["TireEnd"], deg=4)

    # # Fit polynomial models
    # fuel_model = sm.OLS(y, X_fuel).fit()
    # tire_model = sm.OLS(y, X_tire).fit()

    # print("Fuel Model:")
    # print(fuel_model.summary())
    # print("\nTire Model:")
    # print(tire_model.summary())

    constant_X = sm.add_constant(X)
    combined_model = sm.OLS(y, constant_X).fit()
    print("Model:")
    print(combined_model.summary())

    vif_df = pd.DataFrame()
    vif_df["Feature"] = constant_X.columns
    vif_df["VIF"] = [
        variance_inflation_factor(constant_X.values, i)
        for i in range(constant_X.shape[1])
    ]
    print(vif_df)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 10))

    # use combined_model (linear in FuelEnd and TireEnd)
    intercept = combined_model.params.get("const", combined_model.params[0])
    coeff_fuel = combined_model.params["FuelEnd"]
    coeff_tire = combined_model.params["TireEnd"]

    mean_tire = df_clean["TireEnd"].mean()
    mean_fuel = df_clean["FuelEnd"].mean()

    # Top plot - effect of Fuel (holding Tire at its mean)
    fuel_x = np.linspace(df_clean["FuelEnd"].min(), df_clean["FuelEnd"].max(), 100)
    fuel_y = intercept + coeff_fuel * fuel_x

    sns.scatterplot(data=df_clean, x="FuelEnd", y="%DiffToBest", alpha=0.7, ax=ax1)
    ax1.plot(fuel_x, fuel_y, "r-", linewidth=2)
    ax1.set_title("Lap Time Delta vs Fuel (combined linear model)")
    ax1.invert_xaxis()

    # Bottom plot - effect of Tire (holding Fuel at its mean)
    tire_x = np.linspace(df_clean["TireEnd"].min(), df_clean["TireEnd"].max(), 100)
    tire_y = intercept + coeff_tire * tire_x

    sns.scatterplot(data=df_clean, x="TireEnd", y="%DiffToBest", alpha=0.7, ax=ax2)
    ax2.plot(tire_x, tire_y, "r-", linewidth=2)
    ax2.set_title("Lap Time Delta vs Tire Wear (combined linear model)")

    plt.tight_layout()

    # 3D visualization with predicted surface from combined model
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")

    sc = ax.scatter(
        df_clean["TireEnd"],
        df_clean["FuelEnd"],
        df_clean["%DiffToBest"],
        c=df_clean["%DiffToBest"],
        cmap="coolwarm",
        s=80,
        edgecolor="k",
    )

    # make prediction surface
    tire_grid, fuel_grid = np.meshgrid(
        np.linspace(df_clean["TireEnd"].min(), df_clean["TireEnd"].max(), 30),
        np.linspace(df_clean["FuelEnd"].min(), df_clean["FuelEnd"].max(), 30),
    )
    pred_grid = intercept + coeff_fuel * fuel_grid + coeff_tire * tire_grid
    ax.plot_surface(
        tire_grid, fuel_grid, pred_grid, alpha=0.35, cmap="viridis", linewidth=0
    )

    ax.set_xlabel("Tire End")
    ax.set_ylabel("Fuel End")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_zlabel("Δ to Best Lap (%)")
    fig.colorbar(sc, ax=ax, shrink=0.6, label="Δ to Best Lap")
    ax.set_title(
        "Effect of Tire and Fuel End on Lap Time Delta (combined model)", pad=20
    )

    # return combined model params (keeps the original two-value return signature)
    return combined_model.params, combined_model.params


def compare_model_to_actual(
    stint: Stint,
    fuel_params: pd.DataFrame,
    tire_params: pd.DataFrame,
    ax: Axes,
):
    # determine stint length and lap range
    last_lap = stint.laps[-1]
    first_lap = stint.laps[0]
    num_laps = (last_lap.lap_number - first_lap.lap_number) + 1
    laps = np.arange(0, num_laps)  # start at 0 for baseline comparison

    # calculate per-lap changes
    fuel_per_lap = (first_lap.end_fuel_percent - last_lap.end_fuel_percent) / (
        num_laps - 1
    )

    tire_per_lap = stint.wear_percent_per_lap

    # calculate predicted values
    fuel_array = first_lap.end_fuel_percent - (laps * fuel_per_lap)
    tire_array = first_lap.start_tire_wear_percent + (laps * tire_per_lap)

    fuel_prediction = np.polynomial.polynomial.polyval(fuel_array, fuel_params)
    tire_prediction = np.polynomial.polynomial.polyval(tire_array, tire_params)
    combined_prediction = fuel_prediction + tire_prediction

    # plot actual vs predicted
    actual_deltas = []
    for l in stint.laps:
        if not l.is_valid:
            continue
        actual_deltas.append(l.delta_to_best_in_stint)

    x_vals = laps[: len(actual_deltas)]

    ax.plot(x_vals, actual_deltas, "bo-", label="Actual")
    ax.plot(
        x_vals, fuel_prediction[: len(actual_deltas)], "g--", label="Fuel Predicted"
    )
    ax.plot(
        x_vals, tire_prediction[: len(actual_deltas)], "m--", label="Tire Predicted"
    )
    ax.plot(x_vals, combined_prediction[: len(actual_deltas)], "r--", label="Predicted")

    # build and wrap title so it will fit smaller windows, then reserve space for it
    raw_title = (
        f"Actual vs Predicted Lap Time Delta  |  "
        f"Start Wear % {stint.start_wear_percent}  -  First Lap End Fuel % {stint.laps[0].end_fuel_percent:.2f}  |  "
        f"{stint.date}"
    )
    wrapped_title = "\n".join(textwrap.wrap(raw_title, width=80))
    ax.set_title(wrapped_title, fontsize=10)

    ax.set_xlabel("Lap Number")
    ax.set_ylabel("Delta to Best (%)")
    ax.set_ylim(-0.001, 0.020)
    ax.legend()
    ax.grid(True)

    plt.tight_layout()


def print_avgs(stints: list[Stint]):
    # print the weighted avg fuel and tire wear per lap across all stints
    total_laps = sum(len(stint.laps) for stint in stints)
    if total_laps == 0:
        print("No laps to analyze")
        return

    total_fuel = sum(stint.fuel_per_lap_L * len(stint.laps) for stint in stints)
    total_wear = sum(stint.wear_per_lap_tread * len(stint.laps) for stint in stints)

    avg_fuel_per_lap = total_fuel / total_laps
    avg_wear_per_lap = total_wear / total_laps

    print("------------------------------------------------")
    print(f"wAvg L/Lap: {avg_fuel_per_lap:.4f} L")
    print(f"wAvg L%/Lap: {(avg_fuel_per_lap / 120):.4f}")
    print(f"wAvg Wear/Lap: {avg_wear_per_lap:.4f} tread")
    print(f"wAvg Wear%/Lap: {avg_wear_per_lap / 3:.4f}")
    print("------------------------------------------------")


if __name__ == "__main__":
    current_dir = os.path.dirname(__file__)
    laps_csv = pd.read_csv(
        os.path.join(current_dir, "Sessions/suzuka/combined.csv"),
        header=0,
    )
    # laps_csv = pd.read_csv("2025-10-08 210510 race.csv")

    # fmt: off
    stints: list[Stint] = [
        ####################
        ##### valencia #####
        ####################
        # Stint(date=datetime(2025,10,26), start=1, end=13, start_tread=3, end_tread=2.39, in_out_laps_count=0),
        # Stint(date=datetime(2025,10,26), start=14, end=25, start_tread=2.35, end_tread=1.78, in_out_laps_count=0),
        # Stint(date=datetime(2025,10,27), start=1, end=10, start_tread=3, end_tread=2.52, in_out_laps_count=0),
        # Stint(date=datetime(2025,10,27), start=11, end=22, start_tread=2.52, end_tread=1.94, in_out_laps_count=0),
        # Stint(date=datetime(2025,10,29), start=1, end=27, start_tread=3, end_tread=1.81, in_out_laps_count=0)
        ################
        ##### cota #####
        ################
        # Stint(date=datetime(2025,10,17), start=1, end=13, start_tread=3, end_tread=2.23, in_out_laps_count=0),
        # Stint(date=datetime(2025,10,17), start=14, end=27, start_tread=2.23, end_tread=1.42, in_out_laps_count=0),
        # Stint(date=datetime(2025,10,22), start=4, end=16, start_tread=3, end_tread=2.18, in_out_laps_count=0),
        #######################
        ##### silverstone #####
        #######################
        # Stint(start=1, end=13, start_tread=3, end_tread=2.30, in_out_laps_count=1),
        # Stint(start=14, end=26, start_tread=2.30, end_tread=1.58, in_out_laps_count=1),
        # Stint(start=27, end=38, start_tread=3, end_tread=2.34, in_out_laps_count=1),
        # Stint(start=7, end=17, start_tread=2.54, end_tread=1.99, in_out_laps_count=1),
        # Stint(start=1, end=12, start_tread=3, end_tread=2.2, in_out_laps_count=1),
        #####################
        ##### zandvoort #####
        #####################
        # Stint(start=1, end=8, date=datetime(2025,11,9), start_tread=3, end_tread=2.39, in_out_laps_count=0),
        # Stint(start=9, end=36, date=datetime(2025,11,9), start_tread=2.39, end_tread=1.78, in_out_laps_count=0),
        ##########################
        ##### mount panorama #####
        ##########################
        # Stint(start=1, end=5, date=datetime(2025, 11, 9), start_tread=3, end_tread=2.74, in_out_laps_count=0),
        # Stint(start=6, end=10, date=datetime(2025, 11, 9), start_tread=3, end_tread=2.74, in_out_laps_count=0),
        # Stint(start=11, end=14, date=datetime(2025, 11, 9), start_tread=2.74, end_tread=2.51, in_out_laps_count=0),
        # Stint(start=15, end=18, date=datetime(2025, 11, 9), start_tread=2.51, end_tread=2.29, in_out_laps_count=0),
        # Stint(start=1, end=7, date=datetime(2025, 11, 11), start_tread=3, end_tread=2.69, in_out_laps_count=0),
        # Stint(start=3, end=15, date=datetime(2025, 11, 12), start_tread=2.85, end_tread=2.26, in_out_laps_count=0),
        # Stint(start=17, end=22, date=datetime(2025, 11, 12), start_tread=3, end_tread=2.72, in_out_laps_count=0),
        ##################
        ##### suzuka #####
        ##################
        # Stint(start=2, end=21, date=datetime(2025, 11, 17), in_out_laps_count=0),
        # Stint(start=2, end=11, date=datetime(2025, 11, 18), in_out_laps_count=0),
        ########################
        ##### brands hatch #####
        ########################
        Stint(start=1, end=20, date=datetime(2025, 12, 3), in_out_laps_count=0),
        Stint(start=1, end=27, date=datetime(2025, 11, 30), in_out_laps_count=0),
    ]
    # fmt: on

    best_lap_in_stint: Lap
    stints = Lap.parse_laps(stints, laps_csv)
    print_avgs(stints)
    laps = []
    [laps.extend(stint.laps) for stint in stints]
    laps_df = Lap.laps_to_df(laps)
    fuel_model_params, tire_model_params = analyze_laps(laps_df)

    sectors_df = Lap.laps_to_sectors_df(laps)
    fuel_model_params, tire_model_params = analyze_laps(sectors_df)
    plt.show()

    fig, axs = plt.subplots(len(stints), figsize=(10, 6 * len(stints)), sharex=True)
    for ax, stint in zip(axs, stints):
        compare_model_to_actual(stint, fuel_model_params, tire_model_params, ax=ax)
    plt.show()

    pass
