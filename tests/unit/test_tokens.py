"""T05 acceptance: issue->verify round-trip, expiry/revocation rejection, admit cap, release.

The TokenService is exercised with a fixed signing key and an in-memory StateStore, per
modules.md (the service is pure given the key + counters). Expiry is tested with a negative
ttl so a token is already expired at verify time — no sleeping.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from compute4me.master.state import StateStore
from compute4me.master.tokens import InvalidToken, TokenService

# >=32 bytes: avoids pyjwt's InsecureKeyLengthWarning for HS256.
_KEY = "test-signing-key-padded-to-32-bytes-min"
_CERT_FP = "ab:cd:ef:12"


@pytest.fixture
def service() -> TokenService:
    # In-memory DB: each test gets a fresh, isolated store.
    return TokenService(signing_key=_KEY, cert_fp=_CERT_FP, store=StateStore(":memory:"))


@pytest.mark.unit
@pytest.mark.task("T05")
def test_issue_then_verify_round_trips(service: TokenService) -> None:
    token = service.issue(room="lab", max_workers=4, ttl=timedelta(days=30))

    claims = service.verify(token)

    assert claims.room == "lab"
    assert claims.max_workers == 4
    assert claims.admin is False


@pytest.mark.unit
@pytest.mark.task("T05")
def test_claims_carry_master_cert_fp(service: TokenService) -> None:
    token = service.issue(room="lab", max_workers=None, ttl=timedelta(days=30))

    claims = service.verify(token)

    assert claims.master_cert_fp == _CERT_FP


@pytest.mark.unit
@pytest.mark.task("T05")
def test_admin_flag_is_carried(service: TokenService) -> None:
    token = service.issue(room="lab", max_workers=None, ttl=timedelta(days=30), admin=True)

    assert service.verify(token).admin is True


@pytest.mark.unit
@pytest.mark.task("T05")
def test_expired_token_rejected(service: TokenService) -> None:
    token = service.issue(room="lab", max_workers=1, ttl=timedelta(seconds=-1))

    with pytest.raises(InvalidToken):
        service.verify(token)


@pytest.mark.unit
@pytest.mark.task("T05")
def test_bad_signature_rejected(service: TokenService) -> None:
    token = service.issue(room="lab", max_workers=1, ttl=timedelta(days=30))
    other = TokenService(
        signing_key="a-totally-different-signing-key-32-bytes",
        cert_fp=_CERT_FP,
        store=StateStore(":memory:"),
    )

    with pytest.raises(InvalidToken):
        other.verify(token)


@pytest.mark.unit
@pytest.mark.task("T05")
def test_revoked_jti_rejected(service: TokenService) -> None:
    token = service.issue(room="lab", max_workers=1, ttl=timedelta(days=30))
    jti = service.verify(token).jti

    service.revoke(jti)

    with pytest.raises(InvalidToken):
        service.verify(token)


@pytest.mark.unit
@pytest.mark.task("T05")
def test_revocation_survives_restart() -> None:
    # A new TokenService over the same store rebuilds the revocation set from durable metadata.
    store = StateStore(":memory:")
    service = TokenService(signing_key=_KEY, cert_fp=_CERT_FP, store=store)
    token = service.issue(room="lab", max_workers=1, ttl=timedelta(days=30))
    service.revoke(service.verify(token).jti)

    reopened = TokenService(signing_key=_KEY, cert_fp=_CERT_FP, store=store)

    with pytest.raises(InvalidToken):
        reopened.verify(token)


@pytest.mark.unit
@pytest.mark.task("T05")
def test_admit_allows_up_to_max_workers_then_refuses(service: TokenService) -> None:
    claims = service.verify(service.issue(room="lab", max_workers=2, ttl=timedelta(days=30)))

    assert service.admit(claims) is True
    assert service.admit(claims) is True
    # Cap reached.
    assert service.admit(claims) is False


@pytest.mark.unit
@pytest.mark.task("T05")
def test_release_frees_a_slot(service: TokenService) -> None:
    claims = service.verify(service.issue(room="lab", max_workers=1, ttl=timedelta(days=30)))
    assert service.admit(claims) is True
    assert service.admit(claims) is False

    service.release(claims.jti)

    assert service.admit(claims) is True


@pytest.mark.unit
@pytest.mark.task("T05")
def test_unlimited_max_workers_never_refuses(service: TokenService) -> None:
    claims = service.verify(service.issue(room="lab", max_workers=None, ttl=timedelta(days=30)))

    for _ in range(50):
        assert service.admit(claims) is True


@pytest.mark.unit
@pytest.mark.task("T05")
def test_release_below_zero_is_safe(service: TokenService) -> None:
    claims = service.verify(service.issue(room="lab", max_workers=1, ttl=timedelta(days=30)))

    # Releasing a slot that was never taken must not let the count go negative.
    service.release(claims.jti)
    assert service.admit(claims) is True
    assert service.admit(claims) is False
