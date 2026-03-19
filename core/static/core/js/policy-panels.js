(function () {
  if (window.__policyPanelBound) return;
  window.__policyPanelBound = true;

  window.__tableSel = window.__tableSel || {};
  window.__tableSelLast = window.__tableSelLast || null;

  function pane() {
    var all = document.querySelectorAll('#policy-pane');
    return all.length > 1 ? all[all.length - 1] : all[0] || null;
  }
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
  }

  // Делегирование: клики по кнопкам панелей
  document.addEventListener('click', async (e) => {
    const root = pane();
    if (!root) return;
    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;
    const panel = btn.closest('#products-actions, #expdir-actions, #sections-actions, #structures-actions, #grades-actions, #tariffs-actions');
    if (!panel) return;
    const action = btn.dataset.panelAction; // "up" | "down" | "edit" | "delete"
    const name = getNameForPanel(panel);
    if (!name) return;

    const checked = getCheckedByName(name);
    if (!checked.length) return;

    // сохраняем выбор ТОЛЬКО для текущей таблицы
    window.__tableSel[name] = checked.map(ch => String(ch.value));
    window.__tableSelLast = name;

    if (action === 'edit') {
      const first = checked[0];
      const tr = first.closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;
      await htmx.ajax('GET', url, { target: '#policy-modal .modal-content', swap: 'innerHTML' });
      // На случай если модалка не перерисовывает pane — поддержим видимость панели
      ensureActionsVisibility(name);
      return;
    }

    if (action === 'delete') {
      if (!confirm(`Удалить ${checked.length} строк(у/и)?`)) return;
      const urls = checked.map(ch => ch.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#policy-pane', swap: 'outerHTML' });
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
          await htmx.ajax('POST', urls[i], { target: '#policy-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      // Пока ждём перерисовку, не прячем панель (на случай без перерисовки)
      ensureActionsVisibility(name);
      return;
    }
  });

  // Делегирование: мастер-чекбокс
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
  });

  // Делегирование: чекбоксы строк
  document.addEventListener('change', (e) => {
    const root = pane();
    if (!root) return;
    const rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (!rowCb || !root.contains(rowCb)) return;
    const name = rowCb.name;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
  });

  // CSV result modal helper
  function showPolicyCsvResult(html) {
    var body = document.getElementById('policy-csv-result-body');
    var modalEl = document.getElementById('policy-csv-result-modal');
    if (!body || !modalEl) { alert(html); return; }
    body.innerHTML = html;
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  async function handlePolicyCsvUpload(uploadUrl, file) {
    var formData = new FormData();
    formData.append('csv_file', file);
    try {
      var resp = await fetch(uploadUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData,
      });
      var data = await resp.json();
      if (data.ok) {
        var html = '<div class="mb-2"><strong>Загружено строк: ' + data.created + '</strong></div>';
        if (data.warnings && data.warnings.length) {
          html += '<div class="text-danger mb-1"><strong>Предупреждения (' + data.warnings.length + '):</strong></div>';
          html += '<div class="text-danger">';
          for (var i = 0; i < data.warnings.length; i++) {
            html += '<div class="mb-1">' + data.warnings[i].replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>';
          }
          html += '</div>';
        }
        showPolicyCsvResult(html);
        await htmx.ajax('GET', '/policy/policy/partial/', { target: '#policy-pane', swap: 'innerHTML' });
      } else {
        showPolicyCsvResult('<div class="text-danger"><strong>Ошибка:</strong> ' +
          (data.error || 'Неизвестная ошибка').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
      }
    } catch (err) {
      showPolicyCsvResult('<div class="text-danger"><strong>Ошибка загрузки:</strong> ' +
        err.message.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
    }
  }

  document.addEventListener('click', function (e) {
    var mapping = {
      'sections-csv-upload-btn': 'sections-csv-file-input',
    };
    for (var btnId in mapping) {
      var btn = e.target.closest('#' + btnId);
      if (btn) {
        var fileInput = document.getElementById(mapping[btnId]);
        if (fileInput) { fileInput.value = ''; fileInput.click(); }
        return;
      }
    }
  });

  document.addEventListener('change', async function (e) {
    var mapping = {
      'sections-csv-file-input': '/policy/policy/section/csv-upload/',
    };
    var url = mapping[e.target.id];
    if (!url) return;
    var file = e.target.files[0];
    if (!file) return;
    await handlePolicyCsvUpload(url, file);
  });

  // Восстановление выбора только для таблицы, где было действие
  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (!(e.target && e.target.id === 'policy-pane')) return;
    const last = window.__tableSelLast;
    if (!last) return;
    const ids = (window.__tableSel && window.__tableSel[last]) || [];
    const set = new Set(ids || []);
    getRowChecksByName(last).forEach(b => { b.checked = set.has(String(b.value)); });
    updateMasterStateFor(last);
    updateRowHighlightFor(last);
    ensureActionsVisibility(last); // <- панель должна остаться видимой при отмеченных чекбоксах
    try { delete window.__tableSel[last]; } catch(e) { window.__tableSel[last] = []; }
    window.__tableSelLast = null;
  });
})();