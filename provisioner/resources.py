import asyncio
import base64
import enum
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any

__all__ = [
    "load_step",
    "run_command",
    "rm_tree",
]


ASSETS_DIR = Path("/tmp") / "provisioner"


@dataclass
class CommandError(Exception):
    stdout: str | None
    stderr: str | None


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


def load_step(id: str) -> tuple[Any]:
    return (
        json.loads(
            base64.b64decode((ASSETS_DIR / id / "payload").read_bytes()).decode("utf-8")
        )["data"],
    )


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


def rm_tree(path: Path) -> None:
    shutil.rmtree(str(path), ignore_errors=True)
