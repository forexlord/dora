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


def test_migrate_v4_to_hey_dora_only() -> None:
    raw = {
        "stt_engine": "whisper",
        "wake_word": "dora",
        "config_schema_version": 4,
    }
    data, changed = migrate_config_schema(raw)
    assert changed is True
    assert data["wake_word"] == "hey dora"
    assert data["wake_phrases"] == ["hey dora"]
    assert data["wake_listen_rms_multiplier"] == 1.45
    assert data["config_schema_version"] == CONFIG_SCHEMA_VERSION


def test_migrate_v3_does_not_reapply() -> None:
    raw = {
        "stt_engine": "whisper",
        "config_schema_version": CONFIG_SCHEMA_VERSION,
    }
    data, changed = migrate_config_schema(raw)
    assert changed is False
