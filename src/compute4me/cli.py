"""Operator + researcher command-line surface for the ``compute4me`` binary.

Implements the CLI defined in docs/architecture/wire-protocol.md §4 and ADR-0013: the
mode commands (``serve``, ``worker``), the ``token`` group, the five-command
observability split (``status``, ``progress``, ``logs``, ``events``, ``fetch``), Job
lifecycle (``jobs``, ``cancel``), and ``version``/``help``.

T01 establishes the command surface as a scaffold so ``compute4me --help`` lists every
command; each command's behavior is filled in by its owning T-task (T22, T24).
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="compute4me",
    help="Docker-native distributed deep-learning fabric.",
    no_args_is_help=True,
    add_completion=False,
)

token_app = typer.Typer(help="Manage Invite Tokens for a Room.", no_args_is_help=True)
app.add_typer(token_app, name="token")


@app.command()
def serve() -> None:
    """Run a Master: open a Room and accept Worker joins (foreground by default)."""
    raise NotImplementedError("serve lands in T22 (see docs/prd.md §8).")


@app.command()
def worker() -> None:
    """Run a Worker: join a Room with an Invite Token and execute Tasks."""
    raise NotImplementedError("worker lands in T22 (see docs/prd.md §8).")


@token_app.command("issue")
def token_issue() -> None:
    """Issue an Invite Token for a Room (--admin for submission rights)."""
    raise NotImplementedError("token issue lands in T22 (see docs/prd.md §8).")


@token_app.command("revoke")
def token_revoke() -> None:
    """Revoke an Invite Token by its jti."""
    raise NotImplementedError("token revoke lands in T22 (see docs/prd.md §8).")


@token_app.command("list")
def token_list() -> None:
    """List issued Invite Tokens."""
    raise NotImplementedError("token list lands in T22 (see docs/prd.md §8).")


@app.command()
def status() -> None:
    """Show fleet topology and Job progress (--watch for live refresh)."""
    raise NotImplementedError("status lands in T24 (see docs/prd.md §8).")


@app.command()
def progress() -> None:
    """Stream live per-trial metrics from a Job's progress.jsonl."""
    raise NotImplementedError("progress lands in T24 (see docs/prd.md §8).")


@app.command()
def logs() -> None:
    """Stream stdout/stderr from the Master, a Worker, a Task, or a Job."""
    raise NotImplementedError("logs lands in T24 (see docs/prd.md §8).")


@app.command()
def events() -> None:
    """Stream system-level transitions (joined, assigned, completed, failed)."""
    raise NotImplementedError("events lands in T24 (see docs/prd.md §8).")


@app.command()
def fetch() -> None:
    """Download a Job's result Artifacts to a local directory."""
    raise NotImplementedError("fetch lands in T24 (see docs/prd.md §8).")


@app.command()
def jobs() -> None:
    """List Jobs in a Room."""
    raise NotImplementedError("jobs lands in T22 (see docs/prd.md §8).")


@app.command()
def cancel() -> None:
    """Cancel a running Job (prompts unless --yes)."""
    raise NotImplementedError("cancel lands in T22 (see docs/prd.md §8).")


@app.command()
def version() -> None:
    """Print the Compute4Me version."""
    from compute4me import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
