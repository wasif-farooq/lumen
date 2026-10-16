"""Settings: reading and saving, folder checks, and names kept from before the rename."""

import json

from conftest import setting_in_fresh_python


def test_settings_round_trip(env, local):
    s = local.get("/api/settings").json()
    assert s["power_mode"] == "saver"
    saved = local.put("/api/settings", json={"threads": 2, "captions": True}).json()
    assert saved["threads"] == 2 and saved["captions"] is True
    on_disk = json.loads((env.data / "settings.json").read_text())
    assert on_disk["threads"] == 2


def test_out_of_range_values_are_clamped(env, local):
    assert local.put("/api/settings", json={"threads": 999}).json()["threads"] == 32
    assert local.put("/api/settings", json={"power_mode": "turbo"}).json()["power_mode"] == "auto"


def test_adding_a_folder_that_does_not_exist_explains_why(env, local):
    r = local.put("/api/settings", json={"roots": [str(env.documents), str(env.base / "missing")]})
    assert r.status_code == 400
    assert "can't see" in r.json()["detail"]


def test_folders_inside_another_are_merged(env, local):
    r = local.put("/api/settings", json={"roots": [str(env.roots), str(env.documents)]})
    assert r.json()["roots"] == [str(env.roots.resolve())]


def test_a_too_broad_folder_is_refused(env, local):
    assert local.put("/api/settings", json={"roots": ["/"]}).status_code == 400


def test_the_last_folder_cannot_be_removed(env, local):
    r = local.put("/api/settings", json={"roots": []})
    assert r.status_code == 400 and r.json()["detail"] == "Keep at least one folder"
    assert len(local.get("/api/settings").json()["roots"]) == 2


def test_old_environment_names_still_work_and_new_ones_win(env):
    assert setting_in_fresh_python({"OS_OPERATOR_MODEL": "old-model"}, "agent_model") == "old-model"
    both = {"OS_OPERATOR_MODEL": "old-model", "LUMEN_MODEL": "new-model"}
    assert setting_in_fresh_python(both, "agent_model") == "new-model"


def test_data_folder_from_before_the_rename_is_kept(env, tmp_path):
    home = tmp_path / "home"
    (home / ".local/share/os-operator").mkdir(parents=True)
    got = setting_in_fresh_python({"HOME": str(home)}, "data_dir")
    assert got.endswith(".local/share/os-operator")
    (home / ".local/share/lumen").mkdir()
    assert setting_in_fresh_python({"HOME": str(home)}, "data_dir").endswith(".local/share/lumen")


def test_a_new_process_starts_with_what_was_saved(env, local):
    local.put("/api/settings", json={"threads": 3})
    p = local.post(
        "/api/providers", json={"kind": "openai", "name": "LM", "base_url": "http://localhost:1234/v1"}
    ).json()
    local.put("/api/roles", json={"role": "agent", "provider": p["id"], "model": "llama-3"})
    started = {"LUMEN_DATA": str(env.data), "LUMEN_ROOTS": str(env.documents)}
    assert setting_in_fresh_python(started, "threads", after_start=True) == "3"
    assert setting_in_fresh_python(started, "agent_model", after_start=True) == "llama-3"
    assert setting_in_fresh_python(started, "agent_provider", after_start=True) == p["id"]
    assert setting_in_fresh_python(started, "threads") == "4"  # without loading: environment defaults
