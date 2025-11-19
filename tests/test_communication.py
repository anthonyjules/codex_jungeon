import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from server.commands.base import CommandInput
from server.commands.parser import parse_command_input
from server.commands.router import CommandRouter
from server.models import PlayerState
from server.services.connection_manager import ConnectionManager
from server.world.engine import WorldEngine


class MockWorld:
    """Mock WorldEngine for testing communication features."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.state = MagicMock()
        self.state.players = {}
        self.state.config = MagicMock()
        self.state.config.characters = {}

    async def get_player(self, player_id: str):
        return self.state.players.get(player_id)

    async def resolve_character_name(self, name_query: str, connections):
        query_lower = name_query.lower().strip()
        if not query_lower:
            return None

        online_player_ids = connections.get_all_connected_player_ids()
        matches = []

        # Use a simple lock simulation for testing
        for player_id in online_player_ids:
            player = self.state.players.get(player_id)
            if not player:
                continue
            full_name = player.name
            first_name = full_name.split()[0] if full_name else ""

            if full_name.lower() == query_lower or first_name.lower() == query_lower:
                matches.append((player_id, full_name))
            elif first_name.lower().startswith(query_lower):
                matches.append((player_id, full_name))

        if len(matches) == 1:
            return matches[0][0]
        elif len(matches) > 1:
            exact_matches = [
                pid for pid, name in matches
                if name.lower() == query_lower or name.split()[0].lower() == query_lower
            ]
            if len(exact_matches) == 1:
                return exact_matches[0]
        return None


@pytest.fixture
def mock_world():
    """Create a mock world with some test players."""
    world = MockWorld()

    # Create test players
    player1 = PlayerState(
        player_id="player1",
        character_id="char1",
        name="Bob the Brave",
        room_id="room1",
        coins=0,
        items=[],
        last_message_sender_id=None
    )
    player2 = PlayerState(
        player_id="player2",
        character_id="char2",
        name="Lina the Quiet",
        room_id="room1",
        coins=0,
        items=[],
        last_message_sender_id=None
    )
    player3 = PlayerState(
        player_id="player3",
        character_id="char3",
        name="Torin the Swift",
        room_id="room2",
        coins=0,
        items=[],
        last_message_sender_id=None
    )

    world.state.players = {
        "player1": player1,
        "player2": player2,
        "player3": player3,
    }

    return world


@pytest.fixture
def connections():
    """Create a connection manager with mock websockets."""
    conn_mgr = ConnectionManager()
    # Mock websockets for connected players - send_json needs to be async
    mock_ws1 = MagicMock()
    mock_ws1.send_json = AsyncMock()
    mock_ws2 = MagicMock()
    mock_ws2.send_json = AsyncMock()
    mock_ws3 = MagicMock()
    mock_ws3.send_json = AsyncMock()
    conn_mgr._connections = {
        "player1": mock_ws1,
        "player2": mock_ws2,
        "player3": mock_ws3,
    }
    return conn_mgr


@pytest.fixture
def router(mock_world, connections):
    """Create a router with mock world and connections."""
    router = CommandRouter(mock_world, connections)
    # Make sure the router's world and connections are the same instances
    router.world = mock_world
    router.connections = connections
    return router


# Parser Tests

def test_parse_tell_command():
    """Test parsing /tell command."""
    command = parse_command_input("/tell bob hello there")
    assert command.action == "tell"
    assert command.args == ["bob", "hello there"]


def test_parse_tell_all_command():
    """Test parsing /tell all command."""
    command = parse_command_input("/tell all hello everyone")
    assert command.action == "tell"
    assert command.args == ["all", "hello everyone"]


def test_parse_yell_command():
    """Test parsing /yell command."""
    command = parse_command_input("/yell lina watch out")
    assert command.action == "yell"
    assert command.args == ["lina", "watch out"]


def test_parse_yell_all_command():
    """Test parsing /yell all command."""
    command = parse_command_input("/yell all attention please")
    assert command.action == "yell"
    assert command.args == ["all", "attention please"]


def test_parse_reply_command():
    """Test parsing /reply command."""
    command = parse_command_input("/reply got it")
    assert command.action == "reply"
    assert command.args == ["got it"]


def test_parse_tell_with_apostrophe():
    """Test parsing /tell with apostrophe in message."""
    command = parse_command_input("/tell bob let's go")
    assert command.action == "tell"
    assert command.args == ["bob", "let's go"]


# Router Tests - Tell Command

@pytest.mark.asyncio
async def test_tell_to_specific_player(router, mock_world, connections):
    """Test /tell to a specific player."""
    command = CommandInput(action="tell", args=["bob", "hello"])
    result = await router.dispatch("player2", command)

    # Should send message to target
    assert len(result.replies) == 1
    assert "You tell Bob the Brave" in result.replies[0].data["text"]

    # Should update target's last_message_sender_id
    target_player = mock_world.state.players["player1"]
    assert target_player.last_message_sender_id == "player2"


@pytest.mark.asyncio
async def test_tell_all_broadcasts_to_everyone(router, mock_world, connections):
    """Test /tell all broadcasts to all players."""
    command = CommandInput(action="tell", args=["all", "hello everyone"])
    result = await router.dispatch("player1", command)

    # Should not have replies (message sent directly)
    assert len(result.replies) == 0

    # Should update all recipients' last_message_sender_id
    player2 = mock_world.state.players["player2"]
    player3 = mock_world.state.players["player3"]
    assert player2.last_message_sender_id == "player1"
    assert player3.last_message_sender_id == "player1"
    # Sender's own last_message_sender_id should not be updated
    player1 = mock_world.state.players["player1"]
    assert player1.last_message_sender_id is None


@pytest.mark.asyncio
async def test_tell_to_nonexistent_player_raises(router, mock_world, connections):
    """Test /tell to a player that doesn't exist."""
    command = CommandInput(action="tell", args=["nonexistent", "hello"])
    with pytest.raises(ValueError, match="not online or the name is ambiguous"):
        await router.dispatch("player1", command)


@pytest.mark.asyncio
async def test_tell_to_self_raises(router, mock_world, connections):
    """Test /tell to yourself raises error."""
    command = CommandInput(action="tell", args=["bob", "hello"])
    with pytest.raises(ValueError, match="cannot tell yourself"):
        await router.dispatch("player1", command)


@pytest.mark.asyncio
async def test_tell_without_message_raises(router, mock_world, connections):
    """Test /tell without message raises error."""
    command = CommandInput(action="tell", args=["bob"])
    with pytest.raises(ValueError, match="Usage"):
        await router.dispatch("player2", command)


@pytest.mark.asyncio
async def test_tell_with_case_insensitive_name(router, mock_world, connections):
    """Test /tell with case-insensitive character name."""
    command = CommandInput(action="tell", args=["BOB", "hello"])
    result = await router.dispatch("player2", command)

    assert len(result.replies) == 1
    target_player = mock_world.state.players["player1"]
    assert target_player.last_message_sender_id == "player2"


@pytest.mark.asyncio
async def test_tell_with_partial_name(router, mock_world, connections):
    """Test /tell with partial character name."""
    command = CommandInput(action="tell", args=["bo", "hello"])
    result = await router.dispatch("player2", command)

    assert len(result.replies) == 1
    target_player = mock_world.state.players["player1"]
    assert target_player.last_message_sender_id == "player2"


# Router Tests - Yell Command

@pytest.mark.asyncio
async def test_yell_to_specific_player(router, mock_world, connections):
    """Test /yell to a specific player."""
    command = CommandInput(action="yell", args=["lina", "watch out"])
    result = await router.dispatch("player1", command)

    # Should send message to target
    assert len(result.replies) == 1
    assert "You yell at Lina the Quiet" in result.replies[0].data["text"]
    assert "WATCH OUT" in result.replies[0].data["text"]

    # Should update target's last_message_sender_id
    target_player = mock_world.state.players["player2"]
    assert target_player.last_message_sender_id == "player1"


@pytest.mark.asyncio
async def test_yell_all_broadcasts_to_everyone(router, mock_world, connections):
    """Test /yell all broadcasts to all players."""
    command = CommandInput(action="yell", args=["all", "attention"])
    result = await router.dispatch("player1", command)

    # Should not have replies (message sent directly)
    assert len(result.replies) == 0

    # Should update all recipients' last_message_sender_id
    player2 = mock_world.state.players["player2"]
    player3 = mock_world.state.players["player3"]
    assert player2.last_message_sender_id == "player1"
    assert player3.last_message_sender_id == "player1"


@pytest.mark.asyncio
async def test_yell_to_nonexistent_player_raises(router, mock_world, connections):
    """Test /yell to a player that doesn't exist."""
    command = CommandInput(action="yell", args=["nonexistent", "hello"])
    with pytest.raises(ValueError, match="not online or the name is ambiguous"):
        await router.dispatch("player1", command)


@pytest.mark.asyncio
async def test_yell_to_self_raises(router, mock_world, connections):
    """Test /yell to yourself raises error."""
    command = CommandInput(action="yell", args=["bob", "hello"])
    with pytest.raises(ValueError, match="cannot yell at yourself"):
        await router.dispatch("player1", command)


# Router Tests - Reply Command

@pytest.mark.asyncio
async def test_reply_to_last_sender(router, mock_world, connections):
    """Test /reply to the last person who sent a message."""
    # First, set up last_message_sender_id
    sender = mock_world.state.players["player1"]
    receiver = mock_world.state.players["player2"]
    receiver.last_message_sender_id = "player1"

    command = CommandInput(action="reply", args=["got it"])
    result = await router.dispatch("player2", command)

    # Should send message to last sender
    assert len(result.replies) == 1
    assert "You tell Bob the Brave" in result.replies[0].data["text"]

    # Should update sender's last_message_sender_id
    assert sender.last_message_sender_id == "player2"


@pytest.mark.asyncio
async def test_reply_without_last_sender_raises(router, mock_world, connections):
    """Test /reply when there's no last sender."""
    command = CommandInput(action="reply", args=["hello"])
    with pytest.raises(ValueError, match="no one to reply to"):
        await router.dispatch("player1", command)


@pytest.mark.asyncio
async def test_reply_when_sender_offline_raises(router, mock_world, connections):
    """Test /reply when the last sender is no longer online."""
    receiver = mock_world.state.players["player1"]
    receiver.last_message_sender_id = "offline_player"

    command = CommandInput(action="reply", args=["hello"])
    with pytest.raises(ValueError, match="no longer online"):
        await router.dispatch("player1", command)


@pytest.mark.asyncio
async def test_reply_without_message_raises(router, mock_world, connections):
    """Test /reply without message raises error."""
    receiver = mock_world.state.players["player2"]
    receiver.last_message_sender_id = "player1"

    command = CommandInput(action="reply", args=[])
    with pytest.raises(ValueError, match="Usage"):
        await router.dispatch("player2", command)


# Character Name Resolution Tests

@pytest.mark.asyncio
async def test_resolve_character_name_exact_match(mock_world, connections):
    """Test resolving character name with exact match."""
    player_id = await mock_world.resolve_character_name("bob", connections)
    assert player_id == "player1"


@pytest.mark.asyncio
async def test_resolve_character_name_case_insensitive(mock_world, connections):
    """Test resolving character name is case-insensitive."""
    player_id = await mock_world.resolve_character_name("BOB", connections)
    assert player_id == "player1"

    player_id = await mock_world.resolve_character_name("Bob", connections)
    assert player_id == "player1"


@pytest.mark.asyncio
async def test_resolve_character_name_partial_match(mock_world, connections):
    """Test resolving character name with partial match."""
    player_id = await mock_world.resolve_character_name("bo", connections)
    assert player_id == "player1"


@pytest.mark.asyncio
async def test_resolve_character_name_full_name(mock_world, connections):
    """Test resolving character name with full name."""
    player_id = await mock_world.resolve_character_name("Bob the Brave", connections)
    assert player_id == "player1"


@pytest.mark.asyncio
async def test_resolve_character_name_nonexistent(mock_world, connections):
    """Test resolving nonexistent character name returns None."""
    player_id = await mock_world.resolve_character_name("nonexistent", connections)
    assert player_id is None


@pytest.mark.asyncio
async def test_resolve_character_name_ambiguous(mock_world, connections):
    """Test resolving ambiguous character name returns None."""
    # Add another player with similar name
    player4 = PlayerState(
        player_id="player4",
        character_id="char4",
        name="Bob the Bold",
        room_id="room1",
        coins=0,
        items=[],
        last_message_sender_id=None
    )
    mock_world.state.players["player4"] = player4
    mock_ws4 = MagicMock()
    mock_ws4.send_json = AsyncMock()
    connections._connections["player4"] = mock_ws4

    # "bo" is now ambiguous
    player_id = await mock_world.resolve_character_name("bo", connections)
    assert player_id is None

    # But "bob the brave" should still work
    player_id = await mock_world.resolve_character_name("bob the brave", connections)
    assert player_id == "player1"


# Connection Manager Tests

def test_get_all_connected_player_ids(connections):
    """Test getting all connected player IDs."""
    player_ids = connections.get_all_connected_player_ids()
    assert set(player_ids) == {"player1", "player2", "player3"}


@pytest.mark.asyncio
async def test_send_to_all(connections):
    """Test sending message to all connected players."""
    message = {"type": "event", "data": {"text": "test"}}
    await connections.send_to_all(message)

    # Verify all connections received the message
    for ws in connections._connections.values():
        ws.send_json.assert_called_once()


@pytest.mark.asyncio
async def test_send_to_specific_player(connections):
    """Test sending message to a specific player."""
    message = {"type": "event", "data": {"text": "test"}}
    await connections.send("player1", message)

    connections._connections["player1"].send_json.assert_called_once_with(message)
    # Other players should not receive it
    connections._connections["player2"].send_json.assert_not_called()


@pytest.mark.asyncio
async def test_send_to_nonexistent_player(connections):
    """Test sending to nonexistent player doesn't raise error."""
    message = {"type": "event", "data": {"text": "test"}}
    # Should not raise
    await connections.send("nonexistent", message)

