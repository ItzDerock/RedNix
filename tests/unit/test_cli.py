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


def test_gui_menu_and_list():
    assert _parse(["gui"]).program is None
    args = _parse(["gui", "--event", "ctf", "--list"])
    assert args.list and args.event == "ctf" and args.program is None


def test_services_menu_and_named_tunnels():
    assert _parse(["services"]).services == []
    args = _parse(["services", "exploitfarm", "--event", "ctf", "--port", "8050"])
    assert args.services == ["exploitfarm"]
    assert args.port == 8050 and args.event == "ctf"
    assert _parse(["services", "--no-start", "all"]).no_start


def test_service_list_needs_no_event(config, capsys):
    assert cli.cmd_services(_parse(["services", "--list"]), config) == 0
    assert "exploitfarm" in capsys.readouterr().out


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


def test_default_persists_across_commands_and_roots(tmp_path, capsys):
    root = tmp_path / "state"
    other = tmp_path / "other"
    root.mkdir()
    config_path = root / "config.toml"
    contents = '# keep this comment\nshare_root = "~/CTF"\n'
    config_path.write_text(contents)
    prefix = ["--state-root", str(root)]
    assert cli.main(prefix + ["default", "ctf"]) == 0
    capsys.readouterr()
    assert cli.main(prefix + ["default"]) == 0
    assert capsys.readouterr().out.strip() == "ctf"
    assert config_path.read_text() == contents
    with pytest.raises(SystemExit):
        cli.main(["--state-root", str(other), "default"])
    assert "no events found" in capsys.readouterr().err
    assert cli.main(prefix + ["default", "--clear"]) == 0
    assert not (root / "default-event").exists()


def test_default_rejects_event_with_clear():
    with pytest.raises(SystemExit):
        _parse(["default", "ctf", "--clear"])


@pytest.mark.parametrize("command", ["gui", "services"])
@pytest.mark.parametrize("explicit", [False, True])
def test_saved_default_for_flag_commands(config, monkeypatch, command, explicit):
    from rednix import apps, services
    from rednix.state import set_default_event

    set_default_event(config, "selected")
    calls = []
    monkeypatch.setattr(cli.ssh_mod, "write_ssh_config", lambda c: None)
    def record(c, event, *args, **kwargs):
        calls.append(event)
        return 0
    monkeypatch.setattr(apps, "launch", record)
    monkeypatch.setattr(services, "run", record)
    argv = [command] + (["--event", "other"] if explicit else [])
    assert cli.main(argv) == 0
    assert calls == ["other" if explicit else "selected"]


@pytest.mark.parametrize("event", [None, "other"])
def test_exec_separator_with_default(config, monkeypatch, event):
    from rednix.state import set_default_event

    set_default_event(config, "selected")
    calls = []
    monkeypatch.setattr(cli.ssh_mod, "write_ssh_config", lambda c: None)
    monkeypatch.setattr(cli.ssh_mod, "run", lambda c, e, command: calls.append((e, command)) or 0)
    argv = ["exec"] + ([event] if event else []) + ["--", "id", "-u"]
    assert cli.main(argv) == 0
    assert calls == [(event or "selected", ["id", "-u"])]


@pytest.mark.parametrize("command", ["build", "warm", "start"])
@pytest.mark.parametrize("event", [None, "other"])
def test_saved_default_for_lifecycle_commands(config, monkeypatch, command, event):
    from rednix.state import set_default_event

    set_default_event(config, "selected")
    calls = []
    def record(c, event, **kwargs):
        calls.append(event)
        return {"pid": 42, "ssh_port": 2222}
    target = cli.nix_mod if command == "build" else cli.vm_mod
    monkeypatch.setattr(target, command, record)
    assert cli.main([command] + ([event] if event else [])) == 0
    assert calls == [event or "selected"]


@pytest.mark.parametrize("command, expected", [("build", None), ("warm", "warmup")])
def test_lifecycle_without_saved_default(config, monkeypatch, command, expected):
    calls = []
    def record(c, event, **kwargs):
        calls.append(event)
    target = cli.nix_mod if command == "build" else cli.vm_mod
    monkeypatch.setattr(target, command, record)
    assert cli.main([command]) == 0
    assert calls == [expected]


def test_every_subcommand_registered():
    parser = cli.build_parser()
    choices = parser._subparsers._group_actions[0].choices
    for command in (
        "init", "doctor", "default", "build", "warm", "images", "start", "stop", "destroy",
        "list", "status", "shell", "exec", "fhs", "gui", "desktop", "logs",
        "snapshot", "restore", "gc", "net", "services",
    ):
        assert command in choices, command
