(() => {
  const $ = (s) => document.querySelector(s);
  const agentColor = {
    DIRECTOR: '#fbbf24', SALES: '#ff4d6d', PLANNER: '#2dd4bf',
    QA: '#60a5fa', DOC: '#a78bfa', VERIFIER: '#34d399'
  };
  const state = { data: null, config: null, busy: false, lastReportKey: '' };

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...opts,
    });
    const text = await res.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch { body = text; }
    if (!res.ok) {
      const msg = (body && body.error) ? body.error : `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return body;
  }

  function toast(msg, good = false) {
    const el = $('#toast');
    el.textContent = msg;
    el.classList.toggle('good', good);
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('show'), 4200);
  }

  function fmtTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return iso.slice(11, 19);
    return d.toLocaleTimeString('zh-TW', { hour12: false });
  }

  function renderStatus(d) {
    const s = d.status || 'idle';
    const pill = $('#statusPill');
    pill.textContent = s;
    pill.className = `pill ${s}`;
    $('#modePill').textContent = d.mode || 'mock';
    const real = state.config?.real;
    const dry = $('#dryPill');
    if (d.mode === 'real') {
      dry.style.display = '';
      dry.textContent = real?.dry_run ? 'dry run' : 'live';
      dry.className = 'pill ' + (real?.dry_run ? 'dry' : 'running');
    } else {
      dry.style.display = 'none';
    }

    const pause = $('#btnPause');
    if (s === 'running') { pause.textContent = 'Pause'; pause.disabled = false; }
    else if (s === 'paused') { pause.textContent = 'Resume'; pause.disabled = false; }
    else { pause.textContent = 'Pause'; pause.disabled = true; }

    $('#btnStart').disabled = s === 'running' || s === 'paused';
  }

  function renderScene(d) {
    const sc = d.scenario || {};
    const sel = $('#scenario');
    if (sel && sc.id && sel.value !== sc.id) sel.value = sc.id;
    $('#sceneName').textContent = sc.name || '—';
    $('#sceneDesc').textContent = sc.description || '';
    $('#pain').textContent = sc.pain || '—';
    $('#gain').textContent = sc.gain || '—';
    const total = d.total_steps || 1;
    const pct = Math.min(100, Math.round((d.step_index || 0) / total * 100));
    $('#progressBar').style.width = pct + '%';
  }

  function renderPersonas(d) {
    const wrap = $('#personaList');
    wrap.innerHTML = '';
    const list = d.personas || [];
    $('#personaCount').textContent = `${list.length} personas`;
    for (const p of list) {
      const row = document.createElement('div');
      row.className = `persona ${p.status || ''}`;
      row.style.setProperty('--c', p.color || agentColor[p.agent] || '#2dd4bf');
      row.title = p.description || '';
      const dot = document.createElement('span'); dot.className = 'dot';
      const mid = document.createElement('div');
      const name = document.createElement('div'); name.className = 'p-name'; name.textContent = p.name;
      const role = document.createElement('div'); role.className = 'p-role'; role.textContent = `${p.role} · ${p.email}`;
      mid.append(name, role);
      const ag = document.createElement('span'); ag.className = 'p-agent'; ag.textContent = p.agent;
      row.append(dot, mid, ag);
      wrap.appendChild(row);
    }
  }

  function renderFeed(d) {
    const feed = $('#feed');
    const actions = d.actions || [];
    $('#actionCount').textContent = `${actions.length} actions`;
    if (!actions.length) {
      feed.innerHTML = '<div class="empty">按「Start experiment」開始。<br>Mock 模式不需要任何 Google 憑證。</div>';
      return;
    }
    feed.innerHTML = '';
    const frag = document.createDocumentFragment();
    for (const a of actions.slice(-200)) {
      const el = document.createElement('div');
      el.className = `action ${a.status || ''}`;
      el.style.setProperty('--c', agentColor[a.agent] || '#2dd4bf');
      const time = document.createElement('div'); time.className = 'time'; time.textContent = fmtTime(a.created_at);
      const tool = document.createElement('div'); tool.className = 'tool'; tool.textContent = a.tool === 'Workspace' ? 'WS' : a.tool;
      const body = document.createElement('div'); body.className = 'body';
      const summary = document.createElement('div'); summary.className = 'summary'; summary.textContent = a.summary;
      const meta = document.createElement('div'); meta.className = 'meta';
      meta.textContent = `${a.actor} → ${a.target || '—'}${a.error ? ' · ' + a.error : ''}`;
      body.append(summary, meta);
      const st = document.createElement('div'); st.className = 'state'; st.textContent = a.status;
      el.append(time, tool, body, st);
      frag.appendChild(el);
    }
    feed.appendChild(frag);
    feed.scrollTop = feed.scrollHeight;
  }

  function renderKPI(d) {
    const m = {};
    (d.metrics || []).forEach(x => { m[x.key] = x; });
    const actions = (d.actions || []).length;
    const errors = (d.actions || []).filter(a => a.status === 'error').length;
    const dry = (d.actions || []).filter(a => a.status === 'dry_run').length;
    const dryVal = d.mode === 'real' ? dry : '—';
    const dur = m.duration_seconds ? `${m.duration_seconds.value}s` : '—';
    const progress = `${d.step_index || 0}/${d.total_steps || '—'}`;
    const cards = [
      ['ACTIONS', actions, '', ''],
      ['ERRORS', errors, '', errors ? 'bad' : 'hot'],
      ['DRY RUN', dryVal, '', dry ? 'hot' : ''],
      ['DURATION', dur, '', ''],
      ['PROGRESS', progress, '', ''],
      ['MODE', d.mode || 'mock', '', ''],
    ];
    const wrap = $('#kpi');
    wrap.innerHTML = '';
    for (const [k, v, u, cls] of cards) {
      const el = document.createElement('div');
      el.className = `kpi ${cls}`;
      el.innerHTML = `<div class="k">${k}</div><div class="v">${v}<span class="u">${u}</span></div>`;
      wrap.appendChild(el);
    }
  }

  function render(d) {
    renderStatus(d);
    renderScene(d);
    renderPersonas(d);
    renderFeed(d);
    renderKPI(d);
    const key = `${d.experiment?.id || 'none'}-${d.status}-${(d.actions || []).length}`;
    if (key !== state.lastReportKey) {
      state.lastReportKey = key;
      refreshReport();
    }
  }

  async function refreshReport() {
    try {
      const res = await fetch('/api/report');
      const text = await res.text();
      $('#report').textContent = text;
      $('#download').href = '/api/report?download=1';
    } catch (e) {
      $('#report').textContent = '報告載入失敗：' + e.message;
    }
  }

  async function refresh() {
    if (state.busy) return;
    try {
      const d = await api('/api/state');
      state.data = d;
      render(d);
    } catch (e) {
      toast('狀態載入失敗：' + e.message);
    }
  }

  async function loadConfig() {
    try {
      const c = await api('/api/config');
      state.config = c;
      const sel = $('#scenario');
      sel.innerHTML = '';
      for (const s of c.scenarios || []) {
        const o = document.createElement('option');
        o.value = s.id;
        o.textContent = `${s.name}（${s.steps} steps）`;
        sel.appendChild(o);
      }
      const realOpt = $('#mode option[value="real"]');
      const note = $('#configNote');
      if (c.real?.configured) {
        realOpt.disabled = false;
        note.textContent = `Real 已設定：${c.real.admin || ''}｜DRY_RUN=${c.real.dry_run ? '1' : '0'}｜allowlist: ${(c.real.allowlist || []).join(', ')}`;
        note.className = 'hint good';
      } else {
        realOpt.disabled = true;
        note.textContent = 'Demo 使用 Mock 模式；Real Workspace 需設定 service account。';
        note.className = 'hint';
      }
    } catch (e) {
      $('#configNote').textContent = '設定載入失敗：' + e.message;
      $('#configNote').className = 'hint bad';
    }
  }

  async function start() {
    const scenario = $('#scenario').value || 'quote';
    const mode = $('#mode').value || 'mock';
    const delay = Number($('#delay').value || 1.2);
    if (mode === 'real' && !confirm('Real 模式會呼叫真實 Google Workspace API（目前 DRY_RUN 視設定）。確定？')) return;
    $('#btnStart').disabled = true;
    try {
      await api('/api/start', {
        method: 'POST',
        body: JSON.stringify({ scenario, mode, delay }),
      });
      toast(`已啟動：${scenario} / ${mode}`, true);
      await refresh();
    } catch (e) {
      toast('啟動失敗：' + e.message);
      $('#configNote').textContent = '啟動失敗：' + e.message;
      $('#configNote').className = 'hint bad';
    } finally {
      $('#btnStart').disabled = false;
      renderStatus(state.data || {});
    }
  }

  async function pauseResume() {
    const s = state.data?.status;
    const path = s === 'paused' ? '/api/resume' : '/api/pause';
    try {
      await api(path, { method: 'POST', body: '{}' });
      await refresh();
    } catch (e) { toast('操作失敗：' + e.message); }
  }

  async function reset() {
    if (!confirm('清除本次實驗、timeline 與 metrics？（已下載的報告不會被刪）')) return;
    try {
      await api('/api/reset', { method: 'POST', body: '{}' });
      state.lastReportKey = '';
      toast('已重置', true);
      await refresh();
    } catch (e) { toast('重置失敗：' + e.message); }
  }

  async function kill() {
    if (!confirm('KILL：停止所有新動作？')) return;
    try {
      await api('/api/pause', { method: 'POST', body: '{}' });
      toast('KILL：已停止新動作');
      await refresh();
    } catch (e) { toast('KILL 失敗：' + e.message); }
  }

  async function inject(type, payload) {
    try {
      await api('/api/event', {
        method: 'POST',
        body: JSON.stringify({ type, payload }),
      });
      toast(`事件注入：${type}`, true);
      await refresh();
    } catch (e) { toast('事件注入失敗：' + e.message); }
  }

  $('#btnStart').addEventListener('click', start);
  $('#btnPause').addEventListener('click', pauseResume);
  $('#btnReset').addEventListener('click', reset);
  $('#btnKill').addEventListener('click', kill);
  document.querySelectorAll('.event').forEach(b => {
    b.addEventListener('click', () => inject(b.dataset.type, b.dataset.payload));
  });

  (async () => {
    await loadConfig();
    await refresh();
    setInterval(refresh, 1500);
  })();
})();
