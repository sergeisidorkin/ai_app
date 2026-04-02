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
  const QUILL_JS = '/static/letters_app/vendor/quill/quill.min.js';
  const QUILL_CSS = '/static/letters_app/vendor/quill/quill.snow.css';
  let proposalQuillLoaded = false;
  let proposalQuillLoading = false;
  let proposalQuillReadyCallbacks = [];

  function ensureProposalQuillFormats() {
    if (!window.Quill || window.__proposalQuillFormatsReady) return;
    const Font = window.Quill.import('formats/font');
    Font.whitelist = ['cambria', 'sans', 'serif', 'monospace', 'georgia', 'times-new-roman'];
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
    ['customer', 'asset_owner'].forEach(function (fieldName) {
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
    const form = root.closest('form[data-proposal-form]') || root;
    const searchUrl = form.dataset.lerSearchUrl;
    if (!searchUrl) return;

    function bindLerAutocomplete(options) {
      const input = form.querySelector(options.inputSelector);
      const list = form.querySelector(options.listSelector);
      if (!input || !list || input.dataset[options.boundKey] === '1') return;
      input.dataset[options.boundKey] = '1';

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
        const countrySelect = form.querySelector(options.countrySelector);
        const identifierField = form.querySelector(options.identifierSelector);
        const registrationNumberField = form.querySelector(options.registrationNumberSelector);
        const registrationDateField = form.querySelector(options.registrationDateSelector);

        input.value = item.short_name || '';
        if (countrySelect && item.country_id) countrySelect.value = item.country_id;
        if (identifierField) identifierField.value = item.identifier || '';
        if (registrationNumberField) registrationNumberField.value = item.registration_number || '';
        if (registrationDateField) {
          setDateFieldValue(registrationDateField, item.registration_date || '');
          registrationDateField.dispatchEvent(new Event('input', { bubbles: true }));
          registrationDateField.dispatchEvent(new Event('change', { bubbles: true }));
        }

        if (options.changeEventName === 'proposal-customer-changed') {
          const matchesCheckbox = form.querySelector('[name="asset_owner_matches_customer"]');
          const ownerInput = form.querySelector('input[name="asset_owner"]');
          const ownerCountry = form.querySelector('#proposal-asset-owner-country-select');
          const ownerIdentifier = form.querySelector('#proposal-asset-owner-identifier-field');
          const ownerRegistrationNumber = form.querySelector('input[name="asset_owner_registration_number"]');
          const ownerRegistrationDate = form.querySelector('input[name="asset_owner_registration_date"]');
          if (
            matchesCheckbox?.checked
            && ownerInput
            && ownerCountry
            && ownerIdentifier
            && ownerRegistrationNumber
            && ownerRegistrationDate
          ) {
            ownerInput.value = item.short_name || '';
            ownerCountry.value = item.country_id || '';
            ownerIdentifier.value = item.identifier || '';
            ownerRegistrationNumber.value = item.registration_number || '';
            setDateFieldValue(ownerRegistrationDate, item.registration_date || '');
          }
        }

        list.classList.remove('show');
        if (options.changeEventName) {
          form.dispatchEvent(new CustomEvent(options.changeEventName));
          setTimeout(function () {
            form.dispatchEvent(new CustomEvent(options.changeEventName));
          }, 0);
        }
      }

      input.addEventListener('input', function () {
        const query = input.value.trim();
        clearTimeout(debounce);
        if (query.length < 1) {
          list.classList.remove('show');
          if (options.changeEventName) {
            form.dispatchEvent(new CustomEvent(options.changeEventName));
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
    }

    bindLerAutocomplete({
      inputSelector: 'input[name="customer"]',
      listSelector: '#proposal-ler-ac-list',
      boundKey: 'lerBoundCustomer',
      countrySelector: '#proposal-country-select',
      identifierSelector: '#proposal-identifier-field',
      registrationNumberSelector: 'input[name="registration_number"]',
      registrationDateSelector: 'input[name="registration_date"]',
      changeEventName: 'proposal-customer-changed',
    });
    bindLerAutocomplete({
      inputSelector: 'input[name="asset_owner"]',
      listSelector: '#proposal-asset-owner-ler-ac-list',
      boundKey: 'lerBoundAssetOwner',
      countrySelector: '#proposal-asset-owner-country-select',
      identifierSelector: '#proposal-asset-owner-identifier-field',
      registrationNumberSelector: 'input[name="asset_owner_registration_number"]',
      registrationDateSelector: 'input[name="asset_owner_registration_date"]',
      changeEventName: 'proposal-asset-owner-changed',
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
    const wrap = input.closest('.proposal-asset-ler-wrap, .ler-ac-wrap');

    function setOpenState(isOpen) {
      wrap?.classList.toggle('is-open', !!isOpen);
      row?.classList.toggle('proposal-autocomplete-open', !!isOpen);
    }

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

  function getProposalTypeId(form) {
    return (form?.querySelector('select[name="type"]')?.value || '').trim();
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
    const assetsPayloadInput = form?.querySelector('#proposal-assets-payload');
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

  function attachProposalServicesStore(root) {
    if (!root) return null;
    const form = root.closest('form[data-proposal-form]') || root;
    const commercialInput = form.querySelector('#proposal-commercial-offer-payload');
    const serviceInput = form.querySelector('#proposal-service-sections-payload');
    if (!commercialInput || !serviceInput) return null;
    if (form.__proposalServicesStore) return form.__proposalServicesStore;

    function parsePayload(input) {
      try {
        const data = JSON.parse(input?.value || '[]');
        return Array.isArray(data) ? data : [];
      } catch (error) {
        return [];
      }
    }

    function normalizeRow(row, options) {
      const serviceName = String(row?.service_name || '').trim();
      const autofill = getProposalCommercialAutofill(form, serviceName);
      const specialty = autofill.jobTitle || String(row?.job_title || '').trim();
      const forceAutofill = options?.forceAutofill === true;
      const specialistValue = String(row?.specialist || '').trim();
      const statusValue = String(row?.professional_status || '').trim();
      const specialist = forceAutofill ? autofill.specialist : (specialistValue || autofill.specialist);
      const specialistStatus = getProposalCommercialSpecialistStatus(form, serviceName, specialist);
      const currentRate = String(row?.rate_eur_per_day || '').trim();
      const autofillRate = getProposalCommercialRateValue(form, serviceName, specialist);
      const currentDayCounts = Array.isArray(row?.asset_day_counts)
        ? row.asset_day_counts.map(function (value) { return String(value ?? '').trim(); })
        : [];
      const autofillDayCounts = getProposalCommercialDayCounts(form, serviceName, currentDayCounts, {
        replaceAll: forceAutofill,
      });
      return {
        specialist: specialist,
        job_title: specialty,
        professional_status: forceAutofill
          ? (specialistStatus || autofill.professionalStatus)
          : (statusValue || specialistStatus || autofill.professionalStatus),
        service_name: serviceName,
        code: getProposalTypicalSectionCode(form, serviceName) || String(row?.code || '').trim(),
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
      const count = Math.max(commercialRows.length, serviceRows.length);
      const rows = [];
      for (let index = 0; index < count; index += 1) {
        const commercialRow = commercialRows[index] || {};
        const serviceRow = serviceRows[index] || {};
        rows.push(normalizeRow({
          ...commercialRow,
          service_name: serviceRow.service_name ?? commercialRow.service_name ?? '',
          code: serviceRow.code ?? commercialRow.code ?? '',
        }));
      }
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
      return rows.map(function (row) {
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
      form.dispatchEvent(new CustomEvent('proposal-commercial-changed', { detail: detail }));
      form.dispatchEvent(new CustomEvent('proposal-service-sections-changed', {
        detail: {
          rows: detail.serviceRows,
          meta: meta || null,
        },
      }));
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
        syncHiddenInputs();
        emit(meta);
      },
      commitServiceRows: function (nextRows, meta) {
        const currentRows = api.getRows();
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
        syncHiddenInputs();
        emit(meta);
      },
      replaceFromType: function (meta) {
        api.commitServiceRows(
          getProposalTypicalSectionEntries(form).map(function (entry) {
            return {
              service_name: (entry?.name || '').trim(),
              code: (entry?.code || '').trim(),
            };
          }).filter(function (entry) {
            return !!entry.service_name;
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
    form.__proposalServicesStore = api;
    return api;
  }

  function attachProposalCommercialTable(root, assetsApi) {
    if (!root) return null;
    const form = root.closest('form[data-proposal-form]') || root;
    const servicesStore = attachProposalServicesStore(form);
    const table = form.querySelector('#proposal-commercial-table');
    const payloadInput = form.querySelector('#proposal-commercial-offer-payload');
    const thead = form.querySelector('#proposal-commercial-thead');
    const tbody = form.querySelector('#proposal-commercial-tbody');
    const addBtn = form.querySelector('#proposal-commercial-add-btn');
    const actions = form.querySelector('#proposal-commercial-row-actions');
    const upBtn = form.querySelector('#proposal-commercial-up-btn');
    const downBtn = form.querySelector('#proposal-commercial-down-btn');
    const deleteBtn = form.querySelector('#proposal-commercial-delete-btn');
    if (!table || !payloadInput || !thead || !tbody || !addBtn || !actions || !upBtn || !downBtn || !deleteBtn) return null;
    if (form.dataset.commercialBound === '1') return form.__proposalCommercialTableApi || null;
    form.dataset.commercialBound = '1';

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
          + '<th>Профессиональный статус</th>'
          + '<th>Специальность</th>'
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
        + '<th rowspan="2">Профессиональный статус</th>'
        + '<th rowspan="2">Специальность</th>'
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
        recalcRowTotal(row);
        return;
      }

      assetRows.forEach(function (_assetRow, index) {
        const dayCell = createProposalTableCell(
          'proposal-commercial-day-cell' + (assetRows.length === 1 ? ' proposal-commercial-day-cell-single' : '')
        );
        applyCommercialDayColumnWidth(dayCell, dayColumnWidths[index]);
        const input = document.createElement('input');
        input.type = 'number';
        input.min = '0';
        input.step = '1';
        input.className = 'form-control proposal-commercial-day-count';
        input.value = sourceValues[index] ?? '';
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
      syncDayCells(row, getAssetRows(), data.asset_day_counts || []);
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
      specialistTd.appendChild(specialistSelect);
      row.appendChild(specialistTd);

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
      statusTd.appendChild(statusInput);
      row.appendChild(statusTd);

      const titleTd = createProposalTableCell();
      const titleInput = document.createElement('input');
      titleInput.type = 'text';
      titleInput.className = 'form-control proposal-commercial-job-title readonly-field';
      titleInput.readOnly = true;
      titleInput.tabIndex = -1;
      titleInput.value = data.job_title || autofill.jobTitle || '';
      titleTd.appendChild(titleInput);
      row.appendChild(titleTd);

      const serviceTd = createProposalTableCell();
      const serviceSelect = document.createElement('select');
      serviceSelect.className = 'form-select proposal-commercial-service';
      syncProposalCommercialServiceSelect(serviceSelect, form, data.service_name || '');
      serviceSelect.value = data.service_name || '';
      serviceTd.appendChild(serviceSelect);
      row.appendChild(serviceTd);

      const rateTd = createProposalTableCell('proposal-commercial-rate-cell');
      const rateInput = document.createElement('input');
      rateInput.type = 'text';
      rateInput.className = 'form-control js-money-input proposal-commercial-rate';
      rateInput.inputMode = 'decimal';
      rateInput.value = data.rate_eur_per_day ? fmtMoney(data.rate_eur_per_day) : '';
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

      syncDayCells(row, getAssetRows(), data.asset_day_counts || []);

      [statusInput].forEach(function (input) {
        input.addEventListener('change', function () {
          updatePayload({ reason: 'commercial-field-edit', rowIndex: getRows().indexOf(row) });
        });
      });
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

      rateInput.addEventListener('change', function () {
        recalcRowTotal(row);
        updatePayload({ reason: 'commercial-field-edit', rowIndex: getRows().indexOf(row) });
      });
      rateInput.addEventListener('input', function () {
        recalcRowTotal(row);
        updatePayload({ reason: 'commercial-field-edit', rowIndex: getRows().indexOf(row) });
      });

      attachMoneyInputs(row);
      recalcRowTotal(row);
      return row;
    }

    function renderRows(dataRows) {
      tbody.innerHTML = '';
      (dataRows || []).forEach(function (item) {
        tbody.appendChild(createRow(item || {}));
      });
      syncActions();
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
      row.querySelector('.proposal-commercial-specialist')?.focus();
    });

    upBtn.addEventListener('click', function () { moveSelected('up'); });
    downBtn.addEventListener('click', function () { moveSelected('down'); });
    deleteBtn.addEventListener('click', deleteSelected);

    form.addEventListener('proposal-assets-changed', function (event) {
      const rows = Array.isArray(event.detail?.rows) ? event.detail.rows : getAssetRows();
      const meta = event.detail?.meta || {};
      renderHeader(rows);
      getRows().forEach(function (row) {
        if (meta.reason === 'row-add') {
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
        syncDayCells(row, rows);
      });
      updatePayload({ reason: 'sync-asset-columns' });
    });

    servicesStore.subscribe(function (detail) {
      if (detail?.meta?.source === 'commercial-view') return;
      renderRows(detail?.rows || []);
    });

    renderHeader(getAssetRows());
    renderRows(parsePayload());

    const api = {
      getSerializedRows: function () {
        return servicesStore ? servicesStore.getRows() : getRows().map(serializeRow);
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
    form.__proposalCommercialTableApi = api;
    return api;
  }

  function attachProposalServiceSectionsTable(root) {
    if (!root) return null;
    const form = root.closest('form[data-proposal-form]') || root;
    const servicesStore = attachProposalServicesStore(form);
    const payloadInput = form.querySelector('#proposal-service-sections-payload');
    const tbody = form.querySelector('#proposal-service-sections-tbody');
    const addBtn = form.querySelector('#proposal-service-section-add-btn');
    const actions = form.querySelector('#proposal-service-sections-row-actions');
    const upBtn = form.querySelector('#proposal-service-section-up-btn');
    const downBtn = form.querySelector('#proposal-service-section-down-btn');
    const deleteBtn = form.querySelector('#proposal-service-section-delete-btn');
    const masterCheck = form.querySelector('#proposal-service-sections-master-check');
    if (!payloadInput || !tbody || !addBtn || !actions || !upBtn || !downBtn || !deleteBtn) return null;
    if (form.dataset.serviceSectionsBound === '1') return form.__proposalServiceSectionsTableApi || null;
    form.dataset.serviceSectionsBound = '1';

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

    form.querySelector('select[name="type"]')?.addEventListener('change', function () {
      if (servicesStore) {
        servicesStore.replaceFromType({ reason: 'sync-services-by-type', source: 'type-change' });
        return;
      }
    });

    if (servicesStore) {
      servicesStore.subscribe(function (detail) {
        if (detail?.meta?.source === 'service-view') return;
        renderRows(detail?.serviceRows || []);
      });
      if (!servicesStore.getRows().length && getProposalTypeId(form)) {
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
    form.__proposalServiceSectionsTableApi = api;
    return api;
  }

  function attachProposalServiceTextEditor(root) {
    if (!root) return null;
    const form = root.closest('form[data-proposal-form]') || root;
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
      if (api && typeof api.getSerializedRows === 'function') {
        return api.getSerializedRows().filter(function (item) {
          return (item.service_name || '').trim();
        });
      }
      try {
        const rows = JSON.parse(payloadInput.value || '[]');
        return Array.isArray(rows) ? rows.filter(function (item) {
          return (item?.service_name || '').trim();
        }) : [];
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
        const defaultPlainText = getProposalTypicalServiceCompositionText(form, sections[index] || item);
        return {
          ...item,
          html: defaultPlainText ? normalizeTextToHtml(defaultPlainText) : '',
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
          return;
        }
        if (button.dataset.list) {
          const listType = button.dataset.list;
          const currentList = activeQuill.getFormat().list || false;
          activeQuill.format('list', currentList === listType ? false : listType);
          return;
        }
        if (button.dataset.align) {
          const align = button.dataset.align;
          activeQuill.format('align', align === 'left' ? false : align);
          return;
        }
        if (button.dataset.applyColor) {
          const formatName = button.dataset.applyColor;
          const input = toolbar.querySelector('[data-color-source="' + formatName + '"]');
          activeQuill.format(formatName, input?.value || false);
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
        quill.format('align', 'justify');
        quill.on('selection-change', function (range) {
          if (range) {
            lastRange = range;
            setActiveEditor(quill, fieldset);
          }
        });
        quill.on('text-change', function () {
          const currentHtml = quill.root.innerHTML === '<p><br></p>' ? '' : quill.root.innerHTML;
          const currentText = quill.getText().replace(/\s+$/, '').trim();
          draftState[index].html = currentHtml;
          draftState[index].plain_text = currentText;
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
      if (getMode() === 'sections') {
        textarea.value = composeTextareaValue(draftState);
      }
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

    function syncAssetOwnerFromCustomer() {
      const matchesCheckbox = form.querySelector('[name="asset_owner_matches_customer"]');
      const customerInput = form.querySelector('input[name="customer"]');
      const customerCountry = form.querySelector('#proposal-country-select');
      const customerIdentifier = form.querySelector('#proposal-identifier-field');
      const customerRegistrationNumber = form.querySelector('input[name="registration_number"]');
      const customerRegistrationDate = form.querySelector('input[name="registration_date"]');
      const ownerInput = form.querySelector('input[name="asset_owner"]');
      const ownerCountry = form.querySelector('#proposal-asset-owner-country-select');
      const ownerIdentifier = form.querySelector('#proposal-asset-owner-identifier-field');
      const ownerRegistrationNumber = form.querySelector('input[name="asset_owner_registration_number"]');
      const ownerRegistrationDate = form.querySelector('input[name="asset_owner_registration_date"]');
      if (!matchesCheckbox || !ownerInput || !ownerCountry || !ownerIdentifier || !ownerRegistrationNumber || !ownerRegistrationDate) {
        return;
      }

      function setLockedState(locked) {
        ownerInput.readOnly = locked;
        ownerInput.tabIndex = locked ? -1 : 0;
        ownerInput.classList.toggle('readonly-field', locked);
        ownerCountry.disabled = locked;
        ownerCountry.classList.toggle('readonly-field', locked);
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
        ownerIdentifier.value = customerIdentifier ? (customerIdentifier.value || '') : '';
        ownerRegistrationNumber.value = customerRegistrationNumber ? (customerRegistrationNumber.value || '') : '';
        setDateFieldValue(ownerRegistrationDate, customerRegistrationDate ? (customerRegistrationDate.value || '') : '');
        setLockedState(true);
        form.dispatchEvent(new CustomEvent('proposal-asset-owner-changed'));
        return;
      }

      setLockedState(false);
      form.dispatchEvent(new CustomEvent('proposal-asset-owner-changed'));
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
      form.querySelector('select[name="type"]')?.addEventListener('change', function () {
        syncPrefixFromType(true);
      });

      options.syncPrefixFromType(false);
      syncSuffixFromAssetOwner();
      syncCombinedValue();
    }

    attachGroupSelectDisplay(form);
    attachCountryIdentifierSync(form);
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
      'evaluation_date',
      'preliminary_report_date',
      'final_report_date',
    ].forEach(function (fieldName) {
      initProposalDateInput(form.querySelector('input[name="' + fieldName + '"]'));
    });
    const assetsApi = attachProposalAssetsTable(form);
    attachProposalServiceSectionsTable(form);
    attachProposalServiceTextEditor(form);
    const legalEntitiesApi = attachProposalLegalEntitiesTable(form);
    const objectsApi = attachProposalObjectsTable(form);
    attachProposalCommercialTable(form, assetsApi);
    attachProposalAssetsToLegalEntitiesSync(form, assetsApi, legalEntitiesApi);
    attachProposalLegalEntitiesToObjectsSync(form, legalEntitiesApi, objectsApi);
    form.querySelector('[name="advance_percent"]')?.addEventListener('input', syncFinalReportPercent);
    form.querySelector('[name="preliminary_report_percent"]')?.addEventListener('input', syncFinalReportPercent);
    form.querySelector('[name="asset_owner_matches_customer"]')?.addEventListener('change', syncAssetOwnerFromCustomer);
    ['customer', 'registration_number', 'registration_date'].forEach(function (fieldName) {
      form.querySelector('[name="' + fieldName + '"]')?.addEventListener('input', syncAssetOwnerFromCustomer);
      form.querySelector('[name="' + fieldName + '"]')?.addEventListener('change', syncAssetOwnerFromCustomer);
    });
    form.querySelector('#proposal-country-select')?.addEventListener('change', syncAssetOwnerFromCustomer);
    form.addEventListener('proposal-customer-changed', syncAssetOwnerFromCustomer);
    syncFinalReportPercent();
    syncAssetOwnerFromCustomer();
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
