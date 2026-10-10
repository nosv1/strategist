from datetime import datetime
from typing import Optional

from CarStatus import CarStatus
from pyaccsharedmemory import ACC_RAIN_INTENSITY, ACC_TRACK_GRIP_STATUS
from PyAccWrapper import PositionEntry

from PyAccUdpInterface.LapInfo import LapInfo


class TrackStatus:
    def __init__(
        self,
        air_temp: int,
        track_temp: int,
        weather: ACC_RAIN_INTENSITY,
        track_grip: ACC_TRACK_GRIP_STATUS,
    ):
        self.air_temp = air_temp
        self.track_temp = track_temp
        self.weather = weather
        self.track_grip = track_grip
        pass


class Segment:
    def __init__(
        self,
        lap: int,
        idx: int,
        timestamp: datetime,
        time_s: int,
        is_invalid: bool,
        car_status: CarStatus,
        track_status: TrackStatus,
        position_entry: PositionEntry,
    ):
        self.lap = lap
        self.segment_idx = idx
        self.timestamp = timestamp
        self.time_ms = time_s * 1000
        self.is_invalid = is_invalid
        self.car_status = car_status
        self.track_status = track_status
        self.position_entry = position_entry


class MiniSector(Segment):
    def __init__(
        self,
        lap: int,
        idx: int,
        timestamp: datetime,
        # time_s is adjusted based on spline error in relation to speed
        # and expected spline position for mini sector
        time_s: int,
        is_invalid: bool,
        car_status: CarStatus,
        track_status: TrackStatus,
        position_entry: PositionEntry,
        sector_index: Optional[int] = None,
    ):
        super().__init__(
            lap=lap,
            idx=idx,
            timestamp=timestamp,
            time_s=time_s,
            is_invalid=is_invalid,
            car_status=car_status,
            track_status=track_status,
            position_entry=position_entry,
        )
        # sometimes set outside of init,
        self.sector_idx = sector_index


class Sector(Segment):
    def __init__(
        self,
        lap: int,
        idx: int,
        timestamp: datetime,
        time_s: int,
        is_invalid: bool,
        car_status: CarStatus,
        track_status: TrackStatus,
        position_entry: PositionEntry,
    ):
        super().__init__(
            lap=lap,
            idx=idx,
            timestamp=timestamp,
            time_s=time_s,
            is_invalid=is_invalid,
            car_status=car_status,
            track_status=track_status,
            position_entry=position_entry,
        )


class Lap:
    def __init__(
        self,
        lap_number: int,
        lap_info: LapInfo,
        pos_history: list[PositionEntry],
        car_status: CarStatus,
        track_status: TrackStatus,
    ):
        self.lap_number = lap_number
        self.lap_info = lap_info
        self.pos_history = pos_history
        self.mini_sectors: list[MiniSector] = []
        self.car_status = car_status
        self.track_status = track_status
