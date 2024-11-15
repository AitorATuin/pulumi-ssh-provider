import contextlib
import itertools
import shutil
import tempfile
from dataclasses import dataclass
from functools import _lru_cache_wrapper
from pathlib import Path
from typing import Callable, Iterator
from unittest.mock import patch, MagicMock

from provisioner.bootstrap import VenvConfig
from provisioner.users import UsersConfig, User


__all__ = [
    "mock_commands",
    "MockCommands",
]


@dataclass
class MockCommands:
    write_authorized_keys: MagicMock
    write_sudoers_content: MagicMock
    run_command: MagicMock
    chown: MagicMock
    manageable_users: MagicMock
    users_in_sudoer_file: MagicMock
    load_pre_users_config: MagicMock
    read_pub_key: MagicMock
    rm_tree: MagicMock
    load_venv_config: MagicMock


SIDE_EFFECT_MOCKS = [
    "provisioner.{}.run_command",
    "provisioner.{}.write_authorized_keys",
    "provisioner.{}.write_sudoers_content",
    "provisioner.{}.users_in_sudoer_file",
    "provisioner.{}.chown",
    "provisioner.{}.manageable_users",
    "provisioner.{}.load_pre_users_config",
    "provisioner.{}.read_pub_key",
    "provisioner.{}.rm_tree",
    "provisioner.{}.load_venv_config",
]


@contextlib.contextmanager
def mock_commands(
    module: str,
    run_commands: dict[str, tuple[int, str, str]] | None = None,
    users_in_sudoer: frozenset[str] | None = None,
    manageable_users: frozenset[User] | None = None,
    pre_users_config: UsersConfig | None = None,
    pre_venv_config: VenvConfig | None = None,
    pub_keys: dict[str, str] | None = None,
    reset_cache: list[_lru_cache_wrapper] | None = None,
) -> Iterator[MockCommands]:
    def _make_mock(module: str) -> tuple[str, MagicMock]:
        m = module.split(".")[-1]
        try:
            return m, patch(module).start()
        except AttributeError:
            return m, MagicMock()

    patches = {
        k: v for k, v in map(_make_mock, (s.format(module) for s in SIDE_EFFECT_MOCKS))
    }
    mock_command = MockCommands(**patches)

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

        def _read_pub_key(p: Path) -> str:
            match (
                next(
                    itertools.dropwhile(
                        lambda t: str(p).startswith(t[0]),
                        (pub_keys or {}).items(),
                    ),
                    None,
                ),
                p.parts,
            ):
                case None, ["/", "home", user]:
                    return f"{user}-some-key"
                case None, [user]:
                    return f"{user}-some-key"
                case (_, key), _:
                    return key
            return "unknown"

        if run_commands and mock_command.run_command:
            mock_command.run_command.side_effect = _run_command
        if mock_command.users_in_sudoer_file:
            mock_command.users_in_sudoer_file.return_value = (
                users_in_sudoer if users_in_sudoer else frozenset()
            )
        if mock_command.manageable_users:
            mock_command.manageable_users.return_value = (
                manageable_users if manageable_users else frozenset()
            )
        if mock_command.load_pre_users_config:
            mock_command.load_pre_users_config.return_value = (
                pre_users_config if pre_users_config else UsersConfig()
            )
        if mock_command.read_pub_key:
            mock_command.read_pub_key.side_effect = _read_pub_key
        if mock_command.load_venv_config:
            mock_command.load_venv_config.return_value = (
                pre_venv_config if pre_venv_config else VenvConfig(id="test-resource")
            )
        yield mock_command
    finally:
        for p in patches.values():
            p.stop()
        for f in reset_cache or []:
            f.cache_clear()
        if mock_command.manageable_users:
            mock_command.manageable_users.cache_clear()


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
