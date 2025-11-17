from server.commands.parser import parse_command_input


def test_parse_empty_text_returns_noop():
    command = parse_command_input("")
    assert command.action == "noop"


def test_parse_direction_alias():
    command = parse_command_input("n")
    assert command.action == "go"
    assert command.args == ["north"]


def test_parse_emote():
    command = parse_command_input("/Sneeze")
    assert command.action == "emote"
    assert command.verb == "sneeze"
