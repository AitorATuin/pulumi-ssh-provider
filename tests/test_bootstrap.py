from functools import partial
from pathlib import Path
from unittest.mock import call, patch

from provisioner.bootstrap import VenvConfig, load_venv_config
from tests.common import mock_commands


bootstrap_mock_commands = partial(mock_commands, module="bootstrap")


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
