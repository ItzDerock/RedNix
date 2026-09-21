import pytest

import rednix.cli as cli


def _parse(argv):
    return cli.build_parser().parse_args(argv)


def test_start_full():
    args = _parse(["start", "ctf", "--network", "routed", "--mem", "8192", "--cpus", "4", "--fresh"])
    assert args.event == "ctf"
    assert args.network == "routed"
    assert args.mem == 8192
    assert args.cpus == 4
    assert args.fresh is True


def test_start_defaults():
    args = _parse(["start", "ctf"])
    assert args.network is None
    assert args.mem is None
    assert args.share is None


def test_destroy_flags():
    args = _parse(["destroy", "ctf", "--purge-share", "--yes"])
    assert args.purge_share is True
    assert args.yes is True


def test_net_allow_entry():
    args = _parse(["net", "allow", "ctf", "10.20.0.5/32:443"])
    assert args.entry == "10.20.0.5/32:443"


def test_gui_xwls():
    # a token like --help would be eaten by the parser itself; use plain args
    args = _parse(["gui", "--xwls", "burpsuite", "--no-sandbox"])
    assert args.program == "burpsuite"
    assert args.args == ["--no-sandbox"]
    assert args.xwls is True


def test_exec_remainder():
    # argparse strips the "--" separator; ssh.run re-adds it for the remote side
    args = _parse(["exec", "ctf", "--", "id", "-u"])
    assert args.event == "ctf"
    assert args.command == ["id", "-u"]


def test_exec_without_command_is_empty():
    # parse succeeds; cmd_exec rejects an empty command at runtime
    args = _parse(["exec"])
    assert args.event is None
    assert args.command == []


def test_unknown_command_fails():
    with pytest.raises(SystemExit):
        _parse(["frobnicate"])


def test_every_subcommand_registered():
    parser = cli.build_parser()
    choices = parser._subparsers._group_actions[0].choices
    for command in (
        "init", "doctor", "build", "warm", "images", "start", "stop", "destroy",
        "list", "status", "shell", "exec", "fhs", "gui", "desktop", "logs",
        "snapshot", "restore", "gc", "net",
    ):
        assert command in choices, command
