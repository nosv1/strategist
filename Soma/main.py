from __future__ import annotations

import os
import signal
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import argparse
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
from Car import Hero, Villan
from Context import Context
from Logger import Logger
from pyaccsharedmemory import ACC_map, accSharedMemory
from PyAccWrapper import CarEntry
from Session import Session
from Track import TrackInfo
from VoiceControl import VoiceControl

import Soma.Analysis as Analysis
from PyAccUdpInterface.PyAccUdpInterface import accUpdInterface


def set_practice_profile(voice_control: VoiceControl):
    voice_control = VoiceControl()
    voice_control.DO_SPEAK_INVALIDATIONS = True
    voice_control.DO_SPEAK_LAP_TIMES = True
    voice_control.DO_SPEAK_HOT_STINT_TIMES = True
    voice_control.DO_SPEAK_SECTOR_TIMES = True
    voice_control.DO_SPEAK_MINI_SECTORS = True
    voice_control.DO_SPEAK_MIN_SPEEDS = False
    voice_control.DO_SPEAK_WEATHER_CHANGES = True
    voice_control.DO_SPEAK_ALERTS = True
    return voice_control


def set_qualifying_profile(voice_control: VoiceControl):
    voice_control = VoiceControl()
    voice_control.DO_SPEAK_INVALIDATIONS = True
    voice_control.DO_SPEAK_ALERTS = True
    voice_control.DO_SPEAK_QUALI_TIME_LEFT = True
    return voice_control


def set_race_profile(voice_control: VoiceControl):
    voice_control = VoiceControl()
    voice_control.DO_SPEAK_VILLAN_LAP_DELTAS = True
    voice_control.DO_SPEAK_WEATHER_CHANGES = True
    voice_control.DO_SPEAK_ALERTS = True
    voice_control.DO_SPEAK_POSITION_CHANGES = True
    voice_control.DO_SPEAK_PIT_GAP_ALERTS = True
    voice_control.DO_SPEAK_NET_POSITION_ALERTS = True
    voice_control.DO_SPEAK_LAPS_REMAINING = True
    return voice_control


def set_session_profile(voice_control: VoiceControl, session: Session):
    # if session.is_practice or session.is_qualifying:
    # voice_control.speak(f"warning, using practice profile overloaded")
    if session.is_practice:
        voice_control = set_practice_profile(voice_control)
        voice_control.speak("Practice Profile Set")

    elif session.is_qualifying:
        voice_control = set_qualifying_profile(voice_control)
        voice_control.speak("Qualifying Profile Set")

    elif session.is_race:
        voice_control = set_race_profile(voice_control)
        voice_control.speak("Race Profile Set")
    return voice_control


def do_race_analysis(context: Context):
    print(f"Performing race analysis...")
    Analysis.plot_mini_sectors(context.hero)
    # Analysis.plot_stint(context.hero.stints[-1])
    # Analysis.plot_sectors(context.hero)
    # Analysis.plot_track(context.hero)
    # Analysis.plot_predicted_race_times(context.hero_history, context.villan_history)
    # Analysis.plot_logs(
    #     context.session_history, context.hero_history, context.villan_history
    # )
    pass


if __name__ == "__main__":
    CURRENT_DIR = os.path.dirname(__file__)
    WEATHER_WARNING = timedelta(minutes=3)

    # Global flag for graceful shutdown
    shutdown_requested = False

    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully"""
        global shutdown_requested
        if not shutdown_requested:
            shutdown_requested = True
            print("\n[Main] Shutdown requested, cleaning up...")
            VoiceControl.speak("Shutting down gracefully.")
        else:
            # Force exit if Ctrl+C pressed twice
            print("\n[Main] Force shutdown...")
            sys.exit(1)

    # Register the signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    # fmt: off
    # race
    UPD_DATA_LOAD_PKL = "Sessions\\indianapolis\\auto_logs\\20260113_202031_race_udp_data.pkl"
    SM_PKL_LOAD_PKL = "Sessions\\indianapolis\\auto_logs\\20260113_202031_race_sm.pkl"
    # practice
    UPD_DATA_LOAD_PKL = "Sessions\\barcelona\\auto_logs\\20260131_204124_race_udp_data.pkl"
    SM_PKL_LOAD_PKL = "Sessions\\barcelona\\auto_logs\\20260131_204124_race_sm.pkl"
    # error
    error_timestamp = "sm_20260210_205538"
    UPD_DATA_LOAD_PKL = f"C:\\Users\\chris\\OneDrive\\ACC\\Strategist\\udp_data_{'_'.join(error_timestamp.split('_')[-2:])}.pkl"
    UPD_DATA_LOAD_PKL = "C:\\Users\\chris\\OneDrive\\ACC\\Strategist\\udp_data.pkl"
    SM_PKL_LOAD_PKL = f"C:\\Users\\chris\\OneDrive\\ACC\\Strategist\\sm_{'_'.join(error_timestamp.split('_')[-2:])}.pkl"
    # fresh
    UPD_DATA_LOAD_PKL = "C:\\Users\\chris\\OneDrive\\ACC\\Strategist\\udp_data.pkl"
    SM_PKL_LOAD_PKL = "C:\\Users\\chris\\OneDrive\\ACC\\Strategist\\sm.pkl"
    # fmt: on

    parser = argparse.ArgumentParser(description="ACC Strategist Configuration")
    parser.add_argument(
        "--load-entries", action="store_true", help="Load entries from pickle files"
    )
    parser.add_argument(
        "--no-load-entries",
        action="store_false",
        dest="load_entries",
        help="Do not load entries from pickle files",
    )
    parser.add_argument(
        "--race-analysis", action="store_true", help="Perform race analysis"
    )
    parser.add_argument(
        "--no-race-analysis",
        action="store_false",
        dest="race_analysis",
        help="Skip race analysis",
    )
    parser.add_argument(
        "--data-logging", action="store_true", help="Enable data logging"
    )
    parser.add_argument(
        "--no-data-logging",
        action="store_false",
        dest="data_logging",
        help="Disable data logging",
    )
    parser.add_argument(
        "--hero-name", type=str, default="Amos Movo", help="Name of the hero driver"
    )
    parser.set_defaults(
        load_entries=True,
        # load_entries=False,
        race_analysis=True,
        # race_analysis=False,
        data_logging=True,
        hero_name="Amos Movo",
    )

    args = parser.parse_args()
    print(f"Arguments: {args}")

    DO_LOAD_ENTRIES = args.load_entries
    DO_RACE_ANALYSIS = args.race_analysis
    DO_DATA_LOGGING = args.data_logging
    DO_VOICE_CONTROL = True or not DO_RACE_ANALYSIS
    HERO_NAME = args.hero_name
    # HERO_NAME = "Riley Greear" if DO_RACE_ANALYSIS else args.hero_name

    loaded_udp_data: list[dict] = []
    sm: list[Optional[ACC_map]] = []
    aui: Optional[accUpdInterface] = None
    asm: Optional[accSharedMemory] = None

    if DO_LOAD_ENTRIES:
        DO_DATA_LOGGING = False

        VoiceControl.speak("Loading entries from pickle files.")

        loaded_udp_data = list(Logger.load_pickle_data(UPD_DATA_LOAD_PKL))
        loaded_sm = list(Logger.load_pickle_data(SM_PKL_LOAD_PKL))

        min_data_points = min(len(loaded_udp_data), len(loaded_sm))
        loaded_udp_data = loaded_udp_data[:min_data_points]
        loaded_sm = loaded_sm[:min_data_points]

    else:
        aui_info = {
            "name": "Amos Movo",
            "password": "asd",
            "speed": 166,  # ms
            "cmd_password": "",
        }
        aui = accUpdInterface("127.0.0.1", 9000, aui_info)
        aui.start()

        asm = accSharedMemory()

    if DO_DATA_LOGGING:
        logger = Logger()
        logger.initialize_logging()

    voice_control = VoiceControl()

    hero_assistance = None

    context: Context = Context()
    loaded_idx = 0  # used when reading entries csv
    try:
        voice_control.speak(f"Waiting for entries... hero: {HERO_NAME}")
        while not shutdown_requested:
            now = datetime.now()

            data: dict
            sm: Optional[ACC_map]
            if DO_LOAD_ENTRIES:
                if loaded_idx >= len(loaded_udp_data):
                    break

                now_timestamp, data = loaded_udp_data[loaded_idx]
                now_timestamp, sm = loaded_sm[loaded_idx]
                now = datetime.fromtimestamp(now_timestamp)
                loaded_idx += 1

            else:
                try:
                    data = aui.udp_data
                    sm = asm.read_shared_memory()

                except (InterruptedError, EOFError):
                    # Pipe interrupted during shutdown
                    print("[Main] Data access interrupted, shutting down...")
                    break

            # do load entries check in case we want to debug logging while using loaded data
            if DO_DATA_LOGGING and (
                DO_LOAD_ENTRIES or logger.should_log(now.timestamp(), interval=0.5)
            ):
                logger.log_data(now.timestamp(), data, sm)

            if not data:
                continue

            entries: Dict[int, CarEntry]
            entries_name_map: Dict[str, int]
            entries, entries_name_map = CarEntry.entries_to_car_entries(data["entries"])

            if HERO_NAME not in entries_name_map:
                continue
            hero_entry = entries[entries_name_map[HERO_NAME]]

            if sm:
                if not context.track_info:
                    context.track_info = TrackInfo()
                    context.track_info.update_from_sm(sm)
                    context.track_info.load_track_json(
                        track_json=os.path.join(
                            CURRENT_DIR,
                            "../tracks",
                            f"{context.track_info.sm_track}.json",
                        )
                    )

            context.session = Session(
                session_dict=data["session"],
                old_session=context.session,
                sm=sm,
                now=now,
                track_info=context.track_info,
                weather_warning=WEATHER_WARNING,
                voice_control=voice_control,
                mandatory_pits=(
                    max(
                        context.session.mandatory_pits,
                        context.hero.mandatory_pits_remaining,
                    )
                    if context.hero
                    else 0
                ),
            )
            if (
                not context.session.old_session
                or context.session.old_session.session_type
                != context.session.session_type
            ):
                if DO_RACE_ANALYSIS and context.hero:
                    do_race_analysis(context=context)

                if context.hero:
                    context.hero.end_stint(dump_stint=True)

                    if DO_DATA_LOGGING:
                        logger.copy_log_files_to_sessions(context)
                        logger = Logger()
                        logger.initialize_logging()

                # reset cars and track on session change
                context.reset_cars()
                voice_control = (
                    set_session_profile(voice_control, context.session)
                    if DO_VOICE_CONTROL
                    else voice_control
                )
                continue

            if context.session.is_race:
                context.villans = Villan.from_entries(
                    entries=entries,
                    old_villans=context.villans,
                    session=context.session,
                    now=now,
                )

            if not context.hero:
                voice_control.speak("Found hero.")

            context.hero = Hero(
                entry=hero_entry,
                old_hero=context.hero,
                villans=context.villans,
                session=context.session,
                sm=sm,
                now=now,
                voice_control=voice_control,
            )
            context.hero.update()

            if DO_LOAD_ENTRIES:
                context.session_history.append(context.session)
                context.hero_history.append(context.hero)
                context.villan_history.append(list(context.villans.values()))

    except KeyboardInterrupt:
        # This shouldn't happen anymore with signal handler, but just in case
        print("\n[Main] Keyboard interrupt received.")

    except InterruptedError:
        # Interrupted during pipe communication, normal during shutdown
        print("\n[Main] Interrupted during shutdown, cleaning up...")

    except Exception as e:
        voice_control.speak(f"Exception occurred: {e}")

        if DO_DATA_LOGGING:
            logger.log_data(now.timestamp(), data, sm)
            ts = logger.archive_logs_on_error()
            logger.write_error_log(ts, e)

        # Don't re-raise if it's a shutdown-related error
        if not shutdown_requested:
            raise e

    finally:
        print("[Main] Cleaning up resources...")

        if context.hero:
            context.hero.end_stint(dump_stint=True)
            if DO_DATA_LOGGING:
                logger.copy_log_files_to_sessions(context)

        if aui:
            print("[Main] Stopping UDP interface...")
            aui.stop()

        if asm:
            print("[Main] Closing shared memory...")
            asm.close()

        print("[Main] Cleanup complete.")

    if DO_RACE_ANALYSIS:
        do_race_analysis(context)


##### TODO #####
# compare sector 2 percent diff after villan exits pits warn undercut
# net position for class
