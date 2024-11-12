from pathlib import Path

from unittest.mock import call

from provisioner.users import (
    Users,
    User,
    load_users_config,
    UsersConfig,
    UsersDiff,
)
from provisioner.resources import (
    ResourceState,
    ResourceMissing,
    ResourceOutdated,
    ResourcePresent,
)
from tests.common import mock_commands


TEST_USER_ID = "5a97ea12-28e8-4fa4-830f-a5573cbf360b"


def generate_test_user(
    name: str,
    home: Path | None = None,
    key: str | None = None,
    sudo: bool = True,
    state: ResourceState | None = None,
) -> User:
    return User(
        name,
        home or Path(f"/home/{name}"),
        f"{key or name}-some-key",
        sudo=sudo,
    )


def test_users_state_0() -> None:
    """
    No users anywhere
    """
    assert Users(id=TEST_USER_ID).state(Users(id=TEST_USER_ID)) == UsersDiff()


def test_users_state_1() -> None:
    """
    One user in system but no users wanted
    """
    assert Users(id=TEST_USER_ID).state(
        Users(id=TEST_USER_ID, users=frozenset({generate_test_user("user1")}))
    ) == UsersDiff(users_to_delete=frozenset({generate_test_user("user1")}))


def test_users_state_2() -> None:
    with mock_commands(
        users_in_sudoer=frozenset({"user1"}),
    ):
        assert Users(
            id=TEST_USER_ID,
            users=(us := frozenset({generate_test_user("user1")})),
        ).state(
            Users(id=TEST_USER_ID, users=frozenset({generate_test_user("user1")}))
        ) == UsersDiff(users_final=us, sudoers_final=frozenset([u.name for u in us]))


def test_users_state_3() -> None:
    with mock_commands(
        users_in_sudoer=frozenset({"user1"}),
    ):
        assert Users(
            id=TEST_USER_ID,
            users=(us := frozenset({generate_test_user("user1")})),
        ).state(
            Users(id=TEST_USER_ID, users=frozenset({generate_test_user("user2")}))
        ) == UsersDiff(
            users_final=us,
            users_to_delete=frozenset({generate_test_user("user2")}),
            users_to_add=frozenset({generate_test_user("user1")}),
            sudoers_final=frozenset({"user1"}),
        )


def test_users_state_4() -> None:
    with mock_commands(
        users_in_sudoer=frozenset({"user1"}),
    ):
        assert Users(
            id=TEST_USER_ID,
            users=(us := frozenset({generate_test_user("user1")})),
        ).state(
            Users(
                id=TEST_USER_ID,
                users=frozenset({generate_test_user("user1", home=Path("/root"))}),
            )
        ) == UsersDiff(
            users_final=us,
            users_to_update=frozenset(
                {generate_test_user("user1", home=Path("/root"))}
            ),
            sudoers_final=frozenset({"user1"}),
        )


def test_users_state_5() -> None:
    with mock_commands(
        users_in_sudoer=frozenset({"user1"}),
    ):
        assert Users(
            id=TEST_USER_ID,
            users=(us := frozenset({generate_test_user("user1")})),
            ignore=frozenset(
                {
                    "user2",
                    "user3",
                }
            ),
        ).state(
            Users(
                id=TEST_USER_ID,
                users=frozenset(
                    {
                        generate_test_user("user1"),
                        generate_test_user("user2"),
                        generate_test_user("user3"),
                    }
                ),
            )
        ) == UsersDiff(users_final=us, sudoers_final=frozenset({"user1"}))


def test_users_state_6() -> None:
    with mock_commands(
        users_in_sudoer=frozenset({"user1"}),
    ):
        assert Users(
            id=TEST_USER_ID,
            users=(
                us := frozenset(
                    {
                        generate_test_user("user1"),
                    }
                )
            ),
        ).state(Users(id=TEST_USER_ID)) == UsersDiff(
            users_final=us,
            users_to_add=frozenset(
                {
                    generate_test_user("user1"),
                }
            ),
            sudoers_final=frozenset({"user1"}),
        )


def test_users_state_7() -> None:
    with mock_commands(
        users_in_sudoer=frozenset({"user1"}),
    ):
        assert Users(
            id=TEST_USER_ID,
            users=(
                us := frozenset(
                    {
                        generate_test_user("user1", key="key1"),
                    }
                )
            ),
        ).state(
            Users(
                id=TEST_USER_ID,
                users=frozenset(
                    {
                        generate_test_user("user1", key="key2"),
                    }
                ),
            )
        ) == UsersDiff(
            users_final=us,
            users_to_update=frozenset(
                {
                    generate_test_user("user1", key="key1"),
                }
            ),
            sudoers_final=frozenset({"user1"}),
        )


def test_users_state_8() -> None:
    with mock_commands(
        users_in_sudoer=frozenset({"user1"}),
    ):
        assert Users(
            id=TEST_USER_ID,
            users=(
                us := frozenset(
                    {
                        generate_test_user("user1", key="key1"),
                    }
                )
            ),
        ).state(
            Users(
                id=TEST_USER_ID,
                users=frozenset(
                    {
                        generate_test_user("user1", key="key2"),
                    }
                ),
            )
        ) == UsersDiff(
            users_final=us,
            users_to_update=frozenset(
                {
                    generate_test_user("user1", key="key1"),
                }
            ),
            sudoers_final=frozenset({"user1"}),
        )


def test_users_state_9() -> None:
    with mock_commands(
        users_in_sudoer=frozenset({"user1"}),
    ):
        assert Users(
            id=TEST_USER_ID,
            users=(us := frozenset({generate_test_user("user1", key="key1")})),
        ).state(
            Users(
                id=TEST_USER_ID,
                users=frozenset(
                    {generate_test_user("user1", home=Path("/root"), key="key2")}
                ),
            )
        ) == UsersDiff(
            users_final=us,
            users_to_update=frozenset(
                {
                    generate_test_user("user1", home=Path("/root"), key="key1"),
                }
            ),
            sudoers_final=frozenset({"user1"}),
        )


async def test_users_provision_0():
    with mock_commands(
        manageable_users=frozenset(),
        users_in_sudoer=frozenset(),
    ) as commands:
        await Users(
            id=TEST_USER_ID,
            users=frozenset(
                {
                    generate_test_user("user1"),
                }
            ),
        ).provision(apply=True)
        assert commands.run_command.call_args_list == [
            call(["/usr/sbin/useradd", "-m", "-U", "-G", "sudo", "user1"])
        ]
        assert commands.write_authorized_keys.call_args_list == [
            call(Path("/home/user1/.ssh/authorized_keys"), "user1-some-key")
        ]
        assert commands.chown.call_args_list == [
            call(Path("/home/user1/.ssh/authorized_keys"), user="user1", group="user1")
        ]


async def test_users_provision_1():
    with mock_commands(
        manageable_users=frozenset({generate_test_user("user1")}),
        users_in_sudoer=frozenset({"user1"}),
    ) as commands:
        await Users(
            id=TEST_USER_ID,
            users=frozenset(
                {
                    generate_test_user("user1"),
                }
            ),
        ).provision(apply=True)
        assert commands.write_authorized_keys.call_args_list == []
        assert commands.run_command.call_args_list == []


async def test_users_provision_2():
    with mock_commands(
        manageable_users=frozenset({generate_test_user("user2")}),
        users_in_sudoer=frozenset({"user1"}),
    ) as commands:
        await Users(
            id=TEST_USER_ID,
            users=frozenset(
                {
                    generate_test_user("user1"),
                }
            ),
        ).provision(apply=True)
        assert commands.run_command.call_args_list == [
            call(["/usr/sbin/userdel", "-r", "user2"]),
            call(["/usr/sbin/useradd", "-m", "-U", "-G", "sudo", "user1"]),
        ]
        assert commands.write_authorized_keys.call_args_list == [
            call(Path("/home/user1/.ssh/authorized_keys"), "user1-some-key")
        ]


async def test_users_provision_3():
    with mock_commands(
        manageable_users=frozenset({generate_test_user("user1", home=Path("/root"))}),
        users_in_sudoer=frozenset({"user1"}),
    ) as commands:
        await Users(
            id=TEST_USER_ID,
            users=frozenset(
                {
                    generate_test_user("user1"),
                }
            ),
        ).provision(apply=True)
        assert commands.run_command.call_args_list == []
        assert commands.write_authorized_keys.call_args_list == [
            call(Path("/root/.ssh/authorized_keys"), "user1-some-key")
        ]


async def test_users_provision_4():
    with mock_commands(
        manageable_users=frozenset(
            {generate_test_user("user1", home=Path("/root"), key="not+this")}
        ),
        users_in_sudoer=frozenset({"user1"}),
    ) as commands:
        await Users(
            id=TEST_USER_ID,
            users=frozenset(
                {
                    generate_test_user("user1", key="key1"),
                }
            ),
        ).provision(apply=True)
        assert commands.run_command.call_args_list == []
        assert commands.write_authorized_keys.call_args_list == [
            call(Path("/root/.ssh/authorized_keys"), "key1-some-key")
        ]


async def test_load_users_config_0() -> None:
    with mock_commands(
        pre_users_config=(
            uc := UsersConfig(
                users=frozenset(
                    {
                        generate_test_user("user1"),
                        generate_test_user("user2"),
                        generate_test_user("user3"),
                    }
                )
            )
        )
    ):
        assert load_users_config(id=TEST_USER_ID) == UsersConfig()


async def test_load_users_config_1() -> None:
    with mock_commands(
        pre_users_config=(
            uc := UsersConfig(
                users=frozenset(
                    {
                        generate_test_user("user1"),
                        generate_test_user("user2"),
                        generate_test_user("user3"),
                    }
                )
            )
        ),
        manageable_users=frozenset(
            {
                generate_test_user("user1"),
                generate_test_user("user2"),
                generate_test_user("user3"),
            }
        ),
    ):
        assert load_users_config(
            id=TEST_USER_ID,
        ) == UsersConfig(users=uc.users)


async def test_load_users_config_2() -> None:
    with mock_commands(
        pre_users_config=(
            uc := UsersConfig(
                users=frozenset(
                    {
                        generate_test_user("user1"),
                        generate_test_user("user2"),
                        generate_test_user("user3"),
                    }
                )
            )
        ),
        manageable_users=frozenset(
            {
                generate_test_user("user1"),
                generate_test_user("user2"),
                generate_test_user("user3", sudo=False),
            }
        ),
    ):
        assert load_users_config(id=TEST_USER_ID) == UsersConfig(
            users=frozenset(
                {
                    generate_test_user("user1"),
                    generate_test_user("user2"),
                }
            )
        )


async def test_load_users_config_3() -> None:
    with mock_commands(
        pre_users_config=(
            uc := UsersConfig(
                users=frozenset(
                    {
                        generate_test_user("user1"),
                        generate_test_user("user2"),
                        generate_test_user("user3"),
                    }
                )
            )
        ),
        manageable_users=frozenset(
            {
                generate_test_user("user1"),
                generate_test_user("user2", key="another-key"),
                generate_test_user("user3", sudo=False),
            }
        ),
    ):
        assert load_users_config(id=TEST_USER_ID) == UsersConfig(
            users=frozenset(
                {
                    generate_test_user("user1"),
                }
            )
        )


def test_user_state_0() -> None:
    with mock_commands():
        assert generate_test_user("user1").state == ResourceMissing()


def test_user_state_1() -> None:
    with mock_commands(manageable_users=frozenset({generate_test_user("user1")})):
        assert generate_test_user("user1").state == ResourcePresent()


def test_user_state_2() -> None:
    with mock_commands(
        manageable_users=frozenset({generate_test_user("user1", key="key2")})
    ):
        assert generate_test_user("user1").state == ResourceOutdated(
            fields=["key"],
        )


def test_user_state_3() -> None:
    with mock_commands(
        manageable_users=frozenset(
            {generate_test_user("user1", key="key2", sudo=False)}
        )
    ):
        assert generate_test_user("user1").state == ResourceOutdated(
            fields=["key", "sudo"],
        )
