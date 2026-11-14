# Pipeline and Costs

How a video is actually produced by this project, where each integration sits in
the pipeline, and what each of them costs. Everything here was read from the
source; file references point at the current `main`.

## Topology

Three front-ends converge on a single orchestrator.

| Front-end | Entry point | Reaches the pipeline at |
| --- | --- | --- |
| HTTP API | `main.py` -> `app/asgi.py` | `app/controllers/v1/video.py:268` |
| Streamlit WebUI | `webui/Main.py` | `app/services/webui_task.py:147` |
| CLI | `cli.py:1764` | `cli.py:1795` |

All three call `task.start` (`app/services/task.py:1985`), which wraps
`_run_pipeline` (`app/services/task.py:1550`) and converts any exception into a
failed task state instead of propagating it. The pipeline is therefore identical
regardless of how it was launched, which is what makes the CLI, the WebUI and the
API interchangeable.

## Stage order

```
1. script     LLM  (or your own text)  ->  the narration
2. terms      LLM  (or your own text)  ->  search keywords for material
3. save       script.json written to storage/tasks/<id>/
4. audio      TTS                       ->  audio.mp3 + subtitle timings
5. subtitle   timings or Whisper        ->  subtitle.srt
6. materials  provider search + download
7. final      compose, burn subtitles, mix BGM, mux  ->  final-<n>.mp4
```

Audio is generated **before** the material is downloaded, because the subtitle
timings come from the TTS output and the composition needs both.

`stop_at` gates the pipeline at `script`, `terms`, `audio`, `subtitle`,
`materials` or `video`, which is useful for debugging a single stage without
paying for the rest.

## The boundary that matters: text versus picture

**The LLM never selects or sees any footage.** It produces two kinds of text:

- the **script**, which becomes the narration;
- the **search terms**, which are passed verbatim to the material provider as a
  search query.

There is no vision step, no relevance scoring, and no feedback loop. The coherence
between what is narrated and what is shown is a **consequence of the keyword
search**, not of the model understanding the footage. A search for `"apollo11"`
may return a rocket, a conference stage, or a dog.

Two parameters exist to improve that approximation:

| Parameter | Effect |
| --- | --- |
| `match_materials_to_script` | Asks the LLM for the terms in narrative order, and raises the count from 5 to 8 (`app/services/task.py:395`), so the montage follows the story instead of showing a later image early. |
| `video_clip_duration`, `video_clip_speed` | Control how long each clip lasts relative to the narration pace. |

## Material sources

The full set is `_SUPPORTED_VIDEO_SOURCES` (`app/services/task.py:102`):

```
pexels, pixabay, coverr, local, wavespeed, volcengine_seedance, ofox,
metaso_minimax, muapi, loomloom, openai_image, codex_image, infistar, jalapeno
```

They fall into four families:

### Stock footage

`pexels`, `pixabay`, `coverr`.

**Pexels is used for video only.** The single endpoint the project calls is
`https://api.pexels.com/v1/videos/search` (`app/services/material.py:420`); the
`/v1/photos` endpoint is never used. The mental model of "Pexels gives me images"
is wrong for this project: it gives clips.

### Your own footage

`local`. Clips are taken from the local material directory. Zero cost, zero
dependency on any third party, and the only family that produces material nobody
else has.

### Generated video

`wavespeed`, `volcengine_seedance`, `ofox`, `metaso_minimax`, `muapi`, `loomloom`,
`infistar`, `jalapeno`. Each clip is generated from the keyword by a text-to-video
model and **billed per submitted clip**.

### Image-to-video

`openai_image`, `codex_image`. One image is generated per keyword and then
animated with the existing zoom/pan effects (`image_motion`) to produce a clip.
`openai_image` targets any OpenAI-compatible `/images/generations` endpoint, which
includes a local ComfyUI or SD gateway — see `docs/local-image-server/`.

## The Codex image path

`codex_image` is worth understanding precisely, because it is frequently
misunderstood.

**Codex does not generate video in this project.** It generates one PNG per
keyword, which the project then animates.

The request path (`app/services/codex_image.py:225`):

```python
"tools": [{"type": "image_generation", "action": "generate", "output_format": "png"}]
```

The endpoint (`app/services/codex_oauth.py:32`):

```
https://chatgpt.com/backend-api/codex/responses
```

**It does not call `api.openai.com`.** It is the Codex backend, authenticated with
the ChatGPT OAuth session stored in `storage/auth`. The consequences:

- **No API key is involved.** The LLM provider `openai_codex` and the image source
  `codex_image` both draw on the connected ChatGPT account's allowance.
- **Text and images share one device-code login.** Connecting the image source
  also connects the LLM, and vice versa.
- Upstream documents the provider in detail in
  [OpenAI - Codex](codex-provider.md); that document is authoritative for the
  sign-in flow and the credential storage.

### Billing

The Codex allowance is part of the ChatGPT subscription, not the API balance.
OpenAI's documentation states that Codex is included across ChatGPT plans and that
Codex activity is subject to the plan's usage limits and applicable charges; that
the ChatGPT image-generation and voice limits are tracked separately from Codex;
and that Codex shares an allowance pool with other agentic features on plans that
use one.

**So: generating images with Codex costs no API credits and is covered by the flat
plan — but it consumes the same Codex allowance that is otherwise used for
programming work.** For a channel producing videos regularly, that is a real
opportunity cost, not a free lunch.

The number of images per video equals the number of search terms: 5, or 8 with
`match_materials_to_script`.

### The caveat

Image access through this path is **not guaranteed**:

- `chatgpt.com/backend-api/codex/responses` is an internal Codex endpoint, not a
  documented public API. It can stop working, be restricted by plan or workspace,
  or be changed without notice.
- The model catalog lists *candidates*, not account-specific entitlements. The
  selected Responses model must actually support the image-generation tool for
  the account.
- The project raises `codex.image.model_required` when no model is selected, and
  stops without retrying when a result is uncertain or cannot be saved.

Verified against OpenAI's current documentation in November 2026. The exact
numeric allowance per plan could not be retrieved from the public pricing page
during that check; read the live value from **Settings -> Usage** in the Codex
client, or run `/status` in the Codex CLI.

**Recommendation: do not build a production channel on this path.** It is fine for
a first test. For a channel that must still work in six months, use `local`
footage or an `openai_image` endpoint you control.

## Cost model

| Component | Cost | Notes |
| --- | --- | --- |
| **Script + keywords** (LLM) | Free with a local provider; otherwise per token | Short-circuited entirely if you supply the text. |
| **Narration** (Edge TTS) | Free | No account, no key. |
| **Subtitles** | Free with Edge timings | Whisper is local and free, but see the model download note in [Runtime Resources](runtime-resources.md). |
| **Stock footage** (Pexels / Pixabay / Coverr) | Free within the free tier | Generic and shared with every other channel using it. |
| **Your own footage** (`local`) | Zero | The only source that is uniquely yours. |
| **Generated video** (Seedance, OFox, ...) | Per generated clip | Full artistic control, metered cost. |
| **Generated images** (`codex_image`) | Zero marginal, consumes the Codex allowance | Access not guaranteed. |
| **Generated images** (`openai_image`) | Per image, at the image model's price | Can point at a local gateway and become free. |
| **Composition and export** | Zero, local CPU | Roughly 3.9x realtime for a 30 s vertical video on a 12-vCPU host. |

### Which combination for a channel

| Goal | Configuration |
| --- | --- |
| Lowest risk, lowest cost | Own script + own footage (`local`) + Edge TTS. No third-party dependency at all beyond your own disk. |
| Maximum control, zero marginal cost | Own script + `openai_image` pointed at a local ComfyUI/SD gateway + Edge TTS. |
| Fastest to a first video | Own script + Pexels + Edge TTS. One key, no per-video cost, generic visuals. |
| Highest visual quality, metered | Any text-to-video provider, billed per clip. |
| Do not use for production | `codex_image` as the only material source. |

## Cross-posting

Publishing to social platforms is a separate background stage
(`app/services/task.py:1290`) that runs after the video is produced and is
decoupled from it. It can also call the LLM to generate the post metadata
(`app/services/task.py:1334`). A failure in cross-posting does not fail the
video task.

## Related documents

- [Fork Workflow and Local Setup](fork-workflow.md) — repository topology, configuration, authentication.
- [Runtime Resources](runtime-resources.md) — image footprint, measured resources, sizing.
