import { UiController } from "./modules/ui.js";
import {
  fetchAvailableCharacters,
  loginWithCharacter,
  createWebSocket,
} from "./modules/network.js";

class GameClient {
  constructor(ui) {
    this.ui = ui;
    this.sessionId = null;
    this.ws = null;
    this.currentCharacter = null;
  }

  async init() {
    this.ui.bindCommandInput((value) => this.sendCommand(value));
    this.ui.bindControlButtons((cmd) => this.sendCommand(cmd));
    await this.loadCharacters();
  }

  async loadCharacters() {
    try {
      const data = await fetchAvailableCharacters();
      const characters = data.characters || [];
      this.ui.renderCharacters(characters, (character) =>
        this.login(character)
      );
      this.ui.setLoginError("");
    } catch (err) {
      this.ui.setLoginError(
        "Could not load characters. Is the server running?"
      );
    }
  }

  async login(character) {
    try {
      this.ui.setLoginError("");
      const data = await loginWithCharacter(character.id);
      this.sessionId = data.sessionId;
      this.currentCharacter = {
        id: data.characterId,
        name: data.playerName,
      };
      this.onLoggedIn();
      this.connectWebSocket();
    } catch (err) {
      this.ui.setLoginError(
        "Login failed. The character may have been taken."
      );
      await this.loadCharacters();
    }
  }

  onLoggedIn() {
    this.ui.showOverlay(false);
    this.ui.setCharacterInfo(this.currentCharacter.name);
    this.ui.focusInput();
    this.ui.appendLog(
      `You enter the Jungeon as ${this.currentCharacter.name}.`,
      "system"
    );
  }

  connectWebSocket() {
    if (!this.sessionId) {
      return;
    }

    this.ws = createWebSocket(this.sessionId, {
      onOpen: () => {
        this.ui.appendLog("Connection to the dungeon established.", "system");
      },
      onMessage: (msg) => this.handleServerMessage(msg),
      onClose: () => {
        this.ui.appendLog(
          "Your connection to the dungeon has been lost.",
          "error"
        );
      },
    });
  }

  handleServerMessage(msg) {
    const { type, data } = msg;
    if (type === "roomState") {
      this.ui.renderRoom(data);
    } else if (type === "event") {
      if (data.text) {
        this.ui.appendLog(data.text, "event");
      }
    } else if (type === "inventory") {
      this.ui.renderInventory(data);
    } else if (type === "error") {
      if (data.message) {
        this.ui.appendLog(data.message, "error");
      }
    }
  }

  sendCommand(text) {
    if (!text || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }
    this.ws.send(JSON.stringify({ type: "command", input: text }));
  }
}

const ui = new UiController();
const client = new GameClient(ui);
client.init();
