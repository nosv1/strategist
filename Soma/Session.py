from __future__ import annotations

import math
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from EventHandler import EventHandler
from matplotlib.style import context
from pyaccsharedmemory import ACC_RAIN_INTENSITY, ACC_TRACK_GRIP_STATUS, ACC_map
from Track import TrackInfo
from VoiceControl import VoiceControl
from WeatherEvent import WeatherEvent

from PyAccUdpInterface.Enums import SessionType
from PyAccUdpInterface.TrackData import TrackData


class Session:
    class Events(Enum):
        ON_TRACK_GRIP_CHANGED = 0
        ON_RAIN_NOW_CHANGED = 5
        ON_RAIN_IN_10_CHANGED = 1
        ON_RAIN_IN_30_CHANGED = 2
        ON_TRACK_TEMP_CHANGED = 3
        ON_NEW_SESSION = 4

    __time_offset = datetime(1969, 12, 31, 18, 0, 0)  # start of session

    def __init__(
        self,
        session_dict: dict,
        old_session: Optional[Session],
        sm: ACC_map,
        now: datetime,
        track_info: TrackInfo,
        voice_control: VoiceControl,
        weather_warning: timedelta = timedelta(minutes=3),
        mandatory_pits: int = 0,
    ) -> Session:
        # udp
        self.track: TrackData = session_dict["track"]
        self.session_type: str = session_dict["session_type"]
        # _session_time and _session_end_time are arbitrarary datetimes that are
        # based on the __time_offset datetime, use the relevant properties for
        # times based on now
        self._session_time: datetime = session_dict["session_time"]
        self._session_end_time: datetime = session_dict["session_end_time"]
        self.air_temp: int = session_dict["air_temp"]
        self.track_temp: int = session_dict["track_temp"]

        self.old_session: Session = old_session
        self.now: datetime = now
        self.track_info: TrackInfo = track_info
        self.voice_control: VoiceControl = voice_control
        self.weather_warning: timedelta = weather_warning
        self.mandatory_pits: int = mandatory_pits

        self.event_handler = EventHandler(
            events={
                self.Events.ON_TRACK_TEMP_CHANGED.name: (
                    False,
                    self.on_track_temp_changed,
                ),
                self.Events.ON_TRACK_GRIP_CHANGED.name: (
                    False,
                    self.on_track_grip_changed,
                ),
                self.Events.ON_RAIN_NOW_CHANGED.name: (
                    False,
                    self.on_rain_now_changed,
                ),
                self.Events.ON_RAIN_IN_10_CHANGED.name: (
                    False,
                    self.on_rain_in_10_changed,
                ),
                self.Events.ON_RAIN_IN_30_CHANGED.name: (
                    False,
                    self.on_rain_in_30_changed,
                ),
                self.Events.ON_NEW_SESSION.name: (False, self.on_new_session),
            }
        )

        is_new_session = (
            not self.old_session
            or self.old_session.time_remaining < self.time_remaining
        )  # incomplete condition
        if self.old_session:
            self.old_session.old_session = None

        if is_new_session:
            self.old_session = None
            self.event_handler.prepare_event_trigger(self.Events.ON_NEW_SESSION)

        self.forecast: dict[datetime, ACC_RAIN_INTENSITY] = (
            {}
            if not self.old_session or not self.old_session.sm_exists
            else self.old_session.forecast
        )

        # shared memory
        # we keep the most recent known weather, just in case shared memory misses a step it doesn't reset
        self.track_grip_status: Optional[ACC_TRACK_GRIP_STATUS] = None
        self.rain_now: Optional[WeatherEvent] = None
        self.rain_in_10: Optional[WeatherEvent] = None
        self.rain_in_30: Optional[WeatherEvent] = None

        if self.old_session:
            self.rain_now = self.old_session.rain_now
            self.rain_in_10 = self.old_session.rain_in_10
            self.rain_in_30 = self.old_session.rain_in_30

        self.sm_exists = sm is not None
        if self.sm_exists:
            self.track_grip_status = sm.Graphics.track_grip_status
            self.rain_now = WeatherEvent(
                rain_intensity=sm.Graphics.rain_intensity, eta=self.now
            )
            self.rain_in_10 = WeatherEvent(
                rain_intensity=sm.Graphics.rain_intensity_in_10min,
                eta=self.now + timedelta(minutes=10),
            )
            self.rain_in_30 = WeatherEvent(
                rain_intensity=sm.Graphics.rain_intensity_in_30min,
                eta=self.now + timedelta(minutes=30),
            )

            if self.forecast == {}:
                self.forecast[self.rain_now.eta] = self.rain_now

        self.update()

    @property
    def time_remaining(self) -> timedelta:
        return self._session_end_time - self.__time_offset

    @property
    def session_end_time(self):
        return self.now + self.time_remaining

    @property
    def time_in_session(self) -> timedelta:
        return self._session_time - self.__time_offset

    @property
    def session_duration(self) -> timedelta:
        return self.time_remaining + self.time_in_session

    @property
    def num_mini_sectors(self) -> int:
        # roughly one every 10 seconds
        # Valencia example 4005m per 90 seconds = 44.5 m/s * 10 = 445m per 10s
        return self.track.track_meters // 445

    @property
    def sorted_forecast_keys(self) -> list[datetime]:
        if self.sm_exists:
            return sorted(self.forecast.keys(), reverse=False)
        else:
            return []

    @property
    def is_practice(self) -> bool:
        return self.session_type == SessionType.Practice.name

    @property
    def is_qualifying(self) -> bool:
        return self.session_type == SessionType.Qualifying.name

    @property
    def is_race(self) -> bool:
        return self.session_type == SessionType.Race.name

    def speak_forecast(self, two_step_forecast: list[tuple[datetime, timedelta]]):
        # two_step_forecast = [(eta, duration), ...]
        # eta's are the keys to self.forecast

        def minutes(td: timedelta):
            return round(td.seconds / 60)

        # it's about to start raining and it will stay like this for minutes until it changes to for minutes
        first_eta = two_step_forecast[0][0]
        first_duration = minutes(two_step_forecast[0][1])
        first_intensity = self.forecast[first_eta]
        if len(two_step_forecast) == 2:
            second_eta = two_step_forecast[1][0]
            second_intensity = self.forecast[second_eta]
        self.voice_control.speak(
            f"""A {first_intensity} is about to start.
            It will stay like this for {first_duration} minutes."""
            + ""
            if len(two_step_forecast) == 1
            else f"Then there will be a {second_intensity}."
        )
        pass

    def get_next_weather_event(
        self, weather_event: Optional[WeatherEvent]
    ) -> Optional[WeatherEvent]:
        if not weather_event:
            return weather_event[self.sorted_forecast_keys[0]]

        sorted_forecast_keys = self.sorted_forecast_keys
        for i, fk in enumerate(sorted_forecast_keys):
            if not (i < len(sorted_forecast_keys) - 1):
                break

            # found current weather event
            if fk == weather_event.eta:
                return self.forecast[sorted_forecast_keys[i + 1]]

        return None

    ##################################
    ########      EVENTS      ########
    ##################################

    def on_track_temp_changed(self):
        if self.voice_control.DO_SPEAK_WEATHER_CHANGES:
            if self.old_session:
                temp_direction = (
                    "cooled"
                    if self.track_temp < self.old_session.track_temp
                    else "warmed"
                )
                self.voice_control.speak(
                    f"Track {temp_direction} to {self.track_temp} C"
                )
            else:
                self.voice_control.speak(f"Track is {self.track_temp} C")

    def on_track_grip_changed(self):
        if self.voice_control.DO_SPEAK_WEATHER_CHANGES:
            self.voice_control.speak(f"Track is {self.track_grip_status}")

    def speak_new_rain(self, weather_event: WeatherEvent):
        minutes = math.ceil((weather_event.eta - self.now).total_seconds() / 60)
        if minutes > 0:
            session_time = math.ceil(
                (self.time_remaining - timedelta(minutes=minutes)).total_seconds() / 60
            )
            self.voice_control.speak(
                f"{weather_event.rain_intensity} in {minutes} minutes at {session_time} minutes to go"
            )

        else:
            next_weather_event = self.get_next_weather_event(
                weather_event=weather_event
            )
            duration_s = (
                (next_weather_event.eta - weather_event.eta).total_seconds()
                if next_weather_event
                else self.time_remaining.total_seconds()
            )
            duration_m = math.ceil(duration_s / 60)
            self.voice_control.speak(
                f"{weather_event.rain_intensity} for {duration_m} minutes"
            )

    def on_rain_now_changed(self):
        if self.voice_control.DO_SPEAK_WEATHER_CHANGES:
            self.speak_new_rain(weather_event=self.rain_now)
        del self.forecast[self.rain_now.eta]

    def on_rain_in_10_changed(self):
        if self.voice_control.DO_SPEAK_WEATHER_CHANGES:
            self.speak_new_rain(weather_event=self.rain_in_10)

    def on_rain_in_30_changed(self):
        if self.voice_control.DO_SPEAK_WEATHER_CHANGES:
            self.speak_new_rain(weather_event=self.rain_in_30)

    def on_new_session(self):
        # speak(str(self.time_remaining))
        pass

    ###################################
    ########      UPDATES      ########
    ###################################

    def detect_temp_change(self):
        if not self.old_session or (
            self.sm_exists and self.old_session.track_temp != self.track_temp
        ):
            self.event_handler.prepare_event_trigger(self.Events.ON_TRACK_TEMP_CHANGED)
        pass

    def detect_grip_change(self):
        if not self.old_session or (
            self.old_session.sm_exists
            and self.sm_exists
            and self.old_session.track_grip_status != self.track_grip_status
        ):
            self.event_handler.prepare_event_trigger(self.Events.ON_TRACK_GRIP_CHANGED)

    def detect_weather_changes(self):
        # no old session data, only current sm data
        if (
            self.sm_exists
            and self.old_session
            and (not self.old_session.rain_in_10 or not self.old_session.rain_in_30)
        ):
            self.forecast[self.rain_in_10.eta] = self.rain_in_10
            self.forecast[self.rain_in_30.eta] = self.rain_in_30
            if self.rain_in_10.eta < self.session_end_time:
                self.event_handler.prepare_event_trigger(
                    self.Events.ON_RAIN_IN_10_CHANGED
                )

            if self.rain_in_30.eta < self.session_end_time:
                self.event_handler.prepare_event_trigger(
                    self.Events.ON_RAIN_IN_30_CHANGED
                )

        # new rain now
        if (
            self.old_session
            and self.old_session.sm_exists
            and self.sm_exists
            and self.old_session.rain_now.rain_intensity != self.rain_now.rain_intensity
        ) or (not self.old_session and self.rain_now):
            self.forecast[self.rain_now.eta] = self.rain_now
            self.event_handler.prepare_event_trigger(self.Events.ON_RAIN_NOW_CHANGED)

        # new rain in 10 within session time
        if (
            self.old_session
            and self.old_session.sm_exists
            and self.sm_exists
            and self.old_session.rain_in_10.rain_intensity
            != self.rain_in_10.rain_intensity
            and self.rain_in_10.eta < self.session_end_time
        ):
            self.forecast[self.rain_in_10.eta] = self.rain_in_10
            self.event_handler.prepare_event_trigger(self.Events.ON_RAIN_IN_10_CHANGED)

        # new rain in 30 within session time
        if (
            self.old_session
            and self.old_session.sm_exists
            and self.sm_exists
            and self.old_session.rain_in_30.rain_intensity
            != self.rain_in_30.rain_intensity
            and self.rain_in_30.eta < self.session_end_time
        ):
            self.forecast[self.rain_in_30.eta] = self.rain_in_30
            self.event_handler.prepare_event_trigger(self.Events.ON_RAIN_IN_30_CHANGED)

        pass

    def try_speak_forecast(self):
        sorted_forecast_keys = self.sorted_forecast_keys
        intensity_duration = lambda intensity_idx: (
            (sorted_forecast_keys[intensity_idx + 1] - eta)  # til next change
            if intensity_idx + 1 < len(sorted_forecast_keys)
            else min(timedelta(minutes=30), self.time_remaining)  # til end of session
        )
        for i, eta in enumerate(sorted_forecast_keys):
            delta = (eta - self.now).total_seconds()
            if delta <= 0:
                del self.forecast[eta]
                continue

            if delta > self.weather_warning.total_seconds():
                break

            two_step_forecast = [(eta, intensity_duration(i))]
            if i + 1 < len(sorted_forecast_keys):
                two_step_forecast + [(sorted_forecast_keys[i + 1], None)]
            self.speak_forecast(two_step_forecast=two_step_forecast)
            del self.forecast[eta]
            break
        pass

    def update(self):
        self.detect_temp_change()
        self.detect_grip_change()
        self.detect_weather_changes()
        # self.try_speak_forecast()
        self.event_handler.handle_events()
