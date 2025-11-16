(() => {
  const logEl = document.getElementById("log");
  const inputEl = document.getElementById("command-input");
  const overlayEl = document.getElementById("overlay");
  const characterListEl = document.getElementById("character-list");
  const loginErrorEl = document.getElementById("login-error");
  const characterNameEl = document.getElementById("character-name");
  const characterDescEl = document.getElementById("character-description");
  const goldCountEl = document.getElementById("gold-count");
  const roomNameEl = document.getElementById("room-name");
  const roomExitsEl = document.getElementById("room-exits");

  let sessionId = null;
  let ws = null;
  let currentCharacter = null;

  function appendLog(text, kind = "normal") {
    const div = document.createElement("div");
    div.className = `log-line ${kind}`;
    div.textContent = text;
    logEl.appendChild(div);
    logEl.scrollTop = logEl.scrollHeight;
  }

  async function fetchAvailableCharacters() {
    try {
      const res = await fetch("/api/characters/available");
      if (!res.ok) {
        throw new Error("Failed to fetch characters");
      }
      const data = await res.json();
      renderCharacterOptions(data.characters || []);
    } catch (err) {
      loginErrorEl.textContent =
        "Could not load characters. Is the server running?";
    }
  }

  function renderCharacterOptions(characters) {
    characterListEl.innerHTML = "";
    if (!characters.length) {
      const msg = document.createElement("div");
      msg.textContent = "No characters are currently available.";
      characterListEl.appendChild(msg);
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
      div.addEventListener("click", () => loginWithCharacter(c));
      characterListEl.appendChild(div);
    });
  }

  async function loginWithCharacter(character) {
    try {
      loginErrorEl.textContent = "";
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ characterId: character.id }),
      });
      if (!res.ok) {
        throw new Error("Login failed");
      }
      const data = await res.json();
      sessionId = data.sessionId;
      currentCharacter = {
        id: data.characterId,
        name: data.playerName,
      };
      onLoggedIn();
      connectWebSocket();
    } catch (err) {
      loginErrorEl.textContent =
        "Login failed. The character may have been taken.";
      await fetchAvailableCharacters();
    }
  }

  function onLoggedIn() {
    overlayEl.style.display = "none";
    characterNameEl.textContent = currentCharacter.name;
    characterDescEl.textContent = "";
    inputEl.focus();
    appendLog(`You enter the Jungeon as ${currentCharacter.name}.`, "system");
  }

  function connectWebSocket() {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/ws?sessionId=${encodeURIComponent(
      sessionId
    )}`;
    ws = new WebSocket(url);

    ws.addEventListener("open", () => {
      appendLog("Connection to the dungeon established.", "system");
    });

    ws.addEventListener("message", (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleServerMessage(msg);
      } catch {
        // Ignore malformed messages
      }
    });

    ws.addEventListener("close", () => {
      appendLog(
        "Your connection to the dungeon has been lost.",
        "error"
      );
    });
  }

  function handleServerMessage(msg) {
    const { type, data } = msg;
    if (type === "roomState") {
      if (data.name) {
        roomNameEl.textContent = data.name;
      }
      if (data.exits) {
        roomExitsEl.textContent = `Exits: ${data.exits.join(", ")}`;
      }
      if (data.description) {
        appendLog(`\n${data.name}\n${data.description}`, "normal");
      }
    } else if (type === "event") {
      if (data.text) appendLog(data.text, "event");
    } else if (type === "inventory") {
      if (typeof data.coins === "number") {
        goldCountEl.textContent = String(data.coins);
      }
    } else if (type === "error") {
      if (data.message) appendLog(data.message, "error");
    }
  }

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const value = inputEl.value.trim();
      if (!value || !ws || ws.readyState !== WebSocket.OPEN) {
        return;
      }
      ws.send(JSON.stringify({ type: "command", input: value }));
      inputEl.value = "";
    }
  });

  fetchAvailableCharacters();
})();

