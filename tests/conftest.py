"""Shared pytest fixtures for hot-events-radar tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Reference "now" — all fixture entries are relative to this timestamp.
# Tests pass a large window + this fixed now so they are deterministic
# regardless of when the test suite runs.
REFERENCE_NOW = datetime(2026, 4, 11, 14, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def reference_now() -> datetime:
    return REFERENCE_NOW


@pytest.fixture
def fixture_8k_xml() -> str:
    return (FIXTURES / "sample_8k.xml").read_text()


@pytest.fixture
def fixture_halts_xml() -> str:
    return (FIXTURES / "sample_halts.xml").read_text()


@pytest.fixture
def fixture_earnings_json() -> dict:
    import json
    return json.loads((FIXTURES / "sample_earnings.json").read_text())


@pytest.fixture
def fixture_bw_xml() -> str:
    return (FIXTURES / "sample_bw.xml").read_text()
