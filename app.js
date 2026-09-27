const defaultApiOrigin = window.location.protocol === 'http:' || window.location.protocol === 'https:'
  ? `${window.location.protocol}//${window.location.hostname}:8000`
  : 'http://localhost:8000';
const API_URL = window.FARMER_API_URL || `${defaultApiOrigin}/ask`;
const OFFLINE_FLAG = 'offline_ai_enabled';
const elements = {
  form: document.querySelector('#chatForm'), input: document.querySelector('#questionInput'),
  messages: document.querySelector('#messages'), typing: document.querySelector('#typingIndicator'),
  send: document.querySelector('.send-button'), status: document.querySelector('#onlineStatus'),
  statusLabel: document.querySelector('.status-label'), offlineAI: document.querySelector('#offlineAI'),
  offlineModal: document.querySelector('#offlineModal'), offlineConfirm: document.querySelector('#offlineConfirm'),
  offlineDismiss: document.querySelector('#offlineDismiss'), offlineCancel: document.querySelector('#offlineCancel'),
  offlineMessage: document.querySelector('#offlineMessage')
};
const localAnswers = {
  disease: 'Check affected leaves, isolate badly affected plants, and consult a local agriculture officer for a confirmed diagnosis.',
  fertilizer: 'Avoid applying fertilizer without a soil test. Use the crop and soil details for a specific recommendation.',
  default: 'I cannot reach the farm knowledge service right now. Ask about crops, diseases, soil, weather, or fertilizers when the connection returns.'
};

function offlineEnabled() { return localStorage.getItem(OFFLINE_FLAG) === 'true'; }
function setOnlineStatus() {
  const online = navigator.onLine;
  elements.status.classList.toggle('is-offline', !online);
  elements.statusLabel.textContent = online ? 'Online' : 'Offline';
  elements.status.setAttribute('aria-label', online ? 'Online' : 'Offline');
}
function scrollToLatest() { elements.messages.scrollTop = elements.messages.scrollHeight; }
function addMessage(text, role, label = 'Now') {
  const article = document.createElement('article');
  article.className = `message message--${role}`;
  const avatar = role === 'assistant' ? '🌱' : '👨‍🌾';
  article.innerHTML = `<div class="avatar" aria-hidden="true">${avatar}</div><div class="bubble"><p></p><time></time></div>`;
  article.querySelector('p').textContent = text;
  article.querySelector('time').textContent = label;
  elements.messages.append(article);
  scrollToLatest();
}
function localAnswer(question) {
  const lower = question.toLowerCase();
  if (lower.includes('disease') || lower.includes('yellow') || lower.includes('spot')) return localAnswers.disease;
  if (lower.includes('fertilizer') || lower.includes('fertiliser')) return localAnswers.fertilizer;
  return localAnswers.default;
}
function setLoading(loading) {
  elements.typing.hidden = !loading;
  elements.input.disabled = loading;
  elements.send.disabled = loading;
  if (loading) scrollToLatest();
}
async function askAssistant(question) {
  if (!navigator.onLine) throw new Error('offline');
  const response = await fetch(API_URL, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ query: question })
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false) throw new Error(data.error || `Request failed (${response.status})`);
  if (typeof data.answer !== 'string' || !data.answer.trim()) throw new Error('Empty response');
  return { answer: data.answer.trim(), mode: data.mode || 'fallback' };
}
function closeOfflineModal() { elements.offlineModal.hidden = true; }
function markOfflineAIEnabled() {
  localStorage.setItem(OFFLINE_FLAG, 'true');
  elements.offlineAI.classList.add('is-enabled');
  elements.offlineAI.textContent = 'Offline AI ready';
}
function openOfflineModal() {
  if (offlineEnabled()) {
    addMessage('Offline AI is ready. A local model slot is prepared for Gemma, TinyLlama, or WebLLM.', 'assistant', 'Offline AI');
    return;
  }
  elements.offlineMessage.textContent = 'Prepare offline AI (~500 MB simulated download)?';
  elements.offlineConfirm.disabled = false;
  elements.offlineConfirm.textContent = 'Enable Offline AI';
  elements.offlineModal.hidden = false;
  elements.offlineConfirm.focus();
}
function simulateOfflineDownload() {
  elements.offlineConfirm.disabled = true;
  elements.offlineConfirm.textContent = 'Preparing...';
  elements.offlineMessage.textContent = 'Preparing offline AI (simulation)...';
  window.setTimeout(() => {
    markOfflineAIEnabled(); closeOfflineModal();
    addMessage('Offline AI is ready. Local answers will be used when the service or internet is unavailable.', 'assistant', 'Offline AI');
  }, 900);
}

elements.form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = elements.input.value.trim();
  if (!question) return;
  addMessage(question, 'user'); elements.input.value = ''; setLoading(true);
  try {
    const result = offlineEnabled()
      ? { answer: localAnswer(question), mode: 'fallback' }
      : await askAssistant(question);
    addMessage(result.answer, 'assistant', result.mode === 'rag+llm' ? 'AI answer' : result.mode.toUpperCase());
  } catch (error) {
    console.warn('Assistant unavailable:', error);
    addMessage(`${error.message === 'offline' ? 'You are offline.' : 'The service is unavailable.'}\n\n${localAnswer(question)}`, 'assistant', 'Local guidance');
  } finally { setLoading(false); elements.input.focus(); }
});
window.addEventListener('online', setOnlineStatus);
window.addEventListener('offline', setOnlineStatus);
elements.offlineAI.addEventListener('click', openOfflineModal);
elements.offlineConfirm.addEventListener('click', simulateOfflineDownload);
elements.offlineDismiss.addEventListener('click', closeOfflineModal);
elements.offlineCancel.addEventListener('click', closeOfflineModal);
elements.offlineModal.addEventListener('click', (event) => { if (event.target === elements.offlineModal) closeOfflineModal(); });
if (offlineEnabled()) markOfflineAIEnabled();
setOnlineStatus();