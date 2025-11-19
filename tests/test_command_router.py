import pytest

from server.commands.base import CommandInput
from server.commands.router import CommandRouter
from server.services.connection_manager import ConnectionManager


class StubPlayer:
    def __init__(self, name="Hero"):
        self.name = name


class StubWorld:
    def __init__(self):
        self.player = StubPlayer()

    async def move_player(self, player_id: str, direction: str):
        return {"name": "Room", "exits": ["north"], "description": "desc"}

    async def collect_coins(self, player_id: str):
        return {"collected": 2}

    async def drop_coins(self, player_id: str):
        return {"dropped": 3}

    async def take_items(self, player_id: str, query):
        return {"taken": ["ring"]}

    async def get_inventory(self, player_id: str):
        return {"coins": 0, "items": []}

    async def get_emote_message(self, player_id: str, verb: str):
        if verb == "dance":
            return "Hero dances wildly"
        return None

    async def get_player(self, player_id: str):
        return self.player

    async def get_available_characters(self):
        return []

    async def get_room_player_ids(self, room_id: str):
        return []


@pytest.fixture()
def router():
    return CommandRouter(StubWorld(), ConnectionManager())


@pytest.mark.asyncio()
async def test_go_command_returns_room_state(router):
    command = CommandInput(action="go", args=["north"])
    result = await router.dispatch("player1", command)
    assert result.replies[0].type == "roomState"
    assert result.broadcasts[0].text.startswith("You hear footsteps")


@pytest.mark.asyncio()
async def test_collect_command_sets_refresh_flags(router):
    command = CommandInput(action="collect", args=[])
    result = await router.dispatch("player1", command)
    assert result.refresh_room is True
    assert result.refresh_inventory is True
    assert result.replies[0].data["text"].startswith("You collect")


@pytest.mark.asyncio()
async def test_emote_command(router):
    command = CommandInput(action="emote", verb="dance")
    result = await router.dispatch("player1", command)
    assert "You dances" not in result.replies[0].data["text"]
    assert result.broadcasts[0].text == "Hero dances wildly"


@pytest.mark.asyncio()
async def test_unknown_command(router):
    command = CommandInput(action="unknown")
    result = await router.dispatch("player1", command)
    assert result.replies[0].type == "error"
    assert "Unknown command" in result.replies[0].data["message"]


@pytest.mark.asyncio()
async def test_say_command_is_unknown(router):
    """Test that 'say' command is no longer available (replaced by /tell and /yell)."""
    command = CommandInput(action="say", args=["hello"])
    result = await router.dispatch("player1", command)
    assert result.replies[0].type == "error"
    assert "Unknown command" in result.replies[0].data["message"]
