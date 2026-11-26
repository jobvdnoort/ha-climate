"""Load the pure calculation module without importing Home Assistant."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

MODULE_PATH = (
    Path(__file__).parent.parent / "custom_components" / "ha_climate" / "calculations.py"
)


def _load_calculations():
    spec = importlib.util.spec_from_file_location("ha_climate_calculations", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


calc = _load_calculations()


@pytest.fixture
def calculations():
    """Return the calculations module."""
    return calc
