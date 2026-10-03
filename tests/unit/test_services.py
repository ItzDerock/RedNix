import subprocess

import pytest

from rednix import services
from rednix.state import StateError


def test_service_selection():
    assert services.select(["all"]) == list(services.SERVICES)
    assert services.select(["tulip", "tulip"])[0].port == 3000
    assert len(services.select(["tulip", "tulip"])) == 1
    with pytest.raises(StateError, match="--list"):
        services.select(["missing"])


@pytest.mark.parametrize("port,selected", [(0, [services.SERVICES[0]]),
                                            (65536, [services.SERVICES[0]]),
                                            (8080, list(services.SERVICES))])
def test_invalid_port_fails_before_starting(config, port, selected):
    with pytest.raises(StateError, match="--port"):
        services.forward(config, "test", selected, local_port=port)


class Tunnel:
    returncode = None
    stopped = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if timeout is None:
            raise KeyboardInterrupt
        self.returncode = -15
        return self.returncode

    def terminate(self):
        self.stopped = True


def test_tunnel_ports_loopback_and_cleanup_on_interrupt(config, monkeypatch, capsys):
    tunnel = Tunnel()
    commands = []
    starts = []
    monkeypatch.setattr(services.apps, "require_running", lambda *args: None)
    monkeypatch.setattr(services.state, "allocate_free_port",
                        lambda base, avoid: base + 1)  # usual port already occupied
    monkeypatch.setattr(services.ssh, "run",
                        lambda config, event, command: starts.append(command) or 0)
    monkeypatch.setattr(services.subprocess, "Popen",
                        lambda command: commands.append(command) or tunnel)
    monkeypatch.setattr(services, "_healthy", lambda *args: True)
    with pytest.raises(KeyboardInterrupt):
        services.forward(config, "test", list(services.SERVICES))
    assert starts == [["exploitfarm", "start"], ["tulip", "start"]]
    argv = commands[0]
    assert "127.0.0.1:5051:127.0.0.1:5050" in argv
    assert "127.0.0.1:3001:127.0.0.1:3000" in argv
    assert "ControlPath=none" in argv
    assert "ExitOnForwardFailure=yes" in argv
    assert "http://127.0.0.1:5051" in capsys.readouterr().out
    assert tunnel.stopped


def test_failed_guest_start_never_opens_tunnel(config, monkeypatch):
    monkeypatch.setattr(services.apps, "require_running", lambda *args: None)
    monkeypatch.setattr(services.ssh, "run", lambda *args: 1)
    monkeypatch.setattr(services.subprocess, "Popen",
                        lambda *args: pytest.fail("tunnel opened after startup failure"))
    with pytest.raises(StateError, match="exploitfarm logs"):
        services.forward(config, "test", [services.SERVICES[0]], local_port=5050)


def test_no_start_and_early_ssh_failure(config, monkeypatch):
    tunnel = Tunnel()
    tunnel.returncode = 255
    monkeypatch.setattr(services.apps, "require_running", lambda *args: None)
    monkeypatch.setattr(services.ssh, "run", lambda *args: pytest.fail("started a service"))
    monkeypatch.setattr(services.subprocess, "Popen", lambda *args: tunnel)
    with pytest.raises(StateError, match="SSH tunnel exited"):
        services.forward(config, "test", [services.SERVICES[0]], local_port=5050, start=False)


def test_readiness_timeout_cleans_up(config, monkeypatch):
    tunnel = Tunnel()
    monkeypatch.setattr(services.apps, "require_running", lambda *args: None)
    monkeypatch.setattr(services.subprocess, "Popen", lambda *args: tunnel)
    monkeypatch.setattr(services, "_healthy", lambda *args: False)
    times = iter([0, 31])
    monkeypatch.setattr(services.time, "monotonic", lambda: next(times))
    with pytest.raises(StateError, match="exploitfarm logs"):
        services.forward(config, "test", [services.SERVICES[0]], local_port=5050, start=False)
    assert tunnel.stopped
