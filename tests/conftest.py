"""Shared test fixtures for ApiGuard tests."""

from pathlib import Path

import pytest

from apiguard.parser import parse_spec

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir():
    """Return the path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def petstore_v1():
    """Parse petstore v1 spec."""
    return parse_spec(str(FIXTURES_DIR / "petstore_v1.yaml"))


@pytest.fixture
def petstore_v2_breaking():
    """Parse petstore v2 breaking spec."""
    return parse_spec(str(FIXTURES_DIR / "petstore_v2_breaking.yaml"))


@pytest.fixture
def petstore_v2_nonbreaking():
    """Parse petstore v2 non-breaking spec."""
    return parse_spec(str(FIXTURES_DIR / "petstore_v2_nonbreaking.yaml"))


@pytest.fixture
def empty_spec():
    """Parse empty spec."""
    return parse_spec(str(FIXTURES_DIR / "empty_spec.yaml"))


@pytest.fixture
def ref_spec_v1():
    """Parse ref test spec v1."""
    return parse_spec(str(FIXTURES_DIR / "ref_spec_v1.yaml"))


@pytest.fixture
def ref_spec_v2():
    """Parse ref test spec v2."""
    return parse_spec(str(FIXTURES_DIR / "ref_spec_v2.yaml"))


@pytest.fixture
def params_v1():
    """Parse params test spec v1."""
    return parse_spec(str(FIXTURES_DIR / "params_v1.yaml"))


@pytest.fixture
def params_v2():
    """Parse params test spec v2."""
    return parse_spec(str(FIXTURES_DIR / "params_v2.yaml"))
