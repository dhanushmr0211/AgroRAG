// Configure with window.FARMER_API_URL before app.js, or use the local API default.
const API_URL = window.FARMER_API_URL || 'http://localhost:8000/ask';

const elements = {
  form: document.querySelector('#chatForm'),
  input: document.querySelector('#questionInput'),
  messages: document.querySelector('#messages'),
  typing: document.querySelector('#typingIndicator'),
  send: document.querySelector('.send-button'),
  status: document.querySelector('#onlineStatus'),
  statusLabel: document.querySelector('.status-label'),
  offlineAI: document.querySelector('#offlineAI'),
  offlineModal: document.querySelector('#offlineModal'),
  offlineConfirm: document.querySelector('#offlineConfirm'),
  offlineDismiss: document.querySelector('#offlineDismiss'),
  offlineCancel: document.querySelector('#offlineCancel'),
  offlineMessage: document.querySelector('#offlineMessage')
};

const localAnswers = {
  disease: 'I cannot reach the farm knowledge service right now. Check the affected leaves, isolate badly affected plants, and consult a local agriculture officer for a confirmed diagnosis.',
  fertilizer: 'I cannot reach the farm knowledge service right now. Avoid applying fertilizer without a soil test. Use the crop and soil details when the connection returns for a more specific recommendation.',
  default: 'I cannot reach the farm knowledge service right now. Please check your connection and try again. I can help with crops, diseases, soil, weather, and fertilizers.'
};

function setOnlineStatus() {
  const online = navigator.onLine;
  elements.status.classList.toggle('is-offline', !online);
  elements.statusLabel.textContent = online ? 'Online' : 'Offline';
  elements.status.setAttribute('aria-label', online ? 'Online' : 'Offline');
}

function scrollToLatest() {
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function addMessage(text, role, isFallback = false, label = 'Now') {
  const article = document.createElement('article');
  article.className = `message message--${role}`;
  const avatar = role === 'assistant' ? '🌱' : '👨‍🌾';
  article.innerHTML = `<div class="avatar" aria-hidden="true">${avatar}</div><div class="bubble"><p></p><time>${isFallback ? 'Local guidance' : label}</time></div>`;
  article.querySelector('p').textContent = text;
  elements.messages.append(article);
  scrollToLatest();
}

function fallbackFor(question) {
  const lowerQuestion = question.toLowerCase();
  if (lowerQuestion.includes('disease') || lowerQuestion.includes('yellow') || lowerQuestion.includes('spot')) return localAnswers.disease;
  if (lowerQuestion.includes('fertilizer') || lowerQuestion.includes('fertiliser')) return localAnswers.fertilizer;
  return localAnswers.default;
}

function setLoading(isLoading) {
  elements.typing.hidden = !isLoading;
  elements.input.disabled = isLoading;
  elements.send.disabled = isLoading;
  if (isLoading) scrollToLatest();
}

async function askAssistant(question) {
  if (!navigator.onLine) throw new Error('offline');
  const response = await fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ query: question })
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`Request failed with status ${response.status}`);
  }
  if (!response.ok || data.success === false) throw new Error(data.error || `Request failed with status ${response.status}`);
  const answer = data.answer;
  if (typeof answer !== 'string' || !answer.trim()) throw new Error('Empty response');
  return { answer: answer.trim(), mode: data.mode === 'rag+llm' ? 'AI answer' : 'RAG answer' };
}

function closeOfflineModal() {
  elements.offlineModal.hidden = true;
}

function markOfflineAIEnabled() {
  localStorage.setItem('offline_ai_enabled', 'true');
  elements.offlineAI.classList.add('is-enabled');
  elements.offlineAI.textContent = 'Offline AI ready';
}

function openOfflineModal() {
  if (localStorage.getItem('offline_ai_enabled') === 'true') {
    addMessage('Offline AI is enabled. A full local model download will be connected here in a future release.', 'assistant', true);
    return;
  }
  elements.offlineMessage.textContent = 'Download AI model (~500MB)?';
  elements.offlineConfirm.disabled = false;
  elements.offlineConfirm.textContent = 'Download model';
  elements.offlineModal.hidden = false;
  elements.offlineConfirm.focus();
}

function simulateOfflineDownload() {
  elements.offlineConfirm.disabled = true;
  elements.offlineConfirm.textContent = 'Downloading...';
  elements.offlineMessage.textContent = 'Preparing offline AI (simulation)...';
  setTimeout(() => {
    markOfflineAIEnabled();
    closeOfflineModal();
    addMessage('Offline AI is ready. Local answers will remain available when the connection is unavailable.', 'assistant', true);
  }, 1200);
}

elements.form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = elements.input.value.trim();
  if (!question) return;

  addMessage(question, 'user');
  elements.input.value = '';
  setLoading(true);
  try {
    const result = await askAssistant(question);
    console.info('Assistant response', { mode: result.mode, queryLength: question.length });
    addMessage(result.answer, 'assistant', false, result.mode);
  } catch (error) {
    console.warn('Assistant request unavailable:', error);
    const reason = error.message === 'offline' ? 'You are offline' : 'Server busy';
    addMessage(`⚠️ ${reason}. Showing local results.\n\n${fallbackFor(question)}`, 'assistant', true);
  } finally {
    setLoading(false);
    elements.input.focus();
  }
});

window.addEventListener('online', setOnlineStatus);
window.addEventListener('offline', setOnlineStatus);
elements.offlineAI.addEventListener('click', openOfflineModal);
elements.offlineConfirm.addEventListener('click', simulateOfflineDownload);
elements.offlineDismiss.addEventListener('click', closeOfflineModal);
elements.offlineCancel.addEventListener('click', closeOfflineModal);
elements.offlineModal.addEventListener('click', (event) => {
  if (event.target === elements.offlineModal) closeOfflineModal();
});
if (localStorage.getItem('offline_ai_enabled') === 'true') markOfflineAIEnabled();
setOnlineStatus();