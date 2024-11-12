import argparse
import asyncio.subprocess
import base64
import enum
import functools
import json
import pwd
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from shutil import chown
from typing import Protocol, Callable, AsyncIterator, Any, Iterable, TypeGuard

import typedload


__all__ = [
    "Users",
    "load_users_config",
    "load_pre_users_config",
    "UsersDiff",
    "UsersConfig",
    "User",
]


ASSETS_DIR = Path("/tmp") / "provisioner"
SUDOERS_FILE = Path("/etc/sudoers.d") / "ssh-provisioner"


class ResourceStatus(enum.Enum):
    MISSING = 0
    PRESENT = 1
    OUTDATED = 2


class ResourceState:
    status: ResourceStatus


@dataclass
class ResourceMissing(ResourceState):
    status: ResourceStatus = ResourceStatus.MISSING


@dataclass
class ResourcePresent(ResourceState):
    status: ResourceStatus = ResourceStatus.PRESENT


@dataclass
class ResourceOutdated(ResourceState):
    fields: list[str]
    status: ResourceStatus = ResourceStatus.OUTDATED


@dataclass(frozen=True)
class User:
    name: str
    home: Path | None = None
    key: str | None = None
    sudo: bool = True

    @property
    def home_dir(self) -> Path:
        return self.home or Path("/home/") / self.name

    async def write_authorized_keys(self) -> None:
        if self.key:
            await write_authorized_keys(self.authorized_keys, self.key)
            chown(self.authorized_keys, user=self.name, group=self.name)

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

    @property
    def state(self) -> ResourceState:
        match manageable_user_dict().get(self.name):
            case None:
                return ResourceMissing()
            case User(
                key=key,
                sudo=sudo,
            ) if key == self.key and sudo == self.sudo:
                return ResourcePresent()
            case User(key=key, sudo=sudo):
                return ResourceOutdated(
                    fields=list(
                        filter(
                            None,
                            (
                                "key" if key != self.key else None,
                                "sudo" if self.sudo != sudo else None,
                            ),
                        )
                    )
                )


@dataclass(frozen=True)
class UsersConfig:
    ignore: frozenset[str] = field(default_factory=frozenset)
    users: frozenset[User] = field(default_factory=frozenset)


@dataclass(frozen=True)
class UsersDiff:
    users_final: frozenset[User] = field(default_factory=frozenset)
    users_to_add: frozenset[User] = field(default_factory=frozenset)
    users_to_delete: frozenset[User] = field(default_factory=frozenset)
    users_to_update: frozenset[User] = field(default_factory=frozenset)
    sudoers_final: frozenset[str] = field(default_factory=frozenset)
    sudoers_to_add: frozenset[str] = field(default_factory=frozenset)
    sudoers_to_delete: frozenset[str] = field(default_factory=frozenset)

    async def provision(self, apply: bool) -> None:
        print(f"Users to add: {[u.name for u in self.users_to_add]}")
        print(f"Users to delete: {[u.name for u in self.users_to_delete]}")
        print(f"Users to update: {[u.name for u in self.users_to_update]}")
        print(f"Sudoers to delete: {self.sudoers_to_delete}")
        print(f"Sudoers to add: {self.sudoers_to_delete}")

        for user in self.users_to_delete:
            print(f"Removing user {user.name}")
            if apply:
                await user.delete()

        for user in self.users_to_add:
            print(f"Adding user {user.name}")
            if apply:
                await user.create()

        for user in self.users_to_update:
            print(f"Modifying key user {user.name}")
            if apply:
                await user.write_authorized_keys()

        if self.sudoers_final:
            print(f"Adding users to sudoers: {','.join(self.sudoers_final)}")
            if apply:
                await write_sudoers_content(self.sudoers_final)
        else:
            print(f"No sudoer users found, removing sudoers file")
            if apply:
                SUDOERS_FILE.unlink()

    async def deprovision(self, apply: bool = False) -> None:
        for user in self.users_to_delete:
            print(f"Removing user {user.name}")
            if apply:
                await user.delete()


def load_pre_users_config(id: str) -> UsersConfig:
    return typedload.load(
        json.loads(
            base64.b64decode((ASSETS_DIR / id / "payload").read_bytes()).decode("utf-8")
        )["data"],
        UsersConfig,
    )


def load_users_config(
    id: str,
) -> UsersConfig:
    return UsersConfig(
        ignore=(pre := load_pre_users_config(id)).ignore,
        users=frozenset(
            filter(lambda u: u.state.status == ResourceStatus.PRESENT, pre.users),
        ),
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
        print(stderr)
        print(stdout)
        raise CommandError(
            stderr=stderr,
            stdout=stdout,
        )

    return r, stderr, stdout


async def write_authorized_keys(authorized_keys: Path, key: str) -> None:
    print("Creating", authorized_keys.parent)
    authorized_keys.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with authorized_keys.open("w") as f:
        f.write(base64.b64decode(key).decode("utf-8"))


async def write_sudoers_content(users: Iterable[str]) -> None:
    with SUDOERS_FILE.open("w") as f:
        f.write(
            "\n".join(list(map(lambda u: f"{u} ALL=(ALL:ALL) NOPASSWD:ALL", users)))
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
def manageable_user_dict() -> dict[str, User]:
    return {u.name: u for u in manageable_users()}


@dataclass(frozen=True)
class Users:
    id: str
    users: frozenset[User] = field(default_factory=frozenset)
    name: str = "users"
    ignore: frozenset[str] = field(default_factory=frozenset)
    all_users: frozenset[User] | None = None
    all_sudoers: frozenset[str] | None = None

    async def provision(self, apply: bool = False) -> None:
        """
        Provision this state so current state matches it.
        """
        await self.state(
            Users(
                self.id,
                users=self.all_users
                if self.all_users is not None
                else manageable_users(),
            )
        ).provision(apply=apply)

    async def deprovision(self, apply: bool = False) -> None:
        """
        Deprovision all the resources defined in this state
        """
        await UsersDiff(users_to_delete=self.users).provision(apply=apply)

    async def refresh(self, step_id: str, pre: bool) -> "Users":
        """
        Return the current state
        """
        pre_users_config = load_pre_users_config(step_id)
        if pre:
            return Users(
                id=self.id,
                users=pre_users_config.users,
                ignore=pre_users_config.ignore,
            )
        return Users(
            id=self.id,
            ignore=pre_users_config.ignore,
            users=frozenset(
                filter(
                    lambda u: u.state.status == ResourceStatus.PRESENT,
                    pre_users_config.users,
                ),
            ),
        )

    def state(self, current_state: "Users") -> UsersDiff:
        """
        Return the diff from the current state and the expected state.
        """
        add_users = set()
        update_users = set()
        existing_users = set()
        all_users_dict = {s.name: s for s in current_state.users}
        for user in self.users:
            match all_users_dict.get(user.name):
                case User(
                    key=key,
                    home=home,
                    sudo=sudo,
                ) if user.key != key or user.home_dir != home or user.sudo != sudo:
                    update_users.add(
                        u_user := User(
                            name=user.name,
                            key=user.key,
                            home=home or user.home_dir,
                            sudo=user.sudo,
                        )
                    )
                    all_users_dict[user.name] = u_user
                case User() as user:
                    existing_users.add(user)
                case None:
                    add_users.add(user)

        current_sudoers = (
            self.all_sudoers if self.all_sudoers is not None else users_in_sudoer_file()
        )
        expected_sudoers = frozenset(
            map(lambda u: u.name, filter(lambda u: u.sudo, self.users))
        )

        return UsersDiff(
            users_final=frozenset(self.users),
            users_to_delete=frozenset(
                filter(
                    lambda u: u.name not in self.ignore,
                    (
                        set(all_users_dict.values())
                        - add_users.union(existing_users).union(update_users)
                    ),
                )
            ),
            users_to_add=frozenset(add_users),
            users_to_update=frozenset(update_users),
            sudoers_final=expected_sudoers,
            sudoers_to_delete=current_sudoers.difference(expected_sudoers),
            sudoers_to_add=expected_sudoers.difference(current_sudoers),
        )


@dataclass
class Provisioner:
    step: Step

    async def provision(self, apply: bool = False) -> None:
        await self.step.provision(apply=apply)

    async def deprovision(self, apply: bool = False) -> None:
        await self.step.deprovision(apply=apply)

    async def refresh(self, step_id: str, pre: bool) -> None:
        print(
            json.dumps(
                typedload.dump(await self.step.refresh(step_id=step_id, pre=pre))
            )
        )


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
                    step=Users(
                        id=id, users=users_config.users, ignore=users_config.ignore
                    )
                )
            case step:
                raise ValueError(f"Unexpected step {step}")
    finally:
        pass


async def run(step: str, command: str, id: str, apply: bool, pre: bool) -> None:
    async with create_provisioner(id, step) as provisioner:
        match command:
            case "provision":
                await provisioner.provision(apply=apply)
            case "deprovision":
                await provisioner.deprovision(apply=apply)
            case "refresh":
                await provisioner.refresh(step_id=id, pre=pre)
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
