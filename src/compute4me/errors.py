"""Public exception hierarchy for the Compute4Me client.

Defines ``Compute4MeError`` and its subclasses (``ConnectionError``, ``AuthError``,
``SubmissionError``, ``JobFailedError``, ``TaskFailedError``, ``CancelledError``) per
docs/architecture/error-handling.md and wire-protocol.md §5.6. These map 1-to-1 to the
CLI exit codes.

Populated in T23.
"""

from __future__ import annotations
