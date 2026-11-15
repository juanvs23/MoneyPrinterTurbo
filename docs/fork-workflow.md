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
| `llm_provider` | `moonshot` | Upstream default. |
| `video_source` | `pexels` | Upstream default. Requires a Pexels key. |
| `subtitle_provider` | `edge` | Edge TTS needs no account and no key. |

`listen_host = "0.0.0.0"` and `api_key` are a deliberate pair: the service must
listen on all interfaces to be reachable through Docker's port mapping, and the
authentication is what protects it there. Every Compose file in this repository
publishes on `127.0.0.1` only, so the service is not reachable from the network by
default.

### Credentials required for a first render

Exactly two credentials block a complete first video:

| Credential | Used for | Where to get it |
| --- | --- | --- |
| `moonshot_api_key` | Script and search-keyword generation | <https://platform.kimi.com> |
| `pexels_api_keys` | Stock footage search | <https://www.pexels.com/api/> |

Everything else in the default path works without any credential:

- **Narration**: Edge TTS is free and requires no registration.
- **Subtitles**: Edge timings, or Whisper locally (see
  [Runtime Resources](runtime-resources.md) for the Whisper caveats).
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
