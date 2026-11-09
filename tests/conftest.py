from pathlib import Path

import pytest

from redcap2hdcat.adapters import csv_dict, odm
from redcap2hdcat.config import Agent, Config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def dictionary_project():
    return csv_dict.load(FIXTURES / "dictionary.csv")


@pytest.fixture
def odm_project():
    return odm.load(FIXTURES / "project.xml")


@pytest.fixture
def full_config():
    """A configuration with every mandatory slot filled."""
    return Config(
        base_uri="https://redcap.example.org",
        health_categories=["http://healthdataportal.eu/ns/health#ElectronicHealthRecords"],
        publisher=Agent(name="Example Institute", email="data@example.org"),
        hdab=Agent(name="Example HDAB", email="hdab@example.org"),
        contact=Agent(name="DPO", email="dpo@example.org"),
    )
