"""Optional ``c4m`` SDK — pure sugar over the env-vars-in/files-out Container Contract.

Provides ``config()`` / ``input_dir()`` / ``output_dir()`` / ``report(...)`` /
``progress(...)`` so model code gets ergonomics when it wants them. Containers that prefer
``os.environ`` + raw file I/O work identically — no ``import compute4me`` is required. See
ADR-0006 and docs/architecture/wire-protocol.md §1.

Populated in T23.
"""

from __future__ import annotations
