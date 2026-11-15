"""Session-wide isolation of the local configuration.

The test suite must produce the same result on every machine. Three local
settings used to leak into it:

* ``config.toml``. A developer who configured an API key locally locked out the
  API tests, because the routes require the ``x-api-key`` header. The suite
  now runs with the same unauthenticated default that a fresh checkout has.
* ``.env``. The runtime reads it on import, so a local file silently changed
  the provider and the model under test.
* The configuration file itself. A background flush thread could rewrite the
  developer's real ``config.toml`` while the suite was running.

The environment is neutralized before ``app.config`` is imported, because that
module reads the environment once, at import time.
"""

import os

# Neutralize the local .env file before the configuration module reads it.
os.environ["MPT_ENV_FILE"] = os.devnull

# Drop every local override of the runtime configuration, except the
# MPT_ENV_FILE that neutralizes the .env file.
for _name in [name for name in os.environ if name.startswith("MPT_")]:
    if _name != "MPT_ENV_FILE":
        os.environ.pop(_name, None)

import tempfile  # noqa: E402

# Isolate the runtime root for the whole session. The WebUI is started in a
# subprocess by test_webui_startup.py, and that subprocess writes the
# configuration file it loads. Without an isolated root it would rewrite the
# developer's own config.toml and pollute the repository storage directory on
# every test run.
_TEST_ROOT = tempfile.mkdtemp(prefix="moneyprinterturbo-tests-")
os.environ["MPT_HOME"] = _TEST_ROOT

import pytest  # noqa: E402

from app.config import config  # noqa: E402

# The API tests exercise the unauthenticated local default, exactly like a
# fresh checkout where config.toml still holds an empty api_key.
config.app["api_key"] = ""

# No test may write to the developer's configuration file.
config.root_dir = _TEST_ROOT
config.config_file = os.path.join(_TEST_ROOT, "config.toml")


@pytest.fixture
def isolated_config_file():
    """Yield a configuration file path that no test shares."""

    with tempfile.TemporaryDirectory(prefix="mpt-config-") as temp_dir:
        yield os.path.join(temp_dir, "config.toml")
