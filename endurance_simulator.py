from datetime import timedelta


class Car:
    def __init__(
        self,
        refuel_rate=0.2,
        fuel_capacity=120,
    ):
        self.refuel_rate = refuel_rate
        self.fuel_capacity = fuel_capacity

    def perform_pit(
        self, refuel_amount: int, tyre_change: bool, race_details: "RaceDetails"
    ) -> timedelta:
        tyre_time_lost = timedelta()
        fuel_time_lost = timedelta()
        total_time_lost = timedelta()
        if refuel_amount > 0:
            fuel_time_lost = timedelta(seconds=refuel_amount * self.refuel_rate)

        if tyre_change:
            tyre_time_lost += timedelta(seconds=30)

        total_time_lost = (
            max(fuel_time_lost, tyre_time_lost) + race_details.pit_lane_loss
        )
        return total_time_lost


class RaceDetails:
    def __init__(
        self,
        race_time=timedelta(hours=6),
        stint_timer=timedelta(hours=1, minutes=5),
        race_pace=timedelta(minutes=1, seconds=30),
        tyre_sets=5,
        pit_lane_loss=timedelta(seconds=24),
    ):
        self.race_time = race_time
        self.stint_timer = stint_timer
        self.race_pace = race_pace
        self.tyre_sets = tyre_sets
        self.pit_lane_loss = pit_lane_loss

    @staticmethod
    def race_pace_from_quali_pace(
        quali_pace: timedelta, race_pace_factor=1.013
    ) -> timedelta:
        return quali_pace * race_pace_factor


class Simulation:
    def __init__(self, race_details: RaceDetails):
        self.race_details = race_details
        self.elapsed_time = timedelta()
        pass

    def run(self):
        while self.elapsed_time < self.race_details.race_time:
            self.elapsed_time += timedelta(seconds=1)


if __name__ == "__main__":
    pass
