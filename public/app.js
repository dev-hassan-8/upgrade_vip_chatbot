const chatEl = document.getElementById("chat");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("message-input");
const sendButtonEl = document.getElementById("send-button");
const errorEl = document.getElementById("error");

let conversationId = null;
let isSending = false;

function scrollChatToBottom() {
  requestAnimationFrame(() => {
    chatEl.scrollTop = chatEl.scrollHeight;
    const lastMessage = chatEl.lastElementChild;
    if (lastMessage) {
      lastMessage.scrollIntoView({ block: "end", behavior: "smooth" });
    }
  });
}

function appendMessage(role, text) {
  const message = document.createElement("div");
  message.className = `message ${role}`;
  message.textContent = text;
  chatEl.appendChild(message);
  scrollChatToBottom();
  return message;
}

function setError(message) {
  if (!message) {
    errorEl.hidden = true;
    errorEl.textContent = "";
    return;
  }
  errorEl.hidden = false;
  errorEl.textContent = message;
  scrollChatToBottom();
}

function formatApiDetail(detail) {
  if (!detail) return "Unable to send message.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "string" ? item : item.msg || JSON.stringify(item)))
      .join(" ");
  }
  return String(detail);
}

async function readJsonResponse(response) {
  const raw = await response.text();
  if (!raw || !raw.trim()) {
    throw new Error(
      response.ok
        ? "The server returned an empty reply. Please try again in a moment."
        : `Request failed (${response.status}). Please try again.`
    );
  }
  try {
    return JSON.parse(raw);
  } catch (_error) {
    throw new Error(
      "Got an unexpected reply from the server. Please refresh and try again."
    );
  }
}

async function sendMessage(message) {
  if (isSending) return;

  isSending = true;
  sendButtonEl.disabled = true;
  setError("");
  appendMessage("user", message);
  inputEl.value = "";

  const loadingMessage = appendMessage("assistant loading", "Typing...");
  const startedAt = Date.now();
  const slowTimer = setTimeout(() => {
    if (loadingMessage.isConnected) {
      loadingMessage.textContent = "Still working... almost there.";
      scrollChatToBottom();
    }
  }, 4000);

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
      }),
    });

    const data = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiDetail(data.detail) || "Unable to send message.");
    }
    if (!data.answer) {
      throw new Error("No reply was returned. Please try again.");
    }

    conversationId = data.conversation_id;
    loadingMessage.remove();
    appendMessage("assistant", data.answer);
    console.debug("Reply time (ms):", Date.now() - startedAt);
  } catch (error) {
    loadingMessage.remove();
    const messageText = error && error.message ? error.message : "";
    if (/failed to fetch|networkerror|load failed/i.test(messageText)) {
      setError("Connection interrupted. Please check your link and try again.");
    } else {
      setError(messageText || "Something went wrong. Please try again.");
    }
  } finally {
    clearTimeout(slowTimer);
    isSending = false;
    sendButtonEl.disabled = false;
    inputEl.focus();
  }
}

formEl.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = inputEl.value.trim();
  if (!message) return;
  sendMessage(message);
});

appendMessage(
  "assistant",
  "Hello. I can help with UpgradeVIP airport VIP services and transfers. What would you like to know?"
);
