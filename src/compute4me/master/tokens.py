"""Invite Token service: issue / verify / revoke / admit / release.

Signs and verifies JWT-style Invite Tokens with a Master-held key, maintains the
in-memory revocation set and per-``jti`` live-Worker counter, and persists token metadata
via the state store. See ADR-0002 and docs/architecture/modules.md §Token service.

The signing key and the Master cert fingerprint are injected (the cert itself is generated
in T06); this keeps the service pure and unit-testable with a fixed key. Token metadata is
durable (via the state store) so revocations survive a restart; the live-Worker counters
are in-memory only (a fresh process starts every Worker re-joining anyway).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import jwt

from compute4me.types import TokenClaims

if TYPE_CHECKING:
    from compute4me.master.state import StateStore

_ALGORITHM = "HS256"


class InvalidToken(Exception):
    """Raised by ``verify`` for a bad signature, expired token, or revoked ``jti``."""


class TokenService:
    """Issues and verifies Invite Tokens and tracks live per-token Worker counts.

    ``signing_key`` is the Master-held secret the tokens are signed with; ``cert_fp`` is
    the sha256 fingerprint of the Master's self-signed cert, embedded in every token so a
    Worker can pin it (ADR-0011). Both are injected — T06 supplies the real cert-derived
    values; tests pass a fixed key.
    """

    def __init__(self, signing_key: str, cert_fp: str, store: StateStore) -> None:
        self._key = signing_key
        self._cert_fp = cert_fp
        self._store = store
        # Rebuild the revocation set from durable metadata so revocations survive restart.
        self._revoked: set[str] = store.load_revoked_jtis()
        # Live Worker count per jti — in-memory; rebuilt as Workers re-join after a restart.
        self._live: dict[str, int] = {}

    def issue(
        self,
        room: str,
        max_workers: int | None,
        ttl: timedelta,
        *,
        admin: bool = False,
    ) -> str:
        """Mint a signed token for ``room``; persists its metadata and returns the string."""
        now = datetime.now(UTC)
        expires = now + ttl
        jti = uuid.uuid4().hex
        claims = TokenClaims(
            jti=jti,
            room=room,
            max_workers=max_workers,
            expires_at=expires.isoformat(),
            master_cert_fp=self._cert_fp,
            admin=admin,
        )
        # Carry the model as the payload, plus the registered `exp`/`jti` claims so pyjwt
        # enforces expiry and we revoke by the standard id.
        payload = {**claims.model_dump(), "exp": expires, "jti": jti}
        token = jwt.encode(payload, self._key, algorithm=_ALGORITHM)
        # tokens.room_id REFERENCES rooms(id); ensure the Room exists before persisting the
        # token. The Master auto-creates the Room on `serve --room` (wire-protocol.md §4.10);
        # issuing for a room is idempotent here (id == name in v0.1's single-operator model).
        self._store.save_room(id=room, name=room, created_at=now.isoformat())
        self._store.save_token(
            jti=jti,
            room_id=room,
            max_workers=max_workers,
            expires_at=expires.isoformat(),
            created_at=now.isoformat(),
        )
        return token

    def verify(self, token: str) -> TokenClaims:
        """Decode and validate a token. Raises ``InvalidToken`` on any failure."""
        try:
            payload = jwt.decode(token, self._key, algorithms=[_ALGORITHM])
        except jwt.PyJWTError as exc:  # bad signature, expired, malformed
            raise InvalidToken(str(exc)) from exc
        if payload.get("jti") in self._revoked:
            raise InvalidToken("token revoked")
        # `exp` is a pyjwt-internal claim; TokenClaims keeps its own ISO `expires_at`.
        payload.pop("exp", None)
        return TokenClaims.model_validate(payload)

    def revoke(self, jti: str) -> None:
        """Revoke a token by ``jti``; durable and effective for all future ``verify`` calls."""
        self._revoked.add(jti)
        self._store.set_token_revoked(jti)

    def admit(self, claims: TokenClaims) -> bool:
        """Reserve a Worker slot for this token. True if under the cap, else False.

        ``max_workers=None`` means unlimited. On success the live count is incremented;
        the caller pairs each admit with a ``release`` when the Worker disconnects.
        """
        live = self._live.get(claims.jti, 0)
        if claims.max_workers is not None and live >= claims.max_workers:
            return False
        self._live[claims.jti] = live + 1
        return True

    def release(self, jti: str) -> None:
        """Free a Worker slot when a Worker disconnects (floors at zero)."""
        live = self._live.get(jti, 0)
        if live > 0:
            self._live[jti] = live - 1
