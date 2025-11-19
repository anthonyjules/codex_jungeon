# 1. Communication
## 1.1 Know who else is online
* [x] On the right sidebar, add a section to show the names of other characters who are connected to the server
  * Show all online players globally (not just those in the same room)
  * Update the list when players connect/disconnect
  * Implementation: Add method to `ConnectionManager` to list all connected player IDs, then resolve to player names via `WorldEngine`

## 1.2 Messaging
* [ ] Add verbs /tell, /yell, and /reply. Command format is:
  * `/tell {character} {message}` - send private message to a specific character
  * `/tell all {message}` - send message to all online players
  * `/yell {character} {message}` - send private message in ALL CAPS to a specific character
  * `/reply {message}` - reply to the most recent character who sent you a message
* [ ] Character name matching:
  * Characters can be addressed by first name (Bob the Brave => bob, Bob, or BOB)
  * Matching is case-insensitive
  * Partial names are allowed if unambiguous (e.g., "bo" matches "Bob the Brave" if no other character starts with "bo")
  * If the current characters don't have unambiguous names, update the characters in `characters.json`
  * Implementation: Create helper function to resolve character names (first name → full name → player_id) with case-insensitive and partial matching
* [ ] Message delivery:
  * If the character is not online, show an error to the speaker
  * If the character is online, show a message in their main window section
  * `/tell` messages are private (only visible to sender and recipient)
  * `/tell all` messages are visible to all online players
  * Messages that are `/yell`'ed show up in ALL CAPITAL LETTERS
* [ ] Message format:
  * `/tell`: `"Bob the Brave tells you: 'Hello there!'"`
  * `/yell`: `"BOB THE BRAVE YELLS AT YOU: 'HELLO THERE!'"`
  * `/tell all`: `"Bob the Brave tells everyone: 'Hello there!'"`
* [ ] Reply functionality:
  * After a character has received a message, they can `/reply {message}`
  * `/reply` is equivalent to `/tell {most recent other character to message them} {message}`
  * Implementation: Store `last_message_sender_id` field in `PlayerState` to track the most recent sender
* [ ] Implementation notes:
  * Update `server/commands/parser.py` to recognize `/tell`, `/yell`, and `/reply` as special commands before falling back to emotes
  * Add handlers in `server/commands/router.py` for `tell`, `yell`, and `reply` actions
  * Use `ConnectionManager.send()` for direct messaging (not room broadcasts)
  * Add method to `ConnectionManager` to get all connected player IDs
  * Update `PlayerState` model to include `last_message_sender_id: Optional[str]` field
  * Update UI (`client/index.html`) to add "Online Players" section in right sidebar
  * Update `client/app.js` to handle new message types and render online players list
  * Update `UiController` to render the online players list

## 1.3 Remove "say" command
* [ ] Remove the existing `say` command functionality since we now have `/tell` and `/yell` for messaging
  * Remove `say_handler` from `server/commands/router.py`
  * Remove `"say": say_handler` from the `_handlers` dictionary in `CommandRouter`
  * The `say` command currently broadcasts messages to all players in the same room - this functionality is replaced by `/tell all` which sends to all online players globally
