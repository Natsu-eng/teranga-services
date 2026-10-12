"""IP réelle du client derrière les proxys de confiance (app/core/client_ip.py)."""

from typing import Any

import pytest
from starlette.requests import Request

from app.core.client_ip import client_ip
from app.core.config import Settings


def _settings(hops: int | None) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        jwt_secret="x" * 32,
        payment_provider="disabled",
        trusted_proxy_hops=hops,
    )


def _request(peer: str, *forwarded: str) -> Request:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded]
    scope: dict[str, Any] = {"type": "http", "headers": headers, "client": (peer, 1234)}
    return Request(scope)


def test_without_trusted_proxy_the_header_is_ignored() -> None:
    # Dev / accès direct : un en-tête fourni par le client ne compte jamais.
    request = _request("203.0.113.9", "1.2.3.4")
    assert client_ip(request, _settings(None)) == "203.0.113.9"
    assert client_ip(request, _settings(0)) == "203.0.113.9"


def test_behind_one_proxy_the_address_seen_by_the_proxy_wins() -> None:
    # Railway ajoute à droite l'adresse réelle qu'il a vue.
    request = _request("10.0.0.2", "196.207.1.20")
    assert client_ip(request, _settings(1)) == "196.207.1.20"


def test_a_client_cannot_spoof_its_address() -> None:
    # Le client tente de se faire passer pour 1.2.3.4 : le proxy ajoute sa
    # vraie adresse à droite, c'est elle qui compte (limite non contournable).
    request = _request("10.0.0.2", "1.2.3.4, 196.207.1.20")
    assert client_ip(request, _settings(1)) == "196.207.1.20"
    split = _request("10.0.0.2", "1.2.3.4", "196.207.1.20")
    assert client_ip(split, _settings(1)) == "196.207.1.20"


@pytest.mark.parametrize("forwarded", [(), ("196.207.1.20",)])
def test_a_shorter_chain_than_expected_falls_back_to_the_peer(forwarded: tuple[str, ...]) -> None:
    assert client_ip(_request("10.0.0.2", *forwarded), _settings(2)) == "10.0.0.2"


def test_two_trusted_proxies_read_the_second_entry_from_the_right() -> None:
    request = _request("10.0.0.3", "1.2.3.4, 196.207.1.20, 172.16.0.5")
    assert client_ip(request, _settings(2)) == "196.207.1.20"
