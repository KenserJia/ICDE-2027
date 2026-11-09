"""Two-slot, checksummed, directory-durable checkpoint storage.

The payload is opaque.  The MT-Memory engine already checksums its own snapshot;
this layer adds generation selection and a second envelope checksum so recovery
can reject incomplete or corrupt slots before deserializing the engine.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import signal
import struct
import threading
from typing import Optional


MAGIC = b"MT2SLOT1"
HEADER = struct.Struct("<8sQQ32s")
TRAILER_BYTES = 32


class CorruptCheckpoint(ValueError):
    pass


def _envelope(generation: int, payload: bytes) -> bytes:
    payload = bytes(payload)
    header = HEADER.pack(MAGIC, int(generation), len(payload), hashlib.sha256(payload).digest())
    body = header + payload
    return body + hashlib.sha256(body).digest()


def decode(blob: bytes) -> tuple[int, bytes]:
    if len(blob) < HEADER.size + TRAILER_BYTES:
        raise CorruptCheckpoint("truncated envelope")
    body, trailer = blob[:-TRAILER_BYTES], blob[-TRAILER_BYTES:]
    if hashlib.sha256(body).digest() != trailer:
        raise CorruptCheckpoint("envelope checksum")
    magic, generation, length, payload_hash = HEADER.unpack(body[:HEADER.size])
    if magic != MAGIC:
        raise CorruptCheckpoint("magic")
    payload = body[HEADER.size:]
    if len(payload) != length:
        raise CorruptCheckpoint("payload length")
    if hashlib.sha256(payload).digest() != payload_hash:
        raise CorruptCheckpoint("payload checksum")
    return int(generation), payload


def _kill() -> None:
    os.kill(os.getpid(), signal.SIGKILL)


class TwoSlotStore:
    def __init__(self, directory: str | os.PathLike[str], name: str = "state"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.name = name
        self.paths = [self.directory / f"{name}.{i}.chk" for i in range(2)]
        self.lock_path = self.directory / f"{name}.lock"
        self._thread_lock = threading.RLock()

    @contextmanager
    def _locked(self, exclusive: bool):
        with self._thread_lock:
            fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    @staticmethod
    def _read(path: Path) -> tuple[int, bytes]:
        return decode(path.read_bytes())

    def scan(self) -> tuple[list[tuple[int, int, bytes]], list[dict]]:
        valid, invalid = [], []
        for index, path in enumerate(self.paths):
            if not path.exists():
                continue
            try:
                generation, payload = self._read(path)
                valid.append((generation, index, payload))
            except (OSError, CorruptCheckpoint) as exc:
                invalid.append({"slot": index, "path": str(path), "error": str(exc)})
        valid.sort(key=lambda row: (row[0], row[1]))
        return valid, invalid

    def recover(self) -> tuple[int, bytes, dict]:
        with self._locked(False):
            valid, invalid = self.scan()
            if not valid:
                raise FileNotFoundError("no valid checkpoint slot")
            generation, slot, payload = valid[-1]
            return generation, payload, {"slot": slot, "invalid": invalid,
                                         "valid_generations": [v[0] for v in valid]}

    def commit(self, payload: bytes, generation: Optional[int] = None,
               failpoint: Optional[str] = None) -> dict:
        with self._locked(True):
            valid, _ = self.scan()
            newest = valid[-1] if valid else None
            if generation is None:
                generation = 0 if newest is None else newest[0] + 1
            if newest is not None and generation <= newest[0]:
                raise ValueError("generation must increase")
            target = 0 if newest is None else 1 - newest[1]
            path = self.paths[target]
            pending = path.with_suffix(path.suffix + ".pending")
            blob = _envelope(generation, payload)
            with pending.open("wb") as handle:
                if failpoint == "after_partial_write":
                    handle.write(blob[:max(1, len(blob) // 2)])
                    handle.flush()
                    _kill()
                handle.write(blob)
                handle.flush()
                if failpoint == "before_file_fsync":
                    _kill()
                os.fsync(handle.fileno())
            if failpoint == "after_file_fsync":
                _kill()
            os.replace(pending, path)
            if failpoint == "after_replace_before_dir_fsync":
                _kill()
            directory_fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            if failpoint == "after_dir_fsync":
                _kill()
            return {"generation": int(generation), "slot": target,
                    "payload_bytes": len(payload), "envelope_bytes": len(blob)}
