const API_BASE = "/api";

export async function fetchAvailableCharacters() {
  const res = await fetch(`${API_BASE}/characters/available`);
  if (!res.ok) {
    throw new Error("Failed to fetch characters");
  }
  return res.json();
}

export async function loginWithCharacter(characterId) {
  const res = await fetch(`${API_BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ characterId }),
  });
  if (!res.ok) {
    throw new Error("Login failed");
  }
  return res.json();
}

export function createWebSocket(sessionId, { onOpen, onMessage, onClose }) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${window.location.host}/ws?sessionId=${encodeURIComponent(
    sessionId
  )}`;
  const ws = new WebSocket(url);
  if (onOpen) {
    ws.addEventListener("open", onOpen);
  }
  if (onMessage) {
    ws.addEventListener("message", (event) => {
      try {
        const msg = JSON.parse(event.data);
        onMessage(msg);
      } catch {
        // ignore malformed payloads
      }
    });
  }
  if (onClose) {
    ws.addEventListener("close", onClose);
  }
  return ws;
}
