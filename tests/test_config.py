from core.config import DoraConfig, config_to_runtime_dict, migrate_legacy_keys


def test_migrate_legacy_ollama_keys() -> None:
    raw = {
        "ollama_num_ctx": 2048,
        "use_ollama_fallback": False,
        "warmup_ollama_on_start": False,
    }
    data = migrate_legacy_keys(raw)
    assert data["llm_n_ctx"] == 2048
    assert data["use_llm_fallback"] is False
    assert data["warmup_llm_on_start"] is False


def test_dora_config_from_mapping() -> None:
    cfg = DoraConfig.from_mapping({"wake_word": "hey dora", "llm_n_ctx": 8192})
    assert cfg.wake_word == "hey dora"
    assert cfg.llm_n_ctx == 8192
    assert cfg.llm_n_ctx_or_none() == 8192


def test_config_to_runtime_dict() -> None:
    cfg = DoraConfig(wake_word="dora")
    data = config_to_runtime_dict(cfg)
    assert data["wake_word"] == "dora"
