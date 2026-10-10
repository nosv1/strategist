# ACC Strategist

Personal race-strategy tool for Assetto Corsa Competizione. Not maintained for general use, published here mainly for remote access.

Soma (`Soma/main.py`) reads live data from ACC's UDP broadcast interface and shared memory, tracks cars, laps and stints, and gives voice alerts during a session.

## Layout

- `Soma/`: main app
- `Tracks/`: per-track config (see `Tracks/0_example.json`)
- `FuelVsTires.py`, `endurance_simulator.py`: standalone strategy calculators
- `GUI.py`: early GUI experiment

## Running

Depends on two sibling repos placed in the project root: [PyAccUdpInterface](https://github.com/nosv1/PyAccUdpInterface) (fork) and [accapi](https://github.com/EmperorCookie/accapi).

```
python Soma/main.py --no-load-entries --no-race-analysis --hero-name="Your Name"
```

ACC's broadcasting must be enabled (`broadcasting.json`, port 9000). Hardcoded paths in `soma.bat` and `Soma/main.py` assume my machine.
