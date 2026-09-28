(function () {
  if (window.__performersPanelBound) return;
  window.__performersPanelBound = true;

  window.__tableSel = window.__tableSel || {};
  window.__tableSelLast = window.__tableSelLast || null;

  var P = window.UIPref;
  if (P) {
    window.__participationSectionCollapsed = P.get('perf:partSectionCollapsed', false);
    window.__participationAssetCollapsed = P.get('perf:partAssetCollapsed', false);
    window.__contractSectionCollapsed = P.get('perf:contrSectionCollapsed', false);
    window.__contractAssetCollapsed = P.get('perf:contrAssetCollapsed', false);
    window.__infoRequestSectionCollapsed = P.get('perf:irSectionCollapsed', false);
    window.__infoRequestAssetCollapsed = P.get('perf:irAssetCollapsed', false);
  }
  function saveCollapsePrefs() {
    if (!P) return;
    P.set('perf:partSectionCollapsed', !!window.__participationSectionCollapsed);
    P.set('perf:partAssetCollapsed', !!window.__participationAssetCollapsed);
    P.set('perf:contrSectionCollapsed', !!window.__contractSectionCollapsed);
    P.set('perf:contrAssetCollapsed', !!window.__contractAssetCollapsed);
    P.set('perf:irSectionCollapsed', !!window.__infoRequestSectionCollapsed);
    P.set('perf:irAssetCollapsed', !!window.__infoRequestAssetCollapsed);
  }

  function syncCollapseButtons() {
    var root = document.getElementById('performers-pane');
    var contractRoot = contractPane();
    var pairs = [
      ['#participation-confirmation-section', '#participation-asset-toggle', window.__participationAssetCollapsed],
      ['#participation-confirmation-section', '#participation-section-toggle', window.__participationSectionCollapsed],
      ['#info-request-approval-section', '#info-request-asset-toggle', window.__infoRequestAssetCollapsed],
      ['#info-request-approval-section', '#info-request-section-toggle', window.__infoRequestSectionCollapsed],
    ];
    pairs.forEach(function(p) {
      if (!root) return;
      var section = root.querySelector(p[0]);
      if (!section) return;
      var btn = section.querySelector(p[1]);
      if (!btn) return;
      var active = !!p[2];
      btn.classList.toggle('active', active);
      var icon = btn.querySelector('i');
      if (icon) icon.className = active ? 'bi bi-arrows-expand' : 'bi bi-arrows-collapse';
    });
    [
      ['#contract-asset-toggle', window.__contractAssetCollapsed],
      ['#contract-section-toggle', window.__contractSectionCollapsed],
    ].forEach(function(p) {
      if (!contractRoot) return;
      var section = contractRoot.querySelector('#contract-conclusion-section');
      if (!section) return;
      var btn = section.querySelector(p[0]);
      if (!btn) return;
      var active = !!p[1];
      btn.classList.toggle('active', active);
      var icon = btn.querySelector('i');
      if (icon) icon.className = active ? 'bi bi-arrows-expand' : 'bi bi-arrows-collapse';
    });
  }

  function rememberParticipationCollapseButtonState() {
    var root = pane();
    var section = root ? root.querySelector('#participation-confirmation-section') : null;
    if (!section) return;
    var assetToggle = section.querySelector('#participation-asset-toggle');
    var sectionToggle = section.querySelector('#participation-section-toggle');
    if (assetToggle) {
      window.__participationAssetCollapsed = assetToggle.classList.contains('active');
    }
    if (sectionToggle) {
      window.__participationSectionCollapsed = sectionToggle.classList.contains('active');
    }
    saveCollapsePrefs();
  }

  function pane() { return document.getElementById('performers-pane'); }
  function updatePaymentRequestScrollGaps() {
    qa(
      '#participation-confirmation-section .participation-table-wrap, .payment-request-section .info-request-table-wrap, #info-request-approval-section .info-request-table-wrap, #report-submission-section .report-submission-table-wrap, #report-check-section .report-check-table-wrap, #report-macros-section .report-macros-table-wrap',
      document
    ).forEach(function(wrap) {
      var clipped = getComputedStyle(wrap).overflowX === 'hidden';
      wrap.classList.toggle('has-horizontal-scroll', !clipped && wrap.scrollWidth > wrap.clientWidth + 1);
    });
  }
  function schedulePaymentRequestScrollGapsUpdate() {
    window.requestAnimationFrame(updatePaymentRequestScrollGaps);
  }
  function contractPane() {
    var contractsRoot = document.getElementById('contracts-pane');
    if (contractsRoot && contractsRoot.querySelector('#contract-conclusion-section')) return contractsRoot;
    var performersRoot = pane();
    if (performersRoot && performersRoot.querySelector('#contract-conclusion-section')) return performersRoot;
    return contractsRoot || performersRoot;
  }
  const qa = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  window.getProjectFilterSummaryLabel = window.getProjectFilterSummaryLabel || function(input, fallback) {
    var summary = input && input.dataset ? (input.dataset.summaryLabel || '').trim() : '';
    return summary || fallback;
  };
  window.bindProjectFilterMenuWidth = window.bindProjectFilterMenuWidth || function(dropdown) {
    if (!dropdown || dropdown.dataset.projectMenuWidthBound === '1') return;
    dropdown.dataset.projectMenuWidthBound = '1';
    var menu = dropdown.querySelector('.project-filter-menu');
    if (!menu) return;
    dropdown.addEventListener('shown.bs.dropdown', function() {
      var labels = qa('.form-check-label', menu);
      var widestLabel = labels.reduce(function(maxWidth, item) {
        return Math.max(maxWidth, Math.ceil(item.scrollWidth));
      }, 0);
      if (!widestLabel) return;
      var controlWidth = Math.ceil(dropdown.querySelector('.dropdown-toggle')?.offsetWidth || 200);
      var checkboxWidth = Math.ceil(menu.querySelector('.form-check-input')?.offsetWidth || 18);
      var contentWidth = widestLabel + checkboxWidth + 64;
      menu.style.minWidth = Math.max(controlWidth, 200, contentWidth) + 'px';
    });
  };
  window.bindProjectFilterMenuPortal = window.bindProjectFilterMenuPortal || function(dropdown) {
    if (!dropdown || dropdown.dataset.projectMenuPortalBound === '1') return;
    dropdown.dataset.projectMenuPortalBound = '1';
    var menu = dropdown.querySelector('.project-filter-menu');
    var button = dropdown.querySelector('.dropdown-toggle');
    if (!menu || !button) return;

    var originalParent = null;
    var originalNext = null;

    function placeMenu() {
      if (!menu.classList.contains('show')) return;
      var rect = button.getBoundingClientRect();
      if (!rect.width && !rect.height) return;
      var margin = 8;
      var gap = 2;
      var width = Math.ceil(menu.getBoundingClientRect().width || menu.offsetWidth || 200);
      var left = Math.max(margin, Math.min(rect.left, window.innerWidth - width - margin));
      var top = rect.bottom + gap;

      menu.classList.add('project-filter-menu-portal');
      menu.style.position = 'fixed';
      menu.style.left = left + 'px';
      menu.style.top = top + 'px';
      menu.style.right = 'auto';
      menu.style.bottom = 'auto';
      menu.style.transform = 'none';

      var menuRect = menu.getBoundingClientRect();
      if (menuRect.bottom > window.innerHeight - margin && rect.top > menuRect.height + margin) {
        menu.style.top = Math.max(margin, rect.top - menuRect.height - gap) + 'px';
      }
    }

    function returnMenu() {
      menu.classList.remove('project-filter-menu-portal');
      menu.style.removeProperty('position');
      menu.style.removeProperty('left');
      menu.style.removeProperty('top');
      menu.style.removeProperty('right');
      menu.style.removeProperty('bottom');
      menu.style.removeProperty('transform');
      if (originalParent && menu.parentNode !== originalParent) {
        originalParent.insertBefore(menu, originalNext);
      }
    }

    dropdown.addEventListener('shown.bs.dropdown', function() {
      var instance = window.bootstrap && window.bootstrap.Dropdown.getInstance(button);
      if (instance && instance._popper) {
        instance._popper.destroy();
        instance._popper = null;
      }
      originalParent = menu.parentNode;
      originalNext = menu.nextSibling;
      document.body.appendChild(menu);
      placeMenu();
      requestAnimationFrame(placeMenu);
    });
    dropdown.addEventListener('hidden.bs.dropdown', returnMenu);
    window.addEventListener('resize', placeMenu);
    window.addEventListener('scroll', function(e) {
      if (!menu.classList.contains('show')) return;
      var target = e.target;
      if (target === menu || (target && target.nodeType === 1 && menu.contains(target))) return;
      placeMenu();
    }, true);
  };
  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  const csrftoken = getCookie('csrftoken');

  function cleanupDanglingModalState() {
    if (document.querySelector('.modal.show, .modal.showing')) return;
    document.querySelectorAll('.modal-backdrop').forEach((backdrop) => backdrop.remove());
    document.body.classList.remove('modal-open');
    document.body.style.removeProperty('padding-right');
  }

  function hideModalThen(modalEl, callback) {
    const done = () => {
      cleanupDanglingModalState();
      if (typeof callback === 'function') callback();
    };
    if (!modalEl || !window.bootstrap) {
      done();
      return;
    }
    const modal = window.bootstrap.Modal.getInstance(modalEl) || window.bootstrap.Modal.getOrCreateInstance(modalEl);
    if (!modalEl.classList.contains('show')) {
      done();
      return;
    }
    modalEl.addEventListener('hidden.bs.modal', done, { once: true });
    modal.hide();
  }

  function getSelectionRoot(name) {
    return (name === 'contract-select' || name === 'contract-dispatch-select') ? contractPane() : pane();
  }
  function getRowChecks(name) {
    return qa(`tbody input.form-check-input[name="${name}"]`, getSelectionRoot(name))
      .filter(function(box) { return !box.closest('#performers-modal'); });
  }
  function getChecked(name) {
    return getRowChecks(name).filter(b => b.checked);
  }
  function updateRowHighlight(name) {
    getRowChecks(name).forEach(b => {
      const tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function forgetTableSelection(name) {
    try { delete window.__tableSel[name]; } catch (_) { window.__tableSel[name] = []; }
    if (window.__tableSelLast === name) window.__tableSelLast = null;
  }
  function clearTableSelectionByName(name) {
    getRowChecks(name).forEach(function(checkbox) { checkbox.checked = false; });
    forgetTableSelection(name);
    updateRowHighlight(name);
    if (name === 'performer-select') {
      updatePerformerMasterState();
      ensurePerformerActionsVisibility();
      return;
    }
    if (name === 'report-check-select') {
      updateReportCheckMasterState();
      ensureReportCheckActionsVisibility();
      return;
    }
    if (name === 'report-macro-select') {
      updateReportMacrosMasterState();
      ensureReportMacrosActionsVisibility();
    }
  }
  function updatePerformerMasterState() {
    const boxes = getVisiblePerformerChecks();
    const master = pane()?.querySelector('input.form-check-input[data-actions-id="performers-actions"]');
    if (!master) return;
    const checkedCount = boxes.filter(b => b.checked).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }
  function ensurePerformerActionsVisibility() {
    const panel = pane()?.querySelector('#performers-actions');
    if (!panel) return;
    const any = getVisiblePerformerChecks().some(b => b.checked);
    panel.classList.toggle('d-none', !any);
    panel.classList.toggle('d-flex', any);
    updatePerformerLockedActionButtons(panel);
  }
  function performerRowIsSectionLocked(tr) {
    return !!(tr && tr.dataset.reportSectionLocked === '1');
  }
  function performerRowDeleteLocked(tr) {
    return performerRowIsSectionLocked(tr) || !!(tr && tr.dataset.reportUploadLocked === '1');
  }
  function padPerformerSectionCode(n) {
    return String(n).padStart(2, '0');
  }
  function performerRowIsSectionAccounting(tr) {
    return !!(tr && String(tr.dataset.accountingType || '').trim() === 'Раздел');
  }
  function performerGroupSortKey(tr) {
    const number = parseInt(tr && tr.dataset ? tr.dataset.projectNumber : '0', 10) || 0;
    const stage = String((tr && tr.dataset && tr.dataset.stageUid) || '');
    const asset = String((tr && tr.dataset && tr.dataset.assetName) || '');
    return [number, stage, asset];
  }
  function sortPerformerRowsByProjectAndAsset(table) {
    const rootTable = table || pane()?.querySelector('#performers-main-section table.performers-table');
    const tbody = rootTable && rootTable.querySelector('tbody');
    if (!tbody) return rootTable;
    const rows = Array.from(tbody.querySelectorAll('tr[data-row-order-id]'));
    rows.sort(function (a, b) {
      const ka = performerGroupSortKey(a);
      const kb = performerGroupSortKey(b);
      if (ka[0] !== kb[0]) return kb[0] - ka[0];
      if (ka[1] !== kb[1]) return ka[1] < kb[1] ? -1 : 1;
      if (ka[2] !== kb[2]) return ka[2] < kb[2] ? -1 : 1;
      return 0;
    });
    rows.forEach(function (row) { tbody.appendChild(row); });
    return rootTable;
  }
  function updatePerformerSectionCodes(table) {
    const rootTable = table || pane()?.querySelector('#performers-main-section table.performers-table');
    if (!rootTable) return;
    const grouped = {};
    Array.from(rootTable.querySelectorAll('tbody tr[data-row-order-id]')).forEach((tr) => {
      const key = String(tr.dataset.projectId || '') + '\0' + String(tr.dataset.assetName || '');
      (grouped[key] || (grouped[key] = [])).push(tr);
    });
    Object.keys(grouped).forEach((key) => {
      let index = 0;
      grouped[key].forEach((tr) => {
        const cell = tr.querySelector('td.js-section-code');
        if (!cell) return;
        if (performerRowIsSectionAccounting(tr)) {
          index += 1;
          cell.textContent = padPerformerSectionCode(index);
        } else {
          cell.textContent = '';
        }
      });
    });
  }
  function syncPerformerSectionOrder(table) {
    updatePerformerSectionCodes(sortPerformerRowsByProjectAndAsset(table));
  }
  function updatePerformerLockedActionButtons(panel) {
    if (!panel) return;
    const upBtn = panel.querySelector('[data-panel-action="up"]');
    const downBtn = panel.querySelector('[data-panel-action="down"]');
    const deleteBtn = panel.querySelector('[data-panel-action="delete"]');
    const rows = getChecked('performer-select').map((box) => box.closest('tr')).filter(Boolean);
    const anyLocked = rows.some(performerRowIsSectionLocked);
    const anyDeleteLocked = rows.some(performerRowDeleteLocked);
    if (upBtn) {
      upBtn.classList.toggle('d-none', anyLocked);
      upBtn.disabled = anyLocked;
    }
    if (downBtn) {
      downBtn.classList.toggle('d-none', anyLocked);
      downBtn.disabled = anyLocked;
    }
    if (deleteBtn) {
      deleteBtn.classList.toggle('d-none', anyDeleteLocked);
      deleteBtn.disabled = anyDeleteLocked;
    }
  }
  function movePerformerSelectionImmediately(action, checked) {
    if (
      !(action === 'up' || action === 'down') ||
      !window.__queuedRowOrder ||
      typeof window.__queuedRowOrder.moveSelection !== 'function'
    ) {
      return false;
    }
    if (checked.some((box) => performerRowIsSectionLocked(box.closest('tr')))) {
      return false;
    }
    const root = pane();
    if (!root) return false;
    return !!window.__queuedRowOrder.moveSelection(root, action, {
      selectionName: 'performer-select',
      selectedIds: checked.map((box) => String(box.value)),
      rowScopeDataKey: 'projectId',
      onAfterMove: function (table) {
        syncPerformerSectionOrder(table);
        updatePerformerMasterState();
        updateRowHighlight('performer-select');
        ensurePerformerActionsVisibility();
        schedulePaymentRequestScrollGapsUpdate();
      },
    });
  }
  function getVisiblePerformerChecks() {
    return getRowChecks('performer-select').filter((checkbox) => {
      const row = checkbox.closest('tr');
      return row && !row.classList.contains('d-none');
    });
  }

  function getParticipationMaster() {
    return pane()?.querySelector('#participation-master');
  }
  function getParticipationRequestBtn() {
    return pane()?.querySelector('#participation-request-btn');
  }
  function getParticipationBatchActionBtn() {
    return pane()?.querySelector('#participation-batch-action-btn');
  }
  function getParticipationRequestPanel() {
    return pane()?.querySelector('#participation-request-actions');
  }
  function getParticipationDeadlineControls() {
    return pane()?.querySelector('#participation-deadline-controls');
  }
  function getParticipationChannels() {
    return qa('.js-participation-channel', pane());
  }
  function getParticipationRows() {
    return qa('#participation-confirmation-section tbody tr[data-project-id]', pane());
  }
  function isFilterHidden(row) {
    return row.classList.contains('d-none')
      && !row.classList.contains('section-collapsed')
      && !row.classList.contains('asset-collapsed');
  }
  function getVisibleParticipationChecks() {
    return getParticipationRows()
      .filter((row) => !isFilterHidden(row))
      .map((row) => row.querySelector('input[name="participation-select"]'))
      .filter((checkbox) => checkbox && !checkbox.disabled);
  }
  function getParticipationRecipientKey(row) {
    return row?.dataset?.recipientId || row?.dataset?.executor || '';
  }
  function getParticipationBaseGroupKey(row) {
    return (row?.dataset?.projectId || '') + '||' + getParticipationRecipientKey(row);
  }
  function getParticipationGroupKey(row) {
    var batchId = row?.dataset?.participationBatchId || '';
    if (batchId) return 'batch||' + batchId;
    return 'base||' + getParticipationBaseGroupKey(row);
  }
  function getSelectedParticipationRequestIds() {
    const selectedGroups = new Set();
    getVisibleParticipationChecks()
      .filter((checkbox) => checkbox.checked && checkbox.dataset.requestSent !== '1')
      .forEach((checkbox) => selectedGroups.add(getParticipationGroupKey(checkbox.closest('tr'))));

    const ids = new Set();
    getParticipationRows().forEach((row) => {
      if (!selectedGroups.has(getParticipationGroupKey(row))) return;
      const checkbox = row.querySelector('input[name="participation-select"]');
      if (checkbox && !checkbox.disabled && checkbox.dataset.requestSent !== '1') ids.add(checkbox.value);
    });
    return Array.from(ids);
  }
  function getParticipationBatchActionState() {
    const selected = getVisibleParticipationChecks()
      .filter((checkbox) => checkbox.checked && checkbox.dataset.requestSent !== '1');
    if (!selected.length) return { mode: '', ids: [] };

    const rows = selected.map((checkbox) => checkbox.closest('tr')).filter(Boolean);
    const numbers = new Set(rows.map((row) => row.dataset.projectNumber || ''));
    const recipients = new Set(rows.map((row) => row.dataset.recipientId || ''));
    if (numbers.size !== 1 || recipients.size !== 1 || numbers.has('') || recipients.has('')) {
      return { mode: '', ids: [] };
    }

    const batchIds = new Set(rows.map((row) => row.dataset.participationBatchId || '').filter(Boolean));
    const ids = selected.map((checkbox) => checkbox.value);
    if (batchIds.size === 1) {
      return { mode: 'split', ids };
    }
    if (batchIds.size > 1) {
      return { mode: '', ids: [] };
    }

    const baseGroups = new Set(rows.map(getParticipationBaseGroupKey));
    if (baseGroups.size > 1) {
      return { mode: 'merge', ids };
    }
    return { mode: '', ids: [] };
  }
  function updateParticipationState() {
    const boxes = getVisibleParticipationChecks();
    const checkedCount = boxes.filter(b => b.checked).length;
    const master = getParticipationMaster();
    if (master) {
      master.checked = boxes.length > 0 && checkedCount === boxes.length;
      master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
    }
    updateRowHighlight('participation-select');

    const requestBtn = getParticipationRequestBtn();
    if (requestBtn) requestBtn.disabled = checkedCount === 0;

    const batchActionBtn = getParticipationBatchActionBtn();
    if (batchActionBtn) {
      const actionState = getParticipationBatchActionState();
      const visible = !!actionState.mode;
      batchActionBtn.classList.toggle('d-none', !visible);
      batchActionBtn.disabled = !visible;
      batchActionBtn.dataset.mode = actionState.mode || '';
      batchActionBtn.textContent = actionState.mode === 'split' ? 'Разъединить' : 'Объединить';
    }

    const controls = getParticipationDeadlineControls();
    if (controls) {
      const show = checkedCount > 0;
      controls.classList.toggle('invisible', !show);
      controls.classList.toggle('pe-none', !show);
    }
  }

  function getInfoRequestMaster() {
    return pane()?.querySelector('#info-request-master');
  }
  function getInfoRequestBtn() {
    return pane()?.querySelector('#info-request-btn');
  }
  function getInfoRequestPanel() {
    return pane()?.querySelector('#info-request-actions');
  }
  function getInfoRequestDeadlineControls() {
    return pane()?.querySelector('#info-request-deadline-controls');
  }
  function getInfoRequestChannels() {
    return qa('.js-info-request-channel', pane());
  }
  function getInfoRequestRows() {
    return qa('#info-request-approval-section tbody tr[data-project-id]', pane());
  }
  function getVisibleInfoRequestChecks() {
    return getInfoRequestRows()
      .filter((row) => !isFilterHidden(row))
      .map((row) => row.querySelector('input[name="info-request-select"]'))
      .filter((checkbox) => checkbox && !checkbox.disabled);
  }
  function getPaymentRequestSections() {
    return qa('.payment-request-section', document);
  }
  function findPaymentRequestSection(el) {
    return el?.closest('.payment-request-section') || null;
  }
  function getPaymentRequestMaster(section) {
    return section?.querySelector('.js-payment-request-master');
  }
  function getPaymentRequestRows(section) {
    if (section) return qa('tbody tr[data-project-id]', section);
    return qa('.payment-request-section tbody tr[data-project-id]', document);
  }
  function getPaymentRequestRowsForPerformer(performerId) {
    return getPaymentRequestRows().filter((row) => row.dataset.performerId === String(performerId));
  }
  function getVisiblePaymentRequestChecks(section) {
    const rows = section ? getPaymentRequestRows(section) : getPaymentRequestRows();
    return rows
      .filter((row) => !isFilterHidden(row))
      .map((row) => row.querySelector('input[name="payment-request-select"]'))
      .filter((checkbox) => checkbox && !checkbox.disabled);
  }
  function getPaymentRequestSendBtn(section) {
    return section?.querySelector('.js-payment-request-send-btn');
  }
  function getPaymentRequestActionsPanel(section) {
    return section?.querySelector('.js-payment-request-actions');
  }
  function getPaymentRequestChannels(section) {
    return qa('.js-payment-request-channel', section || document);
  }
  function parsePaymentRequestPrepayment(row) {
    const raw = row?.dataset?.prepayment;
    if (raw === '' || raw === undefined) return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }
  function isPaymentRequestAdvanceSkipped(row) {
    return parsePaymentRequestPrepayment(row) === 0;
  }
  function isPaymentRequestAdvanceOn(row) {
    return row?.dataset?.advanceRequested === '1' || isPaymentRequestAdvanceSkipped(row);
  }
  function isPaymentRequestFinalOn(row) {
    return row?.dataset?.finalRequested === '1';
  }
  function isPaymentRequestComplete(row) {
    return isPaymentRequestAdvanceOn(row) && isPaymentRequestFinalOn(row);
  }
  function getNextPaymentRequestStep(row) {
    if (!row || isPaymentRequestComplete(row)) return null;
    if (!isPaymentRequestAdvanceOn(row)) return 'advance';
    if (!isPaymentRequestFinalOn(row)) return 'final';
    return null;
  }
  function setPaymentRequestSentDate(row, kind, value) {
    if (!row || (kind !== 'advance' && kind !== 'final')) return;
    const cell = row.querySelector(`[data-payment-date="${kind}"]`);
    if (!cell) return;
    cell.textContent = value || '';
  }
  function setPaymentRequestNumber(row, kind, value) {
    if (!row || (kind !== 'advance' && kind !== 'final')) return;
    const cell = row.querySelector(`[data-payment-number="${kind}"]`);
    if (!cell) return;
    cell.textContent = value != null && value !== '' ? String(value) : '';
  }
  function setPaymentRequestSender(row, value) {
    if (!row) return;
    const cell = row.querySelector('[data-payment-sender]');
    if (!cell) return;
    cell.textContent = value || '';
  }
  function isPaymentPaidToggleInteractive(section) {
    const target = section || getPaymentRequestSections().find((item) => item.dataset.paymentPaidToggleUrl);
    return Boolean(target?.dataset?.paymentPaidToggleUrl);
  }
  function getPaymentPaidToggleUrl(section) {
    const target = section || getPaymentRequestSections().find((item) => item.dataset.paymentPaidToggleUrl);
    return target?.dataset?.paymentPaidToggleUrl || '';
  }
  function setPaymentPaidDate(row, kind, value) {
    if (!row || (kind !== 'advance' && kind !== 'final')) return;
    const cell = row.querySelector(`[data-payment-paid-date="${kind}"]`);
    if (!cell) return;
    cell.textContent = value || '';
  }
  function setPaymentPaidToggle(row, kind, on, options = {}) {
    if (!row || (kind !== 'advance' && kind !== 'final')) return;
    const skipped = Boolean(options.skipped)
      || (kind === 'advance' && isPaymentRequestAdvanceSkipped(row));
    if (skipped && kind === 'advance' && isPaymentRequestAdvanceSkipped(row)) {
      on = true;
    }
    const datasetKey = kind === 'advance' ? 'advancePaid' : 'finalPaid';
    row.dataset[datasetKey] = on ? '1' : '0';
    const icon = row.querySelector(`[data-payment-paid-toggle="${kind}"]`);
    if (!icon) return;
    icon.classList.toggle('bi-toggle-off', !on);
    icon.classList.toggle('bi-toggle-on', on);
    icon.classList.toggle('is-on', on);
    icon.classList.toggle('is-skipped', skipped);
    if (skipped) {
      icon.classList.remove('is-interactive');
      icon.removeAttribute('role');
      icon.setAttribute('aria-hidden', 'true');
    }
    const labelPrefix = kind === 'advance' ? 'Оплата аванса' : 'Оплата окончательного платежа';
    icon.setAttribute('aria-label', `${labelPrefix}: ${on ? 'выполнена' : 'не выполнена'}`);
    if (options.paidAt !== undefined) {
      setPaymentPaidDate(row, kind, options.paidAt);
    }
  }
  function setPaymentPaidToggleForPerformer(performerId, kind, on, options = {}) {
    getPaymentRequestRowsForPerformer(performerId).forEach((row) => setPaymentPaidToggle(row, kind, on, options));
  }
  function setPaymentRequestToggle(row, kind, on, options = {}) {
    if (!row || (kind !== 'advance' && kind !== 'final')) return;
    const skipped = Boolean(options.skipped);
    if (kind === 'advance') {
      if (skipped) {
        row.setAttribute('data-advance-requested', '0');
      } else {
        row.setAttribute('data-advance-requested', on ? '1' : '0');
      }
    } else {
      row.setAttribute('data-final-requested', on ? '1' : '0');
    }
    const icon = row.querySelector(`[data-payment-toggle="${kind}"]`);
    if (!icon) return;
    icon.classList.toggle('bi-toggle-off', !on);
    icon.classList.toggle('bi-toggle-on', on);
    icon.classList.toggle('is-on', on);
    if (kind === 'advance') {
      icon.classList.toggle('is-skipped', skipped);
    }
  }
  function initPaymentRequestRowState(row) {
    if (!row) return;
    if (isPaymentRequestAdvanceSkipped(row) && row.dataset.advanceRequested !== '1') {
      setPaymentRequestToggle(row, 'advance', true, { skipped: true });
      setPaymentPaidToggle(row, 'advance', true, { skipped: true });
    }
  }
  function isContractsPaymentRequestSection(section) {
    return section?.id === 'contracts-payment-request-section';
  }
  function applyPaymentRequestSentState() {
    getPaymentRequestSections().forEach((section) => {
      const hasActions = Boolean(getPaymentRequestActionsPanel(section));
      const master = getPaymentRequestMaster(section);
      if (isContractsPaymentRequestSection(section)) {
        if (master) {
          master.disabled = true;
          master.checked = false;
          master.indeterminate = false;
        }
      }
      getPaymentRequestRows(section).forEach((row) => {
        const checkbox = row.querySelector('input[name="payment-request-select"]');
        if (!checkbox) return;
        if (isContractsPaymentRequestSection(section)) {
          checkbox.disabled = true;
          checkbox.checked = false;
          checkbox.title = '';
          return;
        }
        if (isPaymentRequestComplete(row)) {
          checkbox.disabled = true;
          checkbox.checked = false;
          checkbox.title = 'Строка недоступна: обе заявки уже отправлены';
        } else if (hasActions) {
          checkbox.disabled = false;
          checkbox.title = '';
        }
      });
    });
  }
  function syncPaymentRequestRowsState() {
    getPaymentRequestRows().forEach(initPaymentRequestRowState);
    applyPaymentRequestSentState();
  }
  function getCreateSourceDataBtn() {
    return pane()?.querySelector('#create-source-data-btn');
  }
  function getRevokeInfoApprovalBtn() {
    return pane()?.querySelector('#revoke-info-approval-btn');
  }

  function getSelectedInfoRequestProjectId() {
    const filter = window.__infoRequestProjectFilter;
    if (filter && filter.length === 1 && filter[0] !== '__all__') return filter[0];
    return null;
  }
  function getInfoRequestRowForCheck(checkbox) {
    return checkbox?.closest('tr[data-project-id]') || null;
  }
  function isInfoRequestRowSent(row) {
    return row?.dataset?.infoRequestSent === '1';
  }
  function isInfoRequestRowApproved(row) {
    return row?.dataset?.infoApprovalStatus === 'approved';
  }
  function infoRequestRevokeSelectionState(checkedRows) {
    const approvedRows = checkedRows.filter(isInfoRequestRowApproved);
    const hasApprovedSelection = approvedRows.length > 0;
    if (!checkedRows.length || approvedRows.length !== checkedRows.length) {
      return { hasApprovedSelection, canRevoke: false };
    }
    const executorSet = new Set(checkedRows.map((row) => row.dataset.employeeUserId || row.dataset.executor || ''));
    const projectSet = new Set(checkedRows.map((row) => row.dataset.projectId || ''));
    return {
      hasApprovedSelection,
      canRevoke: executorSet.size === 1 && projectSet.size === 1,
    };
  }

  function updateInfoRequestState() {
    const boxes = getVisibleInfoRequestChecks();
    const checked = boxes.filter(b => b.checked);
    const checkedCount = checked.length;
    const checkedRows = checked.map(getInfoRequestRowForCheck).filter(Boolean);
    const master = getInfoRequestMaster();
    if (master) {
      master.checked = boxes.length > 0 && checkedCount === boxes.length;
      master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
    }
    updateRowHighlight('info-request-select');

    const requestBtn = getInfoRequestBtn();
    if (requestBtn) {
      const canRequestApproval = checkedCount > 0 && checkedRows.every((row) => !isInfoRequestRowSent(row));
      requestBtn.disabled = !canRequestApproval;
    }

    const revokeBtn = getRevokeInfoApprovalBtn();
    if (revokeBtn) {
      const revokeState = infoRequestRevokeSelectionState(checkedRows);
      revokeBtn.classList.toggle('d-none', !revokeState.hasApprovedSelection);
      revokeBtn.disabled = !revokeState.canRevoke;
    }

    const controls = getInfoRequestDeadlineControls();
    if (controls) {
      const show = checkedCount > 0 && checkedRows.every((row) => !isInfoRequestRowSent(row));
      controls.classList.toggle('invisible', !show);
      controls.classList.toggle('pe-none', !show);
    }

    const wsBtn = getCreateSourceDataBtn();
    if (wsBtn) wsBtn.disabled = !getSelectedInfoRequestProjectId();
  }

  function updatePaymentRequestState(section) {
    const sections = section ? [section] : getPaymentRequestSections();
    sections.forEach((sec) => {
      const boxes = getVisiblePaymentRequestChecks(sec);
      const checkedCount = boxes.filter(b => b.checked).length;
      const master = getPaymentRequestMaster(sec);
      if (master) {
        master.checked = boxes.length > 0 && checkedCount === boxes.length;
        master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
      }
      const sendBtn = getPaymentRequestSendBtn(sec);
      if (sendBtn) sendBtn.disabled = checkedCount === 0;
    });
    updateRowHighlight('payment-request-select');
  }

  function getContractMaster() {
    return contractPane()?.querySelector('#contract-master');
  }
  function getContractDispatchMaster() {
    return contractPane()?.querySelector('#contract-dispatch-master');
  }
  function getContractRequestBtn() {
    return contractPane()?.querySelector('#contract-request-btn');
  }
  function getCreateContractBtn() {
    return contractPane()?.querySelector('#create-contract-btn');
  }
  function getContractSignBtn() {
    return contractPane()?.querySelector('#contract-sign-btn');
  }
  function getContractRequestPanel() {
    return contractPane()?.querySelector('#contract-request-actions');
  }
  function getContractDeadlineControls() {
    return contractPane()?.querySelector('#contract-deadline-controls');
  }
  function getContractChannels() {
    return qa('.js-contract-channel', contractPane());
  }
  function getContractRows() {
    return qa('#contract-conclusion-section tbody tr[data-project-id]', contractPane());
  }
  function getContractDraftRows() {
    return qa('#contract-drafting-table tbody tr[data-project-id]', contractPane());
  }
  function getContractDispatchRows() {
    return qa('#contract-dispatch-table tbody tr[data-project-id]', contractPane());
  }
  function getVisibleContractChecks() {
    return getContractDraftRows()
      .filter((row) => !isFilterHidden(row))
      .map((row) => row.querySelector('input[name="contract-select"]'))
      .filter((checkbox) => checkbox && !checkbox.disabled);
  }
  function getVisibleContractDispatchChecks() {
    return getContractDispatchRows()
      .filter((row) => !isFilterHidden(row))
      .map((row) => row.querySelector('input[name="contract-dispatch-select"]'))
      .filter((checkbox) => checkbox && !checkbox.disabled);
  }
  function normalizeContractGroupText(value) {
    return String(value || '').trim().toLowerCase();
  }
  function getContractGroupKey(row, includeBatch) {
    if (includeBatch) {
      var participationBatchId = row?.dataset?.participationBatchId || '';
      if (participationBatchId) return 'participation-batch||' + participationBatchId;
      var batchId = row?.dataset?.contractBatchId || '';
      if (batchId) return 'batch||' + batchId;
    }
    return (row?.dataset?.projectId || '') + '||' + (row?.dataset?.executor || '');
  }
  function getContractDraftingGroupKey(row) {
    var contractNumber = normalizeContractGroupText(row?.dataset?.contractNumber || '');
    if (contractNumber) {
      return [
        'contract-number',
        normalizeContractGroupText(row?.dataset?.executor || ''),
        contractNumber,
        row?.dataset?.contractIsAddendum === '1' ? '1' : '0',
        row?.dataset?.contractAddendumNumber || '0',
      ].join('||');
    }
    return getContractGroupKey(row, true);
  }
  function getSelectedContractDraftRows() {
    const selectedGroups = new Set();
    getVisibleContractChecks()
      .filter((checkbox) => checkbox.checked && !isContractSentCheckbox(checkbox))
      .forEach((checkbox) => selectedGroups.add(getContractDraftingGroupKey(checkbox.closest('tr'))));

    if (!selectedGroups.size) return [];
    return getContractDraftRows().filter((row) => selectedGroups.has(getContractDraftingGroupKey(row)));
  }
  function getSelectedContractDraftIds() {
    const ids = new Set();
    getSelectedContractDraftRows().forEach((row) => {
      const checkbox = row.querySelector('input[name="contract-select"]');
      if (checkbox && !isContractSentCheckbox(checkbox)) ids.add(checkbox.value);
    });
    return Array.from(ids);
  }
  function getSelectedContractDispatchIds() {
    const selectedGroups = new Set();
    getVisibleContractDispatchChecks()
      .filter((checkbox) => checkbox.checked)
      .forEach((checkbox) => selectedGroups.add(getContractGroupKey(checkbox.closest('tr'), true)));

    const ids = new Set();
    getContractDispatchRows().forEach((row) => {
      if (!selectedGroups.has(getContractGroupKey(row, true))) return;
      const checkbox = row.querySelector('input[name="contract-dispatch-select"]');
      if (checkbox && !checkbox.disabled) ids.add(checkbox.value);
    });
    return Array.from(ids);
  }
  function isContractSentCheckbox(checkbox) {
    return checkbox?.dataset?.contractSent === '1';
  }
  function markContractSentCheckboxDisabled(checkbox) {
    if (!checkbox || !isContractSentCheckbox(checkbox)) return;
    checkbox.checked = false;
    checkbox.disabled = true;
    checkbox.title = 'Строка недоступна: проект договора уже отправлен';
  }
  function disableContractCorrectionChecksByIds(ids) {
    var root = contractPane();
    if (!root || !ids || !ids.length) return;
    var idSet = new Set(ids.map(function(id) { return String(id); }));
    qa('tbody input.form-check-input[name="contract-row-select"]', root).forEach(function(checkbox) {
      if (!idSet.has(String(checkbox.value))) return;
      checkbox.dataset.contractSent = '1';
      markContractSentCheckboxDisabled(checkbox);
    });
  }
  function isContractDispatchReadyCheckbox(checkbox) {
    return checkbox?.closest('tr')?.dataset?.contractDispatchReady === '1';
  }
  function refreshPerformersSelectionState() {
    getRowChecks('performer-select').forEach((checkbox) => {
      const row = checkbox.closest('tr');
      if (row && row.classList.contains('d-none')) checkbox.checked = false;
    });
    getRowChecks('participation-select').forEach((checkbox) => {
      const row = checkbox.closest('tr');
      if (row && isFilterHidden(row)) checkbox.checked = false;
    });
    getRowChecks('contract-select').forEach((checkbox) => {
      const row = checkbox.closest('tr');
      if (row && isFilterHidden(row)) checkbox.checked = false;
    });
    getRowChecks('contract-dispatch-select').forEach((checkbox) => {
      const row = checkbox.closest('tr');
      if (row && isFilterHidden(row)) checkbox.checked = false;
    });
    getRowChecks('info-request-select').forEach((checkbox) => {
      const row = checkbox.closest('tr');
      if (row && isFilterHidden(row)) checkbox.checked = false;
    });
    getRowChecks('payment-request-select').forEach((checkbox) => {
      const row = checkbox.closest('tr');
      if (row && isFilterHidden(row)) checkbox.checked = false;
    });
    updatePerformerMasterState();
    updateRowHighlight('performer-select');
    ensurePerformerActionsVisibility();
    updateParticipationState();
    updateContractState();
    updateInfoRequestState();
    updatePaymentRequestState();
  }
  window.__refreshPerformersSelectionState = refreshPerformersSelectionState;

  function updateContractState() {
    const boxes = getVisibleContractChecks();
    const checked = boxes.filter(b => b.checked);
    const checkedCount = checked.length;
    const master = getContractMaster();
    if (master) {
      master.checked = boxes.length > 0 && checkedCount === boxes.length;
      master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
    }
    updateRowHighlight('contract-select');

    const dispatchBoxes = getVisibleContractDispatchChecks();
    const dispatchCheckedCount = dispatchBoxes.filter(b => b.checked).length;
    const dispatchMaster = getContractDispatchMaster();
    if (dispatchMaster) {
      dispatchMaster.checked = dispatchBoxes.length > 0 && dispatchCheckedCount === dispatchBoxes.length;
      dispatchMaster.indeterminate = dispatchCheckedCount > 0 && dispatchCheckedCount < dispatchBoxes.length;
    }
    updateRowHighlight('contract-dispatch-select');

    const requestBtn = getContractRequestBtn();
    if (requestBtn) {
      const dispatchChecked = dispatchBoxes.filter(b => b.checked);
      const allDispatchReady = dispatchCheckedCount > 0 && dispatchChecked.every(isContractDispatchReadyCheckbox);
      requestBtn.disabled = !allDispatchReady;
    }

    const selectedDraftRows = getSelectedContractDraftRows();
    const selectedDraftIds = getSelectedContractDraftIds();
    const selectedActionableDraftRows = selectedDraftRows.filter((row) => {
      const checkbox = row.querySelector('input[name="contract-select"]');
      return checkbox && !isContractSentCheckbox(checkbox);
    });
    const createBtn = getCreateContractBtn();
    if (createBtn) createBtn.disabled = selectedDraftIds.length === 0;

    const signBtn = getContractSignBtn();
    if (signBtn) {
      const allReadyToSign = selectedDraftIds.length > 0 && selectedActionableDraftRows.every((row) => {
        return row?.dataset?.contractSignReady === '1';
      });
      signBtn.disabled = !allReadyToSign;
    }

    const controls = getContractDeadlineControls();
    if (controls) {
      const show = dispatchCheckedCount > 0;
      controls.classList.toggle('invisible', !show);
      controls.classList.toggle('pe-none', !show);
    }
  }

  function applyRowGrouping(sectionEl) {
    if (!sectionEl) return;
    var bodies = Array.from(sectionEl.querySelectorAll('table.performers-table tbody'));
    bodies.forEach(function(tbody) {
      var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
      var table = tbody.closest('table');
      var isContractDispatchTable = table?.id === 'contract-dispatch-table';
      var isContractDraftingTable = table?.id === 'contract-drafting-table';
      var isReportTable = table?.id === 'report-submission-table';
      if (isContractDispatchTable) {
        rows.forEach(function(row) {
          if (row.classList.contains('contract-dispatch-collapsed')) {
            row.classList.remove('d-none', 'contract-dispatch-collapsed');
          }
        });
      }
      var prevGroupKey = null;
      var prevAssetKey = null;
      var prevDetailTexts = null;
      var prevGroupTexts = null;
      var includeContractBatchInGroup = isContractDispatchTable || isContractDraftingTable;
      var isParticipationTable = !!tbody.closest('#participation-confirmation-section');
      rows.forEach(function(row) {
        row.classList.remove('group-first', 'group-cont', 'asset-cont');
        var groupCells = row.querySelectorAll('.cell-group-val');
        groupCells.forEach(function(c) { c.classList.remove('cell-group-repeated'); });
        var detailCells = row.querySelectorAll('.cell-detail-val');
        detailCells.forEach(function(c) { c.classList.remove('cell-repeated'); });
        if (isFilterHidden(row)) return;
        var groupKey = isReportTable
          ? (
            (row.dataset.projectId || '')
            + '||' + (row.dataset.assetName || '')
            + '||' + (row.dataset.reportKind === 'full' ? '__full__' : (row.dataset.executor || ''))
          )
          : (isParticipationTable
            ? getParticipationGroupKey(row)
            : (isContractDraftingTable ? getContractDraftingGroupKey(row) : getContractGroupKey(row, includeContractBatchInGroup)));
        var assetKey = groupKey + '||' + (row.dataset.assetName || '');
        if (groupKey !== prevGroupKey) {
          row.classList.add('group-first');
          prevDetailTexts = null;
          prevGroupTexts = null;
        } else {
          row.classList.add('group-cont');
          if (assetKey === prevAssetKey) {
            row.classList.add('asset-cont');
          }
        }
        var curGroupTexts = [];
        if (isParticipationTable || isContractDraftingTable || isReportTable) {
          groupCells.forEach(function(c, i) {
            var txt = c.textContent.trim();
            curGroupTexts.push(txt);
            if (prevGroupTexts && prevGroupTexts[i] === txt) {
              c.classList.add('cell-group-repeated');
            }
          });
        }
        var curDetailTexts = [];
        detailCells.forEach(function(c, i) {
          var txt = c.textContent.trim();
          curDetailTexts.push(txt);
          if (prevDetailTexts && prevDetailTexts[i] === txt) {
            c.classList.add('cell-repeated');
          }
        });
        prevGroupKey = groupKey;
        prevAssetKey = assetKey;
        prevDetailTexts = curDetailTexts;
        prevGroupTexts = curGroupTexts;
      });

      if (isContractDispatchTable) {
        rows.forEach(function(row) {
          if (!row.classList.contains('group-cont') || isFilterHidden(row)) return;
          row.classList.add('d-none', 'contract-dispatch-collapsed');
        });
      }

      var lastVisible = null;
      rows.forEach(function(row) {
        row.classList.remove('last-visible-row');
        if (!row.classList.contains('d-none')) lastVisible = row;
      });
      if (lastVisible) lastVisible.classList.add('last-visible-row');
    });
  }

  function propagateGroupCheck(checkbox, name) {
    var row = checkbox.closest('tr');
    if (!row || !row.classList.contains('group-first')) return;
    var sibling = row.nextElementSibling;
    while (sibling && sibling.classList.contains('group-cont')) {
      var cb = sibling.querySelector('input[name="' + name + '"]');
      if (cb && !cb.disabled) cb.checked = checkbox.checked;
      sibling = sibling.nextElementSibling;
    }
  }

  function applyParticipationSentState() {
    var root = pane();
    var section = root ? root.querySelector('#participation-confirmation-section') : null;
    if (!section) return;
    var tbody = section.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var expertReadonly = section.dataset.expertReadonly === '1';
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    if (expertReadonly) {
      var master = getParticipationMaster();
      if (master) master.disabled = true;
      rows.forEach(function(row) {
        var cb = row.querySelector('input[name="participation-select"]');
        if (cb) {
          cb.disabled = true;
          cb.title = 'Строка недоступна для редактирования';
        }
      });
      return;
    }
    rows.forEach(function(row) {
      var cb = row.querySelector('input[name="participation-select"]');
      if (cb && cb.dataset.requestSent === '1') {
        cb.disabled = true;
        cb.title = 'Запрос уже отправлен';
      }
    });
    var i = 0;
    while (i < rows.length) {
      if (rows[i].classList.contains('d-none') || !rows[i].classList.contains('group-first')) { i++; continue; }
      var group = [rows[i]];
      var j = i + 1;
      while (j < rows.length && rows[j].classList.contains('group-cont')) {
        group.push(rows[j]);
        j++;
      }
      var hasUnsent = group.some(function(r) {
        var cb = r.querySelector('input[name="participation-select"]');
        return cb && cb.dataset.requestSent !== '1';
      });
      var firstCb = group[0].querySelector('input[name="participation-select"]');
      if (firstCb && firstCb.disabled && hasUnsent) {
        firstCb.disabled = false;
        firstCb.title = '';
      }
      i = j;
    }
  }

  function applyContractSentState() {
    var root = contractPane();
    if (!root) return;
    qa('tbody input.form-check-input[name="contract-row-select"][data-contract-sent="1"]', root)
      .forEach(markContractSentCheckboxDisabled);
    var section = root ? root.querySelector('#contract-conclusion-section') : null;
    if (!section) return;
    var tbody = section.querySelector('#contract-drafting-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    rows.forEach(function(row) {
      var cb = row.querySelector('input[name="contract-select"]');
      markContractSentCheckboxDisabled(cb);
    });
    var i = 0;
    while (i < rows.length) {
      if (rows[i].classList.contains('d-none') || !rows[i].classList.contains('group-first')) { i++; continue; }
      var group = [rows[i]];
      var j = i + 1;
      while (j < rows.length && rows[j].classList.contains('group-cont')) {
        group.push(rows[j]);
        j++;
      }
      var hasUnsent = group.some(function(r) {
        var cb = r.querySelector('input[name="contract-select"]');
        return cb && !isContractSentCheckbox(cb);
      });
      var firstCb = group[0].querySelector('input[name="contract-select"]');
      if (firstCb && firstCb.disabled && hasUnsent) {
        firstCb.disabled = false;
        firstCb.title = '';
      }
      i = j;
    }
  }

  function pluralSections(n) {
    var mod10 = n % 10, mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return n + ' раздел';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return n + ' раздела';
    return n + ' разделов';
  }

  function restoreParticipationSectionText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__participationProjectFilter || ['__all__'];
    var showAll = !filterValues.length || filterValues.indexOf('__all__') !== -1;
    rows.forEach(function(row) {
      var td = row.querySelector('.cell-typical-val');
      if (td && td.dataset.originalTypical !== undefined) {
        td.innerHTML = td.dataset.originalTypical;
        delete td.dataset.originalTypical;
      }
      var projectTd = row.querySelector('.cell-project-val');
      if (projectTd && projectTd.dataset.originalProject !== undefined) {
        projectTd.innerHTML = projectTd.dataset.originalProject;
        delete projectTd.dataset.originalProject;
      }
      var typeTd = row.querySelector('.cell-type-val');
      if (typeTd && typeTd.dataset.originalType !== undefined) {
        typeTd.innerHTML = typeTd.dataset.originalType;
        delete typeTd.dataset.originalType;
      }
      if (row.classList.contains('section-collapsed')) {
        row.classList.remove('section-collapsed');
        var pid = row.dataset.projectId || '';
        if (showAll || filterValues.indexOf(pid) !== -1) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function participationCollapsedTypeLabel(rows) {
    var byProject = new Map();
    rows.forEach(function(row) {
      var projectId = row.dataset.projectId || '';
      var projectType = (row.dataset.projectType || '').trim();
      if (!projectId || !projectType || byProject.has(projectId)) return;
      var stage = parseInt(row.dataset.projectStage || '0', 10);
      byProject.set(projectId, {
        stage: Number.isFinite(stage) ? stage : 0,
        projectId: projectId,
        type: projectType,
      });
    });
    return Array.from(byProject.values())
      .sort(function(a, b) {
        if (a.stage !== b.stage) return a.stage - b.stage;
        return String(a.projectId).localeCompare(String(b.projectId), undefined, { numeric: true });
      })
      .map(function(item) { return item.type; })
      .join('-');
  }

  function applyCollapsedParticipationProjectType(currentFirst, currentRows) {
    if (!currentFirst || !currentRows || currentRows.length < 2) return;
    var batchId = currentFirst.dataset.participationBatchId || '';
    if (!batchId) return;
    var projectIds = new Set(currentRows.map(function(row) { return row.dataset.projectId || ''; }).filter(Boolean));
    if (projectIds.size <= 1) return;

    var projectTd = currentFirst.querySelector('.cell-project-val');
    if (projectTd) {
      projectTd.dataset.originalProject = projectTd.innerHTML;
      projectTd.textContent = '';
    }
    var typeTd = currentFirst.querySelector('.cell-type-val');
    var typeLabel = participationCollapsedTypeLabel(currentRows);
    if (typeTd && typeLabel) {
      typeTd.dataset.originalType = typeTd.innerHTML;
      typeTd.textContent = typeLabel;
    }
  }

  function collapseParticipationSections(sectionEl) {
    if (!sectionEl || sectionEl.id === 'report-submission-section') return;
    var tbody = sectionEl.querySelector('table.performers-table:not(#report-submission-table) tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var currentFirst = null;
    var currentRows = [];
    var currentCount = 0;
    function finishGroup() {
      if (!currentFirst) return;
      var td = currentFirst.querySelector('.cell-typical-val');
      if (td) {
        td.dataset.originalTypical = td.innerHTML;
        td.textContent = pluralSections(currentCount);
      }
      applyCollapsedParticipationProjectType(currentFirst, currentRows);
    }
    rows.forEach(function(row) {
      if (row.classList.contains('d-none')) return;
      if (!row.classList.contains('asset-cont')) {
        finishGroup();
        currentFirst = row;
        currentRows = [row];
        currentCount = 1;
      } else {
        currentRows.push(row);
        currentCount++;
        row.classList.add('d-none', 'section-collapsed');
      }
    });
    finishGroup();
    applyRowGrouping(sectionEl);
  }

  function expandParticipationSections(sectionEl) {
    restoreParticipationSectionText(sectionEl);
    applyRowGrouping(sectionEl);
  }

  function reapplyParticipationCollapse() {
    if (!window.__participationSectionCollapsed && !window.__participationAssetCollapsed) return;
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#participation-confirmation-section');
    if (!section) return;
    restoreParticipationAssetText(section);
    restoreParticipationSectionText(section);
    applyRowGrouping(section);
    if (window.__participationAssetCollapsed) {
      collapseParticipationAssets(section);
      var assetToggle = section.querySelector('#participation-asset-toggle');
      if (assetToggle) {
        assetToggle.classList.add('active');
        var aIcon = assetToggle.querySelector('i');
        if (aIcon) aIcon.className = 'bi bi-arrows-expand';
      }
    } else if (window.__participationSectionCollapsed) {
      collapseParticipationSections(section);
      var sectionToggle = section.querySelector('#participation-section-toggle');
      if (sectionToggle) {
        sectionToggle.classList.add('active');
        var sIcon = sectionToggle.querySelector('i');
        if (sIcon) sIcon.className = 'bi bi-arrows-expand';
      }
    }
  }

  function toggleParticipationCollapse() {
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#participation-confirmation-section');
    if (!section) return;
    var toggle = section.querySelector('#participation-section-toggle');
    var collapsed = !!window.__participationSectionCollapsed;
    if (window.__participationAssetCollapsed) {
      window.__participationSectionCollapsed = !collapsed;
      if (toggle) {
        toggle.classList.toggle('active', !collapsed);
        var icon = toggle.querySelector('i');
        if (icon) icon.className = !collapsed ? 'bi bi-arrows-expand' : 'bi bi-arrows-collapse';
      }
      saveCollapsePrefs();
      return;
    }
    if (collapsed) {
      expandParticipationSections(section);
      window.__participationSectionCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
    } else {
      collapseParticipationSections(section);
      window.__participationSectionCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    applyParticipationSentState();
    updateParticipationState();
    saveCollapsePrefs();
  }

  function pluralAssets(n) {
    var mod10 = n % 10, mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return n + ' актив';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return n + ' актива';
    return n + ' активов';
  }

  function restoreParticipationAssetText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__participationProjectFilter || ['__all__'];
    var showAll = !filterValues.length || filterValues.indexOf('__all__') !== -1;
    rows.forEach(function(row) {
      var assetTd = row.querySelector('.cell-asset-val');
      if (assetTd && assetTd.dataset.originalAsset !== undefined) {
        assetTd.innerHTML = assetTd.dataset.originalAsset;
        delete assetTd.dataset.originalAsset;
      }
      var typicalTd = row.querySelector('.cell-typical-val');
      if (typicalTd && typicalTd.dataset.originalTypicalAsset !== undefined) {
        typicalTd.innerHTML = typicalTd.dataset.originalTypicalAsset;
        delete typicalTd.dataset.originalTypicalAsset;
      }
      var projectTd = row.querySelector('.cell-project-val');
      if (projectTd && projectTd.dataset.originalProject !== undefined) {
        projectTd.innerHTML = projectTd.dataset.originalProject;
        delete projectTd.dataset.originalProject;
      }
      var typeTd = row.querySelector('.cell-type-val');
      if (typeTd && typeTd.dataset.originalType !== undefined) {
        typeTd.innerHTML = typeTd.dataset.originalType;
        delete typeTd.dataset.originalType;
      }
      if (row.classList.contains('asset-collapsed')) {
        row.classList.remove('asset-collapsed');
        var pid = row.dataset.projectId || '';
        if (showAll || filterValues.indexOf(pid) !== -1) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function collapseParticipationAssets(sectionEl) {
    if (!sectionEl || sectionEl.id === 'report-submission-section') return;
    var tbody = sectionEl.querySelector('table.performers-table:not(#report-submission-table) tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var i = 0;
    while (i < rows.length) {
      var row = rows[i];
      if (row.classList.contains('d-none') || !row.classList.contains('group-first')) { i++; continue; }
      var groupRows = [row];
      var j = i + 1;
      while (j < rows.length && !rows[j].classList.contains('group-first')) {
        groupRows.push(rows[j]);
        j++;
      }
      var assetSet = new Set();
      var totalSections = 0;
      groupRows.forEach(function(r) {
        if (r.classList.contains('d-none')) return;
        assetSet.add(r.dataset.assetName || '');
        totalSections++;
      });
      var visibleGroupRows = groupRows.filter(function(r) { return !r.classList.contains('d-none'); });
      for (var k = 1; k < groupRows.length; k++) {
        if (!groupRows[k].classList.contains('d-none')) {
          groupRows[k].classList.add('d-none', 'asset-collapsed');
        }
      }
      var assetTd = row.querySelector('.cell-asset-val');
      if (assetTd) {
        assetTd.dataset.originalAsset = assetTd.innerHTML;
        assetTd.textContent = pluralAssets(assetSet.size);
      }
      var typicalTd = row.querySelector('.cell-typical-val');
      if (typicalTd) {
        typicalTd.dataset.originalTypicalAsset = typicalTd.innerHTML;
        typicalTd.textContent = pluralSections(totalSections);
      }
      applyCollapsedParticipationProjectType(row, visibleGroupRows);
      i = j;
    }
    applyRowGrouping(sectionEl);
  }

  function toggleParticipationAssetCollapse() {
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#participation-confirmation-section');
    if (!section) return;
    var toggle = section.querySelector('#participation-asset-toggle');
    var collapsed = !!window.__participationAssetCollapsed;
    if (collapsed) {
      restoreParticipationAssetText(section);
      applyRowGrouping(section);
      window.__participationAssetCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
      if (window.__participationSectionCollapsed) {
        collapseParticipationSections(section);
        var sectionToggle = section.querySelector('#participation-section-toggle');
        if (sectionToggle) {
          sectionToggle.classList.add('active');
          var sIcon = sectionToggle.querySelector('i');
          if (sIcon) sIcon.className = 'bi bi-arrows-expand';
        }
      }
    } else {
      if (window.__participationSectionCollapsed) {
        restoreParticipationSectionText(section);
        applyRowGrouping(section);
      }
      collapseParticipationAssets(section);
      window.__participationAssetCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    applyParticipationSentState();
    updateParticipationState();
    saveCollapsePrefs();
  }

  function initContractProjectFilter() {
    const root = contractPane();
    if (!root) return;

    const FILTER_ALL = '__all__';
    window.__contractProjectFilter = window.__contractProjectFilter || [FILTER_ALL];

    const dropdown = root.querySelector('#contract-project-filter-toggle')?.closest('.dropdown');
    const checks = root.querySelectorAll('.js-contract-filter');
    const label = root.querySelector('.js-contract-filter-label');
    const master = root.querySelector('#contract-master');

    if (!dropdown || !checks.length || !label || dropdown.dataset.bound === '1') return;
    dropdown.dataset.bound = '1';
    window.bindProjectFilterMenuWidth(dropdown);

    function syncCheckboxes(values) {
      const set = new Set(values);
      checks.forEach((cb) => {
        cb.checked = set.has(cb.value);
      });
    }

    function updateLabel(values) {
      if (values.includes(FILTER_ALL) || !values.length) {
        label.textContent = 'Все';
        return;
      }
      if (values.length === 1) {
        const input = Array.from(checks).find((cb) => cb.value === values[0]);
        label.textContent = window.getProjectFilterSummaryLabel(input, '1 проект');
        return;
      }
      label.textContent = `${values.length} выбрано`;
    }

    function normalizeStatusValues(values) {
      values = Array.isArray(values) && values.length ? values.slice() : [FILTER_ALL];
      if (values.includes(FILTER_ALL)) return [FILTER_ALL];
      return values;
    }

    function getStatusValues() {
      return normalizeStatusValues(window.__contractStatusFilter || [FILTER_ALL]);
    }

    function applyFilter(values) {
      window.__contractProjectFilter = values.slice();
      const showAll = values.includes(FILTER_ALL) || !values.length;
      const statusValues = getStatusValues();
      const showAllStatuses = statusValues.includes(FILTER_ALL) || !statusValues.length;
      const statusSet = new Set(statusValues);
      getContractRows().forEach((row) => {
        row.classList.remove('contract-dispatch-collapsed');
        const pid = row.dataset.projectId || '';
        const projectVisible = showAll || values.includes(pid);
        const statusVisible = showAllStatuses || statusSet.has(row.dataset.contractStatus || '—');
        const visible = projectVisible && statusVisible;
        row.classList.toggle('d-none', !visible);
        if (!visible) {
          ['contract-select', 'contract-dispatch-select'].forEach((name) => {
            const checkbox = row.querySelector('input[name="' + name + '"]');
            if (checkbox) checkbox.checked = false;
          });
        }
      });
      if (master && !showAll && !getContractRows().some((row) => !row.classList.contains('d-none'))) {
        master.checked = false;
        master.indeterminate = false;
      }
      updateLabel(values);
      applyRowGrouping(root.querySelector('#contract-conclusion-section'));
      applyContractSentState();
      updateContractState();
      reapplyContractCollapse();
      document.body.dispatchEvent(new CustomEvent('contract-project-filter-updated', {
        detail: { values: window.__contractProjectFilter.slice() },
      }));
    }

    function normalizeSelection() {
      let values = Array.from(checks)
        .filter((cb) => cb.checked)
        .map((cb) => cb.value);

      if (!values.length) values = [FILTER_ALL];
      if (values.includes(FILTER_ALL)) values = [FILTER_ALL];

      syncCheckboxes(values);
      return values;
    }

    checks.forEach((cb) => {
      cb.addEventListener('change', (event) => {
        const value = event.target.value;
        if (value === FILTER_ALL && event.target.checked) {
          syncCheckboxes([FILTER_ALL]);
          applyFilter([FILTER_ALL]);
          return;
        }

        if (value === FILTER_ALL && !event.target.checked) {
          const firstProject = Array.from(checks).find((item) => item.value !== FILTER_ALL);
          if (firstProject) firstProject.checked = true;
        } else {
          const allCheckbox = root.querySelector('#contract-filter-all');
          if (allCheckbox && allCheckbox.checked) allCheckbox.checked = false;
        }

        applyFilter(normalizeSelection());
      });
    });

    window.__syncContractProjectFilter = function(values) {
      var isAll = values[0] === FILTER_ALL;
      var isSingle = !isAll && values.length === 1;
      var set = new Set(values);
      checks.forEach(function(cb) {
        if (isAll) { cb.checked = cb.value === FILTER_ALL; cb.disabled = false; }
        else if (isSingle) { cb.checked = cb.value === values[0]; cb.disabled = true; }
        else {
          if (cb.value === FILTER_ALL) { cb.checked = true; cb.disabled = false; }
          else { cb.checked = set.has(cb.value); cb.disabled = !set.has(cb.value); }
        }
      });
      applyFilter(isAll ? [FILTER_ALL] : values.slice());
    };

    window.__syncContractStatusFilter = function(values) {
      window.__contractStatusFilter = normalizeStatusValues(values);
      applyFilter(window.__contractProjectFilter || [FILTER_ALL]);
    };

    const initialValues = window.__contractProjectFilter && window.__contractProjectFilter.length
      ? window.__contractProjectFilter
      : [FILTER_ALL];
    window.__contractStatusFilter = normalizeStatusValues(window.__contractStatusFilter || [FILTER_ALL]);
    syncCheckboxes(initialValues);
    applyFilter(initialValues);
  }

  function restoreContractSectionText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__contractProjectFilter || ['__all__'];
    var showAll = !filterValues.length || filterValues.indexOf('__all__') !== -1;
    var statusValues = window.__contractStatusFilter || ['__all__'];
    var showAllStatuses = !statusValues.length || statusValues.indexOf('__all__') !== -1;
    var statusSet = new Set(statusValues);
    rows.forEach(function(row) {
      var td = row.querySelector('.cell-typical-val');
      if (td && td.dataset.originalTypical !== undefined) {
        td.innerHTML = td.dataset.originalTypical;
        delete td.dataset.originalTypical;
      }
      var projectTd = row.querySelector('.cell-project-val');
      if (projectTd && projectTd.dataset.originalProject !== undefined) {
        projectTd.innerHTML = projectTd.dataset.originalProject;
        delete projectTd.dataset.originalProject;
      }
      var typeTd = row.querySelector('.cell-type-val');
      if (typeTd && typeTd.dataset.originalType !== undefined) {
        typeTd.innerHTML = typeTd.dataset.originalType;
        delete typeTd.dataset.originalType;
      }
      if (row.classList.contains('section-collapsed')) {
        row.classList.remove('section-collapsed');
        var pid = row.dataset.projectId || '';
        var status = row.dataset.contractStatus || '—';
        if ((showAll || filterValues.indexOf(pid) !== -1) && (showAllStatuses || statusSet.has(status))) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function restoreContractAssetText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__contractProjectFilter || ['__all__'];
    var showAll = !filterValues.length || filterValues.indexOf('__all__') !== -1;
    var statusValues = window.__contractStatusFilter || ['__all__'];
    var showAllStatuses = !statusValues.length || statusValues.indexOf('__all__') !== -1;
    var statusSet = new Set(statusValues);
    rows.forEach(function(row) {
      var assetTd = row.querySelector('.cell-asset-val');
      if (assetTd && assetTd.dataset.originalAsset !== undefined) {
        assetTd.innerHTML = assetTd.dataset.originalAsset;
        delete assetTd.dataset.originalAsset;
      }
      var typicalTd = row.querySelector('.cell-typical-val');
      if (typicalTd && typicalTd.dataset.originalTypicalAsset !== undefined) {
        typicalTd.innerHTML = typicalTd.dataset.originalTypicalAsset;
        delete typicalTd.dataset.originalTypicalAsset;
      }
      var projectTd = row.querySelector('.cell-project-val');
      if (projectTd && projectTd.dataset.originalProject !== undefined) {
        projectTd.innerHTML = projectTd.dataset.originalProject;
        delete projectTd.dataset.originalProject;
      }
      var typeTd = row.querySelector('.cell-type-val');
      if (typeTd && typeTd.dataset.originalType !== undefined) {
        typeTd.innerHTML = typeTd.dataset.originalType;
        delete typeTd.dataset.originalType;
      }
      if (row.classList.contains('asset-collapsed')) {
        row.classList.remove('asset-collapsed');
        var pid = row.dataset.projectId || '';
        var status = row.dataset.contractStatus || '—';
        if ((showAll || filterValues.indexOf(pid) !== -1) && (showAllStatuses || statusSet.has(status))) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function reapplyContractCollapse() {
    if (!window.__contractSectionCollapsed && !window.__contractAssetCollapsed) return;
    var root = contractPane();
    if (!root) return;
    var section = root.querySelector('#contract-conclusion-section');
    if (!section) return;
    restoreContractAssetText(section);
    restoreContractSectionText(section);
    applyRowGrouping(section);
    if (window.__contractAssetCollapsed) {
      collapseParticipationAssets(section);
      var assetToggle = section.querySelector('#contract-asset-toggle');
      if (assetToggle) {
        assetToggle.classList.add('active');
        var aIcon = assetToggle.querySelector('i');
        if (aIcon) aIcon.className = 'bi bi-arrows-expand';
      }
    } else if (window.__contractSectionCollapsed) {
      collapseParticipationSections(section);
      var sectionToggle = section.querySelector('#contract-section-toggle');
      if (sectionToggle) {
        sectionToggle.classList.add('active');
        var sIcon = sectionToggle.querySelector('i');
        if (sIcon) sIcon.className = 'bi bi-arrows-expand';
      }
    }
  }

  function toggleContractCollapse() {
    var root = contractPane();
    if (!root) return;
    var section = root.querySelector('#contract-conclusion-section');
    if (!section) return;
    var toggle = section.querySelector('#contract-section-toggle');
    var collapsed = !!window.__contractSectionCollapsed;
    if (window.__contractAssetCollapsed) {
      window.__contractSectionCollapsed = !collapsed;
      if (toggle) {
        toggle.classList.toggle('active', !collapsed);
        var icon = toggle.querySelector('i');
        if (icon) icon.className = !collapsed ? 'bi bi-arrows-expand' : 'bi bi-arrows-collapse';
      }
      saveCollapsePrefs();
      return;
    }
    if (collapsed) {
      restoreContractSectionText(section);
      applyRowGrouping(section);
      window.__contractSectionCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
    } else {
      collapseParticipationSections(section);
      window.__contractSectionCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    updateContractState();
    saveCollapsePrefs();
  }

  function toggleContractAssetCollapse() {
    var root = contractPane();
    if (!root) return;
    var section = root.querySelector('#contract-conclusion-section');
    if (!section) return;
    var toggle = section.querySelector('#contract-asset-toggle');
    var collapsed = !!window.__contractAssetCollapsed;
    if (collapsed) {
      restoreContractAssetText(section);
      applyRowGrouping(section);
      window.__contractAssetCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
      if (window.__contractSectionCollapsed) {
        collapseParticipationSections(section);
        var sectionToggle = section.querySelector('#contract-section-toggle');
        if (sectionToggle) {
          sectionToggle.classList.add('active');
          var sIcon = sectionToggle.querySelector('i');
          if (sIcon) sIcon.className = 'bi bi-arrows-expand';
        }
      }
    } else {
      if (window.__contractSectionCollapsed) {
        restoreContractSectionText(section);
        applyRowGrouping(section);
      }
      collapseParticipationAssets(section);
      window.__contractAssetCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    updateContractState();
    saveCollapsePrefs();
  }

  function restoreInfoRequestSectionText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__infoRequestProjectFilter || [];
    var showAll = !filterValues.length || (filterValues.length === 1 && filterValues[0] === '');
    rows.forEach(function(row) {
      var td = row.querySelector('.cell-typical-val');
      if (td && td.dataset.originalTypical !== undefined) {
        td.innerHTML = td.dataset.originalTypical;
        delete td.dataset.originalTypical;
      }
      if (row.classList.contains('section-collapsed')) {
        row.classList.remove('section-collapsed');
        var pid = row.dataset.projectId || '';
        if (showAll || filterValues.indexOf(pid) !== -1) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function restoreInfoRequestAssetText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__infoRequestProjectFilter || [];
    var showAll = !filterValues.length || (filterValues.length === 1 && filterValues[0] === '');
    rows.forEach(function(row) {
      var assetTd = row.querySelector('.cell-asset-val');
      if (assetTd && assetTd.dataset.originalAsset !== undefined) {
        assetTd.innerHTML = assetTd.dataset.originalAsset;
        delete assetTd.dataset.originalAsset;
      }
      var typicalTd = row.querySelector('.cell-typical-val');
      if (typicalTd && typicalTd.dataset.originalTypicalAsset !== undefined) {
        typicalTd.innerHTML = typicalTd.dataset.originalTypicalAsset;
        delete typicalTd.dataset.originalTypicalAsset;
      }
      if (row.classList.contains('asset-collapsed')) {
        row.classList.remove('asset-collapsed');
        var pid = row.dataset.projectId || '';
        if (showAll || filterValues.indexOf(pid) !== -1) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function reapplyInfoRequestCollapse() {
    if (!window.__infoRequestSectionCollapsed && !window.__infoRequestAssetCollapsed) return;
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#info-request-approval-section');
    if (!section) return;
    restoreInfoRequestAssetText(section);
    restoreInfoRequestSectionText(section);
    applyRowGrouping(section);
    if (window.__infoRequestAssetCollapsed) {
      collapseParticipationAssets(section);
      var assetToggle = section.querySelector('#info-request-asset-toggle');
      if (assetToggle) {
        assetToggle.classList.add('active');
        var aIcon = assetToggle.querySelector('i');
        if (aIcon) aIcon.className = 'bi bi-arrows-expand';
      }
    } else if (window.__infoRequestSectionCollapsed) {
      collapseParticipationSections(section);
      var sectionToggle = section.querySelector('#info-request-section-toggle');
      if (sectionToggle) {
        sectionToggle.classList.add('active');
        var sIcon = sectionToggle.querySelector('i');
        if (sIcon) sIcon.className = 'bi bi-arrows-expand';
      }
    }
  }

  function toggleInfoRequestCollapse() {
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#info-request-approval-section');
    if (!section) return;
    var toggle = section.querySelector('#info-request-section-toggle');
    var collapsed = !!window.__infoRequestSectionCollapsed;
    if (window.__infoRequestAssetCollapsed) {
      window.__infoRequestSectionCollapsed = !collapsed;
      if (toggle) {
        toggle.classList.toggle('active', !collapsed);
        var icon = toggle.querySelector('i');
        if (icon) icon.className = !collapsed ? 'bi bi-arrows-expand' : 'bi bi-arrows-collapse';
      }
      saveCollapsePrefs();
      return;
    }
    if (collapsed) {
      restoreInfoRequestSectionText(section);
      applyRowGrouping(section);
      window.__infoRequestSectionCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
    } else {
      collapseParticipationSections(section);
      window.__infoRequestSectionCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    updateInfoRequestState();
    saveCollapsePrefs();
  }

  function toggleInfoRequestAssetCollapse() {
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#info-request-approval-section');
    if (!section) return;
    var toggle = section.querySelector('#info-request-asset-toggle');
    var collapsed = !!window.__infoRequestAssetCollapsed;
    if (collapsed) {
      restoreInfoRequestAssetText(section);
      applyRowGrouping(section);
      window.__infoRequestAssetCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
      if (window.__infoRequestSectionCollapsed) {
        collapseParticipationSections(section);
        var sectionToggle = section.querySelector('#info-request-section-toggle');
        if (sectionToggle) {
          sectionToggle.classList.add('active');
          var sIcon = sectionToggle.querySelector('i');
          if (sIcon) sIcon.className = 'bi bi-arrows-expand';
        }
      }
    } else {
      if (window.__infoRequestSectionCollapsed) {
        restoreInfoRequestSectionText(section);
        applyRowGrouping(section);
      }
      collapseParticipationAssets(section);
      window.__infoRequestAssetCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    updateInfoRequestState();
    saveCollapsePrefs();
  }

  function initParticipationProjectFilter() {
    const root = pane();
    if (!root) return;

    const FILTER_ALL = '__all__';
    window.__participationProjectFilter = window.__participationProjectFilter || [FILTER_ALL];

    const dropdown = root.querySelector('#participation-project-filter-toggle')?.closest('.dropdown');
    const checks = root.querySelectorAll('.js-participation-filter');
    const label = root.querySelector('.js-participation-filter-label');
    const master = root.querySelector('#participation-master');

    if (!dropdown || !checks.length || !label || dropdown.dataset.bound === '1') return;
    dropdown.dataset.bound = '1';
    window.bindProjectFilterMenuWidth(dropdown);

    function syncCheckboxes(values) {
      const set = new Set(values);
      checks.forEach((cb) => {
        cb.checked = set.has(cb.value);
      });
    }

    function updateLabel(values) {
      if (values.includes(FILTER_ALL) || !values.length) {
        label.textContent = 'Все';
        return;
      }
      if (values.length === 1) {
        const input = Array.from(checks).find((cb) => cb.value === values[0]);
        label.textContent = window.getProjectFilterSummaryLabel(input, '1 проект');
        return;
      }
      label.textContent = `${values.length} выбрано`;
    }

    function applyFilter(values) {
      window.__participationProjectFilter = values.slice();
      const showAll = values.includes(FILTER_ALL) || !values.length;
      getParticipationRows().forEach((row) => {
        const pid = row.dataset.projectId || '';
        const visible = showAll || values.includes(pid);
        row.classList.toggle('d-none', !visible);
        if (!visible) {
          const checkbox = row.querySelector('input[name="participation-select"]');
          if (checkbox) checkbox.checked = false;
        }
      });
      if (master && !showAll && !getParticipationRows().some((row) => !row.classList.contains('d-none'))) {
        master.checked = false;
        master.indeterminate = false;
      }
      updateLabel(values);
      updateParticipationState();
      applyRowGrouping(root.querySelector('#participation-confirmation-section'));
      applyParticipationSentState();
      reapplyParticipationCollapse();
    }

    function normalizeSelection() {
      let values = Array.from(checks)
        .filter((cb) => cb.checked)
        .map((cb) => cb.value);

      if (!values.length) values = [FILTER_ALL];
      if (values.includes(FILTER_ALL)) values = [FILTER_ALL];

      syncCheckboxes(values);
      return values;
    }

    checks.forEach((cb) => {
      cb.addEventListener('change', (event) => {
        const value = event.target.value;
        if (value === FILTER_ALL && event.target.checked) {
          syncCheckboxes([FILTER_ALL]);
          applyFilter([FILTER_ALL]);
          return;
        }

        if (value === FILTER_ALL && !event.target.checked) {
          const firstProject = Array.from(checks).find((item) => item.value !== FILTER_ALL);
          if (firstProject) firstProject.checked = true;
        } else {
          const allCheckbox = root.querySelector('#participation-filter-all');
          if (allCheckbox && allCheckbox.checked) allCheckbox.checked = false;
        }

        applyFilter(normalizeSelection());
      });
    });

    window.__syncParticipationProjectFilter = function(values) {
      var isAll = values[0] === FILTER_ALL;
      var isSingle = !isAll && values.length === 1;
      var set = new Set(values);
      checks.forEach(function(cb) {
        if (isAll) { cb.checked = cb.value === FILTER_ALL; cb.disabled = false; }
        else if (isSingle) { cb.checked = cb.value === values[0]; cb.disabled = true; }
        else {
          if (cb.value === FILTER_ALL) { cb.checked = true; cb.disabled = false; }
          else { cb.checked = set.has(cb.value); cb.disabled = !set.has(cb.value); }
        }
      });
      applyFilter(isAll ? [FILTER_ALL] : values.slice());
    };

    const initialValues = window.__participationProjectFilter && window.__participationProjectFilter.length
      ? window.__participationProjectFilter
      : [FILTER_ALL];
    syncCheckboxes(initialValues);
    applyFilter(initialValues);
  }

  function initInfoRequestProjectFilter() {
    const root = pane();
    if (!root) return;

    window.__infoRequestProjectFilter = window.__infoRequestProjectFilter || [];

    const dropdown = root.querySelector('#info-request-project-filter-toggle')?.closest('.dropdown');
    const radios = root.querySelectorAll('.js-info-request-filter');
    const label = root.querySelector('.js-info-request-filter-label');
    const master = root.querySelector('#info-request-master');

    if (!dropdown || !radios.length || !label || dropdown.dataset.bound === '1') return;
    dropdown.dataset.bound = '1';
    window.bindProjectFilterMenuWidth(dropdown);
    window.bindProjectFilterMenuPortal(dropdown);

    function applyFilter(projectId) {
      window.__infoRequestProjectFilter = projectId ? [projectId] : [];
      getInfoRequestRows().forEach((row) => {
        const pid = row.dataset.projectId || '';
        const visible = projectId && pid === projectId;
        row.classList.toggle('d-none', !visible);
        if (!visible) {
          const checkbox = row.querySelector('input[name="info-request-select"]');
          if (checkbox) checkbox.checked = false;
        }
      });
      if (master) {
        master.checked = false;
        master.indeterminate = false;
      }
      const selected = Array.from(radios).find((r) => r.checked);
      label.textContent = (selected && selected.value)
        ? window.getProjectFilterSummaryLabel(selected, '—')
        : 'Не выбран';
      updateInfoRequestState();
      applyRowGrouping(root.querySelector('#info-request-approval-section'));
      reapplyInfoRequestCollapse();
    }

    function selectProject(projectId) {
      radios.forEach((r) => { r.checked = r.value === projectId; });
      applyFilter(projectId);
    }

    window.__syncInfoRequestFilter = selectProject;

    radios.forEach((r) => {
      r.addEventListener('change', () => {
        if (r.checked) applyFilter(r.value);
      });
    });

    const saved = window.__infoRequestProjectFilter;
    if (saved && saved.length === 1 && saved[0] !== '__all__' && saved[0] !== '') {
      const target = Array.from(radios).find((r) => r.value === saved[0]);
      if (target) {
        target.checked = true;
        applyFilter(saved[0]);
        return;
      }
    }
    selectProject('');
  }

  function initPaymentRequestProjectFilter() {
    getPaymentRequestSections().forEach(initPaymentRequestProjectFilterSection);
  }

  function initPaymentRequestProjectFilterSection(section) {
    const FILTER_ALL = '__all__';
    if (!section) return;

    window.__paymentRequestsProjectFilter = window.__paymentRequestsProjectFilter || [FILTER_ALL];

    const dropdown = section.querySelector('.js-payment-request-filter')?.closest('.dropdown');
    const checks = section.querySelectorAll('.js-payment-request-filter');
    const label = section.querySelector('.js-payment-request-filter-label');
    const master = getPaymentRequestMaster(section);

    if (!dropdown || !checks.length || !label || dropdown.dataset.bound === '1') return;
    dropdown.dataset.bound = '1';
    window.bindProjectFilterMenuWidth(dropdown);
    window.bindProjectFilterMenuPortal(dropdown);

    function normalizeValues(values) {
      values = Array.isArray(values) && values.length ? values.slice() : [FILTER_ALL];
      if (values.includes(FILTER_ALL)) return [FILTER_ALL];
      return values;
    }

    function syncChecks(values) {
      const set = new Set(normalizeValues(values));
      checks.forEach((cb) => { cb.checked = set.has(cb.value); });
    }

    function updateLabel(values) {
      const normalized = normalizeValues(values);
      if (normalized.includes(FILTER_ALL) || !normalized.length) {
        label.textContent = 'Все';
        return;
      }
      if (normalized.length === 1) {
        const selected = Array.from(checks).find((cb) => cb.value === normalized[0]);
        label.textContent = selected
          ? window.getProjectFilterSummaryLabel(selected, '1 проект')
          : '1 проект';
        return;
      }
      label.textContent = normalized.length + ' выбрано';
    }

    function filterRows(values) {
      const normalized = normalizeValues(values);
      window.__paymentRequestsProjectFilter = normalized;
      const showAll = normalized.includes(FILTER_ALL) || !normalized.length;
      const selectedProjects = new Set(normalized);
      getPaymentRequestSections().forEach((paymentSection) => {
        getPaymentRequestRows(paymentSection).forEach((row) => {
          const pid = row.dataset.projectId || '';
          const visible = showAll || selectedProjects.has(pid);
          row.classList.toggle('d-none', !visible);
          if (!visible) {
            const checkbox = row.querySelector('input[name="payment-request-select"]');
            if (checkbox) checkbox.checked = false;
          }
        });
        const sectionMaster = getPaymentRequestMaster(paymentSection);
        if (sectionMaster) {
          sectionMaster.checked = false;
          sectionMaster.indeterminate = false;
        }
      });
      updatePaymentRequestState();
    }

    function applyFilter(values) {
      const normalized = normalizeValues(values);
      checks.forEach((cb) => { cb.disabled = false; });
      syncChecks(normalized);
      updateLabel(normalized);
      filterRows(normalized);
    }

    function normalizeSelection() {
      let values = Array.from(checks)
        .filter((cb) => cb.checked && !cb.disabled)
        .map((cb) => cb.value);
      if (!values.length) values = [FILTER_ALL];
      if (values.includes(FILTER_ALL)) values = [FILTER_ALL];
      return values;
    }

    window.__syncPaymentRequestFilter = function(values) {
      const source = normalizeValues(values);
      const isAll = source[0] === FILTER_ALL;
      const set = new Set(source);
      getPaymentRequestSections().forEach((paymentSection) => {
        const sectionChecks = paymentSection.querySelectorAll('.js-payment-request-filter');
        const sectionLabel = paymentSection.querySelector('.js-payment-request-filter-label');
        sectionChecks.forEach((cb) => {
          cb.checked = isAll ? cb.value === FILTER_ALL : set.has(cb.value);
          cb.disabled = false;
        });
        if (!sectionLabel) return;
        if (isAll) {
          sectionLabel.textContent = 'Все';
        } else if (source.length === 1) {
          const selected = Array.from(sectionChecks).find((cb) => cb.value === source[0]);
          sectionLabel.textContent = window.getProjectFilterSummaryLabel(selected, '1 проект');
        } else {
          sectionLabel.textContent = source.length + ' выбрано';
        }
      });
      filterRows(isAll ? [FILTER_ALL] : source);
    };

    checks.forEach((cb) => {
      cb.addEventListener('change', (event) => {
        const value = event.target.value;
        if (value === FILTER_ALL && event.target.checked) {
          applyFilter([FILTER_ALL]);
          return;
        }
        if (value === FILTER_ALL && !event.target.checked) {
          const firstProject = Array.from(checks).find((item) => item.value !== FILTER_ALL);
          if (firstProject) firstProject.checked = true;
        } else {
          const allCheckbox = Array.from(checks).find((item) => item.value === FILTER_ALL);
          if (allCheckbox && allCheckbox.checked) allCheckbox.checked = false;
        }
        applyFilter(normalizeSelection());
      });
    });

    applyFilter(window.__paymentRequestsProjectFilter);
  }

  var REPORT_SUBMISSION_COLPICKER = {
    prefKey: 'reports:hiddenCols',
    wrapId: 'report-submission-colpicker-wrap',
    btnId: 'report-submission-colpicker-btn',
    menuId: 'report-submission-colpicker-menu',
    allId: 'report-submission-col-all',
    tableId: 'report-submission-table',
    hidden: null,
  };

  function getReportSubmissionSection() {
    return pane()?.querySelector('#report-submission-section') || null;
  }

  function getReportSubmissionDefaultHiddenColumns() {
    var menu = document.getElementById(REPORT_SUBMISSION_COLPICKER.menuId);
    var hidden = {};
    if (!menu) return hidden;
    menu.querySelectorAll('input.form-check-input[data-default-hidden="true"]:not([value="all"])').forEach(function(cb) {
      hidden[cb.value] = true;
    });
    return hidden;
  }

  function getReportSubmissionHiddenColumns() {
    var cfg = REPORT_SUBMISSION_COLPICKER;
    if (!cfg.hidden) {
      var saved = window.UIPref ? UIPref.get(cfg.prefKey, null) : null;
      if (saved && typeof saved === 'object' && !Array.isArray(saved)) {
        cfg.hidden = saved;
      } else if (document.getElementById(cfg.menuId)) {
        cfg.hidden = getReportSubmissionDefaultHiddenColumns();
      }
    }
    return cfg.hidden || {};
  }

  function saveReportSubmissionHiddenColumns() {
    if (window.UIPref) UIPref.set(REPORT_SUBMISSION_COLPICKER.prefKey, getReportSubmissionHiddenColumns());
  }

  function updateReportSubmissionColPickerLabel(btn, menu) {
    var cbs = qa('input.form-check-input:not([value="all"])', menu);
    var checked = cbs.filter(function(cb) { return cb.checked; }).length;
    btn.textContent = checked === cbs.length ? 'Все поля' : checked + ' из ' + cbs.length;
  }

  var REPORT_FIXED_COLUMN_WIDTHS = { checkbox: 30, stage: 105 };
  var REPORT_CHECK_RESULT_FLOOR_REM = 40;
  var reportColumnLayoutCache = null;
  var reportColumnLayoutQueued = false;
  var reportColumnLayoutNeedsMeasure = false;
  var reportColumnLayoutObserver = null;
  var reportColumnLayoutObserved = null;

  function reportCheckResultFloorPx() {
    var root = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    return Math.ceil(REPORT_CHECK_RESULT_FLOOR_REM * root);
  }

  function reportSubmissionColumnKey(col) {
    if (!col) return '';
    if (col.classList.contains('col-checkbox')) return 'checkbox';
    return col.getAttribute('data-col') || '';
  }

  function reportSubmissionColumnElements(table, key) {
    if (key === 'checkbox') {
      return {
        col: table.querySelector('col.col-checkbox'),
        th: table.querySelector('thead th.col-checkbox'),
      };
    }
    return {
      col: table.querySelector('col[data-col="' + key + '"]'),
      th: table.querySelector('thead th[data-col="' + key + '"]'),
    };
  }

  function clearReportSubmissionAssignedWidths(table) {
    table.style.removeProperty('width');
    table.style.removeProperty('min-width');
    table.style.removeProperty('table-layout');
    table.querySelectorAll('col, thead th, tbody td').forEach(function(el) {
      el.style.removeProperty('width');
      el.style.removeProperty('min-width');
      el.style.removeProperty('max-width');
    });
  }

  function assignReportSubmissionColumnWidth(el, width, minWidth) {
    if (!el) return;
    var floor = minWidth == null ? width : minWidth;
    el.style.setProperty('width', width + 'px', 'important');
    el.style.setProperty('min-width', floor + 'px', 'important');
    el.style.setProperty('max-width', width + 'px', 'important');
  }

  function reportSubmissionColumnHidden(th) {
    if (!th) return true;
    if (th.style.display === 'none') return true;
    return getComputedStyle(th).display === 'none';
  }

  function measureReportSubmissionColumns(table) {
    clearReportSubmissionAssignedWidths(table);
    var floor = reportCheckResultFloorPx();
    table.querySelectorAll(
      'col.col-report-check-result, thead th.report-check-result-col, tbody td.report-check-result-cell'
    ).forEach(function(el) {
      assignReportSubmissionColumnWidth(el, floor);
    });
    table.style.setProperty('width', 'max-content', 'important');
    table.style.setProperty('min-width', '0', 'important');
    table.style.setProperty('table-layout', 'auto', 'important');
    return Array.from(table.querySelectorAll('colgroup col')).map(function(col) {
      var key = reportSubmissionColumnKey(col);
      var nodes = reportSubmissionColumnElements(table, key);
      var hidden = reportSubmissionColumnHidden(nodes.th);
      var fixed = REPORT_FIXED_COLUMN_WIDTHS[key] || 0;
      var min = 0;
      if (!hidden) {
        if (fixed) min = fixed;
        else if (key === 'check-result') min = floor;
        else min = Math.floor(nodes.th.getBoundingClientRect().width);
      }
      return { key: key, hidden: hidden, fixed: fixed, min: min };
    });
  }

  function reportSubmissionColumnNodes(table, key) {
    var nodes = reportSubmissionColumnElements(table, key);
    var cells = key === 'checkbox'
      ? table.querySelectorAll('tbody td.report-select-cell')
      : table.querySelectorAll('tbody td[data-col="' + key + '"]');
    return [nodes.col, nodes.th].concat(Array.from(cells));
  }

  var REPORT_FIT_SLACK_PX = 2;
  var REPORT_FIT_SLOP_PX = 48;

  function applyReportSubmissionColumnWidths(table, columns, available) {
    var visible = columns.filter(function(column) { return !column.hidden && column.min > 0; });
    var flex = visible.filter(function(column) { return !column.fixed; });
    var fixedSum = 0;
    var flexMin = 0;
    visible.forEach(function(column) {
      if (column.fixed) fixedSum += column.fixed;
      else flexMin += column.min;
    });
    var delta = available - fixedSum - flexMin;
    var fitting = delta >= -REPORT_FIT_SLOP_PX;
    var target = fitting ? Math.max(fixedSum + flex.length, available - REPORT_FIT_SLACK_PX) : available;
    var room = fitting ? target - fixedSum - flexMin : 0;
    var count = flex.length;
    var base = count ? Math.trunc(room / count) : 0;
    var remainder = count ? Math.abs(room - base * count) : 0;
    var flexIndex = 0;
    var total = 0;
    columns.forEach(function(column) {
      var nodes = reportSubmissionColumnNodes(table, column.key);
      if (column.hidden || column.min <= 0) {
        nodes.forEach(function(el) {
          if (!el) return;
          el.style.removeProperty('width');
          el.style.removeProperty('min-width');
          el.style.removeProperty('max-width');
        });
        return;
      }
      var width = column.fixed ? column.fixed : column.min;
      if (!column.fixed && count) {
        width += base;
        if (flexIndex < remainder) width += room >= 0 ? 1 : -1;
        if (width < 1) width = 1;
        flexIndex += 1;
      }
      var floor = column.fixed ? width : Math.min(column.min, width);
      nodes.forEach(function(el) { assignReportSubmissionColumnWidth(el, width, floor); });
      total += width;
    });
    table.style.setProperty('table-layout', 'fixed', 'important');
    if (fitting) {
      var fitted = 'calc(100% - ' + REPORT_FIT_SLACK_PX + 'px)';
      table.style.setProperty('width', fitted, 'important');
      table.style.setProperty('max-width', fitted, 'important');
      table.style.setProperty('min-width', '0', 'important');
    } else {
      table.style.setProperty('width', total + 'px', 'important');
      table.style.setProperty('min-width', total + 'px', 'important');
      table.style.setProperty('max-width', 'none', 'important');
    }
    return fitting;
  }

  function reportSubmissionWrapOverflow(wrap) {
    var overflow = wrap.scrollWidth - wrap.clientWidth;
    if (overflow > 0) return Math.ceil(overflow);
    var style = getComputedStyle(wrap);
    var borderY = (parseFloat(style.borderTopWidth) || 0) + (parseFloat(style.borderBottomWidth) || 0);
    if (wrap.offsetHeight - wrap.clientHeight - borderY > 2) return 1;
    return 0;
  }

  function suppressReportSubmissionPhantomScroll(wrap, fitting) {
    if (!fitting) {
      wrap.style.overflowX = '';
      return;
    }
    var overflow = reportSubmissionWrapOverflow(wrap);
    wrap.style.overflowX = overflow > 0 && overflow <= REPORT_FIT_SLOP_PX ? 'hidden' : '';
  }

  function reportSubmissionLayoutSignature(table) {
    var hiddenKey = Object.keys(getReportSubmissionHiddenColumns()).sort().join(',');
    var fontSize = getComputedStyle(document.documentElement).fontSize;
    var body = table.tBodies && table.tBodies[0];
    var content = body ? body.textContent.length : 0;
    var zoom = Math.round((window.devicePixelRatio || 1) * 100);
    return table.id + '|' + fontSize + '|' + zoom + '|' + hiddenKey + '|' + content;
  }

  function ensureReportSubmissionColumnLayoutObserver() {
    var wrap = document.querySelector('#report-submission-section .report-submission-table-wrap');
    if (!wrap || typeof ResizeObserver === 'undefined') return;
    if (reportColumnLayoutObserved === wrap) return;
    if (reportColumnLayoutObserver) reportColumnLayoutObserver.disconnect();
    reportColumnLayoutObserver = new ResizeObserver(function() {
      scheduleReportSubmissionColumnLayout(false);
    });
    reportColumnLayoutObserver.observe(wrap);
    reportColumnLayoutObserved = wrap;
  }

  function layoutReportSubmissionColumns(forceMeasure) {
    var table = document.getElementById(REPORT_SUBMISSION_COLPICKER.tableId);
    var wrap = table && table.closest('.report-submission-table-wrap');
    if (!table || !wrap) return;
    ensureReportSubmissionColumnLayoutObserver();
    var available = wrap.clientWidth;
    if (available < 1) return;
    var signature = reportSubmissionLayoutSignature(table);
    var cache = reportColumnLayoutCache;
    var canReuse = !forceMeasure && cache && cache.signature === signature && cache.table === table;
    if (canReuse && cache.available === available && reportSubmissionWrapOverflow(wrap) <= 0) return;
    var columns = canReuse ? cache.columns : measureReportSubmissionColumns(table);
    var fitting = applyReportSubmissionColumnWidths(table, columns, available);
    suppressReportSubmissionPhantomScroll(wrap, fitting);
    reportColumnLayoutCache = {
      table: table,
      signature: signature,
      columns: columns,
      available: available,
    };
    schedulePaymentRequestScrollGapsUpdate();
  }

  function scheduleReportSubmissionColumnLayout(forceMeasure) {
    if (forceMeasure) reportColumnLayoutNeedsMeasure = true;
    if (reportColumnLayoutQueued) return;
    reportColumnLayoutQueued = true;
    window.requestAnimationFrame(function() {
      reportColumnLayoutQueued = false;
      var measure = reportColumnLayoutNeedsMeasure;
      reportColumnLayoutNeedsMeasure = false;
      layoutReportSubmissionColumns(measure);
    });
  }

  function applyReportSubmissionColumnVisibility() {
    var table = document.getElementById(REPORT_SUBMISSION_COLPICKER.tableId);
    if (!table) return;
    var hidden = Object.keys(getReportSubmissionHiddenColumns());
    table.querySelectorAll('[data-col]').forEach(function(cell) {
      cell.style.display = hidden.indexOf(cell.getAttribute('data-col')) !== -1 ? 'none' : '';
    });
    scheduleReportSubmissionColumnLayout(true);
  }

  function initReportSubmissionColPicker() {
    var cfg = REPORT_SUBMISSION_COLPICKER;
    var wrap = document.getElementById(cfg.wrapId);
    var btn = document.getElementById(cfg.btnId);
    var menu = document.getElementById(cfg.menuId);
    if (!wrap || !btn || !menu) return;

    btn.onclick = function(event) {
      event.stopPropagation();
      menu.classList.toggle('show');
    };

    var cbs = qa('input.form-check-input:not([value="all"])', menu);
    var hiddenState = getReportSubmissionHiddenColumns();
    cbs.forEach(function(cb) {
      cb.checked = !hiddenState[cb.value];
    });

    var allCb = document.getElementById(cfg.allId);
    if (allCb) allCb.checked = cbs.every(function(cb) { return cb.checked; });

    updateReportSubmissionColPickerLabel(btn, menu);
    applyReportSubmissionColumnVisibility();

    menu.onchange = function(event) {
      var cb = event.target;
      if (!cb.classList || !cb.classList.contains('form-check-input')) return;
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
      saveReportSubmissionHiddenColumns();
      updateReportSubmissionColPickerLabel(btn, menu);
      applyReportSubmissionColumnVisibility();
    };
  }

  document.addEventListener('click', function(event) {
    var wrap = document.getElementById(REPORT_SUBMISSION_COLPICKER.wrapId);
    var menu = document.getElementById(REPORT_SUBMISSION_COLPICKER.menuId);
    if (wrap && menu && !wrap.contains(event.target)) menu.classList.remove('show');
  });

  function getReportSubmissionRows() {
    const section = getReportSubmissionSection();
    if (!section) return [];
    return Array.from(section.querySelectorAll('#report-submission-table tbody tr[data-project-id]'));
  }

  function getVisibleReportSelectChecks() {
    return getReportSubmissionRows()
      .filter(function(row) {
        return !row.classList.contains('d-none')
          && !row.classList.contains('report-version-row-collapsed-hidden');
      })
      .map(function(row) { return row.querySelector('input[name="report-select"]'); })
      .filter(function(checkbox) { return checkbox && !checkbox.disabled; });
  }

  function updateReportSubmissionMasterState() {
    const section = getReportSubmissionSection();
    if (!section) return;
    const master = section.querySelector('#report-submission-master');
    if (!master || master.disabled) return;
    const checks = getVisibleReportSelectChecks();
    const checked = checks.filter((checkbox) => checkbox.checked);
    master.checked = checks.length > 0 && checked.length === checks.length;
    master.indeterminate = checked.length > 0 && checked.length < checks.length;
    updateReportSendButtonState();
    updateRowHighlight('report-select');
  }

  function reportRowIsRemarksPending(row) {
    return Boolean(row && row.dataset.remarksPending === '1');
  }

  function updateReportSendButtonState() {
    const section = getReportSubmissionSection();
    if (!section) return;
    const btn = section.querySelector('#report-submission-send-btn');
    if (!btn) return;
    const checked = getVisibleReportSelectChecks().filter(function(checkbox) { return checkbox.checked; });
    const pending = checked.filter(function(checkbox) {
      return reportRowIsRemarksPending(checkbox.closest('tr'));
    });
    const regular = checked.filter(function(checkbox) {
      return !reportRowIsRemarksPending(checkbox.closest('tr'));
    });
    if (!checked.length || (pending.length && regular.length)) {
      btn.disabled = true;
      return;
    }
    if (pending.length) {
      btn.disabled = pending.some(function(checkbox) {
        return !(checkbox.closest('tr').dataset.reviewEntryId || '').trim();
      });
      return;
    }
    const selectedRow = regular.length === 1 ? regular[0].closest('tr') : null;
    const uploadId = selectedRow && (selectedRow.dataset.uploadId || '').trim();
    btn.disabled = !uploadId;
  }

  function getReportCheckSection() {
    return pane()?.querySelector('#report-check-section') || null;
  }

  function getReportCheckRows() {
    const section = getReportCheckSection();
    if (!section) return [];
    return Array.from(section.querySelectorAll('#report-check-table tbody tr[data-edit-url]'));
  }

  function getVisibleReportCheckChecks() {
    return getReportCheckRows()
      .filter((row) => !row.classList.contains('d-none'))
      .map((row) => row.querySelector('input[name="report-check-select"]'))
      .filter((checkbox) => checkbox && !checkbox.disabled);
  }

  function updateReportCheckMasterState() {
    const section = getReportCheckSection();
    if (!section) return;
    const master = section.querySelector('#report-check-master');
    if (!master || master.disabled) return;
    const checks = getVisibleReportCheckChecks();
    const checked = checks.filter((checkbox) => checkbox.checked);
    master.checked = checks.length > 0 && checked.length === checks.length;
    master.indeterminate = checked.length > 0 && checked.length < checks.length;
  }

  function ensureReportCheckActionsVisibility() {
    const panel = pane()?.querySelector('#report-check-actions');
    if (!panel) return;
    const any = getVisibleReportCheckChecks().some((checkbox) => checkbox.checked);
    panel.classList.toggle('d-none', !any);
    panel.classList.toggle('d-flex', any);
  }

  function getReportMacrosSection() {
    return pane()?.querySelector('#report-macros-section') || null;
  }

  function reportMacrosListQuery() {
    const section = getReportMacrosSection();
    const params = new URLSearchParams();
    params.set('macros_page', section?.dataset.macrosPage || '1');
    params.set('macros_page_size', section?.dataset.macrosPageSize || '25');
    return '?' + params.toString();
  }

  function getReportMacroRows() {
    const section = getReportMacrosSection();
    if (!section) return [];
    return Array.from(section.querySelectorAll('#report-macros-table tbody tr[data-edit-url]'));
  }

  function getVisibleReportMacroChecks() {
    return getReportMacroRows()
      .filter((row) => !row.classList.contains('d-none'))
      .map((row) => row.querySelector('input[name="report-macro-select"]'))
      .filter((checkbox) => checkbox && !checkbox.disabled);
  }

  function updateReportMacrosMasterState() {
    const section = getReportMacrosSection();
    if (!section) return;
    const master = section.querySelector('#report-macros-master');
    if (!master || master.disabled) return;
    const checks = getVisibleReportMacroChecks();
    const checked = checks.filter((checkbox) => checkbox.checked);
    master.checked = checks.length > 0 && checked.length === checks.length;
    master.indeterminate = checked.length > 0 && checked.length < checks.length;
  }

  function ensureReportMacrosActionsVisibility() {
    const panel = pane()?.querySelector('#report-macros-actions');
    if (!panel) return;
    const any = getVisibleReportMacroChecks().some((checkbox) => checkbox.checked);
    panel.classList.toggle('d-none', !any);
    panel.classList.toggle('d-flex', any);
  }

  function initReportSubmissionProjectFilter() {
    const root = pane();
    if (!root) return;
    const FILTER_ALL = '__all__';
    window.__reportSubmissionProjectFilter = window.__reportSubmissionProjectFilter || [FILTER_ALL];

    const dropdown = root.querySelector('#report-submission-project-filter-toggle')?.closest('.dropdown');
    const checks = root.querySelectorAll('.js-report-submission-filter');
    const label = root.querySelector('.js-report-submission-filter-label');
    if (!dropdown || !checks.length || !label || dropdown.dataset.bound === '1') return;
    dropdown.dataset.bound = '1';
    if (window.bindProjectFilterMenuWidth) window.bindProjectFilterMenuWidth(dropdown);

    function syncCheckboxes(values) {
      const set = new Set(values);
      checks.forEach((cb) => { cb.checked = set.has(cb.value); });
    }

    function updateLabel(values) {
      if (values.includes(FILTER_ALL) || !values.length) {
        label.textContent = 'Все';
        return;
      }
      if (values.length === 1) {
        const selected = Array.from(checks).find((cb) => cb.value === values[0]);
        label.textContent = selected
          ? window.getProjectFilterSummaryLabel(selected, '1 проект')
          : '1 проект';
        return;
      }
      label.textContent = values.length + ' выбрано';
    }

    function reportFilterIsSpecific(values) {
      const filter = values || window.__reportSubmissionProjectFilter || [FILTER_ALL];
      return filter.length > 0 && !filter.includes(FILTER_ALL);
    }

    function maxReportPageSize() {
      const select = document.querySelector('#policy-page-size-report-submission');
      if (!select || !select.options.length) return '100';
      return select.options[select.options.length - 1].value;
    }

    function reportPageSizeForRequest() {
      if (reportFilterIsSpecific()) return maxReportPageSize();
      return window.__reportSubmissionPageSize || '25';
    }

    function reportSubmissionTableUrl(page) {
      const block = document.querySelector('#report-submission-table-block');
      if (!block) return '';
      const params = new URLSearchParams();
      params.set('page', String(page || '1'));
      params.set('page_size', reportPageSizeForRequest());
      const filter = window.__reportSubmissionProjectFilter || [FILTER_ALL];
      if (reportFilterIsSpecific(filter)) {
        filter.forEach((id) => params.append('project', id));
      }
      return (block.dataset.reportsTableUrl || '') + '?' + params.toString();
    }

    function reloadReportSubmissionTable(page) {
      const url = reportSubmissionTableUrl(page || '1');
      if (!url || !window.htmx) return;
      window.htmx.ajax('GET', url, {
        target: '#report-submission-table-block',
        swap: 'outerHTML',
      });
    }

    function reportBlockMatchesFilter(values) {
      const block = document.querySelector('#report-submission-table-block');
      if (!block) return true;
      const rendered = (block.dataset.reportsProjects || FILTER_ALL).split(',').filter(Boolean).sort();
      const wanted = (!values.length || values.includes(FILTER_ALL))
        ? [FILTER_ALL]
        : values.map(String).slice().sort();
      return rendered.length === wanted.length && rendered.every((value, index) => value === wanted[index]);
    }

    function applyFilter(values, options) {
      options = options || {};
      const block = document.querySelector('#report-submission-table-block');
      const rendered = block?.dataset.reportsProjects || FILTER_ALL;
      if (block && rendered === FILTER_ALL && block.dataset.reportsPageSize) {
        window.__reportSubmissionPageSize = block.dataset.reportsPageSize;
      }
      window.__reportSubmissionProjectFilter = values.slice();
      updateLabel(values);
      if (options.reload) reloadReportSubmissionTable('1');
    }

    function normalizeSelection() {
      let values = Array.from(checks)
        .filter((cb) => cb.checked)
        .map((cb) => cb.value);
      if (!values.length) values = [FILTER_ALL];
      if (values.includes(FILTER_ALL)) values = [FILTER_ALL];
      syncCheckboxes(values);
      return values;
    }

    checks.forEach((cb) => {
      cb.addEventListener('change', (event) => {
        const value = event.target.value;
        if (value === FILTER_ALL && event.target.checked) {
          syncCheckboxes([FILTER_ALL]);
          applyFilter([FILTER_ALL], { reload: true });
          return;
        }
        if (value === FILTER_ALL && !event.target.checked) {
          const firstProject = Array.from(checks).find((item) => item.value !== FILTER_ALL);
          if (firstProject) firstProject.checked = true;
        } else {
          const allCheckbox = root.querySelector('#report-submission-filter-all');
          if (allCheckbox && allCheckbox.checked) allCheckbox.checked = false;
        }
        applyFilter(normalizeSelection(), { reload: true });
      });
    });

    window.__syncReportSubmissionProjectFilter = function(values) {
      var isAll = values[0] === FILTER_ALL;
      var isSingle = !isAll && values.length === 1;
      var set = new Set(values);
      checks.forEach(function(cb) {
        if (isAll) { cb.checked = cb.value === FILTER_ALL; cb.disabled = false; }
        else if (isSingle) { cb.checked = cb.value === values[0]; cb.disabled = true; }
        else {
          if (cb.value === FILTER_ALL) { cb.checked = true; cb.disabled = false; }
          else { cb.checked = set.has(cb.value); cb.disabled = !set.has(cb.value); }
        }
      });
      applyFilter(isAll ? [FILTER_ALL] : values.slice(), { reload: true });
    };

    const initialValues = window.__reportSubmissionProjectFilter && window.__reportSubmissionProjectFilter.length
      ? window.__reportSubmissionProjectFilter
      : [FILTER_ALL];
    syncCheckboxes(initialValues);
    applyFilter(initialValues, { reload: !reportBlockMatchesFilter(initialValues) });
  }

  function ensureReportUploadProgressModal() {
    if (document.getElementById('report-upload-progress-modal')) return;
    document.body.insertAdjacentHTML('beforeend',
      '<div class="modal fade" id="report-upload-progress-modal" tabindex="-1" aria-hidden="true" data-bs-backdrop="static" data-bs-keyboard="false">'
      + '<div class="modal-dialog"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title">Загрузка отчета</h5></div>'
      + '<div class="modal-body">'
      + '<div id="report-upload-progress"><div class="ws-progress-track"><div class="ws-progress-fill" id="report-upload-progress-bar" style="width:0%"></div></div></div>'
      + '<div id="report-upload-status" class="small mt-2"></div>'
      + '</div>'
      + '<div class="modal-footer"><button type="button" class="btn btn-outline-secondary btn-sm" id="report-upload-close-btn" data-bs-dismiss="modal" disabled>Закрыть</button></div>'
      + '</div></div></div>'
    );
  }

  function handleReportUpload(inputEl) {
    var section = getReportSubmissionSection();
    var url = section && section.dataset.reportUploadUrl;
    if (!url) return;

    var sourceSel = section.querySelector('#report-submission-source');
    var isLocal = Boolean(sourceSel && sourceSel.value === 'local');
    var file = inputEl.files && inputEl.files[0];
    if (!file) return;
    var localPath = '';
    if (isLocal) {
      var pathInput = section.querySelector('#report-submission-local-path');
      localPath = pathInput ? pathInput.value.trim() : '';
      if (!localPath) {
        ensureReportUploadProgressModal();
        var emptyModal = document.getElementById('report-upload-progress-modal');
        var emptyStatus = document.getElementById('report-upload-status');
        var emptyClose = document.getElementById('report-upload-close-btn');
        if (emptyStatus) emptyStatus.textContent = 'Укажите путь к локальной папке.';
        if (emptyClose) emptyClose.disabled = false;
        if (emptyModal && window.bootstrap) bootstrap.Modal.getOrCreateInstance(emptyModal).show();
        inputEl.value = '';
        return;
      }
    }

    ensureReportUploadProgressModal();
    var modalEl = document.getElementById('report-upload-progress-modal');
    var progressBar = document.getElementById('report-upload-progress-bar');
    var statusEl = document.getElementById('report-upload-status');
    var closeBtn = document.getElementById('report-upload-close-btn');
    if (progressBar) progressBar.style.width = '0%';
    if (statusEl) statusEl.textContent = isLocal ? 'Загрузка в локальную папку…' : '';
    if (closeBtn) closeBtn.disabled = true;
    if (modalEl && window.bootstrap) {
      bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    var fd = new FormData();
    fd.append('file', file);
    if (isLocal) {
      fd.append('source_kind', 'local');
      fd.append('local_folder_path', localPath);
    }
    if (inputEl.dataset.fullReport === '1') {
      fd.append('is_full_report', '1');
      fd.append('registration_id', inputEl.dataset.registrationId || '');
      fd.append('asset_name', inputEl.dataset.assetName || '');
      fd.append('executor', inputEl.dataset.executor || '');
    } else if (inputEl.dataset.allSections === '1') {
      fd.append('is_all_sections', '1');
      fd.append('registration_id', inputEl.dataset.registrationId || '');
      fd.append('executor', inputEl.dataset.executor || '');
      fd.append('asset_name', inputEl.dataset.assetName || '');
    } else {
      fd.append('performer_id', inputEl.dataset.performerId || '');
    }

    var xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('X-CSRFToken', csrftoken);
    xhr.upload.addEventListener('progress', function(ev) {
      if (ev.lengthComputable && progressBar) {
        progressBar.style.width = Math.round(ev.loaded / ev.total * 100) + '%';
      }
    });
    xhr.addEventListener('load', function() {
      if (progressBar) progressBar.style.width = '100%';
      var data = null;
      try { data = JSON.parse(xhr.responseText); } catch (_) {}
      if (xhr.status >= 200 && xhr.status < 300 && data && data.ok) {
        if (statusEl) {
          statusEl.textContent = '';
          var icon = document.createElement('i');
          icon.className = 'bi bi-check-circle me-1';
          var span = document.createElement('span');
          span.className = 'text-success';
          span.appendChild(icon);
          var successText = data.local
            ? 'Файл сохранён в локальную папку.'
            : ('Файл успешно загружен на ' + (data.storage_label || 'облачное хранилище') + ' в папку с отчетами проекта.');
          span.appendChild(document.createTextNode(successText));
          statusEl.appendChild(span);
        }
        try {
          var cell = inputEl.closest('.report-upload-cell');
          var row = inputEl.closest('tr');
          if (cell && data.file_name && data.download_url) {
            var existing = cell.querySelector('.report-file-name-link');
            if (existing) existing.remove();
            var link = document.createElement('a');
            link.href = data.download_url;
            link.className = 'report-file-name-link';
            link.setAttribute('download', '');
            link.title = data.file_name;
            var nameSpan = document.createElement('span');
            nameSpan.className = 'report-file-name-text';
            nameSpan.textContent = data.file_name;
            link.appendChild(nameSpan);
            cell.appendChild(link);
          }
          if (row) {
            if (data.upload_id) row.dataset.uploadId = String(data.upload_id);
            applyReportUploadVersionUpdate(row, data);
          }
          updateReportSendButtonState();
          document.body.dispatchEvent(new Event('notifications-updated'));
        } catch (err) {
          console.error(err);
        }
      } else if (statusEl) {
        statusEl.textContent = '';
        var errSpan = document.createElement('span');
        errSpan.className = 'text-danger';
        errSpan.textContent = (data && data.error) || 'Ошибка при загрузке файла.';
        statusEl.appendChild(errSpan);
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
    xhr.send(fd);
    inputEl.value = '';
  }

  var REPORT_VERSIONS_STORAGE_KEY = 'report-versions-collapsed';

  function loadReportVersionCollapsed() {
    try {
      var raw = window.localStorage.getItem(REPORT_VERSIONS_STORAGE_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return new Set(Array.isArray(arr) ? arr.map(String) : []);
    } catch (_) {
      return new Set();
    }
  }

  function saveReportVersionCollapsed(set) {
    try {
      window.localStorage.setItem(
        REPORT_VERSIONS_STORAGE_KEY,
        JSON.stringify(Array.from(set))
      );
    } catch (_) { /* storage may be disabled */ }
  }

  function applyReportVersionCollapsedState() {
    var section = getReportSubmissionSection();
    if (!section) return;
    var collapsed = loadReportVersionCollapsed();
    section.querySelectorAll('#report-submission-table tbody tr[data-is-current="1"]').forEach(function(row) {
      var group = row.dataset.versionGroup || '';
      var btn = row.querySelector('.js-report-version-toggle');
      if (btn) {
        btn.setAttribute('aria-expanded', collapsed.has(group) ? 'false' : 'true');
      }
    });
    section.querySelectorAll('#report-submission-table tbody tr[data-parent-id]').forEach(function(row) {
      var parentId = row.dataset.parentId || '';
      row.classList.toggle('report-version-row-collapsed-hidden', collapsed.has(parentId));
    });
    updateReportSendButtonState();
  }

  function expandReportVersionGroup(group) {
    if (!group) return;
    var collapsed = loadReportVersionCollapsed();
    if (collapsed.delete(group)) {
      saveReportVersionCollapsed(collapsed);
    }
    applyReportVersionCollapsedState();
  }

  function ensureReportVersionToggle(row) {
    if (!row) return;
    var cell = row.querySelector('.cell-typical-val');
    if (!cell) return;
    var btn = cell.querySelector('.js-report-version-toggle');
    if (btn) {
      btn.setAttribute('aria-expanded', 'true');
      return;
    }
    var slot = cell.querySelector('.report-section-toggle-slot');
    if (!slot) {
      slot = document.createElement('span');
      slot.className = 'report-section-toggle-slot';
      cell.insertBefore(slot, cell.firstChild);
    }
    btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'col-task-toggle js-report-version-toggle';
    btn.setAttribute('aria-label', 'Свернуть/развернуть версии');
    btn.setAttribute('aria-expanded', 'true');
    var icon = document.createElement('i');
    icon.className = 'bi bi-caret-down-fill';
    btn.appendChild(icon);
    slot.appendChild(btn);
    row.dataset.hasHistory = '1';
  }

  function insertReviewStepRow(settledRow, html) {
    if (!settledRow || !html) return;
    var wrap = document.createElement('tbody');
    wrap.innerHTML = String(html).trim();
    var nextRow = wrap.querySelector('tr');
    if (!nextRow) return;
    var nextId = nextRow.dataset.rowId || '';
    var table = settledRow.closest('table');
    if (nextId && table && settledRow.dataset.rowId !== nextId && table.querySelector('tr[data-row-id="' + nextId + '"]')) {
      return;
    }
    if (settledRow.dataset.rowId === nextId) {
      var versionCell = settledRow.querySelector('.report-version-cell');
      var version = versionCell ? versionCell.textContent.trim() : '';
      settledRow.dataset.rowId = nextId + (version ? '-v' + version : '-accepted');
      settledRow.dataset.isCurrent = '0';
      settledRow.dataset.parentId = nextRow.dataset.versionGroup || nextId;
      settledRow.dataset.hasHistory = '';
      settledRow.classList.add('report-row-history');
      var toggle = settledRow.querySelector('.js-report-version-toggle');
      if (toggle) toggle.remove();
      var oldBox = settledRow.querySelector('input[name="report-select"]');
      if (oldBox) {
        oldBox.checked = false;
        oldBox.disabled = true;
      }
    }
    if (settledRow.classList.contains('d-none')) nextRow.classList.add('d-none');
    settledRow.before(nextRow);
    applyReportSubmissionColumnVisibility();
    applyReportVersionCollapsedState();
    applyRowGrouping(getReportSubmissionSection());
    scheduleReportSubmissionColumnLayout(true);
  }

  function replaceReportSubmissionRow(row, html) {
    if (!row || !html) return null;
    var wrap = document.createElement('tbody');
    wrap.innerHTML = String(html).trim();
    var next = wrap.querySelector('tr');
    if (!next) return null;
    row.replaceWith(next);
    applyReportSubmissionColumnVisibility();
    applyReportVersionCollapsedState();
    applyRowGrouping(getReportSubmissionSection());
    updateReportSubmissionMasterState();
    scheduleReportSubmissionColumnLayout(true);
    return next;
  }

  function insertPreviousReportVersionRow(currentRow, html) {
    if (!currentRow || !html) return;
    var wrap = document.createElement('tbody');
    wrap.innerHTML = String(html).trim();
    var histRow = wrap.querySelector('tr');
    if (!histRow) return;
    var rowId = histRow.dataset.rowId || '';
    if (rowId) {
      var table = currentRow.closest('table');
      var existing = table && table.querySelector('tr[data-row-id="' + rowId + '"]');
      if (existing) return;
    }
    var parentId = currentRow.dataset.versionGroup || currentRow.dataset.rowId || '';
    if (parentId) histRow.dataset.parentId = parentId;
    var histCheckbox = histRow.querySelector('input[name="report-select"]');
    if (histCheckbox) {
      histCheckbox.checked = false;
      histCheckbox.disabled = true;
    }
    if (currentRow.classList.contains('d-none')) histRow.classList.add('d-none');
    currentRow.after(histRow);
    applyReportSubmissionColumnVisibility();
  }

  function ensureReportSelectCheckbox(row) {
    if (!row || row.dataset.isCurrent !== '1') return;
    var section = getReportSubmissionSection();
    if (section && section.dataset.reportReadonly === '1') return;
    if (row.dataset.canSend !== '1') return;
    var cell = row.querySelector('.report-select-cell');
    if (!cell) return;
    var checkbox = cell.querySelector('input[name="report-select"]');
    if (!checkbox) {
      var wrap = document.createElement('div');
      wrap.className = 'form-check m-0';
      checkbox = document.createElement('input');
      checkbox.className = 'form-check-input';
      checkbox.type = 'checkbox';
      checkbox.id = 'report-sel-' + (row.dataset.rowId || '');
      checkbox.name = 'report-select';
      checkbox.value = row.dataset.rowId || '';
      checkbox.setAttribute('aria-label', 'Выделить строку отчета');
      wrap.appendChild(checkbox);
      cell.appendChild(wrap);
    }
    checkbox.disabled = false;
    checkbox.checked = false;
    row.classList.remove('table-active');
  }

  function reportFindingsMeetThreshold(count, threshold) {
    var findings = Number(count) || 0;
    var limit = Number(threshold) || 0;
    if (limit === 0) return findings === 0;
    return findings < limit;
  }

  function reportFindingCountText(data) {
    if (data && data.finding_count_display) return String(data.finding_count_display);
    if (data && data.check_status === 'done') return formatFindingCount(data.check_finding_count);
    return '—';
  }

  function reportFindingCountValue(text) {
    if (!text || text === '—') return 0;
    var digits = String(text).replace(/[\s\u00a0\u202f]/g, '');
    if (!/^\d+$/.test(digits)) return 0;
    return Number(digits);
  }

  function findingThresholdText(value) {
    if (value === null || value === undefined || value === '') return '';
    return String(value);
  }

  function findingMeetsThreshold(count, threshold) {
    if (threshold === null || threshold === undefined || threshold === '') return null;
    var findings = Number(count) || 0;
    var limit = Number(threshold);
    if (!isFinite(limit)) return null;
    if (findings < 0) findings = 0;
    if (limit < 0) limit = 0;
    return findings < limit || (limit === 0 && findings === 0);
  }

  function appendFindingTextCell(row, className, text) {
    var cell = document.createElement('td');
    if (className) cell.className = className;
    cell.textContent = text || '';
    row.appendChild(cell);
    return cell;
  }

  function formatFindingCount(value) {
    var amount = Math.round(Number(value) || 0);
    if (amount < 0) amount = 0;
    return String(amount).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
  }

  function appendFindingCountCell(row, value, threshold) {
    var cell = document.createElement('td');
    cell.className = 'report-finding-count';
    var meets = findingMeetsThreshold(value, threshold);
    if (meets === true) cell.classList.add('report-finding-count--ok');
    if (meets === false) cell.classList.add('report-finding-count--over');
    cell.textContent = formatFindingCount(value);
    row.appendChild(cell);
  }

  function appendFindingThresholdCell(row, value) {
    var cell = document.createElement('td');
    cell.className = 'report-finding-threshold';
    cell.textContent = findingThresholdText(value);
    row.appendChild(cell);
  }

  function findingHistogramScale(groups) {
    return (groups && groups.courses || []).reduce(function(sum, course) {
      return sum + (Number(course.total) || 0);
    }, 0);
  }

  function appendFindingHistogramCell(row, value, scale, tone) {
    var cell = document.createElement('td');
    cell.className = 'report-finding-hist';
    var track = document.createElement('div');
    track.className = 'report-finding-hist-track' + (tone === 'item' ? ' report-finding-hist-track-item' : '');
    var bar = document.createElement('div');
    bar.className = 'report-finding-hist-bar' + (tone === 'item' ? ' report-finding-hist-bar-item' : '');
    var amount = Number(value) || 0;
    var width = 0;
    if (tone === 'total') width = scale > 0 ? 100 : 0;
    else if (scale > 0) width = amount / scale * 100;
    bar.style.width = width + '%';
    track.appendChild(bar);
    cell.appendChild(track);
    row.appendChild(cell);
  }

  function findingKindText(item) {
    var kind = (item && item.kind_label) || '';
    return kind === 'Макрос' || kind === 'Навык' ? kind : '';
  }

  function appendCourseToggle(cell, course) {
    var label = document.createElement('span');
    label.className = 'report-finding-course-label';
    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'col-task-toggle js-report-finding-course-toggle';
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-label', 'Свернуть/развернуть курс');
    var caret = document.createElement('i');
    caret.className = 'bi bi-caret-down-fill';
    caret.setAttribute('aria-hidden', 'true');
    toggle.appendChild(caret);
    var courseName = document.createElement('span');
    var code = course || '';
    courseName.textContent = /^[A-Z]{4}$/.test(code) ? code : (code || '—');
    label.appendChild(toggle);
    label.appendChild(courseName);
    cell.appendChild(label);
  }

  function findingHeaderSpecs(editable) {
    var specs = [
      ['Курс', 'report-finding-course'],
      ['Вид', 'report-finding-kind'],
      ['Название', 'report-finding-name'],
      ['Порог', 'report-finding-threshold'],
      ['Замеч.', 'report-finding-count']
    ];
    if (editable) specs.push(['Корр.', 'report-finding-corrected']);
    specs.push(['', 'report-finding-hist']);
    return specs;
  }

  function tagFindingHistogram(row, role, key) {
    var bar = row.querySelector('.report-finding-hist-bar');
    if (!bar) return;
    bar.dataset.histRole = role;
    if (key) bar.dataset.histKey = key;
  }

  function appendFindingCorrectedCell(row, value, options) {
    options = options || {};
    var cell = document.createElement('td');
    cell.className = 'report-finding-count report-finding-corrected';
    if (options.editable) {
      cell.dataset.label = options.label || '';
      cell.dataset.calculated = String(options.calculated == null ? 0 : options.calculated);
      cell.dataset.value = String(value == null ? 0 : value);
      if (options.threshold != null && options.threshold !== '') cell.dataset.threshold = String(options.threshold);
      cell.tabIndex = 0;
    } else if (options.sum) {
      cell.classList.add('report-finding-corrected-sum');
    } else if (options.total) {
      cell.classList.add('report-finding-corrected-total');
    }
    setCorrectedCellText(cell, formatFindingCount(value));
    var meets = findingMeetsThreshold(value, options.threshold);
    if (meets === true) cell.classList.add('report-finding-count--ok');
    if (meets === false) cell.classList.add('report-finding-count--over');
    row.appendChild(cell);
    return cell;
  }

  function correctionRulesAccepted(rules, counts, total) {
    if (!rules || !rules.length) return findingMeetsThreshold(total, 0);
    return rules.every(function(rule) {
      var hasSum = rule.sum_threshold !== null && rule.sum_threshold !== undefined && rule.sum_threshold !== '';
      var sumOk = hasSum ? findingMeetsThreshold(total, rule.sum_threshold) : true;
      var items = rule.items || {};
      var labels = Object.keys(items);
      var itemsOk = true;
      if (rule.mode === 'per_item' || rule.mode === 'sum_and_per_item') {
        if (!labels.length) itemsOk = false;
        labels.forEach(function(label) {
          if (!findingMeetsThreshold(Number(counts[label]) || 0, items[label])) itemsOk = false;
        });
      }
      if (rule.mode === 'per_item') return itemsOk;
      if (rule.mode === 'sum_and_per_item') return !!(sumOk && itemsOk);
      return !!sumOk;
    });
  }

  function correctedCellState(cell) {
    var raw = String(cell.dataset.value == null ? '' : cell.dataset.value).trim();
    if (!/^\d+$/.test(raw)) return 'format';
    if (Number(raw) > Number(cell.dataset.calculated || 0)) return 'high';
    return '';
  }

  function readCorrectedCounts(table) {
    var counts = {};
    var byCourse = {};
    table.querySelectorAll('td.report-finding-corrected[data-label]').forEach(function(cell) {
      var row = cell.closest('tr');
      var key = row ? row.dataset.courseKey || '' : '';
      var raw = String(cell.dataset.value == null ? '' : cell.dataset.value).trim();
      var amount = /^\d+$/.test(raw) ? Number(raw) : 0;
      counts[cell.dataset.label] = amount;
      byCourse[key] = (byCourse[key] || 0) + amount;
    });
    return { counts: counts, byCourse: byCourse };
  }

  function refreshFindingCorrectionTable(table) {
    if (!table) return;
    var parsed = readCorrectedCounts(table);
    var total = 0;
    Object.keys(parsed.byCourse).forEach(function(key) { total += parsed.byCourse[key]; });
    table.querySelectorAll('tr.report-finding-course-row').forEach(function(row) {
      var sumCell = row.querySelector('.report-finding-corrected-sum');
      var amount = parsed.byCourse[row.dataset.courseKey] || 0;
      if (sumCell) setCorrectedCellText(sumCell, formatFindingCount(amount));
    });
    var totalCell = table.querySelector('.report-finding-corrected-total');
    if (totalCell) {
      setCorrectedCellText(totalCell, formatFindingCount(total));
      totalCell.classList.remove('report-finding-count--ok', 'report-finding-count--over');
    }
    table.querySelectorAll('td.report-finding-corrected[data-label]').forEach(function(cell) {
      var state = correctedCellState(cell);
      cell.classList.toggle('report-finding-corrected--invalid', !!state);
      setCorrectedCellText(cell, state ? (cell.dataset.value || '') : formatFindingCount(cell.dataset.value || 0));
      var meets = state ? null : findingMeetsThreshold(Number(cell.dataset.value), cell.dataset.threshold);
      cell.classList.toggle('report-finding-count--ok', meets === true);
      cell.classList.toggle('report-finding-count--over', meets === false);
    });
    var rules = [];
    try { rules = JSON.parse(table.dataset.rules || '[]'); } catch (_) { rules = []; }
    var accepted = correctionRulesAccepted(rules, parsed.counts, total);
    var totalRow = table.querySelector('.report-finding-total-row');
    var statusCell = table.querySelector('.report-finding-status');
    if (totalRow) {
      totalRow.classList.toggle('report-finding-total-row--ok', accepted === true);
      totalRow.classList.toggle('report-finding-total-row--over', accepted === false);
    }
    if (statusCell) {
      statusCell.textContent = accepted === true ? 'Отчет сдан' : (accepted === false ? 'Отчет не сдан' : '');
    }
    if (totalCell && accepted === true) totalCell.classList.add('report-finding-count--ok');
    if (totalCell && accepted === false) totalCell.classList.add('report-finding-count--over');
    table.querySelectorAll('.report-finding-hist-bar').forEach(function(bar) {
      var role = bar.dataset.histRole || '';
      var amount = 0;
      if (role === 'total') amount = total;
      else if (role === 'course') amount = parsed.byCourse[bar.dataset.histKey] || 0;
      else amount = Number(parsed.counts[bar.dataset.histKey]) || 0;
      var width = 0;
      if (role === 'total') width = total > 0 ? 100 : 0;
      else if (total > 0) width = amount / total * 100;
      bar.style.width = width + '%';
    });
  }

  function findingCorrectionSelectionClasses() {
    return ['inline-cell-selected', 'inline-cell-sel-t', 'inline-cell-sel-r', 'inline-cell-sel-b', 'inline-cell-sel-l'];
  }

  function selectFindingCorrectionCell(cell) {
    var modal = document.getElementById('report-finding-modal');
    if (modal) {
      modal.querySelectorAll('td.inline-cell-selected').forEach(function(other) {
        if (other !== cell) other.classList.remove.apply(other.classList, findingCorrectionSelectionClasses());
      });
    }
    if (!cell) return;
    cell.classList.add.apply(cell.classList, findingCorrectionSelectionClasses());
    if (!cell.querySelector('input') && document.activeElement !== cell) {
      try { cell.focus({ preventScroll: true }); } catch (_) { cell.focus(); }
    }
  }

  function lockCorrectionSpinner(input, cell) {
    var calculated = Number(cell.dataset.calculated || 0);
    if (calculated < 0) calculated = 0;
    input.min = '0';
    input.max = String(calculated);
    var raw = String(input.value == null ? '' : input.value).trim();
    var current = /^\d+$/.test(raw) ? Number(raw) : 0;
    var line = input.closest('.report-corr-line');
    var lock = line && line.querySelector('.report-corr-up-lock');
    if (lock) lock.hidden = current < calculated;
  }

  function setCorrectedCellText(cell, text) {
    if (!cell) return;
    var live = cell.querySelector('.report-corr-value');
    if (cell.querySelector('input')) {
      if (live) live.textContent = text;
      return;
    }
    cell.textContent = '';
    var line = document.createElement('div');
    line.className = 'report-corr-line';
    var value = document.createElement('span');
    value.className = 'report-corr-value';
    value.textContent = text;
    var slot = document.createElement('span');
    slot.className = 'report-corr-slot';
    slot.setAttribute('aria-hidden', 'true');
    line.appendChild(value);
    line.appendChild(slot);
    cell.appendChild(line);
  }

  function closeCorrectedEditor(cell, revert) {
    var input = cell.querySelector('input');
    if (!input) return;
    if (revert) cell.dataset.value = cell.dataset.editStart || '0';
    else cell.dataset.value = input.value;
    input.remove();
    cell.classList.remove('inline-cell-editing');
    refreshFindingCorrectionTable(cell.closest('table'));
  }

  function commitFindingCorrectionEditors(revert) {
    var modal = document.getElementById('report-finding-modal');
    if (!modal) return;
    modal.querySelectorAll('td.report-finding-corrected[data-label] input').forEach(function(input) {
      closeCorrectedEditor(input.closest('td'), !!revert);
    });
  }

  function focusAdjacentCorrectedCell(cell, step, openEditor) {
    var cells = Array.from(cell.closest('table').querySelectorAll('td.report-finding-corrected[data-label]'));
    var index = cells.indexOf(cell);
    var next = cells[index + step];
    if (!next) return;
    if (openEditor) openCorrectedEditor(next);
    else selectFindingCorrectionCell(next);
  }

  function openCorrectedEditor(cell, seed) {
    if (!cell || cell.querySelector('input')) return;
    commitFindingCorrectionEditors(false);
    selectFindingCorrectionCell(cell);
    cell.dataset.editStart = cell.dataset.value || '0';
    if (!cell.querySelector('.report-corr-line')) {
      setCorrectedCellText(cell, formatFindingCount(cell.dataset.value || 0));
    }
    var line = cell.querySelector('.report-corr-line');
    var valueEl = cell.querySelector('.report-corr-value');
    var input = document.createElement('input');
    input.type = 'number';
    input.step = '1';
    input.inputMode = 'numeric';
    input.className = 'inline-table-number-input report-finding-corrected-input';
    input.value = seed != null ? String(seed) : (cell.dataset.value || '0');
    if (seed != null) cell.dataset.value = String(seed);
    input.lang = document.documentElement.getAttribute('lang') || 'ru';
    input.setAttribute('aria-label', 'Корректировка замечаний');
    if (valueEl) valueEl.textContent = input.value;
    lockCorrectionSpinner(input, cell);
    input.addEventListener('wheel', function(event) { event.preventDefault(); }, { passive: false });
    line.appendChild(input);
    var lock = document.createElement('span');
    lock.className = 'report-corr-up-lock';
    lock.setAttribute('aria-hidden', 'true');
    line.appendChild(lock);
    lockCorrectionSpinner(input, cell);
    var spinnerPointer = false;
    input.addEventListener('input', function() {
      cell.dataset.value = input.value;
      lockCorrectionSpinner(input, cell);
      refreshFindingCorrectionTable(cell.closest('table'));
    });
    input.addEventListener('pointerdown', function(event) {
      var box = input.getBoundingClientRect();
      if (event.clientX >= box.right - 24) spinnerPointer = true;
    });
    input.addEventListener('keydown', function(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeCorrectedEditor(cell, true);
        selectFindingCorrectionCell(cell);
        return;
      }
      if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault();
        closeCorrectedEditor(cell, false);
        focusAdjacentCorrectedCell(cell, event.shiftKey ? -1 : 1, false);
      }
    });
    input.addEventListener('blur', function() {
      window.setTimeout(function() {
        if (spinnerPointer) {
          spinnerPointer = false;
          if (cell.querySelector('input') === input && document.activeElement !== input) input.focus();
          return;
        }
        if (cell.querySelector('input') === input) closeCorrectedEditor(cell, false);
      }, 0);
    });
    input.focus();
    if (seed != null) refreshFindingCorrectionTable(cell.closest('table'));
  }

  function renderReportFindingGroups(groups, editable) {
    var table = document.createElement('table');
    table.className = 'table table-sm align-middle report-finding-groups-table';
    if (editable) table.dataset.rules = JSON.stringify((groups && groups.rules) || []);
    var thead = document.createElement('thead');
    var headRow = document.createElement('tr');
    findingHeaderSpecs(!!editable).forEach(function(spec) {
      var cell = document.createElement('th');
      cell.className = spec[1];
      if (spec[1] === 'report-finding-hist') cell.setAttribute('aria-label', 'Гистограмма');
      if (spec[1] === 'report-finding-course') {
        var wrap = document.createElement('span');
        wrap.className = 'report-finding-course-label';
        var toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'clf-wrap-btn report-finding-courses-toggle js-report-finding-courses-toggle';
        toggle.setAttribute('aria-expanded', 'true');
        toggle.setAttribute('aria-label', 'Свернуть курсы');
        toggle.title = 'Свернуть/развернуть курсы';
        var icon = document.createElement('i');
        icon.className = 'bi bi-arrows-collapse';
        icon.setAttribute('aria-hidden', 'true');
        toggle.appendChild(icon);
        var title = document.createElement('span');
        title.textContent = 'Курс';
        wrap.appendChild(toggle);
        wrap.appendChild(title);
        cell.appendChild(wrap);
      } else {
        cell.textContent = spec[0];
      }
      headRow.appendChild(cell);
    });
    thead.appendChild(headRow);
    var tbody = document.createElement('tbody');
    var histogramScale = editable
      ? (groups.courses || []).reduce(function(sum, course) {
          var amount = course.corrected_total != null ? Number(course.corrected_total) : Number(course.total);
          return sum + (amount || 0);
        }, 0)
      : findingHistogramScale(groups);
    (groups.courses || []).slice().sort(function(a, b) {
      return (Number(b.total) || 0) - (Number(a.total) || 0);
    }).forEach(function(course, index) {
      var key = String(index);
      var courseCorrected = course.corrected_total != null ? course.corrected_total : course.total;
      var courseRow = document.createElement('tr');
      courseRow.className = 'report-finding-course-row';
      courseRow.dataset.courseKey = key;
      var courseCell = document.createElement('td');
      courseCell.className = 'report-finding-course';
      appendCourseToggle(courseCell, course.course);
      courseRow.appendChild(courseCell);
      appendFindingTextCell(courseRow, 'report-finding-kind', '');
      appendFindingTextCell(courseRow, 'report-finding-name', '');
      appendFindingThresholdCell(courseRow, null);
      appendFindingCountCell(courseRow, course.total, null);
      if (editable) appendFindingCorrectedCell(courseRow, courseCorrected, { sum: true });
      appendFindingHistogramCell(courseRow, editable ? courseCorrected : course.total, histogramScale, 'course');
      if (editable) tagFindingHistogram(courseRow, 'course', key);
      tbody.appendChild(courseRow);
      (course.items || []).slice().sort(function(a, b) {
        return (Number(b.count) || 0) - (Number(a.count) || 0);
      }).forEach(function(item) {
        var itemCorrected = item.corrected != null ? item.corrected : item.count;
        var itemRow = document.createElement('tr');
        itemRow.className = 'report-finding-item-row';
        itemRow.dataset.courseKey = key;
        appendFindingTextCell(itemRow, 'report-finding-course', '');
        appendFindingTextCell(itemRow, 'report-finding-kind', findingKindText(item));
        appendFindingTextCell(itemRow, 'report-finding-name', item.label || item.name || '');
        appendFindingThresholdCell(itemRow, item.threshold);
        appendFindingCountCell(itemRow, item.count, item.threshold);
        if (editable) {
          appendFindingCorrectedCell(itemRow, itemCorrected, {
            editable: true,
            label: item.label || item.name || '',
            calculated: item.count,
            threshold: item.threshold,
          });
        }
        appendFindingHistogramCell(itemRow, editable ? itemCorrected : item.count, histogramScale, 'item');
        if (editable) tagFindingHistogram(itemRow, 'item', item.label || item.name || '');
        tbody.appendChild(itemRow);
      });
    });
    var correctedTotal = groups.corrected_total != null ? groups.corrected_total : groups.total;
    var totalMeets = editable
      ? correctionRulesAccepted(groups.rules || [], (function() {
          var counts = {};
          (groups.courses || []).forEach(function(course) {
            (course.items || []).forEach(function(item) {
              counts[item.label] = item.corrected != null ? Number(item.corrected) : Number(item.count) || 0;
            });
          });
          return counts;
        })(), correctedTotal)
      : findingMeetsThreshold(groups.total, groups.total_threshold);
    var totalRow = document.createElement('tr');
    totalRow.className = 'report-finding-total-row';
    if (totalMeets === true) totalRow.classList.add('report-finding-total-row--ok');
    if (totalMeets === false) totalRow.classList.add('report-finding-total-row--over');
    var totalLabel = document.createElement('td');
    totalLabel.colSpan = 2;
    totalLabel.className = 'report-finding-total-label';
    totalLabel.textContent = 'Итого';
    totalRow.appendChild(totalLabel);
    var status = '';
    if (totalMeets === true) status = 'Отчет сдан';
    if (totalMeets === false) status = 'Отчет не сдан';
    appendFindingTextCell(totalRow, 'report-finding-name report-finding-status', status);
    appendFindingThresholdCell(totalRow, groups.total_threshold);
    appendFindingCountCell(totalRow, groups.total, groups.total_threshold);
    if (editable) appendFindingCorrectedCell(totalRow, correctedTotal, { total: true, threshold: groups.total_threshold });
    appendFindingHistogramCell(totalRow, editable ? correctedTotal : groups.total, histogramScale, 'total');
    if (editable) tagFindingHistogram(totalRow, 'total', '');
    tbody.appendChild(totalRow);
    table.appendChild(thead);
    table.appendChild(tbody);
    if (editable) refreshFindingCorrectionTable(table);
    return table;
  }

  function fillReportFindingHeading(groups) {
    var ctx = (groups && groups.context) || {};
    var projectEl = document.getElementById('report-finding-project');
    var executorEl = document.getElementById('report-finding-executor');
    var reportEl = document.getElementById('report-finding-report');
    if (projectEl) {
      projectEl.textContent = [ctx.stage, ctx.product, ctx.name].filter(Boolean).join(' ');
    }
    if (executorEl) executorEl.textContent = ctx.executor || '';
    if (reportEl) {
      reportEl.textContent = ((ctx.section || '') + ' по активу ' + (ctx.asset || '')).trim();
    }
    var versionEl = document.getElementById('report-finding-version');
    if (versionEl) versionEl.textContent = ctx.version || '';
  }

  function setReportFindingModalMode(mode) {
    var editing = mode === 'edit';
    var closeBtn = document.getElementById('report-finding-close');
    var cancelBtn = document.getElementById('report-finding-cancel');
    var saveBtn = document.getElementById('report-finding-save');
    var errorEl = document.getElementById('report-finding-correction-error');
    if (closeBtn) closeBtn.classList.toggle('d-none', editing);
    if (cancelBtn) cancelBtn.classList.toggle('d-none', !editing);
    if (saveBtn) {
      saveBtn.classList.toggle('d-none', !editing);
      saveBtn.disabled = false;
    }
    if (errorEl) {
      errorEl.textContent = '';
      errorEl.classList.add('d-none');
    }
  }

  function showFindingCorrectionError(message) {
    var errorEl = document.getElementById('report-finding-correction-error');
    if (!errorEl) return;
    errorEl.textContent = message || '';
    errorEl.classList.toggle('d-none', !message);
  }

  function openReportFindingModal(btn, mode) {
    var modalEl = document.getElementById('report-finding-modal');
    if (!modalEl || !window.bootstrap) return;
    mode = mode || 'info';
    var groups = {};
    try {
      groups = JSON.parse(btn.dataset.findings || '{}');
    } catch (_) {
      groups = {};
    }
    setReportFindingModalMode(mode);
    fillReportFindingHeading(groups);
    var host = document.getElementById('report-finding-groups');
    if (host) {
      host.textContent = '';
      host.appendChild(renderReportFindingGroups(groups, mode === 'edit'));
    }
    modalEl.dataset.correctionUploadId = btn.dataset.uploadId || '';
    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  function reportFindingCorrectionUrl(section, uploadId) {
    var template = (section && section.dataset.reportFindingCorrectionUrl) || '';
    if (!template || !uploadId) return '';
    return template.replace(/\/0\/finding-correction\/?$/, '/' + uploadId + '/finding-correction/');
  }

  function replaceReportSlotRows(section, versionGroup, html) {
    var table = document.getElementById('report-submission-table');
    if (!table || !versionGroup || !html) return;
    var rows = Array.from(table.querySelectorAll('tr[data-version-group="' + versionGroup + '"]'));
    if (!rows.length) return;
    var anchor = rows[0];
    var wrap = document.createElement('tbody');
    wrap.innerHTML = String(html).trim();
    var nextRows = Array.from(wrap.querySelectorAll('tr'));
    if (!nextRows.length) return;
    nextRows.forEach(function(row) { anchor.parentNode.insertBefore(row, anchor); });
    rows.forEach(function(row) { row.remove(); });
    applyReportSubmissionColumnVisibility();
    if (typeof applyReportVersionCollapsedState === 'function') applyReportVersionCollapsedState();
    if (typeof applyRowGrouping === 'function') applyRowGrouping(section);
    scheduleReportSubmissionColumnLayout(true);
  }

  function saveFindingCorrection() {
    var modalEl = document.getElementById('report-finding-modal');
    var table = modalEl && modalEl.querySelector('.report-finding-groups-table');
    var section = getReportSubmissionSection();
    if (!table || !modalEl) return;
    var counts = {};
    var increased = false;
    var invalid = false;
    var labels = [];
    table.querySelectorAll('td.report-finding-corrected[data-label]').forEach(function(cell) {
      if (cell.querySelector('input')) closeCorrectedEditor(cell, false);
      var state = correctedCellState(cell);
      cell.classList.toggle('report-finding-corrected--invalid', !!state);
      if (state === 'high') increased = true;
      if (state === 'format') invalid = true;
      if (state) labels.push(cell.dataset.label);
      counts[cell.dataset.label] = Number(cell.dataset.value);
    });
    if (increased || invalid) {
      showFindingCorrectionError(increased
        ? 'Число замечаний нельзя увеличить выше расчётного.'
        : 'Укажите целое число от 0 до расчётного.');
      var first = table.querySelector('td.report-finding-corrected--invalid');
      if (first) first.focus();
      return;
    }
    var uploadId = modalEl.dataset.correctionUploadId || '';
    var url = reportFindingCorrectionUrl(section, uploadId);
    var saveBtn = document.getElementById('report-finding-save');
    if (!url) {
      showFindingCorrectionError('Не удалось сохранить корректировку.');
      return;
    }
    if (saveBtn) saveBtn.disabled = true;
    showFindingCorrectionError('');
    fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrftoken,
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ counts: counts }),
    }).then(function(response) {
      return response.json().then(function(data) {
        if (!response.ok || !data || !data.ok) {
          var error = new Error((data && data.error) || 'Не удалось сохранить корректировку.');
          error.labels = (data && data.invalid_labels) || [];
          throw error;
        }
        return data;
      });
    }).then(function(data) {
      replaceReportSlotRows(section, data.version_group || '', data.slot_rows_html || '');
      window.bootstrap.Modal.getOrCreateInstance(modalEl).hide();
    }).catch(function(err) {
      if (saveBtn) saveBtn.disabled = false;
      (err.labels || labels).forEach(function(label) {
        table.querySelectorAll('td.report-finding-corrected[data-label]').forEach(function(cell) {
          if (cell.dataset.label === label) cell.classList.add('report-finding-corrected--invalid');
        });
      });
      showFindingCorrectionError(err.message || 'Не удалось сохранить корректировку.');
    });
  }

  function reportCountIsPositive(text) {
    var digits = String(text || '').replace(/[\s\u00a0\u202f]/g, '');
    return /^\d+$/.test(digits) && Number(digits) > 0;
  }

  function appendReportInfoControl(parent, active, findings, label) {
    var icon = document.createElement('i');
    icon.className = 'bi bi-info-circle';
    icon.setAttribute('aria-hidden', 'true');
    if (!active) {
      var mark = document.createElement('span');
      mark.className = 'report-finding-info-btn report-finding-info-btn--disabled';
      mark.setAttribute('aria-hidden', 'true');
      mark.appendChild(icon);
      parent.appendChild(mark);
      return;
    }
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'report-finding-info-btn js-report-finding-info';
    btn.setAttribute('aria-label', label);
    btn.title = label;
    if (findings) btn.dataset.findings = JSON.stringify(findings);
    btn.appendChild(icon);
    parent.appendChild(btn);
  }

  function updateReportFindingCountCell(row, data) {
    if (!row) return;
    var cell = row.querySelector('.report-finding-count-cell');
    if (!cell) return;
    var text = reportFindingCountText(data);
    cell.textContent = '';
    var inner = document.createElement('span');
    inner.className = 'report-finding-count-inner';
    inner.appendChild(document.createTextNode(text));
    if (text !== '—') {
      var active = reportCountIsPositive(text) && (!data || data.finding_info_active !== false);
      appendReportInfoControl(
        inner,
        active,
        data && data.finding_groups,
        'Результаты проверки'
      );
    }
    cell.appendChild(inner);
  }

  function updateReportCalculatedCell(row, data) {
    var cell = row && row.querySelector('.report-calculated-count-cell');
    if (!cell || !cell.querySelector('.report-finding-count-inner') || !data) return;
    var text = data.calculated_count_display || data.finding_count_display;
    if (!text) return;
    var inner = cell.querySelector('.report-finding-count-inner');
    inner.textContent = '';
    inner.appendChild(document.createTextNode(text));
    if (text === '—') return;
    appendReportInfoControl(
      inner,
      reportCountIsPositive(text) && !!data.calculated_groups,
      data.calculated_groups,
      'Расчётные замечания'
    );
  }

  function updateReportCorrectedCell(row, data) {
    var cell = row && row.querySelector('.report-corrected-count-cell');
    if (!cell || !cell.querySelector('.report-corrected-count-inner') || !data) return;
    var text = data.corrected_count_display || data.finding_count_display;
    if (!text) return;
    var inner = cell.querySelector('.report-corrected-count-inner');
    inner.textContent = '';
    if (reportCountIsPositive(text) && data.edit_groups) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'report-finding-edit-btn js-report-finding-edit';
      btn.dataset.findings = JSON.stringify(data.edit_groups);
      btn.dataset.uploadId = String(data.upload_id || row.dataset.uploadId || '');
      btn.setAttribute('aria-label', 'Скорректировать замечания');
      btn.title = 'Скорректировать замечания';
      var icon = document.createElement('i');
      icon.className = 'bi bi-pencil-square';
      icon.setAttribute('aria-hidden', 'true');
      btn.appendChild(icon);
      inner.appendChild(btn);
    }
    var value = document.createElement('span');
    value.className = 'report-corrected-count-value';
    value.textContent = text;
    inner.appendChild(value);
  }

  function reportWorkflowStatusClass(status) {
    if ((status || '').indexOf('Сдан') === 0 || (status || '').indexOf('Согласован') === 0) return 'report-status--accepted';
    if ((status || '').indexOf('Проверен') === 0 || (status || '').indexOf('В работе после ') === 0) return 'report-status--checked';
    if (status === 'На проверке ИИ' || (status || '').indexOf('На проверке ') === 0) return 'report-status--sent';
    if (status === 'Загружен') return 'report-status--uploaded';
    return 'report-status--idle';
  }

  function updateReportWorkflowStatusCell(row, data) {
    if (!row) return;
    var cell = row.querySelector('.report-workflow-status-cell');
    var status = (data && data.workflow_status) || '';
    if (!status) {
      if (data && data.check_status === 'done') {
        status = reportFindingsMeetThreshold(data.check_finding_count, data.finding_threshold) ? 'Согласован ИИ' : 'Проверен ИИ';
      } else if (data && data.sent_at && data.sent_at !== '—') {
        status = 'На проверке ИИ';
      } else if (data && data.file_name) {
        status = 'Загружен';
      } else {
        status = 'В работе';
      }
    }
    var statusClass = (data && data.workflow_status_class) || reportWorkflowStatusClass(status);
    row.dataset.workflowStatus = status;
    if (!cell) return;
    cell.innerHTML = '';
    var inner = document.createElement('span');
    inner.className = 'report-workflow-status-inner';
    var icon = document.createElement('i');
    icon.className = 'bi bi-circle reg-launch-icon reg-launch-indicator ' + statusClass;
    icon.setAttribute('aria-hidden', 'true');
    var label = document.createElement('span');
    label.className = 'report-workflow-status-label';
    if ((status || '').indexOf('Сдан') === 0 || (status || '').indexOf('Согласован') === 0 || status === 'Загружен') {
      label.classList.add('report-workflow-status-label--inset');
      label.style.paddingLeft = '1px';
    }
    label.textContent = status;
    inner.appendChild(icon);
    inner.appendChild(label);
    cell.appendChild(inner);
  }

  function reportStatusDateDisplay(data) {
    if (data && data.status_date && data.status_date !== '—') return data.status_date;
    var status = (data && data.workflow_status) || '';
    if (status === 'Загружен') return (data && data.uploaded_at) || '—';
    if (status === 'Отправлен' || status === 'На проверке ИИ') return (data && data.sent_at) || '—';
    if ((status || '').indexOf('Проверен') === 0 || (status || '').indexOf('Сдан') === 0 || (status || '').indexOf('Согласован') === 0 || (status || '').indexOf('На проверке ') === 0 || (status || '').indexOf('В работе после ') === 0) {
      return (data && (data.checked_at || data.sent_at || data.uploaded_at)) || '—';
    }
    return '—';
  }

  function updateReportStatusDateCell(row, data) {
    if (!row) return;
    var cell = row.querySelector('.report-status-date-cell, .report-sent-at-cell');
    if (cell) cell.textContent = reportStatusDateDisplay(data);
  }

  function applyReportUploadVersionUpdate(row, data) {
    var versionCell = row.querySelector('.report-version-cell');
    if (versionCell && data.version_display) {
      versionCell.textContent = data.version_display;
    }
    row.dataset.checkStatus = '';
    updateReportCheckResultCell(row.querySelector('.report-check-result-cell'), {});
    updateReportWorkflowStatusCell(row, Object.assign({}, data, {
      check_status: '',
      sent_at: '',
      checked_at: '',
      workflow_status: data.workflow_status || 'Загружен'
    }));
    updateReportStatusDateCell(row, Object.assign({}, data, {
      sent_at: '',
      checked_at: '',
      workflow_status: data.workflow_status || 'Загружен'
    }));
    updateReportFindingCountCell(row, Object.assign({}, data, {
      check_status: '',
      finding_count_display: '—'
    }));
    if ((data.workflow_status || 'Загружен') === 'Загружен') {
      row.dataset.canSend = '1';
    }
    ensureReportSelectCheckbox(row);
    if (data.previous_row_html) {
      insertPreviousReportVersionRow(row, data.previous_row_html);
    }
    if (data.has_history) {
      ensureReportVersionToggle(row);
      expandReportVersionGroup(row.dataset.versionGroup || row.dataset.rowId || '');
    }
    applyRowGrouping(getReportSubmissionSection());
    applyReportVersionCollapsedState();
    scheduleReportSubmissionColumnLayout(true);
  }

  function statusWantsVersionDownload(status) {
    status = status || '';
    return status.indexOf('Проверен') === 0 || status.indexOf('Сдан') === 0 || status.indexOf('Согласован') === 0;
  }

  function replaceUploadIconWithDownload(row, data) {
    if (!row) return;
    var uploadCell = row.querySelector('.report-upload-cell');
    var downloadUrl = (data && data.download_url) || '';
    if (!uploadCell || !downloadUrl) return;
    var uploadLabel = uploadCell.querySelector('label.ct-upload-link');
    if (uploadCell.querySelector('a.ct-upload-link i.bi-download')) {
      if (uploadLabel) uploadLabel.remove();
      return;
    }
    var iconLink = document.createElement('a');
    iconLink.href = downloadUrl;
    iconLink.className = 'ct-upload-link';
    iconLink.setAttribute('download', '');
    iconLink.title = 'Скачать файл';
    var glyph = document.createElement('i');
    glyph.className = 'bi bi-download';
    iconLink.appendChild(glyph);
    var spacer = uploadCell.querySelector('.report-upload-icon-spacer');
    if (uploadLabel) uploadLabel.replaceWith(iconLink);
    else if (spacer) spacer.replaceWith(iconLink);
    else uploadCell.insertBefore(iconLink, uploadCell.firstChild);
  }

  function fillReviewDecisionControls(inner, uploadId) {
    var label = document.createElement('label');
    label.className = 'report-review-upload-action';
    var up = document.createElement('i');
    up.className = 'bi bi-upload';
    up.setAttribute('aria-hidden', 'true');
    var uploadText = document.createElement('span');
    uploadText.className = 'report-review-action-text';
    uploadText.textContent = 'Загрузить замечания';
    var input = document.createElement('input');
    input.type = 'file';
    input.className = 'd-none js-report-review-upload';
    input.accept = '.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    input.dataset.uploadId = String(uploadId || '');
    label.appendChild(up);
    label.appendChild(uploadText);
    label.appendChild(input);
    var rule = document.createElement('span');
    rule.className = 'report-review-action-rule';
    rule.setAttribute('aria-hidden', 'true');
    var accept = document.createElement('button');
    accept.type = 'button';
    accept.className = 'report-review-accept-action js-report-review-accept';
    accept.dataset.uploadId = String(uploadId || '');
    var check = document.createElement('i');
    check.className = 'bi bi-check2-square';
    check.setAttribute('aria-hidden', 'true');
    var acceptText = document.createElement('span');
    acceptText.className = 'report-review-action-text';
    acceptText.textContent = 'Принять без замечаний';
    accept.appendChild(check);
    accept.appendChild(acceptText);
    inner.appendChild(label);
    inner.appendChild(rule);
    inner.appendChild(accept);
  }

  function appendRemarksDiscardAction(inner, entryId) {
    var rule = document.createElement('span');
    rule.className = 'report-review-action-rule';
    rule.setAttribute('aria-hidden', 'true');
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'report-review-discard-action js-report-remarks-discard';
    button.dataset.reviewEntryId = String(entryId || '');
    var icon = document.createElement('i');
    icon.className = 'bi bi-x-square';
    icon.setAttribute('aria-hidden', 'true');
    var text = document.createElement('span');
    text.className = 'report-review-action-text';
    text.textContent = 'Удалить файл';
    button.appendChild(icon);
    button.appendChild(text);
    inner.appendChild(rule);
    inner.appendChild(button);
  }

  function applyManualReviewRowControls(row, data) {
    if (!row) return;
    replaceUploadIconWithDownload(row, data);
    if (!data || !data.can_review_upload) return;
    var resultCell = row.querySelector('.report-check-result-cell');
    if (!resultCell || resultCell.querySelector('.js-report-review-upload')) return;
    resultCell.textContent = '';
    var inner = document.createElement('span');
    inner.className = 'report-check-result-inner';
    fillReviewDecisionControls(inner, (data && data.upload_id) || row.dataset.uploadId || '');
    resultCell.appendChild(inner);
  }

  function applyReportSendResult(row, data) {
    if (!row || !data) return;
    if (Object.prototype.hasOwnProperty.call(data, 'check_status')) {
      row.dataset.checkStatus = data.check_status || '';
    }
    updateReportCheckResultCell(row.querySelector('.report-check-result-cell'), data);
    updateReportWorkflowStatusCell(row, data);
    if ((data.workflow_status || '').indexOf('На проверке ') === 0 && data.workflow_status !== 'На проверке ИИ') {
      applyManualReviewRowControls(row, data);
    }
    if (statusWantsVersionDownload(data.workflow_status)) {
      replaceUploadIconWithDownload(row, data);
    }
    updateReportStatusDateCell(row, data);
    updateReportFindingCountCell(row, data);
    updateReportCalculatedCell(row, data);
    updateReportCorrectedCell(row, data);
    if (data.review_row_html) insertReviewStepRow(row, data.review_row_html);
    var checkbox = row.querySelector('input[name="report-select"]');
    if (data.check_status === 'done' || data.check_status === 'running' || (data.workflow_status || '').indexOf('На проверке') === 0) {
      if (checkbox) {
        checkbox.checked = false;
        checkbox.disabled = true;
      }
      row.dataset.canSend = '0';
      row.classList.remove('table-active');
    } else if (checkbox && row.dataset.isCurrent === '1') {
      checkbox.disabled = false;
    }
    updateReportSubmissionMasterState();
    scheduleReportSubmissionColumnLayout(true);
  }

  var reportCheckPollingRows = new WeakSet();

  function reportCheckStatusUrl(section, uploadId) {
    var template = (section && section.dataset.reportCheckStatusUrl) || '';
    if (!template || !uploadId) return '';
    return template.replace(/\/0\/check-status\/?$/, '/' + uploadId + '/check-status/');
  }

  function reportPollDelay(milliseconds) {
    return new Promise(function(resolve) {
      window.setTimeout(resolve, milliseconds);
    });
  }

  async function pollReportCheck(row, gate) {
    if (!row || reportCheckPollingRows.has(row)) return;
    var uploadId = (row.dataset.uploadId || '').trim();
    var section = getReportSubmissionSection();
    var url = reportCheckStatusUrl(section, uploadId);
    if (!url) return;
    reportCheckPollingRows.add(row);
    try {
      while (row.isConnected && row.dataset.checkStatus === 'running') {
        try {
          var response = await fetch(url, {
            method: 'GET',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
          });
          var data = null;
          try { data = await response.json(); } catch (_) {}
          if (!response.ok || !data || !data.ok) {
            throw new Error((data && data.error) || 'Не удалось получить статус проверки.');
          }
          var stillStarting = gate && gate.allowFinish === false;
          if (data.check_status === 'running' || !stillStarting) {
            applyReportSendResult(row, data);
          }
        } catch (err) {
          console.warn('report check status error', err);
          await reportPollDelay(3000);
        }
        if (!row.isConnected || row.dataset.checkStatus !== 'running') break;
        await reportPollDelay(1000);
      }
    } finally {
      reportCheckPollingRows.delete(row);
    }
  }

  function initReportCheckPolling() {
    getReportSubmissionRows().forEach(function(row) {
      if (row.dataset.checkStatus === 'running') pollReportCheck(row);
    });
  }

  function reportCheckPendingText(data) {
    var progress = data && data.check_progress ? String(data.check_progress).trim() : '';
    return progress ? 'Идет проверка... ' + progress : 'Идет проверка...';
  }

  function updateReportCheckResultCell(cell, data) {
    if (!cell) return;
    cell.textContent = '';
    if (!data.check_file_name && !data.review_file_name && data.check_status !== 'error' && data.check_status !== 'running') {
      cell.textContent = '';
      var empty = document.createElement('span');
      empty.className = 'report-check-result-inner';
      var mark = document.createElement('span');
      mark.className = 'report-check-result-empty';
      mark.textContent = '—';
      empty.appendChild(mark);
      cell.appendChild(empty);
      return;
    }
    var inner = document.createElement('span');
    inner.className = 'report-check-result-inner';
    if (data.review_file_name && data.review_download_url) {
      var reviewIcon = document.createElement('a');
      reviewIcon.href = data.review_download_url;
      reviewIcon.className = 'ct-upload-link report-check-download-icon';
      reviewIcon.setAttribute('download', '');
      reviewIcon.title = 'Скачать файл замечаний';
      var reviewGlyph = document.createElement('i');
      reviewGlyph.className = 'bi bi-download';
      reviewIcon.appendChild(reviewGlyph);
      inner.appendChild(reviewIcon);
      var reviewLink = document.createElement('a');
      reviewLink.href = data.review_download_url;
      reviewLink.className = 'report-file-name-link';
      reviewLink.setAttribute('download', '');
      if (!data.remarks_notice_pending) reviewLink.title = data.review_file_name;
      else reviewLink.classList.add('report-remarks-loaded-link');
      var reviewName = document.createElement('span');
      reviewName.className = 'report-file-name-text';
      reviewName.textContent = data.remarks_notice_pending ? 'Загружен' : data.review_file_name;
      reviewLink.appendChild(reviewName);
      inner.appendChild(reviewLink);
      if (data.remarks_notice_pending) appendRemarksDiscardAction(inner, data.review_entry_id);
    } else if (data.check_file_name && data.check_download_url) {
      var iconLink = document.createElement('a');
      iconLink.href = data.check_download_url;
      iconLink.className = 'ct-upload-link report-check-download-icon';
      iconLink.setAttribute('download', '');
      iconLink.title = 'Скачать результат проверки';
      var icon = document.createElement('i');
      icon.className = 'bi bi-download';
      iconLink.appendChild(icon);
      inner.appendChild(iconLink);
      var link = document.createElement('a');
      link.href = data.check_download_url;
      link.className = 'report-file-name-link js-report-check-file-link';
      link.setAttribute('download', '');
      link.title = data.check_file_name;
      var nameSpan = document.createElement('span');
      nameSpan.className = 'report-file-name-text';
      nameSpan.textContent = data.check_file_name;
      link.appendChild(nameSpan);
      inner.appendChild(link);
    }
    if (data.check_status === 'error') {
      var badge = document.createElement('span');
      badge.className = 'text-danger small js-report-check-badge';
      badge.textContent = 'ошибка проверки';
      if (data.check_error) badge.title = data.check_error;
      inner.appendChild(badge);
    } else if (data.check_status === 'running') {
      var spacer = document.createElement('span');
      spacer.className = 'report-upload-icon-spacer';
      spacer.setAttribute('aria-hidden', 'true');
      inner.appendChild(spacer);
      var pending = document.createElement('span');
      pending.className = 'text-muted js-report-check-badge report-check-pending-text';
      pending.textContent = reportCheckPendingText(data);
      inner.appendChild(pending);
    }
    cell.appendChild(inner);
  }

  function syncReportLocalSourceUi() {
    var section = getReportSubmissionSection();
    if (!section) return;
    var sourceSel = section.querySelector('#report-submission-source');
    var wrap = section.querySelector('#report-submission-local-wrap');
    var isLocal = Boolean(sourceSel && sourceSel.value === 'local');
    if (wrap) wrap.classList.toggle('d-none', !isLocal);
    section.querySelectorAll('.report-upload-cell .ct-upload-link').forEach(function(label) {
      label.title = isLocal ? 'Загрузить файл в локальную папку' : 'Загрузить файл';
    });
  }

  function initReportLocalSource() {
    var section = getReportSubmissionSection();
    if (!section) return;
    var sourceSel = section.querySelector('#report-submission-source');
    var pathInput = section.querySelector('#report-submission-local-path');
    if (!sourceSel) return;
    if (window.UIPref) {
      var savedSource = UIPref.get('reports:source', 'cloud');
      if (savedSource === 'local') sourceSel.value = 'local';
      var savedPath = UIPref.get('reports:localFolder', '');
      if (pathInput && !pathInput.value && savedPath) pathInput.value = savedPath;
    }
    syncReportLocalSourceUi();
  }

  function reportRowById(section, rowId) {
    if (!section || !rowId) return null;
    var escaped = window.CSS && CSS.escape ? CSS.escape(rowId) : String(rowId).replace(/"/g, '\\"');
    return section.querySelector('#report-submission-table tbody tr[data-row-id="' + escaped + '"]');
  }

  function reportFileDeleteUrl(section, uploadId) {
    var template = (section && section.dataset.reportDeleteUrl) || '';
    if (!template || !uploadId) return '';
    return template.replace(/\/0\/delete\/?$/, '/' + uploadId + '/delete/');
  }

  function reportFileDeleteMessage(btn) {
    var kind = btn.dataset.removeKind || '';
    var fileName = btn.dataset.fileName || '';
    var row = btn.closest('tr');
    var checkBtn = row && row.querySelector('.js-report-file-remove[data-remove-kind="check"]');
    var checkName = checkBtn ? (checkBtn.dataset.fileName || '') : '';
    if (kind === 'check') {
      return 'Удалить результат проверки «' + fileName + '»? Файл будет удалён и с диска.';
    }
    var text = 'Удалить файл «' + fileName + '»? Файл будет удалён и с диска.';
    if (checkName) {
      text += ' Также будет удалён результат проверки «' + checkName + '» и его файл на диске.';
    }
    return text;
  }

  function clearReportVersionToggle(row) {
    if (!row) return;
    var btn = row.querySelector('.js-report-version-toggle');
    if (btn) btn.remove();
    delete row.dataset.hasHistory;
  }

  function replaceReportCurrentRow(section, slotRowId, html) {
    var current = reportRowById(section, slotRowId);
    if (!current || current.dataset.isCurrent !== '1' || !html) return null;
    var wrap = document.createElement('tbody');
    wrap.innerHTML = String(html).trim();
    var next = wrap.querySelector('tr');
    if (!next) return null;
    current.replaceWith(next);
    applyReportSubmissionColumnVisibility();
    return next;
  }

  var reportFileDeletePending = null;

  function setReportFileDeleteBusy(busy) {
    var confirmBtn = document.getElementById('report-file-delete-confirm');
    var cancelBtn = document.getElementById('report-file-delete-cancel');
    if (confirmBtn) confirmBtn.disabled = busy;
    if (cancelBtn) cancelBtn.disabled = busy;
  }

  function showReportFileDeleteError(message) {
    var messageEl = document.getElementById('report-file-delete-message');
    if (!messageEl) return;
    messageEl.textContent = message || 'Не удалось удалить файл.';
    messageEl.classList.add('text-danger');
  }

  async function submitReportFileDelete() {
    var pending = reportFileDeletePending;
    if (!pending) return;
    var section = getReportSubmissionSection();
    var url = reportFileDeleteUrl(section, pending.uploadId);
    if (!url) {
      showReportFileDeleteError('Не удалось удалить файл.');
      return;
    }
    setReportFileDeleteBusy(true);
    var body = new FormData();
    body.append('kind', pending.kind);
    try {
      var response = await fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken, 'X-Requested-With': 'XMLHttpRequest' },
        body: body,
      });
      var data = null;
      try { data = await response.json(); } catch (_) {}
      if (!response.ok || !data || !data.ok) {
        showReportFileDeleteError((data && data.error) || 'Не удалось удалить файл.');
        setReportFileDeleteBusy(false);
        return;
      }
      if (pending.kind === 'check') {
        var checkRow = pending.row && pending.row.isConnected ? pending.row : null;
        if (checkRow) applyReportSendResult(checkRow, data);
      } else if (data.replaced_current) {
        var nextRow = replaceReportCurrentRow(section, data.slot_row_id || '', data.current_row_html);
        if (data.remove_row_id) {
          var historyRow = reportRowById(section, data.remove_row_id);
          if (historyRow) historyRow.remove();
        }
        if (nextRow && nextRow.dataset.checkStatus === 'running') pollReportCheck(nextRow);
      } else {
        var removed = pending.row && pending.row.isConnected ? pending.row : reportRowById(section, pending.rowId);
        if (removed) removed.remove();
        if (!data.has_history) clearReportVersionToggle(reportRowById(section, data.slot_row_id || ''));
      }
      applyRowGrouping(section);
      applyReportVersionCollapsedState();
      updateReportSendButtonState();
      reportFileDeletePending = null;
      var modalEl = document.getElementById('report-file-delete-modal');
      if (modalEl && window.bootstrap) {
        var instance = window.bootstrap.Modal.getInstance(modalEl);
        if (instance) instance.hide();
      }
    } catch (err) {
      console.error(err);
      showReportFileDeleteError('Ошибка сети при удалении файла.');
    }
    setReportFileDeleteBusy(false);
  }

  function openReportFileDeleteModal(btn) {
    var row = btn.closest('tr');
    var modalEl = document.getElementById('report-file-delete-modal');
    var messageEl = document.getElementById('report-file-delete-message');
    if (!row || !modalEl || !messageEl || !window.bootstrap) return;
    reportFileDeletePending = {
      kind: btn.dataset.removeKind || '',
      uploadId: btn.dataset.uploadId || row.dataset.uploadId || '',
      rowId: row.dataset.rowId || '',
      row: row,
    };
    messageEl.classList.remove('text-danger');
    messageEl.textContent = reportFileDeleteMessage(btn);
    setReportFileDeleteBusy(false);
    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  document.addEventListener('click', function(e) {
    var removeBtn = e.target.closest('.js-report-file-remove');
    if (!removeBtn) return;
    var section = getReportSubmissionSection();
    if (!section || !section.contains(removeBtn)) return;
    e.preventDefault();
    e.stopPropagation();
    openReportFileDeleteModal(removeBtn);
  });

  document.addEventListener('click', function(e) {
    var confirmBtn = e.target.closest('#report-file-delete-confirm');
    if (!confirmBtn || confirmBtn.disabled) return;
    e.preventDefault();
    submitReportFileDelete();
  });

  document.addEventListener('change', function(e) {
    var inputEl = e.target.closest('.js-report-upload');
    var root = pane();
    if (!inputEl || !root || !root.contains(inputEl)) return;
    handleReportUpload(inputEl);
  });

  function applyReviewDecisionResult(row, data) {
    if (!row || !data) return;
    if (data.workflow_status) {
      updateReportWorkflowStatusCell(row, data);
      updateReportStatusDateCell(row, data);
      updateReportFindingCountCell(row, data);
      updateReportCheckResultCell(row.querySelector('.report-check-result-cell'), data);
      if (statusWantsVersionDownload(data.workflow_status)) {
        replaceUploadIconWithDownload(row, data);
        row.dataset.canSend = '0';
      }
      var checkbox = row.querySelector('input[name="report-select"]');
      if (data.remarks_notice_pending) {
        row.dataset.remarksPending = '1';
        row.dataset.reviewEntryId = String(data.review_entry_id || '');
        if (checkbox) {
          checkbox.disabled = false;
          checkbox.checked = true;
        }
        updateReportSubmissionMasterState();
      } else if (statusWantsVersionDownload(data.workflow_status) && checkbox) {
        checkbox.checked = false;
        checkbox.disabled = true;
      }
    }
    var uploadLabel = row.querySelector('.js-report-review-upload');
    if (uploadLabel) {
      var label = uploadLabel.closest('label');
      if (label) {
        var uploadRule = label.nextElementSibling;
        if (uploadRule && uploadRule.classList.contains('report-review-action-rule')) uploadRule.remove();
        label.remove();
      }
    }
    var acceptBtn = row.querySelector('.js-report-review-accept');
    if (acceptBtn) acceptBtn.remove();
    if (data.review_row_html && !data.remarks_notice_pending) insertReviewStepRow(row, data.review_row_html);
  }

  document.addEventListener('change', function(e) {
    var inputEl = e.target.closest('.js-report-review-upload');
    var section = getReportSubmissionSection();
    if (!inputEl || !section || !section.contains(inputEl)) return;
    var url = section.dataset.reportReviewUrl;
    var file = inputEl.files && inputEl.files[0];
    var uploadId = inputEl.dataset.uploadId || '';
    inputEl.value = '';
    if (!url || !file || !uploadId) return;
    var row = inputEl.closest('tr');
    var body = new FormData();
    body.append('upload_id', uploadId);
    body.append('file', file);
    var sourceSel = section.querySelector('#report-submission-source');
    if (sourceSel && sourceSel.value === 'local') {
      body.append('source_kind', 'local');
      var pathInput = section.querySelector('#report-submission-local-path');
      body.append('local_folder_path', pathInput ? pathInput.value.trim() : '');
    }
    fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrftoken, 'X-Requested-With': 'XMLHttpRequest' },
      body: body,
    }).then(function(response) {
      return response.json().then(function(data) {
        if (!response.ok || !data.ok) throw new Error((data && data.error) || 'Не удалось загрузить файл.');
        return data;
      });
    }).then(function(data) {
      applyReviewDecisionResult(row, data);
    }).catch(function(err) {
      window.alert(err.message || 'Не удалось загрузить файл.');
    });
  });

  document.addEventListener('click', function(e) {
    var acceptBtn = e.target.closest('.js-report-review-accept');
    var section = getReportSubmissionSection();
    if (!acceptBtn || !section || !section.contains(acceptBtn)) return;
    e.preventDefault();
    var url = section.dataset.reportReviewUrl;
    var uploadId = acceptBtn.dataset.uploadId || '';
    var row = acceptBtn.closest('tr');
    if (!url || !uploadId || !row || acceptBtn.disabled) return;
    acceptBtn.disabled = true;
    var body = new FormData();
    body.append('upload_id', uploadId);
    body.append('accept_without_remarks', '1');
    fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrftoken, 'X-Requested-With': 'XMLHttpRequest' },
      body: body,
    }).then(function(response) {
      return response.json().then(function(data) {
        if (!response.ok || !data.ok) throw new Error((data && data.error) || 'Не удалось принять отчёт.');
        return data;
      });
    }).then(function(data) {
      applyReviewDecisionResult(row, data);
    }).catch(function(err) {
      acceptBtn.disabled = false;
      window.alert(err.message || 'Не удалось принять отчёт.');
    });
  });

  document.addEventListener('click', function(e) {
    var editBtn = e.target.closest('.js-report-finding-edit');
    if (editBtn) {
      var editSection = getReportSubmissionSection();
      if (!editSection || !editSection.contains(editBtn)) return;
      e.preventDefault();
      e.stopPropagation();
      openReportFindingModal(editBtn, 'edit');
      return;
    }
    var correctedCell = e.target.closest('#report-finding-modal td.report-finding-corrected[data-label]');
    if (correctedCell) {
      if (e.target.closest('input, .inline-table-number-wrap')) return;
      e.preventDefault();
      if (correctedCell.classList.contains('inline-cell-selected') && !correctedCell.querySelector('input')) {
        openCorrectedEditor(correctedCell);
      } else if (!correctedCell.querySelector('input')) {
        commitFindingCorrectionEditors(false);
        selectFindingCorrectionCell(correctedCell);
      }
      return;
    }
    if (e.target.closest('#report-finding-cancel, #report-finding-close, #report-finding-modal .btn-close')) {
      commitFindingCorrectionEditors(true);
      selectFindingCorrectionCell(null);
    } else if (e.target.closest('#report-finding-modal') && !e.target.closest('#report-finding-save')) {
      commitFindingCorrectionEditors(false);
      selectFindingCorrectionCell(null);
    }
    if (e.target.closest('#report-finding-save')) {
      e.preventDefault();
      saveFindingCorrection();
      return;
    }
    var btn = e.target.closest('.js-report-finding-info');
    if (!btn) return;
    var section = getReportSubmissionSection();
    if (!section || !section.contains(btn)) return;
    e.preventDefault();
    e.stopPropagation();
    openReportFindingModal(btn, 'info');
  });

  document.addEventListener('keydown', function(e) {
    var modal = document.getElementById('report-finding-modal');
    if (!modal || !modal.classList.contains('show')) return;
    if (e.target.closest && e.target.closest('input, textarea, button')) return;
    var cell = e.target.closest && e.target.closest('#report-finding-modal td.report-finding-corrected[data-label]');
    if (!cell) return;
    if (e.key === 'Enter' || e.key === 'F2') {
      e.preventDefault();
      openCorrectedEditor(cell);
      return;
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
      e.preventDefault();
      focusAdjacentCorrectedCell(cell, (e.key === 'ArrowUp' || e.key === 'ArrowLeft') ? -1 : 1, false);
      return;
    }
    if (!e.ctrlKey && !e.metaKey && !e.altKey && e.key.length === 1 && /^[0-9]$/.test(e.key)) {
      e.preventDefault();
      openCorrectedEditor(cell, e.key);
    }
  });

  function setFindingCourseExpanded(modal, courseBtn, expanded) {
    courseBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    var courseRow = courseBtn.closest('tr');
    var key = courseRow && courseRow.dataset.courseKey;
    if (!key) return;
    modal.querySelectorAll('.report-finding-item-row[data-course-key="' + key + '"]').forEach(function(row) {
      row.classList.toggle('report-finding-item-collapsed', !expanded);
    });
  }

  function syncFindingCoursesToggle(modal) {
    var master = modal.querySelector('.js-report-finding-courses-toggle');
    if (!master) return;
    var buttons = modal.querySelectorAll('.js-report-finding-course-toggle');
    var allCollapsed = buttons.length > 0 && Array.prototype.every.call(buttons, function(button) {
      return button.getAttribute('aria-expanded') === 'false';
    });
    master.setAttribute('aria-expanded', allCollapsed ? 'false' : 'true');
    master.classList.toggle('active', allCollapsed);
    master.title = allCollapsed ? 'Развернуть курсы' : 'Свернуть курсы';
    master.setAttribute('aria-label', allCollapsed ? 'Развернуть курсы' : 'Свернуть курсы');
    var icon = master.querySelector('i');
    if (icon) icon.className = allCollapsed ? 'bi bi-arrows-expand' : 'bi bi-arrows-collapse';
  }

  document.addEventListener('click', function(e) {
    var master = e.target.closest('.js-report-finding-courses-toggle');
    if (!master) return;
    var modal = document.getElementById('report-finding-modal');
    if (!modal || !modal.contains(master)) return;
    e.preventDefault();
    var buttons = modal.querySelectorAll('.js-report-finding-course-toggle');
    var expand = master.getAttribute('aria-expanded') === 'false';
    buttons.forEach(function(button) {
      setFindingCourseExpanded(modal, button, expand);
    });
    syncFindingCoursesToggle(modal);
  });

  document.addEventListener('click', function(e) {
    var btn = e.target.closest('.js-report-finding-course-toggle');
    if (!btn) return;
    var modal = document.getElementById('report-finding-modal');
    if (!modal || !modal.contains(btn)) return;
    e.preventDefault();
    var expanded = btn.getAttribute('aria-expanded') === 'false';
    setFindingCourseExpanded(modal, btn, expanded);
    syncFindingCoursesToggle(modal);
  });

  document.addEventListener('click', function(e) {
    var btn = e.target.closest('.js-report-version-toggle');
    if (!btn) return;
    var section = getReportSubmissionSection();
    if (!section || !section.contains(btn)) return;
    var row = btn.closest('tr');
    var group = row && (row.dataset.versionGroup || row.dataset.rowId);
    if (!group) return;
    e.preventDefault();
    var collapsed = loadReportVersionCollapsed();
    if (collapsed.has(group)) collapsed.delete(group);
    else collapsed.add(group);
    saveReportVersionCollapsed(collapsed);
    applyReportVersionCollapsedState();
  });

  function revealReportRemarksFile(rowPayload) {
    var section = getReportSubmissionSection();
    var entryId = String((rowPayload && rowPayload.review_entry_id) || '');
    if (!section || !entryId) return;
    var row = section.querySelector('tr[data-review-entry-id="' + entryId + '"]');
    if (!row) return;
    delete row.dataset.remarksPending;
    updateReportCheckResultCell(row.querySelector('.report-check-result-cell'), {
      review_file_name: rowPayload.review_file_name,
      review_download_url: rowPayload.review_download_url,
    });
    var checkbox = row.querySelector('input[name="report-select"]');
    if (checkbox) {
      checkbox.checked = false;
      checkbox.disabled = true;
    }
    row.classList.remove('table-active');
    if (rowPayload.review_row_html) insertReviewStepRow(row, rowPayload.review_row_html);
  }

  document.addEventListener('click', function(e) {
    var discardBtn = e.target.closest('.js-report-remarks-discard');
    var section = getReportSubmissionSection();
    if (!discardBtn || !section || !section.contains(discardBtn) || discardBtn.disabled) return;
    e.preventDefault();
    e.stopPropagation();
    var row = discardBtn.closest('tr');
    var entryId = discardBtn.dataset.reviewEntryId || (row && row.dataset.reviewEntryId) || '';
    var url = section.dataset.reportRemarksDiscardUrl || '';
    if (!row || !entryId || !url) return;
    discardBtn.disabled = true;
    var body = new FormData();
    body.append('entry_id', entryId);
    fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrftoken, 'X-Requested-With': 'XMLHttpRequest' },
      body: body,
    }).then(function(response) {
      return response.json().then(function(data) {
        if (!response.ok || !data || !data.ok) {
          throw new Error((data && data.error) || 'Не удалось удалить файл.');
        }
        return data;
      });
    }).then(function(data) {
      replaceReportSubmissionRow(row, data.row_html);
    }).catch(function(err) {
      discardBtn.disabled = false;
      window.alert(err.message || 'Не удалось удалить файл.');
    });
  });

  var REPORT_REMARKS_CHANNELS_PREF_KEY = 'reports:remarksChannels';

  function getReportRemarksChannels() {
    var modal = document.getElementById('report-remarks-modal');
    if (!modal) return [];
    return Array.from(modal.querySelectorAll('.js-report-remarks-channel'));
  }

  function saveReportRemarksChannels() {
    if (!window.UIPref) return;
    UIPref.set(REPORT_REMARKS_CHANNELS_PREF_KEY, getReportRemarksChannels()
      .filter(function(box) { return box.checked && !box.disabled; })
      .map(function(box) { return box.value; }));
  }

  function restoreReportRemarksChannels() {
    var channels = getReportRemarksChannels();
    if (!channels.length || !window.UIPref) return;
    var saved = UIPref.get(REPORT_REMARKS_CHANNELS_PREF_KEY, null);
    if (!Array.isArray(saved)) return;
    var savedValues = new Set(saved);
    channels.forEach(function(box) {
      box.checked = !box.disabled && savedValues.has(box.value);
    });
  }

  function reportRemarksDeliveryAlert(emailDelivery) {
    if (!emailDelivery || !emailDelivery.requested || !(emailDelivery.failed > 0)) return;
    var errorLines = (emailDelivery.errors || []).slice(0, 5).map(function(item) {
      var channelPrefix = item.channel_label ? '[' + item.channel_label + '] ' : '';
      return '- ' + channelPrefix + item.recipient + ': ' + item.error;
    });
    var moreCount = Math.max((emailDelivery.errors || []).length - errorLines.length, 0);
    var details = [
      'Не удалось отправить ' + emailDelivery.failed + ' из ' + emailDelivery.attempted + ' email-писем.',
    ].concat(errorLines);
    if (moreCount > 0) details.push('- И еще ' + moreCount + ' ошибок.');
    window.alert(details.join('\n'));
  }

  async function sendReportRemarks(section, btn, pendingBoxes) {
    var modal = document.getElementById('report-remarks-modal');
    var channels = modal
      ? Array.from(modal.querySelectorAll('.js-report-remarks-channel')).filter(function(box) { return box.checked; })
      : [];
    if (!channels.length) {
      window.alert('Выберите хотя бы один способ отправки.');
      return;
    }
    var url = section.dataset.reportRemarksSendUrl || '';
    if (!url) return;
    var sentAtInput = modal ? modal.querySelector('.js-report-remarks-sent-at') : null;
    var formData = new FormData();
    pendingBoxes.forEach(function(checkbox) {
      formData.append('entry_ids[]', checkbox.closest('tr').dataset.reviewEntryId || '');
    });
    formData.append('request_sent_at', sentAtInput ? sentAtInput.value : '');
    channels.forEach(function(box) { formData.append('delivery_channels[]', box.value); });
    btn.disabled = true;
    try {
      var response = await fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData,
      });
      var data = null;
      try { data = await response.json(); } catch (_) {}
      if (!response.ok || !data || !data.ok) {
        throw new Error((data && data.error) || 'Не удалось отправить замечания.');
      }
      (data.rows || []).forEach(revealReportRemarksFile);
      if (data.warning) window.alert(data.warning);
      reportRemarksDeliveryAlert(data.email_delivery);
      var modalInstance = modal && window.bootstrap ? window.bootstrap.Modal.getInstance(modal) : null;
      if (modalInstance) modalInstance.hide();
      document.body.dispatchEvent(new Event('notifications-updated'));
    } catch (err) {
      window.alert(err.message || 'Не удалось отправить замечания.');
    }
    updateReportSubmissionMasterState();
  }

  document.addEventListener('change', function(event) {
    var box = event.target.closest('.js-report-remarks-channel');
    if (!box) return;
    var modal = document.getElementById('report-remarks-modal');
    if (!modal || !modal.contains(box)) return;
    saveReportRemarksChannels();
  });

  document.addEventListener('click', async function(e) {
    var btn = e.target.closest('#report-submission-send-btn');
    if (!btn) return;
    var section = getReportSubmissionSection();
    if (!section || !section.contains(btn) || btn.disabled) return;
    e.preventDefault();
    var checked = getVisibleReportSelectChecks().filter(function(checkbox) { return checkbox.checked; });
    var pendingBoxes = checked.filter(function(checkbox) {
      return reportRowIsRemarksPending(checkbox.closest('tr'));
    });
    if (pendingBoxes.length) {
      if (pendingBoxes.length !== checked.length) {
        updateReportSendButtonState();
        return;
      }
      sendReportRemarks(section, btn, pendingBoxes);
      return;
    }
    if (checked.length !== 1) {
      updateReportSendButtonState();
      return;
    }
    var selectedCheckbox = checked[0];
    var row = selectedCheckbox.closest('tr');
    var uploadId = row && (row.dataset.uploadId || '').trim();
    var url = section.dataset.reportSendUrl || '';
    if (!uploadId || !url) {
      alert('Выберите одну строку с загруженным файлом.');
      return;
    }
    selectedCheckbox.checked = false;
    selectedCheckbox.disabled = true;
    row.classList.remove('table-active');
    updateReportSubmissionMasterState();
    var resultCell = row.querySelector('.report-check-result-cell');
    if (resultCell) {
      resultCell.textContent = '';
      var spacer = document.createElement('span');
      spacer.className = 'report-upload-icon-spacer';
      spacer.setAttribute('aria-hidden', 'true');
      resultCell.appendChild(spacer);
      var pending = document.createElement('span');
      pending.className = 'text-muted js-report-check-badge report-check-pending-text';
      pending.textContent = reportCheckPendingText(null);
      resultCell.appendChild(pending);
    }
    updateReportFindingCountCell(row, { check_status: 'running' });
    row.dataset.checkStatus = 'running';
    var checkPollGate = { allowFinish: false };
    pollReportCheck(row, checkPollGate);
    btn.disabled = true;
    try {
      var fd = new FormData();
      fd.append('upload_id', uploadId);
      var response = await fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: fd,
      });
      var data = null;
      try { data = await response.json(); } catch (_) {}
      if (!response.ok || !data || !data.ok) {
        throw new Error((data && data.error) || 'Не удалось отправить файл.');
      }
      checkPollGate.allowFinish = true;
      applyReportSendResult(row, data);
      if (data.check_status === 'running') pollReportCheck(row, checkPollGate);
    } catch (err) {
      alert(err.message || 'Не удалось отправить файл.');
      row.dataset.checkStatus = '';
      if (selectedCheckbox && row.dataset.isCurrent === '1') {
        selectedCheckbox.disabled = false;
      }
      if (resultCell && resultCell.querySelector('.js-report-check-badge')) {
        resultCell.textContent = '';
        var emptyMark = document.createElement('span');
        emptyMark.className = 'report-check-result-inner';
        var emptyDash = document.createElement('span');
        emptyDash.className = 'report-check-result-empty';
        emptyDash.textContent = '—';
        emptyMark.appendChild(emptyDash);
        resultCell.appendChild(emptyMark);
      }
    } finally {
      updateReportSendButtonState();
    }
  });

  document.addEventListener('click', function(e) {
    var section = getReportSubmissionSection();
    if (!section || !section.contains(e.target)) return;
    var sourceSel = section.querySelector('#report-submission-source');
    if (!sourceSel || sourceSel.value !== 'local') return;
    var label = e.target.closest('.ct-upload-link');
    if (!label || !section.contains(label) || !label.closest('.report-upload-cell')) return;
    if (!label.querySelector('.js-report-upload')) return;
    var pathInput = section.querySelector('#report-submission-local-path');
    var localPath = pathInput ? pathInput.value.trim() : '';
    if (localPath) return;
    e.preventDefault();
    e.stopPropagation();
    ensureReportUploadProgressModal();
    var emptyModal = document.getElementById('report-upload-progress-modal');
    var emptyStatus = document.getElementById('report-upload-status');
    var emptyClose = document.getElementById('report-upload-close-btn');
    if (emptyStatus) emptyStatus.textContent = 'Укажите путь к локальной папке.';
    if (emptyClose) emptyClose.disabled = false;
    if (emptyModal && window.bootstrap) bootstrap.Modal.getOrCreateInstance(emptyModal).show();
  }, true);

  document.addEventListener('change', function(e) {
    var section = getReportSubmissionSection();
    if (!section || !section.contains(e.target)) return;
    if (e.target.id === 'report-submission-source') {
      if (window.UIPref) UIPref.set('reports:source', e.target.value);
      syncReportLocalSourceUi();
    }
    if (e.target.id === 'report-submission-local-path' && window.UIPref) {
      UIPref.set('reports:localFolder', e.target.value.trim());
    }
  });

  document.addEventListener('change', function(e) {
    var root = pane();
    if (!root) return;
    if (e.target.closest && e.target.closest('#performers-modal')) return;
    if (e.target.id === 'report-submission-master') {
      var checked = e.target.checked;
      getVisibleReportSelectChecks().forEach(function(checkbox) {
        checkbox.checked = checked;
      });
      updateReportSubmissionMasterState();
      return;
    }
    if (e.target.name === 'report-select' && root.contains(e.target)) {
      updateReportSubmissionMasterState();
      return;
    }
    if (e.target.id === 'report-check-master') {
      var reportCheckChecked = e.target.checked;
      getVisibleReportCheckChecks().forEach(function(checkbox) {
        checkbox.checked = reportCheckChecked;
      });
      e.target.indeterminate = false;
      updateReportCheckMasterState();
      updateRowHighlight('report-check-select');
      ensureReportCheckActionsVisibility();
      return;
    }
    if (e.target.name === 'report-check-select' && root.contains(e.target)) {
      updateReportCheckMasterState();
      updateRowHighlight('report-check-select');
      ensureReportCheckActionsVisibility();
      return;
    }
    if (e.target.id === 'report-macros-master') {
      var reportMacroChecked = e.target.checked;
      getVisibleReportMacroChecks().forEach(function(checkbox) {
        checkbox.checked = reportMacroChecked;
      });
      e.target.indeterminate = false;
      updateReportMacrosMasterState();
      updateRowHighlight('report-macro-select');
      ensureReportMacrosActionsVisibility();
      return;
    }
    if (e.target.name === 'report-macro-select' && root.contains(e.target)) {
      updateReportMacrosMasterState();
      updateRowHighlight('report-macro-select');
      ensureReportMacrosActionsVisibility();
    }
  });

  document.addEventListener('click', async (e) => {
    const paymentPaidToggleIcon = e.target.closest('[data-payment-paid-toggle]');
    const paymentSectionFromToggle = paymentPaidToggleIcon ? findPaymentRequestSection(paymentPaidToggleIcon) : null;
    if (paymentPaidToggleIcon && paymentSectionFromToggle) {
      if (
        !isPaymentPaidToggleInteractive(paymentSectionFromToggle)
        || !paymentPaidToggleIcon.classList.contains('is-interactive')
        || paymentPaidToggleIcon.classList.contains('is-skipped')
      ) {
        return;
      }
      const row = paymentPaidToggleIcon.closest('tr[data-performer-id]');
      const kind = paymentPaidToggleIcon.dataset.paymentPaidToggle;
      const toggleUrl = getPaymentPaidToggleUrl(paymentSectionFromToggle);
      if (!row || (kind !== 'advance' && kind !== 'final') || !toggleUrl) return;

      e.preventDefault();
      const previousOn = paymentPaidToggleIcon.classList.contains('is-on');
      const nextOn = !previousOn;
      const previousPaidAt = row.querySelector(`[data-payment-paid-date="${kind}"]`)?.textContent || '';
      setPaymentPaidToggleForPerformer(row.dataset.performerId, kind, nextOn, {
        paidAt: nextOn ? previousPaidAt : '',
      });

      const formData = new FormData();
      formData.append('performer_id', row.dataset.performerId);
      formData.append('kind', kind);
      formData.append('paid', nextOn ? '1' : '0');

      paymentPaidToggleIcon.classList.add('is-pending');
      try {
        const response = await fetch(toggleUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось сохранить статус оплаты.');
        }
        if (typeof data.paid === 'boolean') {
          const updatedRowIds = Array.isArray(data.row_ids) && data.row_ids.length
            ? data.row_ids
            : [row.dataset.performerId];
          updatedRowIds.forEach((performerId) => {
            setPaymentPaidToggleForPerformer(performerId, kind, data.paid, {
              paidAt: data.paid_at || '',
            });
          });
        }
        document.body.dispatchEvent(new Event('notifications-updated'));
      } catch (err) {
        setPaymentPaidToggleForPerformer(row.dataset.performerId, kind, previousOn, {
          paidAt: previousPaidAt,
        });
        alert(err.message || 'Не удалось сохранить статус оплаты.');
      } finally {
        paymentPaidToggleIcon.classList.remove('is-pending');
      }
      return;
    }

    const paymentRequestSendBtn = e.target.closest('.js-payment-request-send-btn');
    const paymentSectionFromSend = paymentRequestSendBtn ? findPaymentRequestSection(paymentRequestSendBtn) : null;
    if (paymentRequestSendBtn && paymentSectionFromSend) {
      const checked = getVisiblePaymentRequestChecks(paymentSectionFromSend).filter((cb) => cb.checked);
      if (!checked.length || paymentRequestSendBtn.disabled) return;

      const requestPanel = getPaymentRequestActionsPanel(paymentSectionFromSend);
      const requestUrl = requestPanel?.dataset?.requestUrl;
      const sentAtInput = paymentSectionFromSend.querySelector('.js-payment-request-sent-at');
      const selectedChannels = getPaymentRequestChannels(paymentSectionFromSend).filter((cb) => cb.checked).map((cb) => cb.value);
      if (!selectedChannels.length) {
        alert('Выберите хотя бы один способ отправки.');
        return;
      }
      if (!requestUrl) return;

      const formData = new FormData();
      checked.forEach((checkbox) => formData.append('performer_ids[]', checkbox.value));
      formData.append('request_sent_at', sentAtInput?.value || '');
      selectedChannels.forEach((value) => formData.append('delivery_channels[]', value));

      paymentRequestSendBtn.disabled = true;
      try {
        const response = await fetch(requestUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось отправить заявку.');
        }

        const sentAtDisplay = data?.request_sent_at || '';
        const requestNumber = data?.request_number;
        const senderDisplay = data?.sender_display || '';
        const rowUpdateMap = new Map(
          (data?.row_updates || []).map((item) => [String(item.id), item.stage]),
        );
        getPaymentRequestRows().forEach((row) => {
          const performerId = row.dataset.performerId;
          const step = rowUpdateMap.get(String(performerId));
          if (!step) return;
          if (step === 'advance') {
            setPaymentRequestToggle(row, 'advance', true);
            setPaymentRequestSentDate(row, 'advance', sentAtDisplay);
            setPaymentRequestNumber(row, 'advance', requestNumber);
          } else if (step === 'final') {
            setPaymentRequestToggle(row, 'final', true);
            setPaymentRequestSentDate(row, 'final', sentAtDisplay);
            setPaymentRequestNumber(row, 'final', requestNumber);
          }
          setPaymentRequestSender(row, senderDisplay);
          const checkbox = row.querySelector('input[name="payment-request-select"]');
          if (checkbox) checkbox.checked = false;
        });
        syncPaymentRequestRowsState();

        const modalEl = paymentSectionFromSend.querySelector('.js-payment-request-modal');
        const modal = modalEl ? window.bootstrap?.Modal.getInstance(modalEl) : null;
        modal?.hide();

        const emailDelivery = data?.email_delivery;
        if (emailDelivery?.requested && emailDelivery?.failed > 0) {
          const errorLines = (emailDelivery.errors || [])
            .slice(0, 5)
            .map((item) => {
              const channelPrefix = item.channel_label ? `[${item.channel_label}] ` : '';
              return `- ${channelPrefix}${item.recipient}: ${item.error}`;
            });
          const moreCount = Math.max((emailDelivery.errors || []).length - errorLines.length, 0);
          const details = [
            `Не удалось отправить ${emailDelivery.failed} из ${emailDelivery.attempted} email-писем.`,
            ...errorLines,
          ];
          if (moreCount > 0) {
            details.push(`- И еще ${moreCount} ошибок.`);
          }
          alert(details.join('\n'));
        }

        document.body.dispatchEvent(new Event('performers-updated'));
        document.body.dispatchEvent(new Event('contracts-execution-updated'));
        document.body.dispatchEvent(new Event('notifications-updated'));
        updatePaymentRequestState();
      } catch (err) {
        alert(err.message || 'Не удалось отправить заявку.');
        updatePaymentRequestState(paymentSectionFromSend);
      }
      return;
    }

    const root = pane(); if (!root) return;
    const contractRoot = contractPane();

    var sectionToggle = e.target.closest('#participation-section-toggle');
    if (sectionToggle && root.contains(sectionToggle)) {
      toggleParticipationCollapse();
      return;
    }

    var assetToggle = e.target.closest('#participation-asset-toggle');
    if (assetToggle && root.contains(assetToggle)) {
      toggleParticipationAssetCollapse();
      return;
    }

    var contractSectionToggle = e.target.closest('#contract-section-toggle');
    if (contractSectionToggle && contractRoot && contractRoot.contains(contractSectionToggle)) {
      toggleContractCollapse();
      return;
    }

    var contractAssetToggle = e.target.closest('#contract-asset-toggle');
    if (contractAssetToggle && contractRoot && contractRoot.contains(contractAssetToggle)) {
      toggleContractAssetCollapse();
      return;
    }

    var irSectionToggle = e.target.closest('#info-request-section-toggle');
    if (irSectionToggle && root.contains(irSectionToggle)) {
      toggleInfoRequestCollapse();
      return;
    }

    var irAssetToggle = e.target.closest('#info-request-asset-toggle');
    if (irAssetToggle && root.contains(irAssetToggle)) {
      toggleInfoRequestAssetCollapse();
      return;
    }

    const quickEdit = e.target.closest('.performer-quick-edit');
    if (quickEdit && root.contains(quickEdit)) {
      const tr = quickEdit.closest('tr');
      if (!tr) return;
      const url = tr.dataset.editUrl;
      if (!url) return;

      getRowChecks('performer-select').forEach(b => { b.checked = false; });
      const cb = tr.querySelector('input[name="performer-select"]');
      if (cb) cb.checked = true;

      window.__tableSel['performer-select'] = cb ? [String(cb.value)] : [];
      window.__tableSelLast = 'performer-select';

      updatePerformerMasterState();
      updateRowHighlight('performer-select');
      ensurePerformerActionsVisibility();

      await htmx.ajax('GET', url, { target: '#performers-modal .modal-content', swap: 'innerHTML' });
      return;
    }

    const revokeInfoApprovalBtn = e.target.closest('#revoke-info-approval-btn');
    if (revokeInfoApprovalBtn && root.contains(revokeInfoApprovalBtn)) {
      const checked = getVisibleInfoRequestChecks().filter((cb) => cb.checked);
      if (!checked.length || revokeInfoApprovalBtn.disabled) return;

      const requestPanel = getInfoRequestPanel();
      const revokeUrl = requestPanel?.dataset?.revokeInfoApprovalUrl;
      if (!revokeUrl) return;

      const formData = new FormData();
      checked.forEach((cb) => formData.append('performer_ids[]', cb.value));

      revokeInfoApprovalBtn.disabled = true;
      try {
        const response = await fetch(revokeUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось отменить согласование.');
        }

        window.__tableSel['info-request-select'] = [];
        window.__tableSelLast = null;
        document.body.dispatchEvent(new Event('performers-updated'));
        document.body.dispatchEvent(new Event('notifications-updated'));
      } catch (err) {
        alert(err.message || 'Не удалось отменить согласование.');
        updateInfoRequestState();
      }
      return;
    }

    const infoRequestBtn = e.target.closest('#info-request-btn');
    if (infoRequestBtn && root.contains(infoRequestBtn)) {
      const checked = getVisibleInfoRequestChecks().filter((cb) => cb.checked);
      if (!checked.length || infoRequestBtn.disabled) return;

      const requestPanel = getInfoRequestPanel();
      const requestUrl = requestPanel?.dataset?.requestUrl;
      const hoursInput = root.querySelector('#info-request-duration-hours');
      const sentAtInput = root.querySelector('#info-request-sent-at');
      const selectedChannels = getInfoRequestChannels().filter((cb) => cb.checked).map((cb) => cb.value);
      const durationHours = parseInt(hoursInput?.value || '', 10);

      if (!Number.isInteger(durationHours) || durationHours <= 0) {
        alert('Укажите срок в целых часах больше нуля.');
        hoursInput?.focus();
        return;
      }
      if (!selectedChannels.length) {
        alert('Выберите хотя бы один способ отправки.');
        return;
      }
      if (!requestUrl) return;

      const formData = new FormData();
      checked.forEach((cb) => formData.append('performer_ids[]', cb.value));
      formData.append('duration_hours', String(durationHours));
      formData.append('request_sent_at', sentAtInput?.value || '');
      selectedChannels.forEach((value) => formData.append('delivery_channels[]', value));

      infoRequestBtn.disabled = true;
      try {
        const response = await fetch(requestUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось запросить согласование.');
        }

        window.__tableSel['info-request-select'] = [];
        window.__tableSel['performer-select'] = (window.__tableSel['performer-select'] || []);
        window.__tableSelLast = null;

        const modalEl = root.querySelector('#info-request-modal');
        const modal = modalEl ? window.bootstrap?.Modal.getInstance(modalEl) : null;
        modal?.hide();

        document.body.dispatchEvent(new Event('performers-updated'));
        document.body.dispatchEvent(new Event('notifications-updated'));
      } catch (err) {
        alert(err.message || 'Не удалось запросить согласование.');
        updateInfoRequestState();
      }
      return;
    }

    const sdConfirmBtn = e.target.closest('#source-data-confirm-btn');
    if (sdConfirmBtn && root.contains(sdConfirmBtn)) {
      const projectId = getSelectedInfoRequestProjectId();
      if (!projectId) {
        alert('Выберите проект в фильтре.');
        return;
      }
      const panel = getInfoRequestPanel();
      const sdUrl = panel?.dataset?.createSourceDataUrl;
      if (!sdUrl) return;

      const statusEl = root.querySelector('#source-data-status');
      const progressEl = root.querySelector('#source-data-progress');
      const fillEl = progressEl?.querySelector('.ws-progress-fill');
      sdConfirmBtn.disabled = true;
      if (statusEl) statusEl.textContent = '';
      if (fillEl) fillEl.style.width = '0%';
      if (progressEl) progressEl.classList.remove('d-none');

      try {
        const formData = new FormData();
        formData.append('project_id', projectId);

        const response = await fetch(sdUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });

        if (!response.ok && !response.body) {
          throw new Error('Не удалось создать пространство исходных данных.');
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
          throw new Error(lastResult?.error || 'Не удалось создать пространство исходных данных.');
        }

        if (fillEl) fillEl.style.width = '100%';
        if (statusEl) statusEl.innerHTML = '<span class="text-success">' + (lastResult.message || 'Готово!') + '</span>';
      } catch (err) {
        if (progressEl) progressEl.classList.add('d-none');
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">' + (err.message || 'Ошибка') + '</span>';
        else alert(err.message || 'Не удалось создать пространство исходных данных.');
      } finally {
        sdConfirmBtn.disabled = false;
      }
      return;
    }

    const createContractConfirm = e.target.closest('#create-contract-confirm-btn');
    if (createContractConfirm && contractRoot && contractRoot.contains(createContractConfirm)) {
      const contractActionRoot = contractRoot;
      const checked = getVisibleContractChecks().filter((cb) => cb.checked && !isContractSentCheckbox(cb));
      const performerIds = getSelectedContractDraftIds();
      if (!checked.length || !performerIds.length) return;

      const panel = getContractRequestPanel();
      const createUrl = panel?.dataset?.createContractUrl;
      if (!createUrl) return;

      const statusEl = contractActionRoot.querySelector('#create-contract-status');
      const progressEl = contractActionRoot.querySelector('#create-contract-progress');
      const fillEl = progressEl?.querySelector('.ws-progress-fill');
      const modalEl = createContractConfirm.closest('.modal');
      createContractConfirm.disabled = true;
      if (statusEl) statusEl.textContent = '';
      if (fillEl) fillEl.style.width = '0%';
      if (progressEl) progressEl.classList.remove('d-none');

      const formData = new FormData();
      performerIds.forEach((id) => formData.append('performer_ids[]', id));

      try {
        const response = await fetch(createUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });

        if (!response.ok && !response.body) {
          throw new Error('Не удалось создать проект договора.');
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
          throw new Error(lastResult?.error || 'Не удалось создать проект договора.');
        }

        if (fillEl) fillEl.style.width = '100%';
        var resultHtml = '<span class="text-success">' + (lastResult.message || 'Готово!') + '</span>';
        if (lastResult.warnings && lastResult.warnings.length) {
          resultHtml += '<ul class="text-warning small mt-2 mb-0">';
          lastResult.warnings.forEach(function(w) {
            resultHtml += '<li>' + w.replace(/</g, '&lt;') + '</li>';
          });
          resultHtml += '</ul>';
        }
        if (statusEl) statusEl.innerHTML = resultHtml;

        window.__tableSel['contract-select'] = [];
        window.__tableSelLast = null;
        const refreshAfterModal = () => {
          document.body.dispatchEvent(new Event('performers-updated'));
          document.body.dispatchEvent(new Event('contracts-updated'));
        };
        if (lastResult.warnings && lastResult.warnings.length && modalEl?.classList.contains('show')) {
          modalEl.addEventListener('hidden.bs.modal', () => {
            cleanupDanglingModalState();
            refreshAfterModal();
          }, { once: true });
        } else {
          hideModalThen(modalEl, refreshAfterModal);
        }
      } catch (err) {
        if (progressEl) progressEl.classList.add('d-none');
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">' + (err.message || 'Ошибка') + '</span>';
        else alert(err.message || 'Не удалось создать проект договора.');
      } finally {
        createContractConfirm.disabled = false;
      }
      return;
    }

    const contractSignBtn = e.target.closest('#contract-sign-btn');
    if (contractSignBtn && contractRoot && contractRoot.contains(contractSignBtn)) {
      const checked = getVisibleContractChecks().filter((cb) => cb.checked && !isContractSentCheckbox(cb));
      const performerIds = getSelectedContractDraftIds();
      if (!checked.length || !performerIds.length || contractSignBtn.disabled) return;

      const contractPanel = getContractRequestPanel();
      const signUrl = contractPanel?.dataset?.signContractUrl;
      if (!signUrl) return;

      const formData = new FormData();
      performerIds.forEach((id) => formData.append('performer_ids[]', id));

      const originalHtml = contractSignBtn.innerHTML;
      contractSignBtn.disabled = true;
      contractSignBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Подписание...';
      try {
        const response = await fetch(signUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось сформировать PDF для договора.');
        }

        checked.forEach((cb) => { cb.checked = false; });
        window.__tableSel['contract-select'] = [];
        window.__tableSelLast = null;

        document.body.dispatchEvent(new Event('contracts-updated'));
        if (data.warnings && data.warnings.length) {
          alert((data.message || 'PDF для договора сформирован.') + '\n\n' + data.warnings.join('\n'));
        }
      } catch (err) {
        alert(err.message || 'Не удалось сформировать PDF для договора.');
        updateContractState();
      } finally {
        contractSignBtn.innerHTML = originalHtml;
      }
      return;
    }

    const contractBtn = e.target.closest('#contract-request-btn');
    if (contractBtn && contractRoot && contractRoot.contains(contractBtn)) {
      const contractActionRoot = contractRoot;
      const checked = getVisibleContractDispatchChecks().filter((cb) => cb.checked);
      const performerIds = getSelectedContractDispatchIds();
      if (!checked.length || contractBtn.disabled) return;

      const contractPanel = getContractRequestPanel();
      const requestUrl = contractPanel?.dataset?.requestUrl;
      const hoursInput = contractActionRoot.querySelector('#contract-duration-hours');
      const selectedChannels = getContractChannels().filter((cb) => cb.checked).map((cb) => cb.value);
      const durationHours = parseInt(hoursInput?.value || '', 10);

      if (!Number.isInteger(durationHours) || durationHours <= 0) {
        alert('Укажите срок в целых часах больше нуля.');
        hoursInput?.focus();
        return;
      }
      if (!selectedChannels.length) {
        alert('Выберите хотя бы один способ отправки.');
        return;
      }
      if (!requestUrl) return;

      const formData = new FormData();
      performerIds.forEach((id) => formData.append('performer_ids[]', id));
      formData.append('duration_hours', String(durationHours));
      selectedChannels.forEach((value) => formData.append('delivery_channels[]', value));

      contractBtn.disabled = true;
      try {
        const response = await fetch(requestUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось отправить проект договора.');
        }

        window.__tableSel['contract-select'] = [];
        window.__tableSel['contract-dispatch-select'] = [];
        window.__tableSel['performer-select'] = (window.__tableSel['performer-select'] || []);
        window.__tableSelLast = null;
        disableContractCorrectionChecksByIds(performerIds);

        const modalEl = contractActionRoot.querySelector('#contract-request-modal');
        const modal = modalEl ? window.bootstrap?.Modal.getInstance(modalEl) : null;
        modal?.hide();

        const emailDelivery = data?.email_delivery;
        if (emailDelivery?.requested && emailDelivery?.failed > 0) {
          const errorLines = (emailDelivery.errors || [])
            .slice(0, 5)
            .map((item) => {
              const channelPrefix = item.channel_label ? `[${item.channel_label}] ` : '';
              return `- ${channelPrefix}${item.recipient}: ${item.error}`;
            });
          const moreCount = Math.max((emailDelivery.errors || []).length - errorLines.length, 0);
          const details = [
            `Не удалось отправить ${emailDelivery.failed} из ${emailDelivery.attempted} email-писем.`,
            ...errorLines,
          ];
          if (moreCount > 0) {
            details.push(`- И еще ${moreCount} ошибок.`);
          }
          alert(details.join('\n'));
        }

        document.body.dispatchEvent(new Event('performers-updated'));
        document.body.dispatchEvent(new Event('notifications-updated'));
        document.body.dispatchEvent(new Event('contracts-updated'));
      } catch (err) {
        alert(err.message || 'Не удалось отправить проект договора.');
        updateContractState();
      }
      return;
    }

    const participationBatchActionBtn = e.target.closest('#participation-batch-action-btn');
    if (participationBatchActionBtn && root.contains(participationBatchActionBtn)) {
      const actionState = getParticipationBatchActionState();
      if (!actionState.mode || participationBatchActionBtn.disabled) return;

      const requestPanel = getParticipationRequestPanel();
      const url = actionState.mode === 'split'
        ? requestPanel?.dataset?.splitUrl
        : requestPanel?.dataset?.mergeUrl;
      if (!url) return;

      const formData = new FormData();
      actionState.ids.forEach((id) => formData.append('performer_ids[]', id));

      participationBatchActionBtn.disabled = true;
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось изменить объединение батча.');
        }
        rememberParticipationCollapseButtonState();
        window.__tableSel['participation-select'] = [];
        window.__tableSelLast = null;
        document.body.dispatchEvent(new Event('performers-updated'));
      } catch (err) {
        alert(err.message || 'Не удалось изменить объединение батча.');
        updateParticipationState();
      }
      return;
    }

    const requestBtn = e.target.closest('#participation-request-btn');
    if (requestBtn && root.contains(requestBtn)) {
      const checked = getVisibleParticipationChecks().filter((cb) => cb.checked && cb.dataset.requestSent !== '1');
      const performerIds = getSelectedParticipationRequestIds();
      if (!checked.length || !performerIds.length || requestBtn.disabled) return;

      const requestPanel = getParticipationRequestPanel();
      const requestUrl = requestPanel?.dataset?.requestUrl;
      const hoursInput = root.querySelector('#participation-duration-hours');
      const sentAtInput = root.querySelector('#participation-request-sent-at');
      const selectedChannels = getParticipationChannels().filter((cb) => cb.checked).map((cb) => cb.value);
      const durationHours = parseInt(hoursInput?.value || '', 10);

      if (!Number.isInteger(durationHours) || durationHours <= 0) {
        alert('Укажите срок в целых часах больше нуля.');
        hoursInput?.focus();
        return;
      }
      if (!selectedChannels.length) {
        alert('Выберите хотя бы один способ отправки.');
        return;
      }
      if (!requestUrl) return;

      const formData = new FormData();
      performerIds.forEach((id) => formData.append('performer_ids[]', id));
      formData.append('duration_hours', String(durationHours));
      formData.append('request_sent_at', sentAtInput?.value || '');
      selectedChannels.forEach((value) => formData.append('delivery_channels[]', value));

      requestBtn.disabled = true;
      try {
        const response = await fetch(requestUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось запросить подтверждение.');
        }

        window.__tableSel['participation-select'] = [];
        window.__tableSel['performer-select'] = (window.__tableSel['performer-select'] || []);
        window.__tableSelLast = null;

        const modalEl = root.querySelector('#participation-request-modal');
        const modal = modalEl ? window.bootstrap?.Modal.getInstance(modalEl) : null;
        modal?.hide();

        const emailDelivery = data?.email_delivery;
        if (emailDelivery?.requested && emailDelivery?.failed > 0) {
          const errorLines = (emailDelivery.errors || [])
            .slice(0, 5)
            .map((item) => {
              const channelPrefix = item.channel_label ? `[${item.channel_label}] ` : '';
              return `- ${channelPrefix}${item.recipient}: ${item.error}`;
            });
          const moreCount = Math.max((emailDelivery.errors || []).length - errorLines.length, 0);
          const details = [
            `Не удалось отправить ${emailDelivery.failed} из ${emailDelivery.attempted} email-писем.`,
            ...errorLines,
          ];
          if (moreCount > 0) {
            details.push(`- И еще ${moreCount} ошибок.`);
          }
          alert(details.join('\n'));
        }

        document.body.dispatchEvent(new Event('performers-updated'));
        document.body.dispatchEvent(new Event('notifications-updated'));
      } catch (err) {
        alert(err.message || 'Не удалось запросить подтверждение.');
        updateParticipationState();
      }
      return;
    }

    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;

    if (btn.closest('#report-check-actions')) {
      const action = btn.dataset.panelAction;
      const checked = getChecked('report-check-select');
      if (!checked.length) return;

      if (action === 'edit') {
        const tr = checked[0].closest('tr');
        const url = tr?.dataset?.editUrl;
        if (!url) return;
        forgetTableSelection('report-check-select');
        await htmx.ajax('GET', url, { target: '#performers-modal .modal-content', swap: 'innerHTML' });
        ensureReportCheckActionsVisibility();
        return;
      }

      window.__tableSel['report-check-select'] = checked.map(ch => String(ch.value));
      window.__tableSelLast = 'report-check-select';

      if (action === 'delete') {
        if (!confirm(`Удалить ${checked.length} строк(у/и)?`)) return;
        const urls = checked.map(ch => ch.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
        for (let i = 0; i < urls.length; i++) {
          const isLast = i === urls.length - 1;
          if (isLast) {
            await htmx.ajax('POST', urls[i], { target: '#performers-pane', swap: 'innerHTML' });
          } else {
            await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(()=>{});
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
            await htmx.ajax('POST', urls[i], { target: '#performers-pane', swap: 'innerHTML' });
          } else {
            await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(()=>{});
          }
        }
        ensureReportCheckActionsVisibility();
      }
      return;
    }

    if (btn.closest('#report-macros-actions')) {
      const action = btn.dataset.panelAction;
      const checked = getChecked('report-macro-select');
      if (!checked.length) return;

      if (action === 'edit') {
        const tr = checked[0].closest('tr');
        const url = tr?.dataset?.editUrl;
        if (!url) return;
        forgetTableSelection('report-macro-select');
        await htmx.ajax('GET', url, { target: '#performers-modal .modal-content', swap: 'innerHTML' });
        ensureReportMacrosActionsVisibility();
        return;
      }

      window.__tableSel['report-macro-select'] = checked.map(ch => String(ch.value));
      window.__tableSelLast = 'report-macro-select';

      if (action === 'delete') {
        if (!confirm(`Удалить ${checked.length} строк(у/и)?`)) return;
        const urls = checked.map(ch => {
          const url = ch.closest('tr')?.dataset?.deleteUrl;
          return url ? url + reportMacrosListQuery() : '';
        }).filter(Boolean);
        for (let i = 0; i < urls.length; i++) {
          const isLast = i === urls.length - 1;
          if (isLast) {
            await htmx.ajax('POST', urls[i], { target: '#performers-pane', swap: 'innerHTML' });
          } else {
            await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(()=>{});
          }
        }
        return;
      }

      if (action === 'up' || action === 'down') {
        let urls = checked
          .map(ch => {
            const url = ch.closest('tr')?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'];
            return url ? url + reportMacrosListQuery() : '';
          })
          .filter(Boolean);
        if (action === 'down') urls = urls.reverse();
        for (let i = 0; i < urls.length; i++) {
          const isLast = i === urls.length - 1;
          if (isLast) {
            await htmx.ajax('POST', urls[i], { target: '#performers-pane', swap: 'innerHTML' });
          } else {
            await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(()=>{});
          }
        }
        ensureReportMacrosActionsVisibility();
      }
      return;
    }

    if (!btn.closest('#performers-actions')) return;

    const action = btn.dataset.panelAction; // up|down|edit|delete
    const checked = getChecked('performer-select');
    if (!checked.length) return;

    // кеш выбора
    window.__tableSel['performer-select'] = checked.map(ch => String(ch.value));
    window.__tableSelLast = 'performer-select';

    if (action === 'edit') {
      const tr = checked[0].closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;
      await htmx.ajax('GET', url, { target: '#performers-modal .modal-content', swap: 'innerHTML' });
      ensurePerformerActionsVisibility();
      return;
    }

    if (action === 'delete') {
      const deletable = checked.filter((box) => !performerRowDeleteLocked(box.closest('tr')));
      if (!deletable.length) return;
      if (!confirm(`Удалить ${deletable.length} строк(у/и)?`)) return;
      const urls = deletable.map(ch => ch.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#performers-pane', swap: 'innerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(()=>{});
        }
      }
      return;
    }

    if (action === 'up' || action === 'down') {
      if (checked.some((box) => performerRowIsSectionLocked(box.closest('tr')))) return;
      if (movePerformerSelectionImmediately(action, checked)) return;
      let urls = checked
        .map(ch => ch.closest('tr')?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'])
        .filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#performers-pane', swap: 'innerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(()=>{});
        }
      }
      ensurePerformerActionsVisibility();
    }
  });

  document.body.addEventListener('queued-row-order:conflict', function(e) {
    const root = pane();
    const table = e.detail && e.detail.table;
    if (!root || !table || !root.contains(table)) return;
    window.__tableSel['performer-select'] = getChecked('performer-select').map((box) => String(box.value));
    window.__tableSelLast = 'performer-select';
    document.body.dispatchEvent(new Event('performers-updated'));
  });

  // мастер-чекбокс
  document.addEventListener('change', (e) => {
    const paymentRequestMaster = e.target.closest('.js-payment-request-master');
    const paymentSectionFromMaster = paymentRequestMaster ? findPaymentRequestSection(paymentRequestMaster) : null;
    if (paymentRequestMaster && paymentSectionFromMaster) {
      getPaymentRequestRows(paymentSectionFromMaster).forEach((row) => {
        if (isFilterHidden(row)) return;
        const checkbox = row.querySelector('input[name="payment-request-select"]');
        if (!checkbox || checkbox.disabled) return;
        checkbox.checked = paymentRequestMaster.checked;
      });
      paymentRequestMaster.indeterminate = false;
      updatePaymentRequestState(paymentSectionFromMaster);
      return;
    }

    const paymentRequestRowCb = e.target.closest('tbody input.form-check-input[name="payment-request-select"]');
    const paymentSectionFromRow = paymentRequestRowCb ? findPaymentRequestSection(paymentRequestRowCb) : null;
    if (paymentRequestRowCb && paymentSectionFromRow) {
      propagateGroupCheck(paymentRequestRowCb, 'payment-request-select');
      updatePaymentRequestState(paymentSectionFromRow);
      return;
    }

    const paymentRequestChannelCb = e.target.closest('.js-payment-request-channel');
    const paymentSectionFromChannel = paymentRequestChannelCb ? findPaymentRequestSection(paymentRequestChannelCb) : null;
    if (paymentRequestChannelCb && paymentSectionFromChannel) {
      const checkedChannels = getPaymentRequestChannels(paymentSectionFromChannel).filter((cb) => cb.checked);
      if (!checkedChannels.length) {
        paymentRequestChannelCb.checked = true;
      }
      return;
    }

    const root = pane(); if (!root) return;
    const contractRoot = contractPane();

    const master = e.target.closest('input.form-check-input[data-actions-id="performers-actions"]');
    if (master && root.contains(master)) {
      getVisiblePerformerChecks().forEach(b => { b.checked = master.checked; });
      master.indeterminate = false;
      updatePerformerMasterState();
      updateRowHighlight('performer-select');
      ensurePerformerActionsVisibility();
      return;
    }

    const participationMaster = e.target.closest('#participation-master');
    if (participationMaster && root.contains(participationMaster)) {
      getParticipationRows().forEach((row) => {
        if (isFilterHidden(row)) return;
        const checkbox = row.querySelector('input[name="participation-select"]');
        if (!checkbox || checkbox.disabled) return;
        if (checkbox) checkbox.checked = participationMaster.checked;
      });
      participationMaster.indeterminate = false;
      updateParticipationState();
      return;
    }

    const rowCb = e.target.closest('tbody input.form-check-input[name="performer-select"]');
    if (rowCb && root.contains(rowCb)) {
      updatePerformerMasterState();
      updateRowHighlight('performer-select');
      ensurePerformerActionsVisibility();
      return;
    }

    const participationRowCb = e.target.closest('tbody input.form-check-input[name="participation-select"]');
    if (participationRowCb && root.contains(participationRowCb)) {
      propagateGroupCheck(participationRowCb, 'participation-select');
      updateParticipationState();
      return;
    }

    const participationChannelCb = e.target.closest('.js-participation-channel');
    if (participationChannelCb && root.contains(participationChannelCb)) {
      const checkedChannels = getParticipationChannels().filter((cb) => cb.checked);
      if (!checkedChannels.length) {
        participationChannelCb.checked = true;
      }
    }

    const contractMaster = e.target.closest('#contract-master');
    if (contractMaster && contractRoot && contractRoot.contains(contractMaster)) {
      getContractDraftRows().forEach((row) => {
        if (isFilterHidden(row)) return;
        const checkbox = row.querySelector('input[name="contract-select"]');
        if (!checkbox || checkbox.disabled) return;
        checkbox.checked = contractMaster.checked;
      });
      contractMaster.indeterminate = false;
      updateContractState();
      return;
    }

    const contractDispatchMaster = e.target.closest('#contract-dispatch-master');
    if (contractDispatchMaster && contractRoot && contractRoot.contains(contractDispatchMaster)) {
      getContractDispatchRows().forEach((row) => {
        if (isFilterHidden(row)) return;
        const checkbox = row.querySelector('input[name="contract-dispatch-select"]');
        if (!checkbox || checkbox.disabled) return;
        checkbox.checked = contractDispatchMaster.checked;
      });
      contractDispatchMaster.indeterminate = false;
      updateContractState();
      return;
    }

    const contractRowCb = e.target.closest('tbody input.form-check-input[name="contract-select"]');
    if (contractRowCb && contractRoot && contractRoot.contains(contractRowCb)) {
      propagateGroupCheck(contractRowCb, 'contract-select');
      updateContractState();
      return;
    }

    const contractDispatchRowCb = e.target.closest('tbody input.form-check-input[name="contract-dispatch-select"]');
    if (contractDispatchRowCb && contractRoot && contractRoot.contains(contractDispatchRowCb)) {
      propagateGroupCheck(contractDispatchRowCb, 'contract-dispatch-select');
      updateContractState();
      return;
    }

    const contractChannelCb = e.target.closest('.js-contract-channel');
    if (contractChannelCb && contractRoot && contractRoot.contains(contractChannelCb)) {
      const checkedChannels = getContractChannels().filter((cb) => cb.checked);
      if (!checkedChannels.length) {
        contractChannelCb.checked = true;
      }
    }

    const infoRequestMaster = e.target.closest('#info-request-master');
    if (infoRequestMaster && root.contains(infoRequestMaster)) {
      getInfoRequestRows().forEach((row) => {
        if (isFilterHidden(row)) return;
        const checkbox = row.querySelector('input[name="info-request-select"]');
        if (!checkbox || checkbox.disabled) return;
        checkbox.checked = infoRequestMaster.checked;
      });
      infoRequestMaster.indeterminate = false;
      updateInfoRequestState();
      return;
    }

    const infoRequestRowCb = e.target.closest('tbody input.form-check-input[name="info-request-select"]');
    if (infoRequestRowCb && root.contains(infoRequestRowCb)) {
      propagateGroupCheck(infoRequestRowCb, 'info-request-select');
      updateInfoRequestState();
      return;
    }

    const infoRequestChannelCb = e.target.closest('.js-info-request-channel');
    if (infoRequestChannelCb && root.contains(infoRequestChannelCb)) {
      const checkedChannels = getInfoRequestChannels().filter((cb) => cb.checked);
      if (!checkedChannels.length) {
        infoRequestChannelCb.checked = true;
      }
    }
  });

  // ── Source-data settings modal (gear) ──

  function initSourceDataSettingsModal() {
    const modalEl = document.getElementById('source-data-settings-modal');
    if (!modalEl || modalEl.dataset.sdBound === '1') return;
    modalEl.dataset.sdBound = '1';

    modalEl.addEventListener('show.bs.modal', async () => {
      const panel = document.getElementById('info-request-actions');
      const url = panel?.dataset?.sourceDataTargetUrl;
      if (!url) return;

      const select = modalEl.querySelector('#source-data-target-select');
      if (!select) return;

      try {
        const resp = await fetch(url, { headers: { 'X-CSRFToken': csrftoken } });
        const data = await resp.json();
        select.innerHTML = '';
        (data.options || []).forEach((name) => {
          const opt = document.createElement('option');
          opt.value = name;
          opt.textContent = name;
          if (name === data.folder_name) opt.selected = true;
          select.appendChild(opt);
        });
      } catch (_) { /* ignore */ }
    });

    const saveBtn = modalEl.querySelector('#source-data-target-save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', async () => {
        const panel = document.getElementById('info-request-actions');
        const saveUrl = panel?.dataset?.sourceDataTargetSaveUrl;
        if (!saveUrl) return;

        const select = modalEl.querySelector('#source-data-target-select');
        const folderName = select?.value;
        if (!folderName) return;

        saveBtn.disabled = true;
        try {
          const resp = await fetch(saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify({ folder_name: folderName }),
          });
          const data = await resp.json();
          if (!data.ok) throw new Error(data.error || 'Ошибка сохранения');
          const modal = window.bootstrap?.Modal.getInstance(modalEl);
          modal?.hide();
        } catch (err) {
          alert(err.message || 'Не удалось сохранить.');
        } finally {
          saveBtn.disabled = false;
        }
      });
    }
  }
  initSourceDataSettingsModal();

  // ── Create-contract settings modal (gear) ──

  function initCreateContractSettingsModal() {
    const modalEl = document.getElementById('create-contract-modal');
    if (!modalEl || modalEl.dataset.ccBound === '1') return;
    modalEl.dataset.ccBound = '1';

    modalEl.addEventListener('show.bs.modal', async () => {
      const panel = document.getElementById('contract-request-actions');
      const url = panel?.dataset?.contractTargetUrl;
      if (!url) return;

      const select = modalEl.querySelector('#create-contract-target-select');
      if (!select) return;

      try {
        const resp = await fetch(url, { headers: { 'X-CSRFToken': csrftoken } });
        const data = await resp.json();
        select.innerHTML = '';
        (data.options || []).forEach((name) => {
          const opt = document.createElement('option');
          opt.value = name;
          opt.textContent = name;
          if (name === data.folder_name) opt.selected = true;
          select.appendChild(opt);
        });
      } catch (_) { /* ignore */ }
    });

    const saveBtn = modalEl.querySelector('#create-contract-target-save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', async () => {
        const panel = document.getElementById('contract-request-actions');
        const saveUrl = panel?.dataset?.contractTargetSaveUrl;
        if (!saveUrl) return;

        const select = modalEl.querySelector('#create-contract-target-select');
        const folderName = select?.value;
        if (!folderName) return;

        saveBtn.disabled = true;
        try {
          const resp = await fetch(saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify({ folder_name: folderName }),
          });
          const data = await resp.json();
          if (!data.ok) throw new Error(data.error || 'Ошибка сохранения');
          const modal = window.bootstrap?.Modal.getInstance(modalEl);
          modal?.hide();
        } catch (err) {
          alert(err.message || 'Не удалось сохранить.');
        } finally {
          saveBtn.disabled = false;
        }
      });
    }
  }
  initCreateContractSettingsModal();

  document.addEventListener('show.bs.modal', (e) => {
    if (!e.target.matches('#create-contract-progress-modal')) return;
    const progressEl = e.target.querySelector('#create-contract-progress');
    const fillEl = progressEl?.querySelector('.ws-progress-fill');
    const statusEl = e.target.querySelector('#create-contract-status');
    if (progressEl) progressEl.classList.add('d-none');
    if (fillEl) fillEl.style.width = '0%';
    if (statusEl) statusEl.textContent = '';
  });

  function restorePerformersPane(root) {
    // Re-apply main performers filter, labels and totals before the browser
    // paints to avoid a visible flash of unfiltered / empty-totals state.
    (function earlyRestore() {
      var FA = '__all__';
      var pf = window.__perfProjectFilter || [FA];
      var af = window.__perfAssetFilter || [FA];
      var allProj = !pf.length || pf.indexOf(FA) !== -1;
      var allAsset = !af.length || af.indexOf(FA) !== -1;

      var perfRows = root.querySelectorAll(
        '#performers-main-section table.performers-table tbody tr[data-project-id]'
      );

      if (!allProj || !allAsset) {
        perfRows.forEach(function(row) {
          var mp = allProj || pf.indexOf(row.dataset.projectId || '') !== -1;
          var ma = allAsset || af.indexOf(row.dataset.assetName || '') !== -1;
          if (!(mp && ma)) row.classList.add('d-none');
        });
      }
      if (typeof window.__enforceMasterOnRows === 'function') window.__enforceMasterOnRows();
      if (typeof window.__syncPaymentRequestFilter === 'function') {
        window.__syncPaymentRequestFilter(window.__paymentRequestsProjectFilter || [FA]);
      }

      // --- filter labels ---
      var projLabel = root.querySelector('.js-perf-filter-label');
      if (projLabel) {
        if (allProj) {
          projLabel.textContent = 'Все';
        } else if (pf.length === 1) {
          var cb = root.querySelector('.js-perf-filter[value="' + CSS.escape(pf[0]) + '"]');
          projLabel.textContent = window.getProjectFilterSummaryLabel(cb, '1 проект');
        } else {
          projLabel.textContent = pf.length + ' выбрано';
        }
      }
      var assetLabel = root.querySelector('.js-perf-asset-label');
      if (assetLabel) {
        if (allAsset) assetLabel.textContent = 'Все';
        else if (af.length === 1) assetLabel.textContent = af[0];
        else assetLabel.textContent = af.length + ' выбрано';
      }

      // --- totals ---
      var sums = { actual: {}, estimated: {}, agreed: {} };
      perfRows.forEach(function(row) {
        if (row.classList.contains('d-none')) return;
        var a = row.querySelector('[data-sum-actual]');
        var e = row.querySelector('[data-sum-estimated]');
        var g = row.querySelector('[data-sum-agreed]');
        [['actual', a, 'sumActual'], ['estimated', e, 'sumEstimated'], ['agreed', g, 'sumAgreed']].forEach(function(t) {
          var cell = t[1];
          if (!cell) return;
          var val = parseFloat(cell.dataset[t[2]]) || 0;
          if (!val) return;
          var cur = cell.dataset.currency || '';
          if (!sums[t[0]][cur]) sums[t[0]][cur] = 0;
          sums[t[0]][cur] += val;
        });
      });
      function fmtT(n) {
        var p = n.toFixed(2).split('.');
        p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
        return p.join(',');
      }
      function renderS(obj) {
        var parts = [];
        for (var c in obj) {
          if (!obj[c]) continue;
          var s = fmtT(obj[c]);
          if (c) s += ' ' + c;
          parts.push(s);
        }
        return parts.join(', ');
      }
      var elA = root.querySelector('#perf-total-actual');
      var elE = root.querySelector('#perf-total-estimated');
      var elG = root.querySelector('#perf-total-agreed');
      if (elA) elA.textContent = renderS(sums.actual);
      if (elE) elE.textContent = renderS(sums.estimated);
      if (elG) elG.textContent = renderS(sums.agreed);
    })();

    var performerIds = (window.__tableSel && window.__tableSel['performer-select']) || [];
    var performerSet = new Set(performerIds || []);
    getRowChecks('performer-select').forEach(function(b) { b.checked = performerSet.has(String(b.value)); });
    updatePerformerMasterState();
    updateRowHighlight('performer-select');
    ensurePerformerActionsVisibility();
    try { delete window.__tableSel['performer-select']; } catch(_) {}

    var participationIds = (window.__tableSel && window.__tableSel['participation-select']) || [];
    var participationSet = new Set(participationIds || []);
    getRowChecks('participation-select').forEach(function(b) { b.checked = participationSet.has(String(b.value)); });
    initParticipationProjectFilter();
    updateParticipationState();
    try { delete window.__tableSel['participation-select']; } catch(_) {}

    var contractIds = (window.__tableSel && window.__tableSel['contract-select']) || [];
    var contractSet = new Set(contractIds || []);
    getRowChecks('contract-select').forEach(function(b) { b.checked = contractSet.has(String(b.value)); });
    var contractDispatchIds = (window.__tableSel && window.__tableSel['contract-dispatch-select']) || [];
    var contractDispatchSet = new Set(contractDispatchIds || []);
    getRowChecks('contract-dispatch-select').forEach(function(b) { b.checked = contractDispatchSet.has(String(b.value)); });
    initContractProjectFilter();
    updateContractState();
    try { delete window.__tableSel['contract-select']; } catch(_) {}
    try { delete window.__tableSel['contract-dispatch-select']; } catch(_) {}

    var infoRequestIds = (window.__tableSel && window.__tableSel['info-request-select']) || [];
    var infoRequestSet = new Set(infoRequestIds || []);
    getRowChecks('info-request-select').forEach(function(b) { b.checked = infoRequestSet.has(String(b.value)); });
    initInfoRequestProjectFilter();
    updateInfoRequestState();
    initSourceDataSettingsModal();
    initCreateContractSettingsModal();
    try { delete window.__tableSel['info-request-select']; } catch(_) {}

    var paymentRequestIds = (window.__tableSel && window.__tableSel['payment-request-select']) || [];
    var paymentRequestSet = new Set(paymentRequestIds || []);
    getRowChecks('payment-request-select').forEach(function(b) { b.checked = paymentRequestSet.has(String(b.value)); });
    initPaymentRequestProjectFilter();
    syncPaymentRequestRowsState();
    updatePaymentRequestState();
    try { delete window.__tableSel['payment-request-select']; } catch(_) {}

    var reportIds = (window.__tableSel && window.__tableSel['report-select']) || [];
    var reportSet = new Set(reportIds || []);
    getRowChecks('report-select').forEach(function(b) { b.checked = reportSet.has(String(b.value)); });
    initReportSubmissionProjectFilter();
    initReportSubmissionColPicker();
    restoreReportRemarksChannels();
    initReportLocalSource();
    applyRowGrouping(root.querySelector('#report-submission-section'));
    applyReportVersionCollapsedState();
    initReportCheckPolling();
    updateReportSubmissionMasterState();
    updateRowHighlight('report-select');
    try { delete window.__tableSel['report-select']; } catch(_) {}

    var reportCheckIds = (window.__tableSel && window.__tableSel['report-check-select']) || [];
    var reportCheckSet = new Set(reportCheckIds || []);
    getRowChecks('report-check-select').forEach(function(b) { b.checked = reportCheckSet.has(String(b.value)); });
    updateReportCheckMasterState();
    updateRowHighlight('report-check-select');
    ensureReportCheckActionsVisibility();
    try { delete window.__tableSel['report-check-select']; } catch(_) {}

    var reportMacroIds = (window.__tableSel && window.__tableSel['report-macro-select']) || [];
    var reportMacroSet = new Set(reportMacroIds || []);
    getRowChecks('report-macro-select').forEach(function(b) { b.checked = reportMacroSet.has(String(b.value)); });
    updateReportMacrosMasterState();
    updateRowHighlight('report-macro-select');
    ensureReportMacrosActionsVisibility();
    try { delete window.__tableSel['report-macro-select']; } catch(_) {}

    applyRowGrouping(root.querySelector('#participation-confirmation-section'));
    applyParticipationSentState();
    reapplyParticipationCollapse();
    applyRowGrouping(root.querySelector('#contract-conclusion-section'));
    applyContractSentState();
    updateContractState();
    reapplyContractCollapse();
    applyRowGrouping(root.querySelector('#info-request-approval-section'));
    reapplyInfoRequestCollapse();
    syncCollapseButtons();

    window.__tableSelLast = null;
  }

  function restoreContractConclusionPane(root) {
    if (!root || !root.querySelector('#contract-conclusion-section')) return;
    var contractIds = (window.__tableSel && window.__tableSel['contract-select']) || [];
    var contractSet = new Set(contractIds || []);
    getRowChecks('contract-select').forEach(function(b) {
      b.checked = contractSet.has(String(b.value));
    });
    var contractDispatchIds = (window.__tableSel && window.__tableSel['contract-dispatch-select']) || [];
    var contractDispatchSet = new Set(contractDispatchIds || []);
    getRowChecks('contract-dispatch-select').forEach(function(b) {
      b.checked = contractDispatchSet.has(String(b.value));
    });
    initContractProjectFilter();
    initCreateContractSettingsModal();
    applyRowGrouping(root.querySelector('#contract-conclusion-section'));
    applyContractSentState();
    updateContractState();
    reapplyContractCollapse();
    syncCollapseButtons();
    try { delete window.__tableSel['contract-select']; } catch(_) {}
    try { delete window.__tableSel['contract-dispatch-select']; } catch(_) {}
  }

  document.body.addEventListener('htmx:beforeSwap', function (e) {
    var root = pane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    window.__perfScrollY = window.scrollY;
  });

  document.body.addEventListener('htmx:afterSwap', function (e) {
    var root = pane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    restorePerformersPane(root);
    if (typeof window.__perfScrollY === 'number') {
      window.scrollTo(0, window.__perfScrollY);
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (e) {
    var root = contractPane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    restoreContractConclusionPane(root);
  });

  document.body.addEventListener('htmx:afterSettle', function (e) {
    var root = pane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    ensurePerformerActionsVisibility();
    ensureReportCheckActionsVisibility();
    ensureReportMacrosActionsVisibility();
    syncPerformerSectionOrder();
    schedulePaymentRequestScrollGapsUpdate();
    scheduleReportSubmissionColumnLayout(true);
    if (typeof window.__perfScrollY === 'number') {
      window.scrollTo(0, window.__perfScrollY);
      delete window.__perfScrollY;
    }
  });

  document.body.addEventListener('htmx:afterSettle', function (e) {
    var executionPane = document.getElementById('contracts-execution-pane');
    if (!executionPane || e.target !== executionPane) return;
    initPaymentRequestProjectFilter();
    syncPaymentRequestRowsState();
    updatePaymentRequestState();
    schedulePaymentRequestScrollGapsUpdate();
  });

  // ---- Prev / Next navigation inside performers modal ----

  function getVisiblePerfRows() {
    var root = pane();
    if (!root) return [];
    return Array.from(root.querySelectorAll(
      '#performers-main-section table.performers-table tbody tr[data-project-id]'
    )).filter(function(r) {
      if (r.classList.contains('d-none')) return false;
      var cb = r.querySelector('input[name="performer-select"]');
      return !cb || !cb.disabled;
    });
  }

  function findCurrentPerfIndex(rows) {
    var checked = getChecked('performer-select');
    if (!checked.length) return -1;
    var id = String(checked[0].value);
    for (var i = 0; i < rows.length; i++) {
      var cb = rows[i].querySelector('input[name="performer-select"]');
      if (cb && String(cb.value) === id) return i;
    }
    return -1;
  }

  function updatePerfNavButtons() {
    var modal = document.getElementById('performers-modal');
    if (!modal) return;
    var prevBtn = modal.querySelector('[data-perf-nav="prev"]');
    var nextBtn = modal.querySelector('[data-perf-nav="next"]');
    if (!prevBtn && !nextBtn) return;
    var rows = getVisiblePerfRows();
    var idx = findCurrentPerfIndex(rows);
    if (prevBtn) prevBtn.disabled = idx <= 0;
    if (nextBtn) nextBtn.disabled = idx < 0 || idx >= rows.length - 1;
  }

  document.body.addEventListener('htmx:afterSwap', function (e) {
    var modal = document.getElementById('performers-modal');
    if (!modal) return;
    var mc = modal.querySelector('.modal-content');
    if (mc && (e.target === mc || mc.contains(e.target))) updatePerfNavButtons();
  });

  function rawMoneyValue(v) {
    return String(v).replace(/\s/g, '').replace(/\u00a0/g, '').replace(',', '.');
  }

  function swapModalHtml(container, html) {
    container.innerHTML = html;
    Array.from(container.querySelectorAll('script')).forEach(function(old) {
      var s = document.createElement('script');
      Array.from(old.attributes).forEach(function(a) { s.setAttribute(a.name, a.value); });
      s.textContent = old.textContent;
      old.parentNode.replaceChild(s, old);
    });
    htmx.process(container);
  }

  document.addEventListener('click', async function (e) {
    var navBtn = e.target.closest('[data-perf-nav]');
    if (!navBtn) return;
    var modal = document.getElementById('performers-modal');
    if (!modal || !modal.contains(navBtn)) return;

    var direction = navBtn.dataset.perfNav;
    var rows = getVisiblePerfRows();
    var idx = findCurrentPerfIndex(rows);
    var targetIdx = direction === 'next' ? idx + 1 : idx - 1;
    if (targetIdx < 0 || targetIdx >= rows.length) return;

    var targetRow = rows[targetIdx];
    var targetUrl = targetRow.dataset.editUrl;
    var targetCb = targetRow.querySelector('input[name="performer-select"]');
    var targetId = targetCb ? String(targetCb.value) : null;
    if (!targetUrl || !targetId) return;

    var mc = modal.querySelector('.modal-content');
    var form = mc?.querySelector('form');
    var postUrl = form?.getAttribute('hx-post');

    if (form && postUrl) {
      navBtn.disabled = true;
      mc.querySelectorAll('.js-money-input').forEach(function(inp) {
        inp.value = rawMoneyValue(inp.value);
      });

      var formData = new FormData(form);

      try {
        var resp = await fetch(postUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });

        if (resp.status === 204) {
          getRowChecks('performer-select').forEach(function(b) { b.checked = false; });
          if (targetCb) targetCb.checked = true;
          window.__tableSel['performer-select'] = [targetId];
          window.__tableSelLast = 'performer-select';
          updatePerformerMasterState();
          updateRowHighlight('performer-select');
          ensurePerformerActionsVisibility();

          var paneEl = document.getElementById('performers-pane');
          var paneUrl = paneEl?.getAttribute('hx-get');

          await htmx.ajax('GET', targetUrl, {
            target: '#performers-modal .modal-content', swap: 'innerHTML'
          });

          if (paneUrl) {
            htmx.ajax('GET', paneUrl, {
              target: '#performers-pane', swap: 'innerHTML'
            });
          }
        } else {
          var html = await resp.text();
          swapModalHtml(mc, html);
        }
      } catch (err) {
        console.error('perf-nav save error', err);
        navBtn.disabled = false;
      }
    }
  });

  function showProjectsCsvResult(html) {
    var body = document.getElementById('projects-csv-result-body');
    var modalEl = document.getElementById('projects-csv-result-modal');
    if (!body || !modalEl) {
      alert(html.replace(/<[^>]+>/g, ''));
      return;
    }
    body.innerHTML = html;
    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  async function handleReportMacrosCsvUpload(uploadUrl, file) {
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
        showProjectsCsvResult(html);
        document.body.dispatchEvent(new Event('performers-updated'));
      } else {
        showProjectsCsvResult('<div class="text-danger"><strong>Ошибка:</strong> ' +
          (data.error || 'Неизвестная ошибка').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
      }
    } catch (err) {
      showProjectsCsvResult('<div class="text-danger"><strong>Ошибка загрузки:</strong> ' +
        err.message.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
    }
  }

  document.body.addEventListener('htmx:configRequest', function (evt) {
    const path = evt.detail && evt.detail.path || '';
    if (path.indexOf('performers/partial') === -1 || !evt.detail.parameters) return;
    const macros = document.querySelector('#report-macros-section');
    if (macros) {
      evt.detail.parameters.macros_page = macros.dataset.macrosPage || '1';
      evt.detail.parameters.macros_page_size = macros.dataset.macrosPageSize || '25';
    }
    const reports = document.querySelector('#report-submission-table-block');
    if (reports) {
      const filter = window.__reportSubmissionProjectFilter || [];
      const filtered = filter.length && filter.indexOf('__all__') === -1;
      const rendered = (reports.dataset.reportsProjects || '__all__').split(',').filter(Boolean).sort();
      const wanted = filtered ? filter.map(String).slice().sort() : ['__all__'];
      const sameFilter = rendered.length === wanted.length && rendered.every(function (value, index) {
        return value === wanted[index];
      });
      evt.detail.parameters.reports_page = sameFilter ? (reports.dataset.reportsPage || '1') : '1';
      if (filtered && !sameFilter) {
        const select = document.querySelector('#policy-page-size-report-submission');
        evt.detail.parameters.reports_page_size = (select && select.options.length)
          ? select.options[select.options.length - 1].value
          : '100';
      } else if (!filtered) {
        const blockUnfiltered = (reports.dataset.reportsProjects || '__all__') === '__all__';
        if (blockUnfiltered && reports.dataset.reportsPageSize) {
          window.__reportSubmissionPageSize = reports.dataset.reportsPageSize;
        }
        evt.detail.parameters.reports_page_size = window.__reportSubmissionPageSize || '25';
      } else {
        evt.detail.parameters.reports_page_size = reports.dataset.reportsPageSize || '100';
      }
      if (filtered) evt.detail.parameters.reports_project = filter.join(',');
    }
  });

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('#report-macros-csv-upload-btn');
    if (!btn) return;
    var fileInput = document.getElementById('report-macros-csv-file-input');
    if (fileInput) {
      fileInput.value = '';
      fileInput.click();
    }
  });

  document.addEventListener('change', async function (e) {
    if (e.target.id !== 'report-macros-csv-file-input') return;
    var file = e.target.files && e.target.files[0];
    var btn = document.getElementById('report-macros-csv-upload-btn');
    var uploadUrl = btn && btn.getAttribute('data-upload-url');
    e.target.value = '';
    if (!file || !uploadUrl) return;
    await handleReportMacrosCsvUpload(uploadUrl, file);
  });

  document.addEventListener('DOMContentLoaded', () => {
    initParticipationProjectFilter();
    initContractProjectFilter();
    initInfoRequestProjectFilter();
    initPaymentRequestProjectFilter();
    initReportSubmissionProjectFilter();
    initReportSubmissionColPicker();
    restoreReportRemarksChannels();
    initReportLocalSource();
    initReportCheckPolling();
    var root = pane();
    if (root) {
      applyRowGrouping(root.querySelector('#participation-confirmation-section'));
      applyParticipationSentState();
      reapplyParticipationCollapse();
      applyRowGrouping(root.querySelector('#contract-conclusion-section'));
      applyContractSentState();
      updateContractState();
      reapplyContractCollapse();
      applyRowGrouping(root.querySelector('#info-request-approval-section'));
      reapplyInfoRequestCollapse();
      applyRowGrouping(root.querySelector('#report-submission-section'));
      applyReportVersionCollapsedState();
      updatePaymentRequestState();
      updateReportSubmissionMasterState();
      updateReportCheckMasterState();
      updateRowHighlight('report-check-select');
      ensureReportCheckActionsVisibility();
      updateReportMacrosMasterState();
      updateRowHighlight('report-macro-select');
      ensureReportMacrosActionsVisibility();
      syncCollapseButtons();
      syncPerformerSectionOrder();
    }
    schedulePaymentRequestScrollGapsUpdate();

    const perfModal = document.getElementById('performers-modal');
    if (perfModal) {
      perfModal.addEventListener('hidden.bs.modal', () => {
        clearTableSelectionByName('performer-select');
        clearTableSelectionByName('report-check-select');
        clearTableSelectionByName('report-macro-select');
      });
    }
  });

  window.addEventListener('resize', function() {
    schedulePaymentRequestScrollGapsUpdate();
    scheduleReportSubmissionColumnLayout(false);
  });
  window.addEventListener('load', function() {
    schedulePaymentRequestScrollGapsUpdate();
    scheduleReportSubmissionColumnLayout(true);
  });
  window.addEventListener('projects:section-shown', function(e) {
    if (e.detail && (e.detail.section === 'team' || e.detail.section === 'performer-payments' || e.detail.section === 'info-request' || e.detail.section === 'report-submission')) {
      schedulePaymentRequestScrollGapsUpdate();
    }
    if (e.detail && e.detail.section === 'report-submission') {
      scheduleReportSubmissionColumnLayout(true);
    }
  });
  window.addEventListener('contracts:payment-request-shown', function() {
    initPaymentRequestProjectFilter();
    syncPaymentRequestRowsState();
    updatePaymentRequestState();
    schedulePaymentRequestScrollGapsUpdate();
  });
})();