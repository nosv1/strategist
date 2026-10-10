from datetime import datetime, timedelta
from typing import Optional

from Car import Hero, Villan
from Session import Session
from Track import TrackInfo


class Context:
    def __init__(self):
        self.session: Optional[Session] = None
        self.track_info: Optional[TrackInfo] = None
        self.hero: Optional[Hero] = None
        self.villans: dict[int, Villan] = {}
        self.start = datetime.now()

        self.session_history: list[Session] = []
        self.hero_history: list[Hero] = []
        self.villan_history: list[list[Villan]] = []

    def reset_cars(self):
        if self.hero:
            self.hero.end_stint(dump_stint=True)
        self.hero = None
        self.villans = {}
