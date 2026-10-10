from __future__ import annotations

from enum import Enum
from typing import Optional

from pyaccsharedmemory import Wheels


class CarStatusHistory:
    def __init__(self):
        self.history: list[CarStatus] = []

        self.max_wheel_pressure: Optional[Wheels] = Wheels(
            float("-inf"), float("-inf"), float("-inf"), float("-inf")
        )
        self.max_tyre_temperature: Optional[Wheels] = Wheels(
            float("-inf"), float("-inf"), float("-inf"), float("-inf")
        )

    def update_max_values(self, car_status: CarStatus):
        for key in ["front_left", "front_right", "rear_left", "rear_right"]:
            pressure_value = getattr(car_status.wheel_pressure, key)
            max_pressure_value = getattr(self.max_wheel_pressure, key)
            if pressure_value is not None and pressure_value > max_pressure_value:
                setattr(self.max_wheel_pressure, key, pressure_value)

            temp_value = getattr(car_status.tyre_temperature, key)
            max_temp_value = getattr(self.max_tyre_temperature, key)
            if temp_value is not None and temp_value > max_temp_value:
                setattr(self.max_tyre_temperature, key, temp_value)

        pass

    def update(self, car_status: CarStatus):
        self.history.append(car_status)

        # these only exist for hero
        if car_status.wheel_pressure and car_status.tyre_temperature:
            self.update_max_values(car_status)


class CarStatus:
    class TyreCompound(Enum):
        DRY = "dry"
        WET = "wet"

    def __init__(
        self,
        fuel: Optional[float] = None,
        tyre_set: Optional[int] = None,
        tyre_compound: Optional[str] = None,
        distance_traveled_m: Optional[float] = None,
        wheel_pressure: Optional[Wheels] = None,
        tyre_temperature: Optional[Wheels] = None,
    ):
        # we have to use optionals because villans won't have this data
        self.fuel = fuel  # physics map fuel -- fuel remaining in liters
        self.tyre_set = tyre_set
        self.tyre_compound = (
            self.tyre_compound_correction(tyre_compound) if tyre_compound else None
        )
        self.distance_traveled_m = distance_traveled_m
        self.wheel_pressure = wheel_pressure
        self.tyre_temperature = tyre_temperature

    @staticmethod
    def tyre_compound_correction(tyre_compound: str) -> Optional[TyreCompound]:
        # 'wet_compound\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        clean = tyre_compound.strip("\x00").lower()
        if "wet" in clean:
            return CarStatus.TyreCompound.WET
        elif "dry" in clean:
            return CarStatus.TyreCompound.DRY
        return None

    def distance_as_laps(self, track_length_m: float) -> Optional[float]:
        if self.distance_traveled_m is None:
            return None
        return self.distance_traveled_m / track_length_m
