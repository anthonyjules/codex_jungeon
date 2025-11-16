MUD Prompt – the Jungeon

I want to create a multi-user online dungeon, which is a text-based game that allows multiple people to log into one server and receive a text-based description of their surroundings and the world they are in. Each user can navigate the world by giving commands on a command line, like "go north," "south," "east," or "west," and can also interact with objects in the world through a limited set of verbs like "touch," "open," and "press." Additionally, users can say or emote to other agents in the world.

The world in this game has one “world state” that is shared with all players. For example if a player A enters a room that player B is in the description should include a mention that A is in the room.

There should be a number of verbs that describe actions a character can take: dance, jump, smile, burp, sneeze, cough. These should be in a list in the code that we can extend. If a character types an action (e.g. “/sneeze”), then the other characters in the same room should get a message (e.g. “Bob has sneezed.”).

Each room can contain a number of gold coins. A player in a room with gold coins can execute the action “collect”, which removes all the gold coins from the room and puts them into the player’s private inventory. Players can can also execute a “drop” function which transfers all the coins in their inventory back into the room they are currently in. The shared state of the game consists of the positions and inventories of all of the characters and the number of coins currently in each room’s inventory. When a player enters a room, the number of coins in the room is part of the description of the room given to them.

The game should run in a browser window. The window should be divided into 3 sections
Left side = ⅔ of window
Top – 90% of window
Where all the descriptions of what is happening show up
Bottom – 1 line
Where the user can enter there commands to move, emote, act, etc.
Right side = ⅓ of window
Shows the user’s inventory & gold coin count

**Please propose a system that uses JSON or another human-friendly representation for the description of the world map and how the rooms are connected.** This should also include room descriptions, descriptions of characters, and how they appear in the environment. 

Furthermore, **please create a set of ten default characters that users can choose from when they log in.** When they log in, they should only have access to characters that are currently not being used by other players in the game. The game should be able to run on one computer and be visible to other computers on the same Wi-Fi network with minimal infrastructure changes.

The game should run as a web server that allows players to connect to it through HTTP. Once a user connects the server is responsible for maintaining all unique state needed for each player.

Propose an overall project structure, tech stack and representation for the map, characters, item generation settings etc. Describe how the world will maintain state and how basic networking will work.
