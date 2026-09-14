"""Short-lived, strictly read-only connections to the Collector's existing files."""
from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import time

from data_provider.errors import (DataNotFoundError, DataProviderError,
                                  DataProviderInputError, DataUnavailableError)


def validate_day(day):
    if not re.fullmatch(r"[0-9]{8}", day):
        raise DataProviderInputError("day must be a valid YYYYMMDD")
    try:
        parsed = datetime.strptime(day, "%Y%m%d")
        if parsed.year < 1900:
            raise ValueError()
    except ValueError:
        raise DataProviderInputError("day must be a valid YYYYMMDD") from None
    return day


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).absolute()

    def check_directory(self):
        if not self.directory.is_dir() or not os.access(self.directory, os.R_OK | os.X_OK):
            raise DataUnavailableError("Shared data directory is unavailable or unreadable")

    def path(self, day):
        validate_day(day)
        self.check_directory()
        path = self.directory / f"{day}.sqlite"
        if path.is_symlink():
            raise DataUnavailableError("Daily database must not be a symlink")
        if not path.is_file():
            raise DataNotFoundError("Daily database does not exist")
        return path

    @staticmethod
    def size(path):
        size = path.stat().st_size
        try:
            size += Path(str(path) + "-wal").stat().st_size
        except FileNotFoundError:
            pass
        return size

    def days(self):
        self.check_directory()
        result = []
        for path in self.directory.glob("*.sqlite"):
            try:
                validate_day(path.stem)
                if path.is_file() and not path.is_symlink():
                    result.append({"day": path.stem, "size_bytes": self.size(path)})
            except (DataProviderError, FileNotFoundError):
                continue
        return sorted(result, key=lambda row: row["day"], reverse=True)

    @contextmanager
    def connect(self, day):
        path = self.path(day)
        lock = None
        connection = None
        immutable = False
        try:
            # Do not create lock files, sidecars or databases from the query service.
            try:
                lock = open(self.directory / ".collector.lock", "rb")
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                wal = Path(str(path) + "-wal")
                immutable = not wal.exists() or wal.stat().st_size == 0
            except BlockingIOError:
                lock.close()
                lock = None
            except FileNotFoundError:
                pass
            if not immutable:
                # A read-only mount cannot create WAL sidecars. Refuse early even on
                # a writable development directory, preserving deployment semantics.
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(path) + suffix)
                    if not sidecar.is_file() or sidecar.is_symlink():
                        raise DataUnavailableError("WAL sidecars unavailable; stop Collector normally to read this historical day")
            uri = path.as_uri() + "?mode=ro" + ("&immutable=1" if immutable else "")
            connection = sqlite3.connect(uri, uri=True, timeout=1)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            deadline = time.monotonic() + 3
            connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            connection.execute("BEGIN")
            if (connection.execute("PRAGMA user_version").fetchone()[0] != 1
                    or connection.execute("PRAGMA application_id").fetchone()[0] != 1145914161
                    or [tuple(r) for r in connection.execute("SELECT singleton,trading_day,schema_version FROM dataset")] != [(1, day, 1)]):
                raise DataUnavailableError("Unsupported schema or mismatched trading day")
            yield connection
        except sqlite3.Error:
            raise DataUnavailableError("Daily SQLite unreadable, incompatible, busy or query timed out") from None
        finally:
            if connection is not None:
                connection.close()
            if lock is not None:
                lock.close()

    def summary(self, day):
        with self.connect(day) as db:
            instruments = [dict(row) for row in db.execute(
                "SELECT InstrumentID AS instrument,COUNT(*) AS rows,MAX(received_us) AS last_received_us "
                "FROM snapshots GROUP BY InstrumentID ORDER BY InstrumentID")]
            runs = [dict(row) for row in db.execute(
                "SELECT run_id,source,started_us,stopped_us,last_write_us FROM runs ORDER BY started_us DESC LIMIT 100")]
        return {"day": day, "rows": sum(row["rows"] for row in instruments),
                "size_bytes": self.size(self.path(day)), "instruments": instruments, "runs": runs}

    def snapshots(self, day, instrument, limit):
        with self.connect(day) as db:
            clause = "WHERE InstrumentID=?" if instrument is not None else ""
            params = (instrument, limit) if instrument is not None else (limit,)
            rows = [dict(row) for row in db.execute(
                "SELECT id,run_id,sequence,received_us,snapshot_us,TradingDay,InstrumentID,"
                "UpdateTime,LastPrice,BidPrice1,AskPrice1,Volume,OpenInterest FROM snapshots "
                + clause + " ORDER BY received_us DESC,id DESC LIMIT ?", params)]
        return {"day": day, "rows": rows}

    def heartbeat(self):
        from data_provider.runtime_status import read_runtime_status, diagnostic
        try:
            return diagnostic(read_runtime_status(self.directory))
        except DataUnavailableError:
            return diagnostic(None)
