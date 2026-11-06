"use strict";

// 页面只调用同源 /chat；密钥、模型客户端和工具执行都留在 Python 后端。
const form = document.querySelector("#chat-form");
const question = document.querySelector("#question");
const send = document.querySelector("#send");
const sendLabel = document.querySelector("#send-label");
const messages = document.querySelector("#messages");
const welcome = document.querySelector("#welcome");
const scrollArea = document.querySelector("#conversation-scroll");
const status = document.querySelector("#request-status");
const newChat = document.querySelector("#new-chat");
const dialog = document.querySelector("#new-chat-dialog");
const suggestions = [...document.querySelectorAll("[data-prompt]")];
let conversationId = crypto.randomUUID();
let busy = false;
let turnCount = 0;
let toastTimer;

function updateSessionLabel() {
  const label = document.querySelector("#session-id");
  label.textContent = conversationId.slice(0, 8);
  label.title = conversationId;
}

function updateComposer() {
  document.querySelector("#character-count").textContent =
    `${[...question.value].length} / 4000`;
  send.disabled = busy || !question.value.trim();
  question.style.height = "auto";
  question.style.height = `${Math.min(question.scrollHeight, 180)}px`;
}

function setBusy(value) {
  busy = value;
  form.setAttribute("aria-busy", String(value));
  question.readOnly = value;
  newChat.disabled = value;
  document.querySelector("#new-chat-mobile").disabled = value;
  suggestions.forEach((button) => {
    button.disabled = value;
  });
  sendLabel.textContent = value ? "等待中" : "发送";
  updateComposer();
}

function scrollToLatest() {
  scrollArea.scrollTop = scrollArea.scrollHeight;
}

function showToast(text) {
  const toast = document.querySelector("#toast");
  clearTimeout(toastTimer);
  toast.textContent = text;
  toast.hidden = false;
  toastTimer = setTimeout(() => {
    toast.hidden = true;
  }, 3000);
}

// 只创建文本节点和代码块，不把模型或用户的输出当作 HTML 执行。
function renderText(container, text) {
  const pattern = /```[^\n`]*\n([\s\S]*?)```/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) {
      const paragraph = document.createElement("p");
      paragraph.textContent = text.slice(cursor, match.index);
      container.append(paragraph);
    }
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.textContent = match[1];
    pre.append(code);
    container.append(pre);
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) {
    const paragraph = document.createElement("p");
    paragraph.textContent = text.slice(cursor);
    container.append(paragraph);
  }
}

function addMessage(role, text) {
  welcome.hidden = true;
  const article = document.createElement("article");
  article.className = `message message--${role}`;
  const header = document.createElement("div");
  header.className = "message-header";
  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "user" ? "U" : ">_";
  const name = document.createElement("span");
  name.textContent = role === "user" ? "你" : "Mini Code Agent";
  header.append(avatar, name);
  const content = document.createElement("div");
  content.className = "message-content";
  if (text) renderText(content, text);
  article.append(header, content);
  messages.append(article);
  scrollToLatest();
  return { article, content };
}

function addCopyAction(article, text) {
  const actions = document.createElement("div");
  actions.className = "message-actions";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "copy-button";
  button.textContent = "复制回答";
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      showToast("回答已复制");
    } catch {
      showToast("无法访问剪贴板，请手动选择文字复制");
    }
  });
  actions.append(button);
  article.append(actions);
}

function errorForStatus(code) {
  if (code === 422)
    return "问题或会话参数未通过校验。请检查输入长度，调整后手动发送。";
  if (code === 502)
    return "后端未完成本次问答，可能是工具权限或模型输出检查未通过。本轮未保存，请调整问题后手动发送。";
  if (code === 404)
    return "没有找到 /chat 接口。请确认从本项目的本地服务打开网页。";
  return `请求失败（HTTP ${code}）。请检查后端终端、网络与模型配置；不会自动重试。`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  const text = question.value.trim();
  if (!text) return;
  if ([...text].length > 4000) {
    showToast("问题不能超过4000个字符");
    return;
  }
  setBusy(true);
  addMessage("user", text);
  if (turnCount === 0)
    document.querySelector("#session-title").textContent = text;
  question.value = "";
  updateComposer();
  const pending = addMessage("assistant", "");
  pending.content.classList.add("pending-content");
  const dots = document.createElement("span");
  dots.className = "dots";
  dots.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 3; i += 1) dots.append(document.createElement("i"));
  const pendingLabel = document.createElement("span");
  pendingLabel.textContent = "正在等待 Agent 返回…";
  pending.content.append(dots, pendingLabel);
  scrollToLatest();
  const started = Date.now();
  status.textContent = "请求已发送；需要工具时，会先读取文件再生成回答。";
  const timer = setInterval(() => {
    const seconds = Math.floor((Date.now() - started) / 1000);
    status.textContent =
      seconds >= 45
        ? `已等待 ${seconds} 秒，后台可能仍在处理，请勿重复发送。`
        : "请求处理中，不会自动重试。";
  }, 5000);
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, question: text }),
    });
    if (!response.ok) throw new Error(errorForStatus(response.status));
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(
        "后端没有返回有效JSON，本次未取得可展示的答案。请检查服务，不会自动重试。",
      );
    }
    if (!data || typeof data.answer !== "string" || !data.answer.trim()) {
      throw new Error(
        "后端返回的 answer 为空或类型不正确。请检查接口，不会自动重试。",
      );
    }
    pending.content.replaceChildren();
    pending.content.classList.remove("pending-content");
    renderText(pending.content, data.answer);
    addCopyAction(pending.article, data.answer);
    turnCount += 1;
    status.textContent = "本轮已完成 · 上下文保存在当前后端进程中";
  } catch (error) {
    pending.content.replaceChildren();
    pending.content.classList.remove("pending-content");
    pending.content.classList.add("error-content");
    pending.content.setAttribute("role", "alert");
    pending.content.textContent =
      error instanceof TypeError
        ? "连接中断或本地服务未启动。后台可能仍在处理原请求，请先检查终端；不会自动重试。"
        : error.message;
    question.value = text;
    status.textContent = "未取得成功响应 · 问题已放回输入框，不会自动重新发送";
  } finally {
    clearInterval(timer);
    setBusy(false);
    scrollToLatest();
    question.focus();
  }
});

question.addEventListener("input", updateComposer);
question.addEventListener("keydown", (event) => {
  if (
    event.key === "Enter" &&
    !event.shiftKey &&
    !event.isComposing &&
    event.keyCode !== 229
  ) {
    event.preventDefault();
    if (!busy) form.requestSubmit();
  }
});

suggestions.forEach((button) => {
  button.addEventListener("click", () => {
    if (busy) return;
    question.value = button.dataset.prompt;
    updateComposer();
    question.focus();
  });
});

function requestNewChat() {
  if (busy) return;
  if (messages.childElementCount || question.value.trim()) {
    // 每次打开都重置，避免上次确认后按Escape仍沿用旧的返回值。
    dialog.returnValue = "cancel";
    dialog.showModal();
  } else {
    resetConversation();
  }
}

function resetConversation() {
  conversationId = crypto.randomUUID();
  turnCount = 0;
  messages.replaceChildren();
  welcome.hidden = false;
  question.value = "";
  document.querySelector("#session-title").textContent = "新的代码对话";
  status.textContent = "";
  updateSessionLabel();
  updateComposer();
  scrollArea.scrollTop = 0;
  question.focus();
  showToast("新对话已创建，不会带入旧对话的上下文");
}

newChat.addEventListener("click", requestNewChat);
dialog.addEventListener("close", () => {
  if (dialog.returnValue === "new") resetConversation();
});

// 窄屏不显示侧栏，仍提供同一个新建对话入口。
const mobileNewChat = document.createElement("button");
mobileNewChat.id = "new-chat-mobile";
mobileNewChat.type = "button";
mobileNewChat.className = "new-chat-mobile";
mobileNewChat.textContent = "＋";
mobileNewChat.setAttribute("aria-label", "新建对话");
mobileNewChat.addEventListener("click", requestNewChat);
document.querySelector(".breadcrumb").append(mobileNewChat);

window.addEventListener("beforeunload", (event) => {
  if (busy) {
    event.preventDefault();
    event.returnValue = "";
  }
});

document.querySelector("#local-address").textContent = location.host;
updateSessionLabel();
updateComposer();
