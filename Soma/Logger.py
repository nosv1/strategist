import os
import pickle
import shutil
import traceback
from datetime import datetime
from threading import Thread
from typing import Optional

from Context import Context
from pyaccsharedmemory import ACC_map
from Track import TrackInfo


class Logger:
    """Handles all data logging operations for ACC session data."""

    def __init__(self):
        self.start_time = datetime.now()
        self.udp_dump_path = "udp_data.pkl"
        self.sm_dump_path = "sm.pkl"
        self.pos_history_dump_path = "pos_history.pkl"
        self.last_dump_timestamp = datetime.now().timestamp()
        self.is_enabled = False

    def initialize_logging(self):
        """
        Initialize logging by archiving existing log files.
        Deletes .old files and renames current files to .old.
        """
        pkl_files = [self.udp_dump_path, self.sm_dump_path, self.pos_history_dump_path]

        for pkl_file in pkl_files:
            old_file = pkl_file + ".old"
            if os.path.exists(old_file):
                os.remove(old_file)
            if os.path.exists(pkl_file):
                os.rename(pkl_file, old_file)

        self.is_enabled = True

    def log_data(self, timestamp: float, udp_data: dict, sm: ACC_map):
        """
        Log UDP and shared memory data to pickle files asynchronously.

        Args:
            timestamp: Unix timestamp for the log entry
            udp_data: UDP data dictionary
            sm: ACC shared memory object
        """
        if not self.is_enabled:
            return

        def worker(udp_data, sm):
            with open(self.udp_dump_path, "ab") as f_udp:
                pickle.dump([timestamp, udp_data], f_udp)
            with open(self.sm_dump_path, "ab") as f_sm:
                pickle.dump([timestamp, sm], f_sm)

        t = Thread(target=worker, args=(udp_data, sm), daemon=True)
        t.start()

    def should_log(self, current_timestamp: float, interval: float = 1.0) -> bool:
        """
        Check if enough time has passed since last log.

        Args:
            current_timestamp: Current Unix timestamp
            interval: Minimum time interval between logs in seconds

        Returns:
            True if logging should occur
        """
        if current_timestamp - self.last_dump_timestamp >= interval:
            self.last_dump_timestamp = current_timestamp
            return True
        return False

    def copy_log_files_to_sessions(self, context: Context):
        """
        Copy current log files to the sessions directory structure.
        Runs asynchronously in a separate thread.
        """

        try:
            if (
                not context.track_info
                or not hasattr(context.track_info, "sm_track")
                or not context.track_info.sm_track
            ):
                print(f"[Logger] No valid track info; skipping log copy.")
                return

            # Create sessions directory structure
            sessions_dir = os.path.join(
                os.path.dirname(__file__),
                "..",
                "sessions",
                context.track_info.sm_track,
                "auto_logs",
            )
            os.makedirs(sessions_dir, exist_ok=True)

            # Generate timestamp for filenames
            ts = self.start_time.strftime("%Y%m%d_%H%M%S")
            prefix = f"{ts}_{context.session.session_type.lower()}"

            # Copy pickle files if they exist
            files_to_copy = [
                (self.udp_dump_path, f"{prefix}_udp_data.pkl"),
                (self.sm_dump_path, f"{prefix}_sm.pkl"),
            ]

            for source, dest_name in files_to_copy:
                if os.path.exists(source):
                    dest_path = os.path.join(sessions_dir, dest_name)
                    shutil.copy2(source, dest_path)
                    print(f"[Logger] Copied log file to {dest_path}")

        except Exception:
            pass

    def archive_logs_on_error(self) -> str:
        """
        Rename log files with timestamp when an error occurs.

        Returns:
            Timestamp string used for file naming
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            pkl_candidates = [self.udp_dump_path, self.sm_dump_path]
            for p in pkl_candidates:
                if p and os.path.exists(p):
                    base, ext = os.path.splitext(p)
                    new_name = f"{base}_{ts}{ext}"
                    try:
                        os.rename(p, new_name)
                    except Exception:
                        # ignore individual rename errors but continue
                        pass
        except Exception:
            # ignore rename routine errors
            pass

        return ts

    def write_error_log(self, timestamp_str: str, exception: Exception):
        """
        Write error details to a timestamped error log file.

        Args:
            timestamp_str: Timestamp string for the error log filename
            exception: The exception that occurred
        """
        with open(f"error_log_{timestamp_str}.txt", "w") as error_file:
            error_file.write(f"\n{'='*50}\n")
            error_file.write(f"Error occurred at: {datetime.now()}\n")
            error_file.write(f"Exception: {exception}\n")
            error_file.write(traceback.format_exc())

    @staticmethod
    def load_pickle_data(file_path: str):
        """
        Load data from a pickle file.

        Args:
            file_path: Path to the pickle file

        Yields:
            Unpickled data entries
        """
        with open(file_path, "rb") as f:
            while True:
                try:
                    yield pickle.load(f)
                except EOFError:
                    break
