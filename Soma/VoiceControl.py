import time
from threading import Lock, Thread
from typing import Optional

import pyttsx3  # Text-to-Speech for voice alerts

# Configure TTS
# Use per-thread engine instances to avoid "run loop already started" errors
# (pyttsx3 is not thread-safe when sharing a single engine across threads)
# Keep default rate value
_DEFAULT_TTS_RATE = 200

TTS_QUEUE = []
TTS_THREAD: Optional[Thread] = None
TTS_LOCK = Lock()
TTS_IDLE_TIMEOUT = 0.5  # Wait 500ms for new items before shutting down thread


class VoiceControl:
    def __init__(
        self,
        position_dump: bool = False,
        speak_turn_numbers: bool = False,
        speak_invalidations: bool = False,
        speak_lap_times: bool = False,
        speak_hot_stint_times: bool = False,
        speak_villan_lap_deltas: bool = False,
        speak_sector_times: bool = False,
        speak_mini_sectors: bool = False,
        speak_min_speeds: bool = False,
        speak_max_speeds: bool = False,
        speak_weather_changes: bool = False,
        speak_alerts: bool = False,
        speak_quali_time_left: bool = False,
        speak_position_changes: bool = False,
        speak_pit_gap_alerts: bool = False,
        speak_net_position_alerts: bool = False,
        speak_laps_remaining: bool = False,
    ):
        self.DO_POSITION_DUMP = position_dump
        self.DO_SPEAK_TURN_NUMBERS = speak_turn_numbers
        self.DO_SPEAK_INVALIDATIONS = speak_invalidations
        self.DO_SPEAK_LAP_TIMES = speak_lap_times
        self.DO_SPEAK_HOT_STINT_TIMES = speak_hot_stint_times
        self.DO_SPEAK_VILLAN_LAP_DELTAS = speak_villan_lap_deltas
        self.DO_SPEAK_SECTOR_TIMES = speak_sector_times
        self.DO_SPEAK_MINI_SECTORS = speak_mini_sectors
        self.DO_SPEAK_MIN_SPEEDS = speak_min_speeds
        self.DO_SPEAK_MAX_SPEEDS = speak_max_speeds
        self.DO_SPEAK_WEATHER_CHANGES = speak_weather_changes
        self.DO_SPEAK_ALERTS = speak_alerts
        self.DO_SPEAK_QUALI_TIME_LEFT = speak_quali_time_left
        self.DO_SPEAK_POSITION_CHANGES = speak_position_changes
        self.DO_SPEAK_PIT_GAP_ALERTS = speak_pit_gap_alerts
        self.DO_SPEAK_NET_POSITION_ALERTS = speak_net_position_alerts
        self.DO_SPEAK_LAPS_REMAINING = speak_laps_remaining

    @staticmethod
    def speak_thread():
        """Actual speech function that runs in a single background thread"""
        global TTS_THREAD

        try:
            idle_start = None
            while True:
                text = None
                with TTS_LOCK:
                    if TTS_QUEUE:
                        text = TTS_QUEUE.pop(0)

                if text:
                    print(f"[TTS] Speaking: {text}")
                    # Reinitialize engine for each utterance to avoid pyttsx3 bug
                    engine = None
                    try:
                        engine = pyttsx3.init()
                        engine.setProperty("rate", _DEFAULT_TTS_RATE)
                        engine.say(text)
                        engine.runAndWait()
                    except Exception as e:
                        print(f"[TTS] ERROR during speech: {e}")
                    finally:
                        if engine:
                            try:
                                del engine
                            except Exception:
                                pass
                    # Reset idle timer after speaking since we did work
                    idle_start = None
                else:
                    # Queue is empty, start/continue idle timer
                    if idle_start is None:
                        idle_start = time.time()
                    elif time.time() - idle_start > TTS_IDLE_TIMEOUT:
                        # Been idle too long, shut down thread
                        break
                    # Sleep briefly to avoid busy-waiting
                    time.sleep(0.1)

        finally:
            TTS_THREAD = None

    @staticmethod
    def speak(text: str):
        """Convert text to speech in a separate thread"""
        text = text.replace("69", "69... nice.")
        with TTS_LOCK:
            print(f"[TTS] Queueing text for speech: {text}")
            TTS_QUEUE.append(text)

        global TTS_THREAD
        # Only start a new background thread if there's not one already running
        if TTS_THREAD is None or not TTS_THREAD.is_alive():
            TTS_THREAD = Thread(target=VoiceControl.speak_thread, daemon=True)
            TTS_THREAD.start()
