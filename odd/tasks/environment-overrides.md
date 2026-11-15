# Feature: Environment Overrides

## Objective

Allow every key in `config.toml` to be supplied through an environment variable,
so a deployment can be configured without editing the configuration file, and a
secret can live in a file that is never committed.

## Problem

The configuration lives in a single TOML file that holds every provider API key.
That file is excluded from Git, which is correct, but it forces three problems:

1. **Secrets and settings share one file.** There is no way to inject a key from
   the environment without editing the file, so CI, Docker and a local checkout
   all need their own copy of the same document.
2. **The file is rewritten by the application.** `save_config` serializes the
   in-memory configuration, so a secret that arrives through the environment
   would be written straight back into `config.toml`, where it does not belong.
3. **The test suite depends on the developer's local file.** A configured
   `api_key` locked the API tests out, and the WebUI that
   `test/services/test_webui_startup.py` starts in a subprocess rewrote the
   developer's real `config.toml` on every test run.

## Why

The fork exists to produce videos on a machine that is configured once and then
left alone. Moving the secrets and the deployment settings into the environment
makes that possible, and it removes the failure mode where a running application
writes a key it was only given for the length of one request.

## Scope

- A new module `app/config/env_overrides.py` that resolves environment
  variables to configuration keys and coerces them to the right type.
- Integration in `app/config/config.py`: load the `.env` file, apply the
  overrides to the in-memory configuration, and keep them out of the saved file.
- A `.env.example` template.
- Test isolation in `test/conftest.py`, so the suite never touches the local
  configuration.

Out of scope: unifying the 19 hand-written `os.environ` reads that already
exist in the service layer. They keep working, and several of them use names
that the generic mapping already accepts.

## Constraints

- **No new dependency.** `uv.lock` is frozen and CI runs `uv sync --frozen`, so
  adding `python-dotenv` would require regenerating the lockfile. The parser is
  a small module instead.
- **The environment wins over the file.** That is the twelve-factor expectation,
  and it is what makes `.env` a source of truth rather than a fallback.
- **Environment values never reach the disk.** A secret in the environment must
  not be serialized into `config.toml`.
- **A malformed value never stops the application.** The WebUI, the API and the
  CLI would all fail together otherwise; the value is reported and skipped.
- **The mapping is mechanical.** No per-provider table, so a new provider
  inherits the behaviour without a code change.

## Acceptance criteria

- [x] Every configuration key can be overridden by an environment variable.
- [x] The canonical name is prefixed (`MPT_APP_GEMINI_API_KEY`) and cannot
      collide with an unrelated variable of the host.
- [x] The unprefixed form works for provider-qualified keys, matching the
      convention the codebase already uses.
- [x] Types follow the value in `config.toml`: lists, booleans, integers and
      floats are coerced, not carried as strings.
- [x] An invalid value is reported in the log and ignored, and the value from
      the configuration file is kept.
- [x] Environment values are not written to `config.toml` by `save_config`.
- [x] The `.env` file is excluded from version control.
- [x] The test suite is isolated from the local configuration and from the
      local `.env` file.
- [x] The full suite passes and the local `config.toml` is not modified by it.

## Verification

- 41 new tests in `test/services/test_env_overrides.py`, covering the parser, the
  name resolution, the type coercion, the override collection and the runtime
  integration.
- Full suite: 3384 passed, 71 skipped, 0 failed.
- `config.toml` verified unchanged by the suite: identical checksum and
  identical modification time before and after the run.
- The application was run against a real `.env` and reported the expected
  provider and API key.

## Delivery

- **Strategy:** `exception-ok`. The maintainer explicitly accepted a
  `size:exception` on 2026-11-14 for the feature pull request.
- **Chain:** two stacked pull requests. PR #2 (`docs/fork-setup-documentation`,
  +718/-0, 5 files) is the documentation set and merges first. PR #4
  (`feat/environment-overrides`, +1256/-6, 7 files) is this feature and merges
  second, based on the PR #2 branch.
- **Why PR #4 is not split:** the bulk is the test file, and the tests belong
  with the behaviour they verify. Splitting the suite isolation from the
  feature would leave an intermediate state in which the suite still rewrites
  the developer's `config.toml`. The unit stays whole.
- **Commits:** `0cadfc3` (the feature, with its tests and template) and
  `b943e5a` (the local material source and the Pexels pause), plus the
  delivery record in this document.
- **Rollback boundary:** revert `app/config/env_overrides.py`,
  `app/config/config.py`, `test/conftest.py`,
  `test/services/test_env_overrides.py` and `.env.example`. That removes the
  environment layer and the test isolation without touching the documentation
  set from PR #2.

## Notes

- The canonical naming keeps a prefixed form for every key, and the unprefixed
  form is a convenience for provider-qualified keys. `MPT_APP_API_KEY` and
  `MPT_APP_TLS_VERIFY` always require the prefix: a bare `API_KEY` in the host
  environment must not change the server's own authentication.
- `MPT_HOME` selects the runtime root. The test session points it at a
  temporary directory, which isolates the configuration file, the storage
  directory and the WebUI subprocess at the same time.
- The configured material source is `local`. Pexels paused the issuance of new
  API keys on 2026-09-30 without a reopening date, so the stock source that
  the upstream default points at cannot be used by a new installation. `local`
  needs no key, no account and no per-video cost, and it keeps the pipeline on
  the LLM only: the search-keyword generation is skipped for it
  (`app/services/task.py:1756`).
- Coverr and Pixabay still issue keys and remain configured as the stock
  alternatives. The runtime caches every stock search for 24 hours
  (`app/services/material_cache.py:24`), which already satisfies the Pixabay
  caching clause.
