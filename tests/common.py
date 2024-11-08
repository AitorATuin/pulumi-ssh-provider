import contextlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator
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
) -> Iterator[MockCommands]:
    with patch("provisioner.provision.run_command") as run_command, patch(
        "provisioner.provision.write_authorized_keys"
    ) as write_authorized_keys, patch("provisioner.provision.write_sudoers_content"):
        try:

            def _run_command(
                cmd: list[str],
                err_f: Callable[[str], str] | None = None,
                out_f: Callable[[str], str] | None = None,
            ) -> tuple[int, str | None, str | None]:
                match (run_commands or {}).get(" ".join(cmd), None):
                    case None:
                        return 1, None, None
                    case p, e, o:
                        return p, err_f(e) if err_f else e, out_f(o) if out_f else o
                return 1, None, None

            if run_commands:
                run_command.side_effect = _run_command

            yield MockCommands(
                run_command=run_command,
                write_authorized_keys=write_authorized_keys,
            )
        finally:
            pass


@contextlib.contextmanager
def local_files(files: list[tuple[str, str]]) -> Iterator[list[Path]]:
    dir = Path(tempfile.TemporaryDirectory().name)
    dir.mkdir(exist_ok=True)
    try:
        for file, content in files:
            with (dir / file).open("w") as f:
                f.write(content)

        yield [dir / f[0] for f in files]
    finally:
        shutil.rmtree(dir)
