(function () {
  if (window.__proposalsPanelBound) return;
  window.__proposalsPanelBound = true;

  window.__tableSel = window.__tableSel || {};
  window.__tableSelLast = window.__tableSelLast || null;

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

  function updateHeaderPath() {
    const heading = document.getElementById('proposals-section-heading');
    if (!heading) return;
    const root = pane();
    if (!root) {
      heading.textContent = 'ТКП';
      return;
    }

    const rootLabel = root.dataset.headerRootLabel || 'ТКП';
    const rootUrl = root.dataset.headerRootUrl || '';
    const currentLabel = root.dataset.headerCurrentLabel || '';
    const currentUrl = root.dataset.headerCurrentUrl || '';

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

  function getRowChecks(name) {
    return qa('tbody input.form-check-input[name="' + name + '"]', pane());
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
    const hasChecked = getChecked('proposal-dispatch-select').length > 0;
    const editBtn = pane()?.querySelector('#proposal-dispatch-edit-btn');
    const createBtn = pane()?.querySelector('#proposal-create-btn');
    const sendBtn = pane()?.querySelector('#proposal-send-btn');
    if (editBtn) editBtn.disabled = !hasChecked;
    if (createBtn) createBtn.disabled = !hasChecked;
    if (sendBtn) sendBtn.disabled = !hasChecked;
  }

  function getProposalChannels() {
    return qa('.js-proposal-channel', pane());
  }

  function varsCollapse() {
    return pane()?.querySelector('#proposal-dispatch-vars') || null;
  }

  function varsToggle() {
    return pane()?.querySelector('a[href="#proposal-dispatch-vars"]') || null;
  }

  function restoreVariableCollapseState() {
    const collapseEl = varsCollapse();
    if (!collapseEl) return;
    const expanded = !!window.__proposalVarsExpanded;
    const toggle = varsToggle();
    if (toggle) toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    if (!window.bootstrap?.Collapse) {
      collapseEl.classList.toggle('show', expanded);
      return;
    }
    const instance = window.bootstrap.Collapse.getOrCreateInstance(collapseEl, { toggle: false });
    if (expanded) instance.show();
    else instance.hide();
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

  function attachCountryIdentifierSync(root) {
    if (!root) return;
    const form = root.closest('form[data-proposal-form]') || root;
    const countrySelect = form.querySelector('#proposal-country-select');
    const identifierField = form.querySelector('#proposal-identifier-field');
    const url = form.dataset.countryIdentifierUrl;
    if (!countrySelect || !identifierField || !url || countrySelect.dataset.identBound === '1') return;
    countrySelect.dataset.identBound = '1';

    countrySelect.addEventListener('change', () => {
      const countryId = countrySelect.value;
      if (!countryId) {
        identifierField.value = '';
        return;
      }
      fetch(url + '?country_id=' + encodeURIComponent(countryId))
        .then((response) => response.json())
        .then((data) => {
          identifierField.value = data.identifier || '';
        });
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
    const input = root.querySelector('input[name="customer"]');
    if (!input || input.dataset.guillBound === '1') return;
    input.dataset.guillBound = '1';
    input.addEventListener('input', function () {
      replaceQuotes(input);
    });
  }

  function attachLerAutocomplete(root) {
    if (!root) return;
    const form = root.closest('form[data-proposal-form]') || root;
    const input = form.querySelector('input[name="customer"]');
    const list = form.querySelector('#proposal-ler-ac-list');
    const searchUrl = form.dataset.lerSearchUrl;
    if (!input || !list || !searchUrl || input.dataset.lerBound === '1') return;
    input.dataset.lerBound = '1';

    let debounce = null;
    let results = [];
    let picking = false;

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
      input.value = item.short_name || '';
      const countrySelect = form.querySelector('#proposal-country-select');
      const identifierField = form.querySelector('#proposal-identifier-field');
      const registrationNumberField = form.querySelector('input[name="registration_number"]');
      const registrationDateField = form.querySelector('input[name="registration_date"]');
      if (countrySelect && item.country_id) countrySelect.value = item.country_id;
      if (identifierField) identifierField.value = item.identifier || '';
      if (registrationNumberField) registrationNumberField.value = item.registration_number || '';
      if (registrationDateField) registrationDateField.value = item.registration_date || '';
      list.classList.remove('show');
    }

    input.addEventListener('input', function () {
      const query = input.value.trim();
      clearTimeout(debounce);
      if (query.length < 1) {
        list.classList.remove('show');
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

  function attachMoneyInputs(root) {
    if (!root) return;
    root.querySelectorAll('.js-money-input').forEach(function (input) {
      if (input.dataset.moneyBound === '1') return;
      input.dataset.moneyBound = '1';
      if (input.value) input.value = fmtMoney(input.value);
      input.addEventListener('blur', function () {
        if (input.value) input.value = fmtMoney(input.value);
      });
    });

    var form = root.closest('form[data-proposal-form]') || root;
    if (form.dataset.moneySubmitBound === '1') return;
    form.dataset.moneySubmitBound = '1';
    form.addEventListener('submit', function () {
      form.querySelectorAll('.js-money-input').forEach(function (input) {
        input.value = rawMoney(input.value);
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

  function bindProposalEntityAutocomplete(input, list, row, updatePayload, searchUrl, selectors, getRowIndex) {
    let debounce = null;
    let results = [];
    let picking = false;

    function positionList() {
      if (!list.classList.contains('show')) return;
      const rect = input.getBoundingClientRect();
      list.style.position = 'fixed';
      list.style.left = rect.left + 'px';
      list.style.top = (rect.bottom + 2) + 'px';
      list.style.minWidth = rect.width + 'px';
      list.style.width = 'max-content';
      list.style.maxWidth = 'none';
      list.style.zIndex = '2000';
    }

    function hideList() {
      list.classList.remove('show');
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
      positionList();
    }

    function pick(item) {
      input.value = item.short_name || '';
      row.dataset.countryId = item.country_id || '';
      row.dataset.countryName = item.country_name || '';
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

  function getProposalTypeId(form) {
    return (form?.querySelector('select[name="type"]')?.value || '').trim();
  }

  function syncProposalCommercialServiceSelect(select, form, selectedValue) {
    const sectionsMap = getProposalTypicalSectionsMap(form);
    const options = sectionsMap[getProposalTypeId(form)] || [];
    return syncOptionsSelect(select, options, selectedValue);
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

    function getRows() {
      return Array.from(tbody.querySelectorAll('tr'));
    }

    function getSelectedRows() {
      return getRows().filter(function (row) {
        return !!row.querySelector(config.selectors.check + ':checked');
      });
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

    function createRow(data) {
      const row = document.createElement('tr');
      row.dataset.countryId = data.country_id || '';
      row.dataset.countryName = data.country_name || '';

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

      countrySelect.addEventListener('change', function () {
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
      const row = createRow({});
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
      rowsChangedEvent: 'proposal-assets-changed',
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
          region: rows[meta.rowIndex].country_name || '',
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

  function attachProposalCommercialTable(root, assetsApi) {
    if (!root) return null;
    const form = root.closest('form[data-proposal-form]') || root;
    const payloadInput = form.querySelector('#proposal-commercial-offer-payload');
    const thead = form.querySelector('#proposal-commercial-thead');
    const tbody = form.querySelector('#proposal-commercial-tbody');
    const addBtn = form.querySelector('#proposal-commercial-add-btn');
    const actions = form.querySelector('#proposal-commercial-row-actions');
    const upBtn = form.querySelector('#proposal-commercial-up-btn');
    const downBtn = form.querySelector('#proposal-commercial-down-btn');
    const deleteBtn = form.querySelector('#proposal-commercial-delete-btn');
    if (!payloadInput || !thead || !tbody || !addBtn || !actions || !upBtn || !downBtn || !deleteBtn) return null;
    if (form.dataset.commercialBound === '1') return form.__proposalCommercialTableApi || null;
    form.dataset.commercialBound = '1';

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

    function renderHeader(assetRows) {
      const labels = getAssetLabels(assetRows);
      if (labels.length <= 1) {
        thead.innerHTML = ''
          + '<tr>'
          + '<th class="proposal-assets-check-col"></th>'
          + '<th>Специалист</th>'
          + '<th>Должность</th>'
          + '<th>Профессиональный статус</th>'
          + '<th>Услуги</th>'
          + '<th>Ставка, евро / день</th>'
          + '<th>Количество дней</th>'
          + '<th>Итого, евро без НДС</th>'
          + '</tr>';
        return;
      }

      thead.innerHTML = ''
        + '<tr>'
        + '<th class="proposal-assets-check-col" rowspan="2"></th>'
        + '<th rowspan="2">Специалист</th>'
        + '<th rowspan="2">Должность</th>'
        + '<th rowspan="2">Профессиональный статус</th>'
        + '<th rowspan="2">Услуги</th>'
        + '<th rowspan="2">Ставка, евро / день</th>'
        + '<th class="proposal-commercial-days-group proposal-commercial-days-group-subheaders" colspan="' + labels.length + '">Количество дней</th>'
        + '<th rowspan="2">Итого, евро без НДС</th>'
        + '</tr>'
        + '<tr>'
        + labels.map(function (label) {
          return '<th class="proposal-commercial-day-header">' + escapeHtml(label) + '</th>';
        }).join('')
        + '</tr>';
    }

    function syncActions() {
      const hasSelected = getSelectedRows().length > 0;
      actions.classList.toggle('d-none', !hasSelected);
      actions.classList.toggle('d-flex', hasSelected);
    }

    function getDayInputs(row) {
      return Array.from(row.querySelectorAll('.proposal-commercial-day-count'));
    }

    function recalcRowTotal(row) {
      if (!row) return;
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

    function syncDayCells(row, assetRows, values) {
      const sourceValues = Array.isArray(values) ? values : getDayInputs(row).map(function (input) { return input.value || ''; });
      row.querySelectorAll('.proposal-commercial-day-cell, .proposal-commercial-day-placeholder-cell').forEach(function (cell) {
        cell.remove();
      });

      const totalCell = row.querySelector('.proposal-commercial-total-cell');
      if (!totalCell) return;

      if (!assetRows.length) {
        const placeholderCell = createProposalTableCell('proposal-commercial-day-placeholder-cell');
        placeholderCell.textContent = '—';
        row.insertBefore(placeholderCell, totalCell);
        return;
      }

      assetRows.forEach(function (_assetRow, index) {
        const dayCell = createProposalTableCell('proposal-commercial-day-cell');
        const input = document.createElement('input');
        input.type = 'number';
        input.min = '0';
        input.step = '1';
        input.className = 'form-control proposal-commercial-day-count';
        input.value = sourceValues[index] ?? '';
        input.addEventListener('change', function () {
          recalcRowTotal(row);
          updatePayload();
        });
        input.addEventListener('input', function () {
          recalcRowTotal(row);
          updatePayload();
        });
        dayCell.appendChild(input);
        row.insertBefore(dayCell, totalCell);
      });

      recalcRowTotal(row);
    }

    function serializeRow(row) {
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

    function updatePayload(meta) {
      const rows = getRows().map(serializeRow);
      payloadInput.value = JSON.stringify(rows);
      syncActions();
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
      if (specialist) specialist.value = data.specialist || '';
      if (jobTitle) jobTitle.value = data.job_title || '';
      if (status) status.value = data.professional_status || '';
      if (service) {
        syncProposalCommercialServiceSelect(service, form, data.service_name || '');
        service.value = data.service_name || '';
      }
      if (rate) rate.value = data.rate_eur_per_day ? fmtMoney(data.rate_eur_per_day) : '';
      if (total) total.value = data.total_eur_without_vat ? fmtMoney(data.total_eur_without_vat) : '';
      syncDayCells(row, getAssetRows(), data.asset_day_counts || []);
      recalcRowTotal(row);
    }

    function createRow(data) {
      const row = document.createElement('tr');

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
      const specialistInput = document.createElement('input');
      specialistInput.type = 'text';
      specialistInput.className = 'form-control proposal-commercial-specialist';
      specialistInput.value = data.specialist || '';
      specialistTd.appendChild(specialistInput);
      row.appendChild(specialistTd);

      const titleTd = createProposalTableCell();
      const titleInput = document.createElement('input');
      titleInput.type = 'text';
      titleInput.className = 'form-control proposal-commercial-job-title';
      titleInput.value = data.job_title || '';
      titleTd.appendChild(titleInput);
      row.appendChild(titleTd);

      const statusTd = createProposalTableCell();
      const statusInput = document.createElement('input');
      statusInput.type = 'text';
      statusInput.className = 'form-control proposal-commercial-status';
      statusInput.value = data.professional_status || '';
      statusTd.appendChild(statusInput);
      row.appendChild(statusTd);

      const serviceTd = createProposalTableCell();
      const serviceSelect = document.createElement('select');
      serviceSelect.className = 'form-select proposal-commercial-service';
      syncProposalCommercialServiceSelect(serviceSelect, form, data.service_name || '');
      serviceSelect.value = data.service_name || '';
      serviceTd.appendChild(serviceSelect);
      row.appendChild(serviceTd);

      const rateTd = createProposalTableCell();
      const rateInput = document.createElement('input');
      rateInput.type = 'text';
      rateInput.className = 'form-control js-money-input proposal-commercial-rate';
      rateInput.inputMode = 'decimal';
      rateInput.value = data.rate_eur_per_day ? fmtMoney(data.rate_eur_per_day) : '';
      rateTd.appendChild(rateInput);
      row.appendChild(rateTd);

      const totalTd = createProposalTableCell('proposal-commercial-total-cell');
      const totalInput = document.createElement('input');
      totalInput.type = 'text';
      totalInput.className = 'form-control js-money-input proposal-commercial-total readonly-field';
      totalInput.inputMode = 'decimal';
      totalInput.readOnly = true;
      totalInput.tabIndex = -1;
      totalInput.value = data.total_eur_without_vat ? fmtMoney(data.total_eur_without_vat) : '';
      totalTd.appendChild(totalInput);
      row.appendChild(totalTd);

      syncDayCells(row, getAssetRows(), data.asset_day_counts || []);

      [specialistInput, titleInput, statusInput, serviceSelect].forEach(function (input) {
        input.addEventListener('change', updatePayload);
        input.addEventListener('input', updatePayload);
      });

      rateInput.addEventListener('change', function () {
        recalcRowTotal(row);
        updatePayload();
      });
      rateInput.addEventListener('input', function () {
        recalcRowTotal(row);
        updatePayload();
      });

      attachMoneyInputs(row);
      recalcRowTotal(row);
      return row;
    }

    function moveSelected(direction) {
      const rows = getRows();
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
      updatePayload({ reason: 'row-add', rowIndex: getRows().length - 1 });
      row.querySelector('.proposal-commercial-specialist')?.focus();
    });

    upBtn.addEventListener('click', function () { moveSelected('up'); });
    downBtn.addEventListener('click', function () { moveSelected('down'); });
    deleteBtn.addEventListener('click', deleteSelected);

    form.addEventListener('proposal-assets-changed', function (event) {
      const rows = Array.isArray(event.detail?.rows) ? event.detail.rows : getAssetRows();
      renderHeader(rows);
      getRows().forEach(function (row) {
        syncDayCells(row, rows);
      });
      updatePayload({ reason: 'sync-asset-columns' });
    });

    form.querySelector('select[name="type"]')?.addEventListener('change', function () {
      let changed = false;
      getRows().forEach(function (row) {
        const select = row.querySelector('.proposal-commercial-service');
        if (syncProposalCommercialServiceSelect(select, form)) changed = true;
      });
      if (changed) updatePayload({ reason: 'sync-services-by-type' });
    });

    renderHeader(getAssetRows());
    parsePayload().forEach(function (item) {
      tbody.appendChild(createRow(item));
    });
    updatePayload();

    const api = {
      getSerializedRows: function () {
        return getRows().map(serializeRow);
      },
    };
    form.__proposalCommercialTableApi = api;
    return api;
  }

  function initProposalForm() {
    const root = pane();
    const form = root?.querySelector('form[data-proposal-form]');
    if (!form) return;
    attachGroupSelectDisplay(form);
    attachCountryIdentifierSync(form);
    attachGuillemets(form);
    attachLerAutocomplete(form);
    attachMoneyInputs(form);
    const assetsApi = attachProposalAssetsTable(form);
    const legalEntitiesApi = attachProposalLegalEntitiesTable(form);
    const objectsApi = attachProposalObjectsTable(form);
    attachProposalCommercialTable(form, assetsApi);
    attachProposalAssetsToLegalEntitiesSync(form, assetsApi, legalEntitiesApi);
    attachProposalLegalEntitiesToObjectsSync(form, legalEntitiesApi, objectsApi);
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
      const refreshUrl = panel?.dataset?.refreshUrl;
      if (!createUrl || !refreshUrl) return;

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
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось создать ТКП.');
        }

        window.__tableSel['proposal-dispatch-select'] = [];
        window.__tableSelLast = null;
        await htmx.ajax('GET', refreshUrl, { target: '#proposals-pane', swap: 'outerHTML' });

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

    const editBtn = event.target.closest('#proposal-dispatch-edit-btn');
    if (!editBtn || !root.contains(editBtn)) return;

    const checked = getChecked('proposal-dispatch-select');
    if (!checked.length) return;

    window.__tableSel['proposal-dispatch-select'] = checked.map((box) => String(box.value));
    window.__tableSelLast = 'proposal-dispatch-select';

    const url = checked[0].closest('tr')?.dataset?.editUrl;
    if (!url) return;
    await htmx.ajax('GET', url, { target: '#proposals-modal .modal-content', swap: 'innerHTML' });
    updateDispatchActionBtns();
  });

  document.addEventListener('click', async (event) => {
    const root = pane();
    if (!root) return;
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
    const sendBtn = event.target.closest('#proposal-send-btn');
    if (!sendBtn || !root.contains(sendBtn)) return;

    const checked = getChecked('proposal-dispatch-select');
    if (!checked.length || sendBtn.disabled) return;

    const panel = root.querySelector('#proposal-dispatch-controls');
    const sendUrl = panel?.dataset?.sendUrl;
    const refreshUrl = panel?.dataset?.refreshUrl;
    const sentAtInput = root.querySelector('#proposal-request-sent-at');
    const selectedChannels = getProposalChannels().filter((cb) => cb.checked).map((cb) => cb.value);

    if (!selectedChannels.length) {
      alert('Выберите хотя бы один способ отправки.');
      return;
    }
    if (!sendUrl || !refreshUrl) return;

    const formData = new FormData();
    checked.forEach((cb) => formData.append('proposal_ids[]', cb.value));
    formData.append('sent_at', sentAtInput?.value || '');
    selectedChannels.forEach((value) => formData.append('delivery_channels[]', value));

    sendBtn.disabled = true;
    try {
      const response = await fetch(sendUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData,
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data?.error || 'Не удалось отправить ТКП.');
      }

      window.__tableSel['proposal-dispatch-select'] = [];
      window.__tableSelLast = null;

      const modalEl = root.querySelector('#proposal-send-modal');
      const modal = modalEl ? window.bootstrap?.Modal.getInstance(modalEl) : null;
      modal?.hide();

      await htmx.ajax('GET', refreshUrl, { target: '#proposals-pane', swap: 'outerHTML' });
    } catch (err) {
      alert(err.message || 'Не удалось отправить ТКП.');
      updateDispatchActionBtns();
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
      const savedIds = new Set((window.__tableSel && window.__tableSel[last]) || []);
      getRowChecks(last).forEach((box) => {
        box.checked = savedIds.has(String(box.value));
      });
      try {
        delete window.__tableSel[last];
      } catch (error) {
        window.__tableSel[last] = [];
      }
      window.__tableSelLast = null;
    }
    updateHeaderPath();
    syncAllSelectionStates();
    initProposalForm();
    restoreVariableCollapseState();
  });

  document.addEventListener('DOMContentLoaded', function () {
    updateHeaderPath();
    syncAllSelectionStates();
    initProposalForm();
    if (typeof window.__proposalVarsExpanded === 'undefined') {
      window.__proposalVarsExpanded = !!varsCollapse()?.classList.contains('show');
    }
    restoreVariableCollapseState();
  });
})();
