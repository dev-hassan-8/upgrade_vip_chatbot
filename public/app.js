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

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Unable to send message.");
    }

    conversationId = data.conversation_id;
    loadingMessage.remove();
    appendMessage("assistant", data.answer);
    console.debug("Reply time (ms):", Date.now() - startedAt);
  } catch (error) {
    loadingMessage.remove();
    setError(error.message || "Something went wrong. Please try again.");
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
