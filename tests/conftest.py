import socket
from pathlib import Path

import pytest

from factlock.adapters.json_repo import JsonCompanyData

DATA = Path(__file__).resolve().parents[1] / "data" / "tlink"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must never reach the network."""

    def blocked(*args: object, **kwargs: object) -> None:
        raise RuntimeError("network access is blocked in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture(scope="session")
def company() -> JsonCompanyData:
    return JsonCompanyData(DATA)
