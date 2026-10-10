from __future__ import annotations

from enum import Enum
from typing import Optional


class Alerts:
    """Base class for managing race alerts."""

    class Names(Enum):
        RACE_UPDATE = "race_update"
        MAX_QUALI_PACE = "max_quali_pace"
        TC = "tc"

    def __init__(self, alert: Optional[dict] = None):
        self.spline = alert.get("spline") if alert else None

        # Specific alert attributes
        self.race_update: Optional[RaceUpdateAlert] = None
        self.max_quali_pace: Optional[MaxQualiPaceAlert] = None
        self.tc: Optional[TCAlerts] = None

    def update_from_data(self, data: list[dict]) -> None:
        """Update alerts from a list of alert dictionaries."""
        for alert in data:
            alert_name = alert.get("name")
            if alert_name == self.Names.RACE_UPDATE.value:
                self.race_update = RaceUpdateAlert(alert)

            elif alert_name == self.Names.TC.value:
                self.tc = TCAlerts(alert)

            elif alert_name == self.Names.MAX_QUALI_PACE.value:
                self.max_quali_pace = MaxQualiPaceAlert(alert)

    def did_pass_spline(self, old_spline: float, current_spline: float) -> bool:
        """Check if spline position satisfies alert conditions."""
        if self.spline is None:
            return False
        if old_spline is None:
            return current_spline <= self.spline
        return old_spline < self.spline <= current_spline


class RaceUpdateAlert(Alerts):
    """Alert for race updates."""

    def __init__(self, alert: dict):
        super().__init__(alert)


class MaxQualiPaceAlert(Alerts):
    """Alert for maximum qualifying pace."""

    def __init__(self, alert: dict):
        super().__init__(alert)


class TCAlerts(Alerts):
    """Alert for traction control monitoring."""

    class Names(Enum):
        MIN_VALUE = "min_value"
        MAX_VALUE = "max_value"

    # {
    #     "name": "tc",
    #     "alerts": [
    #         {
    #             "name": "min_value",
    #             "spline": 0.089,
    #             "value": 6
    #         },
    #         {
    #             "name": "max_vaule",
    #             "spline": 0.7,
    #             "value": 4
    #         }
    #     ]
    # }

    def __init__(self, alert: dict):
        self.alerts: Alerts = alert.get("alerts")
        for i, alert in enumerate(self.alerts):
            self.alerts[i] = Alerts(alert)
            self.alerts[i].name = alert.get("name")
            self.alerts[i].spline = alert.get("spline")
            self.alerts[i].value = alert.get("value")

        pass
