from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Optional

from Alerts import Alerts
from pyaccsharedmemory import ACC_map


class TrackInfo:
    def __init__(self):
        self.sm_track: str = ""
        self.pit_DT: timedelta = None
        self.turns: list[dict] = []
        self.race_pace_s: Optional[float] = None
        self.alerts: Alerts = Alerts()

    def get_tire_change_pit_loss_s(self, pit_DT: timedelta) -> int:
        """Calculate total pit loss time in seconds, including minimum stop time."""
        # we send in pit_DT because it could be none, so the caller should check
        # if pit_DT is None before calling this function

        # ACC adds 35s to pit DT for min stop time, 30 for tire change, 5 for stop and go
        min_stop_time_s = 35
        return int(pit_DT.total_seconds() + min_stop_time_s)

    def load_track_json(self, track_json: str):
        if not os.path.isfile(track_json):
            print(f"[TrackInfo] WARNING: Track JSON file not found: {track_json}")
            return

        with open(track_json, "r") as f:
            data: dict = json.load(f)

        self.pit_DT = timedelta(seconds=data.get("pit_DT_s", 0))
        self.turns = data.get("turns", [])
        self.race_pace_s = data.get("race_pace_s", None)
        self.alerts.update_from_data(data.get("alerts", []))
        print(f"[TrackInfo] Loaded track data from {track_json}")

    def update_from_sm(self, sm: ACC_map):
        self.sm_track = sm.Static.track.rstrip("\x00").lower()
        pass
