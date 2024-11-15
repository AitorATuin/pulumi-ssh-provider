import json
from functools import partial
from pathlib import Path
from unittest.mock import call, patch

from provisioner.bootstrap import (
    VenvConfig,
    load_venv_config,
    BootstrapConfig,
    pip_is_installed,
)
from provisioner.resources import run_command
from tests.common import mock_commands


bootstrap_mock_commands = partial(mock_commands, module="bootstrap")


def test_pip_is_installed() -> None:
    assert pip_is_installed("ssh-provisioner", []) is False

    assert (
        pip_is_installed(
            "ssh-provisioner",
            [
                {"name": "package-a", "version": "6.6.6"},
                {"name": "package-b", "version": "6.6.6"},
            ],
        )
        is False
    )

    assert (
        pip_is_installed(
            "ssh-provisioner",
            [
                {"name": "ssh-provisioner", "version": "6.6.6"},
                {"name": "package-a", "version": "6.6.6"},
                {"name": "package-b", "version": "6.6.6"},
            ],
        )
        is True
    )

    assert (
        pip_is_installed(
            "ssh-provisioner",
            [
                {"name": "package-a", "version": "6.6.6"},
                {"name": "package-b", "version": "6.6.6"},
                {"name": "ssh-provisioner", "version": "6.6.6"},
            ],
        )
        is True
    )

    assert (
        pip_is_installed(
            "ssh-provisioner",
            [
                {"name": "package-a", "version": "6.6.6"},
                {"name": "ssh-provisioner", "version": "6.6.6"},
                {"name": "package-b", "version": "6.6.6"},
            ],
        )
        is True
    )


async def test_venv_config_provision_0() -> None:
    with bootstrap_mock_commands() as cmd:
        await VenvConfig(
            id="test-resource",
        ).provision(apply=True)
        assert cmd.run_command.call_args_list == [
            call(
                [
                    "/usr/bin/python3",
                    "-m",
                    "venv",
                    "/tmp/provisioner/test-resource/venv",
                ]
            ),
        ]


async def test_venv_config_deprovision_0() -> None:
    with bootstrap_mock_commands() as cmd:
        await VenvConfig(
            id="test-resource",
        ).deprovision(apply=True)
        assert cmd.rm_tree.call_args_list == [
            call(Path("/tmp/provisioner/test-resource/venv"))
        ]


async def test_venv_config_refresh_0() -> None:
    with bootstrap_mock_commands(
        pre_venv_config=VenvConfig(id="test-resource", ready=False),
    ) as cmd:
        assert await VenvConfig(
            id="test-resource",
        ).refresh(_step_id="test-resource", pre=False) == VenvConfig(
            id="test-resource",
            ready=True,
        )
        assert cmd.run_command.call_args_list == [
            call(["/tmp/provisioner/test-resource/venv/bin/python3", "--version"]),
        ]


async def test_venv_config_refresh_1() -> None:
    with bootstrap_mock_commands(
        pre_venv_config=VenvConfig(id="test-resource", ready=False),
    ) as cmd:
        assert await VenvConfig(
            id="test-resource",
        ).refresh(_step_id="test-resource", pre=True) == VenvConfig(
            id="test-resource",
            ready=False,
        )
        assert cmd.run_command.call_args_list == []


async def test_venv_config_refresh_2() -> None:
    with bootstrap_mock_commands(
        pre_venv_config=VenvConfig(id="test-resource", ready=True),
    ) as cmd:
        assert await VenvConfig(
            id="test-resource",
        ).refresh(_step_id="test-resource", pre=True) == VenvConfig(
            id="test-resource",
            ready=True,
        )
        assert cmd.run_command.call_args_list == []


async def test_bootstrap_config_provision_0() -> None:
    with bootstrap_mock_commands() as cmd:
        await BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("ssh-provisioner.whl"),
        ).provision(apply=True)
        assert cmd.run_command.call_args_list == [
            call(
                [
                    "/tmp/provisioner/test-resource-1/venv/bin/pip",
                    "install",
                    "--require-virtualenv",
                    "-y",
                    "/tmp/provisioner/test-resource-2/ssh-provisioner.whl",
                ]
            ),
        ]


async def test_bootstrap_config_provision_1() -> None:
    with bootstrap_mock_commands() as cmd:
        await BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("something-else.whl"),
        ).provision(apply=True)
        assert cmd.run_command.call_args_list == [
            call(
                [
                    "/tmp/provisioner/test-resource-1/venv/bin/pip",
                    "install",
                    "--require-virtualenv",
                    "-y",
                    "/tmp/provisioner/test-resource-2/something-else.whl",
                ]
            ),
        ]


async def test_bootstrap_config_provision_2() -> None:
    with bootstrap_mock_commands() as cmd:
        await BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("complex/path/without/leading/slash.whl"),
        ).provision(apply=True)
        assert cmd.run_command.call_args_list == [
            call(
                [
                    "/tmp/provisioner/test-resource-1/venv/bin/pip",
                    "install",
                    "--require-virtualenv",
                    "-y",
                    "/tmp/provisioner/test-resource-2/complex/path/without/leading/slash.whl",
                ]
            ),
        ]


async def test_bootstrap_config_provision_3() -> None:
    with bootstrap_mock_commands() as cmd:
        await BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("/complex/path/with/leading/slash.whl"),
        ).provision(apply=True)
        assert cmd.run_command.call_args_list == [
            call(
                [
                    "/tmp/provisioner/test-resource-1/venv/bin/pip",
                    "install",
                    "--require-virtualenv",
                    "-y",
                    "/tmp/provisioner/test-resource-2/complex/path/with/leading/slash.whl",
                ]
            ),
        ]


async def test_bootstrap_config_deprovision_0() -> None:
    with bootstrap_mock_commands() as cmd:
        await BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("ssh-provisioner.whl"),
        ).deprovision(apply=True)
        assert cmd.run_command.call_args_list == [
            call(
                [
                    "/tmp/provisioner/test-resource-1/venv/bin/pip",
                    "uninstall",
                    "--require-virtualenv",
                    "-y",
                    "ssh-provisioner",
                ]
            ),
        ]


async def test_bootstrap_config_deprovision_1() -> None:
    with bootstrap_mock_commands() as cmd:
        await BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("ssh-provisioner.whl"),
            package_name="new-ssh-provisioner",
        ).deprovision(apply=True)
        assert cmd.run_command.call_args_list == [
            call(
                [
                    "/tmp/provisioner/test-resource-1/venv/bin/pip",
                    "uninstall",
                    "--require-virtualenv",
                    "-y",
                    "new-ssh-provisioner",
                ]
            ),
        ]


async def test_bootstrap_config_refresh_0() -> None:
    with bootstrap_mock_commands(
        pre_bootstrap_config=BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("ssh-provisioner.whl"),
            package_name="ssh-provisioner",
        )
    ) as cmd:
        assert await BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("ssh-provisioner.whl"),
            package_name="new-ssh-provisioner",
        ).refresh(step_id="test-resource-2", pre=True) == BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("ssh-provisioner.whl"),
            package_name="ssh-provisioner",
        )
        assert cmd.load_pre_bootstrap_config.call_count == 1


async def test_bootstrap_config_refresh_1() -> None:
    with bootstrap_mock_commands(
        pre_bootstrap_config=BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("ssh-provisioner.whl"),
            package_name="ssh-provisioner",
            installed=False,
        ),
        run_commands={
            "/tmp/provisioner/test-resource-1/venv/bin/pip list "
            + "--require-virtualenv "
            + "--format "
            + "json": (
                0,
                json.dumps([{"name": "ssh-provisioner", "version": "6.6.6"}]),
                None,
            )
        },
    ) as cmd:
        assert await BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("ssh-provisioner.whl"),
            package_name="ssh-provisioner",
        ).refresh(step_id="test-resource-2", pre=False) == BootstrapConfig(
            id="test-resource-2",
            venv_resource_id="test-resource-1",
            whl=Path("ssh-provisioner.whl"),
            package_name="ssh-provisioner",
            installed=True,
        )
        assert cmd.load_pre_bootstrap_config.call_count == 1
