import pytest

from rednix.config import DEFAULT_STATE_ROOT, ConfigError, load_config


def write_toml(root, text):
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.toml").write_text(text, encoding="utf-8")


def test_flag_beats_env(tmp_path, monkeypatch):
    env_root = tmp_path / "env"
    env_root.mkdir()
    monkeypatch.setenv("REDNIX_STATE_ROOT", str(env_root))
    flag_root = tmp_path / "flag"
    cfg = load_config(str(flag_root))
    assert cfg.state_root == flag_root


def test_env_beats_default(tmp_path, monkeypatch):
    env_root = tmp_path / "env"
    env_root.mkdir()
    monkeypatch.setenv("REDNIX_STATE_ROOT", str(env_root))
    assert load_config(None).state_root == env_root


def test_default_root_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv("REDNIX_STATE_ROOT", raising=False)
    assert load_config(None).state_root == DEFAULT_STATE_ROOT


def test_toml_redirects_state_root(tmp_path, monkeypatch):
    import rednix.config as config_mod

    monkeypatch.delenv("REDNIX_STATE_ROOT", raising=False)
    default = tmp_path / "default-root"
    relocated = tmp_path / "ssd-root"
    write_toml(default, f'state_root = "{relocated}"\nshare_root = "{tmp_path}/CTF"\n')
    write_toml(relocated, f'share_root = "{tmp_path}/CTF"\n')
    monkeypatch.setattr(config_mod, "DEFAULT_STATE_ROOT", default)
    cfg = load_config(None)
    assert cfg.state_root == relocated
    assert cfg.share_root == tmp_path / "CTF"


def test_explicit_root_ignores_toml_redirect(tmp_path):
    explicit = tmp_path / "explicit"
    elsewhere = tmp_path / "elsewhere"
    write_toml(explicit, f'state_root = "{elsewhere}"\n')
    assert load_config(str(explicit)).state_root == explicit


def test_invalid_network_raises(tmp_path):
    root = tmp_path / "state"
    write_toml(root, 'default_network = "bridged"\n')
    with pytest.raises(ConfigError, match="default_network"):
        load_config(str(root))


def test_non_integer_mem_raises(tmp_path):
    root = tmp_path / "state"
    write_toml(root, 'guest_mem_mib = "big"\n')
    with pytest.raises(ConfigError, match="guest_mem_mib"):
        load_config(str(root))


def test_share_root_and_derived_paths(tmp_path):
    root = tmp_path / "state"
    write_toml(root, f'share_root = "{tmp_path}/shares"\n')
    cfg = load_config(str(root))
    assert cfg.share_root == tmp_path / "shares"
    assert cfg.events_dir == root / "events"
    assert cfg.gcroots_dir == root / "gcroots"
    assert cfg.private_key == root / "keys" / "id_ed25519"
    assert cfg.ssh_config == root / "ssh_config"
    assert cfg.default_event_path == root / "default-event"
    assert cfg.event_dir("ev") == root / "events" / "ev"
