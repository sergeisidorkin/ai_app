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
  };

  function pane() { return document.getElementById('classifiers-pane'); }
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
    if (oksmEl) parts.push('oksm_date=' + encodeURIComponent(oksmEl.value));
    if (okvEl) parts.push('okv_date=' + encodeURIComponent(okvEl.value));
    if (katdEl) parts.push('date=' + encodeURIComponent(katdEl.value));
    if (lwEl) parts.push('lw_date=' + encodeURIComponent(lwEl.value));
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
    const root = pane();
    if (!root) return;
    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;
    const panel = btn.closest('#oksm-actions, #okv-actions, #lei-actions, #katd-actions, #lw-actions');
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
    if (oksmEl) e.detail.parameters['oksm_date'] = oksmEl.value;
    if (okvEl) e.detail.parameters['okv_date'] = okvEl.value;
    if (katdEl) e.detail.parameters['date'] = katdEl.value;
    if (lwEl) e.detail.parameters['lw_date'] = lwEl.value;
  });

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
  function showCsvResult(html) {
    var body = document.getElementById('csv-result-body');
    var modalEl = document.getElementById('csv-result-modal');
    if (!body || !modalEl) { alert(html); return; }
    body.innerHTML = html;
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  // CSV upload helper
  async function handleCsvUpload(uploadUrl, file) {
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
        showCsvResult(html);
        await htmx.ajax('GET', '/classifiers/partial/' + filterQueryString(), {
          target: '#classifiers-pane', swap: 'outerHTML'
        });
      } else {
        showCsvResult('<div class="text-danger"><strong>Ошибка:</strong> ' +
          (data.error || 'Неизвестная ошибка').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
      }
    } catch (err) {
      showCsvResult('<div class="text-danger"><strong>Ошибка загрузки:</strong> ' +
        err.message.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
    }
  }

  // CSV upload buttons (OKSM + OKV)
  document.addEventListener('click', function (e) {
    var mapping = {
      'oksm-csv-upload-btn': 'oksm-csv-file-input',
      'okv-csv-upload-btn': 'okv-csv-file-input',
      'katd-csv-upload-btn': 'katd-csv-file-input',
      'lw-csv-upload-btn': 'lw-csv-file-input',
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
      'oksm-csv-file-input': '/classifiers/oksm/csv-upload/',
      'okv-csv-file-input': '/classifiers/okv/csv-upload/',
      'katd-csv-file-input': '/classifiers/katd/csv-upload/',
      'lw-csv-file-input': '/classifiers/lw/csv-upload/',
    };
    var url = mapping[e.target.id];
    if (!url) return;
    var file = e.target.files[0];
    if (!file) return;
    await handleCsvUpload(url, file);
  });

  document.body.addEventListener('htmx:afterSettle', function (e) {
    const settleId = e.target && e.target.id;
    const last = window.__clTableSelLast;
    if (!last) return;
    const cfg = TABLE_CONFIG[last];
    const expectedId = cfg?.settleId || 'classifiers-pane';
    if (settleId !== expectedId && settleId !== 'classifiers-pane') return;
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
