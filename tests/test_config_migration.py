from core.config import CONFIG_SCHEMA_VERSION, migrate_config_schema


def test_migrate_v1_vosk_install_to_whisper() -> None:
    raw = {"stt_engine": "vosk", "wake_word": "dora"}
    data, changed = migrate_config_schema(raw)
    assert changed is True
    assert data["stt_engine"] == "whisper"
    assert data["whisper_model"] == "small.en"
    assert data["whisper_max_utterance_sec"] == 12.0
    assert data["config_schema_version"] == CONFIG_SCHEMA_VERSION


def test_migrate_v2_vosk_upgrades_to_whisper() -> None:
    raw = {
        "stt_engine": "vosk",
        "config_schema_version": 2,
    }
    data, changed = migrate_config_schema(raw)
    assert changed is True
    assert data["stt_engine"] == "whisper"
    assert data["whisper_max_utterance_sec"] == 12.0
    assert data["config_schema_version"] == CONFIG_SCHEMA_VERSION


def test_migrate_v3_does_not_reapply() -> None:
    raw = {
        "stt_engine": "whisper",
        "config_schema_version": CONFIG_SCHEMA_VERSION,
    }
    data, changed = migrate_config_schema(raw)
    assert changed is False
