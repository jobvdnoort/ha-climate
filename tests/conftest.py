"""Load the pure calculation module without importing Home Assistant."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

PACKAGE = Path(__file__).parent.parent / "custom_components" / "ha_climate"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"ha_climate_{name}", PACKAGE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


calc = _load("calculations")
thermal = _load("thermal")
boiler = _load("boiler")


@pytest.fixture
def calculations():
    """Return the calculations module."""
    return calc
