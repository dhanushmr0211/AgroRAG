const API_URL = window.FARMER_API_URL || 'https://agrorag-xfrx.onrender.com/ask';
const OFFLINE_FLAG = 'offline_ai_enabled';
const CACHE_KEY = 'farmer_ai_answers';
const elements = {
  form: document.getElementById('chatForm'),
  input: document.getElementById('questionInput'),
  messages: document.getElementById('messages'),
  typing: document.getElementById('typingIndicator'),
  send: document.querySelector('.send-button'),
  status: document.getElementById('onlineStatus'),
  statusLabel: document.querySelector('.status-label'),
  offlineAI: document.getElementById('offlineAI'),
  offlineModal: document.getElementById('offlineModal'),
  offlineConfirm: document.getElementById('offlineConfirm'),
  offlineDismiss: document.getElementById('offlineDismiss'),
  offlineCancel: document.getElementById('offlineCancel'),
  offlineMessage: document.getElementById('offlineMessage')
};
const localAnswers = {
  disease: 'Check affected leaves, isolate badly affected plants, and consult a local agriculture officer for a confirmed diagnosis.',
  fertilizer: 'Avoid applying fertilizer without a soil test. Use crop and soil details for a specific recommendation.',
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
  article.innerHTML = `<div class="avatar" aria-hidden="true">${role === 'assistant' ? '🌱' : '👨‍🌾'}</div><div class="bubble"><p></p><time></time></div>`;
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
function readCachedAnswer(question) {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY) || '{}')[question.toLowerCase()] || ''; } catch { return ''; }
}
function cacheAnswer(question, answer) {
  try {
    const cache = JSON.parse(localStorage.getItem(CACHE_KEY) || '{}');
    cache[question.toLowerCase()] = answer;
    localStorage.setItem(CACHE_KEY, JSON.stringify(Object.fromEntries(Object.entries(cache).slice(-20))));
  } catch { /* Storage can be disabled by the browser. */ }
}
function setLoading(loading) { elements.typing.hidden = !loading; elements.input.disabled = loading; elements.send.disabled = loading; if (loading) scrollToLatest(); }
async function askAssistant(question) {
  if (!navigator.onLine) throw new Error('offline');
  const response = await fetch(API_URL, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ query: question }), signal: AbortSignal.timeout(15000) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false) throw new Error(data.error || `Request failed (${response.status})`);
  if (typeof data.answer !== 'string' || !data.answer.trim()) throw new Error('Empty response');
  return { answer: data.answer.trim(), mode: data.mode || 'fallback' };
}
function closeOfflineModal() { elements.offlineModal.hidden = true; }
function markOfflineAIEnabled() { localStorage.setItem(OFFLINE_FLAG, 'true'); elements.offlineAI.classList.add('is-enabled'); elements.offlineAI.textContent = 'Offline AI ready'; }
function openOfflineModal() {
  if (offlineEnabled()) { addMessage('Offline AI is ready. The local model slot is prepared for a future Gemma, TinyLlama, or WebLLM integration.', 'assistant', 'Offline AI'); return; }
  elements.offlineModal.hidden = false; elements.offlineConfirm.focus();
}
function simulateOfflineDownload() {
  elements.offlineConfirm.disabled = true; elements.offlineConfirm.textContent = 'Preparing...'; elements.offlineMessage.textContent = 'Preparing offline AI (simulation)...';
  window.setTimeout(() => { markOfflineAIEnabled(); closeOfflineModal(); addMessage('Offline AI is ready. Local answers will be used when the service or internet is unavailable.', 'assistant', 'Offline AI'); }, 900);
}
elements.form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = elements.input.value.trim();
  if (!question) return;
  addMessage(question, 'user'); elements.input.value = ''; setLoading(true);
  try {
    let result;
    if (offlineEnabled()) result = { answer: readCachedAnswer(question) || localAnswer(question), mode: 'fallback' };
    else { result = await askAssistant(question); cacheAnswer(question, result.answer); }
    addMessage(result.answer, 'assistant', result.mode === 'rag+llm' ? 'AI answer' : result.mode.toUpperCase());
  } catch (error) {
    const cached = readCachedAnswer(question);
    addMessage(`${error.message === 'offline' ? 'You are offline.' : 'The service is unavailable.'}\n\n${cached || localAnswer(question)}`, 'assistant', cached ? 'Cached answer' : 'Local guidance');
  } finally { setLoading(false); elements.input.focus(); }
});
window.addEventListener('online', setOnlineStatus); window.addEventListener('offline', setOnlineStatus);
elements.offlineAI.addEventListener('click', openOfflineModal); elements.offlineConfirm.addEventListener('click', simulateOfflineDownload); elements.offlineDismiss.addEventListener('click', closeOfflineModal); elements.offlineCancel.addEventListener('click', closeOfflineModal);
elements.offlineModal.addEventListener('click', (event) => { if (event.target === elements.offlineModal) closeOfflineModal(); });
if (offlineEnabled()) markOfflineAIEnabled();
setOnlineStatus();
