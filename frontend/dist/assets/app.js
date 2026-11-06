"use strict";

// 页面只调用同源聊天与历史接口；密钥、模型客户端和工具执行都留在 Python 后端。
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
const historyDialog = document.querySelector("#history-dialog");
const switchHistoryDialog = document.querySelector("#switch-history-dialog");
const openHistory = document.querySelector("#open-history");
const refreshHistory = document.querySelector("#refresh-history");
const historyLists = [document.querySelector("#history-list"), document.querySelector("#history-dialog-list")];
const historyNotices = [document.querySelector("#history-notice"), document.querySelector("#history-dialog-notice")];
const suggestions = [...document.querySelectorAll("[data-prompt]")];
let conversationId = crypto.randomUUID();
let busy = false;
let turnCount = 0;
let toastTimer;
let savedConversationIds = [];
let historyFetchVersion = 0;
let pendingHistoryId = null;
const conversationTitles = new Map();

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
  openHistory.disabled = value;
  refreshHistory.disabled = value;
  document.querySelectorAll("[data-conversation-id]").forEach((button) => {
    button.disabled = value;
  });
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

function renderHistoryLists() {
  for (const list of historyLists) {
    list.replaceChildren();
    for (const id of savedConversationIds) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "history-item";
      button.dataset.conversationId = id;
      button.disabled = busy;
      button.title = id;
      const title = document.createElement("span");
      title.textContent = conversationTitles.get(id) || `会话 ${id.slice(0, 8)}`;
      button.append(title);
      if (id === conversationId) {
        button.setAttribute("aria-current", "true");
        const current = document.createElement("small");
        current.textContent = "当前";
        button.append(current);
      }
      button.addEventListener("click", () => switchConversation(id));
      list.append(button);
    }
  }
}

async function refreshConversations() {
  const version = ++historyFetchVersion;
  historyNotices.forEach((notice) => { notice.textContent = "正在读取会话列表…"; });
  try {
    const response = await fetch("/conversations", { cache: "no-store" });
    if (!response.ok) throw new Error("history_list_failed");
    const data = await response.json();
    if (!Array.isArray(data?.conversations) || !data.conversations.every(
      (id) => typeof id === "string" && id.length > 0 && id.length <= 100,
    )) throw new Error("invalid_history_list");
    if (version !== historyFetchVersion) return;
    savedConversationIds = [...new Set(data.conversations)];
    renderHistoryLists();
    historyNotices.forEach((notice) => {
      notice.textContent = savedConversationIds.length ? "" : "还没有已保存的会话，完成一次问答后会出现在这里。";
    });
  } catch {
    if (version !== historyFetchVersion) return;
    historyNotices.forEach((notice) => {
      notice.textContent = "会话列表读取失败，请检查本地服务后手动刷新。";
    });
  }
}

function rememberConversation() {
  const url = new URL(location.href);
  url.hash = new URLSearchParams({ conversation: conversationId }).toString();
  window.history.replaceState(null, "", url);
}

async function switchConversation(id, initial = false, discardDraft = false) {
  if (busy) return;
  if (id === conversationId) {
    historyDialog.close();
    return;
  }
  if (question.value.trim() && !discardDraft) {
    pendingHistoryId = id;
    switchHistoryDialog.returnValue = "cancel";
    switchHistoryDialog.showModal();
    return;
  }
  const previousStatus = status.textContent;
  setBusy(true);
  status.textContent = "正在从本机数据库读取历史，不会调用模型…";
  try {
    const response = await fetch(`/conversations/${encodeURIComponent(id)}/messages`, { cache: "no-store" });
    if (!response.ok) throw new Error("history_failed");
    const data = await response.json();
    if (data?.conversation_id !== id || !Array.isArray(data.messages) || !data.messages.length ||
        !data.messages.every((row) => row && ["user", "assistant"].includes(row.role) && typeof row.content === "string")) {
      throw new Error("invalid_history");
    }
    // 验证读取结果成功后才切换，失败时保留原会话和草稿。
    conversationId = id;
    turnCount = data.messages.filter((row) => row.role === "assistant").length;
    const title = data.messages.find((row) => row.role === "user")?.content || `会话 ${id.slice(0, 8)}`;
    conversationTitles.set(id, title);
    document.querySelector("#session-title").textContent = title;
    messages.replaceChildren();
    for (const row of data.messages) {
      const message = addMessage(row.role, row.content);
      if (row.role === "assistant") addCopyAction(message.article, row.content);
    }
    question.value = "";
    updateSessionLabel();
    rememberConversation();
    renderHistoryLists();
    status.textContent = `已恢复 ${turnCount} 轮对话 · 可以继续提问`;
    historyDialog.close();
  } catch {
    status.textContent = previousStatus;
    showToast("历史读取失败或会话不存在，当前对话未切换；请检查服务后手动重试。");
    if (initial) window.history.replaceState(null, "", location.pathname + location.search);
  } finally {
    setBusy(false);
    question.focus();
  }
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

async function errorForResponse(response) {
  // 只识别约定的错误码，不直接回显未知服务错误或SDK异常全文。
  {
    try {
      const body = await response.json();
      const messages = {
        output_truncated: "模型回答因长度限制被截断，本轮未保存。请缩小问题范围，或提高后端 max_tokens 后手动发送；不会自动重试。",
        model_call_limit: "本次问答已达到模型请求次数上限，任务尚未完成，本轮未保存。请拆分问题后手动发送；不会继续调用工具或自动重试。",
        tool_rejected: "工具请求被拒绝：工具名称、访问路径或数量不符合规则。本轮未保存；请使用白名单内的文件，不要通过放宽权限来绕过检查。",
        invalid_tool_arguments: "模型提出的工具参数不合法，本轮未保存。请明确问题后手动发送；程序不会执行这条不合格的工具请求。",
        tool_failed: "工具读取文件失败，本轮未保存。请检查文件是否存在、读取权限及UTF-8编码，再手动发送。",
        invalid_tool_call: "模型返回的工具请求缺失必要信息或编号不正确，本轮未保存，不继续执行工具。",
        invalid_model_response: "模型返回的数据未通过检查，本轮未保存；请检查后端，不会自动重试。",
        incomplete_model_response: "模型响应未正常完成，本轮未保存；请稍后手动发送。",
        empty_model_response: "模型没有返回有效正文，本轮未保存；请调整问题后手动发送。",
        model_refused: "模型未提供可用回答，本轮未保存；请调整问题，不会自动重试。",
        configuration_error: "后端缺少模型配置。请检查项目.env中的密钥和模型名称，不要把密钥填入网页。",
        model_timeout: "模型请求超时，本轮未保存。请先检查后端状态，等待后再手动发送；不会自动重试。",
        model_connection_failed: "后端无法连接模型服务，本轮未保存。请检查后端网络与代理配置，再手动发送。",
        model_auth_failed: "模型密钥认证失败。请在后端.env中检查密钥，不要把真实密钥贴到网页或聊天里。",
        model_permission_denied: "当前模型密钥没有访问权限，请检查模型名称和账户权限。",
        model_rate_limited: "模型服务限流，本轮未保存。请稍等后手动发送；不会自动重试。",
        model_balance_exhausted: "模型账户余额不足，本轮未保存，请检查DeepSeek账户额度。",
        model_service_error: "模型服务暂时不可用，本轮未保存，请稍后手动发送。",
        model_request_rejected: "模型服务拒绝了请求，请检查后端模型名称、请求参数或上下文长度；本轮未保存。",
        model_request_failed: "模型请求未完成，本轮未保存，请检查后端配置和服务状态。",
        invalid_input: "问题不能为空，请输入有效问题后发送。",
      };
      const code = body?.detail?.code;
      if (typeof code === "string" && Object.hasOwn(messages, code)) {
        return messages[code];
      }
    } catch {
      // 兼容旧接口、非JSON错误页和没有错误码的响应。
    }
  }
  return errorForStatus(response.status);
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
    if (!response.ok) throw new Error(await errorForResponse(response));
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
    conversationTitles.set(conversationId, document.querySelector("#session-title").textContent);
    rememberConversation();
    status.textContent = "本轮已完成 · 对话已保存到本机数据库";
    void refreshConversations();
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
  window.history.replaceState(null, "", location.pathname + location.search);
  renderHistoryLists();
  updateComposer();
  scrollArea.scrollTop = 0;
  question.focus();
  showToast("新对话已创建，不会带入旧对话的上下文");
}

newChat.addEventListener("click", requestNewChat);
refreshHistory.addEventListener("click", () => { if (!busy) void refreshConversations(); });
openHistory.addEventListener("click", () => {
  if (busy) return;
  historyDialog.showModal();
  void refreshConversations();
});
switchHistoryDialog.addEventListener("close", () => {
  const id = pendingHistoryId;
  pendingHistoryId = null;
  if (switchHistoryDialog.returnValue === "switch" && id) {
    void switchConversation(id, false, true);
  }
});
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
const restoredId = new URLSearchParams(location.hash.slice(1)).get("conversation");
if (restoredId && restoredId.length <= 100) void switchConversation(restoredId, true);
void refreshConversations();
