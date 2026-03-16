(function () {
  if (window.__projectsPanelBound) return;
  window.__projectsPanelBound = true;

  // ТОЧНО как в policy-panels.js — общий кеш выбора
  window.__tableSel = window.__tableSel || {};
  window.__tableSelLast = window.__tableSelLast || null;

  function pane() { return document.getElementById('projects-pane'); }
  const qa = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  const csrftoken = getCookie('csrftoken');

  function getMasterForPanel(panel) {
    const id = panel?.id;
    if (!id) return null;
    return pane()?.querySelector(`input.form-check-input[data-actions-id="${CSS.escape(id)}"]`) || null;
  }
  function getNameForPanel(panel) {
    const master = getMasterForPanel(panel);
    return master?.dataset?.targetName || null;
  }
  function getRowChecksByName(name) {
    const root = pane();
    return qa(`tbody input.form-check-input[name="${CSS.escape(name)}"]`, root);
  }
  function getCheckedByName(name) {
    return getRowChecksByName(name).filter(b => b.checked);
  }
  function updateRowHighlightFor(name) {
    getRowChecksByName(name).forEach(b => {
      const tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updateMasterStateFor(name) {
    const boxes = getRowChecksByName(name);
    const root = pane();
    const master = root?.querySelector(`input.form-check-input[data-target-name="${CSS.escape(name)}"]`);
    if (!master) return;
    const checkedCount = boxes.filter(b => b.checked).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }

  function findActionsByName(name) {
    const root = pane();
    if (!root) return null;
    const master = root.querySelector(`input.form-check-input[data-target-name="${CSS.escape(name)}"]`);
    if (!master) return null;
    const actionsId = master.getAttribute('data-actions-id') || '';
    if (!actionsId) return null;
    return root.querySelector('#' + actionsId);
  }
  function ensureActionsVisibility(name) {
    const panel = findActionsByName(name);
    if (!panel) return;
    const anyChecked = getRowChecksByName(name).some(b => b.checked);
    panel.classList.toggle('d-none', !anyChecked);
    panel.classList.toggle('d-flex', anyChecked);
  }

  function getDeleteConfirmationMessage(name, count) {
    if (name === 'work-select') {
      return `Удалить ${count} строк(у/и) из "Объем услуг"? Будут также удалены связанные строки в "Юридические лица" и "Исполнители".`;
    }
    return `Удалить ${count} строк(у/и)?`;
  }

  function updateRegWorkspaceBtn() {
    const root = pane();
    if (!root) return;
    const btn = root.querySelector('#reg-create-workspace-btn');
    const checkedCount = getCheckedByName('registration-select').length;
    if (btn) btn.disabled = checkedCount !== 1;
  }

  // Кнопка «Редактировать» для таблицы «Условия контракта»
  function updateContractEditBtn() {
    const root = pane();
    if (!root) return;
    const btn = root.querySelector('#contract-edit-btn');
    if (!btn) return;
    const anyChecked = getRowChecksByName('contract-select').some(b => b.checked);
    btn.disabled = !anyChecked;
  }

  document.addEventListener('click', async (e) => {
    const root = pane();
    if (!root) return;
    const editBtn = e.target.closest('#contract-edit-btn');
    if (editBtn && root.contains(editBtn)) {
      const checked = getCheckedByName('contract-select');
      if (!checked.length) return;
      const first = checked[0];
      const tr = first.closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;

      window.__tableSel['contract-select'] = checked.map(ch => String(ch.value));
      window.__tableSelLast = 'contract-select';

      await htmx.ajax('GET', url, { target: '#projects-modal .modal-content', swap: 'innerHTML' });
      updateContractEditBtn();
      return;
    }
  });

  // Делегирование: клики по кнопкам панели РЕГИСТРАЦИИ (строго как в products)
  document.addEventListener('click', async (e) => {
    const root = pane();
    if (!root) return;
    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;

    // Панель теперь общая для трёх таблиц
    const panel = btn.closest('#registrations-actions, #work-actions, #legal-entities-actions');
    if (!panel) return;

    const action = btn.dataset.panelAction; // "up" | "down" | "edit" | "delete"
    const name = getNameForPanel(panel);    // ожидаем "registration-select"
    if (!name) return;

    const checked = getCheckedByName(name);
    if (!checked.length) return;

    // как в policy: запомним выбор именно этой таблицы
    window.__tableSel[name] = checked.map(ch => String(ch.value));
    window.__tableSelLast = name;

    if (action === 'edit') {
      const first = checked[0];
      const tr = first.closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;

      // грузим форму в модалку ПРОЕКТОВ — как в Продуктах
      await htmx.ajax('GET', url, { target: '#projects-modal .modal-content', swap: 'innerHTML' });
      ensureActionsVisibility(name);
      return;
    }

    if (action === 'delete') {
      if (!confirm(getDeleteConfirmationMessage(name, checked.length))) return;
      const urls = checked.map(ch => ch.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#projects-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      return;
    }

    if (action === 'up' || action === 'down') {
      let urls = checked
        .map(ch => ch.closest('tr')?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'])
        .filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#projects-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      ensureActionsVisibility(name);
      return;
    }
  });

  // Мастер-чекбокс (один-в-один)
  document.addEventListener('change', (e) => {
    const root = pane();
    if (!root) return;
    const master = e.target.closest('input.form-check-input[data-actions-id][data-target-name]');
    if (!master || !root.contains(master)) return;
    const name = master.dataset.targetName;
    const boxes = getRowChecksByName(name);
    boxes.forEach(b => { b.checked = master.checked; });
    master.indeterminate = false;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
    if (name === 'contract-select') updateContractEditBtn();
    if (name === 'registration-select') updateRegWorkspaceBtn();
  });

  // Чекбоксы строк (один-в-один)
  document.addEventListener('change', (e) => {
    const root = pane();
    if (!root) return;
    const rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (!rowCb || !root.contains(rowCb)) return;
    const name = rowCb.name;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
    if (name === 'contract-select') updateContractEditBtn();
    if (name === 'registration-select') updateRegWorkspaceBtn();
  });

  // Восстановление выбора после перерисовки HTMX (один-в-один)
  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (!(e.target && e.target.id === 'projects-pane')) return;
    const last = window.__tableSelLast;
    if (!last) return;
    const ids = (window.__tableSel && window.__tableSel[last]) || [];
    const set = new Set(ids || []);
    getRowChecksByName(last).forEach(b => { b.checked = set.has(String(b.value)); });
    updateMasterStateFor(last);
    updateRowHighlightFor(last);
    ensureActionsVisibility(last);
    if (last === 'contract-select') updateContractEditBtn();
    if (last === 'registration-select') updateRegWorkspaceBtn();
    try { delete window.__tableSel[last]; } catch(e) { window.__tableSel[last] = []; }
    window.__tableSelLast = null;
  });

  // «Создать» в модальном окне рабочего пространства регистрации
  document.addEventListener('click', async (e) => {
    const root = pane();
    if (!root) return;
    const wsConfirmBtn = e.target.closest('#reg-create-workspace-confirm-btn');
    if (!wsConfirmBtn || !root.contains(wsConfirmBtn)) return;

    const checked = getCheckedByName('registration-select');
    if (checked.length !== 1) {
      alert('Выберите ровно один проект.');
      return;
    }
    const tr = checked[0].closest('tr');
    const projectId = tr?.dataset?.projectId;
    if (!projectId) return;

    const actionsRow = root.querySelector('[data-create-workspace-url]');
    const wsUrl = actionsRow?.dataset?.createWorkspaceUrl;
    if (!wsUrl) return;

    const statusEl = root.querySelector('#reg-create-workspace-status');
    const progressEl = root.querySelector('#reg-ws-progress');
    const fillEl = progressEl?.querySelector('.ws-progress-fill');
    wsConfirmBtn.disabled = true;
    if (statusEl) statusEl.textContent = '';
    if (fillEl) fillEl.style.width = '0%';
    if (progressEl) progressEl.classList.remove('d-none');

    try {
      const formData = new FormData();
      formData.append('project_id', projectId);

      const response = await fetch(wsUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData,
      });

      if (!response.ok && !response.body) {
        throw new Error('Не удалось создать рабочее пространство.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let lastResult = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          const msg = JSON.parse(line);
          if (msg.current !== undefined && msg.total) {
            const pct = Math.round((msg.current / msg.total) * 100);
            if (fillEl) fillEl.style.width = pct + '%';
          }
          if (msg.ok !== undefined) lastResult = msg;
        }
      }
      if (buffer.trim()) {
        const msg = JSON.parse(buffer);
        if (msg.ok !== undefined) lastResult = msg;
      }

      if (!lastResult || !lastResult.ok) {
        throw new Error(lastResult?.error || 'Не удалось создать рабочее пространство.');
      }

      if (fillEl) fillEl.style.width = '100%';
      if (statusEl) statusEl.innerHTML = '<span class="text-success">' + (lastResult.message || 'Готово!') + '</span>';
    } catch (err) {
      if (progressEl) progressEl.classList.add('d-none');
      if (statusEl) statusEl.innerHTML = '<span class="text-danger">' + (err.message || 'Ошибка') + '</span>';
      else alert(err.message || 'Не удалось создать рабочее пространство.');
    } finally {
      wsConfirmBtn.disabled = false;
    }
  });

  // ── Настройки рабочего пространства (модалка с таблицей папок) ──

  let wsFolders = [];

  function getSettingsModal() { return document.getElementById('reg-workspace-settings-modal'); }
  function getTbody() { return document.getElementById('ws-folders-tbody'); }

  function renderFolderRows() {
    const tbody = getTbody();
    if (!tbody) return;
    tbody.innerHTML = '';
    wsFolders.forEach((f, idx) => {
      const tr = document.createElement('tr');
      tr.dataset.idx = idx;
      tr.innerHTML =
        '<td class="text-nowrap">' +
          '<div class="form-check">' +
            '<input class="form-check-input ws-folder-check" type="checkbox" data-idx="' + idx + '">' +
          '</div>' +
        '</td>' +
        '<td>' +
          '<select class="form-select form-select-sm ws-folder-level" data-idx="' + idx + '">' +
            '<option value="1"' + (f.level === 1 ? ' selected' : '') + '>1</option>' +
            '<option value="2"' + (f.level === 2 ? ' selected' : '') + '>2</option>' +
            '<option value="3"' + (f.level === 3 ? ' selected' : '') + '>3</option>' +
          '</select>' +
        '</td>' +
        '<td>' +
          '<input type="text" class="form-control form-control-sm ws-folder-name" data-idx="' + idx + '" value="' + escHtml(f.name) + '">' +
        '</td>';
      tbody.appendChild(tr);
    });
    updateFolderRowActions();
  }

  function escHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function getCheckedFolderIdxs() {
    const checks = getTbody()?.querySelectorAll('.ws-folder-check:checked') || [];
    return Array.from(checks).map(c => parseInt(c.dataset.idx, 10));
  }

  function updateFolderRowActions() {
    const panel = document.getElementById('ws-folders-row-actions');
    if (!panel) return;
    const anyChecked = getCheckedFolderIdxs().length > 0;
    panel.classList.toggle('d-none', !anyChecked);
    panel.classList.toggle('d-flex', anyChecked);
  }

  function syncFromInputs() {
    const tbody = getTbody();
    if (!tbody) return;
    tbody.querySelectorAll('.ws-folder-level').forEach(sel => {
      const idx = parseInt(sel.dataset.idx, 10);
      if (wsFolders[idx]) wsFolders[idx].level = parseInt(sel.value, 10);
    });
    tbody.querySelectorAll('.ws-folder-name').forEach(inp => {
      const idx = parseInt(inp.dataset.idx, 10);
      if (wsFolders[idx]) wsFolders[idx].name = inp.value;
    });
  }

  async function loadFolders() {
    const root = pane();
    const url = root?.querySelector('[data-workspace-folders-url]')?.dataset?.workspaceFoldersUrl;
    if (!url) return;
    try {
      const resp = await fetch(url);
      const data = await resp.json();
      wsFolders = (data.folders || []).map(f => ({ level: f.level, name: f.name }));
    } catch { wsFolders = []; }
    renderFolderRows();
  }

  const settingsModal = getSettingsModal();
  if (settingsModal) {
    settingsModal.addEventListener('show.bs.modal', () => { loadFolders(); });
  }

  // Populate folder-level counts when create-workspace modal opens (delegated — partial loaded via HTMX)
  document.addEventListener('show.bs.modal', async (e) => {
    if (!e.target.matches('#reg-create-workspace-modal')) return;
    const root = pane();
    const url = root?.querySelector('[data-workspace-folders-url]')?.dataset?.workspaceFoldersUrl;
    const listEl = document.getElementById('reg-ws-folder-counts');
    if (!listEl) return;
    listEl.innerHTML = '<li class="text-muted">Загрузка…</li>';

    let folders = [];
    if (url) {
      try {
        const resp = await fetch(url);
        const data = await resp.json();
        folders = data.folders || [];
      } catch { /* ignore */ }
    }

    const counts = {};
    folders.forEach(f => { counts[f.level] = (counts[f.level] || 0) + 1; });
    listEl.innerHTML = '';
    [1, 2, 3].forEach(lvl => {
      const li = document.createElement('li');
      li.textContent = 'директории уровня ' + lvl + ': ' + (counts[lvl] || 0);
      listEl.appendChild(li);
    });

    const progressEl = document.getElementById('reg-ws-progress');
    if (progressEl) progressEl.classList.add('d-none');
    const statusEl = document.getElementById('reg-create-workspace-status');
    if (statusEl) statusEl.textContent = '';
  });

  document.addEventListener('change', (e) => {
    if (e.target.closest('.ws-folder-check')) updateFolderRowActions();
  });

  document.addEventListener('click', (e) => {
    if (e.target.closest('#ws-folder-add-btn')) {
      syncFromInputs();
      wsFolders.push({ level: 1, name: '' });
      renderFolderRows();
      const tbody = getTbody();
      const lastInput = tbody?.querySelector('tr:last-child .ws-folder-name');
      if (lastInput) lastInput.focus();
      return;
    }

    if (e.target.closest('#ws-folder-delete-btn')) {
      syncFromInputs();
      const idxs = new Set(getCheckedFolderIdxs());
      wsFolders = wsFolders.filter((_, i) => !idxs.has(i));
      renderFolderRows();
      return;
    }

    if (e.target.closest('#ws-folder-up-btn')) {
      syncFromInputs();
      const idxs = getCheckedFolderIdxs().sort((a, b) => a - b);
      for (const idx of idxs) {
        if (idx > 0 && !idxs.includes(idx - 1)) {
          [wsFolders[idx - 1], wsFolders[idx]] = [wsFolders[idx], wsFolders[idx - 1]];
        }
      }
      renderFolderRows();
      const newIdxs = idxs.map(i => (i > 0 && !idxs.includes(i - 1)) ? i - 1 : i);
      newIdxs.forEach(i => {
        const cb = getTbody()?.querySelector('.ws-folder-check[data-idx="' + i + '"]');
        if (cb) cb.checked = true;
      });
      updateFolderRowActions();
      return;
    }

    if (e.target.closest('#ws-folder-down-btn')) {
      syncFromInputs();
      const idxs = getCheckedFolderIdxs().sort((a, b) => b - a);
      for (const idx of idxs) {
        if (idx < wsFolders.length - 1 && !idxs.includes(idx + 1)) {
          [wsFolders[idx], wsFolders[idx + 1]] = [wsFolders[idx + 1], wsFolders[idx]];
        }
      }
      renderFolderRows();
      const newIdxs = idxs.map(i => (i < wsFolders.length - 1 && !idxs.includes(i + 1)) ? i + 1 : i);
      newIdxs.forEach(i => {
        const cb = getTbody()?.querySelector('.ws-folder-check[data-idx="' + i + '"]');
        if (cb) cb.checked = true;
      });
      updateFolderRowActions();
      return;
    }
  });

  document.addEventListener('click', async (e) => {
    if (!e.target.closest('#ws-folders-save-btn')) return;
    syncFromInputs();

    const root = pane();
    const saveUrl = root?.querySelector('[data-workspace-folders-save-url]')?.dataset?.workspaceFoldersSaveUrl;
    if (!saveUrl) return;

    const btn = e.target.closest('#ws-folders-save-btn');
    btn.disabled = true;

    try {
      const resp = await fetch(saveUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' },
        body: JSON.stringify({ folders: wsFolders }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error(data?.error || 'Ошибка сохранения.');

      const modal = window.bootstrap?.Modal.getInstance(getSettingsModal());
      modal?.hide();
    } catch (err) {
      alert(err.message || 'Не удалось сохранить.');
    } finally {
      btn.disabled = false;
    }
  });
})();