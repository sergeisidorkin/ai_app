(function () {
  if (window.__expertsPanelBound) return;
  window.__expertsPanelBound = true;

  window.__espTableSel = window.__espTableSel || {};

  function pane() { return document.getElementById('experts-pane'); }
  const qa = (sel, root) => Array.from((root || document).querySelectorAll(sel));

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
    if (!btn) return;
    const checked = getCheckedByName('epr-select');
    btn.disabled = checked.length !== 1;
  }

  function findPanelConfig(btn) {
    for (const [panelId, config] of Object.entries(PANELS)) {
      if (btn.closest('#' + panelId)) return config;
    }
    return null;
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
    if (name === 'epr-select') updateEditBtnState();
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
    window.__espTableSel = {};
    initWrapToggle();
  });

  window.__eprWrapActive = true;

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
  });
})();
