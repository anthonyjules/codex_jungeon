# The Jungeon – Browser MUD

This is a small multi-user dungeon (MUD) that runs as a web server and is playable from a browser on the same Wi‑Fi network.

## Features (first pass)

- Shared world state for all players (rooms, exits, coins).
- 10 pre-defined characters; each can only be used by one player at a time.
- Commands:
  - `go north|south|east|west`
  - `collect` / `drop` gold coins
  - `look` to re-print the current room
  - `say <message>` to speak to others in the room
  - Emotes like `/dance`, `/sneeze`, `/smile` (see `data/verbs.json`).
- Browser UI:
  - Left: log of room descriptions and events.
  - Bottom-left: one-line command input.
  - Right: character info, current room, and gold count.

## Running the server

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

Then open a browser to:

- `http://localhost:8000/` from the same machine, or
- `http://<server-lan-ip>:8000/` from another machine on the same Wi‑Fi.

Each browser tab can pick one of the available characters and enter the dungeon.

## Running tests

From the project root with the virtual environment activated:

```bash
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pytest tests/ -v
```

To run a specific test file:

```bash
pytest tests/test_communication.py -v
```

## World data

- World map, rooms, exits, coins, and interactable objects:
  - `data/world.json`
- Default characters and how they appear in rooms:
  - `data/characters.json`
- Emote verbs and simple object verbs:
  - `data/verbs.json`

These files are designed to be human-editable so you can extend the map, add rooms, change descriptions, or define new emotes.

