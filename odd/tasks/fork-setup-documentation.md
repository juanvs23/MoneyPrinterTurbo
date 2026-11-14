# Feature: Fork Setup Documentation

## Objective

Capture everything established during the initial setup and investigation of this
MoneyPrinterTurbo fork so that a future session (or contributor) can reproduce the
environment, understand the runtime cost model, and avoid re-deriving what was
measured.

## Problem

The repository was a bare clone of `harry0703/MoneyPrinterTurbo` with no local
configuration, no fork, and no branch strategy. Several operational facts were
discovered only by running the code (not documented upstream): which API calls the
Codex image path actually makes, that Pexels is only used for video, the real disk
and RAM footprint of the published container image, and which credentials are
actually required for a first render.

## Why

This fork exists to produce videos for a freelance video channel. The decisions
about providers, material sources and cost are the ones that determine whether the
channel is viable. Losing them to session context would mean re-running the same
investigation and, worse, re-paying for the same mistakes.

## Scope

Authoritative, additive documentation for this fork:

- `docs/fork-workflow.md` — fork topology, branch strategy, local configuration,
  credentials and security posture.
- `docs/pipeline-and-costs.md` — how the generation pipeline actually works and
  what each integration costs.
- `docs/runtime-resources.md` — measured footprint of the published container
  image and sizing guidance.
- `docs/README.md` — index for the fork-specific documents.

Out of scope: upstream README translations, upstream provider documentation
(`docs/codex-provider.md`, `docs/chatgpt-provider.md`), and any change to
application source code.

## Constraints

- Canonical artifacts are written in English (project convention; upstream `docs/`
  are English).
- `config.toml` stays untracked (`.gitignore:2`) because it holds API keys.
- Every documented number must be one that was observed, not estimated. Where a
  value could not be verified, the document says so explicitly.
- New files only, so that merging `upstream/main` stays conflict-free.

## Constraints on upstream synchronization

`upstream` publishes roughly 700 commits per year. The fork must be able to absorb
those updates without manual conflict resolution, which is why this work adds new
files under `docs/` instead of editing the translated READMEs.

## Acceptance criteria

- [x] Fork topology, remote names and upstream-sync commands are documented.
- [x] The exact credential list required for a first render is documented, with
      the free/no-credential path separated from the paid one.
- [x] The authentication behaviour of `api_key` is documented with the verified
      status codes.
- [x] The pipeline stage order is documented from the source, and the boundary
      between "LLM writes text" and "material search" is explicit.
- [x] The Codex image path is documented with the endpoint it actually calls and
      the billing consequence.
- [x] A cost comparison table covers every material source.
- [x] The container image digest, size and measured resource usage are recorded,
      together with the commands that reproduce the measurements.
- [x] The GPU-variant caveat is recorded.
- [x] All documents are in English and use the repository's Markdown conventions.

## Verification

- Facts about call sites were read from source and cited as `file:line`.
- Resource numbers come from running the published image on a 12 vCPU / 31 GB host,
  not from inspecting the Dockerfile.
- Authentication was verified with live HTTP requests against the running
  container (`401` without the header, `200` with it).
- TOML validity of the generated `config.toml` was checked with `tomllib`.

## Route

Delegated direct: one writer, four new files plus this document. No application
code changes, so no verification suite beyond the checks above applies.

## Progress

- [x] T1 — Create branch `docs/fork-setup-documentation` from `main`.
- [x] T2 — Create the fork, rewire remotes (`origin` → fork, `upstream` →
      harry0703), push `main`.
- [x] T3 — Generate local `config.toml` with local-appropriate values.
- [x] T4 — Measure the published container image (size, layers, runtime resources).
- [x] T5 — Investigate the Codex image path and its billing model against current
      OpenAI documentation.
- [x] T6 — Write the four `docs/` files.
- [x] T7 — Open issue #1, label it `status:approved`, open PR #2 with the
      `type:docs` label and `Closes #1`.

## Delivery

- Issue: `juanvs23/MoneyPrinterTurbo#1` — "Document fork setup, pipeline costs
  and runtime resources", labelled `status:approved`.
- Pull request: `juanvs23/MoneyPrinterTurbo#2`, `docs/fork-setup-documentation`
  into `main`, labelled `type:docs`, state `MERGEABLE` / `CLEAN`.
- The branch was renamed from `feature/bootstrap-local-setup` to
  `docs/fork-setup-documentation` before pushing, because the `branch-pr` skill
  requires the branch name to match
  `^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)/[a-z0-9._-]+$`
  and `feature/` is not in that list.

## Repository settings changed on the fork

- `has_issues` enabled. The fork inherited `has_issues=false` from the GitHub
  fork creation, while upstream has issues enabled. Restoring parity was a
  prerequisite for the issue-first pull request workflow.
- Labels `status:approved` and `type:docs` created.

## Open findings for the fork

1. **Fork workflows are not registered with GitHub Actions.** The fork's
   `main` contains `ci.yml`, `docker-ghcr.yml` and `security.yml`, but
   `GET /actions/workflows` returns `total_count: 0` and
   `gh workflow run ci.yml` fails with "not found on the default branch".
   GitHub does not register fork workflows until they are enabled in the
   repository's Actions tab. Until then, pull requests in this fork run no
   automated checks.
2. **`docker-ghcr.yml` hardcodes the upstream image name**:
   `IMAGE_NAME: ghcr.io/harry0703/moneyprinterturbo`. The workflow triggers on
   `push` to `main` with `paths-ignore: docs/**`, so it does not run for a
   documentation-only merge. Any future code change merged into this fork's
   `main` will attempt to publish to the upstream registry and fail. The
   workflow must be repointed at `ghcr.io/juanvs23/moneyprinterturbo` before the
   first code merge.


## Notes

- The generated `api_key` value is intentionally not recorded in this document;
  it lives only in the local, untracked `config.toml`.
- The published `:latest` image is three commits behind `main`, and all three are
  documentation-only. This is recorded in `docs/runtime-resources.md` so that a
  future reader does not mistake it for a functional gap.
