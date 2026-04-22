(function () {
  if (window.__classifiersPanelBound) return;
  window.__classifiersPanelBound = true;

  window.__clTableSel = window.__clTableSel || {};
  window.__clTableSelLast = window.__clTableSelLast || null;

  const TABLE_CONFIG = {
    'oksm-select': { target: '#oksm-table-wrap', swap: 'innerHTML', url: '/classifiers/oksm/table/', settleId: 'oksm-table-wrap' },
    'okv-select': { target: '#okv-table-wrap', swap: 'innerHTML', url: '/classifiers/okv/table/', settleId: 'okv-table-wrap' },
    'lei-select': { target: '#lei-table-wrap', swap: 'innerHTML', url: '/classifiers/lei/table/', settleId: 'lei-table-wrap' },
    'pei-select': { target: '#pei-table-wrap', swap: 'innerHTML', url: '/classifiers/pei/table/', settleId: 'pei-table-wrap' },
    'numcap-select': { target: '#numcap-table-wrap', swap: 'innerHTML', url: '/classifiers/numcap/table/', settleId: 'numcap-table-wrap' },
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
  const SECTION_PREF_KEY_PREFIX = 'classifiers:section:';

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
    'numcap-wrap-toggle': { wrap: 'numcap-table-wrap', cellClass: 'numcap-gar-cell' },
    'katd-wrap-toggle': { wrap: 'katd-table-wrap', cellClass: 'katd-source-cell' },
    'lw-wrap-toggle':   { wrap: 'lw-table-wrap',   cellClass: 'lw-source-cell' },
  };
  const CLF_SECTION_CFG = {
    'oksm-section-toggle': {
      controls: 'oksm-header-controls',
      body: 'oksm-section-body',
      collapsedLabel: 'Развернуть раздел ОКСМ',
      expandedLabel: 'Свернуть раздел ОКСМ',
    },
    'okv-section-toggle': {
      controls: 'okv-header-controls',
      body: 'okv-section-body',
      collapsedLabel: 'Развернуть раздел ОКВ',
      expandedLabel: 'Свернуть раздел ОКВ',
    },
    'lei-section-toggle': {
      controls: 'lei-header-controls',
      body: 'lei-section-body',
      collapsedLabel: 'Развернуть раздел идентификаторов юрлиц',
      expandedLabel: 'Свернуть раздел идентификаторов юрлиц',
    },
    'pei-section-toggle': {
      controls: 'pei-header-controls',
      body: 'pei-section-body',
      collapsedLabel: 'Развернуть раздел идентификаторов физлиц',
      expandedLabel: 'Свернуть раздел идентификаторов физлиц',
    },
    'numcap-section-toggle': {
      controls: 'numcap-header-controls',
      body: 'numcap-section-body',
      collapsedLabel: 'Развернуть раздел реестра нумерации',
      expandedLabel: 'Свернуть раздел реестра нумерации',
    },
    'katd-section-toggle': {
      controls: 'katd-header-controls',
      body: 'katd-section-body',
      collapsedLabel: 'Развернуть раздел КАТД',
      expandedLabel: 'Свернуть раздел КАТД',
    },
    'rfs-section-toggle': {
      controls: 'rfs-header-controls',
      body: 'rfs-section-body',
      collapsedLabel: 'Развернуть раздел кодов ФНС',
      expandedLabel: 'Свернуть раздел кодов ФНС',
    },
  };

  function getSectionPref(toggleId, defaultValue) {
    try {
      const raw = window.localStorage.getItem(SECTION_PREF_KEY_PREFIX + toggleId);
      if (raw === null) return defaultValue;
      return raw === '1';
    } catch (e) {
      return defaultValue;
    }
  }

  function setSectionPref(toggleId, collapsed) {
    try {
      window.localStorage.setItem(SECTION_PREF_KEY_PREFIX + toggleId, collapsed ? '1' : '0');
    } catch (e) {}
  }

  function syncCollapsedSectionHeaderSpacing() {
    const toggles = Array.from(document.querySelectorAll('.classifiers-section-toggle'));
    const items = toggles.map(toggle => {
      const header = toggle.closest('.table-section-header');
      const bodyId = toggle.dataset.sectionBodyId;
      const body = bodyId ? document.getElementById(bodyId) : null;
      if (!header || !body) return null;

      if (!header.dataset.baseMarginTop) {
        header.dataset.baseMarginTop = header.style.marginTop || '0px';
      }

      return {
        header,
        collapsed: body.classList.contains('d-none'),
        baseMarginTop: header.dataset.baseMarginTop,
      };
    }).filter(Boolean);

    items.forEach((item, index) => {
      const prev = items[index - 1];
      const basePx = parseFloat(item.baseMarginTop) || 0;
      const nextPx = prev && prev.collapsed && item.collapsed && basePx > 0 ? basePx / 4 : basePx;
      item.header.style.marginTop = `${nextPx}px`;
    });
  }

  function applySectionState(toggleId, collapsed) {
    const cfg = CLF_SECTION_CFG[toggleId];
    if (!cfg) return;
    const toggle = document.getElementById(toggleId);
    if (!toggle) return;

    const controls = document.getElementById(cfg.controls);
    const body = document.getElementById(cfg.body);
    const icon = toggle.querySelector('i');
    const label = collapsed ? cfg.collapsedLabel : cfg.expandedLabel;

    if (controls) {
      controls.classList.toggle('classifiers-section-controls-hidden', collapsed);
      controls.setAttribute('aria-hidden', collapsed ? 'true' : 'false');
    }
    if (body) body.classList.toggle('d-none', collapsed);

    toggle.classList.toggle('active', collapsed);
    toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    toggle.setAttribute('aria-label', label);
    toggle.setAttribute('title', label);

    if (icon) icon.className = collapsed ? 'bi bi-plus-square' : 'bi bi-dash-square';
    syncCollapsedSectionHeaderSpacing();
  }

  function initClassifierSectionToggles() {
    Object.keys(CLF_SECTION_CFG).forEach(toggleId => {
      applySectionState(toggleId, getSectionPref(toggleId, false));
    });
  }

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

  document.addEventListener('click', function (e) {
    const toggle = e.target.closest('.classifiers-section-toggle');
    if (!toggle) return;
    const cfg = CLF_SECTION_CFG[toggle.id];
    if (!cfg) return;

    const body = document.getElementById(cfg.body);
    const isCollapsed = !!body && body.classList.contains('d-none');
    const nextCollapsed = !isCollapsed;

    applySectionState(toggle.id, nextCollapsed);
    setSectionPref(toggle.id, nextCollapsed);
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
    var numcapQEl = document.getElementById('numcap-q-filter');
    var numcapCodeEl = document.getElementById('numcap-code-filter');
    var numcapRegionEl = document.getElementById('numcap-region-filter');
    var numcapPageEl = document.getElementById('numcap-page-input');
    if (oksmEl) parts.push('oksm_date=' + encodeURIComponent(oksmEl.value));
    if (okvEl) parts.push('okv_date=' + encodeURIComponent(okvEl.value));
    if (katdEl) parts.push('date=' + encodeURIComponent(katdEl.value));
    if (lwEl) parts.push('lw_date=' + encodeURIComponent(lwEl.value));
    if (numcapQEl && numcapQEl.value) parts.push('numcap_q=' + encodeURIComponent(numcapQEl.value));
    if (numcapCodeEl && numcapCodeEl.value) parts.push('numcap_code=' + encodeURIComponent(numcapCodeEl.value));
    if (numcapRegionEl && numcapRegionEl.value) parts.push('numcap_region=' + encodeURIComponent(numcapRegionEl.value));
    if (numcapPageEl) parts.push('numcap_page=' + encodeURIComponent(numcapPageEl.value));
    return parts.length ? '?' + parts.join('&') : '';
  }

  function urlWithFilters(url) {
    var qs = filterQueryString();
    return qs ? url + qs : url;
  }

  async function refreshTable(name) {
    const cfg = TABLE_CONFIG[name];
    if (!cfg) {
      const legacyPane = document.getElementById('classifiers-pane');
      if (!legacyPane) {
        console.warn('[classifiers] skipped refresh for unknown table:', name);
        return;
      }
      await htmx.ajax('GET', '/classifiers/partial/' + filterQueryString(), {
        target: '#classifiers-pane',
        swap: 'outerHTML',
      });
      return;
    }
    const targetEl = document.querySelector(cfg.target);
    if (!targetEl) {
      console.warn('[classifiers] skipped refresh without target:', name, cfg.target);
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
    const panel = btn.closest('#oksm-actions, #okv-actions, #lei-actions, #pei-actions, #numcap-actions, #katd-actions, #lw-actions, #ler-actions');
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

  async function handleCsvUpload(uploadUrl, files, refreshName) {
    var formData = new FormData();
    var selectedFiles = Array.isArray(files) ? files : [files];
    if (selectedFiles.length > 1) {
      selectedFiles.forEach(function (file) {
        formData.append('csv_files', file);
      });
    } else if (selectedFiles[0]) {
      formData.append('csv_file', selectedFiles[0]);
    }
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
        if (data.files && data.files.length) {
          html += '<div class="text-muted mt-2">';
          for (var j = 0; j < data.files.length; j++) {
            var item = data.files[j];
            html += '<div class="mb-1">' + esc(item.name) + ': обработано ' + item.processed + ', добавлено ' + item.created + '</div>';
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
      'numcap-csv-upload-btn': 'numcap-csv-file-input',
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
      'numcap-csv-file-input': { url: '/classifiers/numcap/csv-upload/', refresh: 'numcap-select' },
      'katd-csv-file-input': { url: '/classifiers/katd/csv-upload/', refresh: null },
      'lw-csv-file-input':   { url: '/classifiers/lw/csv-upload/',   refresh: 'lw-select' },
      'ler-csv-file-input':  { url: '/classifiers/ler/csv-upload/',  refresh: 'ler-select' },
    };
    var cfg = mapping[e.target.id];
    if (!cfg) return;
    var files = Array.from(e.target.files || []);
    if (!files.length) return;
    await handleCsvUpload(cfg.url, files.length > 1 ? files : files[0], cfg.refresh);
  });

  document.body.addEventListener('htmx:afterSettle', function (e) {
    const settleId = e.target && e.target.id;
    const last = window.__clTableSelLast;
    initClassifierSectionToggles();
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

  initClassifierSectionToggles();
})();
