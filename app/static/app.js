// Tabs
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'fortschritt') loadProgress();
  });
});

// ==================== Fragen üben ====================
let currentQuestion = null;

async function loadNextQuestion() {
  const meta = document.getElementById('q-meta');
  const btn = document.getElementById('q-next');
  btn.disabled = true;
  meta.textContent = 'Wähle nächste Frage…';
  try {
    const r = await fetch('/api/questions/next');
    if (!r.ok) {
      const t = await r.text();
      document.getElementById('q-kontext').textContent = 'Keine Fragen verfügbar — erst preprocess.py laufen lassen oder Fragen generieren.';
      document.getElementById('q-teilfragen').innerHTML = '';
      meta.textContent = '';
      return;
    }
    const data = await r.json();
    currentQuestion = data.question;
    meta.textContent = `Pool: ${data.pool_size} Fragen · ${data.unanswered_count} unbeantwortet`;
    renderCurrent();
  } catch (e) {
    meta.textContent = 'Fehler: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

function renderCurrent() {
  const q = currentQuestion;
  if (!q) return;
  const quelle = q.quelle ? `<div class="quelle-tag">${escapeHtml(q.quelle)}</div>` : '';
  document.getElementById('q-kontext').innerHTML = quelle + escapeHtml(q.kontext || '');
  const tf = document.getElementById('q-teilfragen');
  tf.innerHTML = '<b>Teilfragen:</b><ul>' +
    (q.teilfragen || []).map(t => `<li>${escapeHtml(t)}</li>`).join('') + '</ul>';
  document.getElementById('q-answer').value = '';
  document.getElementById('q-result').innerHTML = '';
}

document.getElementById('q-next').addEventListener('click', loadNextQuestion);

document.getElementById('q-generate').addEventListener('click', async () => {
  const btn = document.getElementById('q-generate');
  const meta = document.getElementById('q-meta');
  btn.disabled = true;
  const prev = btn.textContent;
  btn.textContent = 'Generiere…';
  try {
    const r = await fetch('/api/questions/generate', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ n: 5 })
    });
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    meta.textContent = `+${d.added} neue Fragen · Pool insgesamt: ${d.total}`;
  } catch (e) {
    meta.textContent = 'Fehler: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = prev;
  }
});

document.getElementById('q-submit').addEventListener('click', async () => {
  const q = currentQuestion;
  if (!q) { alert('Erst Frage laden'); return; }
  const answer = document.getElementById('q-answer').value.trim();
  if (!answer) { alert('Bitte Antwort eingeben'); return; }
  const fullQ = (q.kontext || '') + '\n\n' + (q.teilfragen || []).join('\n');
  const btn = document.getElementById('q-submit');
  btn.disabled = true; btn.textContent = 'Bewerte…';
  const resultBox = document.getElementById('q-result');
  const stopLoader = startLoader(resultBox, [
    'Antwort wird gelesen…',
    'Abgleich mit Lehrmaterial…',
    'Stärken und Schwächen identifizieren…',
    'Musterantwort formulieren…',
    'Schwachstellen ableiten…',
    'Fast fertig…',
  ]);
  try {
    const r = await fetch('/api/grade', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ question_id: q.id || null, question_text: fullQ, user_answer: answer })
    });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    resultBox.innerHTML = renderGrade(data);
  } catch (e) {
    resultBox.innerHTML = `<p style="color:red">Fehler: ${escapeHtml(e.message)}</p>`;
  } finally {
    stopLoader();
    btn.disabled = false; btn.textContent = 'Antwort bewerten';
  }
});

function startLoader(el, steps) {
  el.innerHTML = `
    <div class="grade-loader">
      <div class="row1">
        <div class="spinner"></div>
        <div class="status">${escapeHtml(steps[0])}</div>
        <div class="elapsed">0.0 s</div>
      </div>
      <div class="progress-track"></div>
    </div>`;
  const statusEl = el.querySelector('.status');
  const elapsedEl = el.querySelector('.elapsed');
  const t0 = performance.now();
  let idx = 0;
  const stepTimer = setInterval(() => {
    idx = Math.min(idx + 1, steps.length - 1);
    statusEl.textContent = steps[idx];
  }, 2500);
  const tickTimer = setInterval(() => {
    const s = (performance.now() - t0) / 1000;
    elapsedEl.textContent = s.toFixed(1) + ' s';
  }, 100);
  return () => { clearInterval(stepTimer); clearInterval(tickTimer); };
}

function mdBlock(text) {
  if (!text) return '';
  try { return marked.parse(String(text)); } catch { return escapeHtml(text); }
}
function mdInline(text) {
  if (!text) return '';
  try { return marked.parseInline(String(text)); } catch { return escapeHtml(text); }
}

function renderGrade(d) {
  const s = d.score ?? 0;
  const cls = s >= 75 ? 'good' : s >= 50 ? 'mid' : 'bad';
  return `
    <div class="score ${cls}">Score: ${s}/100</div>
    ${list('Stärken', d.staerken)}
    ${list('Schwächen', d.schwaechen)}
    ${list('Fehlende Aspekte', d.fehlende_aspekte)}
    <h4>Musterantwort</h4>
    <div class="muster markdown">${mdBlock(d.musterantwort || '')}</div>
  `;
}
function list(title, items) {
  if (!items || !items.length) return '';
  return `<h4>${title}</h4><ul class="markdown">${items.map(i => `<li>${mdInline(i)}</li>`).join('')}</ul>`;
}

// ==================== Quiz ====================
async function runQuiz(url, body, btn, labelDone) {
  const box = document.getElementById('quiz-box');
  const prev = btn.textContent;
  btn.disabled = true; btn.textContent = 'Generiere…';
  const stopLoader = startLoader(box, [
    'Themen wählen…',
    'Fragen formulieren…',
    'Antwortoptionen bauen…',
    'Erklärungen ergänzen…',
    'Fast fertig…',
  ]);
  try {
    const r = await fetch(url, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    const qs = Array.isArray(data) ? data : (data.questions || []);
    box.innerHTML = '';
    if (data.message) {
      box.innerHTML = `<p class="loading">${escapeHtml(data.message)}</p>`;
    }
    qs.forEach((q, i) => box.appendChild(renderQuizItem(q, i)));
  } catch (e) {
    box.innerHTML = `<p style="color:red">Fehler: ${escapeHtml(e.message)}</p>`;
  } finally {
    stopLoader();
    btn.disabled = false; btn.textContent = labelDone || prev;
  }
}

document.getElementById('quiz-start').addEventListener('click', () => {
  const topic = document.getElementById('quiz-topic').value;
  const n = +document.getElementById('quiz-n').value || 5;
  runQuiz('/api/quiz/generate', { topic, n }, document.getElementById('quiz-start'), 'Quiz zum Thema');
});

document.getElementById('quiz-weak').addEventListener('click', () => {
  const n = +document.getElementById('quiz-n').value || 5;
  runQuiz('/api/quiz/from_weak', { n }, document.getElementById('quiz-weak'), 'Aus meinen Schwachstellen üben');
});

function renderQuizItem(q, i) {
  const el = document.createElement('div');
  el.className = 'quiz-q';
  const topicBadge = q.topic ? `<div class="topic-pill">Schwachstelle: ${escapeHtml(q.topic)}</div>` : '';
  el.innerHTML = `${topicBadge}<div class="frage"><b>Frage ${i + 1}:</b> ${escapeHtml(q.frage)}</div><div class="options"></div>`;
  const opts = el.querySelector('.options');
  (q.optionen || []).forEach((opt, idx) => {
    const o = document.createElement('label');
    o.className = 'option';
    o.innerHTML = `<input type="radio" name="q${i}" value="${idx}" /><span>${escapeHtml(opt)}</span>`;
    o.querySelector('input').addEventListener('change', async () => {
      const gewaehlt = idx;
      opts.querySelectorAll('.option').forEach((node, j) => {
        node.style.pointerEvents = 'none';
        if (j === q.korrekt) node.classList.add('correct');
        if (j === gewaehlt && j !== q.korrekt) node.classList.add('wrong');
      });
      const expl = document.createElement('div');
      expl.className = 'erklaerung';
      expl.textContent = (gewaehlt === q.korrekt ? '✓ Richtig. ' : '✗ Falsch. ') + (q.erklaerung || '');
      el.appendChild(expl);
      const r = await fetch('/api/quiz/answer', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ frage: q.frage, optionen: q.optionen,
          korrekt: q.korrekt, gewaehlt, erklaerung: q.erklaerung || '',
          topic_id: q.topic_id || null })
      });
      const data = await r.json().catch(() => ({}));
      if (data.topic) {
        const info = document.createElement('div');
        info.className = 'erklaerung';
        const m = data.topic.mastery;
        if (data.topic.archived_at) {
          info.textContent = `🎉 Thema „${data.topic.topic}" gemeistert — verschwindet aus dem Quiz-Pool.`;
        } else {
          info.textContent = `Mastery „${data.topic.topic}": ${'●'.repeat(m)}${'○'.repeat(3 - m)} (${m}/3)`;
        }
        el.appendChild(info);
      }
    });
    opts.appendChild(o);
  });
  return el;
}

// ==================== Chat ====================
const chatHistory = [];
document.getElementById('chat-form').addEventListener('submit', async e => {
  e.preventDefault();
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  appendMsg('user', text);
  chatHistory.push({ role: 'user', content: text });
  const assistantEl = appendMsg('assistant', '');
  try {
    const r = await fetch('/api/chat', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ messages: chatHistory })
    });
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let full = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = dec.decode(value, { stream: true });
      full += chunk;
      assistantEl.innerHTML = mdBlock(full);
      document.getElementById('chat-log').scrollTop = 1e9;
    }
    chatHistory.push({ role: 'assistant', content: full });
  } catch (e) {
    assistantEl.textContent = 'Fehler: ' + e.message;
  }
});

function appendMsg(role, text) {
  const log = document.getElementById('chat-log');
  const el = document.createElement('div');
  el.className = 'msg ' + role + (role === 'assistant' ? ' markdown' : '');
  if (role === 'assistant' && text) el.innerHTML = mdBlock(text);
  else el.textContent = text;
  log.appendChild(el);
  log.scrollTop = 1e9;
  return el;
}

// ==================== Fortschritt ====================
document.getElementById('progress-reload').addEventListener('click', loadProgress);

async function loadProgress() {
  try {
    const r = await fetch('/api/progress');
    const d = await r.json();
    const s = d.stats;
    document.getElementById('progress-stats').innerHTML = `
      <div class="stat"><div class="num">${s.answers_count}</div><div class="lbl">Beantwortete Fragen</div></div>
      <div class="stat"><div class="num">${s.answers_avg_score ?? '–'}</div><div class="lbl">Ø Score</div></div>
      <div class="stat"><div class="num">${s.quiz_correct}/${s.quiz_count}</div><div class="lbl">Quiz korrekt</div></div>
      <div class="stat"><div class="num">${s.topics_active}</div><div class="lbl">Offene Schwachstellen</div></div>
      <div class="stat"><div class="num">${s.topics_mastered}</div><div class="lbl">Gemeisterte Themen</div></div>
    `;
    const topicsEl = document.getElementById('progress-topics');
    if (!d.topics.length) {
      topicsEl.innerHTML = '<p class="loading">Noch keine Schwachstellen — beantworte Fragen im Tab „Fragen üben", dann landen fehlende Themen hier.</p>';
    } else {
      topicsEl.innerHTML = d.topics.map(t => {
        const pct = Math.round((t.mastery / 3) * 100);
        const archived = t.archived_at ? ' archived' : '';
        const badge = t.archived_at ? '✓ gemeistert' : `${t.mastery}/3`;
        return `<div class="topic${archived}">
          <span class="label">${escapeHtml(t.topic)}</span>
          <span class="bar"><span style="width:${pct}%"></span></span>
          <span class="counts">${badge} · ✓${t.right_count} ✗${t.wrong_count}</span>
        </div>`;
      }).join('');
    }
    document.getElementById('progress-answers').innerHTML = d.answers.map(a => `
      <div class="row">
        <span>${escapeHtml((a.question_text || '').slice(0, 80))}…</span>
        <span>${a.score ?? '–'}/100 <span class="date">${a.created_at}</span></span>
      </div>`).join('') || '<p class="loading">Keine Einträge</p>';
    document.getElementById('progress-quiz').innerHTML = d.quiz.map(q => `
      <div class="row">
        <span>${escapeHtml((q.frage || '').slice(0, 80))}…</span>
        <span>${q.korrekt === q.gewaehlt ? '✓' : '✗'} <span class="date">${q.created_at}</span></span>
      </div>`).join('') || '<p class="loading">Keine Einträge</p>';
  } catch (e) {
    document.getElementById('progress-stats').innerHTML = `<p style="color:red">Fehler: ${escapeHtml(e.message)}</p>`;
  }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}

// ==================== Auth ====================
async function checkAuth() {
  try {
    const r = await fetch('/api/auth/me');
    if (!r.ok) return null;
    const d = await r.json();
    return d.user;
  } catch { return null; }
}

function showLogin() {
  document.getElementById('login-overlay').hidden = false;
  document.getElementById('user-box').hidden = true;
  document.getElementById('login-username').focus();
}

function hideLogin(user) {
  document.getElementById('login-overlay').hidden = true;
  document.getElementById('user-box').hidden = false;
  document.getElementById('user-name').textContent = user.username;
}

document.getElementById('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  const err = document.getElementById('login-error');
  err.textContent = '';
  const username = document.getElementById('login-username').value.trim();
  const pin = document.getElementById('login-pin').value.trim();
  try {
    const r = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, pin }),
    });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      err.textContent = d.detail || 'Login fehlgeschlagen';
      return;
    }
    const d = await r.json();
    hideLogin(d.user);
    document.getElementById('login-pin').value = '';
    loadNextQuestion();
  } catch (e) {
    err.textContent = 'Netzwerkfehler';
  }
});

document.getElementById('logout-btn').addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST' });
  showLogin();
});

// Init
(async () => {
  const user = await checkAuth();
  if (user) {
    hideLogin(user);
    loadNextQuestion();
  } else {
    showLogin();
  }
})();
