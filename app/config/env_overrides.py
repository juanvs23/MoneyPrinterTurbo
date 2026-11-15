"""Environment-variable overrides for the runtime configuration.

Every key in ``config.toml`` can be supplied through an environment variable.
The mapping is mechanical, so no per-provider table has to be maintained and a
new provider inherits the behaviour for free.

The canonical name is always prefixed, so it cannot collide with an unrelated
variable of the host:

* Top-level keys: ``log_level`` -> ``MPT_LOG_LEVEL``.
* The ``[app]`` section: ``gemini_api_key`` -> ``MPT_APP_GEMINI_API_KEY``.
* Every other section: ``[whisper] model`` -> ``MPT_WHISPER_MODEL``.

An unprefixed name is also accepted, because the codebase already reads several
provider variables that way: ``MOONSHOT_API_KEY``, ``WHISPER_MODEL``,
``AZURE_API_KEY``. Inside the ``[app]`` section the unprefixed form is only
accepted for provider-qualified keys, so a generic ``api_key`` cannot hijack an
unrelated variable. ``MPT_APP_API_KEY`` and ``MPT_APP_TLS_VERIFY`` are the only
app keys that always require the prefix.

Values from the environment take precedence over ``config.toml``. They are
applied to the in-memory configuration only. ``save_config`` removes them from
the serialized file, so a secret supplied through the environment is never
written back to disk.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping

# Section whose keys are already qualified, so no section prefix is needed.
BARE_ENV_SECTION = "app"

# App keys with a short, generic name. An unrelated program could set the same
# variable in the same environment, so these require the prefixed form.
GENERIC_APP_KEYS = frozenset({"api_key", "tls_verify"})

# Environment variable that overrides the location of the .env file.
ENV_FILE_VARIABLE = "MPT_ENV_FILE"

_ENV_LINE = re.compile(
    r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)$"
)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


class EnvValueError(ValueError):
    """Raised when an environment value cannot be coerced to the expected type."""


@dataclass(frozen=True)
class EnvOverride:
    """A configuration value supplied by the environment."""

    section: str | None
    key: str
    env_name: str
    value: Any


def parse_env_file(text: str) -> dict[str, str]:
    """Parse the contents of a ``.env`` file into a mapping.

    Supported syntax: ``KEY=VALUE`` lines, an optional ``export`` prefix,
    single- or double-quoted values, and ``#`` comments on their own line or
    after an unquoted value. Multiline values are not supported.
    """

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE.match(line)
        if match is None:
            continue
        values[match.group("key")] = _parse_env_value(match.group("value"))
    return values


def _parse_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        quote = value[0]
        value = value[1:-1]
        if quote == '"':
            value = (
                value.replace("\\n", "\n")
                .replace("\\t", "\t")
                .replace('\\"', '"')
                .replace("\\\\", "\\")
            )
        return value
    # An unquoted value ends at an inline comment.
    comment = value.find(" #")
    if comment != -1:
        value = value[:comment].strip()
    return value


def load_env_file(path: str | Path) -> dict[str, str]:
    """Read a ``.env`` file, returning an empty mapping when it cannot be read."""

    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    return parse_env_file(text)


def apply_env_file_to_environ(
    path: str | Path, environ: MutableMapping[str, str] | None = None
) -> dict[str, str]:
    """Merge a ``.env`` file into the environment without overriding real values.

    A variable that is already set in the environment always wins over the
    file, which is the behaviour every container platform assumes.
    """

    target = os.environ if environ is None else environ
    loaded = load_env_file(path)
    for name, value in loaded.items():
        target.setdefault(name, value)
    return loaded


def env_name_for(section: str | None, key: str) -> str:
    """Return the canonical environment variable name for a configuration key.

    The canonical name is always prefixed, so it cannot collide with an
    unrelated variable of the host: ``MPT_LOG_LEVEL``, ``MPT_APP_GEMINI_API_KEY``,
    ``MPT_WHISPER_MODEL``.
    """

    if section is None:
        return f"MPT_{key.upper()}"
    return f"MPT_{section.upper()}_{key.upper()}"


def env_name_candidates(section: str | None, key: str) -> list[str]:
    """Return the environment variable names accepted for a configuration key.

    The canonical prefixed name wins. The unprefixed name is also accepted
    because the codebase already reads several provider variables that way
    (``OFOX_API_KEY``, ``MINIMAX_API_KEY``). Within the ``[app]`` section the
    unprefixed form is only accepted for keys that carry a provider prefix,
    such as ``moonshot_api_key`` -> ``MOONSHOT_API_KEY``. Generic keys like
    ``api_key`` would be too easy to collide with an unrelated variable, so
    they require the ``MPT_APP_`` prefix.
    """

    candidates = [env_name_for(section, key)]

    if section is None:
        candidates.append(key.upper())
        return candidates

    if section != BARE_ENV_SECTION:
        candidates.append(f"{section}_{key}".upper())
        return candidates

    if "_" in key and key not in GENERIC_APP_KEYS:
        candidates.append(key.upper())
    return candidates



def coerce_env_value(raw: str, template: Any) -> Any:
    """Convert an environment string to the type of the value it replaces.

    The type is taken from the current configuration value, so ``pexels_api_keys``
    stays a list of strings, ``log_requests`` stays a boolean and
    ``listen_port`` stays an integer. A key that is absent from the
    configuration keeps its raw string value.
    """

    if isinstance(template, bool):
        lowered = raw.strip().lower()
        if lowered in _TRUE_VALUES:
            return True
        if lowered in _FALSE_VALUES:
            return False
        raise EnvValueError(
            f"expected a boolean value, got {raw.strip()!r}"
        )
    if isinstance(template, int):
        try:
            return int(raw.strip())
        except ValueError as exc:
            raise EnvValueError(f"expected an integer, got {raw.strip()!r}") from exc
    if isinstance(template, float):
        try:
            return float(raw.strip())
        except ValueError as exc:
            raise EnvValueError(f"expected a number, got {raw.strip()!r}") from exc
    if isinstance(template, (list, tuple)):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def collect_env_overrides(
    config: Mapping[str, Any], environ: Mapping[str, str]
) -> tuple[list[EnvOverride], list[str]]:
    """Find every configuration key that the environment overrides.

    Returns the overrides and a list of human-readable errors for values that
    could not be coerced. A malformed value never stops the application: it is
    reported and skipped, leaving the value from the configuration file in
    place.
    """

    overrides: list[EnvOverride] = []
    errors: list[str] = []

    for section, values in config.items():
        if isinstance(values, Mapping):
            for key, template in values.items():
                _collect_one(
                    section, key, template, environ, overrides, errors
                )
        else:
            _collect_one(None, section, values, environ, overrides, errors)

    return overrides, errors


def _collect_one(
    section: str | None,
    key: str,
    template: Any,
    environ: Mapping[str, str],
    overrides: list[EnvOverride],
    errors: list[str],
) -> None:
    for name in env_name_candidates(section, key):
        if name not in environ:
            continue
        try:
            value = coerce_env_value(environ[name], template)
        except (EnvValueError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
            return
        overrides.append(EnvOverride(section, key, name, value))
        return


def without_env_overrides(
    config: Mapping[str, Any], overrides: list[EnvOverride]
) -> dict[str, Any]:
    """Return a copy of ``config`` without the values that the environment owns.

    The input is never mutated, so the in-memory configuration keeps the
    environment values while the serialized file stays free of them.
    """

    result = dict(config)
    for override in overrides:
        if override.section is None:
            result.pop(override.key, None)
            continue
        section = result.get(override.section)
        if not isinstance(section, Mapping):
            continue
        updated = dict(section)
        updated.pop(override.key, None)
        result[override.section] = updated
    return result
