from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    override = os.environ.get("MTMEM_ICDE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def frozen_root() -> Path:
    return repo_root() / "results" / "frozen"
