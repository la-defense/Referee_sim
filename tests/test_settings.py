from referee_sim_app.core.settings import AppSettings, load_settings, save_settings


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    s = AppSettings(mode="回环(无硬件)", port="COM9", baud=921600, scenario=2,
                    robot_id=101, match_duration=180.5, mqtt_host="127.0.0.1",
                    mqtt_port=1883, window=(10, 20, 1280, 720))
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded == s


def test_settings_missing_file_returns_defaults(tmp_path):
    loaded = load_settings(tmp_path / "nope.json")
    assert loaded == AppSettings()


def test_settings_ignores_unknown_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"port": "COM5", "hack": 1, "window": [1,2,3,4]}', encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.port == "COM5"
    assert loaded.window == (1, 2, 3, 4)
    assert not hasattr(loaded, "hack")
