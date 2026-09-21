import os
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))

from rednix.config import load_config  # noqa: E402


@pytest.fixture
def config(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    monkeypatch.setenv("REDNIX_STATE_ROOT", str(root))
    monkeypatch.delenv("REDNIX_FLAKE", raising=False)
    cfg = load_config(None)
    cfg.share_root = tmp_path / "CTF"
    return cfg
