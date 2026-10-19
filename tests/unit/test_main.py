"""
Unit tests for cgm_analytics.main. No network: HTTP calls are mocked.
All these tests have been implemented by using Claude Code, and I have barely review them
"""

from unittest.mock import MagicMock, patch

import pytest
import requests
from pylibrelinkup import PyLibreLinkUp
from pylibrelinkup.api_url import APIUrl
from pylibrelinkup.exceptions import RedirectError
from pylibrelinkup.models.data import GlucoseMeasurement

from cgm_analytics.main import initialize_client, reading_to_row

# Shape of the /llu/config/country reply, trimmed to what initialize_client reads.
COUNTRY_CONFIG = {
    "data": {
        "regionalMap": {
            "us": {"lslApi": "https://api-us.libreview.io/"},
            "eu": {"lslApi": "https://api-eu.libreview.io/"},
        }
    }
}


def fake_response(json_data: dict) -> MagicMock:
    """A stand-in for requests.Response that returns json_data from .json()."""
    response = MagicMock()
    response.json.return_value = json_data
    return response


def test_login_without_redirect_keeps_default_server():
    with (
        patch.object(PyLibreLinkUp, "authenticate") as authenticate,
        patch("cgm_analytics.main.requests.get") as get,
    ):
        client = initialize_client("me@example.com", "secret")

    authenticate.assert_called_once()
    get.assert_not_called()
    assert client.api_url == APIUrl.US.value


def test_redirect_switches_to_regional_server():
    with (
        patch.object(
            PyLibreLinkUp, "authenticate", side_effect=[RedirectError(APIUrl.US), None]
        ) as authenticate,
        patch(
            "cgm_analytics.main.requests.get", return_value=fake_response(COUNTRY_CONFIG)
        ) as get,
    ):
        client = initialize_client("me@example.com", "secret")

    # Trailing slash removed, so the library's f"{api_url}/llu/..." URLs stay valid.
    assert client.api_url == "https://api-us.libreview.io"
    assert authenticate.call_count == 2
    assert get.call_args.args[0] == f"{APIUrl.US}/llu/config/country?country=DE"


def test_redirect_fails_if_country_config_returns_http_error():
    response = fake_response({})
    response.raise_for_status.side_effect = requests.HTTPError("430 Too Many Requests")

    with (
        patch.object(
            PyLibreLinkUp, "authenticate", side_effect=[RedirectError(APIUrl.US), None]
        ) as authenticate,
        patch("cgm_analytics.main.requests.get", return_value=response),
    ):
        with pytest.raises(requests.HTTPError):
            initialize_client("me@example.com", "secret")

    # It stopped at the error instead of logging in again with a bad URL.
    assert authenticate.call_count == 1

def api_reading(**overrides) -> dict:
    """One glucose reading as the LibreLinkUp graph endpoint returns it."""
    reading = {
        "FactoryTimestamp": "10/19/2026 6:15:00 AM",  # UTC
        "Timestamp": "10/19/2026 8:15:00 AM",  # phone's local time (UTC+2)
        "ValueInMgPerDl": 99,
        "Value": 99,
        "GlucoseUnits": 1,  # account displays mg/dL
        "MeasurementColor": 1,
        "Type": 0,
        "isHigh": False,
        "isLow": False,
    }
    return reading | overrides


def to_xcom(raw: dict) -> dict:
    """What load_readings receives: the parsed reading, dumped as in fetch_readings."""
    return GlucoseMeasurement.model_validate(raw).model_dump(mode="json")


def test_reading_to_row_matches_upsert_columns():
    row = reading_to_row(to_xcom(api_reading()))

    assert row == ("2026-10-19T06:15:00Z", "2026-10-19T08:15:00", 99.0)


def test_reading_to_row_uses_mg_dl_when_account_shows_mmol():
    row = reading_to_row(to_xcom(api_reading(Value=5.5, GlucoseUnits=0)))

    assert row[2] == 99.0