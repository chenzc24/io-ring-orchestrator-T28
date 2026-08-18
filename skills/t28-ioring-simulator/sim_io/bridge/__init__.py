"""Virtuoso bridge text-upload helpers for the t28-ioring-simulator.

Issue #3: the previous implementation uploaded remote files with

    mkdir -p /tmp && chmod 755 /tmp && cat > /tmp/sim_io_spectre_setup.csh

Regular users cannot ``chmod /tmp`` on shared EDA machines, so the whole
command failed with ``Operation not permitted`` and the ``cat`` step was
never executed.  Callers that ignored ``CommandResult.returncode`` then
mistook the failed upload for a success and the Spectre flow only failed
much later at the ``test -s`` stage.

This module provides the corrected behavior:

* the remote command only creates the target's parent directory with
  ``mkdir -p`` -- it never runs ``chmod`` on pre-existing system
  directories such as ``/tmp``;
* the upload is validated against the SSH ``returncode`` and raises
  :class:`BridgeError` on failure, so a failed upload can no longer be
  mistaken for a successful one.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from typing import Any

__all__ = ["BridgeError", "CommandResult", "build_upload_command", "upload_text"]


class BridgeError(RuntimeError):
    """A remote bridge command did not complete successfully."""


@dataclass
class CommandResult:
    """Result of one remote command execution."""

    command: str
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        """True when the remote command exited with status 0."""
        return self.returncode == 0


def build_upload_command(remote_path: str) -> str:
    """Return the remote shell command used to upload a text file.

    Only the missing sub-directories of ``remote_path`` are created
    (``mkdir -p``).  The parent directory is never ``chmod``-ed, so
    uploads to world-writable system paths such as ``/tmp`` work for
    regular users.  Steps are chained with ``&&`` so a denied ``mkdir``
    prevents the write and is reported through ``returncode``.
    """
    parent = os.path.dirname(remote_path)
    quoted_path = shlex.quote(remote_path)
    if not parent:
        return "cat > {0}".format(quoted_path)
    return "mkdir -p {0} && cat > {1}".format(shlex.quote(parent), quoted_path)


def upload_text(runner: Any, remote_path: str, text: str) -> CommandResult:
    """Upload ``text`` to ``remote_path`` on the bridge host.

    The remote command is exactly::

        mkdir -p <parent> && cat > <remote_path>

    (no ``chmod`` on the parent directory -- see issue #3).  ``text`` is
    piped through the SSH channel stdin.

    Args:
        runner: transport exposing ``run(command, stdin=...)`` or
            ``exec(command, stdin=...)`` (typically the
            ``virtuoso_bridge`` SSH client) that returns a
            :class:`CommandResult` or an object with ``returncode``,
            ``stdout`` and ``stderr`` attributes.
        remote_path: remote file path, e.g.
            ``/tmp/sim_io_spectre_setup.csh``.
        text: file content to write.

    Raises:
        BridgeError: when ``remote_path`` is empty, when the runner
            cannot be invoked, or when the remote command exits with a
            non-zero ``returncode`` (including a denied parent ``mkdir``).
            A returned :class:`CommandResult` always has
            ``returncode == 0``.
    """
    if not remote_path:
        raise BridgeError("upload_text: remote_path must not be empty")

    try:
        runner_fn = runner.run if hasattr(runner, "run") else runner.exec
    except AttributeError:
        runner_fn = runner
    if not callable(runner_fn):
        raise BridgeError(
            "upload_text: runner must expose run()/exec() or be callable"
        )

    command = build_upload_command(remote_path)
    result = runner_fn(command, stdin=text)

    if not isinstance(result, CommandResult):
        raw_rc = getattr(result, "returncode", None)
        result = CommandResult(
            command=command,
            returncode=1 if raw_rc is None else int(raw_rc),
            stdout=str(getattr(result, "stdout", "") or ""),
            stderr=str(getattr(result, "stderr", "") or ""),
        )

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no output").strip()
        raise BridgeError(
            "upload_text failed for {0!r} (returncode={1}): {2}".format(
                remote_path, result.returncode, detail
            )
        )
    return result
