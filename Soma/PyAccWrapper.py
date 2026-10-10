from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from threading import Thread
from typing import Dict

import pandas as pd

from PyAccUdpInterface.Enums import CarLocation
from PyAccUdpInterface.LapInfo import LapInfo


@dataclass
class CarEntry:
    position: int
    car_number: int
    car_id: int
    cup_category: str
    cup_position: int
    manufacturer: int
    team: str
    driver_first_name: str
    driver_last_name: str
    lap: int
    delta: float
    current_lap: LapInfo
    last_lap: LapInfo
    best_session_lap: LapInfo
    sectors: list[float]
    car_location: CarLocation
    spline_position: float
    world_pos_x: float
    world_pos_y: float
    gear: int
    kph: int

    @property
    def driver_full_name(self) -> str:
        return f"{self.driver_first_name} {self.driver_last_name}"

    @staticmethod
    def entry_to_car_entry(entry: Dict[int, dict]):
        return CarEntry(
            position=entry["position"],
            car_number=entry["car_number"],
            car_id=entry["car_id"],
            cup_category=entry["cup_category"],
            cup_position=entry["cup_position"],
            manufacturer=entry["manufacturer"],
            team=entry["team"],
            driver_first_name=entry["driver"]["first_name"],
            driver_last_name=entry["driver"]["last_name"],
            lap=entry["lap"],
            delta=entry["delta"],
            current_lap=entry["current_lap"],
            last_lap=entry["last_lap"],
            best_session_lap=entry["best_session_lap"],
            sectors=entry["sectors"],
            car_location=CarLocation[entry["car_location"]],
            spline_position=entry["spline_position"],
            world_pos_x=entry["world_pos_x"],
            world_pos_y=entry["world_pos_y"],
            gear=entry["gear"],
            kph=entry["kph"],
        )

    @staticmethod
    def entries_to_car_entries(
        entries: Dict[int, dict],
    ) -> tuple[Dict[int, CarEntry], Dict[str, int]]:
        """Convert raw UDP entries dict to CarEntry objects with name mapping.

        Args:
            entries: Raw entries dictionary from UDP data

        Returns:
            Tuple of:
            - Dict mapping car_id to CarEntry objects
            - Dict mapping driver full names to car_ids for quick lookup
        """
        car_entries: Dict[int, CarEntry] = {}
        name_to_id: Dict[str, int] = {}

        for car_id, entry in entries.items():
            if not entry:
                continue

            car_entry = CarEntry.entry_to_car_entry(entry)
            car_entries[car_id] = car_entry
            name_to_id[car_entry.driver_full_name] = car_id

        return car_entries, name_to_id

    @staticmethod
    def dump_entries(entries: dict[int, "CarEntry"]):
        """Asynchronously dump current entries to a CSV file (non-blocking).

        This spawns a short-lived background thread that appends one row per car
        into a single CSV file in the same directory as this module.
        """

        def worker(snapshot: dict[int, CarEntry]):
            try:
                rows = []
                ts = datetime.now().isoformat()
                for cid, c in snapshot.items():
                    rows.append(
                        {
                            "timestamp": ts,
                            "position": c.position,
                            "car_number": c.car_number,
                            "car_id": c.car_id,
                            "driver": c.driver_full_name,
                            "team": c.team,
                            "manufacturer": c.manufacturer,
                            "cup_category": c.cup_category,
                            "cup_position": c.cup_position,
                            "lap": c.lap,
                            "delta": c.delta,
                            "kph": c.kph,
                            "gear": c.gear,
                            "car_location": str(c.car_location),
                            "spline_position": str(c.spline_position),
                            "world_pos_x": c.world_pos_x,
                            "world_pos_y": c.world_pos_y,
                            "current_lap_time_ms": getattr(
                                c.current_lap, "lap_time_ms", None
                            ),
                            "last_lap_time_ms": getattr(
                                c.last_lap, "lap_time_ms", None
                            ),
                            "best_session_lap_ms": getattr(
                                c.best_session_lap, "lap_time_ms", None
                            ),
                        }
                    )

                current_dir = os.path.dirname(__file__)
                path = os.path.join(current_dir, "entries_dump.csv")

                df = pd.DataFrame(rows)
                # append, write header only if file doesn't exist
                df.to_csv(path, mode="a", header=not os.path.exists(path), index=False)
            except Exception as e:
                # don't raise in background thread; just print for debugging
                print("Error dumping entries to CSV:", e)

        # Make a shallow copy of entries to avoid race conditions with the caller
        try:
            snapshot = dict(entries)
        except Exception:
            snapshot = entries

        t = Thread(target=worker, args=(snapshot,), daemon=True)
        t.start()


@dataclass
class PositionEntry:
    timestamp: datetime
    lap_time_at_pos_ms: int
    x: float
    y: float
    spline_pos: float
    kph: int
