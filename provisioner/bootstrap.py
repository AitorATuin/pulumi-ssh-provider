import json
import shutil
from dataclasses import dataclass, replace
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
class VenvConfig:
    id: str
    ready: bool | None = False

    @property
    def venv_path(self) -> Path:
        return ASSETS_DIR / self.id / "venv"

    @property
    def pip_path(self) -> Path:
        return self.venv_path / "bin" / "pip"

    @property
    def python_path(self) -> Path:
        return self.venv_path / "bin" / "python3"

    async def provision(self, apply: bool = False) -> None:
        if apply:
            await run_command(["/usr/bin/python3", "-m", "venv", str(self.venv_path)])

    async def deprovision(self, apply: bool = False) -> None:
        if apply:
            rm_tree(self.venv_path)

    async def refresh(self, _step_id: str, pre: bool) -> "VenvConfig":
        pre_venv = load_venv_config(self.id)
        if pre:
            return pre_venv
        try:
            await run_command([str(self.python_path), "--version"])
            return replace(pre_venv, ready=True)
        except Exception:
            return pre_venv


def load_venv_config(id: str) -> VenvConfig:
    return typedload.load(load_step(id), VenvConfig)


@dataclass
class BootstrapConfig:
    id: str
    venv_path: Path
    provisioner_path: Path
    installed: bool = False

    async def provision(self, apply: bool = False) -> None:
        await run_command(
            [
                str(self.venv_path / "bin" / "pip"),
                "install",
                "--require-virtualenv",
                "-y",
                str(self.provisioner_path),
            ]
        )

    async def deprovision(self, apply: bool = False) -> None:
        shutil.rmtree(ASSETS_DIR / self.id)
        await run_command(
            [
                str(self.venv_path / "bin" / "pip"),
                "uninstall",
                "--require-virtualenv",
                "-y",
                SSH_PROVISIONER_NAME,
            ]
        )

    async def refresh(self, step_id: str, pre: bool) -> "BootstrapConfig":
        boostrap_config = load_bootstrap_config(step_id)
        if pre:
            return load_bootstrap_config(step_id)
        match await run_command(
            [
                str(self.venv_path / "bin" / "pip"),
                "list",
                "--require-virtualenv",
                "--format",
                "json",
            ]
        ):
            case _, out, _ if out is not None:
                return replace(
                    boostrap_config,
                    installed=any(
                        map(
                            lambda p: p.get("name") == SSH_PROVISIONER_NAME,
                            json.loads(out),
                        )
                    ),
                )
        return boostrap_config


def load_bootstrap_config(id: str) -> BootstrapConfig:
    return typedload.load(load_step(id), BootstrapConfig)
