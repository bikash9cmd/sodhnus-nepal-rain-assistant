from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from sodhnus.data import load

ROOT = Path(__file__).resolve().parents[1]
GOLD = str(ROOT / "data" / "barsha-gold")
TODAY = date(2026, 10, 13)


@pytest.fixture(scope="session")
def gold():
    return load(GOLD)
