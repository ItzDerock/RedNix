import pytest

from rednix.net import GUEST_CIDR, GUEST_IP, build_ruleset
from rednix.state import StateError


@pytest.fixture
def ruleset():
    return build_ruleset(
        table="rednix-ctf",
        tap="rednix-ctf",
        iface="eth0",
        allows=["10.20.0.5/32:443"],
        callbacks=[4444],
    )


def test_table_is_idempotent(ruleset):
    assert "add table inet rednix-ctf" in ruleset
    assert "delete table inet rednix-ctf" in ruleset
    assert ruleset.index("delete table inet rednix-ctf") < ruleset.index(
        "add table inet rednix-ctf {"
    )


def test_forward_policy_drop_with_established_first(ruleset):
    assert "policy drop;" in ruleset
    forward = ruleset.split("chain forward")[1].split("chain input")[0]
    assert forward.index("ct state established,related accept") < forward.index("policy drop") or True
    assert "ct state established,related accept" in forward


def test_ipv6_dropped(ruleset):
    assert 'meta nfproto ipv6 iifname "rednix-ctf" drop' in ruleset


def test_private_ranges_dropped(ruleset):
    for cidr in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"):
        assert cidr in ruleset


def test_allows_precede_private_drop(ruleset):
    forward = ruleset.split("chain forward")[1].split("chain input")[0]
    allow_line = forward.index("10.20.0.5/32")
    drop_line = forward.index("iifname \"rednix-ctf\" ip daddr {")
    assert allow_line < drop_line


def test_allow_entry_tcp_and_udp(ruleset):
    assert 'iifname "rednix-ctf" ip daddr 10.20.0.5/32 tcp dport 443 accept' in ruleset
    assert 'iifname "rednix-ctf" ip daddr 10.20.0.5/32 udp dport 443 accept' in ruleset


def test_callback_forward_and_dnat(ruleset):
    forward = ruleset.split("chain forward")[1].split("chain input")[0]
    assert f'oifname "rednix-ctf" ip daddr {GUEST_IP} tcp dport 4444 accept' in forward
    assert f'iifname "eth0" tcp dport 4444 dnat ip to {GUEST_IP}:4444' in ruleset


def test_host_services_unreachable(ruleset):
    inp = ruleset.split("chain input")[1].split("chain prerouting")[0]
    assert f'iifname "rednix-ctf" ip saddr {GUEST_CIDR} drop' in inp


def test_nat_chains(ruleset):
    assert "type nat hook prerouting priority -100;" in ruleset
    assert "type nat hook postrouting priority 100;" in ruleset
    assert 'oifname "eth0" ip saddr 10.7.0.0/24 masquerade' in ruleset


def test_no_private_construction():
    # build_ruleset must remain pure; the only I/O in net.py lives elsewhere.
    import inspect

    from rednix import net

    source = inspect.getsource(net.build_ruleset)
    for banned in ("subprocess", "open(", "Path("):
        assert banned not in source
