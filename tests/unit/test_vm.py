import pytest

from rednix.state import StateError
from rednix.vm import qemu_extra_args


def test_nat_args():
    args = qemu_extra_args("nat", 2222, "ev")
    assert "hostfwd=tcp:127.0.0.1:2222-:22" in args
    assert "mac=02:00:00:00:00:01" in args
    assert "netdev=rednix0" in args


def test_routed_args():
    args = qemu_extra_args("routed", 2222, "myev")
    assert "ifname=rednix-myev" in args
    assert "script=no" in args
    assert "mac=02:00:00:00:00:02" in args


def test_mem_and_cpu_overrides():
    args = qemu_extra_args("nat", 2222, "ev", mem=8192, cpus=4)
    assert args.startswith("-m 8192 -smp 4 ")


def test_unknown_network_raises():
    with pytest.raises(StateError, match="network profile"):
        qemu_extra_args("bridged", 2222, "ev")


def test_routed_rejects_long_names():
    with pytest.raises(StateError, match="TAP"):
        qemu_extra_args("routed", 2222, "name-too-long-for-tap")
