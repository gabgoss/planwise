"""The lock that serialises `update_backlog.py --create`.

The lock is the file `{backlog_dir}/.backlog-create.lock`, created with
O_CREAT|O_EXCL. Its owner keeps the file open, takes the system's lock on it,
and then writes who it is. The system drops that lock when the owner ends, so a
waiter that can take it on a file that still names an owner has proof that the
owner is dead. The waiter then takes the file over. An empty file, a record it
cannot read, and a record from another machine are never taken over.

A machine is told apart by its host name and `os.name`. Two machines that share
both, on a shared folder whose locks stay local, are not supported.
"""

import json
import os
import socket
import sys
import time
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path

# Seconds `creation_lock` waits for another `--create` to release the lock.
CREATE_LOCK_TIMEOUT = 10.0

# Seconds the lock's release retries a removal that Windows refuses because
# another process holds the file open.
LOCK_RELEASE_TIMEOUT = 2.0

# Seconds a new owner retries the system's lock while a waiter is testing it.
OWNER_LOCK_TIMEOUT = 1.0

_RETRY_SECONDS = 0.05

# A Windows byte lock blocks reads of that byte, so the locked byte lies far
# past the record, and a person can still read the file.
_LOCK_OFFSET = 1 << 30

# Without O_BINARY, Windows opens the descriptor in text mode.
_BINARY = getattr(os, "O_BINARY", 0)


class CreationLockTimeout(Exception):
    """Raised when the backlog creation lock stays held past the timeout."""


def _try_lock(fd: int) -> bool:
    """Take the system's lock on an open file without waiting."""
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _is_file_at(fd: int, path: Path) -> bool:
    """True while `path` still names the open file."""
    try:
        return os.path.samestat(os.fstat(fd), os.stat(path))
    except OSError:
        return False


def _read_record(fd: int) -> dict | None:
    """The owner record in an open lock file, or None when it holds none."""
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        record = json.loads(os.read(fd, 4096).decode("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or not isinstance(record.get("pid"), int):
        return None
    if not all(isinstance(record.get(key), str) for key in ("host", "os", "started")):
        return None
    return record


def _write_record(fd: int) -> None:
    """Replace the file's content with this process's owner record."""
    record = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "os": os.name,
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    data = json.dumps(record).encode("utf-8")
    # Write first and cut after, so a failed write does not leave an empty lock.
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, data)
    os.ftruncate(fd, len(data))


def _is_from_here(record: dict | None) -> bool:
    """True for a record whose owner ran on this host under this os.name."""
    return (
        record is not None
        and record["host"] == socket.gethostname()
        and record["os"] == os.name
    )


def _take_over(lock: Path) -> int | None:
    """Take over a lock whose recorded owner is dead. Returns the open, locked
    descriptor, now carrying this process's record, or None to keep waiting.
    The file is never removed and created again, which two waiters would race.
    """
    try:
        fd = os.open(str(lock), os.O_RDWR | _BINARY)
    except OSError:
        return None
    taken = False
    try:
        # Test the record first, so a new owner's still-empty file is not locked.
        if not _is_from_here(_read_record(fd)) or not _try_lock(fd):
            return None
        # Read again under the lock: the owner may have released in between.
        owner = _read_record(fd)
        if not _is_from_here(owner) or not _is_file_at(fd, lock):
            return None
        _write_record(fd)
        taken = True
    except OSError:
        return None
    finally:
        if not taken:
            os.close(fd)
    print(
        f"NOTE: took over the backlog creation lock at {lock}. Its owner "
        f"(pid {owner['pid']}, started {owner['started']}) is no longer running.",
        file=sys.stderr,
    )
    return fd


def _claim(fd: int) -> None:
    """Lock a file this process just created, then record the owner in it.
    A filesystem without lock support gets no record, so no waiter takes over.
    """
    deadline = time.monotonic() + OWNER_LOCK_TIMEOUT
    while not _try_lock(fd):
        if time.monotonic() >= deadline:
            return
        time.sleep(_RETRY_SECONDS)
    # The lock still serialises without a record.
    with suppress(OSError):
        _write_record(fd)


def _timeout_message(lock: Path, timeout: float) -> str:
    message = (
        f"could not take the backlog creation lock at {lock} "
        f"within {timeout:g}s. If no other update_backlog.py "
        f"--create is running, delete the lock file."
    )
    try:
        fd = os.open(str(lock), os.O_RDONLY | _BINARY)
    except OSError:
        return message
    try:
        owner = _read_record(fd)
    finally:
        os.close(fd)
    if owner is None:
        return message
    return (
        f"{message} The lock records pid {owner['pid']} on host "
        f"{owner['host']}, started {owner['started']}."
    )


def _remove_lock_file(lock: Path) -> None:
    """Remove the lock file. On Windows the removal raises PermissionError
    while another process holds the file open, so retry briefly. A lock that
    stays gets a warning, never an exception: the item file may already be
    written, and the caller still has to print its id.
    """
    deadline = time.monotonic() + LOCK_RELEASE_TIMEOUT
    while True:
        try:
            lock.unlink(missing_ok=True)
            return
        except OSError as e:
            if not isinstance(e, PermissionError) or time.monotonic() >= deadline:
                print(
                    f"WARNING: could not remove the backlog creation lock at {lock}: "
                    f"{e.strerror}. Delete it before the next update_backlog.py --create.",
                    file=sys.stderr,
                )
                return
            time.sleep(_RETRY_SECONDS)


def _release(fd: int, lock: Path) -> None:
    """Empty the record while the lock is still held, so that no waiter can
    mistake a releasing lock for a dead owner's, then remove the file.
    """
    with suppress(OSError):
        os.ftruncate(fd, 0)
    if os.name == "nt":
        # Windows refuses to remove an open file, so close first.
        os.close(fd)
        _remove_lock_file(lock)
        return
    # Elsewhere remove first, while the lock still keeps waiters out. A person
    # may have deleted this file, so remove it only while the path still names it.
    try:
        if _is_file_at(fd, lock):
            _remove_lock_file(lock)
    finally:
        os.close(fd)


@contextmanager
def creation_lock(backlog_dir: Path, timeout: float | None = None):
    """Hold `{backlog_dir}/.backlog-create.lock` for the body of a `with`.

    Two `--create` calls that compute the next id and then write the item
    file must not interleave, or both take the same id. O_CREAT|O_EXCL
    succeeds for exactly one caller, so the lock file serialises them.
    A lock whose recorded owner is proven dead is taken over (`_take_over`).
    `timeout` defaults to `CREATE_LOCK_TIMEOUT`, read at call time. A timeout
    raises `CreationLockTimeout` and never deletes the lock, because another
    caller may hold it. The lock is removed when the body exits, even on error.
    A refused removal is retried, then warned about (`_remove_lock_file`).
    """
    if timeout is None:
        timeout = CREATE_LOCK_TIMEOUT
    backlog_dir = Path(backlog_dir)
    backlog_dir.mkdir(parents=True, exist_ok=True)
    lock = backlog_dir / ".backlog-create.lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_RDWR | _BINARY)
            created = True
        except (FileExistsError, PermissionError) as e:
            fd = _take_over(lock)
            created = False
            if fd is None:
                # On Windows a lock file another process is still deleting
                # raises PermissionError, not FileExistsError: retry it the same.
                if time.monotonic() >= deadline:
                    if isinstance(e, PermissionError) and not lock.exists():
                        raise CreationLockTimeout(
                            f"could not create the backlog creation lock at {lock}: "
                            f"{e.strerror}. Check that the folder is writable."
                        ) from None
                    raise CreationLockTimeout(_timeout_message(lock, timeout)) from None
                time.sleep(_RETRY_SECONDS)
                continue
        # This call owns the lock file, so from here on every exit path,
        # an interrupt included, removes it.
        try:
            if created:
                _claim(fd)
            yield lock
        finally:
            _release(fd, lock)
        return
