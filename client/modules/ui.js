export class UiController {
  constructor() {
    this.logEl = document.getElementById("log");
    this.inputEl = document.getElementById("command-input");
    this.overlayEl = document.getElementById("overlay");
    this.characterListEl = document.getElementById("character-list");
    this.loginErrorEl = document.getElementById("login-error");
    this.characterNameEl = document.getElementById("character-name");
    this.characterDescEl = document.getElementById("character-description");
    this.goldCountEl = document.getElementById("gold-count");
    this.roomNameEl = document.getElementById("room-name");
    this.roomExitsEl = document.getElementById("room-exits");
    this.inventoryItemsEl = document.getElementById("inventory-items");
    this.minimapEl = document.getElementById("minimap");
    this.controlButtons = Array.from(
      document.querySelectorAll("[data-command]")
    );
  }

  showOverlay(show) {
    this.overlayEl.style.display = show ? "block" : "none";
  }

  setCharacterInfo(name, description = "") {
    this.characterNameEl.textContent = name;
    this.characterDescEl.textContent = description;
  }

  setLoginError(message) {
    this.loginErrorEl.textContent = message;
  }

  appendLog(text, kind = "normal") {
    const div = document.createElement("div");
    div.className = `log-line ${kind}`;
    div.textContent = text;
    this.logEl.appendChild(div);
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }

  renderCharacters(characters, onSelect) {
    this.characterListEl.innerHTML = "";
    if (!characters.length) {
      const msg = document.createElement("div");
      msg.textContent = "No characters are currently available.";
      this.characterListEl.appendChild(msg);
      return;
    }
    characters.forEach((c) => {
      const div = document.createElement("div");
      div.className = "character-option";
      div.dataset.characterId = c.id;

      const name = document.createElement("div");
      name.className = "character-option-name";
      name.textContent = c.name;

      const desc = document.createElement("div");
      desc.className = "character-option-description";
      desc.textContent = c.shortDescription;

      div.appendChild(name);
      div.appendChild(desc);
      div.addEventListener("click", () => onSelect(c));
      this.characterListEl.appendChild(div);
    });
  }

  renderRoom(room) {
    if (room.name) {
      this.roomNameEl.textContent = room.name;
    }
    if (room.exits) {
      this.roomExitsEl.textContent = `Exits: ${room.exits.join(", ")}`;
      this._updateControlButtons(room.exits);
    }
    if (room.minimap && this.minimapEl) {
      this.minimapEl.textContent = room.minimap;
    }
    if (room.description) {
      this.appendLog(`\n${room.name}\n${room.description}`, "normal");
    }
  }

  renderInventory(data) {
    if (typeof data.coins === "number") {
      this.goldCountEl.textContent = String(data.coins);
    }
    if (Array.isArray(data.items) && this.inventoryItemsEl) {
      this.inventoryItemsEl.innerHTML = "";
      data.items.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item.name;
        this.inventoryItemsEl.appendChild(li);
      });
    }
  }

  bindCommandInput(handler) {
    this.inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const value = this.inputEl.value.trim();
        if (!value) {
          return;
        }
        handler(value);
        this.inputEl.value = "";
      }
    });
  }

  bindControlButtons(handler) {
    this.controlButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) {
          return;
        }
        const cmd = btn.dataset.command;
        if (cmd) {
          handler(cmd);
        }
      });
    });
  }

  focusInput() {
    this.inputEl.focus();
  }

  _updateControlButtons(exits) {
    const exitsSet = new Set((exits || []).map((e) => String(e).toLowerCase()));
    this.controlButtons.forEach((btn) => {
      const cmd = (btn.dataset.command || "").toLowerCase();
      if (cmd === "n" || cmd === "s" || cmd === "e" || cmd === "w") {
        const needed =
          cmd === "n"
            ? "north"
            : cmd === "s"
            ? "south"
            : cmd === "e"
            ? "east"
            : "west";
        btn.disabled = !exitsSet.has(needed);
      }
    });
  }
}
