from datetime import datetime

from pyaccsharedmemory import ACC_RAIN_INTENSITY


class WeatherEvent:
    def __init__(self, rain_intensity: ACC_RAIN_INTENSITY, eta: datetime):
        self.rain_intensity = rain_intensity
        self.eta = eta
