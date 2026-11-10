# Changelog

## Unreleased

### Playground: no token to paste

The Try it panel signs in with a temporary public token made from the admin session (named `playground (temporary)`, valid 1 day, revoked on sign-out or when the tab closes), so the service token field is hidden and choices such as voices load by themselves. The token shows in the tokens list while it lives.


- New **Engine** setting (`SERVICE_ENGINE`, restart): `transformers` (default, as before) or `bitnet.cpp`, a `llama-server` built from Microsoft's bitnet.cpp into the Docker image (new `cpp` build stage in the `Dockerfile`, pinned commit) and run as a child process by new `src/cpp.py`. It reads the GGUF weights (`microsoft/BitNet-b1.58-2B-4T-gguf`), downloaded from the Updates card; no project models with it; CPU threads restart the server. Roughly 5 times the tokens per second of `transformers` in a quick test (not a benchmark). The Dockerfile pins BitNet to the June 2025 commit `404980e`: the July 2026 `main` gave wrong, never-ending answers with Microsoft's GGUF. The prompt is built in `src/cpp.py` (the GGUF has no chat template) and sent to `/completion`.
- Admin page: new **Model variant** card. It lists the two number formats (`bfloat16`, `float32`) of the one set of weights, with the memory each takes (the figures already in this README, about 5 GB and 8 GB; not measured), the download size, whether the weights are on disk, and whether this machine can run it. Endpoints `GET /admin/variants` and `PUT /admin/variant` (409 when it does not fit); a choice saves `dtype`, a restart setting. New `src/hardware.py` and `src/variants.py`.
- Env files: `run.bat` (`--dotenv`) now loads `.env.local`, then `.env`; the first file to set a name wins and a real environment variable still beats both, so a host run can keep `SERVICE_OLLAMA_URL=http://127.0.0.1:11434` in `.env.local` while Docker uses `http://host.docker.internal:11434`. `.env.compose` is for Docker Desktop on this device (`docker compose --env-file .env.compose up -d --build`). `.env` stays the file Deploy option 2 pushes to the deployment device, where a plain `docker compose up -d --build` reads it. `.env.local` and `.env.compose` are git-ignored and Docker-ignored (`.env.*`). New shared `settings.load_env_files`.
- Admin page and shared styles: polish layer in `web/index.html` (focus ring, hover and pressed states, layered shadow on the sign-in card and dialogs, tabular numbers, one entrance motion per page, themed scrollbars, `prefers-reduced-motion`). No behaviour change.

- Admin page: a closeable warning on the Overview appears while no weights are downloaded, with a button to the Updates page. While **Download new weights** runs, the Updates card shows a progress bar with megabytes downloaded (`progress` in `GET /admin/updates`; new shared `src/progress.py`). Replicas share the numbers through a small file next to the weights marker; where that folder is not shared (Ollama services) the bar shows on the replica doing the download.

- Fix: a caller that hangs up while the first piece of a stream is still being made now stops the work for nobody. The request timing moved from `@app.middleware("http")` to a plain ASGI middleware (`Measure` in `src/disconnect.py`), because the decorator form hides a hang-up from `request.is_disconnected()`; metrics are unchanged.

- Admin UI: separate hash-routed pages in a collapsible sidebar; health-first Overview, one main-header page title, capability-specific navigation, draft-preserving navigation and responsive desktop/mobile layout. Existing admin and public API actions are preserved.

- Admin page: the CPU threads card and tile are hidden when `CONFIG.tags` has `host-threads`, and the Project models card is shown only with `project-models`.

- Admin page: `CONFIG.tags` (same tags as `docs/purpose.md`) switch tag-driven notes: `gpu` shows a CPU-threads note, `license-restricted` shows a licence note on the Updates card.

- Fix: after Download, a CPU threads change or a sync from another replica drops the loaded model, the service now reloads it in the background (when "Load the model at start" is on) instead of showing "Starting" on `/admin/` until the first request.
- Breaking: startup, warm-up and requests load downloaded weights only. First run requires `/admin/` → Updates → Download; missing weights keep health/admin available and inference returns 503. Checks never download; explicit Download replaces weights and tells every replica to reload.
- Updates shows downloaded and online versions, newer-version and not-downloaded states; Download remains available when online comparison fails.

- `SERVICE_MODELS_DIR` sets where a local (no Docker) run keeps downloaded model weights: `settings.apply_models_dir()` maps it to `HF_HOME` and `OLLAMA_MODELS` at start.
- Docs: `docs/guide-cli.md`, a PowerShell-only way to test the service.

### Breaking: common service environment variables

Service-owned environment variables now use `SERVICE_*`. Old names are no longer read.
Rename old names once in your real `.env`, Compose `environment:` block, and CI/secret settings.

| Old name | New name |
|---|---|
| `BITNET_ADMIN_PASSWORD` | `SERVICE_ADMIN_PASSWORD` |
| `BITNET_CACHE_SIZE` | `SERVICE_CACHE_SIZE` |
| `BITNET_DTYPE` | `SERVICE_DTYPE` |
| `BITNET_HOST` | `SERVICE_HOST` |
| `BITNET_MAX_INFLIGHT` | `SERVICE_MAX_INFLIGHT` |
| `BITNET_MAX_PROJECT_MODELS` | `SERVICE_MAX_PROJECT_MODELS` |
| `BITNET_MEM_LIMIT` | `SERVICE_MEM_LIMIT` |
| `BITNET_MODEL` | `SERVICE_MODEL` |
| `BITNET_NUM_THREAD` | `SERVICE_NUM_THREAD` |
| `BITNET_PORT` | `SERVICE_PORT` |
| `BITNET_PROJECT_MODELS_DIR` | `SERVICE_PROJECT_MODELS_DIR` |
| `BITNET_REPLICAS` | `SERVICE_REPLICAS` |
| `BITNET_TOKENS_FILE` | `SERVICE_TOKENS_FILE` |
| `BITNET_UPDATE_CHECK_HOURS` | `SERVICE_UPDATE_CHECK_HOURS` |
| `BITNET_WARM` | `SERVICE_WARM` |
| `BITNET_WEB_DIR` | `SERVICE_WEB_DIR` |
| `BITNET_WEIGHTS_MARKER` | `SERVICE_WEIGHTS_MARKER` |

- Default HTTP port moves from 9140 to 29201. Update explicit old ports in your real `.env`, saved tool-service `backends.json` connections, and browser/MCP client configurations once. Compose now uses 29201 inside API replicas and nginx; deployments using the old Compose default must recreate containers. A custom host-port override stays in effect until you change it; container ports still move to 29201.

- Renamed `BitNet2BModel` to `CNV_BitNet2B_Model`; Docker project, API image, services, load balancer and volumes now use `cnv_bitnet2b_model` names. Callers on `citadel_core` connect to `cnv_bitnet2b_model_lb` at the existing port.
- Docker volume migration: existing volumes with old names are orphaned; renaming does not move data. Stop the old stack before copying; never use `down -v`. The commands below assume the previous default Compose project name; substitute actual volume names if `-p` or `COMPOSE_PROJECT_NAME` overrode it.
  - `bitnet_models` → `cnv_bitnet2b_model_models`: `docker volume inspect bitnet_models && docker volume create cnv_bitnet2b_model_models && docker run --rm -v bitnet_models:/from:ro -v cnv_bitnet2b_model_models:/to alpine:3.21 sh -c "cd /from && cp -a . /to/"`
  - `bitnet_tokens` → `cnv_bitnet2b_model_data`: `docker volume inspect bitnet_tokens && docker volume create cnv_bitnet2b_model_data && docker run --rm -v bitnet_tokens:/from:ro -v cnv_bitnet2b_model_data:/to alpine:3.21 sh -c "cd /from && cp -a . /to/"`
- To retain an old volume instead, set its top-level volume definition to `external: true` and `name: <old-volume-name>` in a local Compose override. Rollback: stop the renamed stack, restore the previous checkout and folder name, and restart the old stack with its original volumes; copy back newer data first if the renamed stack accepted writes.

- `run.bat` loads `.env` from the service folder for a local run: it passes `--dotenv`, the service prints which variable names it loaded (never the values), and a real environment variable still wins. A plain `python src/app.py` and Docker never read `.env`.
- Untracked folders now start with `.` or `_`: `zip_versions/` is `_zip_versions/`. A local `voices`, `tem_code` or `zip_versions` folder from an older checkout needs renaming by hand.
- `run.bat` is now a menu (run the service, deploy, build the release ZIP) and `run.bat run|deploy|zip` skips it. `tools/deploy.bat`, `tools/make_zip.bat` and `tools/deploy.local.example.bat` are gone; the local deploy target is `tools/deploy.local.ini` (copy `tools/deploy.local.example.ini`).
- Admin page: **Connect to this service** card with the addresses other services can use (this page's address, same PC, Docker network, `host.docker.internal`) and every endpoint, each with a Copy button.
- Admin **Try it** panel: descriptor-driven public API requests, live text streams, JSON/media output, status and latency, cancellation and redacted curl. Auth choice (b): pasted public token stays in memory; normal scope, limits and caches apply. Shared `web/playground.js` is copied across all model and tool services.

- `run.bat`: runs `uv sync` directly; `python -m uv` failed when uv was installed only as a program (winget).
- Docker: `.dockerignore` keeps `.git`, `.venv`, tests and local state out of the build context (the same file in every model service).
- Compose: `stop_grace_period: 90s`, so a restart lets a running answer finish instead of cutting it off after Docker's default 10 s.
- Docs: set CPU threads to the number of physical cores, not logical CPUs.
- `/metrics` also returns `bitnet_request_seconds`, a histogram of how long `/v1` calls took on that replica.
- Compose: optional `SERVICE_MEM_LIMIT` caps the container's RAM (default no cap).

- Answer cache (`SERVICE_CACHE_SIZE`, default 256, 0 = off; `X-Cache` header): the last answers to identical `temperature` 0 requests are sent again without generating.
- `POST /v1/chat` accepts `"stream": true`: the answer arrives as JSON lines (`content` pieces, then `done`).

- First version: Microsoft BitNet b1.58 2B4T served on the CPU with `transformers`, with the admin page, project
  tokens (scope, rate limit, expiry), metrics, Settings card, update checks and weight downloads shared with
  `CNV_MiniCPM52B_Model` and `DSC_Laya_Model`.
- `POST /v1/chat` takes `messages`, `project`, `temperature` and `max_tokens`. Tools, schemas and thinking are refused
  with 422.
- Project models are checkpoint folders loaded in process (LRU).
