# Tests Index

Map of **T-task → test file(s) → markers**. Updated per PR — every new test gets an entry. Provides a quick "which tests cover T16?" lookup without grepping.

> _The first tests land with T01 (repo skeleton); subsequent T-tasks fill in the rest._

## Conventions

- Each row: T-ID → test file → comma-separated markers.
- A test file covering multiple T-tasks gets multiple rows (one per T-ID).
- Markers reference [CONTRIBUTING.md §Tests](../CONTRIBUTING.md#tests).

## Index (populated as tests are written)

| T-task | Test file | Markers |
|---|---|---|
| T01 | tests/unit/test_cli_surface.py | `task("T01")`, `unit` |
| T02 | tests/unit/test_types.py | `task("T02")`, `unit` |
| T03 | tests/unit/test_state.py | `task("T03")`, `unit` |
| T04 | tests/unit/test_messages.py | `task("T04")`, `unit` |
| T05 | tests/unit/test_tokens.py | `task("T05")`, `unit` |
| T06 | tests/unit/test_tls.py | `task("T06")`, `unit` |
| T07 | tests/integration/test_ws_server.py | `task("T07")`, `integration` |

<!-- Template row:
| T08 | tests/integration/test_daemon_join.py | `task("T08")`, `integration` |
-->
