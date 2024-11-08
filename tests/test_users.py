from pathlib import Path

from unittest.mock import call

from provisioner.provision import Users, User, load_users_config, UsersConfig
from tests.common import mock_commands


def generate_test_user(
    name: str, home: Path | None = None, key: str | None = None, sudo: bool = True
) -> User:
    return User(
        name, home or Path(f"/home/{name}"), f"{key or name}-some-key", sudo=sudo
    )


def test_users_state_0() -> None:
    """
    No users anywhere
    """
    assert Users().state(Users()) == (
        set(),
        set(),
        set(),
        [],
    )


def test_users_state_1() -> None:
    """
    One user in system but no users wanted
    """
    assert Users().state(Users(users=frozenset({generate_test_user("user1")}))) == (
        {generate_test_user("user1")},
        set(),
        set(),
        [],
    )


def test_users_state_2() -> None:
    """
    Same users wanted and in the system
    """
    assert Users(users=frozenset({generate_test_user("user1")})).state(
        Users(users=frozenset({generate_test_user("user1")}))
    ) == (set(), set(), set(), [])


def test_users_state_3() -> None:
    """
    different users wanted and in the system
    """
    assert Users(users=frozenset({generate_test_user("user1")})).state(
        Users(users=frozenset({generate_test_user("user2")}))
    ) == (
        {generate_test_user("user2")},
        {generate_test_user("user1")},
        set(),
        [
            generate_test_user("user1"),
        ],
    )


def test_users_state_4() -> None:
    """
    Same users wanted but different home
    """
    assert Users(users=frozenset({generate_test_user("user1")})).state(
        Users(users=frozenset({generate_test_user("user1", home=Path("/root"))}))
    ) == (
        set(),
        set(),
        {
            generate_test_user("user1", home=Path("/root")),
        },
        [generate_test_user("user1", home=Path("/root"))],
    )


def test_users_state_5() -> None:
    """
    Same users wanted and in the system but with differences
    """
    assert Users(
        users=frozenset({generate_test_user("user1")}),
        ignore_users=frozenset(
            {
                "user2",
                "user3",
            }
        ),
    ).state(
        Users(
            users=frozenset(
                {
                    generate_test_user("user1"),
                    generate_test_user("user2"),
                    generate_test_user("user3"),
                }
            )
        )
    ) == (
        set(),
        set(),
        set(),
        [],
    )


def test_users_state_6() -> None:
    """
    Same users wanted and in the system but with differences
    """
    assert Users(
        users=frozenset(
            {
                generate_test_user("user1"),
            }
        ),
    ).state(Users()) == (
        set(),
        {
            generate_test_user("user1"),
        },
        set(),
        [generate_test_user("user1")],
    )


def test_users_state_7() -> None:
    """
    Same users wanted and in the system but with differences
    """
    assert Users(
        users=frozenset(
            {
                generate_test_user("user1", key="key1"),
            }
        ),
    ).state(
        Users(
            users=frozenset(
                {
                    generate_test_user("user1", key="key2"),
                }
            )
        )
    ) == (
        set(),
        set(),
        {
            generate_test_user("user1", key="key1"),
        },
        [generate_test_user("user1", key="key1")],
    )


def test_users_state_8() -> None:
    """
    Same users wanted but different home and different key
    """
    assert Users(users=frozenset({generate_test_user("user1", key="key1")})).state(
        Users(
            users=frozenset(
                {generate_test_user("user1", home=Path("/root"), key="key2")}
            )
        )
    ) == (
        set(),
        set(),
        {
            generate_test_user("user1", home=Path("/root"), key="key1"),
        },
        [generate_test_user("user1", home=Path("/root"), key="key1")],
    )


async def test_users_0():
    with mock_commands() as commands:
        await Users(
            users=frozenset(
                {
                    generate_test_user("user1"),
                }
            ),
            all_users=frozenset(),
        ).provision(apply=True)
        assert commands.run_command.call_args_list == [
            call(["/usr/sbin/useradd", "-m", "-U", "-G", "sudo", "user1"])
        ]
        assert commands.write_authorized_keys.call_args_list == [
            call(Path("/home/user1/.ssh/authorized_keys"), "user1-some-key")
        ]


async def test_users_1():
    with mock_commands() as commands:
        await Users(
            users=frozenset(
                {
                    generate_test_user("user1"),
                }
            ),
            all_users=frozenset({generate_test_user("user1")}),
        ).provision(apply=True)
        assert commands.write_authorized_keys.call_args_list == []
        assert commands.run_command.call_args_list == []


async def test_users_2():
    with mock_commands() as commands:
        await Users(
            users=frozenset(
                {
                    generate_test_user("user1"),
                }
            ),
            all_users=frozenset({generate_test_user("user2")}),
        ).provision(apply=True)
        assert commands.run_command.call_args_list == [
            call(["/usr/sbin/userdel", "-r", "user2"]),
            call(["/usr/sbin/useradd", "-m", "-U", "-G", "sudo", "user1"]),
        ]
        assert commands.write_authorized_keys.call_args_list == [
            call(Path("/home/user1/.ssh/authorized_keys"), "user1-some-key")
        ]


async def test_users_3():
    with mock_commands() as commands:
        await Users(
            users=frozenset(
                {
                    generate_test_user("user1"),
                }
            ),
            all_users=frozenset({generate_test_user("user1", home=Path("/root"))}),
        ).provision(apply=True)
        assert commands.run_command.call_args_list == []
        assert commands.write_authorized_keys.call_args_list == [
            call(Path("/root/.ssh/authorized_keys"), "user1-some-key")
        ]


async def test_users_4():
    with mock_commands() as commands:
        await Users(
            users=frozenset(
                {
                    generate_test_user("user1", key="key1"),
                }
            ),
            all_users=frozenset(
                {generate_test_user("user1", home=Path("/root"), key="not-this")}
            ),
        ).provision(apply=True)
        assert commands.run_command.call_args_list == []
        assert commands.write_authorized_keys.call_args_list == [
            call(Path("/root/.ssh/authorized_keys"), "key1-some-key")
        ]


async def test_load_users_config_0() -> None:
    assert (
        load_users_config(
            id="6666",
            custom_pre_users_config=(
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
            custom_manageable_users=frozenset(),
        )
        == uc
    )


async def test_load_users_config_1() -> None:
    uc = UsersConfig(
        users=frozenset(
            {
                generate_test_user("user1"),
                generate_test_user("user2"),
                generate_test_user("user3"),
            }
        )
    )
    assert (
        load_users_config(
            id="6666",
            custom_pre_users_config=uc,
            custom_manageable_users=uc.users,
        )
        == UsersConfig()
    )


async def test_load_users_config_2() -> None:
    uc = UsersConfig(
        users=frozenset(
            {
                generate_test_user("user1"),
                generate_test_user("user2"),
                generate_test_user("user3", sudo=True),
            }
        )
    )
    assert load_users_config(
        id="6666",
        custom_pre_users_config=uc,
        custom_manageable_users=frozenset(
            {
                generate_test_user("user1"),
                generate_test_user("user2"),
                generate_test_user("user3", sudo=False),
            }
        ),
    ) == UsersConfig(
        users=frozenset(
            {
                generate_test_user("user3", sudo=False),
            }
        )
    )
