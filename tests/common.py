import contextlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from unittest.mock import patch, MagicMock


__all__ = [
    "mock_commands",
    "MockCommands",
]


@dataclass
class MockCommands:
    write_authorized_keys: MagicMock
    run_command: MagicMock


@contextlib.contextmanager
def mock_commands(
    run_commands: dict[str, tuple[int, str, str]] | None = None,
) -> MockCommands:
    with patch("provisioner.provision.run_command") as run_command, patch(
        "provisioner.provision.write_authorized_keys"
    ) as write_authorized_keys:
        try:
            m = MockCommands(
                run_command=run_command,
                write_authorized_keys=write_authorized_keys,
            )

            def _run_command(
                cmd: list[str],
                err_f: Callable[[str], str] | None = None,
                out_f: Callable[[str], str] | None = None,
            ) -> tuple[int, str, str]:
                if (s := " ".join(cmd)) in (run_commands or {}):
                    p, e, o = run_commands[s]
                    return p, err_f(e) if err_f else e, out_f(o) if out_f else o

            if run_commands:
                run_command.side_effect = _run_command

            yield m
        finally:
            pass


@contextlib.contextmanager
def local_files(files: list[tuple[str, str]]) -> list[Path]:
    dir = Path(tempfile.TemporaryDirectory().name)
    dir.mkdir(exist_ok=True)
    try:
        for file, content in files:
            with (dir / file).open("w") as f:
                f.write(content)

        yield [dir / f[0] for f in files]
    finally:
        shutil.rmtree(dir)
