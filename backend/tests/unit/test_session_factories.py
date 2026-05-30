"""Unit tests for ADK service factories — env-var-driven backend selection."""

from __future__ import annotations

from unittest.mock import patch

from adk import session as session_mod


class TestGetSessionService:
    def setup_method(self):
        session_mod._reset_session_service_for_tests()

    def teardown_method(self):
        session_mod._reset_session_service_for_tests()

    def test_returns_in_memory_when_no_env(self):
        with patch.dict("os.environ", {}, clear=True):
            svc = session_mod.get_session_service()
        assert type(svc).__name__ == "InMemorySessionService"

    def test_returns_vertex_ai_when_env_set(self):
        env = {
            "AGENT_ENGINE_ID": "projects/p/locations/l/reasoningEngines/123",
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GOOGLE_CLOUD_LOCATION": "europe-west1",
        }
        with patch.dict("os.environ", env, clear=True):
            svc = session_mod.get_session_service()
        assert type(svc).__name__ == "VertexAiSessionService"


class TestGetMemoryService:
    def test_returns_in_memory_when_no_env(self):
        with patch.dict("os.environ", {}, clear=True):
            svc = session_mod.get_memory_service()
        assert type(svc).__name__ == "InMemoryMemoryService"

    def test_returns_vertex_ai_when_env_set(self):
        env = {
            "AGENT_ENGINE_ID": "projects/p/locations/l/reasoningEngines/123",
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GOOGLE_CLOUD_LOCATION": "europe-west1",
        }
        with patch.dict("os.environ", env, clear=True):
            svc = session_mod.get_memory_service()
        assert type(svc).__name__ == "VertexAiMemoryBankService"


class TestGetArtifactService:
    def setup_method(self):
        session_mod._reset_artifact_service_for_tests()

    def teardown_method(self):
        session_mod._reset_artifact_service_for_tests()

    def test_returns_in_memory_when_no_env(self):
        with patch.dict("os.environ", {}, clear=True):
            svc = session_mod.get_artifact_service()
        assert type(svc).__name__ == "InMemoryArtifactService"

    def test_returns_gcs_when_bucket_set(self):
        # GcsArtifactService instantiates a storage.Client in __init__, which
        # calls google.auth.default() — fine on Cloud Run, fatal on CI runners
        # without ADC. Mock the client so the factory branch is exercised
        # without touching real credentials.
        env = {"ADK_ARTIFACT_BUCKET": "my-bucket", "GOOGLE_CLOUD_PROJECT": "test-project"}
        with patch.dict("os.environ", env, clear=True), patch("google.cloud.storage.Client"):
            svc = session_mod.get_artifact_service()
        assert type(svc).__name__ == "GcsArtifactService"


class TestGetServiceUris:
    """Test the URI helpers used by get_fast_api_app()."""

    def test_session_uri_none_when_no_env(self):
        with patch.dict("os.environ", {}, clear=True):
            assert session_mod.get_session_service_uri() is None

    def test_session_uri_agent_engine_when_set(self):
        env = {
            "AGENT_ENGINE_ID": "projects/p/locations/l/reasoningEngines/123",
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GOOGLE_CLOUD_LOCATION": "europe-west1",
        }
        with patch.dict("os.environ", env, clear=True):
            uri = session_mod.get_session_service_uri()
        assert uri is not None
        assert "agentengine://" in uri

    def test_artifact_uri_none_when_no_env(self):
        with patch.dict("os.environ", {}, clear=True):
            assert session_mod.get_artifact_service_uri() is None

    def test_artifact_uri_gcs_when_bucket_set(self):
        env = {"ADK_ARTIFACT_BUCKET": "my-bucket"}
        with patch.dict("os.environ", env, clear=True):
            uri = session_mod.get_artifact_service_uri()
        assert uri == "gs://my-bucket"


class TestGetCompactionConfig:
    def test_gemini_3_flash_gets_long_interval(self):
        cfg = session_mod.get_compaction_config("gemini-3-flash-preview")
        assert cfg.compaction_interval == 10
        assert cfg.overlap_size == 3

    def test_gemini_3_1_pro_gets_long_interval(self):
        cfg = session_mod.get_compaction_config("gemini-3.1-pro-preview")
        assert cfg.compaction_interval == 10

    def test_gpt_5_4_gets_long_interval(self):
        # GPT-5.4 has a 1M context window — same tier as Gemini
        cfg = session_mod.get_compaction_config("gpt-5.4")
        assert cfg.compaction_interval == 10
        assert cfg.overlap_size == 3

    def test_claude_gets_short_interval(self):
        cfg = session_mod.get_compaction_config("claude-sonnet-4-6")
        assert cfg.compaction_interval == 5
        assert cfg.overlap_size == 2

    def test_claude_opus_gets_short_interval(self):
        cfg = session_mod.get_compaction_config("claude-opus-4-7")
        assert cfg.compaction_interval == 5

    def test_gpt_5_1_gets_short_interval(self):
        # GPT-5.1 has 400K context — shorter interval
        cfg = session_mod.get_compaction_config("gpt-5.1-chat-latest")
        assert cfg.compaction_interval == 5

    def test_unknown_model_gets_safe_default(self):
        cfg = session_mod.get_compaction_config("unknown-future-model")
        assert cfg.compaction_interval == 5
        assert cfg.overlap_size == 2
