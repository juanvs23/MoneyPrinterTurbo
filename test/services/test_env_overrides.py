import os
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from app.config import config
from app.config.env_overrides import (
    EnvValueError,
    apply_env_file_to_environ,
    coerce_env_value,
    collect_env_overrides,
    env_name_candidates,
    load_env_file,
    parse_env_file,
    without_env_overrides,
)


class TestEnvFileParsing:
    def test_parses_plain_assignments(self):
        values = parse_env_file("A=1\nB=two\n")

        assert values == {"A": "1", "B": "two"}

    def test_ignores_comments_and_blank_lines(self):
        values = parse_env_file("# a comment\n\nA=1\n   # indented comment\n")

        assert values == {"A": "1"}

    def test_supports_export_prefix(self):
        assert parse_env_file("export A=1\n") == {"A": "1"}

    def test_strips_matching_quotes(self):
        values = parse_env_file('A="quoted value"\nB=\'single\'\n')

        assert values == {"A": "quoted value", "B": "single"}

    def test_keeps_hash_inside_quotes(self):
        assert parse_env_file('A="value # not a comment"\n') == {
            "A": "value # not a comment"
        }

    def test_trims_inline_comment_of_unquoted_value(self):
        assert parse_env_file("A=value # comment\n") == {"A": "value"}

    def test_expands_escapes_in_double_quotes(self):
        assert parse_env_file('A="line1\\nline2"\n') == {"A": "line1\nline2"}

    def test_keeps_single_quoted_value_verbatim(self):
        assert parse_env_file("A='raw\\nvalue'\n") == {"A": "raw\\nvalue"}

    def test_ignores_malformed_lines(self):
        assert parse_env_file("not a pair\nA=1\n") == {"A": "1"}

    def test_load_env_file_returns_empty_for_missing_file(self, tmp_path):
        assert load_env_file(tmp_path / "absent.env") == {}

    def test_load_env_file_reads_file(self, tmp_path):
        target = tmp_path / ".env"
        target.write_text("A=1\n", encoding="utf-8")

        assert load_env_file(target) == {"A": "1"}


class TestApplyEnvFile:
    def test_does_not_override_existing_environment(self, tmp_path):
        target = tmp_path / ".env"
        target.write_text("A=from_file\nB=from_file\n", encoding="utf-8")
        environ = {"A": "from_environment"}

        apply_env_file_to_environ(target, environ)

        assert environ == {"A": "from_environment", "B": "from_file"}


class TestEnvNameResolution:
    def test_top_level_uses_prefixed_name_first(self):
        assert env_name_candidates(None, "log_level")[0] == "MPT_LOG_LEVEL"

    def test_top_level_accepts_unprefixed_name(self):
        assert "LOG_LEVEL" in env_name_candidates(None, "log_level")

    def test_app_section_uses_prefixed_name_first(self):
        candidates = env_name_candidates("app", "gemini_api_key")

        assert candidates[0] == "MPT_APP_GEMINI_API_KEY"

    def test_app_section_accepts_unprefixed_provider_key(self):
        assert "GEMINI_API_KEY" in env_name_candidates("app", "gemini_api_key")

    def test_app_section_rejects_unprefixed_generic_key(self):
        """A generic key must not hijack an unrelated variable of the host."""

        assert "API_KEY" not in env_name_candidates("app", "api_key")

    def test_other_section_uses_section_prefix(self):
        candidates = env_name_candidates("whisper", "model")

        assert candidates[0] == "MPT_WHISPER_MODEL"
        assert "WHISPER_MODEL" in candidates


class TestValueCoercion:
    def test_bool_accepts_common_spellings(self):
        assert coerce_env_value("true", False) is True
        assert coerce_env_value("1", False) is True
        assert coerce_env_value("YES", False) is True
        assert coerce_env_value("off", True) is False

    def test_bool_rejects_garbage(self):
        with pytest.raises(EnvValueError):
            coerce_env_value("maybe", False)

    def test_int_is_parsed(self):
        assert coerce_env_value("8080", 8080) == 8080

    def test_float_is_parsed(self):
        assert coerce_env_value("0.5", 0.2) == 0.5

    def test_list_is_split_on_commas(self):
        assert coerce_env_value("a, b ,c", []) == ["a", "b", "c"]

    def test_empty_list_value_yields_empty_list(self):
        assert coerce_env_value("", []) == []

    def test_string_is_kept(self):
        assert coerce_env_value("gemini", "moonshot") == "gemini"


class TestCollectOverrides:
    @staticmethod
    def _config():
        return {
            "log_level": "DEBUG",
            "listen_port": 8080,
            "app": {
                "llm_provider": "moonshot",
                "gemini_api_key": "",
                "pexels_api_keys": [],
                "hide_config": False,
            },
            "whisper": {"model": "base"},
        }

    def test_collects_prefixed_variables(self):
        overrides, errors = collect_env_overrides(
            self._config(),
            {"MPT_APP_LLM_PROVIDER": "gemini", "MPT_LOG_LEVEL": "INFO"},
        )

        assert errors == []
        assert {(o.section, o.key, o.value) for o in overrides} == {
            (None, "log_level", "INFO"),
            ("app", "llm_provider", "gemini"),
        }

    def test_collects_unprefixed_provider_variables(self):
        overrides, errors = collect_env_overrides(
            self._config(), {"GEMINI_API_KEY": "secret"}
        )

        assert errors == []
        assert overrides[0].value == "secret"

    def test_prefixed_name_wins_over_unprefixed(self):
        overrides, _ = collect_env_overrides(
            self._config(),
            {"MPT_APP_LLM_PROVIDER": "gemini", "LLM_PROVIDER": "deepseek"},
        )

        assert [o.value for o in overrides] == ["gemini"]

    def test_ignores_generic_unprefixed_app_key(self):
        overrides, _ = collect_env_overrides(self._config(), {"API_KEY": "nope"})

        assert overrides == []

    def test_coerces_list_values(self):
        overrides, _ = collect_env_overrides(
            self._config(), {"PEXELS_API_KEYS": "k1,k2"}
        )

        assert overrides[0].value == ["k1", "k2"]

    def test_reports_invalid_value_without_raising(self):
        overrides, errors = collect_env_overrides(
            self._config(), {"MPT_LISTEN_PORT": "not-a-number"}
        )

        assert overrides == []
        assert len(errors) == 1
        assert "MPT_LISTEN_PORT" in errors[0]

    def test_valid_variables_are_kept_when_another_one_is_invalid(self):
        overrides, errors = collect_env_overrides(
            self._config(),
            {"MPT_LISTEN_PORT": "not-a-number", "MPT_APP_LLM_PROVIDER": "gemini"},
        )

        assert len(errors) == 1
        assert [o.key for o in overrides] == ["llm_provider"]


class TestWithoutEnvOverrides:
    def test_removes_overridden_keys_from_a_copy(self):
        config = {"app": {"llm_provider": "gemini", "api_key": "kept"}, "log_level": "INFO"}
        overrides, _ = collect_env_overrides(
            config, {"MPT_APP_LLM_PROVIDER": "gemini", "MPT_LOG_LEVEL": "INFO"}
        )

        result = without_env_overrides(config, overrides)

        assert "log_level" not in result
        assert "llm_provider" not in result["app"]
        assert result["app"]["api_key"] == "kept"

    def test_does_not_mutate_the_input(self):
        config = {"app": {"llm_provider": "gemini"}}
        overrides, _ = collect_env_overrides(
            config, {"MPT_APP_LLM_PROVIDER": "gemini"}
        )

        without_env_overrides(config, overrides)

        assert config["app"]["llm_provider"] == "gemini"

    def test_does_not_mutate_a_shared_nested_section(self):
        """The section object is shared with the live configuration."""

        section = {"llm_provider": "gemini"}
        config = {"app": section}
        overrides, _ = collect_env_overrides(
            config, {"MPT_APP_LLM_PROVIDER": "gemini"}
        )

        without_env_overrides(config, overrides)

        assert "llm_provider" in section


class TestEnvFileIsIgnoredByGit:
    def test_env_file_is_excluded_from_version_control(self):
        repository_root = Path(__file__).resolve().parents[2]
        ignore_file = repository_root / ".gitignore"
        patterns = [
            line.strip()
            for line in ignore_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

        assert any(
            pattern in (".env", "/.env", "**/.env") for pattern in patterns
        ), "the .env file must stay out of version control"


class TestRuntimeIntegration:
    """The environment layer has to work against the live configuration."""

    # A controlled configuration, so the result never depends on the
    # developer's own config.toml.
    CONTROLLED_CONFIG = {
        "log_level": "DEBUG",
        "listen_port": 8080,
        "app": {
            "llm_provider": "moonshot",
            "gemini_api_key": "",
            "pexels_api_keys": [],
            "hide_config": False,
        },
        "whisper": {"model": "base"},
    }

    @staticmethod
    def _restore(original_cfg, original_app, original_overrides, original_log_level):
        config.app.clear()
        config.app.update(original_app)
        config._cfg.clear()
        config._cfg.update(original_cfg)
        config._env_overrides.clear()
        config._env_overrides.extend(original_overrides)
        config.log_level = original_log_level

    @staticmethod
    def _controlled(extra_app=None):
        """Return a copy of the controlled configuration."""

        controlled = {
            section: dict(values) if isinstance(values, dict) else values
            for section, values in TestRuntimeIntegration.CONTROLLED_CONFIG.items()
        }
        if extra_app:
            controlled["app"].update(extra_app)
        return controlled

    def _run_with(self, environ, extra_app=None):
        """Apply the environment to a controlled configuration."""

        original_cfg = dict(config._cfg)
        original_app = dict(config.app)
        original_overrides = list(config._env_overrides)
        original_log_level = config.log_level
        try:
            controlled = self._controlled(extra_app)
            config._cfg.clear()
            config._cfg.update(controlled)
            config.app.clear()
            config.app.update(controlled["app"])
            with patch.dict(os.environ, environ):
                with patch.object(config, "_environment_file", return_value=""):
                    config._apply_environment_overrides()
            return dict(config.app)
        finally:
            self._restore(
                original_cfg, original_app, original_overrides, original_log_level
            )

    def test_environment_value_wins_over_the_config_file(self):
        applied = self._run_with({"MPT_APP_LLM_PROVIDER": "gemini"})

        assert applied["llm_provider"] == "gemini"

    def test_environment_value_is_not_written_to_the_config_file(self):
        """A secret supplied through the environment must not reach the disk."""

        original_cfg = dict(config._cfg)
        original_app = dict(config.app)
        original_overrides = list(config._env_overrides)
        original_log_level = config.log_level
        try:
            controlled = self._controlled()
            config._cfg.clear()
            config._cfg.update(controlled)
            config.app.clear()
            config.app.update(controlled["app"])
            with patch.dict(os.environ, {"MPT_APP_GEMINI_API_KEY": "secret-value"}):
                with patch.object(config, "_environment_file", return_value=""):
                    config._apply_environment_overrides()

            assert config.app["gemini_api_key"] == "secret-value"

            with TemporaryDirectory() as temp_dir:
                config_path = Path(temp_dir) / "config.toml"
                with (
                    patch.object(config, "root_dir", temp_dir),
                    patch.object(config, "config_file", str(config_path)),
                ):
                    config.save_config()

                written = config_path.read_text(encoding="utf-8")
                saved_config = tomllib.loads(written)
                assert "gemini_api_key" not in saved_config.get("app", {})
                assert "secret-value" not in written

            # The in-memory configuration keeps the value for the running task.
            assert config.app["gemini_api_key"] == "secret-value"
        finally:
            self._restore(
                original_cfg, original_app, original_overrides, original_log_level
            )

    def test_env_file_from_the_runtime_root_is_loaded(self):
        original_cfg = dict(config._cfg)
        original_app = dict(config.app)
        original_overrides = list(config._env_overrides)
        original_log_level = config.log_level
        try:
            with TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".env"
                env_path.write_text(
                    "MPT_APP_LLM_PROVIDER=gemini\nGEMINI_API_KEY=from-file\n",
                    encoding="utf-8",
                )
                controlled = self._controlled()
                config._cfg.clear()
                config._cfg.update(controlled)
                config.app.clear()
                config.app.update(controlled["app"])
                with patch.dict(os.environ, {}, clear=False):
                    for name in (
                        "MPT_ENV_FILE",
                        "MPT_APP_LLM_PROVIDER",
                        "GEMINI_API_KEY",
                        "MPT_APP_GEMINI_API_KEY",
                    ):
                        os.environ.pop(name, None)
                    with patch.object(config, "root_dir", temp_dir):
                        config._apply_environment_overrides()

                assert config.app["llm_provider"] == "gemini"
                assert config.app["gemini_api_key"] == "from-file"
        finally:
            self._restore(
                original_cfg, original_app, original_overrides, original_log_level
            )

    def test_real_environment_wins_over_the_env_file(self):
        original_cfg = dict(config._cfg)
        original_app = dict(config.app)
        original_overrides = list(config._env_overrides)
        original_log_level = config.log_level
        try:
            with TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".env"
                env_path.write_text("MPT_APP_LLM_PROVIDER=gemini\n", encoding="utf-8")
                controlled = self._controlled()
                config._cfg.clear()
                config._cfg.update(controlled)
                config.app.clear()
                config.app.update(controlled["app"])
                with patch.dict(
                    os.environ, {"MPT_APP_LLM_PROVIDER": "deepseek"}
                ):
                    with patch.object(config, "root_dir", temp_dir):
                        config._apply_environment_overrides()

                assert config.app["llm_provider"] == "deepseek"
        finally:
            self._restore(
                original_cfg, original_app, original_overrides, original_log_level
            )

    def test_invalid_value_is_ignored_and_the_file_value_is_kept(self):
        original_cfg = dict(config._cfg)
        original_app = dict(config.app)
        original_overrides = list(config._env_overrides)
        original_log_level = config.log_level
        try:
            controlled = self._controlled()
            config._cfg.clear()
            config._cfg.update(controlled)
            config.app.clear()
            config.app.update(controlled["app"])
            with patch.dict(os.environ, {"MPT_APP_HIDE_CONFIG": "not-a-boolean"}):
                with patch.object(config, "_environment_file", return_value=""):
                    with patch.object(config.logger, "error") as error_mock:
                        config._apply_environment_overrides()

            assert config.app["hide_config"] is False
            assert error_mock.called
        finally:
            self._restore(
                original_cfg, original_app, original_overrides, original_log_level
            )
