# Architecture Refactor Plan

## Goals
- Improve maintainability of the FastAPI server by separating HTTP, websocket, and service concerns.
- Decompose the `World` monolith into smaller, testable components with clear responsibilities.
- Introduce simple infrastructure services (connection management, persistence) to remove ad-hoc globals.
- Structure the browser client into modules so UI updates, networking, and state can evolve independently.
- Deliver incremental commits so each logical change is reviewable.

## Phases

### Phase 1 – Server surface re-organization
1. Create `server/api` package with `routers.py` for REST endpoints and `ws.py` for the websocket endpoint.
2. Introduce `server/services/game_service.py` (or similar) that wraps `World` + `SessionManager` interactions exposed to the HTTP layer.
3. Move DTO/Pydantic schemas and command parsing helpers into `server/schemas.py` / `server/commands.py`.

### Phase 2 – Command pipeline + infra services
1. Replace the `if/elif` ladder with a command registry where each handler implements a common interface and returns typed results (`RoomStateMessage`, `EventMessage`, etc.).
2. Build a `ConnectionManager` class that tracks websocket connections and room broadcasts; the websocket handler delegates all broadcast operations to it.
3. Add a background `PersistenceWorker` (or integrate into `WorldRepository`) that batches state saves without blocking gameplay operations.

### Phase 3 – World decomposition
1. Extract `WorldLoader` for reading JSON / procedural generation and returning `WorldConfig`.
2. Extract `WorldRepository` for loading/saving runtime state (`character_saves`, room coins, etc.).
3. Keep a slimmer `WorldState`/`WorldEngine` responsible for player moves, room descriptions, inventories, and minimap creation. It consumes loader + repository dependencies supplied during startup.
4. Update `server/services/game_service.py` to wire these components and expose async-safe methods to the API layer.

### Phase 4 – Client modularization
1. Convert `client/app.js` into ES modules (plain `<script type="module">` is fine) with:
   - `network.js`: websocket + REST helpers.
   - `ui.js`: DOM references + rendering helpers.
   - `client.js`: orchestrates user input, command history, minimap updates.
2. Introduce lightweight state containers (e.g., `GameState`, `UiState`) to avoid scattered globals.
3. Ensure build pipeline remains zero-config (vanilla JS) to keep onboarding simple.

### Phase 5 – Validation & polish
1. Smoke-test HTTP endpoints and websocket commands locally (manual + small async unit tests around handlers).
2. Update README with new run instructions if anything changes (e.g., module entrypoints).
3. Optionally add FastAPI dependency injections/tests verifying routers.

Each numbered bullet should become its own commit or grouped commit when tightly coupled, keeping history reviewable.
