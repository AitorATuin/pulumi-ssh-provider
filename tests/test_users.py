from pathlib import Path

from unittest.mock import call

from provisioner.provision import Users, User
from tests.common import mock_commands


def generate_test_user(
    name: str, home: Path | None = None, key: str | None = None
) -> User:
    return User(name, home or Path(f"/home/{name}"), f"{name}-some-key")


def test_users_state_0() -> None:
    """
    No users anywhere
    """
    assert Users().state(Users()) == (
        set(),
        set(),
    )


def test_users_state_1() -> None:
    """
    One user in system but no users wanted
    """
    assert Users().state(Users(users={generate_test_user("user1")})) == (
        {generate_test_user("user1")},
        set(),
    )


def test_users_state_2() -> None:
    """
    Same users wanted and in the system
    """
    assert Users(users={generate_test_user("user1")}).state(
        Users(users={generate_test_user("user1")})
    ) == (set(), set())


def test_users_state_3() -> None:
    """
    different users wanted and in the system
    """
    assert Users(users={generate_test_user("user1")}).state(
        Users(users={generate_test_user("user2")})
    ) == ({generate_test_user("user2")}, {generate_test_user("user1")})


def test_users_state_4() -> None:
    """
    Same users wanted and in the system but with differences
    """
    assert Users(users={generate_test_user("user1")}).state(
        Users(users={generate_test_user("user1", home=Path("/root"))})
    ) == (
        {
            generate_test_user("user1", home=Path("/root")),
        },
        {generate_test_user("user1")},
    )


def test_users_state_5() -> None:
    """
    Same users wanted and in the system but with differences
    """
    assert Users(
        users={generate_test_user("user1")},
        ignore_users={
            "user2",
            "user3",
        },
    ).state(
        Users(
            users={
                generate_test_user("user1"),
                generate_test_user("user2"),
                generate_test_user("user3"),
            }
        )
    ) == (
        set(),
        set(),
    )


def test_users_state_6() -> None:
    """
    Same users wanted and in the system but with differences
    """
    assert Users(
        users={
            generate_test_user("user1"),
        },
    ).state(Users(users={})) == (
        set(),
        {
            generate_test_user("user1"),
        },
    )


async def test_users_0():
    with mock_commands() as commands:
        await Users(
            users={
                generate_test_user("user1"),
            },
            all_users=set(),
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
            users={
                generate_test_user("user1"),
            },
            all_users={generate_test_user("user1")},
        ).provision(apply=True)
        assert commands.write_authorized_keys.call_args_list == []
        assert commands.run_command.call_args_list == []


async def test_users_2():
    with mock_commands() as commands:
        await Users(
            users={
                generate_test_user("user1"),
            },
            all_users={generate_test_user("user2")},
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
            users={
                generate_test_user("user1"),
            },
            all_users={generate_test_user("user1", home=Path("/root"))},
        ).provision(apply=True)
        assert commands.run_command.call_args_list == [
            call(["/usr/sbin/userdel", "-r", "user1"]),
            call(["/usr/sbin/useradd", "-m", "-U", "-G", "sudo", "user1"]),
        ]
        assert commands.write_authorized_keys.call_args_list == [
            call(Path("/home/user1/.ssh/authorized_keys"), "user1-some-key")
        ]
