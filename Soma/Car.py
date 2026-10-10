from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta
from enum import Enum
from statistics import mean
from typing import Generator, Optional

from Alerts import Alerts, TCAlerts
from EventHandler import EventHandler
from Lap import CarStatus, Lap, MiniSector, Sector, TrackStatus
from pandas import DataFrame
from pyaccsharedmemory import ACC_map, Wheels
from PyAccWrapper import CarEntry, PositionEntry
from Session import Session
from Stint import Stint
from util import ms_to_m_ss_000
from VoiceControl import VoiceControl

from PyAccUdpInterface.Enums import CarLocation, SessionType


class Car:
    class Events(Enum):
        ON_LAP_INVALIDATED = 4
        ON_NEW_LAP = 1
        ON_NEW_MIN_SPEED = 6
        ON_NEW_MAX_SPEED = 5
        ON_NEW_MINI_SECTOR = 8
        ON_NEW_SECTOR = 7
        ON_NEW_TURN = 3
        ON_EXITING_PIT_LANE = 9
        ON_ENTERING_PIT_LANE = 10
        # add event here, then add it in the events dict in __init__, then add a handler function for it

    def __init__(
        self,
        entry: CarEntry,
        old_car: Optional[Car],
        session: Session,
        now: datetime,
    ):
        self.entry: CarEntry = entry
        self.old_entry: Optional[CarEntry] = old_car.entry if old_car else None
        self.session: Session = session
        self.now: datetime = now

        # mini sectors
        self.current_mini_sector_idx: Optional[int] = (
            None if not old_car else old_car.current_mini_sector_idx
        )
        self.running_mini_sectors: list[Optional[MiniSector]] = (
            [None for i in range(self.session.num_mini_sectors)]
            if not old_car
            else old_car.running_mini_sectors
        )

        self.best_mini_sectors: list[Optional[MiniSector]] = (
            [None for i in range(self.session.num_mini_sectors)]
            if not old_car
            else old_car.best_mini_sectors
        )

        self.stints: list[Stint] = [] if not old_car else old_car.stints
        self.pos_entry_history: list[PositionEntry] = (
            [] if not old_car else old_car.pos_entry_history
        )
        self.pit_laps: list[int] = [] if not old_car else old_car.pit_laps

        """
        for events that are observed in Car but handled in a child class, the 
        function is set to None, then the events dict is updated with the 
        function that will be called by the event handler
        """
        self.event_handler = EventHandler(
            events={
                self.Events.ON_NEW_MINI_SECTOR.name: (False, None),
                self.Events.ON_NEW_SECTOR.name: (False, None),
                self.Events.ON_NEW_LAP.name: (False, None),
                self.Events.ON_LAP_INVALIDATED.name: (False, None),
                self.Events.ON_EXITING_PIT_LANE.name: (False, None),
                self.Events.ON_ENTERING_PIT_LANE.name: (False, None),
            },
        )

    def __eq__(self, other: Car):
        return self.entry.car_number == other.entry.car_number

    def __hash__(self):
        return hash(self.entry.car_number)

    @property
    def is_out_lap(self) -> bool:
        if not self.stints:
            return False

        return len(self.stints[-1].laps) == 0 and any(
            len(ms_history) == 0 for ms_history in self.stints[-1].mini_sector_history
        )

    @property
    def best_mini_sector_lap_time_ms(self) -> Optional[int]:
        if None in self.best_mini_sectors:
            return None
        return sum(ms.time_ms for ms in self.best_mini_sectors if ms is not None)

    @property
    def best_lap(self) -> Optional[Lap]:
        best_lap: Optional[Lap] = None
        for stint in self.stints:
            if stint.best_lap and (
                not best_lap
                or stint.best_lap.lap_info.lap_time_ms < best_lap.lap_info.lap_time_ms
            ):
                best_lap = stint.best_lap
        return best_lap

    @property
    def laps(self) -> Generator[Lap, None, None]:
        for s in self.stints:
            for lap in s.laps:
                yield lap

    @property
    def car_status(self) -> CarStatus:
        if isinstance(self, Hero):
            return CarStatus(
                fuel=self.fuel_remaining,
                tyre_set=self.tyre_set,
                tyre_compound=self.tyre_compound,
                distance_traveled_m=self.distance_traveled,
                wheel_pressure=self.wheel_pressure,
                tyre_temperature=self.tyre_temperature,
            )
        else:
            return CarStatus()

    def is_same_cup(self, other: Car) -> bool:
        return self.entry.cup_category == other.entry.cup_category

    def lap_time_from_recent_mini_sectors_ms(
        self, n_laps: int = 2, top_n_mini_sectors: int = 1
    ) -> Optional[int]:
        """These are only as good as the mini sector estimates, may be off by a little"""
        # calculate the average of the top_n mini sector times over the last n_laps laps
        best_mini_sector_times_ms: list[Optional[int]] = []
        for ms_idx in range(len(self.stints[-1].mini_sector_history)):
            last_n_mini_sectors = self.stints[-1].mini_sector_history[ms_idx][-n_laps:]
            best_mini_sector_times_ms.append(
                mean(
                    sorted(ms.time_ms for ms in last_n_mini_sectors)[
                        :top_n_mini_sectors
                    ]
                )
                if last_n_mini_sectors
                else None
            )
            if best_mini_sector_times_ms[-1] is None:
                return None

        return sum(best_mini_sector_times_ms)

    def get_full_service_pit_loss_remaining_s(self):
        n_mandatory_pits = self.session.mandatory_pits
        if n_mandatory_pits == 0:
            return 0

        n_pits_remaining = n_mandatory_pits - len(
            [pl for pl in self.pit_laps if pl > 0]
        )
        if n_pits_remaining <= 0:
            return 0

        pit_DT = self.session.track_info.pit_DT
        tire_change_pit_loss_s = (
            self.session.track_info.get_tire_change_pit_loss_s(pit_DT) if pit_DT else 0
        )
        pit_loss_remaining_s = tire_change_pit_loss_s * n_pits_remaining
        return pit_loss_remaining_s

    @property
    def predicted_race_time_ms(self) -> Optional[int]:
        predicted_lap_time_ms = self.lap_time_from_recent_mini_sectors_ms(
            n_laps=2, top_n_mini_sectors=1
        )
        pot_lap_time_ms = self.best_mini_sector_lap_time_ms
        if predicted_lap_time_ms is None or pot_lap_time_ms is None:
            return None
        avg_lap_time_ms = (predicted_lap_time_ms + pot_lap_time_ms) // 2
        laps_remaining = (
            self.session.time_remaining.total_seconds() / (avg_lap_time_ms / 1000) + 1
        )
        return int(predicted_lap_time_ms * laps_remaining)

    def delta_to_car(
        self, other: Car, account_for_pit_stops: bool = False
    ) -> timedelta:
        if other is None:
            return timedelta(0)

        if None in {self.current_mini_sector_idx, other.current_mini_sector_idx}:
            return timedelta(0)

        mini_sector_idx: int

        # same lap
        if self.entry.lap == other.entry.lap:
            mini_sector_idx = min(
                self.current_mini_sector_idx, other.current_mini_sector_idx
            )

        # self is ahead of other
        elif self.entry.lap > other.entry.lap:
            # self has not lapped other
            if self.current_mini_sector_idx <= other.current_mini_sector_idx:
                mini_sector_idx = other.current_mini_sector_idx

            else:
                # days is number of laps down
                return timedelta(days=self.entry.lap - other.entry.lap)

        # other is ahead of self
        else:
            # other has not lapped self
            if (
                other.entry.lap - self.entry.lap <= 1
                and other.current_mini_sector_idx <= self.current_mini_sector_idx
            ):
                mini_sector_idx = self.current_mini_sector_idx

            else:
                # days is number of laps down
                return timedelta(days=other.entry.lap - self.entry.lap)

        mini_sector_idx -= 1  # adjust to last completed mini sector

        if None in {
            self.running_mini_sectors[mini_sector_idx],
            other.running_mini_sectors[mini_sector_idx],
        }:
            return timedelta(0)

        if other.current_mini_sector_idx < self.current_mini_sector_idx:
            pass

        def get_pit_loss_adjustment(car: Car):
            return car.running_mini_sectors[mini_sector_idx].timestamp + timedelta(
                seconds=car.get_full_service_pit_loss_remaining_s()
            )

        if account_for_pit_stops:
            self_timestamp = get_pit_loss_adjustment(self)
            other_timestamp = get_pit_loss_adjustment(other)

        else:
            self_timestamp = self.running_mini_sectors[mini_sector_idx].timestamp
            other_timestamp = other.running_mini_sectors[mini_sector_idx].timestamp

        return self_timestamp - other_timestamp

    def start_stint(self):
        stint = Stint(
            stint_number=len(self.stints) + 1, session=self.session, now=self.now
        )
        self.stints.append(stint)
        pass

    def end_stint(self, dump_stint: bool = False):
        if self.stints:
            if self.stints[-1].laps:
                self.stints[-1].session = self.session
                self.stints[-1].end_stint(dump_stint=dump_stint)
            else:
                del self.stints[-1]
        pass

    def _create_and_update_timing_segment(
        self,
        segment_type: MiniSector | Sector,
        idx: int,
        timestamp: datetime,
        running_segments: list[MiniSector | Sector],
        best_segments: list[MiniSector | Sector],
        history_list: list[list[MiniSector | Sector]],
        time_s: float,
        position_entry: PositionEntry,
    ):
        """Generic method to create and update mini sectors or sectors."""
        segment: MiniSector | Sector = segment_type(
            lap=self.entry.lap,
            idx=idx,
            timestamp=timestamp,
            time_s=time_s,
            is_invalid=self.entry.current_lap.is_invalid,
            car_status=self.car_status,
            track_status=TrackStatus(
                air_temp=self.session.air_temp,
                track_temp=self.session.track_temp,
                track_grip=self.session.track_grip_status,
                weather=self.session.rain_now if self.session.rain_now else None,
            ),
            position_entry=position_entry,
        )
        if isinstance(segment, MiniSector) and isinstance(self, Hero):
            segment.sector_idx = self.current_sector_idx

        running_segments[idx] = segment

        if segment.time_ms <= 0:
            return segment

        history_list[idx].append(segment)

        if not segment.is_invalid and (
            best_segments[idx] is None or segment.time_ms < best_segments[idx].time_ms
        ):
            best_segments[idx] = segment

        return segment

    ##################################
    ########      EVENTS      ########
    ##################################

    def on_new_mini_sector(self):
        if self.current_mini_sector_idx is None:
            return

        # current mini sector idx has already ticked over
        # we need to create the mini sector for the previous index
        # that's why things seem to be off by one
        prev_mini_sector = self.running_mini_sectors[self.current_mini_sector_idx - 2]
        time_s = (
            (
                self.pos_entry_history[-1].timestamp
                - prev_mini_sector.position_entry.timestamp
            ).total_seconds()
            if prev_mini_sector
            else 0
        )
        spline_error_m = self.pos_entry_history[-1].spline_pos - (
            (self.current_mini_sector_idx - 1)
            * (self.session.track.track_meters / self.session.num_mini_sectors)
            / self.session.track.track_meters
        )  # this is where the mini sector should have been triggered
        velocity_mps = self.pos_entry_history[-1].kph / 3.6  # m/s
        correction_weight = 0  # ish
        adj_time_s = (
            time_s
            - ((spline_error_m / velocity_mps) if velocity_mps != 0 else 0)
            * correction_weight
        )

        mini_sector = self._create_and_update_timing_segment(
            segment_type=MiniSector,
            timestamp=self.pos_entry_history[-1].timestamp,
            idx=self.current_mini_sector_idx - 1,
            running_segments=self.running_mini_sectors,
            best_segments=self.best_mini_sectors,
            history_list=self.stints[-1].mini_sector_history,
            time_s=adj_time_s,
            position_entry=self.pos_entry_history[-1],
        )
        if len(self.stints) > 0 and mini_sector.time_ms > 0:
            self.stints[-1].on_new_mini_sector(mini_sector)

    def on_new_lap(self):
        # handle stint new lap
        self.stints[-1].on_new_lap(
            Lap(
                lap_number=self.entry.lap,
                lap_info=self.entry.last_lap,
                pos_history=self.pos_entry_history,
                car_status=self.car_status,
                track_status=TrackStatus(
                    air_temp=self.session.air_temp,
                    track_temp=self.session.track_temp,
                    track_grip=self.session.track_grip_status,
                    weather=(
                        self.session.rain_now.rain_intensity
                        if self.session.rain_now
                        else None
                    ),
                ),
            )
        )

        self.sector_times_ms = [0, 0, 0]

        # clear position history
        # RaceAnalysis.plot_track(self)
        self.pos_entry_history = []

        pass

    def on_exiting_pit_lane(self, is_hero: bool = False):
        self.pit_laps.append(self.entry.lap)
        # we do stint stuff here instead of when detecting pit entry incase return to garage happens and to capture pit stop lap
        self.end_stint(dump_stint=is_hero)
        self.start_stint()
        pass

    ###################################
    ########      UPDATES      ########
    ###################################

    def update_track_location(self):
        # first entry
        if not self.old_entry:
            self.start_stint()
            return False

        # same location
        if self.old_entry.car_location.name == self.entry.car_location.name:
            return False

        def is_new_location(old_loc: CarLocation, new_loc: CarLocation) -> bool:
            return (
                self.old_entry.car_location.name == old_loc.name
                and self.entry.car_location.name == new_loc.name
            )

        # was on track, now in pit lane
        if is_new_location(CarLocation.PitEntry, CarLocation.Pitlane):
            self.event_handler.prepare_event_trigger(self.Events.ON_ENTERING_PIT_LANE)

        # was in pit lane, now in pit exit
        if is_new_location(CarLocation.Pitlane, CarLocation.PitExit) or is_new_location(
            CarLocation.Pitlane, CarLocation.Track
        ):
            self.event_handler.prepare_event_trigger(self.Events.ON_EXITING_PIT_LANE)

        return True

    def update_track_position(self, dt: float = 0.01):
        if self.pos_entry_history and (
            (self.now - self.pos_entry_history[-1].timestamp).total_seconds() < dt
            or self.event_handler.event_is_pending(self.Events.ON_NEW_MINI_SECTOR)
            or self.event_handler.event_is_pending(self.Events.ON_NEW_SECTOR)
        ):
            return

        self.pos_entry_history.append(
            PositionEntry(
                timestamp=self.now,
                lap_time_at_pos_ms=self.entry.current_lap.lap_time_ms,
                x=self.entry.world_pos_x,
                y=self.entry.world_pos_y,
                spline_pos=self.entry.spline_position,
                kph=self.entry.kph,
            )
        )

    def update_mini_sector_idx(self):
        mini_sector_idx: int = lambda spline_pos: int(
            spline_pos
            * self.session.track.track_meters
            / (self.session.track.track_meters / self.session.num_mini_sectors)
        )
        prev_mini_sector_idx = (
            mini_sector_idx(self.old_entry.spline_position) if self.old_entry else None
        )
        self.current_mini_sector_idx = min(
            self.session.num_mini_sectors - 1,
            mini_sector_idx(self.entry.spline_position),
        )  # apparently spline position is sometimes >= 1.0

        if (
            prev_mini_sector_idx is None
            or self.current_mini_sector_idx != prev_mini_sector_idx
        ):
            self.event_handler.prepare_event_trigger(self.Events.ON_NEW_MINI_SECTOR)
        pass

    def update_laps(self):
        # first entry
        if not self.old_entry:
            return

        # still on same lap
        if self.old_entry.lap == self.entry.lap or self.entry.last_lap.lap_time_ms == 0:
            return

        self.event_handler.prepare_event_trigger(self.Events.ON_NEW_LAP)

    def update_lap(self):
        if (
            self.old_entry
            and self.entry.current_lap.is_invalid
            and not self.old_entry.current_lap.is_invalid
        ):
            self.event_handler.prepare_event_trigger(self.Events.ON_LAP_INVALIDATED)

        pass

    def update(self):
        self.update_mini_sector_idx()
        self.update_track_location()
        self.update_track_position()
        self.update_lap()
        self.update_laps()
        # never put handle_events here, put it in child classes only
        pass


class Villan(Car):
    def __init__(
        self,
        entry: CarEntry,
        old_villan: Optional[Villan],
        session: Session,
        now: datetime,
    ):
        super().__init__(entry=entry, old_car=old_villan, session=session, now=now)

        self.event_handler.events.update(
            {
                self.Events.ON_NEW_MINI_SECTOR.name: (False, self.on_new_mini_sector),
                self.Events.ON_NEW_LAP.name: (False, self.on_new_lap),
                self.Events.ON_EXITING_PIT_LANE.name: (False, self.on_exiting_pit_lane),
            }
        )

    def gap_to_hero(self, hero: Hero, account_for_pit_stops: bool = False):
        return self.delta_to_car(hero, account_for_pit_stops)

    @staticmethod
    def from_entries(
        entries: dict[int, CarEntry],
        old_villans: dict[int, Villan],
        session: Session,
        now: datetime,
    ) -> dict[int, Villan]:
        villans: dict[int, Villan] = {}
        for entry in entries.values():
            old_villan: Optional[Villan] = (
                old_villans[entry.car_id]
                if old_villans and entry.car_id in old_villans
                else None
            )
            villans[entry.car_id] = Villan(
                entry=entry, old_villan=old_villan, session=session, now=now
            )
            villans[entry.car_id].update()
        return villans

    ##################################
    ########      EVENTS      ########
    ##################################

    def update(self):
        super().update()
        self.event_handler.handle_events()
        pass


class Hero(Car):
    def __init__(
        self,
        entry: CarEntry,
        old_hero: Hero,
        villans: dict[int, Villan],
        session: Session,
        sm: Optional[ACC_map],
        now: datetime,
        voice_control: VoiceControl,
    ):
        if old_hero:
            old_hero.old_hero = None
            old_hero.old_entry = None

        super().__init__(entry=entry, old_car=old_hero, session=session, now=now)
        self.voice_control = voice_control
        self.old_hero = old_hero
        self.sm = sm
        self.sm_exists = sm is not None

        # sectors
        # current sector starting at 1
        self.current_sector_idx: Optional[int] = (
            None if not old_hero else old_hero.current_sector_idx
        )
        self.running_sectors: list[Optional[Sector]] = (
            [None, None, None] if not old_hero else old_hero.running_sectors
        )
        self.best_sectors: list[Optional[Sector]] = (
            [None, None, None] if not old_hero else old_hero.best_sectors
        )
        self.sector_times_ms: list[int] = (
            [0, 0, 0] if not old_hero else old_hero.sector_times_ms
        )
        self.current_turn_number: int = (
            0 if not old_hero else old_hero.current_turn_number
        )
        self.current_turn_name: str = "" if not old_hero else old_hero.current_turn_name
        self.recent_min_kph: int = 0 if not old_hero else old_hero.recent_min_kph
        self.recent_max_kph: int = 0 if not old_hero else old_hero.recent_max_kph

        self.speak_current_turn: bool = (
            True if not old_hero else old_hero.speak_current_turn
        )
        self.speak_min: bool = True if not old_hero else old_hero.speak_min
        self.speak_max: bool = True if not old_hero else old_hero.speak_max

        self.villans: dict[int, Villan] = (
            villans  # {car_id: Villan} - currently villans is only populated during a race
        )

        self.current_threat_id: Optional[int] = (
            None if not old_hero else old_hero.current_threat_id
        )

        self.pit_snapshots: list[Hero] = [] if not old_hero else old_hero.pit_snapshots

        self.event_handler.events.update(
            # fmt: off
            {
                self.Events.ON_LAP_INVALIDATED.name: (False, self.on_lap_invalidated),
                self.Events.ON_NEW_MIN_SPEED.name: (False, self.on_new_min_speed),
                self.Events.ON_NEW_MAX_SPEED.name: (False, self.on_new_max_speed),
                # IMPORTANT new mini sector is before new sector
                self.Events.ON_NEW_MINI_SECTOR.name: (False, self.on_new_mini_sector),
                # IMPORTANT new sector is before new lap
                self.Events.ON_NEW_SECTOR.name: (False, self.on_new_sector),
                self.Events.ON_NEW_LAP.name: (False, self.on_new_lap),
                self.Events.ON_NEW_TURN.name: (False, self.on_new_turn),
                self.Events.ON_EXITING_PIT_LANE.name: (False, self.on_exiting_pit_lane),
                self.Events.ON_ENTERING_PIT_LANE.name: (False, self.on_entering_pit_lane),
            }
            # fmt: on
        )

        # shared memory
        # we keep the most recent known sm data just in case sm misses a step
        self.fuel_remaining: float = 0.0
        self.tyre_set: int = -1
        self.tyre_compound: str = ""
        self.distance_traveled: float = 0.0
        self.wheel_pressure: Wheels = Wheels(0, 0, 0, 0)
        self.tyre_temperature: Wheels = Wheels(0, 0, 0, 0)

        if self.old_hero:
            self.fuel_remaining = self.old_hero.fuel_remaining
            self.tyre_set = self.old_hero.tyre_set
            self.tyre_compound = self.old_hero.tyre_compound
            self.distance_traveled = self.old_hero.distance_traveled
            self.wheel_pressure = self.old_hero.wheel_pressure
            self.tyre_temperature = self.old_hero.tyre_temperature

        if self.sm_exists:
            self.fuel_remaining = sm.Physics.fuel
            self.tyre_set = sm.Graphics.current_tyre_set
            self.tyre_compound = sm.Graphics.tyre_compound
            self.distance_traveled = sm.Graphics.distance_traveled
            self.wheel_pressure = sm.Physics.wheel_pressure
            self.tyre_temperature = sm.Physics.tyre_core_temp

    @property
    def mandatory_pits_remaining(self) -> int:
        if not self.sm_exists:
            return 0
        return self.sm.Graphics.missing_mandatory_pits

    def get_laps_remaining(self) -> int:
        leader = self.get_villan_from_pos(1)
        if leader is None:
            return
        leader_pace_ms = leader.lap_time_from_recent_mini_sectors_ms(
            n_laps=3, top_n_mini_sectors=2
        )
        if leader_pace_ms is None:
            return
        pit_loss_remaining_ms = self.get_full_service_pit_loss_remaining_s() * 1000
        adjusted_time_remaining_ms = (
            self.session.time_remaining.total_seconds() * 1000
            + leader.entry.current_lap.lap_time_ms
            - pit_loss_remaining_ms
        )
        estimated_laps_remaining = int(adjusted_time_remaining_ms / leader_pace_ms) + 1
        return estimated_laps_remaining

    def get_net_position(self) -> tuple[int, int]:
        """returns the net global position and cup category position"""
        if not self.session.is_race or not self.sm_exists:
            return 0, 0

        sorted_villans = sorted(
            sorted(
                self.villans.values(),
                key=lambda v: v.entry.position,
            ),
            key=lambda v: v.gap_to_hero(
                self, account_for_pit_stops=True
            ).total_seconds(),
        )

        num_villans_ahead_in_same_cup = 0
        for net_pos, villan in enumerate(sorted_villans, start=1):
            if villan.is_same_cup(self):
                num_villans_ahead_in_same_cup += 1
            if villan.entry.car_id == self.entry.car_id:
                return (net_pos, num_villans_ahead_in_same_cup)

        pass
        return (0, 0)

    def get_villan_from_pos(self, pos: int) -> Optional[Villan]:
        for villan in self.villans.values():
            if villan.entry.position == pos:
                return villan
        return None

    def villans_in_pit_gap(
        self, min_pit_gap_s: int = 5
    ) -> Generator[Villan, None, None]:
        pit_DT = self.session.track_info.pit_DT
        if not pit_DT:
            return

        # for villan in self.villans.values():
        for villan in sorted(self.villans.values(), key=lambda v: v.entry.position):
            if villan == self:
                continue

            gap_to_hero_s = villan.gap_to_hero(self).total_seconds()
            # in pit gap
            tire_change_pit_loss_s = self.session.track_info.get_tire_change_pit_loss_s(
                pit_DT
            )
            if (
                gap_to_hero_s
                and gap_to_hero_s != timedelta(0).total_seconds()
                and tire_change_pit_loss_s
                < gap_to_hero_s
                < tire_change_pit_loss_s + min_pit_gap_s
            ):
                yield villan

    ##########################################
    ########      SPEAK ATTEMPTS      ########
    ##########################################

    def try_speak_car_wheel_pressure_window(self):
        if (
            self.old_hero is None
            or len(self.old_hero.stints[-1].car_status_history.history) < 2
        ):
            return

        for key in ["front_left", "front_right", "rear_left", "rear_right"]:
            if not hasattr(self.stints[-1].car_status_history.max_wheel_pressure, key):
                return

            if not hasattr(
                self.old_hero.stints[-1].car_status_history.max_wheel_pressure, key
            ):
                return

            current_pressure = getattr(self.car_status.wheel_pressure, key)
            current_max_pressure = getattr(
                self.stints[-1].car_status_history.max_wheel_pressure, key
            )
            old_pressure = getattr(
                self.old_hero.stints[-1].car_status_history.history[-2].wheel_pressure,
                key,
            )

            if (
                current_pressure >= 26.6 >= old_pressure
                and current_max_pressure == current_pressure
            ):
                self.voice_control.speak(f"{key.replace('_', ' ')} pressure in window")
                pass

    def _try_speak_segment_std_dev(
        self,
        segment_idx: int,
        segment_history: list[list[MiniSector | Sector]],
        running_segments: list[MiniSector | Sector | None],
    ):
        """Generic method to speak standard deviation for mini sectors or sectors."""
        if segment_idx is None:
            return

        if (
            len(segment_history[segment_idx]) < 2
            or running_segments[segment_idx] is None
        ):
            return

        # excludes first lap of stint
        segment_times_ms: list[int] = [
            seg.time_ms
            for seg in segment_history[segment_idx][1:]
            if not seg.is_invalid
        ]

        if len(segment_times_ms) < 2:
            return

        mean_ms = statistics.mean(segment_times_ms)
        stdev_ms = statistics.stdev(segment_times_ms)
        current_ms = running_segments[segment_idx].time_ms
        if stdev_ms == 0:
            return
        z_score = (current_ms - mean_ms) / stdev_ms
        rounded_z_score = round(z_score, 1)
        sign = "+" if rounded_z_score > 0 else "-"
        self.voice_control.speak(f"{sign}{abs(rounded_z_score)}")

    def try_speak_mini_sector_std_dev(self):
        self._try_speak_segment_std_dev(
            segment_idx=self.current_mini_sector_idx - 1,
            segment_history=self.stints[-1].mini_sector_history,
            running_segments=self.running_mini_sectors,
        )

    def try_speak_sector_std_dev(self):
        self._try_speak_segment_std_dev(
            segment_idx=self.current_sector_idx,
            segment_history=self.stints[-1].sector_history,
            running_segments=self.running_sectors,
        )

    def try_speak_new_best_mini_sector(self):
        if self.current_mini_sector_idx is None:
            return

        mini_sector = self.running_mini_sectors[self.current_mini_sector_idx - 1]
        best_mini_sector = self.best_mini_sectors[self.current_mini_sector_idx - 1]

        if (
            mini_sector
            and best_mini_sector
            and mini_sector.time_ms == best_mini_sector.time_ms
            and len(self.stints[-1].laps) >= 2
        ):
            self.voice_control.speak(
                f"purple mini sector {self.current_mini_sector_idx}"
            )

    def try_speak_mini_sector_numbers(self):
        if not self.is_out_lap:
            return

        prev_mini_sector_idx: float = lambda current_idx: int(
            self.session.num_mini_sectors - 1 if current_idx == 0 else current_idx
        )

        self.voice_control.speak(
            f"end mini sector {prev_mini_sector_idx(self.current_mini_sector_idx) + 1}"
        )

    def try_speak_new_position(self):
        if not self.old_hero:
            return

        def get_hero_pos_from_sorted_villans(sorted_villans: list[Villan]) -> int:
            for pos, villan in enumerate(sorted_villans, start=1):
                if villan.entry.car_id == self.entry.car_id:
                    return pos
            return 0

        old_sorted_villans = sorted(
            self.old_hero.villans.values(),
            key=lambda v: v.gap_to_hero(self.old_hero).total_seconds(),
        )
        sorted_villans = sorted(
            self.villans.values(), key=lambda v: v.gap_to_hero(self).total_seconds()
        )

        old_pos = get_hero_pos_from_sorted_villans(old_sorted_villans)
        new_pos = get_hero_pos_from_sorted_villans(sorted_villans)

        if new_pos and old_pos and new_pos != old_pos:
            self.voice_control.speak(f"Now P{new_pos}")

        else:
            return

        # don't try to speak lap deltas until at least lap 2
        if self.entry.lap < 2:
            return

        villan_predicted_lap_time_ms = None
        villan = None
        if 1 < new_pos < old_pos:
            villan = self.get_villan_from_pos(new_pos - 1)

        elif new_pos > old_pos:
            villan = self.get_villan_from_pos(new_pos + 1)

        if not villan:
            return

        villan_predicted_lap_time_ms = villan.lap_time_from_recent_mini_sectors_ms()
        if villan_predicted_lap_time_ms is None:
            return

        self_predicted_lap_time_ms = self.lap_time_from_recent_mini_sectors_ms()
        if self_predicted_lap_time_ms is None:
            return

        lap_time_diff = villan_predicted_lap_time_ms - self_predicted_lap_time_ms
        self.voice_control.speak(
            f"P{new_pos - 1} is {'slower' if lap_time_diff > 0 else 'faster'} by {abs(lap_time_diff) / 1000:.1f} seconds"
        )

        return True

    def try_speak_villan_gap_behind(self):
        # villans are only active during a race
        closest_threat_id: Optional[int] = None
        closest_threat_delta: Optional[timedelta] = None
        for v_idx, v in self.villans.items():
            # is hero
            if v == self:
                continue

            if v.entry.spline_position > self.entry.spline_position:
                continue

            delta = v.gap_to_hero(self)
            if delta.total_seconds() <= 0:
                continue

            if not closest_threat_delta or delta < closest_threat_delta:
                closest_threat_delta = delta
                closest_threat_id = v_idx

        spoken = False
        # no threats from behind
        if not closest_threat_id:
            return

        # different threat than before
        if self.current_threat_id != closest_threat_id:
            self.current_threat_id = closest_threat_id
            return

        # same threat as before
        else:
            villan = self.villans[self.current_threat_id]
            # we use villan's because they're behind hero
            mini_sector_idx: int = villan.current_mini_sector_idx - 1
            villan_mini_sector = villan.running_mini_sectors[mini_sector_idx - 1]
            self_mini_sector = self.running_mini_sectors[mini_sector_idx - 1]
            # at the start of the race mini sectors may be None
            if not villan_mini_sector or not self_mini_sector:
                return

            old_gap = (
                villan_mini_sector.timestamp - self_mini_sector.timestamp
            ).total_seconds()
            new_gap = closest_threat_delta.total_seconds()

            def speak_new_gap(gap: float):
                other_predicted_lap_time_ms = (
                    villan.lap_time_from_recent_mini_sectors_ms()
                )
                self_predicted_lap_time_ms = self.lap_time_from_recent_mini_sectors_ms()

                if not other_predicted_lap_time_ms or not self_predicted_lap_time_ms:
                    return

                lap_time_diff = other_predicted_lap_time_ms - self_predicted_lap_time_ms
                self.voice_control.speak(
                    f"{self.session.time_remaining.total_seconds() / 60:.1f} {villan.entry.driver_last_name} behind by {gap:.1f} seconds "
                    + f"they're {'slower' if lap_time_diff > 0 else 'faster'} by {abs(lap_time_diff) / 1000:.1f} seconds"
                )
                return True

            if new_gap < 3 < old_gap:
                spoken = speak_new_gap(new_gap)

            elif new_gap < 1 < old_gap:
                spoken = speak_new_gap(new_gap)

        return spoken

    def try_speak_tc(self, name: TCAlerts.Names, value: float):
        is_min_tc = name == TCAlerts.Names.MIN_VALUE.value
        is_max_tc = not is_min_tc
        if self.session.is_practice and self.is_out_lap:
            self.voice_control.speak(f"{'Min' if is_min_tc else 'Max'} TC {value} test")
            pass

        if self.sm_exists and (
            (is_min_tc and self.sm.Graphics.tc_level < value)
            or (is_max_tc and self.sm.Graphics.tc_level > value)
        ):
            self.voice_control.speak(f"TC")

    def try_speak_max_quali_pace(self):
        if self.session.is_practice and self.is_out_lap:
            self.voice_control.speak(f"Max quali pace test")
            pass

        if not self.voice_control.DO_SPEAK_QUALI_TIME_LEFT:
            return

        if not self.session.track_info.race_pace_s:
            return

        time_left = self.session.time_remaining.total_seconds()
        if time_left > self.session.track_info.race_pace_s:
            expected_quali_laps = int(time_left / self.session.track_info.race_pace_s)
            max_lap_time_s = time_left / expected_quali_laps
            self.voice_control.speak(
                f"{int(time_left // 60)} {int(time_left % 60):02d} left, "
                f"need sub {int(max_lap_time_s // 60)} {max_lap_time_s % 60:04.1f}"
            )
        pass

    def try_speak_villan_lap_deltas(self):
        if not self.voice_control.DO_SPEAK_VILLAN_LAP_DELTAS:
            return

        # find largest gain on any villan ahead
        largest_delta_ms: Optional[int] = None
        largest_delta_pos: Optional[int] = None

        sorted_villans = sorted(
            self.villans.values(), key=lambda v: v.entry.position, reverse=True
        )
        for villan in sorted_villans:
            if villan.entry.position >= self.entry.position:
                continue

            delta_time_ms = (
                villan.entry.last_lap.lap_time_ms - self.entry.last_lap.lap_time_ms
            )
            if largest_delta_ms is None or delta_time_ms > largest_delta_ms:
                largest_delta_ms = delta_time_ms
                largest_delta_pos = villan.entry.position

        if largest_delta_ms and largest_delta_ms >= 0:
            self.voice_control.speak(
                f"Caught P{largest_delta_pos} by {largest_delta_ms / 1000:.1f} seconds"
            )

        pass

    def try_speak_num_laps_remaining(self):
        if not self.voice_control.DO_SPEAK_LAPS_REMAINING:
            return

        if self.session.is_race and self.session.time_remaining > timedelta(0):
            estimated_laps_remaining = self.get_laps_remaining()
            # Only speak at 10 minutes remaining or at 75%, 50%, 25% marks
            if not estimated_laps_remaining:
                return

            total_laps = self.entry.lap + estimated_laps_remaining

            # Check if 10 minutes remaining
            sub_10_min_left = self.session.time_remaining < timedelta(minutes=10)

            # Check if at quarter marks (75%, 50%, 25%)
            at_quarter_mark = False
            for quarter in [0.75, 0.5, 0.25]:
                target_lap = int(total_laps * quarter)
                if estimated_laps_remaining == target_lap:
                    at_quarter_mark = True
                    break

            if sub_10_min_left or at_quarter_mark:
                self.voice_control.speak(f"{estimated_laps_remaining} to go")

        pass

    def try_speak_lap_times(self):
        if not self.voice_control.DO_SPEAK_LAP_TIMES:
            return

        self.voice_control.speak(f"""Lap Time {
                float(str(ms_to_m_ss_000(self.entry.last_lap.lap_time_ms, 1))
                    .replace(":", " ")[2:])
            }""")

        self.voice_control.speak(f"""Median {
                float(str(ms_to_m_ss_000(self.stints[-1].median_lap_ms, 1))
                    .replace(":", " ")[2:])
            }""")
        pass

    def try_speak_hot_stint_time(self):
        if not self.voice_control.DO_SPEAK_HOT_STINT_TIMES:
            return

        hot_stint_time_ms = self.stints[-1].hot_stint_time_ms
        if not hot_stint_time_ms:
            return

        self.voice_control.speak(f"""Hot Stint {
                float(str(ms_to_m_ss_000(self.stints[-1].hot_stint_time_ms, 1))
                    .replace(':', ' ')[2:])
            }""")
        pass

    def try_speak_turn_number(self):
        if not self.voice_control.DO_SPEAK_TURN_NUMBERS:
            return

        self.voice_control.speak(
            f"T {self.current_turn_number} {self.current_turn_name.replace(str(self.current_turn_number), '')}"
        )
        pass

    def try_speak_pit_gap_alert(self):
        if not self.voice_control.DO_SPEAK_PIT_GAP_ALERTS:
            return

        if self.mandatory_pits_remaining > 0:
            sorted_villans_in_pit_gap = sorted(
                list(self.villans_in_pit_gap()), key=lambda v: v.entry.position
            )
            if sorted_villans_in_pit_gap:
                villan_mini_sector_lap_time_ms = sorted_villans_in_pit_gap[
                    0
                ].lap_time_from_recent_mini_sectors_ms()
                if villan_mini_sector_lap_time_ms is None:
                    return

                self_mini_sector_lap_time_ms = (
                    self.lap_time_from_recent_mini_sectors_ms()
                )
                if self_mini_sector_lap_time_ms is None:
                    return

                lap_time_diff = (
                    villan_mini_sector_lap_time_ms - self_mini_sector_lap_time_ms
                )
                self.voice_control.speak(
                    # num in pit gap, list names
                    f"{len(sorted_villans_in_pit_gap)} in pit gap: "
                    + f"{', '.join(str(v.entry.driver_last_name) for v in sorted_villans_in_pit_gap[:3])} "
                    + f"they're {'slower' if lap_time_diff > 0 else 'faster'} by {abs(lap_time_diff) / 1000:.1f} seconds"
                )
                pass

            else:
                self.voice_control.speak(f"Pit gap clear")
                pass

    def try_speak_net_position_alert(self):
        if not self.voice_control.DO_SPEAK_NET_POSITION_ALERTS:
            return

        race_pos, cup_pos = self.get_net_position()
        self.voice_control.speak(f"net P{race_pos} in race, P{cup_pos} in cup")
        pass

    def try_speak_race_update_alert(self):
        if self.session.is_practice and self.is_out_lap:
            self.voice_control.speak(f"Race update alert test")
            pass

        if self.entry.lap > 1:
            self.try_speak_net_position_alert()
            self.try_speak_pit_gap_alert()

    ##################################
    ########      EVENTS      ########
    ##################################

    def on_exiting_pit_lane(self):
        super().on_exiting_pit_lane(is_hero=True)
        self.try_speak_max_quali_pace()

        pass

    def on_lap_invalidated(self):
        if self.voice_control.DO_SPEAK_INVALIDATIONS:
            self.voice_control.speak(f"Invalidated")

    def on_new_min_speed(self):
        if self.voice_control.DO_SPEAK_MIN_SPEEDS:
            self.voice_control.speak(f"{self.recent_min_kph}")
        pass

    def on_new_max_speed(self):
        if self.voice_control.DO_SPEAK_MAX_SPEEDS:
            self.voice_control.speak(f"{self.recent_max_kph}")
        pass

    def on_new_mini_sector(self):
        super().on_new_mini_sector()
        self.try_speak_car_wheel_pressure_window()

        if self.voice_control.DO_SPEAK_MINI_SECTORS:
            # self.try_speak_mini_sector_std_dev()
            self.try_speak_new_best_mini_sector()
            self.try_speak_mini_sector_numbers()

        # is race
        if False and self.session.is_race:
            if self.entry.lap > 1:
                self.try_speak_new_position()
                self.try_speak_villan_gap_behind()
            pass
        pass

    def on_new_sector(self):
        self._create_and_update_timing_segment(
            segment_type=Sector,
            idx=self.current_sector_idx,
            timestamp=self.pos_entry_history[-1].timestamp,
            running_segments=self.running_sectors,
            best_segments=self.best_sectors,
            history_list=self.stints[-1].sector_history,
            time_s=self.sector_times_ms[self.current_sector_idx] / 1000,
            position_entry=self.pos_entry_history[-1],
        )

        if self.voice_control.DO_SPEAK_SECTOR_TIMES:
            self.try_speak_sector_std_dev()

            def speak_sector_time(sector_time_ms: int):
                self.voice_control.speak(f"{sector_time_ms / 1000:.1f}")

            match self.current_sector_idx:
                case 0:  # finished sector 1
                    speak_sector_time(self.sector_times_ms[0])
                case 1:  # finished sector 2
                    speak_sector_time(self.sector_times_ms[1])
                case 2:  # finished sector 3
                    speak_sector_time(
                        self.sm.Graphics.last_time - sum(self.sector_times_ms[:2])
                    )
            pass

        self.current_sector_idx = self.sm.Graphics.current_sector_index
        pass

    def on_new_lap(self):
        super().on_new_lap()
        self.try_speak_villan_lap_deltas()
        self.try_speak_num_laps_remaining()
        self.try_speak_lap_times()
        self.try_speak_hot_stint_time()
        pass

    def on_new_turn(self):
        self.try_speak_turn_number()
        pass

    def on_entering_pit_lane(self):
        self.pit_snapshots.append(self)
        pass

    ###################################
    ########      UPDATES      ########
    ###################################

    def check_alerts(self):
        if not self.voice_control.DO_SPEAK_ALERTS:
            return

        if self.old_entry and self.session.track_info:
            track_info_alerts = self.session.track_info.alerts

            # fmt: off
            alerts: list[tuple[Optional[Alerts], callable, tuple]] = []
            # list of (alert, method to call, args for method)

            ##### add tc alerts
            if track_info_alerts.tc:
                for tc_alert in track_info_alerts.tc.alerts:
                    alerts.append((tc_alert, self.try_speak_tc, (tc_alert.name, tc_alert.value,)))

            ##### add other track info alerts here
            alerts.extend([
                (track_info_alerts.race_update, self.try_speak_race_update_alert, ()),
                (track_info_alerts.max_quali_pace, self.try_speak_max_quali_pace, ()),
            ])
            # fmt: on

            for alert, speak_method, args in alerts:
                if alert and alert.did_pass_spline(
                    self.old_entry.spline_position, self.entry.spline_position
                ):
                    speak_method(*args)

        pass

    def update_track_position(self):
        super().update_track_position()

        if self.old_hero:
            if (
                self.sm_exists
                and self.old_hero.sm_exists
                and self.sm.Graphics.current_sector_index
                != self.old_hero.sm.Graphics.current_sector_index
            ):
                # we use sm's current sector idx here because we only set self's current sector idx when we know it's not None
                if self.sm.Graphics.current_sector_index > 0:
                    self.sector_times_ms[self.sm.Graphics.current_sector_index - 1] = (
                        # last sector time is a running lap time
                        self.sm.Graphics.last_sector_time
                        - sum(
                            self.sector_times_ms[
                                : self.sm.Graphics.current_sector_index - 1
                            ]
                        )
                    )
                else:
                    # when sector 3 is finished last sector time is 0 so we use last lap time
                    self.sector_times_ms[2] = self.sm.Graphics.last_time - sum(
                        self.sector_times_ms[:2]
                    )
                self.event_handler.prepare_event_trigger(self.Events.ON_NEW_SECTOR)
                self.current_sector_idx = self.sm.Graphics.current_sector_index - 1
                self.current_sector_idx %= 3
                pass

        return True

    def update_current_turn(self):
        if not self.session.track_info or not self.session.track_info.turns:
            return

        next_turn_idx = (
            self.current_turn_number
            if self.current_turn_number != len(self.session.track_info.turns)
            else 0
        )
        car_pos = (self.entry.world_pos_x, self.entry.world_pos_y)
        distance = lambda pos1, pos2: math.sqrt(
            math.pow(pos1[0] - pos2[0], 2) + math.pow(pos1[1] - pos2[1], 2)
        )
        turn_position = lambda t_idx: (
            self.session.track_info.turns.iloc[t_idx]["x"],
            self.session.track_info.turns.iloc[t_idx]["y"],
        )

        distance_to_current_turn = distance(
            turn_position(self.current_turn_number - 1), car_pos
        )
        distance_to_next_turn = distance(turn_position(next_turn_idx), car_pos)

        if (
            distance_to_current_turn > distance_to_next_turn
            and distance_to_next_turn < 150
        ):
            self.current_turn_number = next_turn_idx + 1
            self.current_turn_name = self.session.track_info.turns.iloc[next_turn_idx][
                "name"
            ]
            self.event_handler.prepare_event_trigger(self.Events.ON_NEW_TURN)

        pass

    def update_recent_speeds(self):
        if self.entry.kph > self.recent_max_kph:
            if self.speak_min:
                self.event_handler.prepare_event_trigger(self.Events.ON_NEW_MIN_SPEED)
                self.speak_min = False
                self.speak_max = True
            self.recent_max_kph = self.entry.kph
            self.recent_min_kph = self.entry.kph

        # + 5 to pad slight lifts
        elif self.entry.kph + 5 < self.recent_min_kph:
            if self.speak_max:
                self.event_handler.prepare_event_trigger(self.Events.ON_NEW_MAX_SPEED)
                self.speak_max = False
                self.speak_min = True
            self.recent_min_kph = self.entry.kph
            self.recent_max_kph = self.entry.kph
        pass

    def update(self):
        super().update()
        self.check_alerts()
        self.update_track_position()
        self.update_current_turn()
        self.update_recent_speeds()
        self.event_handler.handle_events()
        pass
