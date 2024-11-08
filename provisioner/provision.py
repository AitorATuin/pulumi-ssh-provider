import argparse
import asyncio.subprocess
import base64
import enum
import functools
import json
import pwd
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from linecache import cache
from pathlib import Path
from typing import Protocol, Callable, AsyncIterator, Any

import typedload


__all__ = ["Users"]


ASSETS_DIR = Path("/tmp") / "provisioner"
SUDOERS_FILE = Path("/etc/sudoers.d") / "ssh-provisioner"


class ResourceState(enum.Enum):
    MISSING = 0
    PRESENT = 1
    OUTDATED = 2


@dataclass(frozen=True)
class User:
    name: str
    home: Path | None = None
    key: str | None = None
    sudo: bool = True

    @property
    def home_dir(self) -> Path:
        return self.home or Path("/home/") / self.name

    async def has_authorized_keys(self) -> None:
        if self.key:
            await write_authorized_keys(self.authorized_keys, self.key)

    async def write_authorized_keys(self) -> None:
        if self.key:
            await write_authorized_keys(self.authorized_keys, self.key)

    async def delete(self) -> None:
        await run_command(["/usr/sbin/userdel", "-r", self.name])

    async def create(self) -> None:
        await run_command(
            ["/usr/sbin/useradd", "-m", "-U"]
            + (["-G", "sudo"] if self.sudo else [])
            + [self.name]
        )
        await self.write_authorized_keys()

    @property
    def authorized_keys(self) -> Path:
        return self.home_dir / ".ssh" / "authorized_keys"

    def state(self) -> ResourceState:
        if self.name not in manageable_user_names():
            return ResourceState.MISSING
        if read_pub_key(self.authorized_keys) != self.key:
            return ResourceState.OUTDATED
        if (
            (b := self.name in users_in_sudoer_file())
            and not self.sudo
            or not b
            and self.sudo
        ):
            return ResourceState.OUTDATED
        return ResourceState.PRESENT


@dataclass(frozen=True)
class UsersConfig:
    ignore: frozenset[str] = field(default_factory=frozenset)
    users: frozenset[User] = field(default_factory=frozenset)
    delete: frozenset[User] | None = None


def load_pre_users_config(id: str) -> UsersConfig:
    return typedload.load(
        json.loads(
            base64.b64decode((ASSETS_DIR / id / "payload").read_bytes()).decode("utf-8")
        )["data"],
        UsersConfig,
    )


def load_users_config(id: str) -> UsersConfig:
    pre_users_config = load_pre_users_config(id)

    to_delete, to_add, to_update, to_sudoers = Users(
        users=pre_users_config.users, ignore_users=pre_users_config.ignore
    ).state(Users(users=manageable_users()))
    return UsersConfig(
        ignore=pre_users_config.ignore,
        users=frozenset(to_add.union(to_update).union(to_sudoers)),
        delete=frozenset(to_delete),
    )


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


async def write_sudoers_content(users: list[User]) -> None:
    with SUDOERS_FILE.open("w") as f:
        f.write(
            "\n".join(
                list(map(lambda u: f"{u.name} ALL=(ALL:ALL) NOPASSWD:ALL", users))
            )
            + "\n"
        )


class FileInfo:
    source: Path
    dest: Path
    reload: str | None = None


@dataclass
class Step[R](Protocol):
    @property
    def __match_args__(self) -> tuple[str, ...]:
        return ("name",)

    @property
    def name(self) -> str: ...

    async def provision(self, apply: bool = False) -> None: ...

    async def deprovision(self, apply: bool = False) -> None: ...

    async def refresh(self, step_id: str, pre: bool) -> R: ...


def read_pub_key(p: Path) -> str | None:
    try:
        if (ssh_pub_key := (p / ".ssh" / "authorized_keys")).is_file():
            return base64.b64encode(ssh_pub_key.read_bytes()).decode("utf-8")
        return None
    except PermissionError:
        return None


@functools.cache
def users_in_sudoer_file() -> frozenset[str]:
    try:
        with SUDOERS_FILE.open("r") as f:
            return frozenset(map(lambda s: s.split(" ")[0], f.readlines()))
    except FileNotFoundError:
        return frozenset()


def in_sudoer_file(user: str) -> bool:
    return user in users_in_sudoer_file()


def pw_entry_to_user(pw: pwd.struct_passwd) -> User:
    return User(
        name=pw.pw_name,
        home=Path(pw.pw_dir),
        key=read_pub_key(Path(pw.pw_dir)),
        sudo=in_sudoer_file(pw.pw_name),
    )


@functools.cache
def manageable_users() -> frozenset[User]:
    return frozenset(
        map(
            pw_entry_to_user, filter(lambda s: 1000 <= s.pw_uid <= 2000, pwd.getpwall())
        )
    )


@functools.cache
def manageable_user_names() -> frozenset[str]:
    return frozenset(map(lambda u: u.name, manageable_users()))


@dataclass(frozen=True)
class Users:
    users: frozenset[User] = field(default_factory=frozenset)
    name: str = "users"
    ignore_users: frozenset[str] = field(default_factory=frozenset)
    all_users: frozenset[User] | None = None
    delete_users: frozenset[User] | None = None

    async def provision(self, apply: bool = False) -> None:
        delete_users, add_users, update_users, sudo_users = self.state(
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

        if sudo_users and apply:
            await write_sudoers_content(sudo_users)

        elif sudo_users:
            print(f"Adding users to sudoers: {','.join([u.name for u in sudo_users])}")

    async def deprovision(self, apply: bool = False) -> None:
        current_users = set(map(lambda u: u.name, self.all_users or manageable_users()))
        for user in [user for user in self.users if user.name in current_users]:
            if apply:
                await user.delete()
            else:
                print(f"Removing user {user.name}")

    async def refresh(self, step_id: str, pre: bool) -> "Users":
        if pre:
            users_config = load_pre_users_config(step_id)
            return Users(
                users=users_config.users,
                ignore_users=users_config.ignore,
            )
        else:
            users_config = load_users_config(step_id)
            return Users(
                ignore_users=users_config.ignore,
                users=users_config.users,
                delete_users=users_config.delete,
            )

    def state(
        self, all_users: "Users"
    ) -> tuple[set[User], set[User], set[User], list[User]]:
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
            sorted(
                list(filter(lambda u: u.sudo, add_users.union(update_users))),
                key=lambda u: u.name,
            ),
        )


@dataclass
class Provisioner:
    steps: list[Step]

    async def provision(self, step: str | None, apply: bool = False) -> None:
        for s in filter(lambda s: not step or s.name == step, self.steps):
            await s.provision(apply=apply)

    async def deprovision(self, step: str | None, apply: bool = False) -> None:
        for s in filter(lambda s: not step or s.name == step, self.steps):
            await s.deprovision(apply=apply)

    async def refresh(self, step: str | None, step_id: str, pre: bool) -> None:
        xs = []
        for s in filter(lambda s: not step or s.name == step, self.steps):
            xs.append(await s.refresh(step_id=step_id, pre=pre))
        print(typedload.dump(xs))


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


async def run(step: str, command: str, id: str, apply: bool, pre: bool) -> None:
    async with create_provisioner(id, step) as provisioner:
        match command:
            case "provision":
                await provisioner.provision(step=step, apply=apply)
            case "deprovision":
                await provisioner.deprovision(step=step, apply=apply)
            case "refresh":
                await provisioner.refresh(step=step, step_id=id, pre=pre)
            case command:
                raise Exception(f"Command unknown: {command}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--pre", action="store_true")
    parser.add_argument("step")
    parser.add_argument("command")
    parser.add_argument("id")
    args = parser.parse_args()
    asyncio.run(run(args.step, args.command, args.id, args.apply, args.pre))
