(function () {
  if (window.__proposalsPanelBound) return;
  window.__proposalsPanelBound = true;

  window.__tableSel = window.__tableSel || {};
  window.__tableSelLast = window.__tableSelLast || null;
  window.__proposalPendingScrollRestore = window.__proposalPendingScrollRestore || null;

  function pane() {
    return document.getElementById('proposals-pane');
  }

  function qa(selector, root) {
    return Array.from((root || document).querySelectorAll(selector));
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function getCookie(name) {
    const match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? match.pop() : '';
  }

  const csrftoken = getCookie('csrftoken');
  const SELECT_NAMES = ['proposal-select', 'proposal-dispatch-select', 'proposal-template-select', 'proposal-variable-select'];
  const PROPOSAL_SEND_PREF_KEY = 'proposals:dispatch-send-settings';
  const PROPOSAL_KIND_FILTER_PREF_KEY = 'proposals:kind-filter';
  const PROPOSAL_STATUS_FILTER_PREF_KEY = 'proposals:status-filter';
  const PROPOSAL_KIND_FILTER_ALL = '__all__';
  const PROPOSAL_STATUS_FILTER_ALL = '__all__';
  const PROPOSAL_STATUS_FILTER_OPTIONS = [
    { value: 'preliminary', label: 'Предварительное' },
    { value: 'final', label: 'Итоговое' },
    { value: 'sent', label: 'Отправленное' },
    { value: 'completed', label: 'Завершённое' },
    { value: 'not_held', label: 'Несостоявшееся' },
  ];
  const QUILL_JS = '/static/letters_app/vendor/quill/quill.min.js';
  const QUILL_CSS = '/static/letters_app/vendor/quill/quill.snow.css';
  let proposalQuillLoaded = false;
  let proposalQuillLoading = false;
  let proposalQuillReadyCallbacks = [];
  window.__proposalKindFilter = window.__proposalKindFilter || [PROPOSAL_KIND_FILTER_ALL];
  window.__proposalStatusFilter = window.__proposalStatusFilter || [PROPOSAL_STATUS_FILTER_ALL];

  function ensureProposalQuillFormats() {
    if (!window.Quill || window.__proposalQuillFormatsReady) return;
    const Font = window.Quill.import('formats/font');
    Font.whitelist = ['calibri', 'cambria', 'sans', 'serif', 'monospace', 'georgia', 'times-new-roman'];
    window.Quill.register(Font, true);
    window.__proposalQuillFormatsReady = true;
  }

  function loadProposalQuill(callback) {
    if (proposalQuillLoaded || window.Quill) {
      proposalQuillLoaded = true;
      ensureProposalQuillFormats();
      callback();
      return;
    }
    proposalQuillReadyCallbacks.push(callback);
    if (proposalQuillLoading) return;
    proposalQuillLoading = true;

    if (!document.querySelector('link[href="' + QUILL_CSS + '"]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = QUILL_CSS;
      document.head.appendChild(link);
    }

    const script = document.createElement('script');
    script.src = QUILL_JS;
    script.onload = function () {
      ensureProposalQuillFormats();
      proposalQuillLoaded = true;
      proposalQuillLoading = false;
      proposalQuillReadyCallbacks.forEach(function (cb) { cb(); });
      proposalQuillReadyCallbacks = [];
    };
    script.onerror = function () {
      proposalQuillLoading = false;
      console.error('Failed to load Quill.js for proposals.');
    };
    document.body.appendChild(script);
  }

  function updateHeaderPath() {
    const heading = document.getElementById('proposals-section-heading');
    const kindFilterDropdown = document.getElementById('master-proposal-kind-filter-dropdown');
    const statusFilterDropdown = document.getElementById('master-proposal-status-filter-dropdown');
    if (!heading) return;
    const root = pane();
    if (!root) {
      heading.textContent = 'ТКП';
      if (kindFilterDropdown) kindFilterDropdown.classList.add('d-none');
      if (statusFilterDropdown) statusFilterDropdown.classList.add('d-none');
      return;
    }

    const rootLabel = root.dataset.headerRootLabel || 'ТКП';
    const rootUrl = root.dataset.headerRootUrl || '';
    const currentLabel = root.dataset.headerCurrentLabel || '';
    const currentUrl = root.dataset.headerCurrentUrl || '';

    if (kindFilterDropdown) kindFilterDropdown.classList.toggle('d-none', !!currentLabel);
    if (statusFilterDropdown) statusFilterDropdown.classList.toggle('d-none', !!currentLabel);

    if (!currentLabel) {
      heading.textContent = rootLabel;
      return;
    }

    const rootHrefAttrs = rootUrl
      ? ' href="#proposals" data-bs-toggle="tab" hx-get="' + rootUrl + '" hx-target="#proposals-pane" hx-swap="outerHTML"'
      : '';
    const currentHrefAttrs = currentUrl
      ? ' href="#proposals" data-bs-toggle="tab" hx-get="' + currentUrl + '" hx-target="#proposals-pane" hx-swap="outerHTML"'
      : '';

    heading.innerHTML = ''
      + '<a class="proposal-header-link" ' + rootHrefAttrs + '>' + rootLabel + '</a>'
      + '<span class="proposal-header-separator"> / </span>'
      + '<a class="proposal-header-link" ' + currentHrefAttrs + '>' + currentLabel + '</a>';

    if (window.htmx) window.htmx.process(heading);
  }

  function getMaster(name) {
    return pane()?.querySelector('input.form-check-input[data-target-name="' + name + '"]') || null;
  }

  function isSelectableRowCheckbox(box) {
    const row = box?.closest('tr');
    return !!box && !box.disabled && !row?.classList.contains('d-none');
  }

  function getRowChecks(name) {
    return qa('tbody input.form-check-input[name="' + name + '"]', pane()).filter(isSelectableRowCheckbox);
  }

  function getChecked(name) {
    return getRowChecks(name).filter((box) => box.checked);
  }

  function updateRowHighlight(name) {
    getRowChecks(name).forEach((box) => {
      const row = box.closest('tr');
      if (row) row.classList.toggle('table-active', !!box.checked);
    });
  }

  function updateMasterState(name) {
    const master = getMaster(name);
    if (!master) return;
    const boxes = getRowChecks(name);
    if (!boxes.length) {
      master.checked = false;
      master.indeterminate = false;
      return;
    }
    const checkedCount = boxes.filter((box) => box.checked).length;
    master.checked = checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }

  function getActionsPanel(name) {
    const master = getMaster(name);
    const actionsId = master?.dataset?.actionsId || '';
    return actionsId ? pane()?.querySelector('#' + actionsId) : null;
  }

  function updateActionsVisibility(name) {
    const actions = getActionsPanel(name);
    if (!actions) return;
    const anyChecked = getChecked(name).length > 0;
    actions.classList.toggle('d-none', !anyChecked);
    actions.classList.toggle('d-flex', anyChecked);
  }

  function updateDispatchActionBtns() {
    const checked = getChecked('proposal-dispatch-select');
    const hasChecked = checked.length > 0;
    const allCheckedReadyToSend = hasChecked && checked.every((box) => {
      const row = box.closest('tr');
      return row?.dataset?.sendReady === '1';
    });
    const singleCheckedReadyToTransfer = checked.length === 1 && (() => {
      const row = checked[0]?.closest('tr');
      return row?.dataset?.transferReady === '1';
    })();
    const createBtn = pane()?.querySelector('#proposal-create-btn');
    const signBtn = pane()?.querySelector('#proposal-sign-btn');
    const sendBtn = pane()?.querySelector('#proposal-send-btn');
    const transferContractBtn = pane()?.querySelector('#proposal-transfer-contract-btn');
    if (createBtn) createBtn.disabled = !hasChecked;
    if (signBtn) signBtn.disabled = !allCheckedReadyToSend;
    if (sendBtn) sendBtn.disabled = !allCheckedReadyToSend;
    if (transferContractBtn) transferContractBtn.disabled = !singleCheckedReadyToTransfer;
  }

  function applyTransferredProposalState(proposalIds, statusValue, statusLabel, transferDate) {
    const ids = (proposalIds || []).map((value) => String(value));
    ids.forEach((proposalId) => {
      qa('tr[data-proposal-id="' + proposalId + '"]', pane()).forEach((row) => {
        row.dataset.status = statusValue || row.dataset.status || '';
        row.dataset.statusLabel = statusLabel || row.dataset.statusLabel || '';
        row.dataset.transferReady = '1';
        const statusCell = row.querySelector('.proposal-status-cell');
        if (statusCell && statusLabel) statusCell.textContent = statusLabel;
        const transferCell = row.querySelector('.proposal-transfer-date-cell');
        if (transferCell) transferCell.textContent = transferDate || '';
      });
    });
    initProposalMasterFilters();
  }

  function renderProposalFileCell(name, url, iconClass) {
    const fileName = String(name || '').trim();
    const href = String(url || '').trim();
    if (!fileName && !href) return '';
    if (href) {
      return '<a href="' + escapeHtml(href) + '" target="_blank" rel="noopener"'
        + ' class="proposal-file-name-link d-inline-flex align-items-center gap-1"'
        + ' title="Открыть файл">'
        + '<i class="bi ' + escapeHtml(iconClass) + '" style="color: var(--bs-primary, #075D94);"></i>'
        + '<span class="proposal-file-name-text">' + escapeHtml(fileName || 'Файл') + '</span>'
        + '</a>';
    }
    return '<span class="proposal-file-name-link d-inline-flex align-items-center gap-1">'
      + '<i class="bi ' + escapeHtml(iconClass) + '" style="color: var(--bs-primary, #075D94);"></i>'
      + '<span class="proposal-file-name-text">' + escapeHtml(fileName) + '</span>'
      + '</span>';
  }

  function applySentProposalState(updates, fallbackStatusValue, fallbackStatusLabel, fallbackSentDate) {
    const sourceItems = Array.isArray(updates) ? updates : [];
    const items = sourceItems.map((item) => {
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        return item;
      }
      return {
        id: item,
        status: fallbackStatusValue,
        status_label: fallbackStatusLabel,
        sent_date: fallbackSentDate,
      };
    });
    items.forEach((item) => {
      const proposalId = String(item?.id || '');
      if (!proposalId) return;
      qa('tr[data-proposal-id="' + proposalId + '"]', pane()).forEach((row) => {
        const statusValue = item?.status || fallbackStatusValue || row.dataset.status || '';
        const statusLabel = item?.status_label || fallbackStatusLabel || row.dataset.statusLabel || '';
        const sentDate = item?.sent_date || fallbackSentDate || '';
        row.dataset.status = statusValue;
        row.dataset.statusLabel = statusLabel;
        row.dataset.transferReady = sentDate ? '1' : (row.dataset.transferReady || '0');
        const statusCell = row.querySelector('.proposal-status-cell');
        if (statusCell && statusLabel) statusCell.textContent = statusLabel;
        const sentDateCell = row.querySelector('.proposal-sent-date-cell');
        if (sentDateCell) sentDateCell.textContent = sentDate;
      });
    });
    initProposalMasterFilters();
  }

  function applyCreatedDocumentsState(updates) {
    (updates || []).forEach((item) => {
      const proposalId = String(item?.id || '');
      if (!proposalId) return;
      qa('tr[data-proposal-id="' + proposalId + '"]', pane()).forEach((row) => {
        const docxCell = row.querySelector('.proposal-docx-cell');
        const pdfCell = row.querySelector('.proposal-pdf-cell');
        if (docxCell) {
          docxCell.innerHTML = renderProposalFileCell(
            item?.docx_file_name || '',
            item?.proposal_docx_file_url || '',
            'bi-file-word-fill'
          );
        }
        if (pdfCell) {
          pdfCell.innerHTML = renderProposalFileCell(
            item?.pdf_file_name || '',
            item?.proposal_pdf_file_url || '',
            'bi-file-pdf-fill'
          );
        }
        if (item?.docx_file_name) row.dataset.sendReady = '1';
      });
    });
  }

  function applySignedDocumentsState(updates) {
    (updates || []).forEach((item) => {
      const proposalId = String(item?.id || '');
      if (!proposalId) return;
      qa('tr[data-proposal-id="' + proposalId + '"]', pane()).forEach((row) => {
        const pdfCell = row.querySelector('.proposal-pdf-cell');
        if (pdfCell) {
          pdfCell.innerHTML = renderProposalFileCell(
            item?.pdf_file_name || '',
            item?.proposal_pdf_file_url || '',
            'bi-file-pdf-fill'
          );
        }
      });
    });
  }

  async function parseJsonResponse(response, fallbackMessage) {
    const rawText = await response.text();
    let data = null;
    try {
      data = rawText ? JSON.parse(rawText) : {};
    } catch (parseError) {
      if (!response.ok) {
        throw new Error(fallbackMessage);
      }
      throw new Error('Сервер вернул некорректный ответ.');
    }
    return data;
  }

  function bindProposalFilterMenuWidth(dropdown) {
    if (!dropdown) return;
    if (window.bindProjectFilterMenuWidth) {
      window.bindProjectFilterMenuWidth(dropdown);
      return;
    }
    if (dropdown.dataset.projectMenuWidthBound === '1') return;
    dropdown.dataset.projectMenuWidthBound = '1';
    const menu = dropdown.querySelector('.project-filter-menu');
    if (!menu) return;
    dropdown.addEventListener('shown.bs.dropdown', () => {
      const labels = Array.from(menu.querySelectorAll('.form-check-label'));
      const widestLabel = labels.reduce((maxWidth, item) => (
        Math.max(maxWidth, Math.ceil(item.scrollWidth))
      ), 0);
      if (!widestLabel) return;
      const controlWidth = Math.ceil(dropdown.querySelector('.dropdown-toggle')?.offsetWidth || 200);
      const checkboxWidth = Math.ceil(menu.querySelector('.form-check-input')?.offsetWidth || 18);
      const contentWidth = widestLabel + checkboxWidth + 64;
      menu.style.minWidth = Math.max(controlWidth, 200, contentWidth) + 'px';
    });
  }

  function initProposalMasterFilters() {
    const root = pane();
    if (!root) return;

    const kindDropdown = document.getElementById('master-proposal-kind-filter-dropdown');
    const kindListContainer = document.getElementById('proposal-kind-filter-list');
    const kindLabel = document.querySelector('.js-proposal-kind-filter-label');
    const statusDropdown = document.getElementById('master-proposal-status-filter-dropdown');
    const statusListContainer = document.getElementById('proposal-status-filter-list');
    const statusLabel = document.querySelector('.js-proposal-status-filter-label');
    const registryRows = root.querySelectorAll('table.proposals-table tbody tr[data-kind]');
    const dispatchRows = root.querySelectorAll('table.proposal-dispatch-table tbody tr[data-kind]');
    const rows = Array.from([...registryRows, ...dispatchRows]);

    if (!kindDropdown || !kindListContainer || !statusDropdown || !statusListContainer) return;
    bindProposalFilterMenuWidth(kindDropdown);
    bindProposalFilterMenuWidth(statusDropdown);

    const availableKinds = [];
    const seenKinds = new Set();
    rows.forEach((row) => {
      const kindValue = row.dataset.kind || '';
      const kindLabel = row.dataset.kindLabel || kindValue;
      if (!kindValue || seenKinds.has(kindValue)) return;
      seenKinds.add(kindValue);
      availableKinds.push({ value: kindValue, label: kindLabel });
    });

    const availableStatuses = [];
    const seenStatuses = new Set();
    const availableStatusLabels = new Map();
    rows.forEach((row) => {
      const statusValue = row.dataset.status || '';
      const statusText = row.dataset.statusLabel || statusValue;
      if (!statusValue) return;
      if (!availableStatusLabels.has(statusValue)) {
        availableStatusLabels.set(statusValue, statusText);
      }
    });
    PROPOSAL_STATUS_FILTER_OPTIONS.forEach((item) => {
      if (seenStatuses.has(item.value)) return;
      seenStatuses.add(item.value);
      availableStatuses.push({
        value: item.value,
        label: availableStatusLabels.get(item.value) || item.label,
      });
    });
    availableStatusLabels.forEach((label, value) => {
      if (seenStatuses.has(value)) return;
      seenStatuses.add(value);
      availableStatuses.push({ value: value, label: label });
    });

    kindListContainer.innerHTML = '';
    availableKinds.forEach((item) => {
      const div = document.createElement('div');
      div.className = 'form-check';
      const input = document.createElement('input');
      input.className = 'form-check-input js-proposal-kind-filter';
      input.type = 'checkbox';
      input.value = item.value;
      input.id = 'proposal-kind-filter-' + item.value;
      input.dataset.summaryLabel = item.label;
      input.dataset.fullLabel = item.label;
      const inputLabel = document.createElement('label');
      inputLabel.className = 'form-check-label';
      inputLabel.htmlFor = input.id;
      inputLabel.textContent = item.label;
      div.appendChild(input);
      div.appendChild(inputLabel);
      kindListContainer.appendChild(div);
    });

    statusListContainer.innerHTML = '';
    availableStatuses.forEach((item) => {
      const div = document.createElement('div');
      div.className = 'form-check';
      const input = document.createElement('input');
      input.className = 'form-check-input js-proposal-status-filter';
      input.type = 'checkbox';
      input.value = item.value;
      input.id = 'proposal-status-filter-' + item.value;
      input.dataset.summaryLabel = item.label;
      input.dataset.fullLabel = item.label;
      const inputLabel = document.createElement('label');
      inputLabel.className = 'form-check-label';
      inputLabel.htmlFor = input.id;
      inputLabel.textContent = item.label;
      div.appendChild(input);
      div.appendChild(inputLabel);
      statusListContainer.appendChild(div);
    });

    const kindChecks = kindDropdown.querySelectorAll('.js-proposal-kind-filter');
    const statusChecks = statusDropdown.querySelectorAll('.js-proposal-status-filter');

    function syncCheckboxes(checks, values) {
      const set = new Set(values);
      checks.forEach((cb) => { cb.checked = set.has(cb.value); });
    }

    function selectOnlyAll(checks, allValue) {
      checks.forEach((cb) => {
        cb.checked = cb.value === allValue;
      });
      return [allValue];
    }

    function enforceExclusiveAllSelection(checks, allValue) {
      const allCheckbox = Array.from(checks).find((cb) => cb.value === allValue);
      if (!allCheckbox || !allCheckbox.checked) return;
      selectOnlyAll(checks, allValue);
    }

    function updateLabel(labelNode, checks, values, allValue) {
      if (values.includes(allValue) || !values.length) {
        if (labelNode) labelNode.textContent = 'Все';
        return;
      }
      if (values.length === 1) {
        const input = Array.from(checks).find((cb) => cb.value === values[0]);
        if (labelNode) labelNode.textContent = input?.dataset?.summaryLabel?.trim() || '1 выбрано';
        return;
      }
      if (labelNode) labelNode.textContent = values.length + ' выбрано';
    }

    function normalizeSelection(checks, allValue) {
      let values = Array.from(checks).filter((cb) => cb.checked).map((cb) => cb.value);
      if (!values.length) values = [allValue];
      if (values.includes(allValue)) return selectOnlyAll(checks, allValue);
      syncCheckboxes(checks, values);
      return values;
    }

    function getAvailableStatusValues(kindValues) {
      const showAllKinds = kindValues.includes(PROPOSAL_KIND_FILTER_ALL) || !kindValues.length;
      const values = new Set();
      rows.forEach((row) => {
        const kind = row.dataset.kind || '';
        const status = row.dataset.status || '';
        if (!status) return;
        if (!showAllKinds && !kindValues.includes(kind)) return;
        values.add(status);
      });
      return values;
    }

    function syncStatusAvailability(kindValues, statusValues) {
      const availableStatusValues = getAvailableStatusValues(kindValues);
      statusChecks.forEach((cb) => {
        if (cb.value === PROPOSAL_STATUS_FILTER_ALL) {
          cb.disabled = false;
          return;
        }
        const isAvailable = availableStatusValues.has(cb.value);
        cb.disabled = !isAvailable;
        if (!isAvailable) cb.checked = false;
      });

      let nextStatusValues = (Array.isArray(statusValues) ? statusValues : [])
        .filter((value) => value === PROPOSAL_STATUS_FILTER_ALL || availableStatusValues.has(value));
      if (!nextStatusValues.length || nextStatusValues.includes(PROPOSAL_STATUS_FILTER_ALL)) {
        nextStatusValues = selectOnlyAll(statusChecks, PROPOSAL_STATUS_FILTER_ALL);
      } else {
        syncCheckboxes(statusChecks, nextStatusValues);
      }
      return nextStatusValues;
    }

    function applyFilters(kindValues, statusValues) {
      const normalizedStatusValues = syncStatusAvailability(kindValues, statusValues);
      window.__proposalKindFilter = kindValues.slice();
      window.__proposalStatusFilter = normalizedStatusValues.slice();
      if (window.UIPref) {
        UIPref.set(PROPOSAL_KIND_FILTER_PREF_KEY, kindValues);
        UIPref.set(PROPOSAL_STATUS_FILTER_PREF_KEY, normalizedStatusValues);
      }
      const showAllKinds = kindValues.includes(PROPOSAL_KIND_FILTER_ALL) || !kindValues.length;
      const showAllStatuses = normalizedStatusValues.includes(PROPOSAL_STATUS_FILTER_ALL) || !normalizedStatusValues.length;
      [registryRows, dispatchRows].forEach((rowsCollection) => {
        rowsCollection.forEach((row) => {
          const kind = row.dataset.kind || '';
          const status = row.dataset.status || '';
          const visible = (showAllKinds || kindValues.includes(kind)) && (showAllStatuses || normalizedStatusValues.includes(status));
          row.classList.toggle('d-none', !visible);
          row.querySelectorAll('input.form-check-input[name]').forEach((cb) => {
            cb.disabled = !visible;
            if (!visible) cb.checked = false;
          });
        });
      });
      updateLabel(kindLabel, kindChecks, kindValues, PROPOSAL_KIND_FILTER_ALL);
      updateLabel(statusLabel, statusChecks, normalizedStatusValues, PROPOSAL_STATUS_FILTER_ALL);
      syncAllSelectionStates();
    }

    kindChecks.forEach((cb) => {
      cb.onchange = (event) => {
        const value = event.target.value;
        if (value === PROPOSAL_KIND_FILTER_ALL && event.target.checked) {
          applyFilters(selectOnlyAll(kindChecks, PROPOSAL_KIND_FILTER_ALL), normalizeSelection(statusChecks, PROPOSAL_STATUS_FILTER_ALL));
          requestAnimationFrame(() => enforceExclusiveAllSelection(kindChecks, PROPOSAL_KIND_FILTER_ALL));
          return;
        }
        if (value === PROPOSAL_KIND_FILTER_ALL && !event.target.checked) {
          const first = Array.from(kindChecks).find((item) => item.value !== PROPOSAL_KIND_FILTER_ALL);
          if (first) first.checked = true;
        } else {
          const allCb = document.getElementById('proposal-kind-filter-all');
          if (allCb && allCb.checked) allCb.checked = false;
        }
        applyFilters(
          normalizeSelection(kindChecks, PROPOSAL_KIND_FILTER_ALL),
          normalizeSelection(statusChecks, PROPOSAL_STATUS_FILTER_ALL)
        );
      };
    });

    statusChecks.forEach((cb) => {
      cb.onchange = (event) => {
        const value = event.target.value;
        if (value === PROPOSAL_STATUS_FILTER_ALL && event.target.checked) {
          applyFilters(normalizeSelection(kindChecks, PROPOSAL_KIND_FILTER_ALL), selectOnlyAll(statusChecks, PROPOSAL_STATUS_FILTER_ALL));
          requestAnimationFrame(() => enforceExclusiveAllSelection(statusChecks, PROPOSAL_STATUS_FILTER_ALL));
          return;
        }
        if (value === PROPOSAL_STATUS_FILTER_ALL && !event.target.checked) {
          const first = Array.from(statusChecks).find((item) => item.value !== PROPOSAL_STATUS_FILTER_ALL);
          if (first) first.checked = true;
        } else {
          const allCb = document.getElementById('proposal-status-filter-all');
          if (allCb && allCb.checked) allCb.checked = false;
        }
        applyFilters(
          normalizeSelection(kindChecks, PROPOSAL_KIND_FILTER_ALL),
          normalizeSelection(statusChecks, PROPOSAL_STATUS_FILTER_ALL)
        );
      };
    });

    const availableKindValues = new Set(Array.from(kindChecks).map((cb) => cb.value));
    const savedKindValues = window.UIPref ? UIPref.get(PROPOSAL_KIND_FILTER_PREF_KEY, null) : null;
    const preferredKindValues = Array.isArray(savedKindValues) && savedKindValues.length
      ? savedKindValues
      : window.__proposalKindFilter;
    const initialKindValues = Array.isArray(preferredKindValues) && preferredKindValues.length
      ? preferredKindValues.filter((value) => availableKindValues.has(value))
      : [PROPOSAL_KIND_FILTER_ALL];

    const availableStatusValues = new Set(Array.from(statusChecks).map((cb) => cb.value));
    const savedStatusValues = window.UIPref ? UIPref.get(PROPOSAL_STATUS_FILTER_PREF_KEY, null) : null;
    const preferredStatusValues = Array.isArray(savedStatusValues) && savedStatusValues.length
      ? savedStatusValues
      : window.__proposalStatusFilter;
    const initialStatusValues = Array.isArray(preferredStatusValues) && preferredStatusValues.length
      ? preferredStatusValues.filter((value) => availableStatusValues.has(value))
      : [PROPOSAL_STATUS_FILTER_ALL];

    syncCheckboxes(
      kindChecks,
      initialKindValues.includes(PROPOSAL_KIND_FILTER_ALL) || !initialKindValues.length
        ? selectOnlyAll(kindChecks, PROPOSAL_KIND_FILTER_ALL)
        : initialKindValues
    );
    syncCheckboxes(
      statusChecks,
      initialStatusValues.includes(PROPOSAL_STATUS_FILTER_ALL) || !initialStatusValues.length
        ? selectOnlyAll(statusChecks, PROPOSAL_STATUS_FILTER_ALL)
        : initialStatusValues
    );
    applyFilters(
      normalizeSelection(kindChecks, PROPOSAL_KIND_FILTER_ALL),
      normalizeSelection(statusChecks, PROPOSAL_STATUS_FILTER_ALL)
    );
  }

  function getProposalChannels() {
    return qa('.js-proposal-channel', pane());
  }

  function saveProposalSendSettings() {
    if (!window.UIPref) return;
    UIPref.set(PROPOSAL_SEND_PREF_KEY, {
      deliveryChannels: getProposalChannels()
        .filter((cb) => cb.checked && !cb.disabled)
        .map((cb) => cb.value),
    });
  }

  function restoreProposalSendSettings() {
    const channels = getProposalChannels();
    if (!channels.length) return;
    const saved = window.UIPref ? UIPref.get(PROPOSAL_SEND_PREF_KEY, null) : null;
    const savedValues = Array.isArray(saved?.deliveryChannels) ? new Set(saved.deliveryChannels) : null;

    if (savedValues) {
      channels.forEach((cb) => {
        cb.checked = !cb.disabled && savedValues.has(cb.value);
      });
    }

    if (!channels.some((cb) => cb.checked) ) {
      const firstEnabled = channels.find((cb) => !cb.disabled);
      if (firstEnabled) firstEnabled.checked = true;
    }
  }

  function varsCollapse() {
    return pane()?.querySelector('#proposal-dispatch-vars') || null;
  }

  function varsToggle() {
    return pane()?.querySelector('a[href="#proposal-dispatch-vars"]') || null;
  }

  function clearProposalPendingScrollRestore() {
    window.__proposalPendingScrollRestore = null;
    document.documentElement.classList.remove('proposal-progress-cursor');
  }

  function isProposalVariablesSectionElement(element) {
    return element instanceof Element && (element.id === 'proposal-variables-section' || !!element.closest('#proposal-variables-section'));
  }

  function restoreSavedSelection(name) {
    const savedIds = new Set((window.__tableSel && window.__tableSel[name]) || []);
    getRowChecks(name).forEach((box) => {
      box.checked = savedIds.has(String(box.value));
    });
    try {
      delete window.__tableSel[name];
    } catch (error) {
      window.__tableSel[name] = [];
    }
    window.__tableSelLast = null;
  }

  function restoreVariableCollapseState() {
    const collapseEl = varsCollapse();
    if (!collapseEl) return;
    const expanded = !!window.__proposalVarsExpanded;
    const toggle = varsToggle();
    if (toggle) {
      toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      toggle.classList.toggle('collapsed', !expanded);
    }
    if (window.bootstrap?.Collapse) {
      const instance = window.bootstrap.Collapse.getInstance(collapseEl);
      if (instance) instance._isTransitioning = false;
    }
    collapseEl.classList.remove('collapsing');
    collapseEl.classList.add('collapse');
    collapseEl.classList.toggle('show', expanded);
    collapseEl.style.height = '';
  }

  function syncSelectionState(name) {
    updateMasterState(name);
    updateRowHighlight(name);
    updateActionsVisibility(name);
    if (name === 'proposal-dispatch-select') updateDispatchActionBtns();
  }

  function syncAllSelectionStates() {
    SELECT_NAMES.forEach(syncSelectionState);
  }

  function attachGroupSelectDisplay(root) {
    if (!root) return;
    const select = root.querySelector('#proposal-group-select');
    const display = root.querySelector('#proposal-group-display');
    if (!select || !display || select.dataset.displayBound === '1') return;
    select.dataset.displayBound = '1';

    const sync = function () {
      const selected = select.options[select.selectedIndex];
      const label = selected && selected.value ? selected.textContent.trim() : '';
      display.textContent = label ? label.split(/\s+/, 1)[0] : '';
    };

    select.addEventListener('change', sync);
    sync();
  }

  function attachProposalNumberDisplay(root) {
    if (!root) return;
    const input = root.querySelector('#proposal-number-input');
    const display = root.querySelector('#proposal-number-display');
    if (!input || !display || input.dataset.numberBound === '1') return;
    input.dataset.numberBound = '1';

    const sync = function () {
      const raw = String(input.value || '').replace(/\D+/g, '').slice(0, 4);
      display.textContent = raw ? raw.padStart(4, '0') : '';
    };

    input.addEventListener('input', sync);
    input.addEventListener('change', sync);
    sync();
  }

  function attachReportLanguagesDropdown(root) {
    if (!root) return;
    const hiddenInput = root.querySelector('#proposal-report-languages');
    const dropdown = root.querySelector('#proposal-report-languages-dropdown');
    if (!hiddenInput || !dropdown || dropdown.dataset.bound === '1') return;
    dropdown.dataset.bound = '1';
    const label = dropdown.querySelector('.js-proposal-report-languages-label');
    const checkboxes = Array.from(dropdown.querySelectorAll('.js-proposal-report-language'));

    function parseLanguages(value) {
      const aliasMap = {
        ru: 'русский',
        russian: 'русский',
        русский: 'русский',
        en: 'английский',
        english: 'английский',
        английский: 'английский',
        kz: 'казахский',
        kk: 'казахский',
        kazakh: 'казахский',
        казахский: 'казахский',
        zh: 'китайский',
        cn: 'китайский',
        chinese: 'китайский',
        китайский: 'китайский',
      };
      const order = ['русский', 'английский', 'казахский', 'китайский'];
      const selectedSet = new Set();
      String(value || '').replace(/;/g, ',').split(',').forEach(function (item) {
        const normalized = aliasMap[String(item || '').trim().toLowerCase()];
        if (normalized) selectedSet.add(normalized);
      });
      return order.filter(function (item) { return selectedSet.has(item); });
    }

    function updateLabel(selected) {
      if (!label) return;
      if (!selected.length) {
        label.textContent = 'русский';
      } else {
        label.textContent = selected.join(', ');
      }
    }

    function syncFromHidden() {
      let selected = parseLanguages(hiddenInput.value);
      if (!selected.length) {
        selected = ['русский'];
        hiddenInput.value = selected.join(', ');
      }
      const selectedSet = new Set(selected);
      checkboxes.forEach(function (checkbox) {
        checkbox.checked = selectedSet.has(checkbox.value);
      });
      updateLabel(selected);
    }

    function syncHidden() {
      const selected = checkboxes
        .filter(function (checkbox) { return checkbox.checked; })
        .map(function (checkbox) { return checkbox.value; });
      hiddenInput.value = selected.join(', ');
      updateLabel(selected);
    }

    checkboxes.forEach(function (checkbox) {
      checkbox.addEventListener('change', syncHidden);
    });
    syncFromHidden();
  }

  function attachCountryIdentifierSync(root) {
    if (!root) return;
    const form = root.closest('form[data-proposal-form], form[data-proposal-dispatch-form]') || root;
    const url = form.dataset.countryIdentifierUrl;
    if (!url) return;

    function bindCountryIdentifierSync(countrySelector, identifierSelector, boundKey, onSync) {
      const countrySelect = form.querySelector(countrySelector);
      const identifierField = form.querySelector(identifierSelector);
      if (!countrySelect || !identifierField || countrySelect.dataset[boundKey] === '1') return;
      countrySelect.dataset[boundKey] = '1';

      countrySelect.addEventListener('change', () => {
        const countryId = countrySelect.value;
        if (!countryId) {
          identifierField.value = '';
          if (typeof onSync === 'function') onSync();
          return;
        }
        fetch(url + '?country_id=' + encodeURIComponent(countryId))
          .then((response) => response.json())
          .then((data) => {
            identifierField.value = data.identifier || '';
            if (typeof onSync === 'function') onSync();
          });
      });
    }

    bindCountryIdentifierSync('#proposal-country-select', '#proposal-identifier-field', 'identBoundCustomer', function () {
      form.dispatchEvent(new CustomEvent('proposal-customer-changed'));
    });
    bindCountryIdentifierSync('#proposal-asset-owner-country-select', '#proposal-asset-owner-identifier-field', 'identBoundAssetOwner');
    bindCountryIdentifierSync(
      '#proposal-dispatch-recipient-country-select',
      '#proposal-dispatch-recipient-identifier-field',
      'identBoundDispatchRecipient'
    );
  }

  function resetProposalRegionSelect(regionSelect) {
    if (!(regionSelect instanceof HTMLSelectElement)) return;
    regionSelect.innerHTML = '<option value="">---------</option>';
  }

  function ensureProposalRegionOption(regionSelect, regionName) {
    if (!(regionSelect instanceof HTMLSelectElement)) return;
    const value = String(regionName || '').trim();
    if (!value) return;
    for (let i = 0; i < regionSelect.options.length; i += 1) {
      if (regionSelect.options[i].value === value) return;
    }
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    regionSelect.appendChild(option);
  }

  function loadProposalRegionOptions(regionUrl, countryId, regionSelect, options) {
    if (!(regionSelect instanceof HTMLSelectElement)) return Promise.resolve();
    const settings = options || {};
    const nextRequestSeq = String((Number(regionSelect.dataset.regionRequestSeq || '0') || 0) + 1);
    regionSelect.dataset.regionRequestSeq = nextRequestSeq;
    const hasExplicitSelectedRegion = (
      Object.prototype.hasOwnProperty.call(settings, 'selectedRegion')
      && settings.selectedRegion !== undefined
    );
    const hasPendingSelectedRegion = regionSelect.dataset.pendingSelectedRegionSet === '1';
    const pendingRegion = String(regionSelect.dataset.pendingSelectedRegion || '').trim();
    const selectedRegion = String(
      hasExplicitSelectedRegion && settings.selectedRegion !== null
        ? settings.selectedRegion
        : pendingRegion
    ).trim();
    const preserveCurrent = !!settings.preserveCurrent;
    const currentRegion = preserveCurrent ? String(regionSelect.value || '').trim() : '';
    const nextRegion = hasExplicitSelectedRegion
      ? selectedRegion
      : (hasPendingSelectedRegion ? pendingRegion : currentRegion);
    const dateValue = String(settings.dateValue || '').trim();

    if (!countryId) {
      resetProposalRegionSelect(regionSelect);
      if (nextRegion) {
        ensureProposalRegionOption(regionSelect, nextRegion);
        regionSelect.value = nextRegion;
      }
      return Promise.resolve();
    }

    let requestUrl = regionUrl + '?country_id=' + encodeURIComponent(countryId);
    if (dateValue) requestUrl += '&date=' + encodeURIComponent(dateValue);

    return fetch(requestUrl)
      .then((response) => response.json())
      .then((data) => {
        if (regionSelect.dataset.regionRequestSeq !== nextRequestSeq) return;
        const regions = Array.isArray(data?.regions) ? data.regions.slice() : [];
        resetProposalRegionSelect(regionSelect);
        if (nextRegion && !regions.includes(nextRegion)) {
          regions.push(nextRegion);
        }
        regions.forEach((regionName) => {
          const option = document.createElement('option');
          option.value = regionName;
          option.textContent = regionName;
          regionSelect.appendChild(option);
        });
        regionSelect.value = nextRegion;
        if (hasPendingSelectedRegion) {
          delete regionSelect.dataset.pendingSelectedRegion;
          delete regionSelect.dataset.pendingSelectedRegionSet;
        }
      })
      .catch(() => {
        if (regionSelect.dataset.regionRequestSeq !== nextRequestSeq) return;
        resetProposalRegionSelect(regionSelect);
        if (nextRegion) {
          ensureProposalRegionOption(regionSelect, nextRegion);
          regionSelect.value = nextRegion;
        }
        if (hasPendingSelectedRegion) {
          delete regionSelect.dataset.pendingSelectedRegion;
          delete regionSelect.dataset.pendingSelectedRegionSet;
        }
      });
  }

  function attachCountryRegionSync(root) {
    if (!root) return;
    const form = root.closest('form[data-proposal-form]') || root;
    const regionUrl = form.dataset.countryRegionUrl;
    if (!regionUrl) return;

    function bindCountryRegionSync(countrySelector, regionSelector, dateSelector, boundKey, onSync) {
      const countrySelect = form.querySelector(countrySelector);
      const regionSelect = form.querySelector(regionSelector);
      const dateInput = form.querySelector(dateSelector);
      if (!countrySelect || !regionSelect || countrySelect.dataset[boundKey] === '1') return;
      countrySelect.dataset[boundKey] = '1';

      function syncRegions(preserveCurrent, selectedRegion) {
        const regionOptions = {
          preserveCurrent: preserveCurrent,
          dateValue: dateInput?.value || '',
        };
        if (selectedRegion !== undefined) {
          regionOptions.selectedRegion = selectedRegion;
        }
        return loadProposalRegionOptions(regionUrl, countrySelect.value, regionSelect, regionOptions).then(() => {
          if (typeof onSync === 'function') onSync();
        });
      }

      countrySelect.addEventListener('change', () => {
        syncRegions(false);
      });
      dateInput?.addEventListener('change', () => {
        syncRegions(true);
      });

      if (!countrySelect.value) {
        resetProposalRegionSelect(regionSelect);
      } else {
        syncRegions(true, regionSelect.value || '');
      }
    }

    bindCountryRegionSync(
      '#proposal-country-select',
      '#proposal-region-select',
      'input[name="registration_date"]',
      'regionBoundCustomer',
      function () {
        form.dispatchEvent(new CustomEvent('proposal-customer-changed'));
      }
    );
    bindCountryRegionSync(
      '#proposal-asset-owner-country-select',
      '#proposal-asset-owner-region-select',
      'input[name="asset_owner_registration_date"]',
      'regionBoundAssetOwner',
      function () {
        form.dispatchEvent(new CustomEvent('proposal-asset-owner-changed', { detail: { reason: 'owner-change' } }));
      }
    );
  }

  function attachProposalRegistrationRegionAutofill(root) {
    if (!root) return;
    const form = root.closest('form[data-proposal-form]') || root;
    const autofillUrl = form.dataset.regionAutofillUrl;
    if (!autofillUrl) return;

    function bindRegionAutofill(options) {
      const countrySelect = form.querySelector(options.countrySelector);
      const identifierInput = form.querySelector(options.identifierSelector);
      const registrationNumberInput = form.querySelector(options.registrationNumberSelector);
      const regionSelect = form.querySelector(options.regionSelector);
      if (!countrySelect || !identifierInput || !registrationNumberInput || !regionSelect || registrationNumberInput.dataset[options.boundKey] === '1') {
        return;
      }
      registrationNumberInput.dataset[options.boundKey] = '1';
      let requestSeq = 0;
      let debounce = null;

      function applyRegion(regionName) {
        const value = String(regionName || '').trim();
        regionSelect.dataset.pendingSelectedRegion = value;
        regionSelect.dataset.pendingSelectedRegionSet = '1';
        loadProposalRegionOptions(form.dataset.countryRegionUrl || '', countrySelect.value || '', regionSelect, {
          preserveCurrent: false,
          selectedRegion: value,
        }).then(() => {
          if (typeof options.onApplied === 'function') options.onApplied(value);
        });
      }

      function scheduleAutofill() {
        clearTimeout(debounce);
        debounce = setTimeout(() => {
          const seq = requestSeq + 1;
          requestSeq = seq;
          const countryId = String(countrySelect.value || '').trim();
          const identifier = String(identifierInput.value || '').trim();
          const registrationNumber = String(registrationNumberInput.value || '').trim();

          if (!countryId) {
            applyRegion('');
            return;
          }

          const requestUrl = autofillUrl
            + '?country_id=' + encodeURIComponent(countryId)
            + '&identifier=' + encodeURIComponent(identifier)
            + '&registration_number=' + encodeURIComponent(registrationNumber);

          fetch(requestUrl)
            .then((response) => response.json())
            .then((data) => {
              if (seq !== requestSeq) return;
              applyRegion(data?.region || '');
            })
            .catch(() => {
              if (seq !== requestSeq) return;
              applyRegion('');
            });
        }, 150);
      }

      registrationNumberInput.addEventListener('input', scheduleAutofill);
      registrationNumberInput.addEventListener('change', scheduleAutofill);
      countrySelect.addEventListener('change', scheduleAutofill);
    }

    bindRegionAutofill({
      countrySelector: '#proposal-country-select',
      identifierSelector: '#proposal-identifier-field',
      registrationNumberSelector: 'input[name="registration_number"]',
      regionSelector: '#proposal-region-select',
      boundKey: 'regionAutofillBoundCustomer',
      onApplied: function () {
        form.dispatchEvent(new CustomEvent('proposal-customer-changed'));
      },
    });
    bindRegionAutofill({
      countrySelector: '#proposal-asset-owner-country-select',
      identifierSelector: '#proposal-asset-owner-identifier-field',
      registrationNumberSelector: 'input[name="asset_owner_registration_number"]',
      regionSelector: '#proposal-asset-owner-region-select',
      boundKey: 'regionAutofillBoundAssetOwner',
      onApplied: function () {
        form.dispatchEvent(new CustomEvent('proposal-asset-owner-changed', { detail: { reason: 'owner-change' } }));
      },
    });
  }

  function replaceQuotes(element) {
    const value = element.value;
    if (value.indexOf('"') === -1) return;
    const pos = element.selectionStart;
    let out = '';
    for (let i = 0; i < value.length; i += 1) {
      if (value[i] === '"') {
        const prev = out.length ? out[out.length - 1] : '';
        out += (!prev || /[\s(\[{\u00AB]/.test(prev)) ? '\u00AB' : '\u00BB';
      } else {
        out += value[i];
      }
    }
    element.value = out;
    element.setSelectionRange(pos, pos);
  }

  function attachGuillemets(root) {
    if (!root) return;
    ['customer', 'asset_owner', 'recipient'].forEach(function (fieldName) {
      const input = root.querySelector('input[name="' + fieldName + '"]');
      if (!input || input.dataset.guillBound === '1') return;
      input.dataset.guillBound = '1';
      input.addEventListener('input', function () {
        replaceQuotes(input);
      });
    });
  }

  function attachLerAutocomplete(root) {
    if (!root) return;
    const form = root.closest('form[data-proposal-form], form[data-proposal-dispatch-form]') || root;
    const searchUrl = form.dataset.lerSearchUrl;
    const regionUrl = form.dataset.countryRegionUrl || '';
    if (!searchUrl) return;

    function bindLerAutocomplete(options) {
      const input = form.querySelector(options.inputSelector);
      const list = form.querySelector(options.listSelector);
      const selectedIdentifierInput = form.querySelector(options.selectedIdentifierSelector);
      const selectedFlagInput = form.querySelector(options.selectedFlagSelector);
      if (!input || !list || input.dataset[options.boundKey] === '1') return;
      input.dataset[options.boundKey] = '1';

      function queryOptional(selector) {
        if (!selector) return null;
        return form.querySelector(selector);
      }

      let debounce = null;
      let results = [];
      let picking = false;

      function clearSelection() {
        if (selectedIdentifierInput) selectedIdentifierInput.value = '';
        if (selectedFlagInput) selectedFlagInput.value = '0';
      }

      function highlight(text, query) {
        if (!query) return text;
        const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return text.replace(new RegExp('(' + escaped + ')', 'gi'), '<mark>$1</mark>');
      }

      function render(data, query, totalCount) {
        results = data;
        if (!data.length) {
          list.classList.remove('show');
          return;
        }
        const visible = data.slice(0, 3);
        let html = visible.map(function (item, index) {
          const main = highlight(item.short_name || '', query);
          const parts = [item.full_name, item.identifier, item.registration_number].filter(Boolean);
          const sub = parts.length ? highlight(parts.join(' · '), query) : '';
          return '<div class="ler-ac-item" data-idx="' + index + '">'
            + '<div class="ler-ac-main">' + main + '</div>'
            + (sub ? '<div class="ler-ac-sub">' + sub + '</div>' : '')
            + '</div>';
        }).join('');
        const remaining = totalCount - 3;
        if (remaining > 0) {
          html += '<div class="ler-ac-item ler-ac-more">Найдено ещё ' + remaining + ' юрлиц</div>';
        }
        list.innerHTML = html;
        list.classList.add('show');
      }

      function pick(item) {
        const countrySelect = queryOptional(options.countrySelector);
        const regionSelect = queryOptional(options.regionSelector);
        const identifierField = queryOptional(options.identifierSelector);
        const registrationNumberField = queryOptional(options.registrationNumberSelector);
        const registrationDateField = queryOptional(options.registrationDateSelector);

        input.value = item.short_name || '';
        if (countrySelect && item.country_id) countrySelect.value = item.country_id;
        if (regionSelect) {
          regionSelect.dataset.pendingSelectedRegion = item.region || '';
          regionSelect.dataset.pendingSelectedRegionSet = '1';
        }
        if (registrationDateField) {
          setDateFieldValue(registrationDateField, item.registration_date || '');
        }
        if (regionSelect) {
          const countryId = item.country_id || countrySelect?.value || '';
          loadProposalRegionOptions(regionUrl, countryId, regionSelect, {
            preserveCurrent: false,
            selectedRegion: item.region || '',
            dateValue: item.registration_date || registrationDateField?.value || '',
          });
        }
        if (identifierField) identifierField.value = item.identifier || '';
        if (registrationNumberField) registrationNumberField.value = item.registration_number || '';
        if (registrationDateField) {
          registrationDateField.dispatchEvent(new Event('input', { bubbles: true }));
          registrationDateField.dispatchEvent(new Event('change', { bubbles: true }));
        }
        if (selectedIdentifierInput) selectedIdentifierInput.value = item.identifier_record_id || '';
        if (selectedFlagInput) selectedFlagInput.value = '1';

        if (options.changeEventName === 'proposal-customer-changed') {
          const matchesCheckbox = form.querySelector('[name="asset_owner_matches_customer"]');
          const ownerInput = form.querySelector('input[name="asset_owner"]');
          const ownerCountry = form.querySelector('#proposal-asset-owner-country-select');
          const ownerRegion = form.querySelector('#proposal-asset-owner-region-select');
          const ownerIdentifier = form.querySelector('#proposal-asset-owner-identifier-field');
          const ownerRegistrationNumber = form.querySelector('input[name="asset_owner_registration_number"]');
          const ownerRegistrationDate = form.querySelector('input[name="asset_owner_registration_date"]');
          const ownerSelectedIdentifier = form.querySelector('#proposal-asset-owner-autocomplete-identifier-record-id');
          const ownerSelectedFlag = form.querySelector('#proposal-asset-owner-autocomplete-selected');
          if (
            matchesCheckbox?.checked
            && ownerInput
            && ownerCountry
            && ownerRegion
            && ownerIdentifier
            && ownerRegistrationNumber
            && ownerRegistrationDate
          ) {
            ownerInput.value = item.short_name || '';
            ownerCountry.value = item.country_id || '';
            ownerRegion.dataset.pendingSelectedRegion = item.region || '';
            ownerRegion.dataset.pendingSelectedRegionSet = '1';
            setDateFieldValue(ownerRegistrationDate, item.registration_date || '');
            loadProposalRegionOptions(regionUrl, item.country_id || '', ownerRegion, {
              preserveCurrent: false,
              selectedRegion: item.region || '',
              dateValue: item.registration_date || '',
            });
            ownerIdentifier.value = item.identifier || '';
            ownerRegistrationNumber.value = item.registration_number || '';
            if (ownerSelectedIdentifier) ownerSelectedIdentifier.value = item.identifier_record_id || '';
            if (ownerSelectedFlag) ownerSelectedFlag.value = '1';
          }
        }

        list.classList.remove('show');
        if (options.changeEventName) {
          form.dispatchEvent(new CustomEvent(options.changeEventName, { detail: { reason: 'autocomplete-pick' } }));
          setTimeout(function () {
            form.dispatchEvent(new CustomEvent(options.changeEventName, { detail: { reason: 'autocomplete-pick' } }));
          }, 0);
        }
      }

      input.addEventListener('input', function () {
        const query = input.value.trim();
        clearSelection();
        clearTimeout(debounce);
        if (query.length < 1) {
          list.classList.remove('show');
          if (options.changeEventName) {
            form.dispatchEvent(new CustomEvent(options.changeEventName, { detail: { reason: 'autocomplete-clear' } }));
          }
          return;
        }
        debounce = setTimeout(function () {
          fetch(searchUrl + '?q=' + encodeURIComponent(query))
            .then((response) => response.json())
            .then((data) => render(data.results || [], query, data.total_count || 0))
            .catch(() => list.classList.remove('show'));
        }, 200);
      });

      list.addEventListener('mousedown', function (event) {
        event.preventDefault();
        picking = true;
        const item = event.target.closest('.ler-ac-item');
        if (!item) return;
        const idx = parseInt(item.dataset.idx, 10);
        if (results[idx]) pick(results[idx]);
      });

      list.addEventListener('click', function (event) {
        const item = event.target.closest('.ler-ac-item');
        if (!item) return;
        const idx = parseInt(item.dataset.idx, 10);
        if (results[idx]) pick(results[idx]);
        picking = false;
      });

      input.addEventListener('blur', function () {
        if (picking) {
          picking = false;
          return;
        }
        setTimeout(function () {
          list.classList.remove('show');
        }, 200);
      });

      input.addEventListener('focus', function () {
        if (results.length && input.value.trim().length >= 1) list.classList.add('show');
      });

      queryOptional(options.countrySelector)?.addEventListener('change', clearSelection);
      queryOptional(options.registrationNumberSelector)?.addEventListener('input', clearSelection);
      queryOptional(options.registrationNumberSelector)?.addEventListener('change', clearSelection);
      queryOptional(options.registrationDateSelector)?.addEventListener('input', clearSelection);
      queryOptional(options.registrationDateSelector)?.addEventListener('change', clearSelection);
    }

    bindLerAutocomplete({
      inputSelector: 'input[name="customer"]',
      listSelector: '#proposal-ler-ac-list',
      boundKey: 'lerBoundCustomer',
      countrySelector: '#proposal-country-select',
      regionSelector: '#proposal-region-select',
      identifierSelector: '#proposal-identifier-field',
      registrationNumberSelector: 'input[name="registration_number"]',
      registrationDateSelector: 'input[name="registration_date"]',
      selectedIdentifierSelector: '#proposal-customer-autocomplete-identifier-record-id',
      selectedFlagSelector: '#proposal-customer-autocomplete-selected',
      changeEventName: 'proposal-customer-changed',
    });
    bindLerAutocomplete({
      inputSelector: 'input[name="asset_owner"]',
      listSelector: '#proposal-asset-owner-ler-ac-list',
      boundKey: 'lerBoundAssetOwner',
      countrySelector: '#proposal-asset-owner-country-select',
      regionSelector: '#proposal-asset-owner-region-select',
      identifierSelector: '#proposal-asset-owner-identifier-field',
      registrationNumberSelector: 'input[name="asset_owner_registration_number"]',
      registrationDateSelector: 'input[name="asset_owner_registration_date"]',
      selectedIdentifierSelector: '#proposal-asset-owner-autocomplete-identifier-record-id',
      selectedFlagSelector: '#proposal-asset-owner-autocomplete-selected',
      changeEventName: 'proposal-asset-owner-changed',
    });
    bindLerAutocomplete({
      inputSelector: 'input[name="recipient"]',
      listSelector: '#proposal-dispatch-ler-ac-list',
      boundKey: 'lerBoundDispatchRecipient',
      countrySelector: '#proposal-dispatch-recipient-country-select',
      regionSelector: null,
      identifierSelector: '#proposal-dispatch-recipient-identifier-field',
      registrationNumberSelector: 'input[name="recipient_registration_number"]',
      registrationDateSelector: 'input[name="recipient_registration_date"]',
      selectedIdentifierSelector: '#proposal-dispatch-recipient-autocomplete-identifier-record-id',
      selectedFlagSelector: '#proposal-dispatch-recipient-autocomplete-selected',
      changeEventName: null,
    });
  }

  function attachDispatchPersonAutocomplete(root) {
    if (!root) return;
    const form = root.closest('form[data-proposal-dispatch-form]') || root;
    const searchUrl = form.dataset.prsSearchUrl;
    const input = form.querySelector('input[name="contact_last_name"]');
    const firstNameInput = form.querySelector('input[name="contact_first_name"]');
    const middleNameInput = form.querySelector('input[name="contact_middle_name"]');
    const list = form.querySelector('#proposal-dispatch-prs-ac-list');
    if (!searchUrl || !input || !firstNameInput || !middleNameInput || !list || input.dataset.prsAutocompleteBound === '1') return;
    input.dataset.prsAutocompleteBound = '1';

    let debounce = null;
    let results = [];
    let picking = false;

    function escapeHtml(value) {
      return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function highlight(text, query) {
      const safeText = escapeHtml(text);
      if (!query) return safeText;
      const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      return safeText.replace(new RegExp('(' + escaped + ')', 'gi'), '<mark>$1</mark>');
    }

    function render(query) {
      if (!results.length) {
        list.classList.remove('show');
        return;
      }
      list.innerHTML = results.map(function (item, index) {
        const fullName = [item.last_name, item.first_name, item.middle_name].filter(Boolean).join(' ').trim();
        return '<div class="ler-ac-item" data-idx="' + index + '">'
          + '<div class="ler-ac-main">' + highlight(fullName, query) + '</div>'
          + '</div>';
      }).join('');
      list.classList.add('show');
    }

    function pick(item) {
      input.value = item.last_name || '';
      firstNameInput.value = item.first_name || '';
      middleNameInput.value = item.middle_name || '';
      list.classList.remove('show');
    }

    input.addEventListener('input', function () {
      const query = input.value.trim();
      clearTimeout(debounce);
      if (query.length < 1) {
        results = [];
        list.classList.remove('show');
        return;
      }
      debounce = setTimeout(function () {
        fetch(searchUrl + '?q=' + encodeURIComponent(query))
          .then(function (response) { return response.json(); })
          .then(function (data) {
            results = data.results || [];
            render(query);
          })
          .catch(function () {
            results = [];
            list.classList.remove('show');
          });
      }, 200);
    });

    list.addEventListener('mousedown', function (event) {
      event.preventDefault();
      picking = true;
      const item = event.target.closest('.ler-ac-item');
      if (!item) return;
      const idx = parseInt(item.dataset.idx, 10);
      if (results[idx]) pick(results[idx]);
    });

    list.addEventListener('click', function (event) {
      const item = event.target.closest('.ler-ac-item');
      if (!item) return;
      const idx = parseInt(item.dataset.idx, 10);
      if (results[idx]) pick(results[idx]);
      picking = false;
    });

    input.addEventListener('blur', function () {
      if (picking) {
        picking = false;
        return;
      }
      setTimeout(function () {
        list.classList.remove('show');
      }, 200);
    });

    input.addEventListener('focus', function () {
      if (results.length && input.value.trim().length >= 1) list.classList.add('show');
    });
  }

  function fmtMoney(value) {
    var normalized = String(value || '').replace(/[^\d.,-]/g, '').replace(',', '.');
    var number = parseFloat(normalized);
    if (isNaN(number)) return '';
    var parts = number.toFixed(2).split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
    return parts.join(',');
  }

  function rawMoney(value) {
    return String(value || '').replace(/\s/g, '').replace(/\u00a0/g, '').replace(',', '.');
  }

  function formatMoneyWithPrecision(value, precision) {
    var normalized = rawMoney(value);
    var number = parseFloat(normalized);
    if (isNaN(number)) return '';
    var digits = Number.isInteger(precision) && precision >= 0 ? precision : 2;
    var parts = number.toFixed(digits).split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
    return parts.join(',');
  }

  function formatProposalExchangeRateDisplay(value) {
    return formatMoneyWithPrecision(value, 4);
  }

  function attachMoneyInputs(root) {
    if (!root) return;
    root.querySelectorAll('.js-money-input').forEach(function (input) {
      if (input.dataset.moneyBound === '1') return;
      input.dataset.moneyBound = '1';
      var precision = parseInt(input.dataset.moneyPrecision || '2', 10);
      if (input.value) input.value = formatMoneyWithPrecision(input.value, precision);
      input.addEventListener('blur', function () {
        if (input.value) input.value = formatMoneyWithPrecision(input.value, precision);
      });
    });
  }

  function initProposalDateInput(input) {
    if (!input || input.dataset.hasPicker === '1') return;
    input.classList.add('js-date');
    input.autocomplete = 'off';
    if (window.flatpickr) {
      window.flatpickr(input, {
        dateFormat: 'd.m.Y',
        allowInput: true,
        disableMobile: false,
      });
      input.dataset.hasPicker = '1';
      return;
    }
    if (window.$ && $.fn && $.fn.datepicker) {
      $(input).datepicker({
        format: 'dd.mm.yyyy',
        autoclose: true,
        todayHighlight: true,
        language: 'ru',
      });
      input.dataset.hasPicker = '1';
      return;
    }

    const raw = (input.value || '').trim();
    if (raw) {
      const dotParts = raw.split('.');
      if (dotParts.length === 3) {
        const dd = dotParts[0];
        const mm = dotParts[1];
        const yyyy = dotParts[2];
        input.value = yyyy + '-' + mm.padStart(2, '0') + '-' + dd.padStart(2, '0');
      }
    }
    input.setAttribute('type', 'date');
    input.dataset.hasPicker = '1';
  }

  function normalizeDisplayDate(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (isoMatch) {
      return isoMatch[3] + '.' + isoMatch[2] + '.' + isoMatch[1];
    }
    return raw;
  }

  function setDateFieldValue(input, value) {
    const raw = String(value || '').trim();
    if (!input) return;
    if (!raw) {
      input.value = '';
      if (input._flatpickr) input._flatpickr.clear();
      if (window.$ && $.fn && $.fn.datepicker) $(input).datepicker('update', '');
      return;
    }

    const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
    const isoValue = isoMatch ? (isoMatch[1] + '-' + isoMatch[2] + '-' + isoMatch[3]) : raw;
    const displayValue = normalizeDisplayDate(raw);

    if (input._flatpickr) {
      input._flatpickr.setDate(isoValue, true, 'Y-m-d');
      return;
    }
    if (window.$ && $.fn && $.fn.datepicker && input.dataset.hasPicker === '1') {
      $(input).datepicker('update', displayValue);
      return;
    }
    if (input.type === 'date') {
      input.value = isoValue;
      return;
    }
    input.value = displayValue;
  }

  function createProposalTableCell(className) {
    const td = document.createElement('td');
    if (className) td.className = className;
    return td;
  }

  function createProposalEllipsisLabel(text, className) {
    const span = document.createElement('span');
    span.className = className || 'proposal-commercial-row-label';
    span.textContent = text || '';
    return span;
  }

  function bindProposalEntityAutocomplete(input, list, row, updatePayload, searchUrl, selectors, getRowIndex) {
    let debounce = null;
    let results = [];
    let picking = false;
    const wrap = input.closest('.proposal-asset-ler-wrap, .ler-ac-wrap');

    function setOpenState(isOpen) {
      wrap?.classList.toggle('is-open', !!isOpen);
      row?.classList.toggle('proposal-autocomplete-open', !!isOpen);
    }

    function positionList() {
      if (!list.classList.contains('show')) return;
      const rect = input.getBoundingClientRect();
      const stickyHeader = document.querySelector('#proposals > .templates-bleed > .section-header');
      const stickyHeaderRect = stickyHeader?.getBoundingClientRect?.() || null;
      const stickyHeaderBottom = stickyHeaderRect ? Math.max(stickyHeaderRect.bottom, 0) : 0;
      const nextTop = Math.max(rect.bottom + 2, stickyHeaderBottom + 6);
      const maxHeight = Math.max(window.innerHeight - nextTop - 12, 120);
      list.style.position = 'fixed';
      list.style.left = rect.left + 'px';
      list.style.top = nextTop + 'px';
      list.style.minWidth = rect.width + 'px';
      list.style.width = 'max-content';
      list.style.maxWidth = 'none';
      list.style.maxHeight = maxHeight + 'px';
      list.style.zIndex = '2000';
    }

    function hideList() {
      list.classList.remove('show');
      setOpenState(false);
    }

    function highlight(text, query) {
      if (!query) return text;
      const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      return text.replace(new RegExp('(' + escaped + ')', 'gi'), '<mark>$1</mark>');
    }

    function render(data, query, totalCount) {
      results = data;
      if (!data.length) {
        hideList();
        return;
      }
      const visible = data.slice(0, 3);
      let html = visible.map(function (item, index) {
        const main = highlight(item.short_name || '', query);
        const parts = [item.full_name, item.identifier, item.registration_number].filter(Boolean);
        const sub = parts.length ? highlight(parts.join(' · '), query) : '';
        return '<div class="ler-ac-item" data-idx="' + index + '">'
          + '<div class="ler-ac-main">' + main + '</div>'
          + (sub ? '<div class="ler-ac-sub">' + sub + '</div>' : '')
          + '</div>';
      }).join('');
      const remaining = totalCount - 3;
      if (remaining > 0) {
        html += '<div class="ler-ac-item ler-ac-more">Найдено ещё ' + remaining + ' юрлиц</div>';
      }
      list.innerHTML = html;
      list.classList.add('show');
      setOpenState(true);
      positionList();
    }

    function pick(item) {
      input.value = item.short_name || '';
      row.dataset.countryId = item.country_id || '';
      row.dataset.countryName = item.country_name || '';
      row.dataset.region = item.region || '';
      row.dataset.selectedIdentifierRecordId = item.identifier_record_id || '';
      row.dataset.selectedFromAutocomplete = '1';
      row.dataset.userEdited = '1';
      const country = row.querySelector(selectors.country);
      const identifier = row.querySelector(selectors.identifier);
      const regNumber = row.querySelector(selectors.regNumber);
      const regDate = row.querySelector(selectors.regDate);
      if (country) country.value = item.country_id || '';
      if (identifier) identifier.value = item.identifier || '';
      if (regNumber) regNumber.value = item.registration_number || '';
      setDateFieldValue(regDate, item.registration_date);
      hideList();
      updatePayload({
        reason: 'autofill',
        rowIndex: typeof getRowIndex === 'function' ? getRowIndex(row) : -1,
        item: item,
      });
    }

    input.addEventListener('input', function () {
      replaceQuotes(input);
      const query = input.value.trim();
      clearTimeout(debounce);
      row.dataset.selectedIdentifierRecordId = '';
      row.dataset.selectedFromAutocomplete = '0';
      updatePayload();
      if (query.length < 1) {
        hideList();
        return;
      }
      debounce = setTimeout(function () {
        fetch(searchUrl + '?q=' + encodeURIComponent(query))
          .then(function (response) { return response.json(); })
          .then(function (data) { render(data.results || [], query, data.total_count || 0); })
          .catch(function () { hideList(); });
      }, 200);
    });

    list.addEventListener('mousedown', function (event) {
      event.preventDefault();
      picking = true;
      const item = event.target.closest('.ler-ac-item');
      if (!item) return;
      const idx = parseInt(item.dataset.idx, 10);
      if (results[idx]) pick(results[idx]);
    });

    list.addEventListener('click', function (event) {
      const item = event.target.closest('.ler-ac-item');
      if (!item) return;
      const idx = parseInt(item.dataset.idx, 10);
      if (results[idx]) pick(results[idx]);
      picking = false;
    });

    input.addEventListener('blur', function () {
      if (picking) {
        picking = false;
        return;
      }
      setTimeout(hideList, 200);
    });

    input.addEventListener('focus', function () {
      if (results.length && input.value.trim().length >= 1) {
        list.classList.add('show');
        setOpenState(true);
        positionList();
      }
    });

    window.addEventListener('scroll', positionList, true);
    window.addEventListener('resize', positionList);
  }

  function getProposalAssetShortNameOptions(form) {
    const values = Array.from(form.querySelectorAll('#proposal-assets-tbody .proposal-asset-short-name'))
      .map(function (input) { return (input.value || '').trim(); })
      .filter(Boolean);
    return Array.from(new Set(values));
  }

  function getProposalLegalEntityShortNameOptions(form) {
    const values = Array.from(form.querySelectorAll('#proposal-legal-entities-tbody .proposal-legal-entity-short-name'))
      .map(function (input) { return (input.value || '').trim(); })
      .filter(Boolean);
    return Array.from(new Set(values));
  }

  function syncOptionsSelect(select, options, selectedValue) {
    if (!select) return false;
    const previousValue = typeof selectedValue === 'string' ? selectedValue : (select.value || '');
    select.innerHTML = '';

    const emptyOption = document.createElement('option');
    emptyOption.value = '';
    emptyOption.textContent = '— Не выбрано —';
    select.appendChild(emptyOption);

    options.forEach(function (value) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });

    select.value = options.includes(previousValue) ? previousValue : '';
    return select.value !== previousValue;
  }

  function syncProposalAssetNameSelect(select, form, selectedValue) {
    return syncOptionsSelect(select, getProposalAssetShortNameOptions(form), selectedValue);
  }

  function syncProposalLegalEntityNameSelect(select, form, selectedValue) {
    return syncOptionsSelect(select, getProposalLegalEntityShortNameOptions(form), selectedValue);
  }

  function getProposalTypicalSectionsMap(form) {
    const root = form?.closest('#proposals-pane') || pane() || document;
    const script = root.querySelector('#proposal-typical-sections-data');
    if (!script) return {};
    try {
      return JSON.parse(script.textContent || '{}') || {};
    } catch (error) {
      return {};
    }
  }

  function getProposalServiceGoalReportsMap(form) {
    const root = form?.closest('#proposals-pane') || pane() || document;
    const script = root.querySelector('#proposal-service-goal-reports-data');
    if (!script) return {};
    try {
      return JSON.parse(script.textContent || '{}') || {};
    } catch (error) {
      return {};
    }
  }

  function getProposalTypicalServiceCompositionsMap(form) {
    const root = form?.closest('#proposals-pane') || pane() || document;
    const script = root.querySelector('#proposal-typical-service-compositions-data');
    if (!script) return {};
    try {
      return JSON.parse(script.textContent || '{}') || {};
    } catch (error) {
      return {};
    }
  }

  function getProposalTypicalServiceTermsMap(form) {
    const root = form?.closest('#proposals-pane') || pane() || document;
    const script = root.querySelector('#proposal-typical-service-terms-data');
    if (!script) return {};
    try {
      return JSON.parse(script.textContent || '{}') || {};
    } catch (error) {
      return {};
    }
  }

  function getProposalOwningForm(node) {
    if (!node) return null;
    if (node.matches?.('form[data-proposal-form]')) return node;
    return node.closest?.('form[data-proposal-form]') || null;
  }

  function getProposalStageScope(node) {
    if (!node) return null;
    if (node.matches?.('[data-proposal-stage-root="1"]')) return node;
    return node.closest?.('[data-proposal-stage-root="1"]') || null;
  }

  function getProposalScope(node) {
    return getProposalStageScope(node) || getProposalOwningForm(node) || node;
  }

  function getProposalStageKey(node) {
    return String(getProposalStageScope(node)?.dataset?.proposalStageKey || '').trim();
  }

  function getProposalStageRoots(form, stageKey) {
    const key = String(stageKey || '').trim();
    if (!form || !key) return [];
    return Array.from(form.querySelectorAll('[data-proposal-stage-root="1"]')).filter(function (node) {
      return String(node?.dataset?.proposalStageKey || '').trim() === key;
    });
  }

  function getProposalStageRootByKind(form, stageKey, kind) {
    return getProposalStageRoots(form, stageKey).find(function (node) {
      return String(node?.dataset?.proposalStageKind || '').trim() === String(kind || '').trim();
    }) || null;
  }

  function getProposalTypeId(form) {
    const stageScope = getProposalStageScope(form);
    if (stageScope) {
      const stageTypeInput = stageScope.querySelector?.('[data-proposal-stage-type]');
      if (stageTypeInput) {
        return String(stageTypeInput.value || '').trim();
      }
    }
    const scope = getProposalOwningForm(form) || form;
    const typeSelects = Array.from(scope?.querySelectorAll?.('select[name="type"]') || []);
    if (!typeSelects.length) return '';
    return String(typeSelects[typeSelects.length - 1]?.value || '').trim();
  }

  function getProposalTypicalSectionEntries(form) {
    const sectionsMap = getProposalTypicalSectionsMap(form);
    const entries = sectionsMap[getProposalTypeId(form)] || [];
    return Array.isArray(entries) ? entries : [];
  }

  function getProposalServiceGoalReportEntry(form) {
    const entriesMap = getProposalServiceGoalReportsMap(form);
    const entry = entriesMap[getProposalTypeId(form)] || null;
    if (!entry || typeof entry !== 'object') return null;
    return {
      report_title: String(entry.report_title || '').trim(),
      service_goal: String(entry.service_goal || '').trim(),
    };
  }

  function getProposalTypicalServiceCompositionEntry(form, section) {
    const entriesMap = getProposalTypicalServiceCompositionsMap(form);
    const entries = Array.isArray(entriesMap[getProposalTypeId(form)]) ? entriesMap[getProposalTypeId(form)] : [];
    const code = String(section?.code || '').trim();
    const serviceName = String(section?.service_name || section?.name || '').trim();
    if (code) {
      const byCode = entries.find(function (entry) {
        return String(entry?.code || '').trim() === code;
      });
      if (byCode) return byCode;
    }
    if (serviceName) {
      return entries.find(function (entry) {
        return String(entry?.service_name || '').trim() === serviceName;
      }) || null;
    }
    return null;
  }

  function getProposalTypicalServiceCompositionText(form, section) {
    return String(getProposalTypicalServiceCompositionEntry(form, section)?.service_composition || '').trim();
  }

  function getProposalTypicalServiceCompositionEditorState(form, section) {
    const entry = getProposalTypicalServiceCompositionEntry(form, section);
    const value = entry?.service_composition_editor_state;
    return value && typeof value === 'object' ? value : {};
  }

  function getProposalTypicalServiceTermEntry(form) {
    const entriesMap = getProposalTypicalServiceTermsMap(form);
    const entry = entriesMap[getProposalTypeId(form)] || null;
    if (!entry || typeof entry !== 'object') return null;
    return {
      preliminary_report_months: String(entry.preliminary_report_months || '').trim(),
      final_report_weeks: String(entry.final_report_weeks || '').trim(),
    };
  }

  function normalizeProposalProjectNamePart(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function composeProposalProjectName(firstPart, secondPart) {
    return [firstPart, secondPart]
      .map(normalizeProposalProjectNamePart)
      .filter(Boolean)
      .join(' ');
  }

  function splitProposalProjectName(fullValue, secondPart, fallbackFirstPart) {
    const full = normalizeProposalProjectNamePart(fullValue);
    const suffix = normalizeProposalProjectNamePart(secondPart);
    const fallback = normalizeProposalProjectNamePart(fallbackFirstPart);
    if (!full) {
      return { firstPart: fallback, secondPart: '' };
    }
    if (suffix && full === suffix) {
      return { firstPart: '', secondPart: suffix };
    }
    if (suffix && full.endsWith(' ' + suffix)) {
      return {
        firstPart: normalizeProposalProjectNamePart(full.slice(0, full.length - suffix.length)),
        secondPart: suffix,
      };
    }
    if (fallback && (full === fallback || full.startsWith(fallback + ' '))) {
      return {
        firstPart: fallback,
        secondPart: normalizeProposalProjectNamePart(full.slice(fallback.length)),
      };
    }
    return { firstPart: full, secondPart: '' };
  }

  function getProposalTypicalSectionEntry(form, serviceName) {
    const target = (serviceName || '').trim();
    if (!target) return null;
    return getProposalTypicalSectionEntries(form).find(function (entry) {
      return (entry?.name || '').trim() === target;
    }) || null;
  }

  function isProposalTechnicalAssignmentSection(form, section) {
    const entry = getProposalTypicalSectionEntry(form, section?.service_name || section?.name || '');
    return String(entry?.accounting_type || '').trim() === 'Раздел';
  }

  function getProposalTypicalSectionNames(form) {
    return getProposalTypicalSectionEntries(form)
      .map(function (entry) { return (entry?.name || '').trim(); })
      .filter(Boolean);
  }

  function getProposalTypicalSectionCode(form, serviceName) {
    const match = getProposalTypicalSectionEntry(form, serviceName);
    return (match?.code || '').trim();
  }

  function getProposalTypicalSectionPrimaryExecutor(form, serviceName) {
    const match = getProposalTypicalSectionEntry(form, serviceName);
    const raw = String(match?.executor || '').trim();
    if (!raw) return '';
    return raw
      .split(/\s*(?:;|,|\n|\/)\s*/g)
      .map(function (item) { return item.trim(); })
      .filter(Boolean)[0] || '';
  }

  function getProposalCommercialAutofill(form, serviceName) {
    const entry = getProposalTypicalSectionEntry(form, serviceName);
    return {
      jobTitle: getProposalTypicalSectionPrimaryExecutor(form, serviceName),
      specialist: String(entry?.default_specialist || '').trim(),
      professionalStatus: String(entry?.default_professional_status || '').trim(),
      baseRateShare: Number.parseInt(entry?.default_base_rate_share || 0, 10) || 0,
      specialtyTariffRateEur: String(entry?.specialty_tariff_rate_eur || '').trim(),
      serviceDaysTkp: Number.parseInt(entry?.service_days_tkp || 0, 10) || 0,
      specialtyIsDirector: entry?.specialty_is_director === true,
      specialistOptions: Array.isArray(entry?.specialist_options)
        ? entry.specialist_options
          .map(function (item) {
            return {
              name: String(item?.name || '').trim(),
              professional_status: String(item?.professional_status || '').trim(),
              base_rate_share: Number.parseInt(item?.base_rate_share || 0, 10) || 0,
            };
          })
          .filter(function (item) { return !!item.name; })
        : [],
    };
  }

  function getProposalCommercialSpecialistOptions(form, serviceName, selectedValue) {
    const autofill = getProposalCommercialAutofill(form, serviceName);
    const options = autofill.specialistOptions.map(function (item) { return item.name; });
    const current = String(selectedValue || '').trim();
    if (current && !options.includes(current)) options.unshift(current);
    return options;
  }

  function getProposalCommercialSpecialistStatus(form, serviceName, specialistName) {
    const target = String(specialistName || '').trim();
    if (!target) return '';
    const match = getProposalCommercialAutofill(form, serviceName).specialistOptions.find(function (item) {
      return item.name === target;
    });
    return String(match?.professional_status || '').trim();
  }

  function getProposalCommercialSpecialistBaseRateShare(form, serviceName, specialistName) {
    const target = String(specialistName || '').trim();
    if (!target) return 0;
    const match = getProposalCommercialAutofill(form, serviceName).specialistOptions.find(function (item) {
      return item.name === target;
    });
    return Number.parseInt(match?.base_rate_share || 0, 10) || 0;
  }

  function getProposalCommercialRateValue(form, serviceName, specialistName) {
    const autofill = getProposalCommercialAutofill(form, serviceName);
    const baseRate = Number.parseFloat(String(autofill.specialtyTariffRateEur || '').replace(',', '.'));
    if (!Number.isFinite(baseRate) || baseRate <= 0) return '';
    const baseRateShare = autofill.specialtyIsDirector
      ? getProposalCommercialSpecialistBaseRateShare(form, serviceName, specialistName || autofill.specialist)
      : 0;
    const result = baseRate + (baseRate * (baseRateShare || 0) / 100);
    return result.toFixed(2);
  }

  function getProposalCommercialDayCounts(form, serviceName, currentValues, options) {
    const autofill = getProposalCommercialAutofill(form, serviceName);
    const defaultDays = Number.parseInt(autofill.serviceDaysTkp || 0, 10) || 0;
    const assetsPayloadInput = form?.querySelector('#proposal-assets-payload')
      || getProposalOwningForm(form)?.querySelector('#proposal-assets-payload');
    let assetCount = 0;
    try {
      const rows = JSON.parse(assetsPayloadInput?.value || '[]');
      assetCount = Array.isArray(rows) ? rows.length : 0;
    } catch (error) {
      assetCount = 0;
    }
    const targetCount = Math.max(
      assetCount,
      Array.isArray(currentValues) ? currentValues.length : 0,
      1
    );
    const existingValues = Array.isArray(currentValues)
      ? currentValues.map(function (value) { return String(value ?? '').trim(); })
      : [];
    if (options?.replaceAll === true) {
      if (defaultDays <= 0) return existingValues.slice(0, targetCount);
      return Array.from({ length: targetCount }, function () {
        return String(defaultDays);
      });
    }
    const result = existingValues.slice(0, targetCount);
    while (result.length < targetCount) {
      result.push(defaultDays > 0 ? String(defaultDays) : '');
    }
    return result;
  }

  function syncProposalCommercialSpecialistSelect(select, form, serviceName, selectedValue) {
    return syncOptionsSelect(
      select,
      getProposalCommercialSpecialistOptions(form, serviceName, selectedValue),
      selectedValue
    );
  }

  function syncProposalCommercialServiceSelect(select, form, selectedValue) {
    return syncOptionsSelect(select, getProposalTypicalSectionNames(form), selectedValue);
  }

  const PROPOSAL_TRAVEL_EXPENSES_LABEL = 'Командировочные расходы, евро';
  const PROPOSAL_TRAVEL_EXPENSES_LABEL_LEGACY = 'Командировочные расходы';
  const PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL = 'actual';
  const PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION = 'calculation';
  const PROPOSAL_SUMMARY_TOTAL_LABEL = 'ИТОГО, по расчёту';
  const PROPOSAL_SUMMARY_WITH_TRAVEL_TOTAL_LABEL = 'ИТОГО, евро с командировочными по расчёту';
  const PROPOSAL_RUB_TOTAL_LABEL = 'ИТОГО, рубли без НДС';
  const PROPOSAL_RUB_DISCOUNTED_LABEL = 'ИТОГО, рубли без НДС с учетом скидки';
  const PROPOSAL_CONTRACT_TOTAL_LABEL = 'ИТОГО в договор, рубли без НДС с учётом дополнительной скидки';
  const PROPOSAL_CBR_EUR_DAILY_URL = 'https://www.cbr.ru/currency_base/daily/';

  function isProposalTravelExpensesRow(row) {
    const serviceName = String(row?.service_name || '').trim();
    return serviceName === PROPOSAL_TRAVEL_EXPENSES_LABEL || serviceName === PROPOSAL_TRAVEL_EXPENSES_LABEL_LEGACY;
  }

  function normalizeProposalTravelExpensesRow(row) {
    const dayCounts = Array.isArray(row?.asset_day_counts)
      ? row.asset_day_counts.map(function (value) { return String(value ?? '').trim(); })
      : [];
    return {
      specialist: '',
      job_title: '',
      professional_status: '',
      service_name: PROPOSAL_TRAVEL_EXPENSES_LABEL,
      code: '',
      rate_eur_per_day: '',
      asset_day_counts: dayCounts,
      total_eur_without_vat: String(row?.total_eur_without_vat || '').trim(),
    };
  }

  function normalizeProposalTravelExpensesMode(value) {
    const mode = String(value || '').trim();
    if (mode === PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL || mode === PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION) {
      return mode;
    }
    return '';
  }

  function inferProposalTravelExpensesMode(row, fallbackValue) {
    const explicitMode = normalizeProposalTravelExpensesMode(fallbackValue);
    if (explicitMode) return explicitMode;
    const assetValues = Array.isArray(row?.asset_day_counts) ? row.asset_day_counts : [];
    const hasSavedAssetValues = assetValues.some(function (value) { return String(value ?? '').trim(); });
    return hasSavedAssetValues ? PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION : PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL;
  }

  function parseProposalPercent(value) {
    const normalized = String(value || '').replace(/\s/g, '').replace(/\u00a0/g, '').replace('%', '').replace(',', '.');
    const number = parseFloat(normalized);
    return Number.isFinite(number) ? number : null;
  }

  function formatProposalPercentDisplay(value) {
    const normalized = String(value || '').replace(/\s/g, '').replace(/\u00a0/g, '').replace('%', '').replace(',', '.').trim();
    if (!normalized) return '';
    return normalized + '%';
  }

  function normalizeProposalCommercialTotalsState(payload) {
    const source = payload && typeof payload === 'object' ? payload : {};
    return {
      exchange_rate: String(source.exchange_rate || '').trim(),
      discount_percent: String(source.discount_percent || '5').replace('%', '').trim(),
      contract_total: String(source.contract_total || '').trim(),
      contract_total_auto: String(source.contract_total_auto || '').trim(),
      rub_total_service_text: String(source.rub_total_service_text || 'Курс евро Банка России на текущую дату:').trim(),
      discounted_total_service_text: String(source.discounted_total_service_text || 'Размер скидки:').trim(),
      travel_expenses_mode: normalizeProposalTravelExpensesMode(source.travel_expenses_mode),
    };
  }

  function formatProposalCurrentDateLabel(date) {
    const value = date instanceof Date ? date : new Date();
    const day = String(value.getDate()).padStart(2, '0');
    const month = String(value.getMonth() + 1).padStart(2, '0');
    const year = String(value.getFullYear());
    return day + '.' + month + '.' + year;
  }

  function getProposalCbrRateText(dateLabel) {
    return 'Курс евро Банка России на ' + String(dateLabel || formatProposalCurrentDateLabel()) + ':';
  }

  function roundProposalToHundredThousand(value) {
    if (!Number.isFinite(value)) return '';
    return String(Math.floor(value / 100000) * 100000);
  }

  function syncProposalServiceSectionSelect(select, form, selectedValue) {
    return syncOptionsSelect(select, getProposalTypicalSectionNames(form), selectedValue);
  }

  function attachProposalEntityTable(root, config) {
    if (!root) return;
    const form = root.closest('form[data-proposal-form]') || root;
    const payloadInput = form.querySelector(config.payloadSelector);
    const tbody = form.querySelector(config.tbodySelector);
    const addBtn = form.querySelector(config.addBtnSelector);
    const actions = form.querySelector(config.actionsSelector);
    const upBtn = form.querySelector(config.upBtnSelector);
    const downBtn = form.querySelector(config.downBtnSelector);
    const deleteBtn = form.querySelector(config.deleteBtnSelector);
    const searchUrl = form.dataset.lerSearchUrl;
    const identifierUrl = form.dataset.countryIdentifierUrl;
    const countryTemplate = form.querySelector('#proposal-country-select');
    if (!payloadInput || !tbody || !addBtn || !actions || !upBtn || !downBtn || !deleteBtn || !searchUrl || !countryTemplate) return null;
    if (form.dataset[config.boundFlag] === '1') return form[config.apiKey] || null;
    form.dataset[config.boundFlag] = '1';

    function parsePayload() {
      try {
        const data = JSON.parse(payloadInput.value || '[]');
        return Array.isArray(data) ? data : [];
      } catch (error) {
        return [];
      }
    }

    function getDefaultRowData() {
      if (typeof config.getDefaultRowData !== 'function') return null;
      return config.getDefaultRowData(form) || null;
    }

    let lastDefaultRowData = getDefaultRowData();

    function mergeWithDefaultRowData(data) {
      const source = data && typeof data === 'object' ? data : {};
      const defaults = getDefaultRowData();
      if (!defaults) return source;
      return {
        ...source,
        short_name: String(source.short_name || '').trim() || String(defaults.short_name || '').trim(),
        country_id: String(source.country_id || '').trim() || String(defaults.country_id || '').trim(),
        country_name: String(source.country_name || '').trim() || String(defaults.country_name || '').trim(),
        identifier: String(source.identifier || '').trim() || String(defaults.identifier || '').trim(),
        registration_number: String(source.registration_number || '').trim() || String(defaults.registration_number || '').trim(),
        registration_date: String(source.registration_date || '').trim() || String(defaults.registration_date || '').trim(),
        region: String(source.region || '').trim() || String(defaults.region || '').trim(),
      };
    }

    function normalizePrefillValue(value) {
      return String(value || '').trim();
    }

    function shouldOverwritePrefilledValue(currentValue, previousDefaultValue) {
      const current = normalizePrefillValue(currentValue);
      const previousDefault = normalizePrefillValue(previousDefaultValue);
      return !current || (previousDefault && current === previousDefault);
    }

    function getAllRows() {
      return Array.from(tbody.querySelectorAll('tr'));
    }

    function getRows() {
      return getAllRows().filter(function (row) {
        return row.dataset.travelExpensesRow !== '1';
      });
    }

    function getSelectedRows() {
      return getRows().filter(function (row) {
        return !!row.querySelector(config.selectors.check + ':checked');
      });
    }

    function clearRowAutocompleteSelection(row) {
      if (!row) return;
      row.dataset.selectedIdentifierRecordId = '';
      row.dataset.selectedFromAutocomplete = '0';
    }

    function markRowUserEdited(row, edited) {
      if (!row) return;
      row.dataset.userEdited = edited ? '1' : '0';
    }

    function syncActions() {
      const hasSelected = getSelectedRows().length > 0;
      actions.classList.toggle('d-none', !hasSelected);
      actions.classList.toggle('d-flex', hasSelected);
    }

    function serializeRow(row) {
      const data = {
        short_name: (row.querySelector(config.selectors.shortInput)?.value || '').trim(),
        country_id: row.dataset.countryId || '',
        country_name: row.dataset.countryName || '',
        identifier: (row.querySelector(config.selectors.identifier)?.value || '').trim(),
        registration_number: (row.querySelector(config.selectors.regNumber)?.value || '').trim(),
        registration_date: (row.querySelector(config.selectors.regDate)?.value || '').trim(),
        region: row.dataset.region || '',
        selected_identifier_record_id: row.dataset.selectedIdentifierRecordId || '',
        selected_from_autocomplete: row.dataset.selectedFromAutocomplete === '1',
        user_edited: row.dataset.userEdited === '1',
      };
      if (config.withAssetSelect) {
        data.asset_short_name = (row.querySelector(config.selectors.assetSelect)?.value || '').trim();
      }
      return data;
    }

    function updatePayload(meta) {
      const rows = getRows().map(serializeRow);
      payloadInput.value = JSON.stringify(rows);
      syncActions();
      if (config.rowsChangedEvent) {
        form.dispatchEvent(new CustomEvent(config.rowsChangedEvent, { detail: { rows: rows, meta: meta || null } }));
      }
    }

    function setRowData(row, data) {
      if (!row || !data) return;
      if (config.withAssetSelect) {
        const assetSelect = row.querySelector(config.selectors.assetSelect);
        if (assetSelect) {
          syncProposalAssetNameSelect(assetSelect, form, data.asset_short_name || '');
          assetSelect.value = data.asset_short_name || '';
        }
      }

      row.dataset.countryId = data.country_id || '';
      row.dataset.countryName = data.country_name || '';
      row.dataset.region = data.region || '';
      row.dataset.selectedIdentifierRecordId = data.selected_identifier_record_id || '';
      row.dataset.selectedFromAutocomplete = data.selected_from_autocomplete ? '1' : '0';
      row.dataset.userEdited = data.user_edited ? '1' : '0';

      const shortInput = row.querySelector(config.selectors.shortInput);
      const countrySelect = row.querySelector(config.selectors.country);
      const identifierInput = row.querySelector(config.selectors.identifier);
      const regNumberInput = row.querySelector(config.selectors.regNumber);
      const regDateInput = row.querySelector(config.selectors.regDate);

      if (shortInput) shortInput.value = data.short_name || '';
      if (countrySelect) countrySelect.value = data.country_id || '';
      if (identifierInput) identifierInput.value = data.identifier || '';
      if (regNumberInput) regNumberInput.value = data.registration_number || '';
      setDateFieldValue(regDateInput, data.registration_date || '');
    }

    function createRow(data, options) {
      const sourceData = data && typeof data === 'object' ? data : {};
      const skipDefaultPrefill = options?.skipDefaultPrefill === true;
      const hasExplicitSourceData = Boolean(
        (sourceData.short_name || '').trim()
        || (sourceData.country_id || '').trim()
        || (sourceData.country_name || '').trim()
        || (sourceData.identifier || '').trim()
        || (sourceData.registration_number || '').trim()
        || (sourceData.registration_date || '').trim()
        || (sourceData.region || '').trim()
        || (sourceData.selected_identifier_record_id || '').trim()
      );
      data = skipDefaultPrefill ? { ...sourceData } : mergeWithDefaultRowData(sourceData);
      const row = document.createElement('tr');
      row.dataset.countryId = data.country_id || '';
      row.dataset.countryName = data.country_name || '';
      row.dataset.region = data.region || '';
      row.dataset.selectedIdentifierRecordId = data.selected_identifier_record_id || '';
      row.dataset.selectedFromAutocomplete = data.selected_from_autocomplete ? '1' : '0';
      row.dataset.userEdited = data.user_edited ? '1' : (hasExplicitSourceData ? '1' : '0');

      const checkTd = createProposalTableCell('proposal-asset-check-cell');
      const checkWrap = document.createElement('div');
      checkWrap.className = 'form-check proposal-asset-check-wrap';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'form-check-input ' + config.checkClass;
      checkbox.style.margin = '0';
      checkbox.style.float = 'none';
      checkbox.addEventListener('change', syncActions);
      checkWrap.appendChild(checkbox);
      checkTd.appendChild(checkWrap);
      row.appendChild(checkTd);

      if (config.withAssetSelect) {
        const assetTd = createProposalTableCell('proposal-asset-parent-short-cell');
        const assetSelect = document.createElement('select');
        assetSelect.className = 'form-select ' + config.assetSelectClass;
        syncProposalAssetNameSelect(assetSelect, form, data.asset_short_name || '');
        assetSelect.addEventListener('change', updatePayload);
        assetTd.appendChild(assetSelect);
        row.appendChild(assetTd);
      }

      const shortTd = createProposalTableCell('proposal-asset-short-cell');
      const shortWrap = document.createElement('div');
      shortWrap.className = 'ler-ac-wrap proposal-asset-ler-wrap';
      const shortInput = document.createElement('input');
      shortInput.type = 'text';
      shortInput.className = 'form-control ' + config.shortInputClass;
      shortInput.placeholder = 'Искать по наименованию и регистрационному номеру';
      shortInput.value = data.short_name || '';
      const shortList = document.createElement('div');
      shortList.className = 'ler-ac-list proposal-asset-ler-list';
      shortWrap.appendChild(shortInput);
      shortWrap.appendChild(shortList);
      shortTd.appendChild(shortWrap);
      row.appendChild(shortTd);

      const countryTd = createProposalTableCell();
      const countrySelect = countryTemplate.cloneNode(true);
      countrySelect.id = '';
      countrySelect.name = '';
      countrySelect.className = 'form-select ' + config.countryClass;
      countrySelect.value = data.country_id || '';
      countryTd.appendChild(countrySelect);
      row.appendChild(countryTd);

      const identifierTd = createProposalTableCell();
      const identifierInput = document.createElement('input');
      identifierInput.type = 'text';
      identifierInput.className = 'form-control readonly-field ' + config.identifierClass;
      identifierInput.readOnly = true;
      identifierInput.tabIndex = -1;
      identifierInput.value = data.identifier || '';
      identifierTd.appendChild(identifierInput);
      row.appendChild(identifierTd);

      const regNumberTd = createProposalTableCell();
      const regNumberInput = document.createElement('input');
      regNumberInput.type = 'text';
      regNumberInput.className = 'form-control ' + config.regNumberClass;
      regNumberInput.value = data.registration_number || '';
      regNumberTd.appendChild(regNumberInput);
      row.appendChild(regNumberTd);

      const regDateTd = createProposalTableCell();
      const regDateInput = document.createElement('input');
      regDateInput.type = 'text';
      regDateInput.className = 'form-control js-date ' + config.regDateClass;
      regDateInput.autocomplete = 'off';
      setDateFieldValue(regDateInput, data.registration_date);
      regDateTd.appendChild(regDateInput);
      row.appendChild(regDateTd);

      [shortInput, countrySelect, identifierInput, regNumberInput, regDateInput].forEach(function (input) {
        input.addEventListener('change', updatePayload);
        input.addEventListener('input', function () {
          if (input !== shortInput) updatePayload();
        });
      });

      shortInput.addEventListener('input', function () {
        markRowUserEdited(row, true);
      });
      shortInput.addEventListener('change', function () {
        markRowUserEdited(row, true);
      });

      countrySelect.addEventListener('change', function () {
        clearRowAutocompleteSelection(row);
        markRowUserEdited(row, true);
        row.dataset.countryId = countrySelect.value || '';
        row.dataset.countryName = countrySelect.options[countrySelect.selectedIndex]?.textContent?.trim() || '';
        if (!identifierUrl) {
          updatePayload();
          return;
        }
        if (!countrySelect.value) {
          identifierInput.value = '';
          updatePayload();
          return;
        }
        fetch(identifierUrl + '?country_id=' + encodeURIComponent(countrySelect.value))
          .then(function (response) { return response.json(); })
          .then(function (dataResp) {
            identifierInput.value = dataResp.identifier || '';
            updatePayload();
          })
          .catch(function () {
            identifierInput.value = '';
            updatePayload();
          });
      });

      regNumberInput.addEventListener('input', function () {
        clearRowAutocompleteSelection(row);
        markRowUserEdited(row, true);
      });
      regNumberInput.addEventListener('change', function () {
        clearRowAutocompleteSelection(row);
        markRowUserEdited(row, true);
      });
      regDateInput.addEventListener('input', function () {
        clearRowAutocompleteSelection(row);
        markRowUserEdited(row, true);
      });
      regDateInput.addEventListener('change', function () {
        clearRowAutocompleteSelection(row);
        markRowUserEdited(row, true);
      });

      bindProposalEntityAutocomplete(shortInput, shortList, row, updatePayload, searchUrl, config.selectors, function (targetRow) {
        return getRows().indexOf(targetRow);
      });
      return row;
    }

    function activateRow(row) {
      const regDateInput = row.querySelector(config.selectors.regDate);
      if (!regDateInput) return;
      initProposalDateInput(regDateInput);
    }

    function moveSelected(direction) {
      const rows = getRows();
      if (direction === 'up') {
        for (let i = 1; i < rows.length; i += 1) {
          if (rows[i].querySelector(config.selectors.check + ':checked') && !rows[i - 1].querySelector(config.selectors.check + ':checked')) {
            tbody.insertBefore(rows[i], rows[i - 1]);
          }
        }
      } else {
        for (let i = rows.length - 2; i >= 0; i -= 1) {
          if (rows[i].querySelector(config.selectors.check + ':checked') && !rows[i + 1].querySelector(config.selectors.check + ':checked')) {
            tbody.insertBefore(rows[i + 1], rows[i]);
          }
        }
      }
      updatePayload();
    }

    function deleteSelected() {
      getSelectedRows().forEach(function (row) {
        row.remove();
      });
      updatePayload();
    }

    addBtn.addEventListener('click', function () {
      const row = createRow({}, { skipDefaultPrefill: config.skipDefaultPrefillOnManualAdd === true });
      tbody.appendChild(row);
      activateRow(row);
      updatePayload({ reason: 'row-add', rowIndex: getRows().length - 1 });
      row.querySelector(config.selectors.shortInput)?.focus();
    });

    upBtn.addEventListener('click', function () { moveSelected('up'); });
    downBtn.addEventListener('click', function () { moveSelected('down'); });
    deleteBtn.addEventListener('click', deleteSelected);

    if (config.assetOptionsEvent) {
      form.addEventListener(config.assetOptionsEvent, function () {
        let changed = false;
        getRows().forEach(function (row) {
          const select = row.querySelector(config.selectors.assetSelect);
          if (syncProposalAssetNameSelect(select, form)) changed = true;
        });
        if (changed) updatePayload();
      });
    }

    parsePayload().forEach(function (item) {
      const row = createRow(item);
      tbody.appendChild(row);
      activateRow(row);
    });
    updatePayload();

    const api = {
      getRows: getRows,
      getSerializedRows: function () {
        return getRows().map(serializeRow);
      },
      ensureRowCount: function (count) {
        while (getRows().length < count) {
          const row = createRow({});
          tbody.appendChild(row);
          activateRow(row);
        }
        while (getRows().length > count) {
          const row = getRows()[getRows().length - 1];
          if (!row) break;
          row.remove();
        }
        updatePayload({ reason: 'sync-row-count' });
      },
      setRowDataByIndex: function (index, data) {
        if (index < 0) return;
        this.ensureRowCount(index + 1);
        const row = getRows()[index];
        setRowData(row, data);
        updatePayload({ reason: 'sync-row-data', rowIndex: index });
      },
      syncAssetSelectionsByRows: function (assetRows) {
        if (!config.withAssetSelect) return;
        getRows().forEach(function (row, index) {
          const assetSelect = row.querySelector(config.selectors.assetSelect);
          if (!assetSelect) return;
          const assetName = assetRows[index]?.short_name || '';
          syncProposalAssetNameSelect(assetSelect, form, assetName);
          assetSelect.value = assetName;
        });
        updatePayload({ reason: 'sync-asset-selects' });
      },
      fillEmptyRowsFromDefaults: function () {
        const defaults = getDefaultRowData();
        if (!defaults) {
          lastDefaultRowData = defaults;
          return;
        }
        let changed = false;
        getRows().forEach(function (row) {
          const serialized = serializeRow(row);
          const merged = {
            ...serialized,
            short_name: shouldOverwritePrefilledValue(serialized.short_name, lastDefaultRowData?.short_name)
              ? normalizePrefillValue(defaults.short_name)
              : serialized.short_name,
            country_id: shouldOverwritePrefilledValue(serialized.country_id, lastDefaultRowData?.country_id)
              ? normalizePrefillValue(defaults.country_id)
              : serialized.country_id,
            country_name: shouldOverwritePrefilledValue(serialized.country_name, lastDefaultRowData?.country_name)
              ? normalizePrefillValue(defaults.country_name)
              : serialized.country_name,
            identifier: shouldOverwritePrefilledValue(serialized.identifier, lastDefaultRowData?.identifier)
              ? normalizePrefillValue(defaults.identifier)
              : serialized.identifier,
            registration_number: shouldOverwritePrefilledValue(serialized.registration_number, lastDefaultRowData?.registration_number)
              ? normalizePrefillValue(defaults.registration_number)
              : serialized.registration_number,
            registration_date: shouldOverwritePrefilledValue(serialized.registration_date, lastDefaultRowData?.registration_date)
              ? normalizePrefillValue(defaults.registration_date)
              : serialized.registration_date,
            region: shouldOverwritePrefilledValue(serialized.region, lastDefaultRowData?.region)
              ? normalizePrefillValue(defaults.region)
              : serialized.region,
          };
          if (
            merged.short_name !== serialized.short_name
            || merged.country_id !== serialized.country_id
            || merged.country_name !== serialized.country_name
            || merged.identifier !== serialized.identifier
            || merged.registration_number !== serialized.registration_number
            || merged.registration_date !== serialized.registration_date
            || merged.region !== serialized.region
          ) {
            merged.user_edited = false;
            setRowData(row, merged);
            changed = true;
          }
        });
        lastDefaultRowData = { ...defaults };
        if (changed) updatePayload({ reason: 'default-row-prefill' });
      },
    };
    form[config.apiKey] = api;
    return api;
  }

  function attachProposalAssetsTable(root) {
    return attachProposalEntityTable(root, {
      payloadSelector: '#proposal-assets-payload',
      tbodySelector: '#proposal-assets-tbody',
      addBtnSelector: '#proposal-asset-add-btn',
      actionsSelector: '#proposal-assets-row-actions',
      upBtnSelector: '#proposal-asset-up-btn',
      downBtnSelector: '#proposal-asset-down-btn',
      deleteBtnSelector: '#proposal-asset-delete-btn',
      boundFlag: 'assetsBound',
      checkClass: 'proposal-asset-check',
      shortInputClass: 'proposal-asset-short-name',
      countryClass: 'proposal-asset-country',
      identifierClass: 'proposal-asset-identifier',
      regNumberClass: 'proposal-asset-reg-number',
      regDateClass: 'proposal-asset-reg-date',
      selectors: {
        check: '.proposal-asset-check',
        shortInput: '.proposal-asset-short-name',
        country: '.proposal-asset-country',
        identifier: '.proposal-asset-identifier',
        regNumber: '.proposal-asset-reg-number',
        regDate: '.proposal-asset-reg-date',
      },
      getDefaultRowData: function (form) {
        const ownerInput = form.querySelector('input[name="asset_owner"]');
        const ownerCountry = form.querySelector('#proposal-asset-owner-country-select');
        const ownerIdentifier = form.querySelector('#proposal-asset-owner-identifier-field');
        const ownerRegistrationNumber = form.querySelector('input[name="asset_owner_registration_number"]');
        const ownerRegistrationDate = form.querySelector('input[name="asset_owner_registration_date"]');
        return {
          short_name: ownerInput ? (ownerInput.value || '').trim() : '',
          country_id: ownerCountry ? (ownerCountry.value || '').trim() : '',
          country_name: ownerCountry?.options?.[ownerCountry.selectedIndex]?.textContent?.trim() || '',
          identifier: ownerIdentifier ? (ownerIdentifier.value || '').trim() : '',
          registration_number: ownerRegistrationNumber ? (ownerRegistrationNumber.value || '').trim() : '',
          registration_date: ownerRegistrationDate ? (ownerRegistrationDate.value || '').trim() : '',
        };
      },
      rowsChangedEvent: 'proposal-assets-changed',
      skipDefaultPrefillOnManualAdd: true,
      withAssetSelect: false,
      apiKey: '__proposalAssetsTableApi',
    });
  }

  function attachProposalLegalEntitiesTable(root) {
    return attachProposalEntityTable(root, {
      payloadSelector: '#proposal-legal-entities-payload',
      tbodySelector: '#proposal-legal-entities-tbody',
      addBtnSelector: '#proposal-legal-entity-add-btn',
      actionsSelector: '#proposal-legal-entities-row-actions',
      upBtnSelector: '#proposal-legal-entity-up-btn',
      downBtnSelector: '#proposal-legal-entity-down-btn',
      deleteBtnSelector: '#proposal-legal-entity-delete-btn',
      boundFlag: 'legalEntitiesBound',
      checkClass: 'proposal-legal-entity-check',
      shortInputClass: 'proposal-legal-entity-short-name',
      countryClass: 'proposal-legal-entity-country',
      identifierClass: 'proposal-legal-entity-identifier',
      regNumberClass: 'proposal-legal-entity-reg-number',
      regDateClass: 'proposal-legal-entity-reg-date',
      assetSelectClass: 'proposal-legal-entity-asset-short-name',
      selectors: {
        check: '.proposal-legal-entity-check',
        assetSelect: '.proposal-legal-entity-asset-short-name',
        shortInput: '.proposal-legal-entity-short-name',
        country: '.proposal-legal-entity-country',
        identifier: '.proposal-legal-entity-identifier',
        regNumber: '.proposal-legal-entity-reg-number',
        regDate: '.proposal-legal-entity-reg-date',
      },
      rowsChangedEvent: 'proposal-legal-entities-changed',
      withAssetSelect: true,
      assetOptionsEvent: 'proposal-assets-changed',
      apiKey: '__proposalLegalEntitiesTableApi',
    });
  }

  function attachProposalObjectsTable(root) {
    if (!root) return null;
    const form = root.closest('form[data-proposal-form]') || root;
    const payloadInput = form.querySelector('#proposal-objects-payload');
    const tbody = form.querySelector('#proposal-objects-tbody');
    const addBtn = form.querySelector('#proposal-object-add-btn');
    const actions = form.querySelector('#proposal-objects-row-actions');
    const upBtn = form.querySelector('#proposal-object-up-btn');
    const downBtn = form.querySelector('#proposal-object-down-btn');
    const deleteBtn = form.querySelector('#proposal-object-delete-btn');
    if (!payloadInput || !tbody || !addBtn || !actions || !upBtn || !downBtn || !deleteBtn) return null;
    if (form.dataset.objectsBound === '1') return form.__proposalObjectsTableApi || null;
    form.dataset.objectsBound = '1';

    function parsePayload() {
      try {
        const data = JSON.parse(payloadInput.value || '[]');
        return Array.isArray(data) ? data : [];
      } catch (error) {
        return [];
      }
    }

    function getRows() {
      return Array.from(tbody.querySelectorAll('tr'));
    }

    function getSelectedRows() {
      return getRows().filter(function (row) {
        return !!row.querySelector('.proposal-object-check:checked');
      });
    }

    function syncActions() {
      const hasSelected = getSelectedRows().length > 0;
      actions.classList.toggle('d-none', !hasSelected);
      actions.classList.toggle('d-flex', hasSelected);
    }

    function serializeRow(row) {
      return {
        legal_entity_short_name: (row.querySelector('.proposal-object-legal-entity-short-name')?.value || '').trim(),
        short_name: (row.querySelector('.proposal-object-short-name')?.value || '').trim(),
        region: (row.querySelector('.proposal-object-region')?.value || '').trim(),
        object_type: (row.querySelector('.proposal-object-type')?.value || '').trim(),
        license: (row.querySelector('.proposal-object-license')?.value || '').trim(),
        registration_date: (row.querySelector('.proposal-object-reg-date')?.value || '').trim(),
      };
    }

    function updatePayload(meta) {
      const rows = getRows().map(serializeRow);
      payloadInput.value = JSON.stringify(rows);
      syncActions();
      form.dispatchEvent(new CustomEvent('proposal-objects-changed', { detail: { rows: rows, meta: meta || null } }));
    }

    function setRowData(row, data) {
      if (!row || !data) return;
      const legalEntitySelect = row.querySelector('.proposal-object-legal-entity-short-name');
      const shortInput = row.querySelector('.proposal-object-short-name');
      const regionInput = row.querySelector('.proposal-object-region');
      const typeInput = row.querySelector('.proposal-object-type');
      const licenseInput = row.querySelector('.proposal-object-license');
      const regDateInput = row.querySelector('.proposal-object-reg-date');

      if (legalEntitySelect) {
        syncProposalLegalEntityNameSelect(legalEntitySelect, form, data.legal_entity_short_name || '');
        legalEntitySelect.value = data.legal_entity_short_name || '';
      }
      if (shortInput) shortInput.value = data.short_name || '';
      if (regionInput) regionInput.value = data.region || '';
      if (typeInput) typeInput.value = data.object_type || '';
      if (licenseInput) licenseInput.value = data.license || '';
      setDateFieldValue(regDateInput, data.registration_date || '');
    }

    function createRow(data) {
      const row = document.createElement('tr');

      const checkTd = createProposalTableCell('proposal-asset-check-cell');
      const checkWrap = document.createElement('div');
      checkWrap.className = 'form-check proposal-asset-check-wrap';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'form-check-input proposal-object-check';
      checkbox.style.margin = '0';
      checkbox.style.float = 'none';
      checkbox.addEventListener('change', syncActions);
      checkWrap.appendChild(checkbox);
      checkTd.appendChild(checkWrap);
      row.appendChild(checkTd);

      const legalEntityTd = createProposalTableCell('proposal-asset-parent-short-cell');
      const legalEntitySelect = document.createElement('select');
      legalEntitySelect.className = 'form-select proposal-object-legal-entity-short-name';
      syncProposalLegalEntityNameSelect(legalEntitySelect, form, data.legal_entity_short_name || '');
      legalEntitySelect.addEventListener('change', updatePayload);
      legalEntityTd.appendChild(legalEntitySelect);
      row.appendChild(legalEntityTd);

      const shortTd = createProposalTableCell('proposal-asset-short-cell');
      const shortInput = document.createElement('input');
      shortInput.type = 'text';
      shortInput.className = 'form-control proposal-object-short-name';
      shortInput.value = data.short_name || '';
      shortTd.appendChild(shortInput);
      row.appendChild(shortTd);

      const regionTd = createProposalTableCell();
      const regionInput = document.createElement('input');
      regionInput.type = 'text';
      regionInput.className = 'form-control proposal-object-region';
      regionInput.value = data.region || '';
      regionTd.appendChild(regionInput);
      row.appendChild(regionTd);

      const typeTd = createProposalTableCell();
      const typeInput = document.createElement('input');
      typeInput.type = 'text';
      typeInput.className = 'form-control proposal-object-type';
      typeInput.value = data.object_type || '';
      typeTd.appendChild(typeInput);
      row.appendChild(typeTd);

      const licenseTd = createProposalTableCell();
      const licenseInput = document.createElement('input');
      licenseInput.type = 'text';
      licenseInput.className = 'form-control proposal-object-license';
      licenseInput.value = data.license || '';
      licenseTd.appendChild(licenseInput);
      row.appendChild(licenseTd);

      const regDateTd = createProposalTableCell();
      const regDateInput = document.createElement('input');
      regDateInput.type = 'text';
      regDateInput.className = 'form-control js-date proposal-object-reg-date';
      regDateInput.autocomplete = 'off';
      setDateFieldValue(regDateInput, data.registration_date);
      regDateTd.appendChild(regDateInput);
      row.appendChild(regDateTd);

      [shortInput, regionInput, typeInput, licenseInput, regDateInput].forEach(function (input) {
        input.addEventListener('change', updatePayload);
        input.addEventListener('input', updatePayload);
      });

      return row;
    }

    function activateRow(row) {
      const regDateInput = row.querySelector('.proposal-object-reg-date');
      if (!regDateInput) return;
      initProposalDateInput(regDateInput);
    }

    function moveSelected(direction) {
      const rows = getRows();
      if (direction === 'up') {
        for (let i = 1; i < rows.length; i += 1) {
          if (rows[i].querySelector('.proposal-object-check:checked') && !rows[i - 1].querySelector('.proposal-object-check:checked')) {
            tbody.insertBefore(rows[i], rows[i - 1]);
          }
        }
      } else {
        for (let i = rows.length - 2; i >= 0; i -= 1) {
          if (rows[i].querySelector('.proposal-object-check:checked') && !rows[i + 1].querySelector('.proposal-object-check:checked')) {
            tbody.insertBefore(rows[i + 1], rows[i]);
          }
        }
      }
      updatePayload();
    }

    function deleteSelected() {
      getSelectedRows().forEach(function (row) {
        row.remove();
      });
      updatePayload();
    }

    addBtn.addEventListener('click', function () {
      const row = createRow({});
      tbody.appendChild(row);
      activateRow(row);
      updatePayload({ reason: 'row-add', rowIndex: getRows().length - 1 });
      row.querySelector('.proposal-object-short-name')?.focus();
    });

    upBtn.addEventListener('click', function () { moveSelected('up'); });
    downBtn.addEventListener('click', function () { moveSelected('down'); });
    deleteBtn.addEventListener('click', deleteSelected);

    form.addEventListener('proposal-legal-entities-changed', function () {
      let changed = false;
      getRows().forEach(function (row) {
        const select = row.querySelector('.proposal-object-legal-entity-short-name');
        if (syncProposalLegalEntityNameSelect(select, form)) changed = true;
      });
      if (changed) updatePayload();
    });

    parsePayload().forEach(function (item) {
      const row = createRow(item);
      tbody.appendChild(row);
      activateRow(row);
    });
    updatePayload();

    const api = {
      getSerializedRows: function () {
        return getRows().map(serializeRow);
      },
      ensureRowCount: function (count) {
        while (getRows().length < count) {
          const row = createRow({});
          tbody.appendChild(row);
          activateRow(row);
        }
        while (getRows().length > count) {
          const row = getRows()[getRows().length - 1];
          if (!row) break;
          row.remove();
        }
        updatePayload({ reason: 'sync-row-count' });
      },
      setRowDataByIndex: function (index, data) {
        if (index < 0) return;
        this.ensureRowCount(index + 1);
        const row = getRows()[index];
        setRowData(row, data);
        updatePayload({ reason: 'sync-row-data', rowIndex: index });
      },
      syncLegalEntitySelectionsByRows: function (legalEntityRows) {
        getRows().forEach(function (row, index) {
          const select = row.querySelector('.proposal-object-legal-entity-short-name');
          if (!select) return;
          const legalEntityName = legalEntityRows[index]?.short_name || '';
          syncProposalLegalEntityNameSelect(select, form, legalEntityName);
          select.value = legalEntityName;
        });
        updatePayload({ reason: 'sync-legal-entity-selects' });
      },
    };
    form.__proposalObjectsTableApi = api;
    return api;
  }

  function attachProposalAssetsToLegalEntitiesSync(form, assetsApi, legalEntitiesApi) {
    if (!form || !assetsApi || !legalEntitiesApi) return;
    if (form.dataset.assetsLegalSyncBound === '1') return;
    form.dataset.assetsLegalSyncBound = '1';

    function syncRows(detail) {
      const rows = Array.isArray(detail?.rows) ? detail.rows : assetsApi.getSerializedRows();
      const meta = detail?.meta || {};

      legalEntitiesApi.ensureRowCount(rows.length);
      legalEntitiesApi.syncAssetSelectionsByRows(rows);

      if (meta.reason === 'autofill' && typeof meta.rowIndex === 'number' && rows[meta.rowIndex]) {
        legalEntitiesApi.setRowDataByIndex(meta.rowIndex, {
          asset_short_name: rows[meta.rowIndex].short_name || '',
          short_name: rows[meta.rowIndex].short_name || '',
          country_id: rows[meta.rowIndex].country_id || '',
          country_name: rows[meta.rowIndex].country_name || '',
          identifier: rows[meta.rowIndex].identifier || '',
          registration_number: rows[meta.rowIndex].registration_number || '',
          registration_date: rows[meta.rowIndex].registration_date || '',
          region: rows[meta.rowIndex].region || '',
        });
      }
    }

    form.addEventListener('proposal-assets-changed', function (event) {
      syncRows(event.detail || {});
    });

    syncRows();
  }

  function attachProposalLegalEntitiesToObjectsSync(form, legalEntitiesApi, objectsApi) {
    if (!form || !legalEntitiesApi || !objectsApi) return;
    if (form.dataset.legalEntitiesObjectsSyncBound === '1') return;
    form.dataset.legalEntitiesObjectsSyncBound = '1';

    function syncRows(detail) {
      const rows = Array.isArray(detail?.rows) ? detail.rows : legalEntitiesApi.getSerializedRows();
      const meta = detail?.meta || {};

      objectsApi.ensureRowCount(rows.length);
      objectsApi.syncLegalEntitySelectionsByRows(rows);

      if (meta.reason === 'autofill' && typeof meta.rowIndex === 'number' && rows[meta.rowIndex]) {
        objectsApi.setRowDataByIndex(meta.rowIndex, {
          legal_entity_short_name: rows[meta.rowIndex].short_name || '',
          short_name: rows[meta.rowIndex].short_name || '',
          region: rows[meta.rowIndex].region || '',
          object_type: rows[meta.rowIndex].identifier || '',
          license: rows[meta.rowIndex].registration_number || '',
          registration_date: rows[meta.rowIndex].registration_date || '',
        });
      }
    }

    form.addEventListener('proposal-legal-entities-changed', function (event) {
      syncRows(event.detail || {});
    });

    syncRows();
  }

  function attachProposalServicesStore(root) {
    if (!root) return null;
    const scope = getProposalScope(root);
    const form = getProposalOwningForm(scope) || scope;
    const stageKey = getProposalStageKey(scope);
    const commercialRoot = stageKey ? getProposalStageRootByKind(form, stageKey, 'commercial') : scope;
    const serviceRoot = stageKey ? getProposalStageRootByKind(form, stageKey, 'service') : scope;
    const commercialInput = commercialRoot?.querySelector('#proposal-commercial-offer-payload');
    const serviceInput = serviceRoot?.querySelector('#proposal-service-sections-payload');
    if (!commercialInput || !serviceInput) return null;
    if (stageKey) {
      form.__proposalStageServicesStores = form.__proposalStageServicesStores || {};
      if (form.__proposalStageServicesStores[stageKey]) return form.__proposalStageServicesStores[stageKey];
    } else if (form.__proposalServicesStore) {
      return form.__proposalServicesStore;
    }

    function parsePayload(input) {
      try {
        const data = JSON.parse(input?.value || '[]');
        return Array.isArray(data) ? data : [];
      } catch (error) {
        return [];
      }
    }

    function normalizeRow(row, options) {
      if (isProposalTravelExpensesRow(row)) {
        return normalizeProposalTravelExpensesRow(row);
      }
      const serviceName = String(row?.service_name || '').trim();
      const autofill = getProposalCommercialAutofill(scope, serviceName);
      const specialty = autofill.jobTitle || String(row?.job_title || '').trim();
      const forceAutofill = options?.forceAutofill === true;
      const specialistValue = String(row?.specialist || '').trim();
      const statusValue = String(row?.professional_status || '').trim();
      const specialist = forceAutofill ? autofill.specialist : (specialistValue || autofill.specialist);
      const specialistStatus = getProposalCommercialSpecialistStatus(scope, serviceName, specialist);
      const currentRate = String(row?.rate_eur_per_day || '').trim();
      const autofillRate = getProposalCommercialRateValue(scope, serviceName, specialist);
      const currentDayCounts = Array.isArray(row?.asset_day_counts)
        ? row.asset_day_counts.map(function (value) { return String(value ?? '').trim(); })
        : [];
      const autofillDayCounts = getProposalCommercialDayCounts(scope, serviceName, currentDayCounts, {
        replaceAll: forceAutofill,
      });
      return {
        specialist: specialist,
        job_title: specialty,
        professional_status: forceAutofill
          ? (specialistStatus || autofill.professionalStatus)
          : (statusValue || specialistStatus || autofill.professionalStatus),
        service_name: serviceName,
        code: getProposalTypicalSectionCode(scope, serviceName) || String(row?.code || '').trim(),
        rate_eur_per_day: forceAutofill ? (autofillRate || currentRate) : (currentRate || autofillRate),
        asset_day_counts: forceAutofill
          ? autofillDayCounts
          : (currentDayCounts.length ? currentDayCounts : autofillDayCounts),
        total_eur_without_vat: String(row?.total_eur_without_vat || '').trim(),
      };
    }

    function buildMergedRows() {
      const commercialRows = parsePayload(commercialInput);
      const serviceRows = parsePayload(serviceInput);
      const regularCommercialRows = commercialRows.filter(function (row) {
        return !isProposalTravelExpensesRow(row);
      });
      const travelRow = normalizeProposalTravelExpensesRow(
        commercialRows.find(isProposalTravelExpensesRow) || {}
      );
      const count = Math.max(regularCommercialRows.length, serviceRows.length);
      const rows = [];
      for (let index = 0; index < count; index += 1) {
        const commercialRow = regularCommercialRows[index] || {};
        const serviceRow = serviceRows[index] || {};
        rows.push(normalizeRow({
          ...commercialRow,
          service_name: serviceRow.service_name ?? commercialRow.service_name ?? '',
          code: serviceRow.code ?? commercialRow.code ?? '',
        }));
      }
      rows.push(travelRow);
      return rows;
    }

    let rows = buildMergedRows();
    const listeners = [];

    function serializeCommercialRows() {
      return rows.map(function (row) {
        return {
          specialist: row.specialist,
          job_title: row.job_title,
          professional_status: row.professional_status,
          service_name: row.service_name,
          rate_eur_per_day: row.rate_eur_per_day,
          asset_day_counts: row.asset_day_counts.slice(),
          total_eur_without_vat: row.total_eur_without_vat,
        };
      });
    }

    function serializeServiceRows() {
      return rows.filter(function (row) {
        return !isProposalTravelExpensesRow(row);
      }).map(function (row) {
        return {
          service_name: row.service_name,
          code: row.code,
        };
      });
    }

    function syncHiddenInputs() {
      commercialInput.value = JSON.stringify(serializeCommercialRows());
      serviceInput.value = JSON.stringify(serializeServiceRows());
    }

    function emit(meta) {
      const detail = {
        rows: api.getRows(),
        serviceRows: api.getServiceRows(),
        meta: meta || null,
      };
      const eventTargets = stageKey ? getProposalStageRoots(form, stageKey) : [form];
      eventTargets.forEach(function (target) {
        target.dispatchEvent(new CustomEvent('proposal-commercial-changed', { detail: detail }));
        target.dispatchEvent(new CustomEvent('proposal-service-sections-changed', {
          detail: {
            rows: detail.serviceRows,
            meta: meta || null,
          },
        }));
      });
      listeners.slice().forEach(function (listener) {
        listener(detail);
      });
    }

    const api = {
      getRows: function () {
        return rows.map(function (row) {
          return {
            ...row,
            asset_day_counts: row.asset_day_counts.slice(),
          };
        });
      },
      getServiceRows: function () {
        return serializeServiceRows().map(function (row) { return { ...row }; });
      },
      commitCommercialRows: function (nextRows, meta) {
        rows = (Array.isArray(nextRows) ? nextRows : []).map(normalizeRow);
        if (!rows.some(isProposalTravelExpensesRow)) {
          rows.push(normalizeProposalTravelExpensesRow({}));
        }
        syncHiddenInputs();
        emit(meta);
      },
      commitServiceRows: function (nextRows, meta) {
        const currentRows = api.getRows();
        const currentTravelRow = currentRows.find(isProposalTravelExpensesRow) || normalizeProposalTravelExpensesRow({});
        rows = (Array.isArray(nextRows) ? nextRows : []).map(function (row, index) {
          const currentRow = currentRows[index] || {};
          const nextServiceName = String(row?.service_name || '').trim();
          const currentServiceName = String(currentRow?.service_name || '').trim();
          return normalizeRow({
            ...currentRow,
            service_name: nextServiceName,
            code: row?.code || '',
          }, {
            forceAutofill: nextServiceName !== currentServiceName,
          });
        });
        rows.push(normalizeProposalTravelExpensesRow(currentTravelRow));
        syncHiddenInputs();
        emit(meta);
      },
      replaceFromType: function (meta) {
        api.commitServiceRows(
          getProposalTypicalSectionEntries(scope).map(function (entry) {
            return {
              service_name: (entry?.name || '').trim(),
              code: (entry?.code || '').trim(),
              exclude_from_tkp_autofill: !!entry?.exclude_from_tkp_autofill,
            };
          }).filter(function (entry) {
            return !!entry.service_name && !entry.exclude_from_tkp_autofill;
          }).map(function (entry) {
            return {
              service_name: entry.service_name,
              code: entry.code,
            };
          }),
          meta
        );
      },
      subscribe: function (listener) {
        if (typeof listener !== 'function') return function () {};
        listeners.push(listener);
        return function () {
          const index = listeners.indexOf(listener);
          if (index >= 0) listeners.splice(index, 1);
        };
      },
    };

    syncHiddenInputs();
    if (stageKey) {
      form.__proposalStageServicesStores[stageKey] = api;
    } else {
      form.__proposalServicesStore = api;
    }
    return api;
  }

  function attachProposalCommercialTable(root, assetsApi) {
    if (!root) return null;
    const scope = getProposalScope(root);
    const formRoot = getProposalOwningForm(scope) || scope;
    const form = scope;
    const isSummaryCommercialBlock = scope.dataset.proposalCommercialSummary === '1';
    const servicesStore = isSummaryCommercialBlock ? null : attachProposalServicesStore(scope);
    const serviceCostInput = formRoot.querySelector('[name="service_cost"]');
    const table = scope.querySelector('#proposal-commercial-table');
    const payloadInput = scope.querySelector('#proposal-commercial-offer-payload');
    const totalsPayloadInput = scope.querySelector('#proposal-commercial-totals-payload');
    const thead = scope.querySelector('#proposal-commercial-thead');
    const tbody = scope.querySelector('#proposal-commercial-tbody');
    const addBtn = scope.querySelector('#proposal-commercial-add-btn');
    const actions = scope.querySelector('#proposal-commercial-row-actions');
    const upBtn = scope.querySelector('#proposal-commercial-up-btn');
    const downBtn = scope.querySelector('#proposal-commercial-down-btn');
    const deleteBtn = scope.querySelector('#proposal-commercial-delete-btn');
    if (
      !table || !payloadInput || !totalsPayloadInput || !thead || !tbody
      || (!isSummaryCommercialBlock && (!addBtn || !actions || !upBtn || !downBtn || !deleteBtn))
    ) return null;
    if (scope.dataset.commercialBound === '1') return scope.__proposalCommercialTableApi || null;
    scope.dataset.commercialBound = '1';

    function hasVisibleSummaryCommercialBlock() {
      const summaryBlock = formRoot.querySelector('[data-proposal-commercial-summary="1"]');
      return !!summaryBlock && !summaryBlock.classList.contains('d-none');
    }

    function getStageCommercialBlocks() {
      return Array.from(
        formRoot.querySelectorAll('#proposal-commercial-stages-container [data-proposal-stage-kind="commercial"]')
      );
    }

    function getMasterCommercialBlock() {
      return getStageCommercialBlocks()[0] || null;
    }

    function isCommercialRateMasterBlock() {
      if (scope.dataset.proposalCommercialRateMaster === '1') return true;
      return !isSummaryCommercialBlock && getMasterCommercialBlock() === scope;
    }

    function shouldSyncServiceCost() {
      return isSummaryCommercialBlock ? hasVisibleSummaryCommercialBlock() : !hasVisibleSummaryCommercialBlock();
    }

    function readCommercialTotalsState(block) {
      try {
        return normalizeProposalCommercialTotalsState(
          JSON.parse(block?.querySelector('#proposal-commercial-totals-payload')?.value || '{}')
        );
      } catch (error) {
        return normalizeProposalCommercialTotalsState({});
      }
    }

    function getCommercialRateStateFromBlock(block) {
      if (!block) return null;
      const totalsState = readCommercialTotalsState(block);
      const rubTotalRow = block.querySelector('tr[data-rub-total-row="1"]');
      const rateInput = rubTotalRow?.querySelector('.proposal-commercial-rate');
      const serviceInput = rubTotalRow?.querySelector('.proposal-commercial-service-text');
      return {
        exchange_rate: rawMoney(rateInput?.value || totalsState.exchange_rate || ''),
        rub_total_service_text: String(serviceInput?.value || totalsState.rub_total_service_text || '').trim(),
      };
    }

    function getSharedCommercialRateState() {
      if (isCommercialRateMasterBlock()) return null;
      const masterBlock = getMasterCommercialBlock();
      if (!masterBlock || masterBlock === scope) return null;
      return getCommercialRateStateFromBlock(masterBlock);
    }

    function parsePayload() {
      if (servicesStore) return servicesStore.getRows();
      try {
        const data = JSON.parse(payloadInput.value || '[]');
        return Array.isArray(data) ? data : [];
      } catch (error) {
        return [];
      }
    }

    function getRows() {
      return Array.from(tbody.querySelectorAll('tr'));
    }

    function isSummaryRow(row) {
      return row?.dataset?.summaryRow === '1';
    }

    function isSummaryWithTravelRow(row) {
      return row?.dataset?.summaryWithTravelRow === '1';
    }

    function isRubTotalRow(row) {
      return row?.dataset?.rubTotalRow === '1';
    }

    function isDiscountedTotalRow(row) {
      return row?.dataset?.discountedTotalRow === '1';
    }

    function isContractTotalRow(row) {
      return row?.dataset?.contractTotalRow === '1';
    }

    function isTravelRow(row) {
      return row?.dataset?.travelExpensesRow === '1';
    }

    function isFixedRow(row) {
      return isTravelRow(row) || isSummaryRow(row) || isSummaryWithTravelRow(row) || isRubTotalRow(row) || isDiscountedTotalRow(row) || isContractTotalRow(row);
    }

    function getTravelExpensesMode(row) {
      return normalizeProposalTravelExpensesMode(row?.dataset?.travelExpensesMode) || PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL;
    }

    function parseTotalsPayload() {
      try {
        return normalizeProposalCommercialTotalsState(JSON.parse(totalsPayloadInput.value || '{}'));
      } catch (error) {
        return normalizeProposalCommercialTotalsState({});
      }
    }

    function setTotalsPayload(state) {
      totalsPayloadInput.value = JSON.stringify(normalizeProposalCommercialTotalsState(state));
    }

    function applySharedCommercialRateState() {
      const sharedState = getSharedCommercialRateState();
      if (!sharedState) return;
      const rubTotalRow = findFixedRow('tr[data-rub-total-row="1"]');
      const serviceInput = rubTotalRow?.querySelector('.proposal-commercial-service-text');
      const rateInput = rubTotalRow?.querySelector('.proposal-commercial-rate');
      if (serviceInput && document.activeElement !== serviceInput) {
        serviceInput.value = String(sharedState.rub_total_service_text || '').trim();
      }
      if (rateInput && document.activeElement !== rateInput) {
        rateInput.value = sharedState.exchange_rate
          ? formatProposalExchangeRateDisplay(sharedState.exchange_rate)
          : '';
      }
      const currentState = parseTotalsPayload();
      setTotalsPayload({
        ...currentState,
        exchange_rate: sharedState.exchange_rate,
        rub_total_service_text: String(sharedState.rub_total_service_text || '').trim(),
      });
    }

    function getDataRows() {
      return getRows().filter(function (row) {
        return !isFixedRow(row);
      });
    }

    function getEditableRows() {
      return getDataRows();
    }

    function getSelectedRows() {
      return getEditableRows().filter(function (row) {
        return !!row.querySelector('.proposal-commercial-check:checked');
      });
    }

    function getAssetRows() {
      return assetsApi ? assetsApi.getSerializedRows() : [];
    }

    function getAssetLabels(assetRows) {
      return assetRows.map(function (row, index) {
        return (row.short_name || '').trim() || ('Актив ' + (index + 1));
      });
    }

    let dayHeaderMeasureEl = null;

    function measureCommercialDayLabelWidth(label) {
      const text = String(label || '').trim();
      if (!text) return 0;
      if (!document?.body) return 0;
      if (!dayHeaderMeasureEl) {
        dayHeaderMeasureEl = document.createElement('span');
        dayHeaderMeasureEl.className = 'proposal-commercial-day-header';
        dayHeaderMeasureEl.style.position = 'absolute';
        dayHeaderMeasureEl.style.visibility = 'hidden';
        dayHeaderMeasureEl.style.pointerEvents = 'none';
        dayHeaderMeasureEl.style.whiteSpace = 'nowrap';
        dayHeaderMeasureEl.style.left = '-9999px';
        dayHeaderMeasureEl.style.top = '-9999px';
        document.body.appendChild(dayHeaderMeasureEl);
      }
      dayHeaderMeasureEl.textContent = text;
      return Math.ceil(dayHeaderMeasureEl.getBoundingClientRect().width);
    }

    function getCommercialDayColumnWidths(assetRows) {
      const labels = getAssetLabels(assetRows);
      if (labels.length <= 1) return [];
      return labels.map(function (label) {
        return measureCommercialDayLabelWidth(label) + 36;
      });
    }

    function applyCommercialDayColumnWidth(cell, widthPx) {
      if (!cell || !widthPx) return;
      cell.style.width = widthPx + 'px';
      cell.style.minWidth = widthPx + 'px';
      cell.style.maxWidth = widthPx + 'px';
    }

    function renderCommercialColGroup(assetRows) {
      let colgroup = table.querySelector('colgroup[data-proposal-commercial-cols]');
      if (!colgroup) {
        colgroup = document.createElement('colgroup');
        colgroup.setAttribute('data-proposal-commercial-cols', '1');
        table.insertBefore(colgroup, table.firstChild);
      }

      const dayWidths = getCommercialDayColumnWidths(assetRows);
      const cols = [];

      for (let i = 0; i < 5; i += 1) cols.push({});
      cols.push({ width: '10.5rem' });

      if (assetRows.length <= 1) {
        cols.push({ width: '10.5rem' });
      } else {
        dayWidths.forEach(function (widthPx) {
          cols.push({ widthPx: widthPx });
        });
      }

      cols.push({ width: '10.5rem' });

      colgroup.innerHTML = '';
      cols.forEach(function (config) {
        const col = document.createElement('col');
        if (config.width) {
          col.style.width = config.width;
          col.style.minWidth = config.width;
          col.style.maxWidth = config.width;
        }
        if (config.widthPx) {
          const value = config.widthPx + 'px';
          col.style.width = value;
          col.style.minWidth = value;
          col.style.maxWidth = value;
        }
        colgroup.appendChild(col);
      });
    }

    function renderHeader(assetRows) {
      const labels = getAssetLabels(assetRows);
      renderCommercialColGroup(assetRows);
      if (labels.length <= 1) {
        thead.innerHTML = ''
          + '<tr>'
          + '<th class="proposal-assets-check-col"></th>'
          + '<th>Специалист</th>'
          + '<th>Специальность</th>'
          + '<th>Профессиональный статус</th>'
          + '<th>Услуги</th>'
          + '<th class="proposal-commercial-rate-header">Ставка, евро / день</th>'
          + '<th class="proposal-commercial-days-group proposal-commercial-days-header proposal-commercial-days-header-single">Количество дней</th>'
          + '<th class="proposal-commercial-total-header">Итого, евро без НДС</th>'
          + '</tr>';
        return;
      }

      thead.innerHTML = ''
        + '<tr>'
        + '<th class="proposal-assets-check-col" rowspan="2"></th>'
        + '<th rowspan="2">Специалист</th>'
        + '<th rowspan="2">Специальность</th>'
        + '<th rowspan="2">Профессиональный статус</th>'
        + '<th rowspan="2">Услуги</th>'
        + '<th class="proposal-commercial-rate-header" rowspan="2">Ставка, евро / день</th>'
        + '<th class="proposal-commercial-days-group proposal-commercial-days-group-subheaders proposal-commercial-days-header proposal-commercial-days-header-multi" colspan="' + labels.length + '">Количество дней</th>'
        + '<th class="proposal-commercial-total-header" rowspan="2">Итого, евро без НДС</th>'
        + '</tr>'
        + '<tr>'
        + labels.map(function (label) {
          return '<th class="proposal-commercial-day-header">' + escapeHtml(label) + '</th>';
        }).join('')
        + '</tr>';

      const widths = getCommercialDayColumnWidths(assetRows);
      Array.from(thead.querySelectorAll('.proposal-commercial-day-header')).forEach(function (header, index) {
        applyCommercialDayColumnWidth(header, widths[index]);
      });
    }

    function syncActions() {
      const hasSelected = getSelectedRows().length > 0;
      if (isSummaryCommercialBlock) {
        if (upBtn) upBtn.disabled = !hasSelected;
        if (downBtn) downBtn.disabled = !hasSelected;
        return;
      }
      actions.classList.toggle('d-none', !hasSelected);
      actions.classList.toggle('d-flex', hasSelected);
    }

    function getDayInputs(row) {
      return Array.from(row.querySelectorAll('.proposal-commercial-day-count'));
    }

    function recalcRowTotal(row) {
      if (!row) return;
      if (isFixedRow(row)) return;
      const rateInput = row.querySelector('.proposal-commercial-rate');
      const totalInput = row.querySelector('.proposal-commercial-total');
      if (!rateInput || !totalInput) return;

      const rate = parseFloat(rawMoney(rateInput.value || ''));
      const totalDays = getDayInputs(row).reduce(function (sum, input) {
        const value = parseInt((input.value || '').trim(), 10);
        return sum + (Number.isFinite(value) ? value : 0);
      }, 0);

      if (!Number.isFinite(rate) || totalDays <= 0) {
        totalInput.value = '';
        return;
      }

      totalInput.value = fmtMoney((rate * totalDays).toFixed(2));
    }

    function recalcTravelRowTotal(row) {
      if (!row || !isTravelRow(row)) return;
      const totalInput = row.querySelector('.proposal-commercial-total');
      if (!totalInput) return;
      if (getTravelExpensesMode(row) !== PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION) {
        const preservedRaw = rawMoney(row.dataset.preservedActualTotalRaw || '');
        totalInput.value = preservedRaw ? fmtMoney(preservedRaw) : '';
        return;
      }
      const total = getDayInputs(row).reduce(function (sum, input) {
        const value = parseFloat(rawMoney(input.value || ''));
        return sum + (Number.isFinite(value) ? value : 0);
      }, 0);
      totalInput.value = total > 0 ? fmtMoney(total.toFixed(2)) : '';
    }

    function syncCalculatedRowTotal(row) {
      if (isTravelRow(row)) {
        recalcTravelRowTotal(row);
        return;
      }
      recalcRowTotal(row);
    }

    function syncDayCells(row, assetRows, values, options) {
      const isTravelExpenses = isTravelRow(row);
      const isReadOnly = options?.readOnly === true
        || (isTravelExpenses && getTravelExpensesMode(row) !== PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION);
      let sourceValues = Array.isArray(values) ? values : getDayInputs(row).map(function (input) { return input.value || ''; });
      const dayColumnWidths = getCommercialDayColumnWidths(assetRows);
      row.querySelectorAll('.proposal-commercial-day-cell, .proposal-commercial-day-placeholder-cell').forEach(function (cell) {
        cell.remove();
      });

      const totalCell = row.querySelector('.proposal-commercial-total-cell');
      if (!totalCell) return;

      if (!assetRows.length) {
        const placeholderCell = createProposalTableCell('proposal-commercial-day-placeholder-cell');
        placeholderCell.textContent = '—';
        row.insertBefore(placeholderCell, totalCell);
        syncCalculatedRowTotal(row);
        return;
      }

      if (isTravelExpenses && getTravelExpensesMode(row) !== PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION) {
        sourceValues = Array.from({ length: assetRows.length }, function () { return ''; });
      }

      assetRows.forEach(function (_assetRow, index) {
        const dayCell = createProposalTableCell(
          'proposal-commercial-day-cell' + (assetRows.length === 1 ? ' proposal-commercial-day-cell-single' : '')
        );
        applyCommercialDayColumnWidth(dayCell, dayColumnWidths[index]);
        const input = document.createElement('input');
        if (isTravelExpenses) {
          input.type = 'text';
          input.inputMode = 'decimal';
          input.dataset.moneyPrecision = '2';
          input.className = 'form-control js-money-input proposal-commercial-day-count proposal-commercial-travel-amount';
        } else {
          input.type = 'number';
          input.min = '0';
          input.step = '1';
          input.className = 'form-control proposal-commercial-day-count';
        }
        input.value = sourceValues[index] ?? '';
        if (isReadOnly) {
          input.readOnly = true;
          input.tabIndex = -1;
          input.classList.add('readonly-field');
        }
        if (dayColumnWidths[index]) {
          input.style.width = '100%';
          input.style.minWidth = '0';
          input.style.maxWidth = '100%';
          input.style.boxSizing = 'border-box';
        } else {
          input.style.width = '100%';
          input.style.minWidth = '0';
          input.style.maxWidth = '100%';
          input.style.boxSizing = 'border-box';
        }
        if (!isReadOnly) {
          input.addEventListener('change', function () {
            syncCalculatedRowTotal(row);
            updatePayload();
          });
          input.addEventListener('input', function () {
            syncCalculatedRowTotal(row);
            updatePayload();
          });
        }
        dayCell.appendChild(input);
        row.insertBefore(dayCell, totalCell);
      });

      if (isTravelExpenses) attachMoneyInputs(row);
      if (!isReadOnly) syncCalculatedRowTotal(row);
    }

    function serializeRow(row) {
      if (isSummaryRow(row) || isSummaryWithTravelRow(row) || isRubTotalRow(row) || isDiscountedTotalRow(row) || isContractTotalRow(row)) {
        return null;
      }
      if (isTravelRow(row)) {
        return {
          specialist: '',
          job_title: '',
          professional_status: '',
          service_name: PROPOSAL_TRAVEL_EXPENSES_LABEL,
          rate_eur_per_day: '',
          asset_day_counts: getDayInputs(row).map(function (input) { return (input.value || '').trim(); }),
          total_eur_without_vat: rawMoney(row.querySelector('.proposal-commercial-total')?.value || ''),
        };
      }
      return {
        specialist: (row.querySelector('.proposal-commercial-specialist')?.value || '').trim(),
        job_title: (row.querySelector('.proposal-commercial-job-title')?.value || '').trim(),
        professional_status: (row.querySelector('.proposal-commercial-status')?.value || '').trim(),
        service_name: (row.querySelector('.proposal-commercial-service')?.value || '').trim(),
        rate_eur_per_day: rawMoney(row.querySelector('.proposal-commercial-rate')?.value || ''),
        asset_day_counts: getDayInputs(row).map(function (input) { return (input.value || '').trim(); }),
        total_eur_without_vat: rawMoney(row.querySelector('.proposal-commercial-total')?.value || ''),
      };
    }

    function computeSummaryValues() {
      const dataRows = getDataRows();
      const assetCount = Math.max(getAssetRows().length, 1);
      const dayCounts = Array.from({ length: assetCount }, function () { return 0; });
      let total = 0;

      dataRows.forEach(function (row) {
        getDayInputs(row).forEach(function (input, index) {
          const value = parseInt((input.value || '').trim(), 10);
          if (Number.isFinite(value)) dayCounts[index] += value;
        });
        const rowTotal = parseFloat(rawMoney(row.querySelector('.proposal-commercial-total')?.value || ''));
        if (Number.isFinite(rowTotal)) total += rowTotal;
      });

      return {
        asset_day_counts: dayCounts.map(function (value) { return value > 0 ? String(value) : ''; }),
        total_eur_without_vat: total > 0 ? fmtMoney(total.toFixed(2)) : '',
      };
    }

    function computeTravelRowTotalValue() {
      const travelRow = tbody.querySelector('tr[data-travel-expenses-row="1"]');
      if (!travelRow) return 0;
      return getDayInputs(travelRow).reduce(function (sum, input) {
        const value = parseFloat(rawMoney(input.value || ''));
        return sum + (Number.isFinite(value) ? value : 0);
      }, 0);
    }

    function findFixedRow(selector) {
      return tbody.querySelector(selector);
    }

    function createReadOnlyDayValues() {
      return Array.from({ length: Math.max(getAssetRows().length, 1) }, function () { return ''; });
    }

    function syncFinancialServiceCellExpansion(row) {
      const labelCell = row?.querySelector('.proposal-commercial-financial-label-cell');
      const serviceCell = row?.querySelector('.proposal-commercial-financial-service-cell');
      const serviceInput = row?.querySelector('.proposal-commercial-service-text');
      if (!labelCell || !serviceCell || !serviceInput) return;

      const spanVariants = [
        { labelColSpan: 4, serviceColSpan: 1 },
        { labelColSpan: 3, serviceColSpan: 2 },
        { labelColSpan: 2, serviceColSpan: 3 },
      ];

      for (let index = 0; index < spanVariants.length; index += 1) {
        const variant = spanVariants[index];
        labelCell.colSpan = variant.labelColSpan;
        serviceCell.colSpan = variant.serviceColSpan;
        row.dataset.financialServiceExpansionLevel = String(index);
        const hasOverflow = (serviceInput.scrollWidth - serviceInput.clientWidth) > 1;
        if (!hasOverflow || index === spanVariants.length - 1) {
          break;
        }
      }
    }

    function syncAllFinancialServiceCellExpansions() {
      tbody.querySelectorAll('tr.proposal-commercial-financial-row').forEach(function (row) {
        syncFinancialServiceCellExpansion(row);
      });
    }

    function computeCommercialFinancialTotals() {
      applySharedCommercialRateState();
      const summaryTotal = parseFloat(rawMoney(
        findFixedRow('tr[data-summary-with-travel-row="1"]')?.querySelector('.proposal-commercial-total')?.value
        || findFixedRow('tr[data-summary-row="1"]')?.querySelector('.proposal-commercial-total')?.value
        || ''
      ));
      const totalsState = parseTotalsPayload();
      const exchangeRate = parseFloat(rawMoney(findFixedRow('tr[data-rub-total-row="1"]')?.querySelector('.proposal-commercial-rate')?.value || totalsState.exchange_rate || ''));
      const discountPercent = parseProposalPercent(findFixedRow('tr[data-discounted-total-row="1"]')?.querySelector('.proposal-commercial-rate')?.value || totalsState.discount_percent || '');
      const rubTotal = Number.isFinite(summaryTotal) && Number.isFinite(exchangeRate) ? summaryTotal * exchangeRate : null;
      const discountedRubTotal = Number.isFinite(rubTotal)
        ? (rubTotal - (rubTotal * ((discountPercent || 0) / 100)))
        : null;
      const autoContractTotal = Number.isFinite(discountedRubTotal)
        ? roundProposalToHundredThousand(discountedRubTotal)
        : '';

      return {
        exchange_rate: Number.isFinite(exchangeRate) ? rawMoney(exchangeRate) : totalsState.exchange_rate,
        discount_percent: Number.isFinite(discountPercent) ? String(discountPercent) : totalsState.discount_percent,
        rub_total: Number.isFinite(rubTotal) ? fmtMoney(rubTotal.toFixed(2)) : '',
        discounted_rub_total: Number.isFinite(discountedRubTotal) ? fmtMoney(discountedRubTotal.toFixed(2)) : '',
        auto_contract_total: autoContractTotal,
        rub_total_service_text: String(findFixedRow('tr[data-rub-total-row="1"]')?.querySelector('.proposal-commercial-service-text')?.value || totalsState.rub_total_service_text || '').trim(),
        discounted_total_service_text: String(findFixedRow('tr[data-discounted-total-row="1"]')?.querySelector('.proposal-commercial-service-text')?.value || totalsState.discounted_total_service_text || '').trim(),
      };
    }

    function syncSummaryRowValues() {
      const summaryRow = tbody.querySelector('tr[data-summary-row="1"]');
      if (!summaryRow) return;
      const summary = computeSummaryValues();
      syncDayCells(summaryRow, getAssetRows(), summary.asset_day_counts, { readOnly: true });
      const totalInput = summaryRow.querySelector('.proposal-commercial-total');
      if (totalInput) totalInput.value = summary.total_eur_without_vat;
    }

    function syncSummaryWithTravelRowValues() {
      const summaryWithTravelRow = tbody.querySelector('tr[data-summary-with-travel-row="1"]');
      if (!summaryWithTravelRow) return;
      const summaryTotal = parseFloat(rawMoney(computeSummaryValues().total_eur_without_vat || ''));
      const travelTotal = computeTravelRowTotalValue();
      const total = (Number.isFinite(summaryTotal) ? summaryTotal : 0) + travelTotal;
      syncDayCells(summaryWithTravelRow, getAssetRows(), createReadOnlyDayValues(), { readOnly: true });
      const totalInput = summaryWithTravelRow.querySelector('.proposal-commercial-total');
      if (totalInput) totalInput.value = total > 0 ? fmtMoney(total.toFixed(2)) : '';
    }

    function syncServiceCostValue(valueRaw) {
      if (!shouldSyncServiceCost()) return;
      if (!serviceCostInput || document.activeElement === serviceCostInput) return;
      serviceCostInput.value = valueRaw ? fmtMoney(valueRaw) : '';
    }

    function syncCommercialFinancialRows() {
      const totals = computeCommercialFinancialTotals();
      const rubTotalRow = findFixedRow('tr[data-rub-total-row="1"]');
      const discountedRow = findFixedRow('tr[data-discounted-total-row="1"]');
      const contractRow = findFixedRow('tr[data-contract-total-row="1"]');
      const currentState = parseTotalsPayload();

      if (rubTotalRow) {
        syncDayCells(rubTotalRow, getAssetRows(), createReadOnlyDayValues(), { readOnly: true });
        const rateInput = rubTotalRow.querySelector('.proposal-commercial-rate');
        if (rateInput && document.activeElement !== rateInput) rateInput.value = formatProposalExchangeRateDisplay(totals.exchange_rate);
        const totalInput = rubTotalRow.querySelector('.proposal-commercial-total');
        if (totalInput) totalInput.value = totals.rub_total;
      }

      if (discountedRow) {
        syncDayCells(discountedRow, getAssetRows(), createReadOnlyDayValues(), { readOnly: true });
        const rateInput = discountedRow.querySelector('.proposal-commercial-rate');
        if (rateInput) rateInput.value = formatProposalPercentDisplay(totals.discount_percent);
        const totalInput = discountedRow.querySelector('.proposal-commercial-total');
        if (totalInput) totalInput.value = totals.discounted_rub_total;
      }

      let contractValueRaw = rawMoney(contractRow?.querySelector('.proposal-commercial-total')?.value || currentState.contract_total || '');
      const previousAutoRaw = rawMoney(currentState.contract_total_auto || contractRow?.dataset?.autoValue || '');
      const nextAutoRaw = rawMoney(totals.auto_contract_total || '');
      const manualOverride = contractRow?.dataset?.manualContractOverride === '1';
      const numericContractValue = parseFloat(contractValueRaw || '');
      if (!manualOverride || !contractValueRaw || contractValueRaw === previousAutoRaw || (!Number.isNaN(numericContractValue) && numericContractValue === 0)) {
        contractValueRaw = nextAutoRaw;
      }

      if (contractRow) {
        syncDayCells(contractRow, getAssetRows(), createReadOnlyDayValues(), { readOnly: true });
        const totalInput = contractRow.querySelector('.proposal-commercial-total');
        if (totalInput) totalInput.value = contractValueRaw ? fmtMoney(contractValueRaw) : '';
        contractRow.dataset.autoValue = nextAutoRaw;
        contractRow.dataset.manualContractOverride = manualOverride && contractValueRaw && contractValueRaw !== nextAutoRaw ? '1' : '0';
      }

      syncServiceCostValue(contractValueRaw);

      setTotalsPayload({
        exchange_rate: totals.exchange_rate,
        discount_percent: totals.discount_percent,
        contract_total: contractValueRaw,
        contract_total_auto: nextAutoRaw,
        rub_total_service_text: totals.rub_total_service_text,
        discounted_total_service_text: totals.discounted_total_service_text,
        travel_expenses_mode: getTravelExpensesMode(findFixedRow('tr[data-travel-expenses-row="1"]')),
      });
      syncAllFinancialServiceCellExpansions();
      if (isCommercialRateMasterBlock()) {
        formRoot.dispatchEvent(new CustomEvent('proposal-commercial-shared-rate-changed', {
          detail: getCommercialRateStateFromBlock(scope),
        }));
      }
    }

    function updatePayload(meta) {
      recalcTravelRowTotal(tbody.querySelector('tr[data-travel-expenses-row="1"]'));
      const rows = getRows().map(serializeRow).filter(Boolean);
      syncSummaryRowValues();
      syncSummaryWithTravelRowValues();
      syncCommercialFinancialRows();
      syncActions();
      if (servicesStore) {
        servicesStore.commitCommercialRows(rows, { ...(meta || {}), source: 'commercial-view' });
        return;
      }
      payloadInput.value = JSON.stringify(rows);
      form.dispatchEvent(new CustomEvent('proposal-commercial-changed', { detail: { rows: rows, meta: meta || null } }));
    }

    function setRowData(row, data) {
      if (!row || !data) return;
      const specialist = row.querySelector('.proposal-commercial-specialist');
      const jobTitle = row.querySelector('.proposal-commercial-job-title');
      const status = row.querySelector('.proposal-commercial-status');
      const service = row.querySelector('.proposal-commercial-service');
      const rate = row.querySelector('.proposal-commercial-rate');
      const total = row.querySelector('.proposal-commercial-total');
      if (specialist) {
        syncProposalCommercialSpecialistSelect(specialist, form, data.service_name || '', data.specialist || '');
        specialist.value = data.specialist || '';
      }
      if (jobTitle) jobTitle.value = data.job_title || getProposalTypicalSectionPrimaryExecutor(form, data.service_name || '');
      if (status) status.value = data.professional_status || '';
      if (service) {
        syncProposalCommercialServiceSelect(service, form, data.service_name || '');
        service.value = data.service_name || '';
      }
      if (rate) rate.value = data.rate_eur_per_day ? fmtMoney(data.rate_eur_per_day) : '';
      if (total) total.value = data.total_eur_without_vat ? fmtMoney(data.total_eur_without_vat) : '';
      syncDayCells(row, getAssetRows(), data.asset_day_counts || [], { readOnly: isSummaryCommercialBlock });
      recalcRowTotal(row);
    }

    function createRow(data) {
      const row = document.createElement('tr');
      const autofill = getProposalCommercialAutofill(form, data.service_name || '');

      const checkTd = createProposalTableCell('proposal-asset-check-cell');
      const checkWrap = document.createElement('div');
      checkWrap.className = 'form-check proposal-asset-check-wrap';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'form-check-input proposal-commercial-check';
      checkbox.style.margin = '0';
      checkbox.style.float = 'none';
      checkbox.addEventListener('change', syncActions);
      checkWrap.appendChild(checkbox);
      checkTd.appendChild(checkWrap);
      row.appendChild(checkTd);

      const specialistTd = createProposalTableCell();
      const specialistSelect = document.createElement('select');
      specialistSelect.className = 'form-select proposal-commercial-specialist';
      syncProposalCommercialSpecialistSelect(
        specialistSelect,
        form,
        data.service_name || '',
        data.specialist || autofill.specialist || ''
      );
      specialistSelect.value = data.specialist || autofill.specialist || '';
      if (isSummaryCommercialBlock) {
        specialistSelect.disabled = true;
        specialistSelect.tabIndex = -1;
        specialistSelect.classList.add('readonly-field');
      }
      specialistTd.appendChild(specialistSelect);
      row.appendChild(specialistTd);

      const titleTd = createProposalTableCell();
      const titleInput = document.createElement('input');
      titleInput.type = 'text';
      titleInput.className = 'form-control proposal-commercial-job-title readonly-field';
      titleInput.readOnly = true;
      titleInput.tabIndex = -1;
      titleInput.value = data.job_title || autofill.jobTitle || '';
      titleTd.appendChild(titleInput);
      row.appendChild(titleTd);

      const statusTd = createProposalTableCell();
      const statusInput = document.createElement('input');
      statusInput.type = 'text';
      statusInput.className = 'form-control proposal-commercial-status';
      statusInput.value = data.professional_status
        || getProposalCommercialSpecialistStatus(
          form,
          data.service_name || '',
          data.specialist || autofill.specialist || ''
        )
        || autofill.professionalStatus
        || '';
      if (isSummaryCommercialBlock) {
        statusInput.readOnly = true;
        statusInput.tabIndex = -1;
        statusInput.classList.add('readonly-field');
      }
      statusTd.appendChild(statusInput);
      row.appendChild(statusTd);

      const serviceTd = createProposalTableCell();
      let serviceSelect = null;
      if (isSummaryCommercialBlock) {
        const serviceInput = document.createElement('input');
        serviceInput.type = 'text';
        serviceInput.className = 'form-control proposal-commercial-service readonly-field';
        serviceInput.readOnly = true;
        serviceInput.tabIndex = -1;
        serviceInput.value = '';
        serviceTd.appendChild(serviceInput);
      } else {
        serviceSelect = document.createElement('select');
        serviceSelect.className = 'form-select proposal-commercial-service';
        syncProposalCommercialServiceSelect(serviceSelect, form, data.service_name || '');
        serviceSelect.value = data.service_name || '';
        serviceTd.appendChild(serviceSelect);
        serviceSelect.addEventListener('change', function () {
          const serviceAutofill = getProposalCommercialAutofill(form, serviceSelect.value || '');
          titleInput.value = serviceAutofill.jobTitle || '';
          syncProposalCommercialSpecialistSelect(
            specialistSelect,
            form,
            serviceSelect.value || '',
            serviceAutofill.specialist || ''
          );
          specialistSelect.value = serviceAutofill.specialist || '';
          statusInput.value = getProposalCommercialSpecialistStatus(
            form,
            serviceSelect.value || '',
            specialistSelect.value || ''
          ) || serviceAutofill.professionalStatus || '';
          const rateValue = getProposalCommercialRateValue(
            form,
            serviceSelect.value || '',
            specialistSelect.value || ''
          );
          rateInput.value = rateValue ? fmtMoney(rateValue) : '';
          syncDayCells(
            row,
            getAssetRows(),
            getProposalCommercialDayCounts(
              form,
              serviceSelect.value || '',
              getDayInputs(row).map(function (input) { return input.value || ''; }),
              { replaceAll: true }
            )
          );
          recalcRowTotal(row);
          updatePayload({ reason: 'row-edit', rowIndex: getRows().indexOf(row) });
        });
        serviceSelect.addEventListener('input', function () {
          if (!serviceSelect.value) {
            updatePayload({ reason: 'commercial-field-edit', rowIndex: getRows().indexOf(row) });
          }
        });
      }
      row.appendChild(serviceTd);

      const rateTd = createProposalTableCell('proposal-commercial-rate-cell');
      const rateInput = document.createElement('input');
      rateInput.type = 'text';
      rateInput.className = 'form-control js-money-input proposal-commercial-rate';
      rateInput.inputMode = 'decimal';
      rateInput.value = data.rate_eur_per_day ? fmtMoney(data.rate_eur_per_day) : '';
      if (isSummaryCommercialBlock) {
        rateInput.readOnly = true;
        rateInput.tabIndex = -1;
        rateInput.classList.add('readonly-field');
      }
      rateTd.appendChild(rateInput);
      row.appendChild(rateTd);

      const totalTd = createProposalTableCell('proposal-commercial-total-cell proposal-commercial-total-value-cell');
      const totalInput = document.createElement('input');
      totalInput.type = 'text';
      totalInput.className = 'form-control js-money-input proposal-commercial-total readonly-field';
      totalInput.inputMode = 'decimal';
      totalInput.readOnly = true;
      totalInput.tabIndex = -1;
      totalInput.value = data.total_eur_without_vat ? fmtMoney(data.total_eur_without_vat) : '';
      totalTd.appendChild(totalInput);
      row.appendChild(totalTd);

      syncDayCells(row, getAssetRows(), data.asset_day_counts || [], { readOnly: isSummaryCommercialBlock });

      [statusInput].forEach(function (input) {
        if (isSummaryCommercialBlock) return;
        input.addEventListener('change', function () {
          updatePayload({ reason: 'commercial-field-edit', rowIndex: getRows().indexOf(row) });
        });
      });
      if (!isSummaryCommercialBlock) {
        statusInput.addEventListener('input', function () {
          updatePayload({ reason: 'commercial-field-edit', rowIndex: getRows().indexOf(row) });
        });
        specialistSelect.addEventListener('change', function () {
          const specialistStatus = getProposalCommercialSpecialistStatus(
            form,
            serviceSelect.value || '',
            specialistSelect.value || ''
          );
          const rateValue = getProposalCommercialRateValue(
            form,
            serviceSelect.value || '',
            specialistSelect.value || ''
          );
          if (specialistStatus) {
            statusInput.value = specialistStatus;
          } else if (!(specialistSelect.value || '').trim()) {
            statusInput.value = '';
          }
          if (rateValue) {
            rateInput.value = fmtMoney(rateValue);
            recalcRowTotal(row);
          }
          updatePayload({ reason: 'commercial-field-edit', rowIndex: getRows().indexOf(row) });
        });
        rateInput.addEventListener('change', function () {
          recalcRowTotal(row);
          updatePayload({ reason: 'commercial-field-edit', rowIndex: getRows().indexOf(row) });
        });
        rateInput.addEventListener('input', function () {
          recalcRowTotal(row);
          updatePayload({ reason: 'commercial-field-edit', rowIndex: getRows().indexOf(row) });
        });
      }

      attachMoneyInputs(row);
      recalcRowTotal(row);
      return row;
    }

    function createTravelExpensesRow(data, mode) {
      const row = document.createElement('tr');
      row.dataset.travelExpensesRow = '1';
      row.dataset.travelExpensesMode = normalizeProposalTravelExpensesMode(mode) || PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL;
      row.dataset.preservedActualTotalRaw = rawMoney(data?.total_eur_without_vat || '');
      row.className = 'proposal-commercial-travel-row';

      const labelTd = createProposalTableCell('proposal-commercial-travel-label-cell');
      labelTd.colSpan = 5;
      labelTd.appendChild(createProposalEllipsisLabel(PROPOSAL_TRAVEL_EXPENSES_LABEL));
      row.appendChild(labelTd);

      const rateTd = createProposalTableCell('proposal-commercial-rate-cell proposal-commercial-travel-rate-cell');
      const rateSelect = document.createElement('select');
      rateSelect.className = 'form-select proposal-commercial-rate proposal-commercial-travel-mode';
      [
        { value: PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL, label: 'по факту' },
        { value: PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION, label: 'расчёт' },
      ].forEach(function (optionConfig) {
        const option = document.createElement('option');
        option.value = optionConfig.value;
        option.textContent = optionConfig.label;
        rateSelect.appendChild(option);
      });
      rateSelect.value = getTravelExpensesMode(row);
      if (isSummaryCommercialBlock) {
        rateSelect.disabled = true;
        rateSelect.tabIndex = -1;
        rateSelect.classList.add('readonly-field');
      }
      rateTd.appendChild(rateSelect);
      row.appendChild(rateTd);

      const totalTd = createProposalTableCell('proposal-commercial-total-cell proposal-commercial-total-value-cell');
      const totalInput = document.createElement('input');
      totalInput.type = 'text';
      totalInput.className = 'form-control proposal-commercial-total readonly-field';
      totalInput.inputMode = 'decimal';
      totalInput.readOnly = true;
      totalInput.tabIndex = -1;
      totalTd.appendChild(totalInput);
      row.appendChild(totalTd);

      syncDayCells(row, getAssetRows(), data.asset_day_counts || [], { readOnly: isSummaryCommercialBlock });

      if (!isSummaryCommercialBlock) {
        rateSelect.addEventListener('change', function () {
          row.dataset.travelExpensesMode = normalizeProposalTravelExpensesMode(rateSelect.value) || PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL;
          if (getTravelExpensesMode(row) === PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL) {
            row.dataset.preservedActualTotalRaw = '';
          }
          const nextValues = getTravelExpensesMode(row) === PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION
            ? getDayInputs(row).map(function (input) { return input.value || ''; })
            : [];
          syncDayCells(row, getAssetRows(), nextValues);
          recalcTravelRowTotal(row);
          updatePayload({ reason: 'travel-expenses-mode-change' });
        });
      }

      attachMoneyInputs(row);
      recalcTravelRowTotal(row);
      return row;
    }

    function createSummaryRow() {
      const row = document.createElement('tr');
      row.dataset.summaryRow = '1';
      row.className = 'proposal-commercial-summary-row';

      const labelTd = createProposalTableCell('proposal-commercial-summary-label-cell');
      labelTd.colSpan = 5;
      labelTd.appendChild(createProposalEllipsisLabel(PROPOSAL_SUMMARY_TOTAL_LABEL));
      row.appendChild(labelTd);

      const rateTd = createProposalTableCell('proposal-commercial-rate-cell proposal-commercial-summary-rate-cell');
      const rateInput = document.createElement('input');
      rateInput.type = 'text';
      rateInput.className = 'form-control proposal-commercial-rate readonly-field';
      rateInput.value = '';
      rateInput.readOnly = true;
      rateInput.tabIndex = -1;
      rateTd.appendChild(rateInput);
      row.appendChild(rateTd);

      const totalTd = createProposalTableCell('proposal-commercial-total-cell proposal-commercial-total-value-cell');
      const totalInput = document.createElement('input');
      totalInput.type = 'text';
      totalInput.className = 'form-control proposal-commercial-total readonly-field';
      totalInput.readOnly = true;
      totalInput.tabIndex = -1;
      totalTd.appendChild(totalInput);
      row.appendChild(totalTd);

      syncDayCells(row, getAssetRows(), [], { readOnly: true });
      return row;
    }

    function createSummaryWithTravelRow() {
      const row = document.createElement('tr');
      row.dataset.summaryWithTravelRow = '1';
      row.className = 'proposal-commercial-travel-row proposal-commercial-summary-with-travel-row';

      const labelTd = createProposalTableCell('proposal-commercial-travel-label-cell');
      labelTd.colSpan = 5;
      labelTd.appendChild(createProposalEllipsisLabel(PROPOSAL_SUMMARY_WITH_TRAVEL_TOTAL_LABEL));
      row.appendChild(labelTd);

      const rateTd = createProposalTableCell('proposal-commercial-rate-cell proposal-commercial-travel-rate-cell');
      const rateInput = document.createElement('input');
      rateInput.type = 'text';
      rateInput.className = 'form-control proposal-commercial-rate readonly-field';
      rateInput.value = '';
      rateInput.readOnly = true;
      rateInput.tabIndex = -1;
      rateTd.appendChild(rateInput);
      row.appendChild(rateTd);

      const totalTd = createProposalTableCell('proposal-commercial-total-cell proposal-commercial-total-value-cell');
      const totalInput = document.createElement('input');
      totalInput.type = 'text';
      totalInput.className = 'form-control proposal-commercial-total readonly-field';
      totalInput.readOnly = true;
      totalInput.tabIndex = -1;
      totalTd.appendChild(totalInput);
      row.appendChild(totalTd);

      syncDayCells(row, getAssetRows(), createReadOnlyDayValues(), { readOnly: true });
      return row;
    }

    function createFinancialTotalRow(config, state) {
      const row = document.createElement('tr');
      row.className = config.rowClass;
      row.dataset[config.rowDataset] = '1';

      const labelTd = createProposalTableCell('proposal-commercial-financial-label-cell');
      labelTd.colSpan = config.serviceEditable ? 4 : 5;
      labelTd.appendChild(createProposalEllipsisLabel(config.label));
      row.appendChild(labelTd);

      if (config.serviceEditable) {
        const serviceTd = createProposalTableCell('proposal-commercial-financial-service-cell');
        serviceTd.colSpan = 1;
        const serviceWrap = document.createElement('div');
        serviceWrap.className = 'proposal-commercial-financial-service-wrap';
        if (config.showCbrLink && isCommercialRateMasterBlock()) {
          const serviceActions = document.createElement('div');
          serviceActions.className = 'proposal-commercial-service-actions';
          const serviceLink = document.createElement('a');
          serviceLink.className = 'proposal-commercial-service-action proposal-commercial-service-link';
          serviceLink.href = PROPOSAL_CBR_EUR_DAILY_URL;
          serviceLink.target = '_blank';
          serviceLink.rel = 'noreferrer noopener';
          serviceLink.title = 'Открыть официальный курс евро Банка России';
          serviceLink.setAttribute('aria-label', 'Открыть официальный курс евро Банка России');
          serviceLink.innerHTML = '<i class="bi bi-globe2" aria-hidden="true"></i>';
          serviceActions.appendChild(serviceLink);

          const refreshBtn = document.createElement('button');
          refreshBtn.type = 'button';
          refreshBtn.className = 'proposal-commercial-service-action proposal-commercial-service-refresh';
          refreshBtn.title = 'Обновить курс Банка России на текущую дату';
          refreshBtn.setAttribute('aria-label', 'Обновить курс Банка России на текущую дату');
          refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise" aria-hidden="true"></i>';
          refreshBtn.addEventListener('click', async function () {
            const refreshUrl = form.dataset.cbrRateRefreshUrl || '';
            if (!refreshUrl || refreshBtn.disabled) return;
            document.documentElement.classList.add('proposal-progress-cursor');
            refreshBtn.classList.add('is-loading');
            refreshBtn.disabled = true;
            try {
              const response = await fetch(refreshUrl, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
              });
              if (!response.ok) throw new Error('Failed to refresh CBR EUR rate');
              const payload = await response.json();
              if (!payload || payload.ok !== true) throw new Error('Empty CBR EUR rate payload');
              serviceInput.value = String(payload.rub_total_service_text || getProposalCbrRateText()).trim();
              const rubTotalRateInput = row.querySelector('.proposal-commercial-rate');
              if (rubTotalRateInput) {
                rubTotalRateInput.value = payload.exchange_rate
                  ? formatProposalExchangeRateDisplay(String(payload.exchange_rate || '').trim())
                  : '';
              }
              syncCommercialFinancialRows();
            } catch (error) {
              console.error(error);
            } finally {
              document.documentElement.classList.remove('proposal-progress-cursor');
              refreshBtn.classList.remove('is-loading');
              refreshBtn.disabled = false;
            }
          });
          serviceActions.appendChild(refreshBtn);
          serviceWrap.appendChild(serviceActions);
        }
        const serviceInput = document.createElement('input');
        serviceInput.type = 'text';
        serviceInput.className = 'form-control proposal-commercial-service-text';
        serviceInput.value = config.serviceStateKey ? (state[config.serviceStateKey] || '') : '';
        if (config.showCbrLink && !isCommercialRateMasterBlock()) {
          serviceInput.readOnly = true;
          serviceInput.tabIndex = -1;
          serviceInput.classList.add('readonly-field');
        } else {
          serviceInput.addEventListener('input', function () {
            syncCommercialFinancialRows();
          });
          serviceInput.addEventListener('change', function () {
            syncCommercialFinancialRows();
          });
        }
        serviceWrap.appendChild(serviceInput);
        serviceTd.appendChild(serviceWrap);
        row.appendChild(serviceTd);
      }

      const rateTd = createProposalTableCell('proposal-commercial-rate-cell proposal-commercial-financial-rate-cell');
      if (config.rateMode === 'money') {
        const rateInput = document.createElement('input');
        rateInput.type = 'text';
        rateInput.className = 'form-control js-money-input proposal-commercial-rate';
        rateInput.dataset.moneyPrecision = '4';
        rateInput.inputMode = 'decimal';
        rateInput.value = state.exchange_rate ? formatProposalExchangeRateDisplay(state.exchange_rate) : '';
        if (!isCommercialRateMasterBlock()) {
          rateInput.readOnly = true;
          rateInput.tabIndex = -1;
          rateInput.classList.add('readonly-field');
        } else {
          rateInput.addEventListener('input', function () {
            syncCommercialFinancialRows();
          });
          rateInput.addEventListener('change', function () {
            syncCommercialFinancialRows();
          });
        }
        rateTd.appendChild(rateInput);
      } else if (config.rateMode === 'percent') {
        const rateInput = document.createElement('input');
        rateInput.type = 'text';
        rateInput.className = 'form-control proposal-commercial-rate proposal-commercial-discount-rate';
        rateInput.inputMode = 'decimal';
        rateInput.value = formatProposalPercentDisplay(state.discount_percent);
        rateInput.addEventListener('focus', function () {
          rateInput.value = String(rateInput.value || '').replace('%', '').trim();
        });
        rateInput.addEventListener('input', function () {
          syncCommercialFinancialRows();
        });
        rateInput.addEventListener('change', function () {
          syncCommercialFinancialRows();
        });
        rateInput.addEventListener('blur', function () {
          rateInput.value = formatProposalPercentDisplay(rateInput.value);
          syncCommercialFinancialRows();
        });
        rateTd.appendChild(rateInput);
      } else {
        const rateInput = document.createElement('input');
        rateInput.type = 'text';
        rateInput.className = 'form-control proposal-commercial-rate readonly-field';
        rateInput.readOnly = true;
        rateInput.tabIndex = -1;
        rateTd.appendChild(rateInput);
      }
      row.appendChild(rateTd);

      const totalTd = createProposalTableCell('proposal-commercial-total-cell proposal-commercial-total-value-cell');
      const totalInput = document.createElement('input');
      totalInput.type = 'text';
      totalInput.className = 'form-control proposal-commercial-total' + (config.totalEditable ? ' js-money-input' : ' readonly-field');
      totalInput.inputMode = 'decimal';
      if (config.totalEditable) {
        totalInput.value = state.contract_total ? fmtMoney(state.contract_total) : '';
        row.dataset.manualContractOverride = (
          state.contract_total
          && state.contract_total !== state.contract_total_auto
          && parseFloat(rawMoney(state.contract_total || '')) !== 0
        ) ? '1' : '0';
        totalInput.addEventListener('input', function () {
          row.dataset.manualContractOverride = rawMoney(totalInput.value || '') ? '1' : '0';
          syncCommercialFinancialRows();
        });
        totalInput.addEventListener('change', function () {
          row.dataset.manualContractOverride = rawMoney(totalInput.value || '') ? '1' : '0';
          syncCommercialFinancialRows();
        });
      } else {
        totalInput.readOnly = true;
        totalInput.tabIndex = -1;
      }
      totalTd.appendChild(totalInput);
      row.appendChild(totalTd);

      syncDayCells(row, getAssetRows(), createReadOnlyDayValues(), { readOnly: true });
      attachMoneyInputs(row);
      if (config.serviceEditable) syncFinancialServiceCellExpansion(row);
      return row;
    }

    function renderRows(dataRows) {
      tbody.innerHTML = '';
      const rowsList = Array.isArray(dataRows) ? dataRows : [];
      const regularRows = rowsList.filter(function (item) {
        return !isProposalTravelExpensesRow(item);
      });
      const travelRow = normalizeProposalTravelExpensesRow(
        rowsList.find(isProposalTravelExpensesRow) || {}
      );
      const totalsState = parseTotalsPayload();
      const travelExpensesMode = inferProposalTravelExpensesMode(travelRow, totalsState.travel_expenses_mode);
      regularRows.forEach(function (item) {
        tbody.appendChild(createRow(item || {}));
      });
      tbody.appendChild(createSummaryRow());
      tbody.appendChild(createTravelExpensesRow(travelRow, travelExpensesMode));
      tbody.appendChild(createSummaryWithTravelRow());
      tbody.appendChild(createFinancialTotalRow({
        label: PROPOSAL_RUB_TOTAL_LABEL,
        rowClass: 'proposal-commercial-financial-row proposal-commercial-financial-row--first',
        rowDataset: 'rubTotalRow',
        rateMode: 'money',
        totalEditable: false,
        serviceEditable: true,
        serviceStateKey: 'rub_total_service_text',
        showCbrLink: true,
      }, totalsState));
      tbody.appendChild(createFinancialTotalRow({
        label: PROPOSAL_RUB_DISCOUNTED_LABEL,
        rowClass: 'proposal-commercial-financial-row',
        rowDataset: 'discountedTotalRow',
        rateMode: 'percent',
        totalEditable: false,
        serviceEditable: true,
        serviceStateKey: 'discounted_total_service_text',
      }, totalsState));
      tbody.appendChild(createFinancialTotalRow({
        label: PROPOSAL_CONTRACT_TOTAL_LABEL,
        rowClass: 'proposal-commercial-financial-row',
        rowDataset: 'contractTotalRow',
        rateMode: 'readonly',
        totalEditable: true,
        serviceEditable: false,
      }, totalsState));
      syncSummaryRowValues();
      syncSummaryWithTravelRowValues();
      syncCommercialFinancialRows();
      syncActions();
    }

    function moveSelected(direction) {
      const rows = getEditableRows();
      if (direction === 'up') {
        for (let i = 1; i < rows.length; i += 1) {
          if (rows[i].querySelector('.proposal-commercial-check:checked') && !rows[i - 1].querySelector('.proposal-commercial-check:checked')) {
            tbody.insertBefore(rows[i], rows[i - 1]);
          }
        }
      } else {
        for (let i = rows.length - 2; i >= 0; i -= 1) {
          if (rows[i].querySelector('.proposal-commercial-check:checked') && !rows[i + 1].querySelector('.proposal-commercial-check:checked')) {
            tbody.insertBefore(rows[i + 1], rows[i]);
          }
        }
      }
      updatePayload({ reason: 'row-move' });
    }

    function deleteSelected() {
      getSelectedRows().forEach(function (row) {
        row.remove();
      });
      updatePayload({ reason: 'row-delete' });
    }

    if (!isSummaryCommercialBlock && addBtn) {
      addBtn.addEventListener('click', function () {
        const row = createRow({});
        const firstFixedRow = getRows().find(function (item) { return isFixedRow(item); });
        if (firstFixedRow) {
          tbody.insertBefore(row, firstFixedRow);
        } else {
          tbody.appendChild(row);
        }
        updatePayload({ reason: 'row-add', rowIndex: getEditableRows().length - 1 });
        row.querySelector('.proposal-commercial-specialist')?.focus();
      });
    }

    if (upBtn) {
      upBtn.addEventListener('click', function () { moveSelected('up'); });
    }
    if (downBtn) {
      downBtn.addEventListener('click', function () { moveSelected('down'); });
    }
    if (!isSummaryCommercialBlock && deleteBtn) {
      deleteBtn.addEventListener('click', deleteSelected);
    }

    formRoot.addEventListener('proposal-assets-changed', function (event) {
      const rows = Array.isArray(event.detail?.rows) ? event.detail.rows : getAssetRows();
      const meta = event.detail?.meta || {};
      renderHeader(rows);
      getRows().forEach(function (row) {
        if (meta.reason === 'row-add' && !isSummaryCommercialBlock) {
          syncDayCells(
            row,
            rows,
            getProposalCommercialDayCounts(
              form,
              row.querySelector('.proposal-commercial-service')?.value || '',
              getDayInputs(row).map(function (input) { return input.value || ''; }),
              { replaceAll: false }
            )
          );
          return;
        }
        if (isSummaryRow(row)) {
          syncSummaryRowValues();
          return;
        }
        if (isSummaryWithTravelRow(row)) {
          syncSummaryWithTravelRowValues();
          return;
        }
        syncDayCells(row, rows, undefined, { readOnly: isSummaryCommercialBlock || (isFixedRow(row) && !isTravelRow(row)) });
      });
      updatePayload({ reason: 'sync-asset-columns' });
    });

    if (servicesStore) {
      servicesStore.subscribe(function (detail) {
        if (detail?.meta?.source === 'commercial-view') return;
        renderRows(detail?.rows || []);
      });
    }
    if (!scope.dataset.commercialSharedRateBound) {
      scope.dataset.commercialSharedRateBound = '1';
      formRoot.addEventListener('proposal-commercial-shared-rate-changed', function () {
        if (isCommercialRateMasterBlock()) return;
        applySharedCommercialRateState();
        syncCommercialFinancialRows();
      });
    }

    renderHeader(getAssetRows());
    renderRows(parsePayload());
    window.addEventListener('resize', syncAllFinancialServiceCellExpansions);

    const api = {
      getSerializedRows: function () {
        return servicesStore ? servicesStore.getRows() : getRows().map(serializeRow).filter(Boolean);
      },
      replaceRows: function (rowsData, meta) {
        if (servicesStore) {
          servicesStore.commitCommercialRows(rowsData || [], { ...(meta || {}), source: 'commercial-view' });
          return;
        }
        renderRows(rowsData || []);
        updatePayload(meta);
      },
    };
    scope.__proposalCommercialTableApi = api;
    return api;
  }

  function attachProposalServiceSectionsTable(root) {
    if (!root) return null;
    const scope = getProposalScope(root);
    const form = scope;
    const servicesStore = attachProposalServicesStore(scope);
    const payloadInput = scope.querySelector('#proposal-service-sections-payload');
    const tbody = scope.querySelector('#proposal-service-sections-tbody');
    const addBtn = scope.querySelector('#proposal-service-section-add-btn');
    const actions = scope.querySelector('#proposal-service-sections-row-actions');
    const upBtn = scope.querySelector('#proposal-service-section-up-btn');
    const downBtn = scope.querySelector('#proposal-service-section-down-btn');
    const deleteBtn = scope.querySelector('#proposal-service-section-delete-btn');
    const masterCheck = scope.querySelector('#proposal-service-sections-master-check');
    if (!payloadInput || !tbody || !addBtn || !actions || !upBtn || !downBtn || !deleteBtn) return null;
    if (scope.dataset.serviceSectionsBound === '1') return scope.__proposalServiceSectionsTableApi || null;
    scope.dataset.serviceSectionsBound = '1';

    function parsePayload() {
      if (servicesStore) return servicesStore.getServiceRows();
      try {
        const data = JSON.parse(payloadInput.value || '[]');
        return Array.isArray(data) ? data : [];
      } catch (error) {
        return [];
      }
    }

    function getRows() {
      return Array.from(tbody.querySelectorAll('tr'));
    }

    function getSelectedRows() {
      return getRows().filter(function (row) {
        return !!row.querySelector('.proposal-service-section-check:checked');
      });
    }

    function syncActions() {
      const hasSelected = getSelectedRows().length > 0;
      actions.classList.toggle('d-none', !hasSelected);
      actions.classList.toggle('d-flex', hasSelected);
      syncMasterCheck();
    }

    function syncMasterCheck() {
      if (!masterCheck) return;
      const rows = getRows();
      const selectedCount = getSelectedRows().length;
      masterCheck.indeterminate = selectedCount > 0 && selectedCount < rows.length;
      masterCheck.checked = rows.length > 0 && selectedCount === rows.length;
    }

    function serializeRow(row) {
      return {
        service_name: (row.querySelector('.proposal-service-section-name')?.value || '').trim(),
        code: (row.querySelector('.proposal-service-section-code')?.value || '').trim(),
      };
    }

    function updatePayload(meta) {
      const rows = getRows().map(serializeRow);
      syncActions();
      if (servicesStore) {
        servicesStore.commitServiceRows(rows, { ...(meta || {}), source: 'service-view' });
        return;
      }
      payloadInput.value = JSON.stringify(rows);
      form.dispatchEvent(new CustomEvent('proposal-service-sections-changed', { detail: { rows: rows, meta: meta || null } }));
    }

    function syncCode(row) {
      const serviceSelect = row.querySelector('.proposal-service-section-name');
      const codeInput = row.querySelector('.proposal-service-section-code');
      if (!serviceSelect || !codeInput) return;
      codeInput.value = getProposalTypicalSectionCode(form, serviceSelect.value || '');
    }

    function createRow(data) {
      const row = document.createElement('tr');

      const checkTd = createProposalTableCell('proposal-asset-check-cell');
      const checkWrap = document.createElement('div');
      checkWrap.className = 'form-check proposal-asset-check-wrap';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'form-check-input proposal-service-section-check';
      checkbox.style.margin = '0';
      checkbox.style.float = 'none';
      checkbox.addEventListener('change', syncActions);
      checkWrap.appendChild(checkbox);
      checkTd.appendChild(checkWrap);
      row.appendChild(checkTd);

      const nameTd = createProposalTableCell();
      const nameSelect = document.createElement('select');
      nameSelect.className = 'form-select proposal-service-section-name';
      syncProposalServiceSectionSelect(nameSelect, form, data.service_name || '');
      nameSelect.value = data.service_name || '';
      nameTd.appendChild(nameSelect);
      row.appendChild(nameTd);

      const codeTd = createProposalTableCell();
      const codeInput = document.createElement('input');
      codeInput.type = 'text';
      codeInput.className = 'form-control readonly-field proposal-service-section-code';
      codeInput.readOnly = true;
      codeInput.tabIndex = -1;
      codeInput.value = data.code || '';
      codeTd.appendChild(codeInput);
      row.appendChild(codeTd);

      nameSelect.addEventListener('change', function () {
        syncCode(row);
        updatePayload({ reason: 'row-edit', rowIndex: getRows().indexOf(row) });
      });

      syncCode(row);
      if (!codeInput.value && data.code) codeInput.value = data.code;
      return row;
    }

    function renderRows(rowsData) {
      tbody.innerHTML = '';
      rowsData.forEach(function (item) {
        tbody.appendChild(createRow(item));
      });
      syncActions();
    }

    function moveSelected(direction) {
      const rows = getRows();
      if (direction === 'up') {
        for (let i = 1; i < rows.length; i += 1) {
          if (rows[i].querySelector('.proposal-service-section-check:checked') && !rows[i - 1].querySelector('.proposal-service-section-check:checked')) {
            tbody.insertBefore(rows[i], rows[i - 1]);
          }
        }
      } else {
        for (let i = rows.length - 2; i >= 0; i -= 1) {
          if (rows[i].querySelector('.proposal-service-section-check:checked') && !rows[i + 1].querySelector('.proposal-service-section-check:checked')) {
            tbody.insertBefore(rows[i + 1], rows[i]);
          }
        }
      }
      updatePayload({ reason: 'row-move' });
    }

    function deleteSelected() {
      getSelectedRows().forEach(function (row) {
        row.remove();
      });
      updatePayload({ reason: 'row-delete' });
    }

    addBtn.addEventListener('click', function () {
      const row = createRow({});
      tbody.appendChild(row);
      updatePayload({ reason: 'row-add', rowIndex: getRows().length - 1 });
      row.querySelector('.proposal-service-section-name')?.focus();
    });

    upBtn.addEventListener('click', function () { moveSelected('up'); });
    downBtn.addEventListener('click', function () { moveSelected('down'); });
    deleteBtn.addEventListener('click', deleteSelected);
    masterCheck?.addEventListener('change', function () {
      const checked = !!masterCheck.checked;
      getRows().forEach(function (row) {
        const checkbox = row.querySelector('.proposal-service-section-check');
        if (checkbox) checkbox.checked = checked;
      });
      syncActions();
    });

    if (servicesStore) {
      servicesStore.subscribe(function (detail) {
        if (detail?.meta?.source === 'service-view') return;
        renderRows(detail?.serviceRows || []);
      });
      if (!servicesStore.getRows().length && getProposalTypeId(scope)) {
        servicesStore.replaceFromType({ reason: 'autofill-service-sections-by-type', source: 'type-change' });
      }
      renderRows(servicesStore.getServiceRows());
    } else {
      const initialRows = parsePayload();
      if (initialRows.length) {
        initialRows.forEach(function (item) {
          tbody.appendChild(createRow(item));
        });
        updatePayload();
      } else {
        updatePayload();
      }
    }

    const api = {
      getSerializedRows: function () {
        return servicesStore ? servicesStore.getServiceRows() : getRows().map(serializeRow);
      },
      replaceRows: function (rowsData, meta) {
        if (servicesStore) {
          servicesStore.commitServiceRows(rowsData || [], { ...(meta || {}), source: 'service-view' });
          return;
        }
        renderRows(rowsData || []);
        updatePayload(meta);
      },
    };
    scope.__proposalServiceSectionsTableApi = api;
    return api;
  }

  function attachProposalServiceTextEditor(root) {
    if (!root) return null;
    const form = getProposalScope(root);
    const openBtn = form.querySelector('#proposal-service-text-edit-btn');
    const modal = form.querySelector('#proposal-service-text-modal');
    const closeBtn = form.querySelector('#proposal-service-text-close-btn');
    const cancelBtn = form.querySelector('#proposal-service-text-cancel-btn');
    const saveBtn = form.querySelector('#proposal-service-text-save-btn');
    const cards = form.querySelector('#proposal-service-text-cards');
    const toolbar = form.querySelector('#proposal-service-text-toolbar');
    const dialog = form.querySelector('#proposal-service-text-modal .proposal-service-text-modal__dialog');
    const stateInput = form.querySelector('#proposal-service-sections-editor-state');
    const customerStateInput = form.querySelector('#proposal-service-customer-tz-editor-state');
    const textarea = form.querySelector('[name="service_composition"]');
    const customerTextareaInput = form.querySelector('#proposal-service-composition-customer-tz');
    const modeInput = form.querySelector('#proposal-service-composition-mode');
    const modeToggle = form.querySelector('#proposal-service-mode-toggle');
    const payloadInput = form.querySelector('#proposal-service-sections-payload');
    if (!openBtn || !modal || !closeBtn || !cancelBtn || !saveBtn || !cards || !toolbar || !dialog || !stateInput || !customerStateInput || !textarea || !customerTextareaInput || !modeInput || !modeToggle || !payloadInput) {
      return null;
    }
    if (form.dataset.serviceTextEditorBound === '1') return form.__proposalServiceTextEditorApi || null;
    form.dataset.serviceTextEditorBound = '1';

    let activeQuill = null;
    let activeCard = null;
    let draftState = [];
    let quillInstances = [];
    let isOpen = false;
    let lastRange = null;

    function getMode() {
      return (modeInput.value || 'sections') === 'customer_tz' ? 'customer_tz' : 'sections';
    }

    function setMode(mode) {
      modeInput.value = mode === 'customer_tz' ? 'customer_tz' : 'sections';
      modeToggle.checked = modeInput.value === 'customer_tz';
    }

    function getSections() {
      const api = form.__proposalServiceSectionsTableApi;
      const onlyTechnicalAssignmentSections = function (items) {
        return items.filter(function (item) {
          return (item.service_name || '').trim() && isProposalTechnicalAssignmentSection(form, item);
        });
      };
      if (api && typeof api.getSerializedRows === 'function') {
        return onlyTechnicalAssignmentSections(api.getSerializedRows());
      }
      try {
        const rows = JSON.parse(payloadInput.value || '[]');
        return Array.isArray(rows) ? onlyTechnicalAssignmentSections(rows) : [];
      } catch (error) {
        return [];
      }
    }

    function parseEditorState() {
      try {
        const source = getMode() === 'customer_tz' ? (customerStateInput.value || '{}') : (stateInput.value || '[]');
        const rows = JSON.parse(source);
        if (getMode() === 'customer_tz') return rows && typeof rows === 'object' ? rows : {};
        return Array.isArray(rows) ? rows : [];
      } catch (error) {
        return getMode() === 'customer_tz' ? {} : [];
      }
    }

    function getSectionKey(section) {
      const code = (section?.code || '').trim();
      const name = (section?.service_name || '').trim();
      return code || name;
    }

    function normalizeTextToHtml(text) {
      const value = String(text || '').trim();
      if (!value) return '';
      return value.split(/\n{2,}/).map(function (chunk) {
        return '<p>' + escapeHtml(chunk).replace(/\n/g, '<br>') + '</p>';
      }).join('');
    }

    function extractPlainTextFromHtml(html) {
      const wrapper = document.createElement('div');
      wrapper.innerHTML = html || '';
      return (wrapper.textContent || wrapper.innerText || '').replace(/\r\n/g, '\n').trim();
    }

    function parseTextAreaBySections(sections) {
      const fallback = sections.map(function (section) {
        return {
          code: (section.code || '').trim(),
          service_name: (section.service_name || '').trim(),
          html: '',
          plain_text: '',
        };
      });
      const rawText = String(textarea.value || '').trim();
      if (!rawText || !fallback.length) return fallback;

      const byCode = {};
      fallback.forEach(function (item) {
        if (item.code) byCode[item.code] = item;
      });

      let current = null;
      let buffer = [];
      function flush() {
        if (!current) return;
        const plainText = buffer.join('\n').trim();
        current.plain_text = plainText;
        current.html = normalizeTextToHtml(plainText);
      }

      rawText.split('\n').forEach(function (line) {
        const match = line.match(/^\[(.+?)\]\s*(.*)$/);
        const candidate = match ? byCode[(match[1] || '').trim()] : null;
        if (candidate) {
          flush();
          current = candidate;
          buffer = [];
          const remainder = (match[2] || '').trim();
          if (remainder && remainder !== candidate.service_name) buffer.push(remainder);
          return;
        }
        if (current) {
          buffer.push(line);
        } else if (fallback[0]) {
          current = fallback[0];
          buffer.push(line);
        }
      });
      flush();
      return fallback;
    }

    function buildStateFromCurrentData() {
      if (getMode() === 'customer_tz') {
        const stored = parseEditorState();
        const html = String(stored.html || '').trim();
        const plainText = String(stored.plain_text || customerTextareaInput.value || '').trim();
        return [
          {
            code: '',
            service_name: '',
            html: html || normalizeTextToHtml(plainText),
            plain_text: plainText,
          },
        ];
      }

      const sections = getSections();
      const stored = parseEditorState();
      const storedByKey = {};
      stored.forEach(function (item) {
        storedByKey[getSectionKey(item)] = item;
      });

      let merged = sections.map(function (section) {
        const key = getSectionKey(section);
        const saved = storedByKey[key] || {};
        const html = String(saved.html || '').trim();
        const plainText = String(saved.plain_text || extractPlainTextFromHtml(html) || '').trim();
        return {
          code: (section.code || '').trim(),
          service_name: (section.service_name || '').trim(),
          html: html,
          plain_text: plainText,
        };
      });

      const hasSavedContent = merged.some(function (item) {
        return item.html || item.plain_text;
      });
      if (!hasSavedContent) {
        merged = parseTextAreaBySections(sections);
      }
      return merged.map(function (item, index) {
        const html = String(item.html || '').trim();
        const plainText = String(item.plain_text || extractPlainTextFromHtml(html) || '').trim();
        if (html || plainText) {
          return {
            ...item,
            html: html,
            plain_text: plainText,
          };
        }
        const defaultEditorState = getProposalTypicalServiceCompositionEditorState(form, sections[index] || item);
        const defaultHtml = String(defaultEditorState.html || '').trim();
        const defaultPlainText = String(
          defaultEditorState.plain_text
          || extractPlainTextFromHtml(defaultHtml)
          || getProposalTypicalServiceCompositionText(form, sections[index] || item)
          || ''
        ).trim();
        return {
          ...item,
          html: defaultHtml || (defaultPlainText ? normalizeTextToHtml(defaultPlainText) : ''),
          plain_text: defaultPlainText,
        };
      });
    }

    function serializeState(state) {
      if (getMode() === 'customer_tz') {
        const item = state[0] || { html: '', plain_text: '' };
        return JSON.stringify({
          html: item.html || '',
          plain_text: item.plain_text || '',
        });
      }
      return JSON.stringify(state.map(function (item) {
        return {
          code: item.code || '',
          service_name: item.service_name || '',
          html: item.html || '',
          plain_text: item.plain_text || '',
        };
      }));
    }

    function composeTextareaValue(state) {
      if (getMode() === 'customer_tz') {
        return String(state[0]?.plain_text || '').trim();
      }
      return state.map(function (item) {
        const headerParts = [];
        if (item.code) headerParts.push('[' + item.code + ']');
        if (item.service_name) headerParts.push(item.service_name);
        const header = headerParts.join(' ').trim();
        const body = String(item.plain_text || '').trim();
        return [header, body].filter(Boolean).join('\n');
      }).filter(Boolean).join('\n\n');
    }

    function syncModalBounds() {
      if (!isOpen) return;
      const main = form.closest('main') || document.querySelector('main');
      if (!main) return;
      const rect = main.getBoundingClientRect();
      modal.style.left = '0';
      modal.style.top = '0';
      modal.style.right = '0';
      modal.style.bottom = '0';
      dialog.style.left = Math.max(rect.left + 18, 18) + 'px';
      dialog.style.top = '18px';
      dialog.style.right = '18px';
      dialog.style.bottom = '18px';
    }

    function destroyEditors() {
      quillInstances.forEach(function (entry) {
        const editorEl = entry.editorEl;
        if (!editorEl) return;
        editorEl.innerHTML = '';
        editorEl.className = 'proposal-service-text-card__editor';
      });
      quillInstances = [];
      activeQuill = null;
      activeCard = null;
      cards.innerHTML = '';
    }

    function setActiveEditor(quill, card) {
      activeQuill = quill || null;
      if (activeCard) activeCard.classList.remove('is-active');
      activeCard = card || null;
      if (activeCard) activeCard.classList.add('is-active');
      syncToolbarState();
    }

    function restoreSelection() {
      if (!activeQuill) return;
      activeQuill.focus();
      if (lastRange) {
        activeQuill.setSelection(lastRange.index, lastRange.length, 'silent');
      } else {
        activeQuill.getSelection(true);
      }
    }

    function updateColorPreviews() {
      toolbar.querySelectorAll('[data-color-preview]').forEach(function (preview) {
        const kind = preview.dataset.colorPreview;
        const input = toolbar.querySelector('[data-color-source="' + kind + '"]');
        if (input) preview.style.backgroundColor = input.value || '#000000';
      });
    }

    function normalizeToolbarColor(value, fallback) {
      const source = String(value || '').trim();
      if (!source) return fallback;
      if (/^#([0-9a-f]{3}){1,2}$/i.test(source)) {
        if (source.length === 4) {
          return '#' + source.slice(1).split('').map(function (part) { return part + part; }).join('');
        }
        return source;
      }
      const rgbMatch = source.match(/^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/i);
      if (!rgbMatch) return fallback;
      return '#' + rgbMatch.slice(1, 4).map(function (part) {
        return Math.max(0, Math.min(255, Number(part) || 0)).toString(16).padStart(2, '0');
      }).join('');
    }

    function setToolbarButtonActive(button, isActive) {
      if (!button) return;
      button.classList.toggle('is-active', !!isActive);
      button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    }

    function syncToolbarState() {
      const format = activeQuill ? activeQuill.getFormat(lastRange || activeQuill.getSelection() || undefined) : {};
      const fontSelect = toolbar.querySelector('select[data-format="font"]');
      const currentFont = String(format.font || 'calibri').trim() || 'calibri';
      if (fontSelect) {
        const hasOption = Array.from(fontSelect.options).some(function (option) {
          return option.value === currentFont;
        });
        fontSelect.value = hasOption ? currentFont : 'calibri';
      }

      toolbar.querySelectorAll('button[data-format]').forEach(function (button) {
        setToolbarButtonActive(button, !!format[button.dataset.format]);
      });
      toolbar.querySelectorAll('button[data-list]').forEach(function (button) {
        setToolbarButtonActive(button, (format.list || '') === button.dataset.list);
      });
      toolbar.querySelectorAll('button[data-align]').forEach(function (button) {
        const align = format.align || 'left';
        setToolbarButtonActive(button, align === button.dataset.align);
      });

      const colorInput = toolbar.querySelector('[data-color-source="color"]');
      const backgroundInput = toolbar.querySelector('[data-color-source="background"]');
      if (colorInput) colorInput.value = normalizeToolbarColor(format.color, '#000000');
      if (backgroundInput) backgroundInput.value = normalizeToolbarColor(format.background, '#ffffff');
      updateColorPreviews();
    }

    function applyToolbarAction(event) {
      if (!activeQuill) return;
      const button = event.target.closest('button[data-format], button[data-list], button[data-action], button[data-align], button[data-apply-color]');
      if (button && toolbar.contains(button)) {
        event.preventDefault();
        restoreSelection();
        if (button.dataset.format) {
          const formatName = button.dataset.format;
          const current = activeQuill.getFormat().hasOwnProperty(formatName) ? activeQuill.getFormat()[formatName] : false;
          activeQuill.format(formatName, current ? false : true);
          syncToolbarState();
          return;
        }
        if (button.dataset.list) {
          const listType = button.dataset.list;
          const currentList = activeQuill.getFormat().list || false;
          activeQuill.format('list', currentList === listType ? false : listType);
          syncToolbarState();
          return;
        }
        if (button.dataset.align) {
          const align = button.dataset.align;
          activeQuill.format('align', align === 'left' ? false : align);
          syncToolbarState();
          return;
        }
        if (button.dataset.applyColor) {
          const formatName = button.dataset.applyColor;
          const input = toolbar.querySelector('[data-color-source="' + formatName + '"]');
          activeQuill.format(formatName, input?.value || false);
          syncToolbarState();
          return;
        }
        if (button.dataset.action === 'clean') {
          const safeRange = activeQuill.getSelection(true);
          if (safeRange && safeRange.length) {
            activeQuill.removeFormat(safeRange.index, safeRange.length);
          } else {
            activeQuill.format('bold', false);
            activeQuill.format('italic', false);
            activeQuill.format('underline', false);
            activeQuill.format('color', false);
            activeQuill.format('background', false);
            activeQuill.format('list', false);
            activeQuill.format('align', false);
          }
          syncToolbarState();
        }
      }
    }

    function applyToolbarSelect(event) {
      if (!activeQuill) return;
      const input = event.target.closest('select[data-format]');
      if (!input || !toolbar.contains(input)) return;
      const value = input.value || false;
      restoreSelection();
      activeQuill.format(input.dataset.format, value);
      syncToolbarState();
    }

    function handleColorInput(event) {
      const input = event.target.closest('input[data-color-source]');
      if (!input || !toolbar.contains(input)) return;
      updateColorPreviews();
    }

    function persistDraftState() {
      const serialized = serializeState(draftState);
      const plainText = composeTextareaValue(draftState);
      if (getMode() === 'customer_tz') {
        customerStateInput.value = serialized;
        customerTextareaInput.value = plainText;
      } else {
        stateInput.value = serialized;
        textarea.value = plainText;
      }
    }

    function buildCards() {
      destroyEditors();
      draftState = buildStateFromCurrentData();
      draftState.forEach(function (item, index) {
        const fieldset = document.createElement('fieldset');
        fieldset.className = 'proposal-service-text-card' + (getMode() === 'customer_tz' ? ' proposal-service-text-card--single' : '');
        fieldset.innerHTML = (getMode() === 'customer_tz'
          ? ''
          : ('<legend>' + escapeHtml(item.code || 'Без кода') + '</legend>'))
          + '<div class="proposal-service-text-card__editor" id="proposal-service-text-editor-' + index + '"></div>';
        cards.appendChild(fieldset);
        const editorEl = fieldset.querySelector('.proposal-service-text-card__editor');
        const quill = new Quill(editorEl, {
          theme: 'snow',
          modules: {
            toolbar: false,
          },
        });
        const html = item.html || normalizeTextToHtml(item.plain_text || '');
        if (html) {
          const delta = quill.clipboard.convert({ html: html });
          quill.setContents(delta, 'silent');
        }
        quill.format('font', 'calibri', 'silent');
        quill.format('align', 'justify');
        quill.on('selection-change', function (range) {
          if (range) {
            lastRange = range;
            setActiveEditor(quill, fieldset);
          } else if (activeQuill === quill) {
            syncToolbarState();
          }
        });
        quill.on('text-change', function () {
          const currentHtml = quill.root.innerHTML === '<p><br></p>' ? '' : quill.root.innerHTML;
          const currentText = quill.getText().replace(/\s+$/, '').trim();
          draftState[index].html = currentHtml;
          draftState[index].plain_text = currentText;
          if (activeQuill === quill) syncToolbarState();
        });
        editorEl.addEventListener('click', function () {
          setActiveEditor(quill, fieldset);
        });
        quillInstances.push({ quill: quill, editorEl: editorEl, card: fieldset, stateIndex: index });
      });
      setActiveEditor(null, null);
    }

    function focusFirstCardEditor() {
      if (!quillInstances[0]?.quill) return;
      lastRange = { index: 0, length: 0 };
      setActiveEditor(quillInstances[0].quill, quillInstances[0].card);
      quillInstances[0].quill.focus();
      quillInstances[0].quill.setSelection(0, 0, 'silent');
    }

    function openModal() {
      loadProposalQuill(function () {
        isOpen = true;
        lastRange = null;
        syncModalBounds();
        modal.classList.remove('d-none');
        modal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('proposal-service-text-modal-open');
        updateColorPreviews();
        buildCards();
        const modalBody = modal.querySelector('.proposal-service-text-modal__body');
        if (modalBody) modalBody.scrollTop = 0;
        if (cards) cards.scrollTop = 0;
        const activeEl = document.activeElement;
        if (activeEl && typeof activeEl.blur === 'function') activeEl.blur();
      });
    }

    function closeModal() {
      isOpen = false;
      modal.classList.add('d-none');
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('proposal-service-text-modal-open');
      destroyEditors();
    }

    function saveModal() {
      persistDraftState();
      textarea.value = composeTextareaValue(draftState);
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      textarea.dispatchEvent(new Event('change', { bubbles: true }));
      closeModal();
    }

    toolbar.addEventListener('click', applyToolbarAction);
    toolbar.addEventListener('change', applyToolbarSelect);
    toolbar.addEventListener('input', handleColorInput);
    openBtn.addEventListener('click', openModal);
    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    saveBtn.addEventListener('click', saveModal);
    modeToggle.addEventListener('change', function () {
      if (isOpen) persistDraftState();
      setMode(modeToggle.checked ? 'customer_tz' : 'sections');
      lastRange = null;
      if (isOpen && window.Quill) {
        buildCards();
        if (getMode() === 'sections') focusFirstCardEditor();
      }
    });
    modal.querySelector('.proposal-service-text-modal__backdrop')?.addEventListener('click', closeModal);
    window.addEventListener('resize', syncModalBounds);
    window.addEventListener('scroll', syncModalBounds, true);
    form.addEventListener('proposal-service-sections-changed', function () {
      if (getMode() !== 'sections') return;
      const updatedState = buildStateFromCurrentData();
      stateInput.value = JSON.stringify(updatedState.map(function (item) {
        return {
          code: item.code || '',
          service_name: item.service_name || '',
          html: item.html || '',
          plain_text: item.plain_text || '',
        };
      }));
      if (isOpen && window.Quill) buildCards();
    });

    setMode(getMode());

    const api = {
      open: openModal,
      close: closeModal,
    };
    form.__proposalServiceTextEditorApi = api;
    return api;
  }

  function initProposalForm() {
    const root = pane();
    const form = root?.querySelector('form[data-proposal-form]');
    if (!form) return;

    function parsePercentValue(input) {
      const raw = String(input?.value || '').trim().replace(',', '.');
      if (!raw) return 0;
      const value = Number.parseFloat(raw);
      return Number.isFinite(value) ? value : 0;
    }

    function syncFinalReportPercent() {
      const advanceInput = form.querySelector('[name="advance_percent"]');
      const preliminaryInput = form.querySelector('[name="preliminary_report_percent"]');
      const finalInput = form.querySelector('[name="final_report_percent"]');
      if (!advanceInput || !preliminaryInput || !finalInput) return;

      const result = 100 - parsePercentValue(advanceInput) - parsePercentValue(preliminaryInput);
      finalInput.value = result.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1');
    }

    function syncAssetOwnerFromCustomer(reason) {
      const matchesCheckbox = form.querySelector('[name="asset_owner_matches_customer"]');
      const customerInput = form.querySelector('input[name="customer"]');
      const customerCountry = form.querySelector('#proposal-country-select');
      const customerRegion = form.querySelector('#proposal-region-select');
      const customerIdentifier = form.querySelector('#proposal-identifier-field');
      const customerRegistrationNumber = form.querySelector('input[name="registration_number"]');
      const customerRegistrationDate = form.querySelector('input[name="registration_date"]');
      const ownerInput = form.querySelector('input[name="asset_owner"]');
      const ownerCountry = form.querySelector('#proposal-asset-owner-country-select');
      const ownerRegion = form.querySelector('#proposal-asset-owner-region-select');
      const ownerIdentifier = form.querySelector('#proposal-asset-owner-identifier-field');
      const ownerRegistrationNumber = form.querySelector('input[name="asset_owner_registration_number"]');
      const ownerRegistrationDate = form.querySelector('input[name="asset_owner_registration_date"]');
      const customerSelectedIdentifier = form.querySelector('#proposal-customer-autocomplete-identifier-record-id');
      const customerSelectedFlag = form.querySelector('#proposal-customer-autocomplete-selected');
      const ownerSelectedIdentifier = form.querySelector('#proposal-asset-owner-autocomplete-identifier-record-id');
      const ownerSelectedFlag = form.querySelector('#proposal-asset-owner-autocomplete-selected');
      if (
        !matchesCheckbox
        || !ownerInput
        || !ownerCountry
        || !ownerRegion
        || !ownerIdentifier
        || !ownerRegistrationNumber
        || !ownerRegistrationDate
      ) {
        return;
      }

      function setLockedState(locked) {
        ownerInput.readOnly = locked;
        ownerInput.tabIndex = locked ? -1 : 0;
        ownerInput.classList.toggle('readonly-field', locked);
        ownerCountry.disabled = locked;
        ownerCountry.classList.toggle('readonly-field', locked);
        ownerRegion.disabled = locked;
        ownerRegion.classList.toggle('readonly-field', locked);
        ownerRegistrationNumber.readOnly = locked;
        ownerRegistrationNumber.tabIndex = locked ? -1 : 0;
        ownerRegistrationNumber.classList.toggle('readonly-field', locked);
        ownerRegistrationDate.readOnly = locked;
        ownerRegistrationDate.tabIndex = locked ? -1 : 0;
        ownerRegistrationDate.classList.toggle('readonly-field', locked);
        if (ownerRegistrationDate._flatpickr) ownerRegistrationDate._flatpickr.set('clickOpens', !locked);
      }

      if (matchesCheckbox.checked) {
        ownerInput.value = customerInput ? (customerInput.value || '') : '';
        ownerCountry.value = customerCountry ? (customerCountry.value || '') : '';
        loadProposalRegionOptions(form.dataset.countryRegionUrl || '', ownerCountry.value || '', ownerRegion, {
          preserveCurrent: false,
          selectedRegion: customerRegion ? (customerRegion.value || '') : '',
          dateValue: customerRegistrationDate ? (customerRegistrationDate.value || '') : '',
        });
        ownerIdentifier.value = customerIdentifier ? (customerIdentifier.value || '') : '';
        ownerRegistrationNumber.value = customerRegistrationNumber ? (customerRegistrationNumber.value || '') : '';
        setDateFieldValue(ownerRegistrationDate, customerRegistrationDate ? (customerRegistrationDate.value || '') : '');
        if (ownerSelectedIdentifier) ownerSelectedIdentifier.value = customerSelectedIdentifier ? (customerSelectedIdentifier.value || '') : '';
        if (ownerSelectedFlag) ownerSelectedFlag.value = customerSelectedFlag ? (customerSelectedFlag.value || '0') : '0';
        setLockedState(true);
        form.dispatchEvent(new CustomEvent('proposal-asset-owner-changed', { detail: { reason: reason || 'customer-sync' } }));
        return;
      }

      setLockedState(false);
      form.dispatchEvent(new CustomEvent('proposal-asset-owner-changed', { detail: { reason: reason || 'customer-sync' } }));
    }

    function syncProposalTypeDefaults(force) {
      const projectNameInput = form.querySelector('#proposal-project-name-prefix');
      const purposeInput = form.querySelector('#proposal-purpose-prefix');
      const entry = getProposalServiceGoalReportEntry(form);
      if (!projectNameInput || !purposeInput || !entry) return;

      if (force || !String(projectNameInput.value || '').trim()) {
        projectNameInput.value = entry.report_title;
      }
      if (force || !String(purposeInput.value || '').trim()) {
        purposeInput.value = entry.service_goal;
      }
    }

    function syncProposalServiceTermMonths(force) {
      const serviceTermInput = form.querySelector('[name="service_term_months"]');
      const finalReportWeeksInput = form.querySelector('[name="final_report_term_weeks"]');
      const entry = getProposalTypicalServiceTermEntry(form);
      if (!entry) return;
      if (force || !String(serviceTermInput?.value || '').trim()) {
        if (serviceTermInput) {
          serviceTermInput.value = entry.preliminary_report_months;
        }
      }
      if (force || !String(finalReportWeeksInput?.value || '').trim()) {
        if (finalReportWeeksInput) {
          finalReportWeeksInput.value = entry.final_report_weeks;
        }
      }
    }

    function parseProposalDecimal(value) {
      const raw = String(value || '').trim().replace(/\s+/g, '').replace(',', '.');
      if (!raw) return null;
      const parsed = Number(raw);
      return Number.isFinite(parsed) ? parsed : null;
    }

    function parseProposalDate(value) {
      const raw = String(value || '').trim();
      if (!raw) return null;
      const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (isoMatch) {
        return new Date(Number(isoMatch[1]), Number(isoMatch[2]) - 1, Number(isoMatch[3]));
      }
      const displayMatch = raw.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
      if (displayMatch) {
        return new Date(Number(displayMatch[3]), Number(displayMatch[2]) - 1, Number(displayMatch[1]));
      }
      return null;
    }

    function startOfDay(date) {
      return new Date(date.getFullYear(), date.getMonth(), date.getDate());
    }

    function addDays(date, days) {
      const next = new Date(date.getTime());
      next.setDate(next.getDate() + days);
      return startOfDay(next);
    }

    function getNearestMonday(date) {
      const current = startOfDay(date);
      const day = current.getDay();
      const daysSinceMonday = (day + 6) % 7;
      const previousMonday = addDays(current, -daysSinceMonday);
      const nextMonday = addDays(previousMonday, 7);
      const diffToPrevious = Math.abs(current.getTime() - previousMonday.getTime());
      const diffToNext = Math.abs(nextMonday.getTime() - current.getTime());
      return diffToPrevious <= diffToNext ? previousMonday : nextMonday;
    }

    function addDecimalMonths(date, months) {
      const safeMonths = Number.isFinite(months) ? Math.max(months, 0) : 0;
      const wholeMonths = Math.trunc(safeMonths);
      const fractionalMonths = safeMonths - wholeMonths;
      const baseDate = startOfDay(date);
      const targetYear = baseDate.getFullYear();
      const targetMonthIndex = baseDate.getMonth() + wholeMonths;
      const targetMonthStart = new Date(targetYear, targetMonthIndex, 1);
      const targetMonthEndDay = new Date(targetMonthStart.getFullYear(), targetMonthStart.getMonth() + 1, 0).getDate();
      const day = Math.min(baseDate.getDate(), targetMonthEndDay);
      const wholeDate = new Date(targetMonthStart.getFullYear(), targetMonthStart.getMonth(), day);
      const fractionalDays = Math.round(fractionalMonths * 30);
      return addDays(wholeDate, fractionalDays);
    }

    function subtractDecimalMonths(date, months) {
      const safeMonths = Number.isFinite(months) ? Math.max(months, 0) : 0;
      const wholeMonths = Math.trunc(safeMonths);
      const fractionalMonths = safeMonths - wholeMonths;
      const fractionalDays = Math.round(fractionalMonths * 30);
      const baseDate = addDays(startOfDay(date), -fractionalDays);
      const targetYear = baseDate.getFullYear();
      const targetMonthIndex = baseDate.getMonth() - wholeMonths;
      const targetMonthStart = new Date(targetYear, targetMonthIndex, 1);
      const targetMonthEndDay = new Date(targetMonthStart.getFullYear(), targetMonthStart.getMonth() + 1, 0).getDate();
      const day = Math.min(baseDate.getDate(), targetMonthEndDay);
      return new Date(targetMonthStart.getFullYear(), targetMonthStart.getMonth(), day);
    }

    function addDecimalWeeks(date, weeks) {
      const safeWeeks = Number.isFinite(weeks) ? Math.max(weeks, 0) : 0;
      return addDays(date, Math.round(safeWeeks * 7));
    }

    function subtractDecimalWeeks(date, weeks) {
      const safeWeeks = Number.isFinite(weeks) ? Math.max(weeks, 0) : 0;
      return addDays(date, -Math.round(safeWeeks * 7));
    }

    function diffProposalDays(start, end) {
      const safeStart = startOfDay(start);
      const safeEnd = startOfDay(end);
      return Math.round((safeEnd.getTime() - safeStart.getTime()) / 86400000);
    }

    function roundProposalDecimal(value) {
      return Math.round(value * 10) / 10;
    }

    function formatProposalDecimal(value) {
      return Number.isFinite(value) ? roundProposalDecimal(value).toFixed(1) : '';
    }

    function normalizeProposalDecimalInputValue(input) {
      if (!input) return null;
      const parsed = parseProposalDecimal(input.value);
      input.value = parsed === null ? '' : formatProposalDecimal(parsed);
      return parsed;
    }

    function getProposalBaseStartDate() {
      return getNearestMonday(addDays(new Date(), 14));
    }

    function getProposalDefaultEvaluationDate() {
      const today = new Date();
      const year = today.getFullYear();
      const julyFirst = new Date(year, 6, 1);
      return today < julyFirst ? new Date(year, 0, 1) : new Date(year, 5, 1);
    }

    function decimalMonthsBetween(start, end) {
      const safeStart = startOfDay(start);
      const safeEnd = startOfDay(end);
      if (safeEnd.getTime() <= safeStart.getTime()) return 0;

      let wholeMonths = (safeEnd.getFullYear() - safeStart.getFullYear()) * 12
        + (safeEnd.getMonth() - safeStart.getMonth());
      let wholeDate = addDecimalMonths(safeStart, wholeMonths);
      while (wholeMonths > 0 && wholeDate.getTime() > safeEnd.getTime()) {
        wholeMonths -= 1;
        wholeDate = addDecimalMonths(safeStart, wholeMonths);
      }

      const remainderDays = Math.max(0, diffProposalDays(wholeDate, safeEnd));
      return wholeMonths + (remainderDays / 30);
    }

    function setProposalReadonly(input, locked, options) {
      if (!input) return;
      input.readOnly = locked;
      input.classList.toggle('readonly-field', locked);
      if (locked) {
        input.setAttribute('readonly', '');
        input.tabIndex = -1;
      } else {
        input.removeAttribute('readonly');
        input.removeAttribute('tabindex');
      }
      if (options?.lockPicker) {
        if (input._flatpickr) {
          input._flatpickr.set('clickOpens', !locked);
        }
        input.style.pointerEvents = locked ? 'none' : '';
      }
    }

    function formatProposalDateIso(date) {
      const year = String(date.getFullYear()).padStart(4, '0');
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      return year + '-' + month + '-' + day;
    }

    function syncProposalReportDates(force) {
      const preliminaryDateInput = form.querySelector('input[name="preliminary_report_date"]');
      const finalDateInput = form.querySelector('input[name="final_report_date"]');
      const serviceTermInput = form.querySelector('[name="service_term_months"]');
      const finalReportWeeksInput = form.querySelector('[name="final_report_term_weeks"]');
      if (!preliminaryDateInput || !finalDateInput || !serviceTermInput || !finalReportWeeksInput) return;

      const preliminaryMonths = normalizeProposalDecimalInputValue(serviceTermInput);
      const finalWeeks = normalizeProposalDecimalInputValue(finalReportWeeksInput);
      if (preliminaryMonths === null || finalWeeks === null) return;

      const preliminaryDateValue = String(preliminaryDateInput.value || '').trim();
      const finalDateValue = String(finalDateInput.value || '').trim();
      if (!force) {
        if (preliminaryDateValue && finalDateValue) {
          return;
        }
        if (preliminaryDateValue && !finalDateValue) {
          syncProposalFinalDateFromPreliminary();
          return;
        }
        if (!preliminaryDateValue && finalDateValue) {
          syncProposalPreliminaryDateFromFinal();
          return;
        }
      }

      const baseStartDate = getNearestMonday(addDays(new Date(), 14));
      const preliminaryDate = addDecimalMonths(baseStartDate, preliminaryMonths);
      const finalDate = addDecimalWeeks(preliminaryDate, finalWeeks);
      setDateFieldValue(preliminaryDateInput, formatProposalDateIso(preliminaryDate));
      setDateFieldValue(finalDateInput, formatProposalDateIso(finalDate));
    }

    function syncProposalFinalDateFromPreliminary() {
      const preliminaryDateInput = form.querySelector('input[name="preliminary_report_date"]');
      const finalDateInput = form.querySelector('input[name="final_report_date"]');
      const finalReportWeeksInput = form.querySelector('[name="final_report_term_weeks"]');
      if (!preliminaryDateInput || !finalDateInput || !finalReportWeeksInput) return;

      const preliminaryDate = parseProposalDate(preliminaryDateInput.value);
      const finalWeeks = normalizeProposalDecimalInputValue(finalReportWeeksInput);
      if (!preliminaryDate || finalWeeks === null) return;
      setDateFieldValue(finalDateInput, formatProposalDateIso(addDecimalWeeks(preliminaryDate, finalWeeks)));
    }

    function syncProposalPreliminaryDateFromFinal() {
      const preliminaryDateInput = form.querySelector('input[name="preliminary_report_date"]');
      const finalDateInput = form.querySelector('input[name="final_report_date"]');
      const finalReportWeeksInput = form.querySelector('[name="final_report_term_weeks"]');
      if (!preliminaryDateInput || !finalDateInput || !finalReportWeeksInput) return;

      const finalDate = parseProposalDate(finalDateInput.value);
      const finalWeeks = normalizeProposalDecimalInputValue(finalReportWeeksInput);
      if (!finalDate || finalWeeks === null) return;
      setDateFieldValue(preliminaryDateInput, formatProposalDateIso(subtractDecimalWeeks(finalDate, finalWeeks)));
    }

    function syncProposalTermsFromDates() {
      const preliminaryDateInput = form.querySelector('input[name="preliminary_report_date"]');
      const finalDateInput = form.querySelector('input[name="final_report_date"]');
      const serviceTermInput = form.querySelector('[name="service_term_months"]');
      const finalReportWeeksInput = form.querySelector('[name="final_report_term_weeks"]');
      if (!preliminaryDateInput || !finalDateInput || !serviceTermInput || !finalReportWeeksInput) return;

      const preliminaryDate = parseProposalDate(preliminaryDateInput.value);
      const finalDate = parseProposalDate(finalDateInput.value);
      if (preliminaryDate) {
        const months = decimalMonthsBetween(getProposalBaseStartDate(), preliminaryDate);
        serviceTermInput.value = formatProposalDecimal(months);
      } else {
        serviceTermInput.value = '';
      }

      if (preliminaryDate && finalDate) {
        const weeks = Math.max(0, diffProposalDays(preliminaryDate, finalDate) / 7);
        finalReportWeeksInput.value = formatProposalDecimal(weeks);
      } else {
        finalReportWeeksInput.value = '';
      }
    }

    let proposalReportTermsEditMode = false;

    function applyProposalReportTermsLockState() {
      const lockIcons = qa('.js-proposal-report-terms-lock', form);
      const stageRows = qa('.proposal-stage-terms-row', form);
      if (stageRows.length) {
        stageRows.forEach(function (row) {
          setProposalReadonly(row.querySelector('.proposal-stage-preliminary-report-date'), proposalReportTermsEditMode, { lockPicker: true });
          setProposalReadonly(row.querySelector('.proposal-stage-final-report-date'), proposalReportTermsEditMode, { lockPicker: true });
          setProposalReadonly(row.querySelector('.proposal-stage-service-term-months'), !proposalReportTermsEditMode);
          setProposalReadonly(row.querySelector('.proposal-stage-final-report-term-weeks'), !proposalReportTermsEditMode);
        });
        lockIcons.forEach(function (icon) {
          icon.classList.toggle('bi-lock-fill', !proposalReportTermsEditMode);
          icon.classList.toggle('bi-unlock-fill', proposalReportTermsEditMode);
          icon.title = proposalReportTermsEditMode
            ? 'Заблокировать ввод сроков'
            : 'Разблокировать ввод сроков';
        });
        return;
      }

      const preliminaryDateInput = form.querySelector('input[name="preliminary_report_date"]');
      const finalDateInput = form.querySelector('input[name="final_report_date"]');
      const serviceTermInput = form.querySelector('[name="service_term_months"]');
      const finalReportWeeksInput = form.querySelector('[name="final_report_term_weeks"]');
      if (!preliminaryDateInput || !finalDateInput || !serviceTermInput || !finalReportWeeksInput) return;

      if (proposalReportTermsEditMode) {
        syncProposalTermsFromDates();
      }

      setProposalReadonly(preliminaryDateInput, proposalReportTermsEditMode, { lockPicker: true });
      setProposalReadonly(finalDateInput, proposalReportTermsEditMode, { lockPicker: true });
      setProposalReadonly(serviceTermInput, !proposalReportTermsEditMode);
      setProposalReadonly(finalReportWeeksInput, !proposalReportTermsEditMode);

      lockIcons.forEach(function (icon) {
        icon.classList.toggle('bi-lock-fill', !proposalReportTermsEditMode);
        icon.classList.toggle('bi-unlock-fill', proposalReportTermsEditMode);
        icon.title = proposalReportTermsEditMode
          ? 'Заблокировать ввод сроков'
          : 'Разблокировать ввод сроков';
      });
    }

    function attachProposalStageProducts(assetsApi) {
      const container = form.querySelector('#proposal-products-container');
      const addBtn = form.querySelector('#proposal-add-product');
      const metaEl = form.querySelector('#proposal-type-meta');
      const serviceStagesContainer = form.querySelector('#proposal-service-stages-container');
      const commercialStagesContainer = form.querySelector('#proposal-commercial-stages-container');
      const termsTbody = form.querySelector('#proposal-stage-terms-tbody');
      if (!container || !addBtn || !metaEl || !serviceStagesContainer || !commercialStagesContainer || !termsTbody) return null;
      if (form.dataset.stageProductsBound === '1') return form.__proposalStageProductsApi || null;
      form.dataset.stageProductsBound = '1';

      let meta = {};
      try {
        meta = JSON.parse(metaEl.textContent || '{}');
      } catch (error) {
        meta = {};
      }
      const products = Array.isArray(meta.products) ? meta.products : [];
      const consultingTypes = Array.isArray(meta.consulting_types) ? meta.consulting_types : [];
      const serviceCategories = Array.isArray(meta.service_categories) ? meta.service_categories : [];
      const productById = new Map(products.map(function (product) { return [String(product.id), product]; }));
      form.__proposalStageUidCounter = form.__proposalStageUidCounter || (getProductRowsInitialMaxStageUid() + 1);

      function getProductRowsInitialMaxStageUid() {
        return Array.from(container.querySelectorAll('.proposal-product-row')).reduce(function (maxValue, row, index) {
          const raw = String(row.dataset.stageUid || (index + 1));
          const numeric = Number.parseInt(raw, 10);
          return Number.isFinite(numeric) ? Math.max(maxValue, numeric) : maxValue;
        }, 0);
      }

      function nextStageUid() {
        const uid = form.__proposalStageUidCounter || 1;
        form.__proposalStageUidCounter = uid + 1;
        return String(uid);
      }

      function getProductRows() {
        return Array.from(container.querySelectorAll('.proposal-product-row'));
      }

      function getServiceBlocks() {
        return Array.from(serviceStagesContainer.querySelectorAll('[data-proposal-stage-kind="service"]'));
      }

      function getCommercialBlocks() {
        return Array.from(commercialStagesContainer.querySelectorAll('[data-proposal-stage-kind="commercial"]'));
      }

      function getSummaryCommercialBlock() {
        return commercialStagesContainer.querySelector('[data-proposal-stage-kind="commercial-summary"]');
      }

      function getStageTermRows() {
        return Array.from(termsTbody.querySelectorAll('.proposal-stage-terms-row'));
      }

      function getTotalsRow() {
        return termsTbody.querySelector('.proposal-stage-terms-total-row');
      }

      function getAssetRows() {
        return assetsApi ? assetsApi.getSerializedRows() : [];
      }

      function uniqueValues(items) {
        const seen = new Set();
        return items.filter(function (item) {
          const value = String(item || '').trim();
          if (!value || seen.has(value)) return false;
          seen.add(value);
          return true;
        });
      }

      function buildOptions(select, items, placeholder, selectedValue, mapper) {
        if (!select) return;
        const normalizedSelected = String(selectedValue || '');
        select.innerHTML = '';
        if (placeholder) {
          const option = document.createElement('option');
          option.value = '';
          option.textContent = placeholder;
          select.appendChild(option);
        }
        items.forEach(function (item) {
          const option = document.createElement('option');
          const mapped = mapper ? mapper(item) : { value: item, label: item };
          option.value = String(mapped.value || '');
          option.textContent = mapped.label || '';
          select.appendChild(option);
        });
        select.value = normalizedSelected;
        if (select.value !== normalizedSelected) select.value = '';
      }

      function filteredProducts(consultingType, serviceCategory, serviceSubtype) {
        return products.filter(function (product) {
          if (consultingType && product.consulting_type !== consultingType) return false;
          if (serviceCategory && product.service_category !== serviceCategory) return false;
          if (serviceSubtype && product.service_subtype !== serviceSubtype) return false;
          return true;
        });
      }

      function resetClonedStageBlock(block) {
        block.querySelectorAll('tbody').forEach(function (tbody) {
          tbody.innerHTML = '';
        });
        block.querySelectorAll('input[type="hidden"]').forEach(function (input) {
          if (input.matches('[data-proposal-stage-type]')) {
            input.value = '';
            return;
          }
          if (input.name === 'service_composition_mode') {
            input.value = 'sections';
            return;
          }
          if (input.name === 'commercial_totals_payload') {
            input.value = JSON.stringify(normalizeProposalCommercialTotalsState({}));
            return;
          }
          input.value = '';
        });
        block.querySelectorAll('textarea').forEach(function (textarea) {
          textarea.value = '';
        });
        block.querySelectorAll('input:not([type="hidden"])').forEach(function (input) {
          if (input.classList.contains('proposal-stage-label-input')) return;
          if (input.type === 'checkbox') {
            input.checked = false;
            return;
          }
          input.value = '';
        });
        delete block.__proposalServiceSectionsTableApi;
        delete block.__proposalServiceTextEditorApi;
        delete block.__proposalCommercialTableApi;
        delete block.dataset.serviceSectionsBound;
        delete block.dataset.serviceTextEditorBound;
        delete block.dataset.commercialBound;
        delete block.dataset.commercialSharedRateBound;
        delete block.dataset.proposalCommercialRateMaster;
        delete block.dataset.summarySyncBound;
      }

      function cloneStageBlock(block) {
        const clone = block.cloneNode(true);
        resetClonedStageBlock(clone);
        return clone;
      }

      function cloneTermsRow(row) {
        const clone = row.cloneNode(true);
        delete clone.dataset.eventsBound;
        delete clone.dataset.manualDateSource;
        delete clone.dataset.forceDatesFromTerms;
        clone.querySelectorAll('input').forEach(function (input) {
          delete input.dataset.hasPicker;
          if (!input.classList.contains('proposal-stage-label-input')) {
            input.value = '';
          }
        });
        return clone;
      }

      function ensureMirroredBlocks() {
        let serviceBlocks = getServiceBlocks();
        while (serviceBlocks.length < getProductRows().length && serviceBlocks.length) {
          const clone = cloneStageBlock(serviceBlocks[serviceBlocks.length - 1]);
          serviceStagesContainer.appendChild(clone);
          serviceBlocks = getServiceBlocks();
        }
        while (serviceBlocks.length > getProductRows().length && serviceBlocks.length > 1) {
          serviceBlocks[serviceBlocks.length - 1].remove();
          serviceBlocks = getServiceBlocks();
        }

        let commercialBlocks = getCommercialBlocks();
        while (commercialBlocks.length < getProductRows().length && commercialBlocks.length) {
          const clone = cloneStageBlock(commercialBlocks[commercialBlocks.length - 1]);
          const summaryCommercialBlock = getSummaryCommercialBlock();
          if (summaryCommercialBlock) {
            commercialStagesContainer.insertBefore(clone, summaryCommercialBlock);
          } else {
            commercialStagesContainer.appendChild(clone);
          }
          commercialBlocks = getCommercialBlocks();
        }
        while (commercialBlocks.length > getProductRows().length && commercialBlocks.length > 1) {
          commercialBlocks[commercialBlocks.length - 1].remove();
          commercialBlocks = getCommercialBlocks();
        }

        let termRows = getStageTermRows();
        while (termRows.length < getProductRows().length && termRows.length) {
          termsTbody.insertBefore(cloneTermsRow(termRows[termRows.length - 1]), getTotalsRow());
          termRows = getStageTermRows();
        }
        while (termRows.length > getProductRows().length && termRows.length > 1) {
          termRows[termRows.length - 1].remove();
          termRows = getStageTermRows();
        }
      }

      function syncStageLabels() {
        const productRows = getProductRows();
        const serviceBlocks = getServiceBlocks();
        const commercialBlocks = getCommercialBlocks();
        const termRows = getStageTermRows();
        const hasMultipleStages = productRows.length > 1;
        const summaryCommercialBlock = getSummaryCommercialBlock();
        function buildStageTitle(baseTitle, rank, productId) {
          if (!hasMultipleStages) return baseTitle;
          const product = productById.get(String(productId || '').trim()) || null;
          const shortLabel = String(product?.short_label || '').trim();
          return shortLabel
            ? baseTitle + ': Этап ' + rank + ' ' + shortLabel
            : baseTitle + ': Этап ' + rank;
        }
        productRows.forEach(function (row, index) {
          const rank = index + 1;
          if (!row.dataset.stageUid) row.dataset.stageUid = nextStageUid();
          const stageUid = row.dataset.stageUid;
          const productId = String(row.querySelector('.proposal-product-select')?.value || '').trim();
          row.querySelector('.proposal-product-badge').textContent = rank;
          const serviceBlock = serviceBlocks[index];
          const commercialBlock = commercialBlocks[index];
          const termRow = termRows[index];
          [serviceBlock, commercialBlock].forEach(function (block) {
            if (!block) return;
            block.dataset.proposalStageKey = stageUid;
            if (block.dataset.proposalStageKind === 'commercial') {
              block.dataset.proposalCommercialRateMaster = index === 0 ? '1' : '0';
            }
            block.querySelectorAll('.proposal-stage-block-title').forEach(function (title) {
              if (block.dataset.proposalStageKind === 'service') {
                title.textContent = buildStageTitle('Состав услуг / техническое задание', rank, productId);
              } else {
                title.textContent = buildStageTitle('Коммерческое предложение', rank, productId);
              }
            });
          });
          if (termRow) {
            termRow.dataset.proposalStageKey = stageUid;
            const stageInput = termRow.querySelector('.proposal-stage-label-input');
            if (stageInput) stageInput.value = 'Этап ' + rank;
          }
        });
        if (summaryCommercialBlock) {
          summaryCommercialBlock.classList.toggle('d-none', !hasMultipleStages);
          summaryCommercialBlock.dataset.proposalStageKey = 'summary';
          summaryCommercialBlock.dataset.proposalCommercialRateMaster = '0';
          summaryCommercialBlock.querySelectorAll('.proposal-stage-block-title').forEach(function (title) {
            title.textContent = 'Коммерческое предложение: все этапы';
          });
        }
        getTotalsRow()?.classList.toggle('d-none', productRows.length <= 1);
      }

      function bindProductRow(row) {
        if (!row || row.dataset.eventsBound === '1') return;
        if (!row.dataset.stageUid) row.dataset.stageUid = nextStageUid();
        row.dataset.eventsBound = '1';
        const consultingSelect = row.querySelector('.proposal-consulting-select');
        const categorySelect = row.querySelector('.proposal-service-category-select');
        const subtypeSelect = row.querySelector('.proposal-service-subtype-select');
        const productSelect = row.querySelector('.proposal-product-select');

        function syncRow(state) {
          const selectedProduct = productById.get(String(state?.productId ?? productSelect?.value ?? ''));
          let consultingValue = String(state?.consultingType ?? consultingSelect?.value ?? '');
          let categoryValue = String(state?.serviceCategory ?? categorySelect?.value ?? '');
          let subtypeValue = String(state?.serviceSubtype ?? subtypeSelect?.value ?? '');
          let productValue = String(state?.productId ?? productSelect?.value ?? '');
          if (selectedProduct) {
            consultingValue = selectedProduct.consulting_type || consultingValue;
            categoryValue = selectedProduct.service_category || categoryValue;
            subtypeValue = selectedProduct.service_subtype || subtypeValue;
            productValue = String(selectedProduct.id);
          }
          buildOptions(consultingSelect, consultingTypes, '— выберите вид консалтинга —', consultingValue);
          consultingValue = consultingSelect?.value || '';
          const categoryOptions = uniqueValues(filteredProducts(consultingValue, '', '').map(function (product) {
            return product.service_category;
          }));
          const orderedCategories = serviceCategories.filter(function (value) { return categoryOptions.includes(value); });
          const extraCategories = categoryOptions.filter(function (value) { return !orderedCategories.includes(value); });
          buildOptions(
            categorySelect,
            orderedCategories.concat(extraCategories),
            consultingValue ? '— выберите тип услуги —' : '— выберите вид консалтинга —',
            categoryValue
          );
          categoryValue = categorySelect?.value || '';
          const subtypeOptions = uniqueValues(filteredProducts(consultingValue, categoryValue, '').map(function (product) {
            return product.service_subtype;
          }));
          buildOptions(
            subtypeSelect,
            subtypeOptions,
            categoryValue ? '— выберите подтип услуги —' : '— выберите тип услуги —',
            subtypeValue
          );
          subtypeValue = subtypeSelect?.value || '';
          buildOptions(
            productSelect,
            filteredProducts(consultingValue, categoryValue, subtypeValue),
            '— выберите продукт —',
            productValue,
            function (product) {
              return { value: product.id, label: product.label };
            }
          );
          const displayProduct = productById.get(String(productSelect?.value || ''));
          const productDisplay = row.querySelector('.proposal-product-display');
          if (productDisplay) {
            productDisplay.textContent = displayProduct?.short_label || '— выберите продукт —';
            productDisplay.classList.toggle('is-placeholder', !displayProduct);
          }
          row.dataset.selectedConsultingType = consultingValue;
          row.dataset.selectedServiceCategory = categoryValue;
          row.dataset.selectedServiceSubtype = subtypeValue;
          row.dataset.selectedProductId = productSelect?.value || '';
        }

        consultingSelect?.addEventListener('change', function () {
          syncRow({ consultingType: consultingSelect.value, serviceCategory: '', serviceSubtype: '', productId: '' });
          syncStageContent();
        });
        categorySelect?.addEventListener('change', function () {
          syncRow({ consultingType: consultingSelect?.value || '', serviceCategory: categorySelect.value, serviceSubtype: '', productId: '' });
          syncStageContent();
        });
        subtypeSelect?.addEventListener('change', function () {
          syncRow({ consultingType: consultingSelect?.value || '', serviceCategory: categorySelect?.value || '', serviceSubtype: subtypeSelect.value, productId: '' });
          syncStageContent();
        });
        productSelect?.addEventListener('change', function () {
          syncRow({ productId: productSelect.value });
          syncStageContent();
        });

        syncRow({
          consultingType: row.dataset.selectedConsultingType || '',
          serviceCategory: row.dataset.selectedServiceCategory || '',
          serviceSubtype: row.dataset.selectedServiceSubtype || '',
          productId: row.dataset.selectedProductId || '',
        });
      }

      function bindTermsRows() {
        getStageTermRows().forEach(function (row) {
          if (row.dataset.eventsBound === '1') return;
          row.dataset.eventsBound = '1';
          row.querySelectorAll('.js-date').forEach(function (input) {
            initProposalDateInput(input);
          });
          const monthsInput = row.querySelector('.proposal-stage-service-term-months');
          const weeksInput = row.querySelector('.proposal-stage-final-report-term-weeks');
          normalizeProposalDecimalInputValue(monthsInput);
          normalizeProposalDecimalInputValue(weeksInput);
          ['input', 'change'].forEach(function (eventName) {
            row.querySelector('.proposal-stage-evaluation-date')?.addEventListener(eventName, function () {
              syncStageEvaluationDates(row.querySelector('.proposal-stage-evaluation-date')?.value || '');
            });
            monthsInput?.addEventListener(eventName, function () {
              syncStageTerms();
              if (eventName === 'change') normalizeProposalDecimalInputValue(monthsInput);
            });
            weeksInput?.addEventListener(eventName, function () {
              syncStageTerms();
              if (eventName === 'change') normalizeProposalDecimalInputValue(weeksInput);
            });
            row.querySelector('.proposal-stage-preliminary-report-date')?.addEventListener(eventName, function () {
              if (!proposalReportTermsEditMode) {
                row.dataset.manualDateSource = 'preliminary';
                syncStageTerms();
              }
            });
            row.querySelector('.proposal-stage-final-report-date')?.addEventListener(eventName, function () {
              if (!proposalReportTermsEditMode) {
                row.dataset.manualDateSource = 'final';
                syncStageTerms();
              }
            });
          });
        });
      }

      function getSharedEvaluationDateValue(preferredValue) {
        const preferredDate = parseProposalDate(preferredValue);
        if (preferredDate) return formatProposalDateIso(preferredDate);
        const firstInput = getStageTermRows()[0]?.querySelector('.proposal-stage-evaluation-date');
        const firstDate = parseProposalDate(firstInput?.value) || getProposalDefaultEvaluationDate();
        return formatProposalDateIso(firstDate);
      }

      function syncStageEvaluationDates(preferredValue) {
        const sharedValue = getSharedEvaluationDateValue(preferredValue);
        getStageTermRows().forEach(function (row) {
          const evaluationInput = row.querySelector('.proposal-stage-evaluation-date');
          if (evaluationInput) {
            setDateFieldValue(evaluationInput, sharedValue);
          }
        });
      }

      function ensureStageEditorsInitialized() {
        getServiceBlocks().forEach(function (block) {
          attachProposalServiceSectionsTable(block);
          attachProposalServiceTextEditor(block);
        });
        getCommercialBlocks().forEach(function (block) {
          attachProposalCommercialTable(block, assetsApi);
        });
        const summaryCommercialBlock = getSummaryCommercialBlock();
        if (summaryCommercialBlock) {
          attachProposalCommercialTable(summaryCommercialBlock, assetsApi);
        }
      }

      function parseCommercialTotalsPayload(block) {
        try {
          return normalizeProposalCommercialTotalsState(
            JSON.parse(block?.querySelector('#proposal-commercial-totals-payload')?.value || '{}')
          );
        } catch (error) {
          return normalizeProposalCommercialTotalsState({});
        }
      }

      function parseCommercialOfferPayload(block) {
        try {
          const data = JSON.parse(block?.querySelector('#proposal-commercial-offer-payload')?.value || '[]');
          return Array.isArray(data) ? data : [];
        } catch (error) {
          return [];
        }
      }

      function getSummaryCommercialRowOrder() {
        const summaryCommercialBlock = getSummaryCommercialBlock();
        const rows = parseCommercialOfferPayload(summaryCommercialBlock);
        const order = new Map();
        rows.forEach(function (row, index) {
          if (isProposalTravelExpensesRow(row)) return;
          const key = String(row?.specialist || '').trim() + '\u0000' + String(row?.job_title || '').trim();
          if (key && !order.has(key)) {
            order.set(key, index);
          }
        });
        return order;
      }

      function buildSummaryCommercialRows() {
        const assetCount = Math.max(getAssetRows().length, 1);
        const groupedRows = [];
        const groupedByKey = new Map();
        const preferredOrder = getSummaryCommercialRowOrder();
        const travelDayTotals = Array.from({ length: assetCount }, function () { return 0; });
        let travelTotal = 0;
        let hasTravelCalculation = false;
        let hasTravelActual = false;
        let hasTravelData = false;

        getCommercialBlocks().forEach(function (block) {
          const api = attachProposalCommercialTable(block, assetsApi);
          const rows = Array.isArray(api?.getSerializedRows?.()) ? api.getSerializedRows() : [];
          const totalsState = parseCommercialTotalsPayload(block);
          const travelMode = normalizeProposalTravelExpensesMode(totalsState.travel_expenses_mode) || PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL;
          rows.forEach(function (row) {
            if (isProposalTravelExpensesRow(row)) {
              const totalValue = parseFloat(rawMoney(row?.total_eur_without_vat || ''));
              if (Number.isFinite(totalValue)) {
                travelTotal += totalValue;
                hasTravelData = true;
              }
              if (travelMode === PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION) {
                hasTravelCalculation = true;
                (Array.isArray(row?.asset_day_counts) ? row.asset_day_counts : []).slice(0, assetCount).forEach(function (value, index) {
                  const numericValue = parseFloat(rawMoney(value || ''));
                  if (Number.isFinite(numericValue)) {
                    travelDayTotals[index] += numericValue;
                    hasTravelData = true;
                  }
                });
              } else if (totalValue || String(row?.total_eur_without_vat || '').trim()) {
                hasTravelActual = true;
              }
              return;
            }

            const specialist = String(row?.specialist || '').trim();
            const jobTitle = String(row?.job_title || '').trim();
            const key = specialist + '\u0000' + jobTitle;
            let bucket = groupedByKey.get(key);
            if (!bucket) {
              bucket = {
                specialist: specialist,
                job_title: jobTitle,
                professional_status: String(row?.professional_status || '').trim(),
                service_name: '',
                rate_eur_per_day: String(row?.rate_eur_per_day || '').trim(),
                asset_day_counts: Array.from({ length: assetCount }, function () { return 0; }),
                total_eur_without_vat: 0,
              };
              groupedByKey.set(key, bucket);
              groupedRows.push(bucket);
            }
            (Array.isArray(row?.asset_day_counts) ? row.asset_day_counts : []).slice(0, assetCount).forEach(function (value, index) {
              const numericValue = parseInt(String(value || '').trim(), 10);
              if (Number.isFinite(numericValue)) {
                bucket.asset_day_counts[index] += numericValue;
              }
            });
            const totalValue = parseFloat(rawMoney(row?.total_eur_without_vat || ''));
            if (Number.isFinite(totalValue)) {
              bucket.total_eur_without_vat += totalValue;
            }
          });
        });

        const rows = groupedRows.map(function (bucket, index) {
          return {
            specialist: bucket.specialist,
            job_title: bucket.job_title,
            professional_status: bucket.professional_status,
            service_name: '',
            rate_eur_per_day: bucket.rate_eur_per_day,
            asset_day_counts: bucket.asset_day_counts.map(function (value) { return value > 0 ? String(value) : ''; }),
            total_eur_without_vat: bucket.total_eur_without_vat > 0 ? bucket.total_eur_without_vat.toFixed(2) : '',
            __summaryOrderIndex: index,
          };
        });

        rows.sort(function (left, right) {
          const leftKey = String(left?.specialist || '').trim() + '\u0000' + String(left?.job_title || '').trim();
          const rightKey = String(right?.specialist || '').trim() + '\u0000' + String(right?.job_title || '').trim();
          const leftOrder = preferredOrder.has(leftKey) ? preferredOrder.get(leftKey) : Number.MAX_SAFE_INTEGER;
          const rightOrder = preferredOrder.has(rightKey) ? preferredOrder.get(rightKey) : Number.MAX_SAFE_INTEGER;
          if (leftOrder !== rightOrder) return leftOrder - rightOrder;
          return (left.__summaryOrderIndex || 0) - (right.__summaryOrderIndex || 0);
        });

        const serializedRows = rows.map(function (row) {
          return {
            specialist: row.specialist,
            job_title: row.job_title,
            professional_status: row.professional_status,
            service_name: row.service_name,
            rate_eur_per_day: row.rate_eur_per_day,
            asset_day_counts: row.asset_day_counts,
            total_eur_without_vat: row.total_eur_without_vat,
          };
        });

        const travelMode = (
          hasTravelCalculation && !hasTravelActual
            ? PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION
            : PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL
        );
        if (hasTravelData) {
          serializedRows.push({
            specialist: '',
            job_title: '',
            professional_status: '',
            service_name: PROPOSAL_TRAVEL_EXPENSES_LABEL,
            rate_eur_per_day: '',
            asset_day_counts: travelMode === PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION
              ? travelDayTotals.map(function (value) { return value > 0 ? fmtMoney(value.toFixed(2)) : ''; })
              : Array.from({ length: assetCount }, function () { return ''; }),
            total_eur_without_vat: travelTotal > 0 ? travelTotal.toFixed(2) : '',
          });
        }

        return {
          rows: serializedRows,
          travelMode: travelMode,
        };
      }

      function syncSummaryCommercialBlock() {
        const summaryCommercialBlock = getSummaryCommercialBlock();
        const hasMultipleStages = getProductRows().length > 1;
        if (!summaryCommercialBlock) return;
        summaryCommercialBlock.classList.toggle('d-none', !hasMultipleStages);
        if (!hasMultipleStages) return;
        const summaryApi = attachProposalCommercialTable(summaryCommercialBlock, assetsApi);
        if (!summaryApi) return;
        const summaryPayload = buildSummaryCommercialRows();
        const totalsInput = summaryCommercialBlock.querySelector('#proposal-commercial-totals-payload');
        const totalsState = parseCommercialTotalsPayload(summaryCommercialBlock);
        totalsState.travel_expenses_mode = summaryPayload.travelMode;
        if (totalsInput) {
          totalsInput.value = JSON.stringify(normalizeProposalCommercialTotalsState(totalsState));
        }
        summaryApi.replaceRows(summaryPayload.rows, { reason: 'summary-sync' });
      }

      function bindSummaryCommercialSync() {
        getCommercialBlocks().forEach(function (block) {
          if (block.dataset.summarySyncBound === '1') return;
          block.dataset.summarySyncBound = '1';
          block.addEventListener('proposal-commercial-changed', function () {
            syncSummaryCommercialBlock();
          });
        });
      }

      function syncStageTerms() {
        const termRows = getStageTermRows();
        const states = termRows.map(function (row) {
          const monthsInput = row.querySelector('.proposal-stage-service-term-months');
          const weeksInput = row.querySelector('.proposal-stage-final-report-term-weeks');
          const months = normalizeProposalDecimalInputValue(monthsInput);
          const weeks = normalizeProposalDecimalInputValue(weeksInput);
          return {
            row: row,
            monthsInput: monthsInput,
            preliminaryInput: row.querySelector('.proposal-stage-preliminary-report-date'),
            weeksInput: weeksInput,
            finalInput: row.querySelector('.proposal-stage-final-report-date'),
            months: months,
            weeks: weeks,
            preliminaryDate: parseProposalDate(row.querySelector('.proposal-stage-preliminary-report-date')?.value),
            finalDate: parseProposalDate(row.querySelector('.proposal-stage-final-report-date')?.value),
            shouldForceDatesFromTerms: row.dataset.forceDatesFromTerms === '1',
            manualDateSource: String(row.dataset.manualDateSource || '').trim(),
            calculatedPreliminaryDate: null,
            calculatedFinalDate: null,
          };
        });

        function applyStateDates(state) {
          setDateFieldValue(
            state.preliminaryInput,
            state.calculatedPreliminaryDate ? formatProposalDateIso(state.calculatedPreliminaryDate) : ''
          );
          setDateFieldValue(
            state.finalInput,
            state.calculatedFinalDate ? formatProposalDateIso(state.calculatedFinalDate) : ''
          );
        }

        function computeForwardDates(startDate, state) {
          if (state.months === null) {
            state.calculatedPreliminaryDate = null;
            state.calculatedFinalDate = null;
            return startDate;
          }
          state.calculatedPreliminaryDate = addDecimalMonths(startDate, state.months);
          if (state.weeks === null) {
            state.calculatedFinalDate = null;
            return state.calculatedPreliminaryDate;
          }
          state.calculatedFinalDate = addDecimalWeeks(state.calculatedPreliminaryDate, state.weeks);
          return state.calculatedFinalDate;
        }

        if (proposalReportTermsEditMode) {
          let startDate = form.__proposalStageBaseStartDate || getProposalBaseStartDate();
          states.forEach(function (state) {
            startDate = computeForwardDates(startDate, state);
            applyStateDates(state);
            delete state.row.dataset.forceDatesFromTerms;
            delete state.row.dataset.manualDateSource;
          });
        } else {
          let baseStartDate = form.__proposalStageBaseStartDate || getProposalBaseStartDate();
          const manualIndex = states.findIndex(function (state) {
            if (state.manualDateSource === 'preliminary') return !!state.preliminaryDate && state.months !== null;
            if (state.manualDateSource === 'final') return !!state.finalDate && state.weeks !== null;
            return false;
          });

          if (manualIndex >= 0) {
            const manualState = states[manualIndex];
            let manualStageStartDate = null;
            if (manualState.manualDateSource === 'preliminary') {
              manualState.calculatedPreliminaryDate = manualState.preliminaryDate;
              manualState.calculatedFinalDate = manualState.weeks !== null
                ? addDecimalWeeks(manualState.preliminaryDate, manualState.weeks)
                : null;
              manualStageStartDate = manualState.preliminaryDate && manualState.months !== null
                ? subtractDecimalMonths(manualState.preliminaryDate, manualState.months)
                : null;
            } else {
              manualState.calculatedFinalDate = manualState.finalDate;
              manualState.calculatedPreliminaryDate = manualState.weeks !== null
                ? subtractDecimalWeeks(manualState.finalDate, manualState.weeks)
                : null;
              manualStageStartDate = manualState.calculatedPreliminaryDate && manualState.months !== null
                ? subtractDecimalMonths(manualState.calculatedPreliminaryDate, manualState.months)
                : null;
            }

            let rollingStartDate = manualStageStartDate;

            for (let index = manualIndex - 1; index >= 0; index -= 1) {
              const state = states[index];
              state.calculatedFinalDate = rollingStartDate;
              state.calculatedPreliminaryDate = rollingStartDate && state.weeks !== null
                ? subtractDecimalWeeks(rollingStartDate, state.weeks)
                : null;
              rollingStartDate = state.calculatedPreliminaryDate && state.months !== null
                ? subtractDecimalMonths(state.calculatedPreliminaryDate, state.months)
                : rollingStartDate;
            }

            if (rollingStartDate) {
              baseStartDate = rollingStartDate;
              form.__proposalStageBaseStartDate = baseStartDate;
            }

            let forwardStartDate = manualState.calculatedFinalDate || manualState.calculatedPreliminaryDate || manualStageStartDate || baseStartDate;
            for (let index = manualIndex + 1; index < states.length; index += 1) {
              const state = states[index];
              forwardStartDate = computeForwardDates(forwardStartDate, state);
            }

            states.forEach(applyStateDates);
          } else {
            let startDate = baseStartDate;
            states.forEach(function (state) {
              const shouldComputeFromTerms = state.shouldForceDatesFromTerms || (!state.preliminaryDate && !state.finalDate);
              if (shouldComputeFromTerms) {
                startDate = computeForwardDates(startDate, state);
                applyStateDates(state);
              } else {
                startDate = state.finalDate || state.preliminaryDate || startDate;
              }
            });
          }

          states.forEach(function (state) {
            delete state.row.dataset.forceDatesFromTerms;
            delete state.row.dataset.manualDateSource;
          });
        }
        const totalsRow = getTotalsRow();
        if (!totalsRow) return;
        const totalMonths = termRows.reduce(function (sum, row) {
          return sum + (parseProposalDecimal(row.querySelector('.proposal-stage-service-term-months')?.value) || 0);
        }, 0);
        const totalWeeks = termRows.reduce(function (sum, row) {
          return sum + (parseProposalDecimal(row.querySelector('.proposal-stage-final-report-term-weeks')?.value) || 0);
        }, 0);
        const totalMonthsInput = totalsRow.querySelector('.proposal-stage-total-service-term-months');
        const totalWeeksInput = totalsRow.querySelector('.proposal-stage-total-final-report-term-weeks');
        if (totalMonthsInput) totalMonthsInput.value = termRows.length > 1 ? formatProposalDecimal(totalMonths) : '';
        if (totalWeeksInput) totalWeeksInput.value = termRows.length > 1 ? formatProposalDecimal(totalWeeks) : '';
      }

      function syncStageContent() {
        ensureMirroredBlocks();
        syncStageLabels();
        ensureStageEditorsInitialized();
        bindSummaryCommercialSync();
        bindTermsRows();
        getProductRows().forEach(function (row, index) {
          const productId = String(row.querySelector('.proposal-product-select')?.value || '').trim();
          const serviceBlock = getServiceBlocks()[index];
          const commercialBlock = getCommercialBlocks()[index];
          const termsRow = getStageTermRows()[index];
          [serviceBlock, commercialBlock].forEach(function (block) {
            if (!block) return;
            const typeInput = block.querySelector('[data-proposal-stage-type]');
            const previousProductId = String(typeInput?.value || '').trim();
            if (typeInput) typeInput.value = productId;
            const store = attachProposalServicesStore(block);
            if (store && productId && (productId !== previousProductId || !store.getRows().length)) {
              store.replaceFromType({ reason: 'stage-product-change', source: 'type-change' });
            }
          });
          if (termsRow) {
            const termEntry = getProposalTypicalServiceTermEntry(serviceBlock || row);
            const evaluationInput = termsRow.querySelector('.proposal-stage-evaluation-date');
            const monthsInput = termsRow.querySelector('.proposal-stage-service-term-months');
            const weeksInput = termsRow.querySelector('.proposal-stage-final-report-term-weeks');
            const previousProductId = String(termsRow.dataset.productId || '');
            if (evaluationInput && (!String(evaluationInput.value || '').trim() || productId !== String(termsRow.dataset.productId || ''))) {
              setDateFieldValue(evaluationInput, getSharedEvaluationDateValue());
            }
            if (termEntry && monthsInput && weeksInput) {
              if (!String(monthsInput.value || '').trim() || productId !== previousProductId) {
                monthsInput.value = formatProposalDecimal(parseProposalDecimal(termEntry.preliminary_report_months) || 0);
              }
              if (!String(weeksInput.value || '').trim() || productId !== previousProductId) {
                weeksInput.value = formatProposalDecimal(parseProposalDecimal(termEntry.final_report_weeks) || 0);
              }
            }
            if (productId !== previousProductId) {
              termsRow.dataset.forceDatesFromTerms = '1';
            }
            termsRow.dataset.productId = productId;
          }
        });
        syncStageEvaluationDates();
        syncStageTerms();
        applyProposalReportTermsLockState();
        syncSummaryCommercialBlock();
        form.dispatchEvent(new CustomEvent('proposal-stage-products-changed'));
      }

      addBtn.addEventListener('click', function () {
        const firstRow = getProductRows()[0];
        const lastRow = getProductRows()[getProductRows().length - 1];
        const clone = lastRow ? lastRow.cloneNode(true) : null;
        if (!clone) return;
        const firstProductId = String(
          firstRow?.querySelector('.proposal-product-select')?.value
          || firstRow?.dataset?.selectedProductId
          || ''
        ).trim();
        const copiedState = firstProductId ? {
          consultingType: String(
            firstRow?.querySelector('.proposal-consulting-select')?.value
            || firstRow?.dataset?.selectedConsultingType
            || ''
          ).trim(),
          serviceCategory: String(
            firstRow?.querySelector('.proposal-service-category-select')?.value
            || firstRow?.dataset?.selectedServiceCategory
            || ''
          ).trim(),
          serviceSubtype: String(
            firstRow?.querySelector('.proposal-service-subtype-select')?.value
            || firstRow?.dataset?.selectedServiceSubtype
            || ''
          ).trim(),
        } : null;
        clone.dataset.stageUid = nextStageUid();
        clone.dataset.selectedConsultingType = copiedState?.consultingType || '';
        clone.dataset.selectedServiceCategory = copiedState?.serviceCategory || '';
        clone.dataset.selectedServiceSubtype = copiedState?.serviceSubtype || '';
        clone.dataset.selectedProductId = '';
        delete clone.dataset.eventsBound;
        container.appendChild(clone);
        bindProductRow(clone);
        syncStageContent();
      });

      container.addEventListener('click', function (event) {
        const removeBtn = event.target.closest('.proposal-product-remove');
        if (!removeBtn) return;
        const rows = getProductRows();
        const row = removeBtn.closest('.proposal-product-row');
        if (!row) return;
        if (rows.length === 1) {
          row.dataset.selectedConsultingType = '';
          row.dataset.selectedServiceCategory = '';
          row.dataset.selectedServiceSubtype = '';
          row.dataset.selectedProductId = '';
          delete row.dataset.eventsBound;
          row.querySelectorAll('select').forEach(function (select) { select.value = ''; });
          bindProductRow(row);
        } else {
          row.remove();
        }
        syncStageContent();
      });

      getProductRows().forEach(bindProductRow);
      syncStageContent();

      const api = {
        sync: syncStageContent,
      };
      form.__proposalStageProductsApi = api;
      return api;
    }

    function initCompositeProposalField(options) {
      const hiddenInput = form.querySelector(options.hiddenSelector);
      const prefixInput = form.querySelector(options.prefixSelector);
      const suffixInput = form.querySelector(options.suffixSelector);
      const assetOwnerInput = form.querySelector('input[name="asset_owner"]');
      if (!hiddenInput || !prefixInput || !suffixInput || !assetOwnerInput) return;
      const measureEl = document.createElement('span');
      measureEl.style.position = 'absolute';
      measureEl.style.visibility = 'hidden';
      measureEl.style.whiteSpace = 'pre';
      measureEl.style.pointerEvents = 'none';
      measureEl.style.left = '-9999px';
      measureEl.style.top = '-9999px';
      document.body.appendChild(measureEl);

      const initialParts = splitProposalProjectName(
        hiddenInput.value,
        assetOwnerInput.value,
        options.getFallbackFirstPart()
      );
      prefixInput.value = initialParts.firstPart;
      suffixInput.value = initialParts.secondPart;

      function syncPrefixWidth() {
        const styles = window.getComputedStyle(prefixInput);
        const text = prefixInput.value || prefixInput.placeholder || '';
        measureEl.style.font = styles.font;
        measureEl.style.fontFamily = styles.fontFamily;
        measureEl.style.fontSize = styles.fontSize;
        measureEl.style.fontWeight = styles.fontWeight;
        measureEl.style.fontStyle = styles.fontStyle;
        measureEl.style.letterSpacing = styles.letterSpacing;
        measureEl.style.textTransform = styles.textTransform;
        measureEl.textContent = text.replace(/ /g, '\u00a0');
        const paddingLeft = parseFloat(styles.paddingLeft) || 0;
        const paddingRight = parseFloat(styles.paddingRight) || 0;
        const width = Math.max(
          12,
          Math.ceil(measureEl.getBoundingClientRect().width + paddingLeft + paddingRight + 2)
        );
        prefixInput.style.width = width + 'px';
        prefixInput.style.flexBasis = width + 'px';
      }

      function syncCombinedValue() {
        hiddenInput.value = composeProposalProjectName(prefixInput.value, suffixInput.value);
        syncPrefixWidth();
      }

      function syncSuffixFromAssetOwner() {
        suffixInput.value = normalizeProposalProjectNamePart(assetOwnerInput.value);
        syncCombinedValue();
      }

      function syncPrefixFromType(force) {
        options.syncPrefixFromType(force);
        syncCombinedValue();
      }

      prefixInput.addEventListener('input', syncCombinedValue);
      prefixInput.addEventListener('change', syncCombinedValue);
      suffixInput.addEventListener('input', syncCombinedValue);
      suffixInput.addEventListener('change', syncCombinedValue);
      assetOwnerInput.addEventListener('input', syncSuffixFromAssetOwner);
      assetOwnerInput.addEventListener('change', syncSuffixFromAssetOwner);
      form.addEventListener('proposal-asset-owner-changed', syncSuffixFromAssetOwner);
      form.addEventListener('proposal-customer-changed', syncSuffixFromAssetOwner);
      form.querySelector('[name="asset_owner_matches_customer"]')?.addEventListener('change', syncSuffixFromAssetOwner);
      form.addEventListener('proposal-stage-products-changed', function () {
        syncPrefixFromType(true);
      });

      options.syncPrefixFromType(false);
      syncSuffixFromAssetOwner();
      syncCombinedValue();
    }

    attachProposalNumberDisplay(form);
    attachGroupSelectDisplay(form);
    attachReportLanguagesDropdown(form);
    attachCountryIdentifierSync(form);
    attachCountryRegionSync(form);
    attachProposalRegistrationRegionAutofill(form);
    attachGuillemets(form);
    attachLerAutocomplete(form);
    initCompositeProposalField({
      hiddenSelector: 'input[name="proposal_project_name"]',
      prefixSelector: '#proposal-project-name-prefix',
      suffixSelector: '#proposal-project-name-suffix',
      getFallbackFirstPart: function () {
        return getProposalServiceGoalReportEntry(form)?.report_title || '';
      },
      syncPrefixFromType: function (force) {
        syncProposalTypeDefaults(force);
      },
    });
    initCompositeProposalField({
      hiddenSelector: 'input[name="purpose"]',
      prefixSelector: '#proposal-purpose-prefix',
      suffixSelector: '#proposal-purpose-suffix',
      getFallbackFirstPart: function () {
        return getProposalServiceGoalReportEntry(form)?.service_goal || '';
      },
      syncPrefixFromType: function (force) {
        syncProposalTypeDefaults(force);
      },
    });
    attachMoneyInputs(form);
    [
      'registration_date',
      'asset_owner_registration_date',
    ].forEach(function (fieldName) {
      initProposalDateInput(form.querySelector('input[name="' + fieldName + '"]'));
    });
    const assetsApi = attachProposalAssetsTable(form);
    const stageProductsApi = attachProposalStageProducts(assetsApi);
    const legalEntitiesApi = attachProposalLegalEntitiesTable(form);
    const objectsApi = attachProposalObjectsTable(form);
    attachProposalAssetsToLegalEntitiesSync(form, assetsApi, legalEntitiesApi);
    attachProposalLegalEntitiesToObjectsSync(form, legalEntitiesApi, objectsApi);
    form.querySelector('[name="advance_percent"]')?.addEventListener('input', syncFinalReportPercent);
    form.querySelector('[name="preliminary_report_percent"]')?.addEventListener('input', syncFinalReportPercent);
    qa('.js-proposal-report-terms-lock', form).forEach(function (icon) {
      icon.addEventListener('click', function () {
        proposalReportTermsEditMode = !proposalReportTermsEditMode;
        stageProductsApi?.sync();
      });
    });
    form.querySelector('[name="asset_owner_matches_customer"]')?.addEventListener('change', function () {
      syncAssetOwnerFromCustomer('customer-sync');
    });
    ['customer', 'registration_number', 'registration_date'].forEach(function (fieldName) {
      form.querySelector('[name="' + fieldName + '"]')?.addEventListener('input', function () {
        syncAssetOwnerFromCustomer('customer-input');
      });
      form.querySelector('[name="' + fieldName + '"]')?.addEventListener('change', function () {
        syncAssetOwnerFromCustomer('customer-sync');
      });
    });
    form.querySelector('#proposal-region-select')?.addEventListener('change', function () {
      syncAssetOwnerFromCustomer('customer-sync');
    });
    form.querySelector('#proposal-country-select')?.addEventListener('change', function () {
      syncAssetOwnerFromCustomer('customer-sync');
    });
    form.addEventListener('proposal-customer-changed', function () {
      syncAssetOwnerFromCustomer('customer-sync');
    });
    form.addEventListener('proposal-asset-owner-changed', function (event) {
      const reason = event?.detail?.reason || '';
      if (reason === 'autocomplete-pick' || reason === 'customer-sync' || reason === 'owner-change') {
        assetsApi?.fillEmptyRowsFromDefaults();
      }
    });
    ['asset_owner', 'asset_owner_registration_number', 'asset_owner_registration_date'].forEach(function (fieldName) {
      form.querySelector('[name="' + fieldName + '"]')?.addEventListener('change', function () {
        form.dispatchEvent(new CustomEvent('proposal-asset-owner-changed', { detail: { reason: 'owner-change' } }));
      });
    });
    form.querySelector('#proposal-asset-owner-region-select')?.addEventListener('change', function () {
      form.dispatchEvent(new CustomEvent('proposal-asset-owner-changed', { detail: { reason: 'owner-change' } }));
    });
    form.querySelector('#proposal-asset-owner-country-select')?.addEventListener('change', function () {
      form.dispatchEvent(new CustomEvent('proposal-asset-owner-changed', { detail: { reason: 'owner-change' } }));
    });
    syncFinalReportPercent();
    syncAssetOwnerFromCustomer('customer-sync');
    assetsApi?.fillEmptyRowsFromDefaults();
      applyProposalReportTermsLockState();
    stageProductsApi?.sync();
  }

  function initProposalDispatchForm() {
    const form = document.querySelector('#proposals-modal form[data-proposal-dispatch-form]');
    if (!form) return;
    attachGuillemets(form);
    attachCountryIdentifierSync(form);
    attachLerAutocomplete(form);
    attachDispatchPersonAutocomplete(form);
    initProposalDateInput(form.querySelector('input[name="recipient_registration_date"]'));
    const countrySelect = form.querySelector('#proposal-dispatch-recipient-country-select');
    const identifierField = form.querySelector('#proposal-dispatch-recipient-identifier-field');
    if (countrySelect && identifierField && countrySelect.value && !String(identifierField.value || '').trim()) {
      countrySelect.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  function getProposalDispatchFormForRequest(target) {
    if (!(target instanceof Element)) return null;
    if (target.matches('form[data-proposal-dispatch-form]')) return target;
    return target.closest('form[data-proposal-dispatch-form]');
  }

  function getProposalFormForRequest(target) {
    if (!(target instanceof Element)) return null;
    if (target.matches('form[data-proposal-form]')) return target;
    if (target.matches('[data-proposal-form-save-btn]')) {
      return target.closest('form[data-proposal-form]');
    }
    return null;
  }

  function setProposalDispatchSaveLoading(form, isLoading) {
    if (!form) return;
    const saveBtn = form.querySelector('[data-proposal-dispatch-save-btn]');
    if (!(saveBtn instanceof HTMLButtonElement)) return;

    if (isLoading) {
      if (saveBtn.dataset.loading === '1') return;
      saveBtn.dataset.loading = '1';
      saveBtn.dataset.originalHtml = saveBtn.innerHTML;
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Сохранение...';
      return;
    }

    if (saveBtn.dataset.originalHtml) {
      saveBtn.innerHTML = saveBtn.dataset.originalHtml;
    }
    saveBtn.disabled = false;
    delete saveBtn.dataset.loading;
  }

  function setProposalFormSaveLoading(form, isLoading) {
    if (!form) return;
    const saveBtn = form.querySelector('[data-proposal-form-save-btn]');
    if (!(saveBtn instanceof HTMLButtonElement)) return;

    if (isLoading) {
      if (saveBtn.dataset.loading === '1') return;
      saveBtn.dataset.loading = '1';
      saveBtn.dataset.originalHtml = saveBtn.innerHTML;
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Сохранение...';
      return;
    }

    if (saveBtn.dataset.originalHtml) {
      saveBtn.innerHTML = saveBtn.dataset.originalHtml;
    }
    saveBtn.disabled = false;
    delete saveBtn.dataset.loading;
  }

  function getProposalFormCancelButtonForRequest(target) {
    if (!(target instanceof Element)) return null;
    if (target.matches('[data-proposal-form-cancel-btn]')) return target;
    return target.closest('[data-proposal-form-cancel-btn]');
  }

  function setProposalFormCancelLoading(button, isLoading) {
    if (!(button instanceof HTMLButtonElement)) return;

    if (isLoading) {
      if (button.dataset.loading === '1') return;
      button.dataset.loading = '1';
      button.dataset.originalHtml = button.innerHTML;
      button.disabled = true;
      button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Отмена';
      return;
    }

    if (button.dataset.originalHtml) {
      button.innerHTML = button.dataset.originalHtml;
    }
    button.disabled = false;
    delete button.dataset.loading;
  }

  function getProposalCreateButtonForRequest(target) {
    if (!(target instanceof Element)) return null;
    if (target.matches('#proposal-new-btn')) return target;
    return target.closest('#proposal-new-btn');
  }

  function setProposalCreateButtonLoading(button, isLoading) {
    if (!(button instanceof HTMLButtonElement)) return;

    if (isLoading) {
      if (button.dataset.loading === '1') return;
      button.dataset.loading = '1';
      button.dataset.originalHtml = button.innerHTML;
      button.disabled = true;
      button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Создание ТКП...';
      return;
    }

    if (button.dataset.originalHtml) {
      button.innerHTML = button.dataset.originalHtml;
    }
    button.disabled = false;
    delete button.dataset.loading;
  }

  function getProposalHeaderLinkForRequest(target) {
    if (!(target instanceof Element)) return null;
    if (target.matches('.proposal-header-link[hx-target="#proposals-pane"]')) return target;
    return target.closest('.proposal-header-link[hx-target="#proposals-pane"]');
  }

  document.addEventListener('click', async (event) => {
    const root = pane();
    if (!root) return;
    const quickEdit = event.target.closest('.proposal-quick-edit');
    if (quickEdit && root.contains(quickEdit)) {
      const tr = quickEdit.closest('tr');
      if (!tr) return;
      const url = tr.dataset.editUrl;
      if (!url) return;
      await htmx.ajax('GET', url, { target: '#proposals-pane', swap: 'outerHTML' });
      return;
    }

    const btn = event.target.closest('button[data-proposal-action]');
    if (!btn || !root.contains(btn)) return;

    const checked = getChecked('proposal-select');
    if (!checked.length) return;

    window.__tableSel['proposal-select'] = checked.map((box) => String(box.value));
    window.__tableSelLast = 'proposal-select';

    const action = btn.dataset.proposalAction;

    if (action === 'edit') {
      const url = checked[0].closest('tr')?.dataset?.editUrl;
      if (!url) return;
      await htmx.ajax('GET', url, { target: '#proposals-pane', swap: 'outerHTML' });
      return;
    }

    if (action === 'delete') {
      if (!window.confirm('Удалить ' + checked.length + ' строк(у/и)?')) return;
      const urls = checked.map((box) => box.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      for (let i = 0; i < urls.length; i += 1) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#proposals-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      return;
    }

    if (action === 'up' || action === 'down') {
      let urls = checked
        .map((box) => box.closest('tr')?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'])
        .filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      for (let i = 0; i < urls.length; i += 1) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#proposals-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      syncSelectionState('proposal-select');
    }
  });

  document.addEventListener('click', async (event) => {
    const root = pane();
    if (!root) return;
    const createBtn = event.target.closest('#proposal-create-btn');
    if (createBtn && root.contains(createBtn)) {
      const checked = getChecked('proposal-dispatch-select');
      if (!checked.length || createBtn.disabled) return;

      const panel = root.querySelector('#proposal-dispatch-controls');
      const createUrl = panel?.dataset?.createUrl;
      if (!createUrl) return;

      const formData = new FormData();
      checked.forEach((cb) => formData.append('proposal_ids[]', cb.value));

      const originalHtml = createBtn.innerHTML;
      createBtn.disabled = true;
      createBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Создание...';
      try {
        const response = await fetch(createUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
      const data = await parseJsonResponse(response, 'Не удалось создать ТКП.');
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось создать ТКП.');
        }

        checked.forEach((cb) => { cb.checked = false; });
        window.__tableSel['proposal-dispatch-select'] = [];
        window.__tableSelLast = null;
        applyCreatedDocumentsState(data?.updates || []);
        syncSelectionState('proposal-dispatch-select');

        if (data.warnings && data.warnings.length) {
          alert((data.message || 'Документы ТКП созданы.') + '\n\n' + data.warnings.join('\n'));
        }
      } catch (err) {
        createBtn.innerHTML = originalHtml;
        alert(err.message || 'Не удалось создать ТКП.');
        updateDispatchActionBtns();
      } finally {
        createBtn.innerHTML = originalHtml;
      }
      return;
    }

    const dispatchQuickEdit = event.target.closest('.proposal-dispatch-quick-edit');
    if (dispatchQuickEdit && root.contains(dispatchQuickEdit)) {
      const tr = dispatchQuickEdit.closest('tr');
      if (!tr) return;
      const rowCheckbox = tr.querySelector('input.form-check-input[name="proposal-dispatch-select"]');
      if (rowCheckbox) {
        window.__tableSel['proposal-dispatch-select'] = [String(rowCheckbox.value)];
        window.__tableSelLast = 'proposal-dispatch-select';
      }
      const url = tr.dataset.editUrl;
      if (!url) return;
      await htmx.ajax('GET', url, { target: '#proposals-modal .modal-content', swap: 'innerHTML' });
      updateDispatchActionBtns();
      return;
    }

    const btn = event.target.closest('button[data-proposal-template-action]');
    if (!btn || !root.contains(btn)) return;

    const checked = getChecked('proposal-template-select');
    if (!checked.length) return;

    window.__tableSel['proposal-template-select'] = checked.map((box) => String(box.value));
    window.__tableSelLast = 'proposal-template-select';

    const action = btn.dataset.proposalTemplateAction;

    if (action === 'edit') {
      const url = checked[0].closest('tr')?.dataset?.editUrl;
      if (!url) return;
      await htmx.ajax('GET', url, { target: '#proposals-modal .modal-content', swap: 'innerHTML' });
      return;
    }

    if (action === 'delete') {
      if (!window.confirm('Удалить ' + checked.length + ' строк(у/и)?')) return;
      const urls = checked.map((box) => box.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      for (let i = 0; i < urls.length; i += 1) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#proposals-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      return;
    }

    if (action === 'up' || action === 'down') {
      let urls = checked
        .map((box) => box.closest('tr')?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'])
        .filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      for (let i = 0; i < urls.length; i += 1) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#proposals-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
    }
  });

  document.addEventListener('click', async (event) => {
    const root = pane();
    if (!root) return;
    const btn = event.target.closest('button[data-proposal-variable-action]');
    if (!btn || !root.contains(btn)) return;
    event.preventDefault();
    event.stopPropagation();

    const checked = getChecked('proposal-variable-select');
    if (!checked.length) return;

    window.__tableSel['proposal-variable-select'] = checked.map((box) => String(box.value));
    window.__tableSelLast = 'proposal-variable-select';

    const action = btn.dataset.proposalVariableAction;

    if (action === 'edit') {
      const url = checked[0].closest('tr')?.dataset?.editUrl;
      if (!url) return;
      await htmx.ajax('GET', url, { target: '#proposals-modal .modal-content', swap: 'innerHTML' });
      return;
    }

    if (action === 'delete') {
      if (!window.confirm('Удалить ' + checked.length + ' строк(у/и)?')) return;
      const urls = checked.map((box) => box.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      for (let i = 0; i < urls.length; i += 1) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#proposals-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      return;
    }

    if (action === 'up' || action === 'down') {
      const scrollX = window.scrollX;
      const scrollY = window.scrollY;
      const actionsPanel = root.querySelector('#proposal-variable-actions');
      let awaitingSettle = false;
      let reorderFailed = false;
      window.__proposalPendingScrollRestore = {
        x: scrollX,
        y: scrollY,
        anchorSelector: '#proposal-variable-actions',
        anchorTop: actionsPanel ? actionsPanel.getBoundingClientRect().top : null,
      };
      if (typeof btn.blur === 'function') btn.blur();
      let urls = checked
        .map((box) => box.closest('tr')?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'])
        .filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      document.documentElement.classList.add('proposal-progress-cursor');
      try {
        for (let i = 0; i < urls.length; i += 1) {
          const isLast = i === urls.length - 1;
          if (isLast) {
            awaitingSettle = true;
            await htmx.ajax('POST', urls[i], { target: '#proposal-variables-section', swap: 'outerHTML' });
          } else {
            await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
          }
        }
      } catch (error) {
        reorderFailed = true;
      } finally {
        if (!reorderFailed && awaitingSettle && window.__proposalPendingScrollRestore) return;
        if (!window.__proposalPendingScrollRestore) {
          document.documentElement.classList.remove('proposal-progress-cursor');
        }
        clearProposalPendingScrollRestore();
      }
    }
  });

  document.addEventListener('click', async (event) => {
    const root = pane();
    if (!root) return;
    const sendBtn = event.target.closest('#proposal-send-btn');
    if (!sendBtn || !root.contains(sendBtn)) return;

    const checked = getChecked('proposal-dispatch-select');
    if (!checked.length || sendBtn.disabled) return;

    const panel = root.querySelector('#proposal-dispatch-controls');
    const sendUrl = panel?.dataset?.sendUrl;
    const sentAtInput = root.querySelector('#proposal-request-sent-at');
    const selectedChannels = getProposalChannels().filter((cb) => cb.checked).map((cb) => cb.value);

    if (!selectedChannels.length) {
      alert('Выберите хотя бы один способ отправки.');
      return;
    }
    const rowsWithoutEmail = checked
      .map((cb) => cb.closest('tr'))
      .filter((row) => row && !String(row.dataset.contactEmail || '').trim());
    if (rowsWithoutEmail.length) {
      const preview = rowsWithoutEmail
        .slice(0, 8)
        .map((row) => '- ' + (row.dataset.tkpId || 'без ID'))
        .join('\n');
      const moreCount = rowsWithoutEmail.length - Math.min(rowsWithoutEmail.length, 8);
      const details = [
        'Нельзя отправить ТКП: у части выбранных строк не заполнено поле «Эл. почта».',
        preview,
      ];
      if (moreCount > 0) {
        details.push('- И еще ' + moreCount + ' строк(и).');
      }
      alert(details.join('\n'));
      return;
    }
    if (!sendUrl) return;

    const formData = new FormData();
    checked.forEach((cb) => formData.append('proposal_ids[]', cb.value));
    formData.append('sent_at', sentAtInput?.value || '');
    selectedChannels.forEach((value) => formData.append('delivery_channels[]', value));

    const originalHtml = sendBtn.innerHTML;
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Отправка...';
    try {
      const response = await fetch(sendUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData,
      });
      const data = await parseJsonResponse(response, 'Не удалось отправить ТКП.');
      if (!response.ok || !data.ok) {
        throw new Error(data?.error || 'Не удалось отправить ТКП.');
      }

      checked.forEach((cb) => { cb.checked = false; });
      window.__tableSel['proposal-dispatch-select'] = [];
      window.__tableSelLast = null;

      const modalEl = root.querySelector('#proposal-send-modal');
      const modal = modalEl ? window.bootstrap?.Modal.getInstance(modalEl) : null;
      modal?.hide();

      const emailDelivery = data?.email_delivery;
      if (emailDelivery?.requested && emailDelivery?.failed > 0) {
        const errorLines = (emailDelivery.errors || [])
          .slice(0, 5)
          .map((item) => {
            const channelPrefix = item.channel_label ? '[' + item.channel_label + '] ' : '';
            return '- ' + channelPrefix + item.recipient + ': ' + item.error;
          });
        const moreCount = Math.max((emailDelivery.errors || []).length - errorLines.length, 0);
        const details = [
          'Не удалось отправить ' + emailDelivery.failed + ' из ' + emailDelivery.attempted + ' email-писем.',
          ...errorLines,
        ];
        if (moreCount > 0) {
          details.push('- И еще ' + moreCount + ' ошибок.');
        }
        alert(details.join('\n'));
      }

      applySentProposalState(
        data?.updates || data?.proposal_ids || [],
        data?.status || 'sent',
        data?.status_label || 'Отправленное',
        data?.sent_at || '',
      );
      syncSelectionState('proposal-dispatch-select');
    } catch (err) {
      alert(err.message || 'Не удалось отправить ТКП.');
      updateDispatchActionBtns();
    } finally {
      sendBtn.innerHTML = originalHtml;
    }
  });

  document.addEventListener('click', async (event) => {
    const root = pane();
    if (!root) return;
    const transferBtn = event.target.closest('#proposal-transfer-contract-btn');
    if (!transferBtn || !root.contains(transferBtn)) return;

    const checked = getChecked('proposal-dispatch-select');
    if (!checked.length || transferBtn.disabled) return;

    const panel = root.querySelector('#proposal-dispatch-controls');
    const transferUrl = panel?.dataset?.transferContractUrl;
    if (!transferUrl) return;

    const formData = new FormData();
    checked.forEach((cb) => formData.append('proposal_ids[]', cb.value));

    const originalHtml = transferBtn.innerHTML;
    transferBtn.disabled = true;
    transferBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Передача...';
    try {
      const response = await fetch(transferUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData,
      });
      const data = await parseJsonResponse(response, 'Не удалось передать строки для договора.');
      if (!response.ok || !data.ok) {
        throw new Error(data?.error || 'Не удалось передать строки для договора.');
      }

      checked.forEach((cb) => { cb.checked = false; });
      window.__tableSel['proposal-dispatch-select'] = [];
      window.__tableSelLast = null;
      applyTransferredProposalState(
        data?.proposal_ids || checked.map((cb) => cb.value),
        data?.status || 'completed',
        data?.status_label || 'Завершённое',
        data?.transfer_to_contract_date || '',
      );
      syncSelectionState('proposal-dispatch-select');
      htmx.trigger(document.body, 'contracts-updated');

      const projectsPane = document.getElementById('projects-pane');
      const projectsRefreshUrl = projectsPane?.getAttribute('hx-get') || projectsPane?.dataset?.refreshUrl;
      if (projectsPane && projectsRefreshUrl) {
        htmx.ajax('GET', projectsRefreshUrl, { target: '#projects-pane', swap: 'outerHTML' });
      }
    } catch (err) {
      alert(err.message || 'Не удалось передать строки для договора.');
      updateDispatchActionBtns();
    } finally {
      transferBtn.innerHTML = originalHtml;
    }
  });

  document.addEventListener('click', async (event) => {
    const root = pane();
    if (!root) return;
    const signBtn = event.target.closest('#proposal-sign-btn');
    if (!signBtn || !root.contains(signBtn)) return;

    const checked = getChecked('proposal-dispatch-select');
    if (!checked.length || signBtn.disabled) return;

    const panel = root.querySelector('#proposal-dispatch-controls');
    const signUrl = panel?.dataset?.signUrl;
    if (!signUrl) return;

    const formData = new FormData();
    checked.forEach((cb) => formData.append('proposal_ids[]', cb.value));

    const originalHtml = signBtn.innerHTML;
    signBtn.disabled = true;
    signBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Подписание...';
    try {
      const response = await fetch(signUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData,
      });
      const data = await parseJsonResponse(response, 'Не удалось сформировать PDF для ТКП.');
      if (!response.ok || !data.ok) {
        throw new Error(data?.error || 'Не удалось сформировать PDF для ТКП.');
      }

      checked.forEach((cb) => { cb.checked = false; });
      window.__tableSel['proposal-dispatch-select'] = [];
      window.__tableSelLast = null;
      applySignedDocumentsState(data?.updates || []);
      syncSelectionState('proposal-dispatch-select');

      if (data.warnings && data.warnings.length) {
        alert((data.message || 'PDF для ТКП сформирован.') + '\n\n' + data.warnings.join('\n'));
      }
    } catch (err) {
      alert(err.message || 'Не удалось сформировать PDF для ТКП.');
      updateDispatchActionBtns();
    } finally {
      signBtn.innerHTML = originalHtml;
    }
  });

  document.addEventListener('change', (event) => {
    const root = pane();
    if (!root) return;
    const master = event.target.closest('input.form-check-input[data-target-name]');
    if (!master || !root.contains(master)) return;
    const name = master.dataset.targetName;
    getRowChecks(name).forEach((box) => {
      box.checked = master.checked;
    });
    master.indeterminate = false;
    syncSelectionState(name);
  });

  document.addEventListener('change', (event) => {
    const root = pane();
    if (!root) return;
    const rowCheckbox = event.target.closest('tbody input.form-check-input[name]');
    if (!rowCheckbox || !root.contains(rowCheckbox)) return;
    syncSelectionState(rowCheckbox.name);
  });

  document.addEventListener('change', (event) => {
    const root = pane();
    if (!root) return;
    const channelCheckbox = event.target.closest('.js-proposal-channel');
    if (!channelCheckbox || !root.contains(channelCheckbox)) return;
    saveProposalSendSettings();
  });

  document.addEventListener('shown.bs.collapse', (event) => {
    if (event.target?.id === 'proposal-dispatch-vars') {
      window.__proposalVarsExpanded = true;
    }
  });

  document.addEventListener('hidden.bs.collapse', (event) => {
    if (event.target?.id === 'proposal-dispatch-vars') {
      window.__proposalVarsExpanded = false;
    }
  });

  document.body.addEventListener('htmx:afterSettle', function (event) {
    if (!(event.target && event.target.id === 'proposals-pane')) return;
    const last = window.__tableSelLast;
    if (SELECT_NAMES.includes(last)) {
      restoreSavedSelection(last);
    }
    updateHeaderPath();
    syncAllSelectionStates();
    initProposalMasterFilters();
    initProposalForm();
    restoreProposalSendSettings();
    restoreVariableCollapseState();
    const pendingScroll = window.__proposalPendingScrollRestore;
    if (pendingScroll) {
      const restoreScroll = () => {
        window.scrollTo(pendingScroll.x, pendingScroll.y);
        if (pendingScroll.anchorSelector && pendingScroll.anchorTop !== null) {
          const anchor = document.querySelector(pendingScroll.anchorSelector);
          if (anchor) {
            const delta = anchor.getBoundingClientRect().top - pendingScroll.anchorTop;
            if (delta) window.scrollBy(0, delta);
          }
        }
      };
      requestAnimationFrame(() => {
        restoreScroll();
        requestAnimationFrame(restoreScroll);
      });
      clearProposalPendingScrollRestore();
    }
  });

  document.body.addEventListener('htmx:afterSettle', function (event) {
    if (!(event.target && event.target.id === 'proposal-variables-section')) return;
    if (window.__tableSelLast === 'proposal-variable-select') {
      restoreSavedSelection('proposal-variable-select');
    }
    restoreVariableCollapseState();
    syncSelectionState('proposal-variable-select');
    const pendingScroll = window.__proposalPendingScrollRestore;
    if (pendingScroll) {
      const restoreScroll = () => {
        window.scrollTo(pendingScroll.x, pendingScroll.y);
        if (pendingScroll.anchorSelector && pendingScroll.anchorTop !== null) {
          const anchor = document.querySelector(pendingScroll.anchorSelector);
          if (anchor) {
            const delta = anchor.getBoundingClientRect().top - pendingScroll.anchorTop;
            if (delta) window.scrollBy(0, delta);
          }
        }
      };
      requestAnimationFrame(() => {
        restoreScroll();
        requestAnimationFrame(restoreScroll);
      });
      window.__proposalPendingScrollRestore = null;
      document.documentElement.classList.remove('proposal-progress-cursor');
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (!target.closest('#proposals-modal .modal-content')) return;
    initProposalDispatchForm();
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    const form = getProposalFormForRequest(event.detail?.elt);
    if (!form) return;
    setProposalFormSaveLoading(form, true);
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    const form = getProposalDispatchFormForRequest(event.detail?.elt);
    if (!form) return;
    setProposalDispatchSaveLoading(form, true);
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    const button = getProposalFormCancelButtonForRequest(event.detail?.elt);
    if (!button) return;
    setProposalFormCancelLoading(button, true);
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    const button = getProposalCreateButtonForRequest(event.detail?.elt);
    if (!button) return;
    setProposalCreateButtonLoading(button, true);
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    const headerLink = getProposalHeaderLinkForRequest(event.detail?.elt);
    if (!headerLink) return;
    document.documentElement.classList.add('proposal-progress-cursor');
  });

  document.body.addEventListener('htmx:afterRequest', function (event) {
    const form = getProposalFormForRequest(event.detail?.elt);
    if (!form || !document.body.contains(form)) return;
    setProposalFormSaveLoading(form, false);
  });

  document.body.addEventListener('htmx:afterRequest', function (event) {
    const form = getProposalDispatchFormForRequest(event.detail?.elt);
    if (!form || !document.body.contains(form)) return;
    setProposalDispatchSaveLoading(form, false);
  });

  document.body.addEventListener('htmx:afterRequest', function (event) {
    if (event.detail?.successful) return;
    const button = getProposalFormCancelButtonForRequest(event.detail?.elt);
    if (!button || !document.body.contains(button)) return;
    setProposalFormCancelLoading(button, false);
  });

  document.body.addEventListener('htmx:afterRequest', function (event) {
    if (event.detail?.successful) return;
    const button = getProposalCreateButtonForRequest(event.detail?.elt);
    if (!button || !document.body.contains(button)) return;
    setProposalCreateButtonLoading(button, false);
  });

  document.body.addEventListener('htmx:afterRequest', function (event) {
    if (event.detail?.successful) return;
    const headerLink = getProposalHeaderLinkForRequest(event.detail?.elt);
    if (!headerLink) return;
    document.documentElement.classList.remove('proposal-progress-cursor');
  });

  document.body.addEventListener('htmx:afterRequest', function (event) {
    if (event.detail?.successful) return;
    const target = event.detail?.target || event.target;
    if (!isProposalVariablesSectionElement(target)) return;
    clearProposalPendingScrollRestore();
  });

  document.body.addEventListener('htmx:sendError', function (event) {
    const form = getProposalFormForRequest(event.detail?.elt);
    if (!form || !document.body.contains(form)) return;
    setProposalFormSaveLoading(form, false);
  });

  document.body.addEventListener('htmx:sendError', function (event) {
    const form = getProposalDispatchFormForRequest(event.detail?.elt);
    if (!form || !document.body.contains(form)) return;
    setProposalDispatchSaveLoading(form, false);
  });

  document.body.addEventListener('htmx:sendError', function (event) {
    const button = getProposalFormCancelButtonForRequest(event.detail?.elt);
    if (!button || !document.body.contains(button)) return;
    setProposalFormCancelLoading(button, false);
  });

  document.body.addEventListener('htmx:sendError', function (event) {
    const button = getProposalCreateButtonForRequest(event.detail?.elt);
    if (!button || !document.body.contains(button)) return;
    setProposalCreateButtonLoading(button, false);
  });

  document.body.addEventListener('htmx:sendError', function (event) {
    const headerLink = getProposalHeaderLinkForRequest(event.detail?.elt);
    if (!headerLink) return;
    document.documentElement.classList.remove('proposal-progress-cursor');
  });

  document.body.addEventListener('htmx:sendError', function (event) {
    const target = event.detail?.target || event.target;
    if (!isProposalVariablesSectionElement(target)) return;
    clearProposalPendingScrollRestore();
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (!target.closest('#proposals-pane') && !target.closest('#proposal-variables-section')) return;
    document.documentElement.classList.remove('proposal-progress-cursor');
  });

  document.addEventListener('DOMContentLoaded', function () {
    updateHeaderPath();
    syncAllSelectionStates();
    initProposalMasterFilters();
    initProposalForm();
    restoreProposalSendSettings();
    if (typeof window.__proposalVarsExpanded === 'undefined') {
      window.__proposalVarsExpanded = !!varsCollapse()?.classList.contains('show');
    }
    restoreVariableCollapseState();
    initProposalDispatchForm();
  });
})();
