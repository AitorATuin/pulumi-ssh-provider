import contextlib
import itertools
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator
from unittest.mock import patch, MagicMock

from provisioner.users import UsersConfig, User, manageable_user_dict


__all__ = [
    "mock_commands",
    "MockCommands",
]


@dataclass
class MockCommands:
    write_authorized_keys: MagicMock
    run_command: MagicMock
    chown: MagicMock
    manageable_users: MagicMock
    users_in_sudoer_file: MagicMock
    load_pre_users_config: MagicMock


@contextlib.contextmanager
def mock_commands(
    run_commands: dict[str, tuple[int, str, str]] | None = None,
    users_in_sudoer: frozenset[str] | None = None,
    manageable_users: frozenset[User] | None = None,
    pre_users_config: UsersConfig | None = None,
    pub_keys: dict[str, str] | None = None,
) -> Iterator[MockCommands]:
    with patch("provisioner.users.run_command") as run_command, patch(
        "provisioner.users.write_authorized_keys"
    ) as write_authorized_keys, patch("provisioner.users.write_sudoers_content"), patch(
        "provisioner.users.chown"
    ) as chown, patch(
        "provisioner.users.users_in_sudoer_file"
    ) as users_in_sudoer_file, patch(
        "provisioner.users.manageable_users"
    ) as manageable_users_f, patch(
        "provisioner.users.load_pre_users_config"
    ) as load_pre_users_config, patch("provisioner.users.read_pub_key") as read_pub_key:
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

            if run_commands:
                run_command.side_effect = _run_command
            users_in_sudoer_file.return_value = (
                users_in_sudoer if users_in_sudoer else frozenset()
            )
            manageable_users_f.return_value = (
                manageable_users if manageable_users else frozenset()
            )
            load_pre_users_config.return_value = (
                pre_users_config if pre_users_config else UsersConfig()
            )
            read_pub_key.side_effect = _read_pub_key

            yield MockCommands(
                run_command=run_command,
                write_authorized_keys=write_authorized_keys,
                chown=chown,
                users_in_sudoer_file=users_in_sudoer_file,
                manageable_users=manageable_users_f,
                load_pre_users_config=load_pre_users_config,
            )
        finally:
            manageable_users_f.cache_clear()
            manageable_user_dict.cache_clear()


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
