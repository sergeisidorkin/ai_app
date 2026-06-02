(function () {
  if (window.__contractsPanelBound) return;
  window.__contractsPanelBound = true;

  function pane() { return document.getElementById('contracts-pane'); }
  var qa = function(sel, root) { return Array.from((root || document).querySelectorAll(sel)); };

  function getRowChecks() {
    return qa('tbody input.form-check-input[name="contract-row-select"]', pane());
  }
  function getVisibleRowChecks() {
    return getRowChecks().filter(function(b) {
      var tr = b.closest('tr');
      return tr && !tr.classList.contains('d-none') && !b.disabled;
    });
  }
  function getChecked() {
    return getVisibleRowChecks().filter(function(b) { return b.checked; });
  }
  function updateRowHighlight() {
    getRowChecks().forEach(function(b) {
      var tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updateMasterState() {
    var boxes = getVisibleRowChecks();
    var master = pane() && pane().querySelector('#contracts-master');
    if (!master) return;
    var checkedCount = boxes.filter(function(b) { return b.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }
  function ensureActionsVisibility() {
    var panel = pane() && pane().querySelector('#contracts-actions');
    if (!panel) return;
    var any = getChecked().length > 0;
    panel.classList.toggle('d-none', !any);
  }
  function updateEditBtn() {
    var root = pane();
    if (!root) return;
    var btn = root.querySelector('#contracts-edit-btn');
    if (!btn) return;
    var anyChecked = getChecked().length > 0;
    btn.disabled = !anyChecked;
  }

  function updateTableScrollGaps() {
    qa('.contracts-action-table-wrap, #contract-conclusion-section .contract-conclusion-table-wrap, #contract-details-section .contract-requisites-table-wrap', document).forEach(function(wrap) {
      wrap.classList.toggle('has-horizontal-scroll', wrap.scrollWidth > wrap.clientWidth + 1);
    });
  }

  function scheduleTableScrollGapsUpdate() {
    window.requestAnimationFrame(updateTableScrollGaps);
  }

  function showContractsModal() {
    var modalEl = document.getElementById('contracts-modal');
    if (!modalEl || !window.bootstrap) return;
    var dlg = modalEl.querySelector('.modal-dialog');
    if (dlg) {
      dlg.classList.remove('modal-sm', 'modal-lg', 'modal-xl');
      var sizeEl = modalEl.querySelector('[data-modal-size]');
      if (sizeEl) dlg.classList.add('modal-' + sizeEl.dataset.modalSize);
    }
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  document.addEventListener('click', function(e) {
    var root = pane(); if (!root) return;

    var editBtn = e.target.closest('#contracts-edit-btn');
    if (editBtn && root.contains(editBtn)) {
      var checked = getChecked();
      if (!checked.length) return;
      var tr = checked[0].closest('tr');
      var url = tr && tr.dataset.editUrl;
      if (!url) return;
      var target = document.querySelector('#contracts-modal .modal-content');
      if (!target) return;
      htmx.ajax('GET', url, target).then(function() {
        showContractsModal();
      });
      updateEditBtn();
      return;
    }
  });

  document.addEventListener('change', function(e) {
    var root = pane(); if (!root) return;

    var master = e.target.closest('#contracts-master');
    if (master && root.contains(master)) {
      getVisibleRowChecks().forEach(function(b) { b.checked = master.checked; });
      master.indeterminate = false;
      updateMasterState();
      updateRowHighlight();
      ensureActionsVisibility();
      updateEditBtn();
      return;
    }

    var rowCb = e.target.closest('tbody input.form-check-input[name="contract-row-select"]');
    if (rowCb && root.contains(rowCb)) {
      updateMasterState();
      updateRowHighlight();
      ensureActionsVisibility();
      updateEditBtn();
      return;
    }
  });

  document.body.addEventListener('htmx:afterSettle', function(e) {
    var root = pane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
    updateEditBtn();
    scheduleTableScrollGapsUpdate();
  });

  document.body.addEventListener('contracts-project-filter-applied', function() {
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
    updateEditBtn();
    scheduleTableScrollGapsUpdate();
  });

  document.addEventListener('DOMContentLoaded', function() {
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
    updateEditBtn();
    scheduleTableScrollGapsUpdate();
  });

  window.addEventListener('resize', scheduleTableScrollGapsUpdate);
  window.addEventListener('load', scheduleTableScrollGapsUpdate);
  window.addEventListener('contracts:section-shown', scheduleTableScrollGapsUpdate);
})();


/* -----------------------------------------------------------------------
   Performer requisites subsection
   ----------------------------------------------------------------------- */
(function () {
  if (window.__contractRequisitesBound) return;
  window.__contractRequisitesBound = true;
  if (typeof window.__contractRequisitesSel === 'undefined') {
    window.__contractRequisitesSel = null;
  }

  function pane() { return document.getElementById('contract-requisites-pane'); }
  var qa = function(sel, root) { return Array.from((root || document).querySelectorAll(sel)); };

  function getRowChecks() {
    return qa('tbody input.form-check-input[name="ecd-select"]', pane());
  }

  function getChecked() {
    return getRowChecks().filter(function(box) { return box.checked; });
  }

  function updateRowHighlight() {
    getRowChecks().forEach(function(box) {
      var tr = box.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!box.checked);
    });
  }

  function updateMasterState() {
    var boxes = getRowChecks();
    var root = pane();
    var master = root && root.querySelector('input.form-check-input[data-target-name="ecd-select"]');
    if (!master) return;
    var checkedCount = boxes.filter(function(box) { return box.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }

  function updateEditBtn() {
    var root = pane();
    var btn = root && root.querySelector('#ecd-edit-btn');
    if (!btn) return;
    btn.disabled = getChecked().length === 0;
  }

  function withRequisitesTarget(url) {
    if (!url) return '';
    return url + (url.indexOf('?') === -1 ? '?' : '&') + 'target=contract-requisites';
  }

  function requisitesModalIsOpen() {
    return !!document.querySelector('#contract-requisites-modal.show');
  }

  function refreshPane() {
    var root = pane();
    if (!root || !window.htmx) return Promise.resolve();
    if (requisitesModalIsOpen()) return Promise.resolve();
    var url = root.getAttribute('hx-get');
    if (!url) return Promise.resolve();
    window.__contractRequisitesSel = getChecked().map(function(ch) { return String(ch.value); });
    return htmx.ajax('GET', url, { target: '#contract-requisites-pane', swap: 'outerHTML' });
  }

  document.addEventListener('click', function(e) {
    var root = pane();
    if (!root) return;

    var editBtn = e.target.closest('#ecd-edit-btn');
    if (!editBtn || !root.contains(editBtn)) return;
    e.preventDefault();

    var checked = getChecked();
    if (!checked.length) return;
    var tr = checked[0].closest('tr');
    var url = withRequisitesTarget(tr && tr.dataset.editUrl);
    var target = document.querySelector('#contract-requisites-modal .modal-content');
    if (!url || !target || !window.htmx) return;

    window.__contractRequisitesSel = checked.map(function(ch) { return String(ch.value); });
    htmx.ajax('GET', url, { target: target, swap: 'innerHTML' }).then(function() {
      var modalEl = document.getElementById('contract-requisites-modal');
      if (modalEl && window.bootstrap) {
        window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
      }
    });
    updateEditBtn();
  });

  document.addEventListener('change', function(e) {
    var root = pane();
    if (!root) return;

    var master = e.target.closest('input.form-check-input[data-target-name="ecd-select"]');
    if (master && root.contains(master)) {
      getRowChecks().forEach(function(box) { box.checked = master.checked; });
      master.indeterminate = false;
      updateMasterState();
      updateRowHighlight();
      updateEditBtn();
      return;
    }

    var rowCb = e.target.closest('tbody input.form-check-input[name="ecd-select"]');
    if (rowCb && root.contains(rowCb)) {
      updateMasterState();
      updateRowHighlight();
      updateEditBtn();
    }
  });

  document.body.addEventListener('htmx:afterSettle', function(e) {
    var root = pane();
    if (!root || !(e.target === root || root.contains(e.target))) return;
    if (Array.isArray(window.__contractRequisitesSel)) {
      var selected = new Set(window.__contractRequisitesSel);
      getRowChecks().forEach(function(box) {
        box.checked = selected.has(String(box.value));
      });
      window.__contractRequisitesSel = null;
    }
    updateMasterState();
    updateRowHighlight();
    updateEditBtn();
  });

  document.body.addEventListener('contacts-updated', function() {
    refreshPane().catch(function() {});
  });

  document.addEventListener('DOMContentLoaded', function() {
    updateMasterState();
    updateRowHighlight();
    updateEditBtn();
  });
})();


/* -----------------------------------------------------------------------
   Development table ("В разработке") panel
   ----------------------------------------------------------------------- */
(function () {
  if (window.__contractsDraftsBound) return;
  window.__contractsDraftsBound = true;
  window.__contractsDraftSel = window.__contractsDraftSel || [];

  var CONTRACTS_DRAFTS_COLPICKER = {
    prefKey: 'contracts:draftsHiddenCols:v7',
    wrapId: 'contracts-drafts-colpicker-wrap',
    btnId: 'contracts-drafts-colpicker-btn',
    menuId: 'contracts-drafts-colpicker-menu',
    allId: 'contracts-drafts-col-all',
    tableId: 'contracts-drafts-table',
    hidden: null,
  };

  var CONTRACTS_PAYMENT_COLPICKER = {
    prefKey: 'contracts:paymentScheduleHiddenCols:v2',
    wrapId: 'contracts-payment-colpicker-wrap',
    btnId: 'contracts-payment-colpicker-btn',
    menuId: 'contracts-payment-colpicker-menu',
    allId: 'contracts-payment-col-all',
    tableId: 'contracts-payment-schedule-table',
    hidden: null,
  };

  var CONTRACTS_DRAFTS_COL_WEIGHTS = {
    'contract-number': 10,
    'contract-date': 7,
    'type': 6,
    'name': 20,
    'status': 10,
    'year': 5,
    'customer': 20,
    'country': 5,
    'identifier': 4,
    'registration-number': 7,
    'region': 7,
    'date': 5,
    'asset-owner': 20,
    'asset-owner-country': 5,
    'asset-owner-identifier': 4,
    'asset-owner-reg-number': 7,
    'asset-owner-region': 7,
    'asset-owner-date': 5,
  };

  var CONTRACTS_PAYMENT_COL_WEIGHTS = {
    'contract-number': 10,
    'type': 6,
    'name': 20,
    'stage': 7,
    'evaluation-date': 8,
    'start-date': 8,
    'term': 9,
    'preliminary-report-date': 8,
    'final-report-weeks': 9,
    'final-report-date': 8,
    'advance-percent': 7,
    'advance-term': 7,
    'preliminary-report-percent': 7,
    'preliminary-report-term': 7,
    'final-report-percent': 7,
    'final-report-term': 7,
  };

  var CONTRACTS_FIXED_COL_WIDTHS = {
    'number': '70px',
    'tkp-id': '90px',
    'agreement-type': '155px',
    'sub-number': '40px',
    'group': '70px',
    'project-id': '125px',
  };

  function pane() { return document.getElementById('contracts-drafts-pane'); }
  var qa = function(sel, root) { return Array.from((root || document).querySelectorAll(sel)); };

  function getDefaultHiddenColumns(cfg) {
    var menu = document.getElementById(cfg.menuId);
    var hidden = {};
    if (!menu) return hidden;
    menu.querySelectorAll('input.form-check-input[data-default-hidden="true"]:not([value="all"])').forEach(function(cb) {
      hidden[cb.value] = true;
    });
    return hidden;
  }

  function getHiddenColumns(cfg) {
    if (!cfg.hidden) {
      var saved = window.UIPref ? UIPref.get(cfg.prefKey, null) : null;
      cfg.hidden = saved && typeof saved === 'object' && !Array.isArray(saved)
        ? saved
        : getDefaultHiddenColumns(cfg);
    }
    return cfg.hidden || {};
  }

  function saveHiddenColumns(cfg) {
    if (window.UIPref) UIPref.set(cfg.prefKey, getHiddenColumns(cfg));
  }

  function updateColPickerLabel(btn, menu) {
    var cbs = qa('input.form-check-input:not([value="all"])', menu);
    var checked = cbs.filter(function(cb) { return cb.checked; }).length;
    btn.textContent = checked === cbs.length ? 'Все поля' : checked + ' из ' + cbs.length;
  }

  function applyColumnVisibility(cfg, weights) {
    var table = document.getElementById(cfg.tableId);
    if (!table) return;
    var hidden = Object.keys(getHiddenColumns(cfg));
    table.querySelectorAll('[data-col]').forEach(function(cell) {
      cell.style.display = hidden.includes(cell.getAttribute('data-col')) ? 'none' : '';
    });

    var visibleWeightedCols = [];
    table.querySelectorAll('col[data-col]').forEach(function(col) {
      var dataCol = col.getAttribute('data-col');
      var isHidden = hidden.includes(dataCol);
      col.style.display = isHidden ? 'none' : '';
      var fixedWidth = CONTRACTS_FIXED_COL_WIDTHS[dataCol];
      if (fixedWidth) {
        col.style.setProperty('width', fixedWidth, 'important');
        col.style.setProperty('min-width', fixedWidth, 'important');
        col.style.setProperty('max-width', fixedWidth, 'important');
        return;
      }
      if (!isHidden) visibleWeightedCols.push(col);
    });

    var totalWeight = visibleWeightedCols.reduce(function(sum, col) {
      return sum + (weights[col.getAttribute('data-col')] || 5);
    }, 0) || 1;

    visibleWeightedCols.forEach(function(col) {
      var weight = weights[col.getAttribute('data-col')] || 5;
      col.style.setProperty('width', (weight / totalWeight * 100).toFixed(4) + '%', 'important');
    });
  }

  function initColPicker(cfg, weights) {
    var wrap = document.getElementById(cfg.wrapId);
    var btn = document.getElementById(cfg.btnId);
    var menu = document.getElementById(cfg.menuId);
    if (!wrap || !btn || !menu) return;

    cfg.hidden = null;

    btn.onclick = function(event) {
      event.stopPropagation();
      var shouldShow = !menu.classList.contains('show');
      menu.classList.toggle('show', shouldShow);
      menu.style.maxHeight = '';
      var header = wrap.closest('.table-section-header');
      if (header) header.classList.toggle('tkp-colpicker-open', shouldShow);
    };

    var cbs = qa('input.form-check-input:not([value="all"])', menu);
    var hiddenState = getHiddenColumns(cfg);
    cbs.forEach(function(cb) {
      cb.checked = !hiddenState[cb.value];
    });

    var allCb = document.getElementById(cfg.allId);
    if (allCb) {
      allCb.checked = cbs.every(function(cb) { return cb.checked; });
    }

    updateColPickerLabel(btn, menu);
    applyColumnVisibility(cfg, weights);

    menu.onchange = function(event) {
      var cb = event.target;
      if (!cb.classList.contains('form-check-input')) return;
      var items = qa('input.form-check-input:not([value="all"])', menu);
      if (cb.value === 'all') {
        items.forEach(function(item) { item.checked = cb.checked; });
      } else {
        var ac = document.getElementById(cfg.allId);
        if (ac) ac.checked = items.every(function(item) { return item.checked; });
      }
      cfg.hidden = {};
      items.forEach(function(item) {
        if (!item.checked) cfg.hidden[item.value] = true;
      });
      saveHiddenColumns(cfg);
      updateColPickerLabel(btn, menu);
      applyColumnVisibility(cfg, weights);
      scheduleDraftTableScrollGapsUpdate();
    };
  }

  function initColumnPickers() {
    initColPicker(CONTRACTS_DRAFTS_COLPICKER, CONTRACTS_DRAFTS_COL_WEIGHTS);
    initColPicker(CONTRACTS_PAYMENT_COLPICKER, CONTRACTS_PAYMENT_COL_WEIGHTS);
  }

  function getCookie(name) {
    var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }

  function getRowChecks() {
    return qa('tbody input.form-check-input[name="contracts-draft-select"]', pane());
  }

  function getChecked() {
    return getRowChecks().filter(function(box) { return box.checked; });
  }

  function updateRowHighlight() {
    getRowChecks().forEach(function(box) {
      var tr = box.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!box.checked);
    });
  }

  function updateMasterState() {
    var boxes = getRowChecks();
    var master = pane() && pane().querySelector('#contracts-drafts-master');
    if (!master) return;
    var checkedCount = boxes.filter(function(box) { return box.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }

  function ensureActionsVisibility() {
    var actions = pane() && pane().querySelector('#contracts-drafts-actions');
    if (!actions) return;
    var anyChecked = getChecked().length > 0;
    actions.classList.toggle('d-none', !anyChecked);
    actions.classList.toggle('d-flex', anyChecked);
  }

  function showContractsModal() {
    var modalEl = document.getElementById('contracts-modal');
    if (!modalEl || !window.bootstrap) return;
    var dlg = modalEl.querySelector('.modal-dialog');
    if (dlg) {
      dlg.classList.remove('modal-sm', 'modal-lg', 'modal-xl');
      var sizeEl = modalEl.querySelector('[data-modal-size]');
      if (sizeEl) dlg.classList.add('modal-' + sizeEl.dataset.modalSize);
    }
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  function openModal(url) {
    var target = document.querySelector('#contracts-modal .modal-content');
    if (!url || !target) return Promise.resolve();
    return htmx.ajax('GET', url, target).then(function() {
      showContractsModal();
    });
  }

  function refreshDraftsPane() {
    var root = pane();
    if (!root) return Promise.resolve();
    var refreshUrl = root.getAttribute('hx-get') || root.dataset.refreshUrl;
    if (!refreshUrl) return Promise.resolve();
    return htmx.ajax('GET', refreshUrl, { target: '#contracts-drafts-pane', swap: 'innerHTML' });
  }

  function postSequential(urls) {
    var csrftoken = getCookie('csrftoken');
    return urls.reduce(function(chain, url) {
      return chain.then(function() {
        return fetch(url, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken, 'HX-Request': 'true' },
        }).then(function(response) {
          if (!response.ok) {
            throw new Error('Операция не выполнена.');
          }
        });
      });
    }, Promise.resolve());
  }

  function restoreSelection(ids) {
    var selected = {};
    (ids || []).forEach(function(id) { selected[String(id)] = true; });
    getRowChecks().forEach(function(box) { box.checked = !!selected[String(box.value)]; });
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
  }

  function setDroidMonoCellValue(cell, value) {
    if (!cell) return;
    cell.textContent = '';
    if (!value) return;
    var span = document.createElement('span');
    span.className = 'clf-id-droid-mono';
    span.textContent = value;
    cell.appendChild(span);
  }

  function getDraftOrderIds() {
    var root = pane();
    return qa('#contracts-drafts-table tbody tr[data-row-order-id]', root)
      .map(function(row) { return String(row.dataset.rowOrderId || ''); })
      .filter(Boolean);
  }

  function syncDraftNumberGroups() {
    var root = pane();
    var rows = qa('#contracts-drafts-table tbody tr[data-project-id]', root);
    rows.forEach(function(row, index) {
      var number = String(row.dataset.number || '');
      var previous = rows[index - 1] || null;
      var next = rows[index + 1] || null;
      var isContinuation = !!previous && String(previous.dataset.number || '') === number;
      var hasNext = !!next && String(next.dataset.number || '') === number;
      var numberCell = row.querySelector('td[data-col="number"]');
      var tkpCell = row.querySelector('td[data-col="tkp-id"]');
      if (numberCell) numberCell.textContent = isContinuation ? '' : number;
      setDroidMonoCellValue(tkpCell, isContinuation ? '' : String(row.dataset.tkpId || ''));
      row.classList.toggle('contracts-drafts-number-continuation', isContinuation);
      row.classList.toggle('contracts-drafts-number-has-next', hasNext);
      row.classList.toggle('contracts-drafts-number-contract-has-next', hasNext);
    });
  }

  function applyDraftOrderToPaymentSchedule(orderIds) {
    var root = pane();
    var table = root && root.querySelector('#contracts-payment-schedule-table');
    var tbody = table && table.querySelector('tbody');
    if (!tbody) return;
    var rowsById = {};
    qa('tr[data-project-id]', tbody).forEach(function(row) {
      var projectId = String(row.dataset.projectId || '');
      if (!rowsById[projectId]) rowsById[projectId] = [];
      rowsById[projectId].push(row);
    });
    orderIds.forEach(function(projectId) {
      (rowsById[String(projectId)] || []).forEach(function(row) {
        tbody.appendChild(row);
      });
    });
  }

  function syncPaymentScheduleNumberGroups() {
    var root = pane();
    var rows = qa('#contracts-payment-schedule-table tbody tr[data-project-id]', root);
    rows.forEach(function(row, index) {
      var projectId = String(row.dataset.projectId || '');
      var number = String(row.dataset.number || '');
      var previous = rows[index - 1] || null;
      var next = rows[index + 1] || null;
      var isFirstForRegistration = !previous || String(previous.dataset.projectId || '') !== projectId;
      var hasNextForRegistration = !!next && String(next.dataset.projectId || '') === projectId;
      var isNumberContinuation = !!previous && String(previous.dataset.number || '') === number;
      var hasNextForNumber = !!next && String(next.dataset.number || '') === number;
      var numberCell = row.querySelector('td[data-col="number"]');
      var tkpCell = row.querySelector('td[data-col="tkp-id"]');
      if (numberCell) numberCell.textContent = isNumberContinuation ? '' : number;
      setDroidMonoCellValue(tkpCell, isNumberContinuation ? '' : String(row.dataset.tkpId || ''));
      row.classList.toggle('contracts-payment-number-has-next', hasNextForNumber);
      row.classList.toggle('contracts-payment-number-contract-has-next', hasNextForNumber && !hasNextForRegistration);
      row.classList.toggle('contracts-payment-stage-has-next', hasNextForRegistration);
      row.classList.toggle('contracts-payment-stage-continuation', !isFirstForRegistration || isNumberContinuation);
    });
  }

  function syncDraftRelatedTablesOrder() {
    var orderIds = getDraftOrderIds();
    if (!orderIds.length) return;
    applyDraftOrderToPaymentSchedule(orderIds);
    syncDraftNumberGroups();
    syncPaymentScheduleNumberGroups();
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
    scheduleDraftTableScrollGapsUpdate();
  }

  function moveDraftSelectionImmediately(action, checked) {
    if (
      !(action === 'up' || action === 'down') ||
      !window.__queuedRowOrder ||
      typeof window.__queuedRowOrder.moveSelection !== 'function'
    ) {
      return false;
    }
    var root = pane();
    if (!root) return false;
    return !!window.__queuedRowOrder.moveSelection(root, action, {
      selectionName: 'contracts-draft-select',
      selectedIds: checked.map(function(box) { return String(box.value); }),
      onAfterMove: syncDraftRelatedTablesOrder,
    });
  }

  function updateDraftTableScrollGaps() {
    qa('#contracts-drafts-pane .contracts-drafts-table-wrap, #contracts-drafts-pane .contracts-payment-schedule-table-wrap', document).forEach(function(wrap) {
      wrap.classList.toggle('has-horizontal-scroll', wrap.scrollWidth > wrap.clientWidth + 1);
    });
  }

  function scheduleDraftTableScrollGapsUpdate() {
    window.requestAnimationFrame(updateDraftTableScrollGaps);
  }

  function updateContractFinalReportPercent(form) {
    if (!form) return;
    var advanceInput = form.querySelector('[name="advance_percent"]');
    var preliminaryInput = form.querySelector('[name="preliminary_report_percent"]');
    var finalInput = form.querySelector('[name="final_report_percent"]');
    if (!advanceInput || !preliminaryInput || !finalInput) return;
    var advance = parseFloat(String(advanceInput.value || '0').replace(',', '.')) || 0;
    var preliminary = parseFloat(String(preliminaryInput.value || '0').replace(',', '.')) || 0;
    var finalValue = 100 - advance - preliminary;
    finalInput.value = Number.isFinite(finalValue) ? finalValue.toFixed(2).replace(/\.00$/, '') : '';
  }

  document.addEventListener('click', function(e) {
    [CONTRACTS_DRAFTS_COLPICKER, CONTRACTS_PAYMENT_COLPICKER].forEach(function(cfg) {
      var colPickerWrap = document.getElementById(cfg.wrapId);
      var colPickerMenu = document.getElementById(cfg.menuId);
      if (colPickerWrap && colPickerMenu && !colPickerWrap.contains(e.target)) {
        colPickerMenu.classList.remove('show');
        colPickerMenu.style.maxHeight = '';
        var header = colPickerWrap.closest('.table-section-header');
        if (header) header.classList.remove('tkp-colpicker-open');
      }
    });

    var root = pane();
    if (!root) return;

    var createBtn = e.target.closest('#contracts-drafts-create-btn');
    if (createBtn && root.contains(createBtn)) {
      openModal(createBtn.dataset.url);
      return;
    }

    var paymentQuickEdit = e.target.closest('.contracts-payment-quick-edit');
    if (paymentQuickEdit && root.contains(paymentQuickEdit)) {
      var paymentRow = paymentQuickEdit.closest('tr');
      openModal(paymentRow && paymentRow.dataset.editUrl);
      return;
    }

    var panelBtn = e.target.closest('#contracts-drafts-actions button[data-panel-action]');
    if (!panelBtn || !root.contains(panelBtn)) return;

    var checked = getChecked();
    if (!checked.length) return;
    window.__contractsDraftSel = checked.map(function(box) { return String(box.value); });

    var action = panelBtn.dataset.panelAction;
    if (action === 'edit') {
      var tr = checked[0].closest('tr');
      openModal(tr && tr.dataset.editUrl);
      return;
    }

    if (action === 'delete') {
      if (!confirm('Удалить ' + checked.length + ' строк(у/и)?')) return;
      var urls = checked.map(function(box) {
        var tr = box.closest('tr');
        return tr && tr.dataset.deleteUrl;
      }).filter(Boolean);
      postSequential(urls)
        .then(function() { return refreshDraftsPane(); })
        .catch(function(err) { alert(err.message || 'Не удалось удалить строки.'); });
      return;
    }

    if (action === 'up' || action === 'down') {
      var selectedIds = checked.map(function(box) { return String(box.value); });
      if (moveDraftSelectionImmediately(action, checked)) return;

      var urls = checked.map(function(box) {
        var tr = box.closest('tr');
        return tr && tr.dataset[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'];
      }).filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      postSequential(urls)
        .then(function() { return refreshDraftsPane(); })
        .then(function() { restoreSelection(selectedIds); })
        .catch(function(err) { alert(err.message || 'Не удалось изменить порядок строк.'); });
    }
  });

  document.body.addEventListener('queued-row-order:conflict', function(e) {
    var root = pane();
    var detail = e.detail || {};
    var table = detail.table;
    if (!root || !table || !root.contains(table)) return;
    window.__contractsDraftSel = getChecked().map(function(box) { return String(box.value); });
    refreshDraftsPane().catch(function() {});
  });

  document.addEventListener('change', function(e) {
    var root = pane();
    if (!root) return;

    var master = e.target.closest('#contracts-drafts-master');
    if (master && root.contains(master)) {
      getRowChecks().forEach(function(box) { box.checked = master.checked; });
      master.indeterminate = false;
      updateMasterState();
      updateRowHighlight();
      ensureActionsVisibility();
      scheduleDraftTableScrollGapsUpdate();
      return;
    }

    var rowCb = e.target.closest('tbody input.form-check-input[name="contracts-draft-select"]');
    if (rowCb && root.contains(rowCb)) {
      updateMasterState();
      updateRowHighlight();
      ensureActionsVisibility();
      scheduleDraftTableScrollGapsUpdate();
    }
  });

  document.addEventListener('input', function(e) {
    if (!e.target.matches('#contracts-modal [name="advance_percent"], #contracts-modal [name="preliminary_report_percent"]')) return;
    updateContractFinalReportPercent(e.target.closest('form'));
  });

  document.body.addEventListener('htmx:afterSettle', function(e) {
    if (!(e.target && e.target.id === 'contracts-drafts-pane')) return;
    initColumnPickers();
    var ids = window.__contractsDraftSel || [];
    restoreSelection(ids);
    window.__contractsDraftSel = [];
    scheduleDraftTableScrollGapsUpdate();
  });

  document.body.addEventListener('htmx:afterSwap', function(e) {
    if (!(e.target instanceof Element)) return;
    if (!e.target.closest('#contracts-modal .modal-content')) return;
    updateContractFinalReportPercent(e.target.querySelector('form'));
  });

  document.addEventListener('DOMContentLoaded', function() {
    initColumnPickers();
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
    scheduleDraftTableScrollGapsUpdate();
  });

  window.addEventListener('resize', function() {
    scheduleDraftTableScrollGapsUpdate();
  });
})();


/* -----------------------------------------------------------------------
   Signing table ("Подписание договора") panel
   ----------------------------------------------------------------------- */
(function () {
  if (window.__signingPanelBound) return;
  window.__signingPanelBound = true;

  function pane() { return document.getElementById('contracts-pane'); }
  var qa = function(sel, root) { return Array.from((root || document).querySelectorAll(sel)); };

  function getSigningChecks() {
    return qa('tbody input.form-check-input[name="signing-row-select"]', pane());
  }
  function getSigningActiveChecks() {
    return getSigningChecks().filter(function(b) {
      var tr = b.closest('tr');
      return tr && !tr.classList.contains('d-none') && !b.disabled;
    });
  }
  function getSigningChecked() {
    return getSigningActiveChecks().filter(function(b) { return b.checked; });
  }
  function updateSigningHighlight() {
    getSigningChecks().forEach(function(b) {
      var tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updateSigningMaster() {
    var boxes = getSigningActiveChecks();
    var master = pane() && pane().querySelector('#signing-master');
    if (!master) return;
    var checkedCount = boxes.filter(function(b) { return b.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }
  function updateSigningEditBtn() {
    var root = pane();
    if (!root) return;
    var checked = getSigningChecked();
    var btn = root.querySelector('#signing-edit-btn');
    if (btn) btn.disabled = checked.length !== 1;
    var signContractBtn = root.querySelector('#signing-sign-contract-btn');
    if (signContractBtn) {
      var selectedSigningRow = checked.length === 1 ? checked[0].closest('tr') : null;
      var expertRequiresSent = signContractBtn.dataset.expertRequiresContractSent === '1';
      var anySentForExpert = signContractBtn.dataset.expertHasContractSent === '1';
      var selectedSentForExpert = selectedSigningRow && selectedSigningRow.dataset.contractSent === '1';
      var sentForExpert = !expertRequiresSent || (selectedSigningRow ? selectedSentForExpert : anySentForExpert);
      if (expertRequiresSent) {
        signContractBtn.classList.toggle('d-none', !sentForExpert);
        signContractBtn.classList.toggle('d-flex', !!sentForExpert);
      }
      var signEnabled = checked.length === 1
        && selectedSigningRow
        && selectedSigningRow.dataset.contractSignReady === '1'
        && (!expertRequiresSent || !!selectedSentForExpert);
      signContractBtn.disabled = !signEnabled;
    }
    var sendBtn = root.querySelector('#signing-send-scan-btn');
    if (sendBtn) {
      var enabled = checked.length === 1
        && checked[0].closest('tr') && checked[0].closest('tr').dataset.hasScan === '1';
      sendBtn.disabled = !enabled;
    }
    var returnBtn = root.querySelector('#signing-return-contract-btn');
    if (returnBtn) returnBtn.disabled = checked.length !== 1;
  }

  function showContractsModal() {
    var modalEl = document.getElementById('contracts-modal');
    if (!modalEl || !window.bootstrap) return;
    var dlg = modalEl.querySelector('.modal-dialog');
    if (dlg) {
      dlg.classList.remove('modal-sm', 'modal-lg', 'modal-xl');
      var sizeEl = modalEl.querySelector('[data-modal-size]');
      if (sizeEl) dlg.classList.add('modal-' + sizeEl.dataset.modalSize);
    }
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  function refreshContractsPane() {
    var contractsPane = document.getElementById('contracts-pane');
    if (!contractsPane || !window.htmx) return;
    var refreshUrl = contractsPane.getAttribute('hx-get') || contractsPane.dataset.refreshUrl;
    if (refreshUrl) {
      htmx.ajax('GET', refreshUrl, { target: '#contracts-pane', swap: 'innerHTML' });
    }
  }

  function openReturnCommentModal(url) {
    var target = document.querySelector('#contracts-modal .modal-content');
    if (!url || !target || !window.htmx) return;
    htmx.ajax('GET', url, target).then(function() {
      showContractsModal();
      var thread = target.querySelector('.contract-return-comment-thread');
      if (thread) thread.scrollTop = thread.scrollHeight;
    });
  }

  function updateReturnCommentDom(payload) {
    var performerId = String(payload.performerId || '');
    if (!performerId) return;
    var wrapper = document.getElementById('contract-return-comment-' + performerId);
    if (!wrapper) return;
    var lawyerCount = Number(payload.lawyerCount || 0);
    var expertCount = Number(payload.expertCount || 0);
    var lawyerCounter = wrapper.querySelector('.chk-comment-counter--lawyer');
    var expertCounter = wrapper.querySelector('.chk-comment-counter--expert');
    if (lawyerCounter) {
      lawyerCounter.textContent = lawyerCount ? String(lawyerCount) : '';
      lawyerCounter.classList.toggle('has-comments', lawyerCount > 0);
    }
    if (expertCounter) {
      expertCounter.textContent = expertCount ? String(expertCount) : '';
      expertCounter.classList.toggle('has-comments', expertCount > 0);
    }
    var icon = wrapper.querySelector('.contract-return-comment-trigger i');
    if (icon) {
      var hasAnyComment = lawyerCount > 0 || expertCount > 0;
      icon.className = 'bi ' + (hasAnyComment ? 'bi-chat-left-text-fill' : 'bi-chat-left text-muted');
      if (payload.lastRole === 'lawyer') icon.classList.add('contract-return-icon--lawyer');
      if (payload.lastRole === 'expert') icon.classList.add('contract-return-icon--expert');
    }
  }

  function refreshSigning() {
    updateSigningMaster();
    updateSigningHighlight();
    updateSigningEditBtn();
  }

  document.addEventListener('click', function(e) {
    var root = pane(); if (!root) return;

    var editBtn = e.target.closest('#signing-edit-btn');
    if (editBtn && root.contains(editBtn)) {
      var checked = getSigningChecked();
      if (!checked.length) return;
      var tr = checked[0].closest('tr');
      var url = tr && tr.dataset.signingEditUrl;
      if (!url) return;
      var target = document.querySelector('#contracts-modal .modal-content');
      if (!target) return;
      htmx.ajax('GET', url, target).then(function() {
        showContractsModal();
      });
      updateSigningEditBtn();
      return;
    }

    var signContractBtn = e.target.closest('#signing-sign-contract-btn');
    if (signContractBtn && root.contains(signContractBtn)) {
      var checkedForSign = getSigningChecked();
      if (checkedForSign.length !== 1 || signContractBtn.disabled) return;
      var signUrl = signContractBtn.dataset.url;
      if (!signUrl) return;

      var signFd = new FormData();
      signFd.append('performer_ids[]', checkedForSign[0].value);

      var originalHtml = signContractBtn.innerHTML;
      signContractBtn.disabled = true;
      signContractBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Подписание...';
      fetch(signUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
        body: signFd,
      }).then(function(resp) {
        return resp.json().then(function(data) {
          if (!resp.ok || !data.ok) {
            throw new Error(data && data.error ? data.error : 'Не удалось подписать договор.');
          }
          return data;
        });
      }).then(function(data) {
        htmx.trigger(document.body, 'contracts-updated');
        htmx.trigger(document.body, 'notifications-updated');
        if (data.warnings && data.warnings.length) {
          alert((data.message || 'Подписанный договор сформирован.') + '\n\n' + data.warnings.join('\n'));
        }
      }).catch(function(err) {
        alert(err.message || 'Ошибка сети при подписании договора.');
      }).finally(function() {
        signContractBtn.innerHTML = originalHtml;
        updateSigningEditBtn();
      });
      return;
    }

    var returnBtn = e.target.closest('#signing-return-contract-btn');
    if (returnBtn && root.contains(returnBtn)) {
      var checkedForReturn = getSigningChecked();
      if (checkedForReturn.length !== 1 || returnBtn.disabled) return;
      var returnRow = checkedForReturn[0].closest('tr');
      openReturnCommentModal(returnRow && returnRow.dataset.returnCommentUrl);
      return;
    }

    var returnCommentTrigger = e.target.closest('[data-contract-return-comment-trigger]');
    if (returnCommentTrigger && root.contains(returnCommentTrigger)) {
      e.preventDefault();
      openReturnCommentModal(returnCommentTrigger.dataset.url);
      return;
    }

    var sendScanBtn = e.target.closest('#signing-send-scan-btn');
    if (sendScanBtn && root.contains(sendScanBtn)) {
      var checked = getSigningChecked();
      if (!checked.length) return;
      var url = sendScanBtn.dataset.url;
      if (!url) return;
      sendScanBtn.disabled = true;
      var fd = new FormData();
      checked.forEach(function(cb) { fd.append('performer_ids[]', cb.value); });
      fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
        body: fd,
      }).then(function(resp) {
        return resp.json();
      }).then(function(data) {
        if (data.ok) {
          htmx.trigger(document.body, 'contracts-updated');
          htmx.trigger(document.body, 'notifications-updated');
          refreshContractsPane();
        } else {
          alert(data.error || 'Ошибка при отправке скана.');
        }
      }).catch(function() {
        alert('Ошибка сети при отправке скана.');
      }).finally(function() {
        updateSigningEditBtn();
      });
      return;
    }
  });

  document.body.addEventListener('contracts:return-comment-updated', function(event) {
    var payload = (event.detail && (event.detail.value || event.detail)) || {};
    updateReturnCommentDom(payload);
    var modalRoot = document.querySelector('#contracts-modal [data-contract-return-modal-root]');
    if (!modalRoot || String(modalRoot.dataset.performerId || '') !== String(payload.performerId || '')) return;
    var lawyerCount = Number(payload.lawyerCount || 0);
    var expertCount = Number(payload.expertCount || 0);
    var lawyerTotal = document.querySelector('#contracts-modal [data-contract-return-total-lawyer]');
    var expertTotal = document.querySelector('#contracts-modal [data-contract-return-total-expert]');
    if (lawyerTotal) {
      lawyerTotal.textContent = lawyerCount ? String(lawyerCount) : '';
      lawyerTotal.classList.toggle('has-comments', lawyerCount > 0);
    }
    if (expertTotal) {
      expertTotal.textContent = expertCount ? String(expertCount) : '';
      expertTotal.classList.toggle('has-comments', expertCount > 0);
    }
  });

  document.addEventListener('htmx:afterRequest', function(event) {
    var form = event.target && event.target.closest && event.target.closest('.contract-return-comment-compose');
    if (!form || !event.detail.successful) return;
    var textarea = form.querySelector('textarea[name="value"]');
    if (textarea) {
      textarea.value = '';
      textarea.focus();
    }
    var thread = document.querySelector('#contracts-modal .contract-return-comment-thread');
    if (thread) thread.scrollTop = thread.scrollHeight;
  });

  document.addEventListener('click', function(event) {
    var submitBtn = event.target.closest('[data-contract-return-submit]');
    if (!submitBtn) return;
    var modalRoot = submitBtn.closest('[data-contract-return-modal-root]');
    if (!modalRoot || submitBtn.disabled) return;
    var returnUrl = modalRoot.dataset.returnUrl;
    if (!returnUrl) return;

    var originalHtml = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Возврат...';
    fetch(returnUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
    }).then(function(resp) {
      return resp.json().then(function(data) {
        if (!resp.ok || !data.ok) {
          throw new Error(data && data.error ? data.error : 'Не удалось вернуть договор.');
        }
        return data;
      });
    }).then(function() {
      var modalEl = document.getElementById('contracts-modal');
      if (modalEl && window.bootstrap) {
        bootstrap.Modal.getOrCreateInstance(modalEl).hide();
      }
      htmx.trigger(document.body, 'contracts-updated');
      htmx.trigger(document.body, 'notifications-updated');
      refreshContractsPane();
    }).catch(function(err) {
      alert(err.message || 'Ошибка сети при возврате договора.');
    }).finally(function() {
      submitBtn.innerHTML = originalHtml;
      submitBtn.disabled = false;
      refreshSigning();
    });
  });

  function getCookie(name) {
    var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }

  document.addEventListener('change', function(e) {
    var root = pane(); if (!root) return;

    var master = e.target.closest('#signing-master');
    if (master && root.contains(master)) {
      getSigningActiveChecks().forEach(function(b) { b.checked = master.checked; });
      master.indeterminate = false;
      refreshSigning();
      return;
    }

    var rowCb = e.target.closest('tbody input.form-check-input[name="signing-row-select"]');
    if (rowCb && root.contains(rowCb)) {
      refreshSigning();
      return;
    }

    function handleScanUpload(inputEl, fieldName) {
      var file = inputEl.files && inputEl.files[0];
      if (!file) return;
      var url = inputEl.dataset.uploadUrl;
      if (!url) return;

      var tr = inputEl.closest('tr');
      var rowCb = tr && tr.querySelector('input[name="signing-row-select"]');
      if (rowCb && !rowCb.disabled && !rowCb.checked) {
        rowCb.checked = true;
        refreshSigning();
      }
      var checkedPerformerIds = getSigningChecked().map(function(b) { return b.value; });

      var modalEl = document.getElementById('scan-upload-progress-modal');
      var progressBar = document.getElementById('scan-upload-progress-bar');
      var statusEl = document.getElementById('scan-upload-status');
      var closeBtn = document.getElementById('scan-upload-close-btn');
      var uploadSucceeded = false;
      if (progressBar) progressBar.style.width = '0%';
      if (statusEl) statusEl.textContent = '';
      if (closeBtn) closeBtn.disabled = true;
      if (modalEl && window.bootstrap) {
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
      }

      var fd = new FormData();
      fd.append(fieldName, file);
      var xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));
      xhr.upload.addEventListener('progress', function(ev) {
        if (ev.lengthComputable && progressBar) {
          var pct = Math.round(ev.loaded / ev.total * 100);
          progressBar.style.width = pct + '%';
        }
      });
      xhr.addEventListener('load', function() {
        if (progressBar) progressBar.style.width = '100%';
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            var data = JSON.parse(xhr.responseText);
            if (data.ok && data.scan_name && statusEl) {
              uploadSucceeded = true;
              var storageLabel = data.storage_label || 'облачное хранилище';
              var icon = document.createElement('i');
              icon.className = 'bi bi-check-circle me-1';
              var span = document.createElement('span');
              span.className = 'text-success';
              span.appendChild(icon);
              span.appendChild(document.createTextNode(
                'Документ успешно загружен на ' + storageLabel + ' в папку с проектом договора и переименован в \u00ab'
                + data.scan_name + '\u00bb.'));
              statusEl.textContent = '';
              statusEl.appendChild(span);
            }
          } catch (_) {}
        } else {
          if (statusEl) {
            statusEl.textContent = '';
            var errSpan = document.createElement('span');
            errSpan.className = 'text-danger';
            errSpan.textContent = 'Ошибка при загрузке файла.';
            statusEl.appendChild(errSpan);
          }
        }
        if (closeBtn) closeBtn.disabled = false;
      });
      xhr.addEventListener('error', function() {
        if (statusEl) {
          statusEl.textContent = '';
          var errSpan = document.createElement('span');
          errSpan.className = 'text-danger';
          errSpan.textContent = 'Ошибка сети при загрузке файла.';
          statusEl.appendChild(errSpan);
        }
        if (closeBtn) closeBtn.disabled = false;
      });
      if (modalEl) {
        modalEl.addEventListener('hidden.bs.modal', function onHidden() {
          modalEl.removeEventListener('hidden.bs.modal', onHidden);
          var contractsPane = document.getElementById('contracts-pane');
          if (contractsPane) {
            var refreshUrl = contractsPane.getAttribute('hx-get') || contractsPane.dataset.refreshUrl;
            if (refreshUrl) {
              htmx.ajax('GET', refreshUrl, { target: '#contracts-pane', swap: 'innerHTML' }).then(function() {
                var set = {};
                if (!uploadSucceeded) {
                  checkedPerformerIds.forEach(function(id) { set[id] = true; });
                }
                getSigningChecks().forEach(function(b) { b.checked = !!set[b.value]; });
                refreshSigning();
              });
            }
          }
        }, { once: true });
      }
      xhr.send(fd);
      inputEl.value = '';
    }

    var scanInput = e.target.closest('.js-scan-upload');
    if (scanInput && root.contains(scanInput)) {
      handleScanUpload(scanInput, 'contract_employee_scan');
      return;
    }

    var signedScanInput = e.target.closest('.js-signed-scan-upload');
    if (signedScanInput && root.contains(signedScanInput)) {
      handleScanUpload(signedScanInput, 'contract_signed_scan_file');
      return;
    }
  });

  document.body.addEventListener('htmx:afterSettle', function(e) {
    var root = pane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    refreshSigning();
  });

  document.body.addEventListener('contracts-project-filter-applied', function() {
    refreshSigning();
  });

  document.addEventListener('DOMContentLoaded', refreshSigning);
})();


/* -----------------------------------------------------------------------
   Contract Templates ("Образцы шаблонов") panel
   ----------------------------------------------------------------------- */
(function () {
  if (window.__ctPanelBound) return;
  window.__ctPanelBound = true;

  window.__ctTableSel = window.__ctTableSel || {};

  function ctPane() { return document.getElementById('contract-templates-pane'); }
  var qa = function(sel, root) { return Array.from((root || document).querySelectorAll(sel)); };

  function getCookie(name) {
    var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  var csrftoken = getCookie('csrftoken');

  var CT_PANELS = {
    'ct-actions': {
      name: 'ct-select',
      modal: '#contract-templates-modal .modal-content',
      modalId: 'contract-templates-modal',
      deleteLabel: 'строк(у/и)',
    },
    'ctv-actions': {
      name: 'ctv-select',
      modal: '#contract-templates-modal .modal-content',
      modalId: 'contract-templates-modal',
      deleteLabel: 'переменных',
    },
  };

  function getRowChecksByName(name) {
    var root = ctPane();
    if (!root) return [];
    return qa('tbody input.form-check-input[name="' + name + '"]', root);
  }
  function getCheckedByName(name) {
    return getRowChecksByName(name).filter(function(b) { return b.checked; });
  }
  function updateRowHighlightFor(name) {
    getRowChecksByName(name).forEach(function(b) {
      var tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updateMasterStateFor(name) {
    var boxes = getRowChecksByName(name);
    var root = ctPane();
    if (!root) return;
    var master = root.querySelector('input.form-check-input[data-target-name="' + name + '"]');
    if (!master) return;
    var checkedCount = boxes.filter(function(b) { return b.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }
  function findActionsByName(name) {
    var root = ctPane();
    if (!root) return null;
    var master = root.querySelector('input.form-check-input[data-target-name="' + name + '"]');
    if (!master) return null;
    var actionsId = master.getAttribute('data-actions-id') || '';
    if (!actionsId) return null;
    return root.querySelector('#' + actionsId);
  }
  function ensureActionsVisibility(name) {
    var panel = findActionsByName(name);
    if (!panel) return;
    var anyChecked = getRowChecksByName(name).some(function(b) { return b.checked; });
    panel.classList.toggle('d-none', !anyChecked);
  }

  function findPanelConfig(btn) {
    for (var panelId in CT_PANELS) {
      if (btn.closest('#' + panelId)) return CT_PANELS[panelId];
    }
    return null;
  }

  document.addEventListener('click', function(e) {
    var root = ctPane();
    if (!root) return;
    var btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;

    var config = findPanelConfig(btn);
    if (!config) return;

    var action = btn.dataset.panelAction;
    var name = config.name;

    var checked = getCheckedByName(name);
    if (!checked.length) return;

    window.__ctTableSel[name] = checked.map(function(ch) { return String(ch.value); });

    var ctVarsEl = document.getElementById('ct-variables');
    window.__ctVarsOpen = !!(ctVarsEl && ctVarsEl.classList.contains('show'));

    if (action === 'edit') {
      var first = checked[0];
      var tr = first.closest('tr');
      var url = tr && tr.dataset.editUrl;
      if (!url) return;
      htmx.ajax('GET', url, { target: config.modal, swap: 'innerHTML' });
      ensureActionsVisibility(name);
      return;
    }

    if (action === 'delete') {
      if (!confirm('Удалить ' + checked.length + ' ' + config.deleteLabel + '?')) return;
      var urls = checked.map(function(ch) { return ch.closest('tr') && ch.closest('tr').dataset.deleteUrl; }).filter(Boolean);
      (function deleteSequential(i) {
        if (i >= urls.length) return;
        fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } })
          .catch(function() {})
          .then(function() {
            if (i < urls.length - 1) {
              deleteSequential(i + 1);
            } else {
              htmx.trigger(document.body, 'contract-templates-updated');
            }
          });
      })(0);
      return;
    }

    if (action === 'up' || action === 'down') {
      var moveUrls = checked
        .map(function(ch) {
          var t = ch.closest('tr');
          return t && t.dataset[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'];
        })
        .filter(Boolean);
      if (action === 'down') moveUrls = moveUrls.reverse();
      (function moveSequential(i) {
        if (i >= moveUrls.length) return;
        fetch(moveUrls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } })
          .catch(function() {})
          .then(function() {
            if (i < moveUrls.length - 1) {
              moveSequential(i + 1);
            } else {
              htmx.trigger(document.body, 'contract-templates-updated');
            }
          });
      })(0);
      return;
    }
  });

  document.addEventListener('change', function(e) {
    var root = ctPane();
    if (!root) return;
    var master = e.target.closest('input.form-check-input[data-actions-id][data-target-name]');
    if (master && root.contains(master)) {
      var name = master.dataset.targetName;
      var boxes = getRowChecksByName(name);
      boxes.forEach(function(b) { b.checked = master.checked; });
      master.indeterminate = false;
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
      return;
    }
    var rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (rowCb && root.contains(rowCb)) {
      var cbName = rowCb.name;
      updateMasterStateFor(cbName);
      updateRowHighlightFor(cbName);
      ensureActionsVisibility(cbName);
      return;
    }
  });

  document.body.addEventListener('htmx:beforeRequest', function(e) {
    var tgt = e.detail && e.detail.target;
    if (tgt && tgt.id === 'contract-templates-pane') {
      var v = document.getElementById('ct-variables');
      if (v && v.classList.contains('show')) window.__ctVarsOpen = true;
    }
  });

  document.body.addEventListener('htmx:afterSettle', function(e) {
    if (!(e.target && e.target.id === 'contract-templates-pane')) return;
    var sel = window.__ctTableSel || {};
    for (var name in sel) {
      var ids = sel[name] || [];
      var set = {};
      ids.forEach(function(id) { set[id] = true; });
      getRowChecksByName(name).forEach(function(b) { b.checked = !!set[String(b.value)]; });
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
    }
    window.__ctTableSel = {};
    if (window.__ctVarsOpen) {
      var ctVars = document.getElementById('ct-variables');
      if (ctVars) ctVars.classList.add('show');
      clearTimeout(window.__ctVarsOpenTimer);
      window.__ctVarsOpenTimer = setTimeout(function() { window.__ctVarsOpen = false; }, 1000);
    }
  });
})();


/* -----------------------------------------------------------------------
   Field Parameters / Contract Subject ("Предмет договора") panel
   ----------------------------------------------------------------------- */
(function () {
  if (window.__fpPanelBound) return;
  window.__fpPanelBound = true;

  window.__fpTableSel = window.__fpTableSel || {};

  function fpPane() { return document.getElementById('field-params-pane'); }
  var qa = function(sel, root) { return Array.from((root || document).querySelectorAll(sel)); };

  function getCookie(name) {
    var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  var csrftoken = getCookie('csrftoken');

  var FP_PANELS = {
    'cs-actions': {
      name: 'cs-select',
      modal: '#field-params-modal .modal-content',
      modalId: 'field-params-modal',
      deleteLabel: 'строк(у/и)',
    },
  };

  function getRowChecksByName(name) {
    var root = fpPane();
    if (!root) return [];
    return qa('tbody input.form-check-input[name="' + name + '"]', root);
  }
  function getCheckedByName(name) {
    return getRowChecksByName(name).filter(function(b) { return b.checked; });
  }
  function updateRowHighlightFor(name) {
    getRowChecksByName(name).forEach(function(b) {
      var tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updateMasterStateFor(name) {
    var boxes = getRowChecksByName(name);
    var root = fpPane();
    if (!root) return;
    var master = root.querySelector('input.form-check-input[data-target-name="' + name + '"]');
    if (!master) return;
    var checkedCount = boxes.filter(function(b) { return b.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }
  function findActionsByName(name) {
    var root = fpPane();
    if (!root) return null;
    var master = root.querySelector('input.form-check-input[data-target-name="' + name + '"]');
    if (!master) return null;
    var actionsId = master.getAttribute('data-actions-id') || '';
    if (!actionsId) return null;
    return root.querySelector('#' + actionsId);
  }
  function ensureActionsVisibility(name) {
    var panel = findActionsByName(name);
    if (!panel) return;
    var anyChecked = getRowChecksByName(name).some(function(b) { return b.checked; });
    panel.classList.toggle('d-none', !anyChecked);
  }

  function findPanelConfig(btn) {
    for (var panelId in FP_PANELS) {
      if (btn.closest('#' + panelId)) return FP_PANELS[panelId];
    }
    return null;
  }

  document.addEventListener('click', function(e) {
    var root = fpPane();
    if (!root) return;
    var btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;

    var config = findPanelConfig(btn);
    if (!config) return;

    var action = btn.dataset.panelAction;
    var name = config.name;

    var checked = getCheckedByName(name);
    if (!checked.length) return;

    window.__fpTableSel[name] = checked.map(function(ch) { return String(ch.value); });

    if (action === 'edit') {
      var first = checked[0];
      var tr = first.closest('tr');
      var url = tr && tr.dataset.editUrl;
      if (!url) return;
      htmx.ajax('GET', url, { target: config.modal, swap: 'innerHTML' }).then(function() {
        var modalEl = document.getElementById(config.modalId);
        if (modalEl && window.bootstrap) {
          window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
      });
      ensureActionsVisibility(name);
      return;
    }

    if (action === 'delete') {
      if (!confirm('Удалить ' + checked.length + ' ' + config.deleteLabel + '?')) return;
      var urls = checked.map(function(ch) { return ch.closest('tr') && ch.closest('tr').dataset.deleteUrl; }).filter(Boolean);
      (function deleteSequential(i) {
        if (i >= urls.length) return;
        fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } })
          .catch(function() {})
          .then(function() {
            if (i < urls.length - 1) {
              deleteSequential(i + 1);
            } else {
              htmx.trigger(document.body, 'field-params-updated');
            }
          });
      })(0);
      return;
    }

    if (action === 'up' || action === 'down') {
      var moveUrls = checked
        .map(function(ch) {
          var t = ch.closest('tr');
          return t && t.dataset[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'];
        })
        .filter(Boolean);
      if (action === 'down') moveUrls = moveUrls.reverse();
      (function moveSequential(i) {
        if (i >= moveUrls.length) return;
        fetch(moveUrls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } })
          .catch(function() {})
          .then(function() {
            if (i < moveUrls.length - 1) {
              moveSequential(i + 1);
            } else {
              htmx.trigger(document.body, 'field-params-updated');
            }
          });
      })(0);
      return;
    }
  });

  document.addEventListener('change', function(e) {
    var root = fpPane();
    if (!root) return;
    var master = e.target.closest('input.form-check-input[data-actions-id][data-target-name]');
    if (master && root.contains(master)) {
      var name = master.dataset.targetName;
      var boxes = getRowChecksByName(name);
      boxes.forEach(function(b) { b.checked = master.checked; });
      master.indeterminate = false;
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
      return;
    }
    var rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (rowCb && root.contains(rowCb)) {
      var cbName = rowCb.name;
      updateMasterStateFor(cbName);
      updateRowHighlightFor(cbName);
      ensureActionsVisibility(cbName);
      return;
    }
  });

  document.body.addEventListener('htmx:afterSettle', function(e) {
    if (!(e.target && e.target.id === 'field-params-pane')) return;
    var sel = window.__fpTableSel || {};
    for (var name in sel) {
      var ids = sel[name] || [];
      var set = {};
      ids.forEach(function(id) { set[id] = true; });
      getRowChecksByName(name).forEach(function(b) { b.checked = !!set[String(b.value)]; });
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
    }
    window.__fpTableSel = {};
  });
})();
