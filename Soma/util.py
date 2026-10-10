from typing import Optional

from PyAccWrapper import PositionEntry


def ms_to_m_ss_000(ms: Optional[float], digits: int = 3):
    if ms is None:
        return None

    seconds = ms / 1000.0
    minutes = int(seconds // 60)
    seconds = round(seconds - (minutes * 60), digits)
    return f"{minutes}:{seconds:0{2 + digits + 1}.{digits}f}"
