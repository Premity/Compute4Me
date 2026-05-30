"""Test doubles — FakeWorker, fake hardware probes, fake container runner.

These let the integration/E2E suite run on GitHub-hosted CI without a real GPU or Docker.
Populated as the modules they fake come online (T08/T09/T17).
"""

from __future__ import annotations
