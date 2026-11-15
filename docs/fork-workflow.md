# Fork Workflow and Local Setup

Operational notes for this fork of `harry0703/MoneyPrinterTurbo`. It describes how
the repository is wired to its upstream, how the local configuration is generated,
which credentials are actually required, and how the API is protected.

## Repository topology

The working copy was originally a plain clone of upstream. It is now a fork.

| Remote | URL | Purpose |
| --- | --- | --- |
| `origin` | `git@github.com:juanvs23/MoneyPrinterTurbo.git` | This fork. `git push` goes here. |
| `upstream` | `git@github.com:harry0703/MoneyPrinterTurbo.git` | Original project. Read-only in practice. |

`upstream`'s **push** URL is deliberately pinned to the original repository, so that
a stray `git push upstream` cannot write to it even if push permissions are ever
granted by mistake.

`main` tracks `origin/main`.

### Creating the fork from an existing clone

The fork is a server-side operation; the local clone never has to be re-downloaded.
A full clone keeps the entire history, so the working copy becomes a working copy
of the fork with no divergence and no rebase.

```sh
gh auth switch --user juanvs23          # gh CLI is authenticated to two accounts
gh repo fork harry0703/MoneyPrinterTurbo --clone=false
git remote rename origin upstream
git remote add origin git@github.com:juanvs23/MoneyPrinterTurbo.git
git remote set-url --push upstream git@github.com:harry0703/MoneyPrinterTurbo.git
git fetch upstream
git push -u origin main
```

Note: `gh repo fork <repo> --remote=false` is rejected when a repository argument
is supplied. With an argument, `gh` leaves the local remotes untouched, which is
what makes the explicit `git remote` steps above necessary.

### Branches

`main` is the synchronization line with upstream. Feature work goes on a branch:

```sh
git switch -c feature/<name>
```

Current work branch: `feature/bootstrap-local-setup`.

### Absorbing upstream updates

```sh
git fetch upstream
git merge upstream/main
git push origin main
```

Upstream publishes frequently. Keeping this fork's changes in **new files** rather
than edits to the translated READMEs keeps those merges conflict-free.

## Local configuration

`config.toml` is the runtime configuration. It holds every provider API key, so it
is excluded from Git by design (`.gitignore:2`). It is generated locally from
`config.example.toml`; it is never committed and never pushed.

```sh
cp config.example.toml config.toml
```

Generated locally with these deviations from the example:

| Setting | Value | Reason |
| --- | --- | --- |
| `log_level` | `INFO` | The example ships `DEBUG`, which is noisy for normal operation. |
| `api_key` | 32 hex characters, randomly generated | Enables authentication for `/api/v1` and `/tasks`. |
| `listen_host` | `0.0.0.0` | Required inside a container: the port is published to the host separately. |
| `llm_provider` | `gemini` | Set through the environment. Google Gemini writes the script. |
| `video_source` | `local` | Set through the environment. Uses your own footage, with no API key and no per-video cost. |
| `subtitle_provider` | `edge` | Edge TTS needs no account and no key. |

`listen_host = "0.0.0.0"` and `api_key` are a deliberate pair: the service must
listen on all interfaces to be reachable through Docker's port mapping, and the
authentication is what protects it there. Every Compose file in this repository
publishes on `127.0.0.1` only, so the service is not reachable from the network by
default.

## Environment overrides

Every key in `config.toml` can also be supplied through an environment variable.
This is the twelve-factor way to configure a deployment, and it keeps secrets out
of the configuration file entirely.

The file is `.env`, in the runtime root next to `config.toml`. It is excluded by
`.gitignore` and must never be committed. Copy `.env.example` to get started.

```sh
cp .env.example .env
```

The runtime reads `.env` on startup, then applies the environment on top of
`config.toml`. **The environment wins.**

### Naming

The canonical name is always prefixed, so it cannot collide with an unrelated
variable of the host:

| Configuration key | Environment variable |
| --- | --- |
| `log_level` | `MPT_LOG_LEVEL` |
| `[app] gemini_api_key` | `MPT_APP_GEMINI_API_KEY` |
| `[app] llm_provider` | `MPT_APP_LLM_PROVIDER` |
| `[whisper] model` | `MPT_WHISPER_MODEL` |
| `[azure] api_key` | `MPT_AZURE_API_KEY` |

An unprefixed name is also accepted for provider-qualified keys, because the
codebase already reads several variables that way: `GEMINI_API_KEY`,
`PEXELS_API_KEYS`, `WHISPER_MODEL`. Inside the `[app]` section the unprefixed
form is only accepted for provider-qualified keys; `MPT_APP_API_KEY` and
`MPT_APP_TLS_VERIFY` always require the prefix, so a generic `API_KEY` in the
host environment cannot silently change the server's own authentication.

### Types

The type follows the value in `config.toml`:

| Kind | Example |
| --- | --- |
| List | `PEXELS_API_KEYS=key-1,key-2` |
| Boolean | `MPT_APP_HIDE_CONFIG=true` (`1/0/true/false/yes/no/on/off`) |
| Integer | `MPT_LISTEN_PORT=8080` |
| String | `MPT_APP_LLM_PROVIDER=gemini` |

A malformed value is reported in the log and ignored, so one typo does not stop
the WebUI, the API and the CLI at once.

### Precedence and persistence

1. A real environment variable wins over the `.env` file.
2. The environment wins over `config.toml`.
3. **Values supplied through the environment are never written back to
   `config.toml`.** `save_config` removes them from the serialized file, so a
   secret that lives in `.env` stays there. The in-memory configuration keeps
   the value for the running process.

This is why a secret can be moved out of `config.toml` entirely: set it in
`.env`, clear it in the file, and the application behaves identically.

### Docker

`MPT_HOME` selects the runtime root. Inside a container the `.env` file does not
have to be mounted: the compose file can pass the variables directly.

```yaml
services:
  api:
    env_file:
      - .env
```

### Pointing the model at Google

`gemini` is a registered LLM provider (`app/models/llm_provider.py:312`).

```sh
MPT_APP_LLM_PROVIDER=gemini
MPT_APP_GEMINI_API_KEY=<key from https://aistudio.google.com/app/apikey>
```

The default model is `gemini-3.1-pro-preview`; override it with
`MPT_APP_GEMINI_MODEL_NAME`. The provider needs no base URL, and the
`google-genai` SDK is already a dependency.

### Running the test suite

The suite is isolated from the local configuration: `test/conftest.py` points
`MPT_HOME` at a temporary directory, neutralizes the `.env` file and resets the
API key. Running the tests therefore never rewrites `config.toml` and never
writes into the repository `storage/` directory.

Without that isolation the WebUI, which `test/services/test_webui_startup.py`
starts in a subprocess, would save its own configuration over the developer's
`config.toml` on every test run.

### Credentials required for a first render

Exactly one credential blocks a complete first video:

| Credential | Used for | Where to get it |
| --- | --- | --- |
| `gemini_api_key` | Script generation | <https://aistudio.google.com/app/apikey> |

The material comes from your own footage, so there is no stock-footage key to
obtain. Pexels is no longer an option for new keys: it paused their issuance
on 2026-09-30 without a reopening date.

Everything else in the default path works without any credential:

- **Narration**: Edge TTS is free and requires no registration.
- **Subtitles**: Edge timings, or Whisper locally (see
  [Runtime Resources](runtime-resources.md) for the Whisper caveats).
- **Material**: your own files in `storage/local_videos`.
- **Composition, muxing and MP4 export**: local, via MoviePy and FFmpeg.

### Paths that need no key at all

These are the options to prefer when the objective is zero marginal cost:

| Capability | No-credential option | Configuration |
| --- | --- | --- |
| Script generation | Write the script yourself | Paste it into the `video_script` field, or pass `--video-script` on the CLI. The LLM is only called when the field is empty (`app/services/task.py:366`). |
| Search keywords | Write them yourself | The same short-circuit applies to `video_terms` (`app/services/task.py:387`). |
| LLM provider | Ollama, OpenAI Codex, Claude Code | `llm_provider` in the registry (`app/models/llm_provider.py:195`). |
| Material | Your own footage | `video_source = "local"`. |
| Music | Bundled tracks | `bgm_type = "random"`. |

## Material source

`MPT_APP_VIDEO_SOURCE=local` uses your own footage. It is the only source that
needs no API key, no account and no per-video cost, and it is what this fork is
configured with.

### Where the files go

The material directory is `local_videos` inside the runtime root:

```
storage/local_videos/     # source checkout
```

Two ways to fill it:

- Copy the files there directly.
- Upload them from the WebUI material picker, which posts them to the
  `/video_materials` endpoint (`app/controllers/v1/video.py:479`). The endpoint
  stores each upload under a UUID name and lists the directory back through
  `GET /video_materials` (`app/controllers/v1/video.py:448`).

The CLI takes the directory directly: `--video-materials <dir>`.

### What the pipeline accepts

| Rule | Value | Source |
| --- | --- | --- |
| Video formats | `.mp4` `.mov` `.avi` `.flv` `.mkv` `.webm` | `app/services/material_upload.py:25` |
| Image formats | `.jpg` `.jpeg` `.png` `.bmp` | `app/services/material_upload.py:26` |
| Minimum resolution | 480px on the shorter side, 470px with the tolerance | `app/services/video.py:85` |
| Maximum upload size | 200 MB per video, 20 MB per image | `app/services/material_upload.py:17` |

Files outside `local_videos` are rejected by design: the material path comes
from the task parameters, and the renderer resolves it inside that directory
only (`app/services/video.py:2141`). A file that fails the resolution check is
skipped with a warning instead of failing the whole task.

Images are rendered as a slow zoom clip (`app/services/video.py:2063`), so a
folder of stills is a valid material source too.

### What changes with `local`

The LLM only writes the script. Search-keyword generation is skipped entirely
(`app/services/task.py:1756`), because there is nothing to search for: the
material is already yours.

### Stock alternatives

| Source | Key | Free tier | Notes |
| --- | --- | --- | --- |
| `coverr` | <https://coverr.co/developers> | 50 calls/hour | Key issued instantly, no credit card. Filters vertical footage natively (`is_vertical:true`). |
| `pixabay` | <https://pixabay.com/api/docs/> | 100 requests/minute | Responses must be cached for 24 hours; the runtime already caches every stock search for exactly that long (`app/services/material_cache.py:24`). |
| `pexels` | — | — | **Paused.** Pexels stopped issuing new API keys on 2026-09-30, with no reopening date. Keys issued before that date keep working. |

## Authentication behaviour

`verify_token` (`app/controllers/base.py:47`) is a **no-op when `app.api_key` is
empty**. With a key configured, it requires an exactly-once `x-api-key` request
header, compares it in constant time, and rejects duplicated headers.

The `/tasks` static mount is mounted outside the router, so it cannot use the
router dependency. It is protected by an HTTP middleware that calls the same
verification function (`app/asgi.py:288`).

Verified against a running container:

```
GET /api/v1/tasks   without x-api-key  -> HTTP 401
GET /tasks/         without x-api-key  -> HTTP 401
GET /api/v1/tasks   with x-api-key      -> HTTP 200
GET /ping           without x-api-key  -> HTTP 200   (health endpoint, unauthenticated by design)
```

Two consequences worth knowing:

1. **The Streamlit WebUI is not affected by `api_key`.** The WebUI calls the task
   pipeline in-process (`app/services/webui_task.py:198`); it never authenticates
   against the HTTP API. Setting a key therefore does not break the UI.
2. **A browser address bar cannot send a custom header.** Task artifacts must be
   downloaded by an HTTP client that can set `x-api-key`.

## Running locally

### Docker (recommended)

```sh
docker compose up -d
```

`docker-compose.yml` builds from source and bind-mounts the whole project.
`docker-compose.release.yml` uses the published GHCR image and mounts only
`config.toml` and `storage`. Both publish on `127.0.0.1` only.

The published image is described in [Runtime Resources](runtime-resources.md).

### Source checkout

Requires Python 3.11+, FFmpeg with `libx264`, and FFprobe on `PATH`.

```sh
uv sync
uv run mpt cli --help
uv run mpt webui
```

## Local layout after a run

```
config.toml                       local, untracked, holds every API key
storage/tasks/<task_id>/script.json
storage/tasks/<task_id>/audio.mp3
storage/tasks/<task_id>/subtitle.srt
storage/tasks/<task_id>/combined-<n>.mp4
storage/tasks/<task_id>/final-<n>.mp4
storage/cache_videos/             downloaded stock footage, the main disk consumer
storage/auth/                     Codex / ChatGPT OAuth credentials
```

## Related documents

- [Pipeline and Costs](pipeline-and-costs.md) — what each stage does and what it costs.
- [Runtime Resources](runtime-resources.md) — image size, measured resources, sizing.
- Upstream: [OpenAI - Codex](codex-provider.md) and [ChatGPT Provider](chatgpt-provider.md).
