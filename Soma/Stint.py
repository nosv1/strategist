import os
from datetime import datetime, timedelta
from statistics import median
from threading import Thread
from typing import Optional

import pandas as pd
from CarStatus import CarStatusHistory
from Lap import Lap, MiniSector, Sector
from Session import Session
from util import ms_to_m_ss_000


class Stint:
    def __init__(self, stint_number: int, session: Session, now: datetime):
        self.stint_number = stint_number
        self.session = session  # may be out of date when stint ends
        self.start_time: datetime = now
        self.end_time: Optional[datetime] = None

        self.mini_sector_history: list[list[MiniSector]] = [
            [] for _ in range(self.session.num_mini_sectors)
        ]
        self.sector_history: list[list[Sector]] = [[] for _ in range(3)]
        self.laps: list[Lap] = []
        self.valid_laps: list[Lap] = []

        # lap the best split[i] occured on where i represents the split index
        self.best_splits: list[Lap] = []
        self.best_lap: Optional[Lap] = None

        self.car_status_history = CarStatusHistory()

    @property
    def running_stint_time(self) -> timedelta:
        return datetime.now() - self.start_time

    @property
    def hot_stint_time_ms(self):
        if len(self.laps) >= 5 and all(
            not l.lap_info.is_invalid for l in self.laps[-5:]
        ):
            return sum(l.lap_info.lap_time_ms for l in self.laps[-5:]) / 5

    @property
    def stint_time(self) -> Optional[timedelta]:
        if not self.end_time:
            return None
        return self.end_time - self.start_time

    @property
    def median_lap_ms(self):
        if not self.valid_laps:
            return 0
        return median(l.lap_info.lap_time_ms for l in self.valid_laps)

    @property
    def start_lap(self):
        if not self.laps:
            return 0
        return self.laps[0].lap_number

    def dump_stint(self):
        def worker(stint: Stint, sm_track: str):
            rows = []
            for l in stint.laps:
                rows.append(
                    {
                        "lap": l.lap_number,
                        "is_invalid": l.lap_info.is_invalid,
                        "lap_time_ms": l.lap_info.lap_time_ms,
                        "sector_1_ms": l.lap_info.splits[0],
                        "sector_2_ms": l.lap_info.splits[1],
                        "sector_3_ms": l.lap_info.splits[2],
                        "lap_time_str": ms_to_m_ss_000(l.lap_info.lap_time_ms),
                        "sector_1_str": ms_to_m_ss_000(l.lap_info.splits[0]),
                        "sector_2_str": ms_to_m_ss_000(l.lap_info.splits[1]),
                        "sector_3_str": ms_to_m_ss_000(l.lap_info.splits[2]),
                        "track_grip": l.track_status.track_grip,
                        "rain_intensity": l.track_status.weather,
                        "air_temp": l.track_status.air_temp,
                        "track_temp": l.track_status.track_temp,
                        "fuel": l.car_status.fuel,
                        "tyre_set": l.car_status.tyre_set,
                    }
                )

            current_dir = os.path.dirname(__file__)
            sessions_dir = os.path.join(current_dir, "..", "sessions")
            track_dir = os.path.join(sessions_dir, sm_track)
            os.makedirs(track_dir, exist_ok=True)

            filename = f"{self.start_time.strftime('%Y%m%d_%H%M%S')}_{self.session.session_type.lower()}_stint_{self.stint_number}_{len(self.laps)}_laps.csv"
            path = os.path.join(track_dir, filename)

            if os.path.exists(path):
                os.remove(path)

            df = pd.DataFrame(rows)
            df.to_csv(path, mode="w", header=True, index=False)
            pass

        t = Thread(
            target=worker, args=(self, self.session.track_info.sm_track), daemon=True
        )
        t.start()
        pass

    def end_stint(self, dump_stint: bool = False):
        self.end_time = datetime.now()
        if dump_stint:
            self.dump_stint()
        pass

    def try_update_bests(self, lap: Lap):
        if (
            not self.best_lap
            or lap.lap_info.lap_time_ms < self.best_lap.lap_info.lap_time_ms
        ):
            self.best_lap = lap

        if not self.best_splits:
            self.best_splits = [lap, lap, lap]

        else:
            for i, s in enumerate(lap.lap_info.splits):
                if s < self.best_splits[i].lap_info.splits[i]:
                    self.best_splits[i] = lap
        pass

    def on_new_mini_sector(self, mini_sector: MiniSector):
        self.car_status_history.update(mini_sector.car_status)
        pass

    def on_new_sector(self, sector: Sector):
        pass

    def on_new_lap(self, lap: Lap):
        self.laps.append(lap)
        if not lap.lap_info.is_invalid:
            self.valid_laps.append(lap)
            self.try_update_bests(lap)
        pass
