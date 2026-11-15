# Fork Notes

These documents describe **this fork's** setup, runtime footprint and cost model.
They were written while establishing the fork and are not part of upstream
`harry0703/MoneyPrinterTurbo`; the upstream documents in this directory remain
authoritative for their own subjects.

| Document | Contents |
| --- | --- |
| [Fork Workflow and Local Setup](fork-workflow.md) | Fork topology, remote layout, branch strategy, generating `config.toml`, which credentials a first render actually needs, and how `api_key` protects the API and the generated files. |
| [Pipeline and Costs](pipeline-and-costs.md) | The three front-ends and the single orchestrator, the stage order, the boundary between text generation and material search, every material source, the Codex image path and its billing model, and a cost comparison per provider. |
| [Runtime Resources](runtime-resources.md) | The published container image (digest, size, layers), measured CPU and RAM during a real render, sizing guidance, and the GPU-variant caveat. |

Upstream documents worth reading alongside these:

- [OpenAI - Codex](codex-provider.md) — sign-in flow, credential storage, model catalog.
- [ChatGPT Provider](chatgpt-provider.md) — the native ChatGPT OAuth provider.
- [Video Projects](video-projects.md) — the local, revision-based render pipeline for hand-prepared footage.
- [Packaging](packaging.md) and [Docker Config Note](docker-config-note.md) — deployment specifics.
