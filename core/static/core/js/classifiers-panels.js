(function () {
  if (window.__classifiersPanelBound) return;
  window.__classifiersPanelBound = true;

  window.__clTableSel = window.__clTableSel || {};
  window.__clTableSelLast = window.__clTableSelLast || null;

  const TABLE_CONFIG = {
    'oksm-select': { target: '#oksm-table-wrap', swap: 'innerHTML', url: '/classifiers/oksm/table/', settleId: 'oksm-table-wrap' },
    'okv-select': { target: '#okv-table-wrap', swap: 'innerHTML', url: '/classifiers/okv/table/', settleId: 'okv-table-wrap' },
    'lei-select': { target: '#lei-table-wrap', swap: 'innerHTML', url: '/classifiers/lei/table/', settleId: 'lei-table-wrap' },
    'katd-select': { target: '#katd-table-wrap', swap: 'innerHTML', url: '/classifiers/katd/table/', settleId: 'katd-table-wrap' },
    'lw-select': { target: '#lw-table-wrap', swap: 'innerHTML', url: '/classifiers/lw/table/', settleId: 'lw-table-wrap' },
    'ler-select': { target: '#ler-table-wrap', swap: 'innerHTML', url: '/classifiers/ler/table/', settleId: 'ler-table-wrap' },
  };

  const PANE_SELECTOR = '#classifiers-pane, #normatives-pane, #legal-entities-pane';
  function panes() {
    return Array.from(document.querySelectorAll(PANE_SELECTOR));
  }
  function paneOf(el) {
    return el?.closest?.(PANE_SELECTOR) || null;
  }
  function inAnyPane(el) {
    return !!paneOf(el);
  }
  const qa = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  function qaAllPanes(sel) {
    return panes().flatMap(p => qa(sel, p));
  }

  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  const csrftoken = getCookie('csrftoken');

  function getMasterForPanel(panel) {
    const id = panel?.id;
    if (!id) return null;
    const root = paneOf(panel);
    return root?.querySelector(`input.form-check-input[data-actions-id="${CSS.escape(id)}"]`) || null;
  }
  function getNameForPanel(panel) {
    const master = getMasterForPanel(panel);
    return master?.dataset?.targetName || null;
  }
  function getRowChecksByName(name) {
    return qaAllPanes(`tbody input.form-check-input[name="${CSS.escape(name)}"]`);
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
    let master = null;
    for (const p of panes()) {
      master = p.querySelector(`input.form-check-input[data-target-name="${CSS.escape(name)}"]`);
      if (master) break;
    }
    if (!master) return;
    const checkedCount = boxes.filter(b => b.checked).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }

  function findActionsByName(name) {
    for (const root of panes()) {
      const master = root.querySelector(`input.form-check-input[data-target-name="${CSS.escape(name)}"]`);
      if (!master) continue;
      const actionsId = master.getAttribute('data-actions-id') || '';
      if (!actionsId) continue;
      const panel = root.querySelector('#' + actionsId);
      if (panel) return panel;
    }
    return null;
  }
  function ensureActionsVisibility(name) {
    const panel = findActionsByName(name);
    if (!panel) return;
    const anyChecked = getRowChecksByName(name).some(b => b.checked);
    panel.classList.toggle('d-none', !anyChecked);
  }

  // Classifiers wrap/truncate toggle (OKSM, OKV)
  const CLF_WRAP_CFG = {
    'oksm-wrap-toggle': { wrap: 'oksm-table-wrap', cellClass: 'oksm-source-cell' },
    'okv-wrap-toggle':  { wrap: 'okv-table-wrap',  cellClass: 'okv-source-cell' },
    'katd-wrap-toggle': { wrap: 'katd-table-wrap', cellClass: 'katd-source-cell' },
    'lw-wrap-toggle':   { wrap: 'lw-table-wrap',   cellClass: 'lw-source-cell' },
  };
  document.addEventListener('click', function (e) {
    const toggle = e.target.closest('.clf-wrap-btn');
    if (!toggle) return;
    const cfg = CLF_WRAP_CFG[toggle.id];
    if (!cfg) return;
    const wrap = document.getElementById(cfg.wrap);
    const table = wrap?.querySelector('table');
    if (!table) return;

    table.classList.toggle('clf-truncated');
    const active = table.classList.contains('clf-truncated');
    toggle.classList.toggle('active', active);

    wrap.querySelectorAll('td.' + cfg.cellClass).forEach(td => {
      if (active) td.setAttribute('title', td.textContent.trim());
      else td.removeAttribute('title');
    });
  });

  function releaseFocus(btn) {
    if (btn && typeof btn.blur === 'function') btn.blur();
    const active = document.activeElement;
    if (active && typeof active.blur === 'function') active.blur();
  }

  function filterQueryString() {
    var parts = [];
    var oksmEl = document.getElementById('oksm-date-filter');
    var okvEl = document.getElementById('okv-date-filter');
    var katdEl = document.getElementById('katd-date-filter');
    var lwEl = document.getElementById('lw-date-filter');
    var lerEl = document.getElementById('ler-date-filter');
    if (oksmEl) parts.push('oksm_date=' + encodeURIComponent(oksmEl.value));
    if (okvEl) parts.push('okv_date=' + encodeURIComponent(okvEl.value));
    if (katdEl) parts.push('date=' + encodeURIComponent(katdEl.value));
    if (lwEl) parts.push('lw_date=' + encodeURIComponent(lwEl.value));
    if (lerEl) parts.push('ler_date=' + encodeURIComponent(lerEl.value));
    return parts.length ? '?' + parts.join('&') : '';
  }

  function urlWithFilters(url) {
    var qs = filterQueryString();
    return qs ? url + qs : url;
  }

  async function refreshTable(name) {
    const cfg = TABLE_CONFIG[name];
    if (!cfg) {
      await htmx.ajax('GET', '/classifiers/partial/' + filterQueryString(), {
        target: '#classifiers-pane',
        swap: 'outerHTML',
      });
      return;
    }
    await htmx.ajax('GET', cfg.url + filterQueryString(), {
      target: cfg.target,
      swap: cfg.swap,
    });
  }

  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !inAnyPane(btn)) return;
    const panel = btn.closest('#oksm-actions, #okv-actions, #lei-actions, #katd-actions, #lw-actions, #ler-actions');
    if (!panel) return;
    const action = btn.dataset.panelAction;
    const name = getNameForPanel(panel);
    if (!name) return;

    const checked = getCheckedByName(name);
    if (!checked.length) return;

    releaseFocus(btn);

    window.__clTableSel[name] = checked.map(ch => String(ch.value));
    window.__clTableSelLast = name;

    if (action === 'edit') {
      const first = checked[0];
      const tr = first.closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;
      await htmx.ajax('GET', url, { target: '#classifiers-modal .modal-content', swap: 'innerHTML' });
      ensureActionsVisibility(name);
      return;
    }

    if (action === 'delete') {
      if (!confirm(`Удалить ${checked.length} строк(у/и)?`)) return;
      const urls = checked.map(ch => ch.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      for (let i = 0; i < urls.length; i++) {
        await fetch(urlWithFilters(urls[i]), {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken, 'HX-Request': 'true' },
        }).catch(() => {});
      }
      await refreshTable(name);
      return;
    }

    if (action === 'up' || action === 'down') {
      let urls = checked
        .map(ch => ch.closest('tr')?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'])
        .filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      for (let i = 0; i < urls.length; i++) {
        await fetch(urlWithFilters(urls[i]), {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken, 'HX-Request': 'true' },
        }).catch(() => {});
      }
      await refreshTable(name);
      ensureActionsVisibility(name);
      return;
    }
  });

  document.addEventListener('htmx:configRequest', function(e) {
    var modal = document.getElementById('classifiers-modal');
    if (!modal || !modal.contains(e.target)) return;
    var oksmEl = document.getElementById('oksm-date-filter');
    var okvEl = document.getElementById('okv-date-filter');
    var katdEl = document.getElementById('katd-date-filter');
    var lwEl = document.getElementById('lw-date-filter');
    var lerEl = document.getElementById('ler-date-filter');
    if (oksmEl) e.detail.parameters['oksm_date'] = oksmEl.value;
    if (okvEl) e.detail.parameters['okv_date'] = okvEl.value;
    if (katdEl) e.detail.parameters['date'] = katdEl.value;
    if (lwEl) e.detail.parameters['lw_date'] = lwEl.value;
    if (lerEl) e.detail.parameters['ler_date'] = lerEl.value;
  });

  document.addEventListener('change', (e) => {
    const master = e.target.closest('input.form-check-input[data-actions-id][data-target-name]');
    if (!master || !inAnyPane(master)) return;
    const name = master.dataset.targetName;
    const boxes = getRowChecksByName(name);
    boxes.forEach(b => { b.checked = master.checked; });
    master.indeterminate = false;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
  });

  document.addEventListener('change', (e) => {
    const rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (!rowCb || !inAnyPane(rowCb)) return;
    const name = rowCb.name;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
  });

  // CSV result modal helper
  function showCsvResult(html) {
    var body = document.getElementById('csv-result-body');
    var modalEl = document.getElementById('csv-result-modal');
    if (!body || !modalEl) { alert(html); return; }
    body.innerHTML = html;
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  // CSV upload helper
  function esc(s) { return (s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

  async function handleCsvUpload(uploadUrl, file, refreshName) {
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
        var html = '<div class="mb-2"><strong>Создано строк: ' + data.created + '</strong></div>';
        if (data.updated) {
          html += '<div class="mb-2"><strong>Обновлено строк: ' + data.updated + '</strong></div>';
        }
        if (data.skipped) {
          html += '<div class="mb-2 text-muted">Пропущено (дубликаты без изменений): ' + data.skipped + '</div>';
        }
        if (data.conflicts && data.conflicts.length) {
          html += '<div class="text-warning mb-1"><strong>Конфликты / обновления (' + data.conflicts.length + '):</strong></div>';
          html += '<div class="text-warning" style="max-height:200px;overflow-y:auto;">';
          for (var i = 0; i < data.conflicts.length; i++) {
            html += '<div class="mb-1">' + esc(data.conflicts[i]) + '</div>';
          }
          html += '</div>';
        }
        if (data.warnings && data.warnings.length) {
          html += '<div class="text-danger mb-1 mt-2"><strong>Ошибки (' + data.warnings.length + '):</strong></div>';
          html += '<div class="text-danger" style="max-height:200px;overflow-y:auto;">';
          for (var i = 0; i < data.warnings.length; i++) {
            html += '<div class="mb-1">' + esc(data.warnings[i]) + '</div>';
          }
          html += '</div>';
        }
        showCsvResult(html);
        if (refreshName && TABLE_CONFIG[refreshName]) {
          await refreshTable(refreshName);
        } else {
          await htmx.ajax('GET', '/classifiers/partial/' + filterQueryString(), {
            target: '#classifiers-pane', swap: 'outerHTML'
          });
        }
      } else {
        showCsvResult('<div class="text-danger"><strong>Ошибка:</strong> ' + esc(data.error || 'Неизвестная ошибка') + '</div>');
      }
    } catch (err) {
      showCsvResult('<div class="text-danger"><strong>Ошибка загрузки:</strong> ' + esc(err.message) + '</div>');
    }
  }

  // CSV upload buttons (OKSM + OKV)
  document.addEventListener('click', function (e) {
    var mapping = {
      'oksm-csv-upload-btn': 'oksm-csv-file-input',
      'okv-csv-upload-btn': 'okv-csv-file-input',
      'katd-csv-upload-btn': 'katd-csv-file-input',
      'lw-csv-upload-btn': 'lw-csv-file-input',
      'ler-csv-upload-btn': 'ler-csv-file-input',
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
      'oksm-csv-file-input': { url: '/classifiers/oksm/csv-upload/', refresh: null },
      'okv-csv-file-input':  { url: '/classifiers/okv/csv-upload/',  refresh: null },
      'katd-csv-file-input': { url: '/classifiers/katd/csv-upload/', refresh: null },
      'lw-csv-file-input':   { url: '/classifiers/lw/csv-upload/',   refresh: 'lw-select' },
      'ler-csv-file-input':  { url: '/classifiers/ler/csv-upload/',  refresh: 'ler-select' },
    };
    var cfg = mapping[e.target.id];
    if (!cfg) return;
    var file = e.target.files[0];
    if (!file) return;
    await handleCsvUpload(cfg.url, file, cfg.refresh);
  });

  document.body.addEventListener('htmx:afterSettle', function (e) {
    const settleId = e.target && e.target.id;
    const last = window.__clTableSelLast;
    if (!last) return;
    const cfg = TABLE_CONFIG[last];
    const expectedId = cfg?.settleId || 'classifiers-pane';
    if (settleId !== expectedId && settleId !== 'classifiers-pane' && settleId !== 'normatives-pane' && settleId !== 'legal-entities-pane') return;
    const ids = (window.__clTableSel && window.__clTableSel[last]) || [];
    const set = new Set(ids || []);
    getRowChecksByName(last).forEach(b => { b.checked = set.has(String(b.value)); });
    updateMasterStateFor(last);
    updateRowHighlightFor(last);
    ensureActionsVisibility(last);
    try { delete window.__clTableSel[last]; } catch(e) { window.__clTableSel[last] = []; }
    window.__clTableSelLast = null;
  });
})();
