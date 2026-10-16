"""Fetch FreeStyle Libre glucose readings from the LibreLinkUp API.

Run as a script, it logs in to LibreLinkUp with the credentials of the
``librelinkup`` Airflow connection (``AIRFLOW_CONN_LIBRELINKUP`` in ``.env``, JSON
with ``login`` and ``password``), the same ones the ``fetch_glucose`` DAG uses,
takes the first patient on the account (myself) and prints the last ~12 hours of
glucose readings, one every ~15 minutes.

Regional servers
----------------
Glucose readings are health data, and laws such as the EU's GDPR restrict where
that data may be stored. Abbott therefore runs the same LibreView API on
several regional servers, each with its own database::

    api-us.libreview.io   -> US accounts
    api-eu.libreview.io   -> EU accounts
    api-de.libreview.io   -> Germany
    api-ap.libreview.io   -> Asia-Pacific
    api-au.libreview.io   -> Australia
    api.libreview.ru      -> Russia (fully separate, not in the shared directory)
    ...

Each account and its readings live in exactly one region. ``api.libreview.io``
is the global entry point: it holds no glucose data and works as a directory,
answering a login with "not here, go to region X".

Login flow
----------
::

    POST api.libreview.io/llu/auth/login      body: email+password -> "go to us"
    GET  api-us.../llu/config/country         (public)             -> us = api-us.libreview.io
    POST api-us.libreview.io/llu/auth/login   body: email+password -> token
    GET  api-us.../llu/connections/{id}/graph header: Bearer token -> glucose data

pylibrelinkup maps the ``US`` region to ``api.libreview.io``, the directory
server, which would just redirect again forever. So instead of using the
library's region list, the real regional server is looked up in
``/llu/config/country`` (the same approach as DiaKEM/libre-link-up-api-client).

Note: this API is unofficial and undocumented; it was worked out from how the
LibreLinkUp app behaves.
"""

import json
import os

import requests
from dotenv import load_dotenv
from pylibrelinkup import PyLibreLinkUp
from pylibrelinkup.api_url import APIUrl
from pylibrelinkup.exceptions import RedirectError
from pylibrelinkup.models.data import GlucoseMeasurement, Patient


def initialize_client(email: str, password: str) -> PyLibreLinkUp:
    """Create a PyLibreLinkUp client and log in to the LibreLinkUp API.

    Follows the regional redirect to the account's home server
    (e.g. api-us.libreview.io).

    Returns:
        An authenticated client, ready for get_patients(), graph(), etc.

    Raises:
        RedirectError, requests.HTTPError: if login fails.
    """
    client = PyLibreLinkUp(email=email, password=password)

    try:
        # 1. Authenticate 
        # Client starts at APIUrl.US = https://api.libreview.io, the library default. That server doesnt keep accounts
        # It only replies: {"status": 0, "data": {"redirect": true, "region": "us"}}
        # pylibrelinkup turns that reply into a RedirectError, with exc.region = APIUrl.US.
        client.authenticate()
    except RedirectError as exc:
        print(f"Regional redirect detected: {exc.region.name}")

        # 2. Figure out right endpoint to authenticate
        # The obvious fix would be to create a new client with api_url=exc.region. 
        # That fails because pylibrelinkup maps US to api.libreview.io, the same server that only redirects.

        # /llu/config/country is a public config endpoint the LLU app uses. It needs no login.
        # ?country=DE is just a required parameter. The DiaKEM client uses DE too. Any valid country returns the same list of regions.
        # client._get_headers() reuses the library's headers (product: llu.android, version: 4.16.0, …), because LibreView rejects requests that don't look like the app.
        response = requests.get(
            f"{APIUrl.US}/llu/config/country?country=DE",
            headers=client._get_headers(),
            timeout = 10
        )
        # raises an error if the reply is an HTTP error such as 430 (rate limited).
        response.raise_for_status()
        # regionalMap lists every region and its real server: e.g. "us": {"lslApi": "https://api-us.libreview.io/", ...}
        regional_map = response.json()["data"]["regionalMap"]
        # .rstrip("/") removes the trailing slash. The library builds URLs as f"{api_url}/llu/...", and without this you'd get //llu/....
        #  It sets client.api_url directly instead of making a new PyLibreLinkUp(...)
        client.api_url = regional_map[exc.region.name.lower()]["lslApi"].rstrip("/")
        
        # 3. Authenticate again, now with the right endpoint
        client.authenticate()

    print("Authentication successful.")
    return client


def get_my_patient(client: PyLibreLinkUp) -> Patient:
    """Return the first patient on the account (myself)."""
    return client.get_patients()[0]  

def fetch_recent_readings(client: PyLibreLinkUp, patient: Patient) -> list[GlucoseMeasurement]:
    """Fetch the patient's recent glucose readings from LibreLinkUp.

    These are the points of the app's history graph: one reading about every
    15 minutes, covering up to the last ~12 hours, oldest first.
    """
    return client.graph(patient_identifier=patient)

if __name__ == "__main__":
    load_dotenv()
    # Same credentials Airflow uses: the `librelinkup` connection, stored as JSON in .env.
    credentials = json.loads(os.environ["AIRFLOW_CONN_LIBRELINKUP"])
    client = initialize_client(credentials["login"], credentials["password"])
    my_patient = get_my_patient(client)
    for reading in fetch_recent_readings(client, my_patient):
        print(reading)

