"""T01 acceptance: ``compute4me --help`` lists the wire-protocol §4.1 command surface."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from compute4me.cli import app

runner = CliRunner()


@pytest.mark.unit
@pytest.mark.task("T01")
def test_help_lists_the_wire_protocol_command_surface() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    expected = [
        "serve",
        "worker",
        "token",
        "status",
        "progress",
        "logs",
        "events",
        "fetch",
        "jobs",
        "cancel",
    ]
    for command in expected:
        assert command in result.output


@pytest.mark.unit
@pytest.mark.task("T01")
def test_version_prints_package_version() -> None:
    from compute4me import __version__

    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert __version__ in result.output
