import argparse
import asyncio.subprocess
import base64
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol, AsyncIterator

import typedload

from provisioner.users import users_step

__all__ = [
    "Provisioner",
]


@dataclass
class Step[R](Protocol):
    @property
    def __match_args__(self) -> tuple[str, ...]:
        return ("name",)

    @property
    def name(self) -> str: ...

    async def provision(self, apply: bool = False) -> None: ...

    async def deprovision(self, apply: bool = False) -> None: ...

    async def refresh(self, step_id: str, pre: bool, apply: bool = True) -> R: ...


@dataclass
class Provisioner:
    step: Step

    async def provision(self, apply: bool = False) -> None:
        await self.step.provision(apply=apply)

    async def deprovision(self, apply: bool = False) -> None:
        await self.step.deprovision(apply=apply)

    async def refresh(self, step_id: str, pre: bool, apply: bool = True) -> None:
        print(
            json.dumps(
                typedload.dump(
                    await self.step.refresh(step_id=step_id, pre=pre, apply=apply)
                ),
            )
        )


@asynccontextmanager
async def create_provisioner(id: str, step: str) -> AsyncIterator[Provisioner]:
    try:
        match step:
            case "users":
                yield Provisioner(step=users_step(id))
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
                await provisioner.refresh(step_id=id, pre=pre, apply=apply)
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
