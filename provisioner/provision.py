from __future__ import annotations
import argparse
import asyncio.subprocess
import base64
import json
import pwd
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from pwd import struct_passwd
from typing import Protocol, Callable, AsyncIterator, TypeGuard

import typedload


ASSETS_DIR = Path("/tmp") / "provisioner"


@dataclass(frozen=True)
class UsersConfig:
    ignore: frozenset[str] = field(default_factory=frozenset)
    users: frozenset[User] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ProvisionerConfig:
    users: UsersConfig = field(default_factory=UsersConfig)


@dataclass
class CommandError(Exception):
    stdout: str | None
    stderr: str | None


async def run_command(
    cmd: list[str],
    err_f: Callable[[str], str] = lambda x: x,
    out_f: Callable[[str], str] = lambda x: x,
) -> tuple[int, str | None, str | None]:
    p = await asyncio.subprocess.create_subprocess_exec(
        cmd[0], *cmd[1:], stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    r = await p.wait()
    stderr = (
        err_f((await p.stderr.read()).decode("utf-8")) if p.stderr is not None else None
    )
    stdout = (
        out_f((await p.stdout.read()).decode("utf-8")) if p.stdout is not None else None
    )

    if r > 0:
        raise CommandError(
            stderr=stderr,
            stdout=stdout,
        )

    return r, stderr, stdout


async def write_authorized_keys(authorized_keys: Path, key: str) -> None:
    with authorized_keys.open("wb") as f:
        authorized_keys.parent.mkdir(parents=True, exist_ok=True)
        f.write(base64.b64decode(key))


@dataclass(frozen=True)
class User:
    name: str
    home: Path
    key: str | None

    async def write_authorized_keys(self) -> None:
        if self.key:
            await write_authorized_keys(self.authorized_keys, self.key)

    async def delete(self) -> None:
        await run_command(["/usr/sbin/userdel", "-r", self.name])

    async def create(self) -> None:
        await run_command(["/usr/sbin/useradd", "-m", "-U", "-G", "sudo", self.name])
        await self.write_authorized_keys()

    @property
    def authorized_keys(self) -> Path:
        return self.home / ".ssh" / "authorized_keys"


@dataclass
class FileInfo:
    source: Path
    dest: Path
    reload: str | None = None


@dataclass
class Step(Protocol):
    @property
    def __match_args__(self) -> tuple[str, ...]:
        return ("name",)

    @property
    def name(self) -> str: ...

    async def provision(self, apply: bool = False) -> None: ...

    async def deprovision(self, apply: bool = False) -> None: ...


def read_pub_key(p: Path) -> str | None:
    try:
        if (ssh_pub_key := (p / ".ssh" / "authorized_keys")).is_file():
            return base64.b64encode(ssh_pub_key.read_bytes()).decode("utf-8")
        return None
    except PermissionError:
        return None


def pw_entry_to_user(pw: pwd.struct_passwd) -> User:
    return User(pw.pw_name, Path(pw.pw_dir), read_pub_key(Path(pw.pw_dir)))


def manageable_users() -> frozenset[User]:
    return frozenset(
        map(
            pw_entry_to_user, filter(lambda s: 1000 <= s.pw_uid <= 2000, pwd.getpwall())
        )
    )


@dataclass(frozen=True)
class Users:
    users: frozenset[User] = field(default_factory=frozenset)
    name: str = "users"
    ignore_users: frozenset[str] = field(default_factory=frozenset)
    all_users: frozenset[User] | None = None

    async def provision(self, apply: bool = False) -> None:
        delete_users, add_users, update_users = self.state(
            Users(
                users=self.all_users
                if self.all_users is not None
                else manageable_users()
            )
        )
        for user in delete_users:
            if apply:
                await user.delete()
            else:
                print(f"Removing user {user.name}")

        for user in add_users:
            if apply:
                await user.create()
            else:
                print(f"Adding user {user.name}")

        for user in update_users:
            if apply:
                await user.write_authorized_keys()

    async def deprovision(self, apply: bool = False) -> None:
        current_users = set(map(lambda u: u.name, self.all_users or manageable_users()))
        for user in [user for user in self.users if user.name in current_users]:
            if apply:
                await user.delete()
            else:
                print(f"Removing user {user.name}")

    def state(self, all_users: "Users") -> tuple[set[User], set[User], set[User]]:
        """
        Return users to delete, create or update.

        Note that a modification here means changing the ssh_key
        """
        add_users = set()
        update_users = set()
        existing_users = set()
        all_users_dict = {s.name: s for s in all_users.users}
        for user in self.users:
            match all_users_dict.get(user.name):
                case User(
                    key=key,
                    home=home,
                ) if user.key != key or user.home != home:
                    update_users.add(
                        u_user := User(name=user.name, key=user.key, home=home)
                    )
                    all_users_dict[user.name] = u_user
                case User() as user:
                    existing_users.add(user)
                case None:
                    add_users.add(user)
        return (
            set(
                filter(
                    lambda u: u.name not in self.ignore_users,
                    (
                        set(all_users_dict.values())
                        - add_users.union(existing_users).union(update_users)
                    ),
                )
            ),
            add_users,
            update_users,
        )


@dataclass
class Provisioner:
    steps: list[Step]

    async def provision(self, step: str | None, apply: bool = False) -> None:
        for s in filter(lambda s: not step or s.name == step, self.steps):
            print(f"Provision step {s.name}")
            await s.provision(apply=apply)

    async def deprovision(self, step: str | None, apply: bool = False) -> None:
        for s in filter(lambda s: not step or s.name == step, self.steps):
            print(f"Deprovision step {s.name}")
            await s.deprovision(apply=apply)


@asynccontextmanager
async def create_provisioner(id: str, step: str) -> AsyncIterator[Provisioner]:
    try:
        match step:
            case "users":
                users_config = typedload.load(
                    json.loads(
                        base64.b64decode(
                            (ASSETS_DIR / id / "payload").read_bytes()
                        ).decode("utf-8")
                    )["data"],
                    UsersConfig,
                )
                yield Provisioner(
                    steps=[
                        Users(
                            users=users_config.users, ignore_users=users_config.ignore
                        )
                    ],
                )
            case step:
                raise ValueError(f"Unexpected step {step}")
    finally:
        pass


async def run(step: str, command: str, id: str, apply: bool) -> None:
    async with create_provisioner(id, step) as provisioner:
        match command:
            case "provision":
                await provisioner.provision(step=step, apply=apply)
            case "deprovision":
                await provisioner.deprovision(step=step, apply=apply)
            case command:
                raise Exception(f"Command unknown: {command}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("step")
    parser.add_argument("command")
    parser.add_argument("id")
    args = parser.parse_args()
    asyncio.run(run(args.step, args.command, args.id, args.apply))
