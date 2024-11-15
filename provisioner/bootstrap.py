import json
from dataclasses import dataclass, replace
from functools import cached_property
from pathlib import Path

import typedload

from provisioner.resources import ASSETS_DIR, run_command, rm_tree, load_step

__all__ = [
    "VenvConfig",
    "BootstrapConfig",
    "SSH_PROVISIONER_NAME",
]


SSH_PROVISIONER_NAME = "ssh-provisioner"


@dataclass(frozen=True)
class VEnv:
    id: str

    @property
    def path(self) -> Path:
        return ASSETS_DIR / self.id / "venv"

    @property
    def pip(self) -> Path:
        return self.path / "bin" / "pip"

    @property
    def python(self) -> Path:
        return self.path / "bin" / "python3"


@dataclass(frozen=True)
class VenvConfig:
    id: str
    ready: bool | None = False

    @cached_property
    def venv(self) -> VEnv:
        return VEnv(id=self.id)

    async def provision(self, apply: bool = False) -> None:
        if apply:
            await run_command(["/usr/bin/python3", "-m", "venv", str(self.venv.path)])

    async def deprovision(self, apply: bool = False) -> None:
        if apply:
            rm_tree(self.venv.path)

    async def refresh(self, _step_id: str, pre: bool) -> "VenvConfig":
        pre_venv = load_venv_config(self.id)
        if pre:
            return pre_venv
        try:
            await run_command([str(self.venv.python), "--version"])
            return replace(pre_venv, ready=True)
        except Exception as e:
            return pre_venv


def load_venv_config(id: str) -> VenvConfig:
    return typedload.load(load_step(id), VenvConfig)


def pip_is_installed(package: str, packages: list[dict[str, str]]) -> bool:
    return any(
        map(
            lambda p: p.get("name") == package,
            packages,
        )
    )


@dataclass(frozen=True)
class BootstrapConfig:
    id: str
    venv_resource_id: str
    whl: Path
    package_name: str = SSH_PROVISIONER_NAME
    installed: bool = False

    @cached_property
    def venv(self) -> VEnv:
        return VEnv(id=self.venv_resource_id)

    @property
    def whl_path(self) -> Path:
        return (
            ASSETS_DIR
            / self.id
            / (self.whl.relative_to("/") if self.whl.is_absolute() else self.whl)
        )

    async def provision(self, apply: bool = False) -> None:
        if apply:
            await run_command(
                [
                    str(self.venv.pip),
                    "install",
                    "--require-virtualenv",
                    "-y",
                    str(self.whl_path),
                ]
            )

    async def deprovision(self, apply: bool = False) -> None:
        if apply:
            await run_command(
                [
                    str(self.venv.pip),
                    "uninstall",
                    "--require-virtualenv",
                    "-y",
                    self.package_name or SSH_PROVISIONER_NAME,
                ]
            )
            rm_tree(ASSETS_DIR / self.id)

    async def refresh(self, step_id: str, pre: bool) -> "BootstrapConfig":
        boostrap_config = load_pre_bootstrap_config(step_id)
        if pre:
            return boostrap_config
        match await run_command(
            [
                str(self.venv.pip),
                "list",
                "--require-virtualenv",
                "--format",
                "json",
            ]
        ):
            case _, out, _ if out is not None:
                return replace(
                    boostrap_config,
                    installed=pip_is_installed(self.package_name, json.loads(out)),
                )
        return boostrap_config


def load_pre_bootstrap_config(id: str) -> BootstrapConfig:
    return typedload.load(load_step(id), BootstrapConfig)
