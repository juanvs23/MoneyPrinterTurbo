# Runtime Resources

Measured footprint of the published container image and the resources a real
render consumes. Every number here was produced by pulling and running the image,
not by reading the Dockerfile. The measurement host was **12 vCPU / 31.04 GiB
RAM**, Linux, Docker 29.9.3.

## Image identity

| Property | Value |
| --- | --- |
| Reference | `ghcr.io/harry0703/moneyprinterturbo:latest` |
| Index digest | `sha256:ce60ebde48c123864e3c950006abef22227fb7c7d9f94ed7f15762ba9b1cecf6` |
| `linux/amd64` manifest | `sha256:9a9e493b04ca58b5f277ed327659140d07630ed30c4f2f3ed3a53edcacc9c046` |
| `linux/arm64` manifest | `sha256:94ae1c7b0991347b8ccba417a6e48d723f3148faac1ca2d3d1b6a1ca205f440e` |
| Built | 2026-11-13 06:45 UTC |
| Base image | `python:3.11-slim-trixie` (Python 3.11.18) |
| Added at build time | `uv` 0.12.12, `git`, FFmpeg **7.1.5-0+deb13u1** |
| Working directory | `/MoneyPrinterTurbo` |
| Exposed port | `8501` (WebUI). The API port 8080 is not declared but works. |
| User | **root** — the Dockerfile declares no `USER`. |
| Default command | `streamlit run ./webui/Main.py` |

The image is multi-architecture (`amd64` and `arm64`) and additionally publishes
two attestation manifests with `unknown/unknown` platforms.

### The published image lags `main` by three commits

The image label `org.opencontainers.image.revision` is
`16986d0118cbdaa284ff7ce03a87734ffd837ee9`, while this fork's `main` is three
commits ahead. All three are documentation-only (`ce289ff`, `f7f4aef`,
`f6eb73e`: packaging examples, Docker setup order, sponsor promotion). There is
no functional difference. Rebuild from source whenever application code changes.

## Size

| Metric | Value |
| --- | --- |
| Download (compressed, amd64) | **780 MB** across 11 layers |
| Uncompressed on disk | **2.94 GB** |
| Application payload inside the image (`/MoneyPrinterTurbo`) | 206 MB |

Largest layers:

| Layer | Size | Content |
| --- | ---: | --- |
| `sha256:384e831e2eaa…` | 370.5 MB | Python dependencies |
| `sha256:98a9a1346ba6…` | 201.0 MB | Python dependencies (continued) |
| `sha256:e75251d746f8…` | 140.9 MB | FFmpeg and system packages |
| `sha256:37fb86c2a767…` | 29.9 MB | Runtime layer |
| `sha256:488a11549e11…` | 22.1 MB | Application layer |
| `sha256:7efbce397249…` | 14.5 MB | Application layer |

### What is *not* in the image

- **No Whisper models.** There is no Hugging Face cache in the image. Selecting
  `subtitle_provider = "whisper"` downloads the model on first use, which is a
  one-off download plus a directory that must be persisted across container
  restarts. `edge` avoids this entirely.
- **No `torch`, no `opencv`.** `faster-whisper` 1.1.0 uses `ctranslate2` 4.8.5
  and `onnxruntime`, both present. The image is far lighter than its size
  suggests, and Whisper runs on CPU.
- **No GPU libraries.** `ctranslate2.get_cuda_device_count()` returns `0` in this
  image, as expected for the CPU variant.

## Measured resource usage

### Idle

| Service | CPU | RSS | Processes | Startup |
| --- | --- | --- | --- | --- |
| Streamlit WebUI | 0.61% | **61.5 MiB** | 8 | Ready within 25 s, `HTTP 200` |
| FastAPI | 0.14% | **101 MiB** | 12 | ~2 s |

Idle cost is negligible. The numbers that matter are the peak ones below.

### During work

| Operation | Result | Peak RSS |
| --- | --- | ---: |
| Subtitle burn (PIL + numpy, 900 frames at 1080x1920) | 7.9 s, 114.3 fps, one core saturated | 74 MB |
| FFmpeg encode, 30 s at 1080x1920, `preset medium` (flat source) | 2.5 s wall, 11.9x realtime | 863 MB |
| **Realistic render**: concat 3 clips of 1080p -> scale and crop to 1080x1920 -> `x264 preset medium` | 30 s of video in **7.6 s (3.9x realtime)** | **1.12 GB** |

**The planning number is 1.12 GB of peak RAM per render, not the ~100 MB seen at
idle.** That figure is dominated by FFmpeg and the numpy frame buffers, and it is
what decides whether a small host survives the composition stage.

The realistic render produced a 7.9 MB MP4 for 30 s of vertical video, implying
roughly **16 MB per 60-second video**.

## Sizing guidance

| | Minimum | Comfortable |
| --- | --- | --- |
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Free disk | 20 GB | 50 GB+ |

On 2 vCPU the render is roughly four times slower than the figures above: about a
minute of wall time for a 30-second video instead of 7.6 seconds. The pipeline
still completes; it is simply slower.

**Disk is dominated by the material cache, not by the output.** The rendered video
is ~16 MB per minute, while the downloaded stock clips behind it are considerably
larger. Plan for tens of gigabytes when producing a regular output, and prune
`storage/cache_videos` periodically.

## Reproducing the measurements

```sh
# Size
docker manifest inspect ghcr.io/harry0703/moneyprinterturbo:latest
docker manifest inspect ghcr.io/harry0703/moneyprinterturbo@sha256:9a9e493b04ca58b5f277ed327659140d07630ed30c4f2f3ed3a53edcacc9c046
docker image inspect ghcr.io/harry0703/moneyprinterturbo:latest

# Idle footprint
docker run -d --name mpt-webui -p 127.0.0.1:8501:8501 \
  -v "$PWD/config.toml:/MoneyPrinterTurbo/config.toml:ro" \
  -v "$PWD/storage:/MoneyPrinterTurbo/storage" \
  ghcr.io/harry0703/moneyprinterturbo:latest
docker stats --no-stream --format '{{.CPUPerc}} {{.MemUsage}} {{.PIDs}}' mpt-webui

# Package inventory
docker run --rm --entrypoint sh ghcr.io/harry0703/moneyprinterturbo:latest \
  -c 'python3 -c "import ctranslate2; print(ctranslate2.__version__, ctranslate2.get_cuda_device_count())"'

# Render benchmark (see the concat/scale/crop/x264 chain described above)
docker run --rm --entrypoint sh ghcr.io/harry0703/moneyprinterturbo:latest -c '...'
```

## The GPU variant: do not trust it yet

Two facts were verified:

1. **It is not published.** `ghcr.io/harry0703/moneyprinterturbo` has no `gpu`,
   `latest-gpu` or `gpu-latest` tag. `docker-compose.gpu.yml` builds it locally
   from `Dockerfile.gpu`.
2. **Its CUDA runtime generation does not match the installed engine.**
   `Dockerfile.gpu` uses `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04` as its
   base, which ships **cuDNN 8**. The installed `ctranslate2` is **4.8.5**, and
   `ctranslate2` 4.x requires **cuDNN 9** to load its CUDA kernels.

That mismatch is very likely to surface as a failure to find
`libcudnn_ops_infer.so.9` when the GPU path is exercised. Verify before relying on
it. The fix, if needed, is a base image with cuDNN 9 (for example a
`nvidia/cuda:12.x-cudnn9-runtime` tag) plus the matching CUDA libraries.

Also keep in mind the scope: a GPU would only accelerate **Whisper subtitle
generation**. Video composition and encoding are FFmpeg CPU work and are not
accelerated by this image in any configuration.

## Related documents

- [Fork Workflow and Local Setup](fork-workflow.md) — configuration, credentials, authentication.
- [Pipeline and Costs](pipeline-and-costs.md) — pipeline stages and provider costs.
