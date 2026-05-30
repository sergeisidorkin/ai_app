(function () {
  if (window.__expertsPanelBound) return;
  window.__expertsPanelBound = true;

  window.__espTableSel = window.__espTableSel || {};
  window.__expertsPaneDirty = window.__expertsPaneDirty || false;

  function pane() { return document.getElementById('experts-pane'); }
  const qa = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function updateExpertsTableScrollGaps() {
    const root = pane();
    if (!root) return;
    qa('.experts-specialties-table-wrap, .experts-profiles-table-wrap', root).forEach((wrap) => {
      wrap.classList.toggle('has-horizontal-scroll', wrap.scrollWidth > wrap.clientWidth + 1);
    });
  }

  function scheduleExpertsTableScrollGapsUpdate() {
    window.requestAnimationFrame(updateExpertsTableScrollGaps);
  }

  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  const csrftoken = getCookie('csrftoken');

  const PANELS = {
    'esp-actions': {
      name: 'esp-select',
      modal: '#experts-modal .modal-content',
      modalId: 'experts-modal',
      deleteLabel: 'строк(у/и)',
    },
    'epr-actions': {
      name: 'epr-select',
      modal: '#experts-profile-modal .modal-content',
      modalId: 'experts-profile-modal',
      deleteLabel: 'строк(у/и)',
    },
    'ecd-actions': {
      name: 'ecd-select',
      modal: '#experts-contract-details-modal .modal-content',
      modalId: 'experts-contract-details-modal',
      deleteLabel: 'строк(у/и)',
    },
  };

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

  function updateEditBtnState() {
    const root = pane();
    if (!root) return;
    const btn = root.querySelector('#epr-edit-btn');
    if (btn) {
      const checked = getCheckedByName('epr-select');
      btn.disabled = checked.length !== 1;
    }
  }

  function updateContractDetailsEditBtn() {
    const root = pane();
    if (!root) return;
    const btn = root.querySelector('#ecd-edit-btn');
    if (!btn) return;
    const anyChecked = getRowChecksByName('ecd-select').some(b => b.checked);
    btn.disabled = !anyChecked;
  }

  function findPanelConfig(btn) {
    for (const [panelId, config] of Object.entries(PANELS)) {
      if (btn.closest('#' + panelId)) return config;
    }
    return null;
  }

  function expertsTabIsActive() {
    return !!document.querySelector('#experts.tab-pane.show.active, #experts.tab-pane.active.show');
  }

  function expertsModalIsOpen() {
    return !!document.querySelector('#experts-modal.show, #experts-profile-modal.show, #experts-contract-details-modal.show');
  }

  async function refreshExpertsPane() {
    const root = pane();
    const url = root?.getAttribute('hx-get');
    if (!root || !url || !window.htmx) return;
    if (expertsModalIsOpen()) {
      window.__expertsPaneDirty = true;
      return;
    }
    await htmx.ajax('GET', url, { target: '#experts-pane', swap: 'outerHTML' });
    window.__expertsPaneDirty = false;
  }

  async function doEdit(name, config) {
    const checked = getCheckedByName(name);
    if (!checked.length) return;
    const first = checked[0];
    const tr = first.closest('tr');
    const url = tr?.dataset?.editUrl;
    if (!url) return;
    await htmx.ajax('GET', url, { target: config.modal, swap: 'innerHTML' });
    const modalEl = document.getElementById(config.modalId);
    if (modalEl && window.bootstrap) {
      window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
    ensureActionsVisibility(name);
  }

  document.addEventListener('click', async (e) => {
    const root = pane();
    if (!root) return;

    const editBtn = e.target.closest('#epr-edit-btn');
    if (editBtn && root.contains(editBtn)) {
      e.preventDefault();
      const config = PANELS['epr-actions'];
      window.__espTableSel['epr-select'] = getCheckedByName('epr-select').map(ch => String(ch.value));
      await doEdit('epr-select', config);
      return;
    }

    const ecdEditBtn = e.target.closest('#ecd-edit-btn');
    if (ecdEditBtn && root.contains(ecdEditBtn)) {
      e.preventDefault();
      const checked = getCheckedByName('ecd-select');
      if (!checked.length) return;
      const first = checked[0];
      const tr = first.closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;

      window.__espTableSel['ecd-select'] = checked.map(ch => String(ch.value));

      const config = PANELS['ecd-actions'];
      await htmx.ajax('GET', url, { target: config.modal, swap: 'innerHTML' });
      const modalEl = document.getElementById(config.modalId);
      if (modalEl && window.bootstrap) {
        window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
      }
      updateContractDetailsEditBtn();
      return;
    }

    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;

    const config = findPanelConfig(btn);
    if (!config) return;

    const action = btn.dataset.panelAction;
    const name = config.name;

    const checked = getCheckedByName(name);
    if (!checked.length) return;

    window.__espTableSel[name] = checked.map(ch => String(ch.value));

    if (action === 'edit') {
      await doEdit(name, config);
      return;
    }

    if (action === 'delete') {
      if (!confirm(`Удалить ${checked.length} ${config.deleteLabel}?`)) return;
      const urls = checked.map(ch => ch.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#experts-pane', swap: 'outerHTML' });
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
          await htmx.ajax('POST', urls[i], { target: '#experts-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      ensureActionsVisibility(name);
      return;
    }
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
    if (name === 'epr-select') updateEditBtnState();
    if (name === 'ecd-select') updateContractDetailsEditBtn();
  });

  document.addEventListener('change', (e) => {
    const root = pane();
    if (!root) return;
    const colpickerInput = e.target.closest('#esp-colpicker-menu input.form-check-input, #epr-colpicker-menu input.form-check-input');
    if (colpickerInput && root.contains(colpickerInput)) {
      scheduleExpertsTableScrollGapsUpdate();
      return;
    }
    const rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (!rowCb || !root.contains(rowCb)) return;
    const name = rowCb.name;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
    if (name === 'epr-select') updateEditBtnState();
    if (name === 'ecd-select') updateContractDetailsEditBtn();
  });

  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (!(e.target && e.target.id === 'experts-pane')) return;
    const sel = window.__espTableSel || {};
    Object.keys(sel).forEach(name => {
      const ids = sel[name] || [];
      const set = new Set(ids);
      getRowChecksByName(name).forEach(b => { b.checked = set.has(String(b.value)); });
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
    });
    updateEditBtnState();
    updateContractDetailsEditBtn();
    window.__espTableSel = {};
    initWrapToggle();
    scheduleExpertsTableScrollGapsUpdate();
  });

  document.body.addEventListener('contacts-updated', function () {
    window.__expertsPaneDirty = true;
    if (expertsTabIsActive()) {
      refreshExpertsPane().catch(() => {});
    }
  });

  document.addEventListener('shown.bs.tab', function (e) {
    const trigger = e.target;
    if (!trigger || trigger.getAttribute('href') !== '#experts') return;
    if (!window.__expertsPaneDirty) return;
    refreshExpertsPane().catch(() => {});
  });

  var P = window.UIPref;
  window.__eprWrapActive = P ? P.get('experts:wrapActive', true) : true;

  function initWrapToggle() {
    const toggle = document.getElementById('epr-wrap-toggle');
    if (!toggle) return;
    toggle.classList.toggle('active', window.__eprWrapActive);
    const wrap = document.getElementById('epr-table-wrap');
    const table = wrap?.querySelector('table');
    if (table) table.classList.toggle('clf-truncated', window.__eprWrapActive);
  }

  document.addEventListener('click', function (e) {
    const toggle = e.target.closest('#epr-wrap-toggle');
    if (!toggle) return;
    const wrap = document.getElementById('epr-table-wrap');
    const table = wrap?.querySelector('table');
    if (!table) return;
    table.classList.toggle('clf-truncated');
    const active = table.classList.contains('clf-truncated');
    toggle.classList.toggle('active', active);
    window.__eprWrapActive = active;
    if (P) P.set('experts:wrapActive', active);
    scheduleExpertsTableScrollGapsUpdate();
  });

  window.addEventListener('resize', scheduleExpertsTableScrollGapsUpdate);
  window.addEventListener('load', scheduleExpertsTableScrollGapsUpdate);

  function showExpertsCsvResult(html) {
    var body = document.getElementById('experts-csv-result-body');
    var modalEl = document.getElementById('experts-csv-result-modal');
    if (!body || !modalEl) {
      alert(html.replace(/<[^>]+>/g, ''));
      return;
    }
    body.innerHTML = html;
    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  async function handleExpertsTableUpload(uploadUrl, file) {
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
        var html;
        if (typeof data.updated === 'number') {
          html = '<div class="mb-2"><strong>Обновлено строк: ' + data.updated + '</strong></div>';
        } else {
          html = '<div class="mb-2"><strong>Загружено строк: ' + data.created + '</strong></div>';
        }
        if (data.warnings && data.warnings.length) {
          html += '<div class="text-danger mb-1"><strong>Предупреждения (' + data.warnings.length + '):</strong></div>';
          html += '<div class="text-danger">';
          for (var i = 0; i < data.warnings.length; i++) {
            html += '<div class="mb-1">' + data.warnings[i].replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>';
          }
          html += '</div>';
        }
        showExpertsCsvResult(html);
        await refreshExpertsPane();
      } else {
        showExpertsCsvResult('<div class="text-danger"><strong>Ошибка:</strong> ' +
          (data.error || 'Неизвестная ошибка').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
      }
    } catch (err) {
      showExpertsCsvResult('<div class="text-danger"><strong>Ошибка загрузки:</strong> ' +
        err.message.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
    }
  }

  document.addEventListener('click', function (event) {
    var uploadMapping = {
      'esp-csv-upload-btn': 'esp-csv-file-input',
      'epr-csv-upload-btn': 'epr-csv-file-input',
    };
    for (var btnId in uploadMapping) {
      if (!event.target.closest('#' + btnId)) continue;
      var fileInput = document.getElementById(uploadMapping[btnId]);
      if (fileInput) fileInput.click();
      return;
    }
  });

  document.addEventListener('change', async function (event) {
    var uploadMapping = {
      'esp-csv-file-input': '/experts/specialty/csv-upload/',
      'epr-csv-file-input': '/experts/profile/csv-upload/',
    };
    var uploadUrl = uploadMapping[event.target.id];
    if (!uploadUrl) return;
    var file = event.target.files && event.target.files[0];
    event.target.value = '';
    if (!file) return;
    await handleExpertsTableUpload(uploadUrl, file);
  });
})();
