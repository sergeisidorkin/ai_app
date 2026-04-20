(function () {
  const rootSelector = '#contacts';
  window.__contactsTableSel = window.__contactsTableSel || {};
  const TABLE_CONFIG = {
    'prs-select': { target: '#contacts-persons-table-wrap', swap: 'innerHTML', url: '/contacts/prs/table/', pageParam: 'prs_page', pageInputId: 'prs-page-input' },
    'ctz-select': { target: '#contacts-citizenships-table-wrap', swap: 'innerHTML', url: '/contacts/ctz/table/', pageParam: 'ctz_page', pageInputId: 'ctz-page-input' },
    'psn-select': { target: '#contacts-positions-table-wrap', swap: 'innerHTML', url: '/contacts/psn/table/', pageParam: 'psn_page', pageInputId: 'psn-page-input' },
    'tel-select': { target: '#contacts-phones-table-wrap', swap: 'innerHTML', url: '/contacts/tel/table/', pageParam: 'tel_page', pageInputId: 'tel-page-input' },
    'eml-select': { target: '#contacts-emails-table-wrap', swap: 'innerHTML', url: '/contacts/eml/table/', pageParam: 'eml_page', pageInputId: 'eml-page-input' },
  };
  const CONTACTS_FILTER_TABLES = ['prs-select', 'ctz-select', 'psn-select', 'tel-select', 'eml-select'];
  const CONTACTS_PERSON_FILTER_ALL = '__all__';
  const CONTACTS_PERSON_FILTER_PREF_KEY = 'contacts:person-filter';
  const CONTACTS_PERSON_FILTER_OPTIONS_URL = '/contacts/prs/filter-options/';
  window.__contactsPersonFilter = window.__contactsPersonFilter || (
    window.UIPref ? UIPref.get(CONTACTS_PERSON_FILTER_PREF_KEY, [CONTACTS_PERSON_FILTER_ALL]) : [CONTACTS_PERSON_FILTER_ALL]
  );
  const SECTION_TABLE_MAP = {
    persons: 'prs-select',
    citizenships: 'ctz-select',
    positions: 'psn-select',
    phones: 'tel-select',
    emails: 'eml-select',
  };
  const SECTION_TITLES = {
    persons: 'База контактов',
    citizenships: 'База контактов',
    positions: 'База контактов',
    phones: 'База контактов',
    emails: 'База контактов',
  };
  const PANEL_NAME_MAP = {
    'prs-actions': 'prs-select',
    'ctz-actions': 'ctz-select',
    'psn-actions': 'psn-select',
    'tel-actions': 'tel-select',
    'eml-actions': 'eml-select',
  };

  function inContacts(node) {
    return !!(node && node.closest && node.closest(rootSelector));
  }

  function paneOf(node) {
    return node && node.closest ? node.closest('#contacts-persons-pane, #contacts-citizenships-pane, #contacts-positions-pane, #contacts-phones-pane, #contacts-emails-pane') : null;
  }

  function getMasterForName(name) {
    return document.querySelector(rootSelector + ' input.form-check-input[data-target-name="' + name + '"]');
  }

  function getRowChecksByName(name) {
    return Array.from(document.querySelectorAll(rootSelector + ' tbody input.form-check-input[name="' + name + '"]'));
  }

  function getCheckedByName(name) {
    return getRowChecksByName(name).filter(function (item) { return item.checked; });
  }

  function updateRowHighlightFor(name) {
    getRowChecksByName(name).forEach(function (checkbox) {
      var row = checkbox.closest('tr');
      if (row) row.classList.toggle('table-active', checkbox.checked);
    });
  }

  function updateMasterStateFor(name) {
    var master = getMasterForName(name);
    if (!master) return;
    var boxes = getRowChecksByName(name);
    var checked = boxes.filter(function (item) { return item.checked; }).length;
    master.checked = !!boxes.length && checked === boxes.length;
    master.indeterminate = checked > 0 && checked < boxes.length;
  }

  function ensureActionsVisibility(name) {
    var master = getMasterForName(name);
    var actionsId = master && master.dataset ? master.dataset.actionsId : '';
    if (!actionsId) return;
    var panel = document.getElementById(actionsId);
    if (!panel) return;
    panel.classList.toggle('d-none', getCheckedByName(name).length === 0);
  }

  function rememberSelection(name) {
    window.__contactsTableSel[name] = getCheckedByName(name).map(function (item) {
      return String(item.value);
    });
  }

  function restoreSelection(name) {
    var ids = window.__contactsTableSel[name] || [];
    if (!ids.length) return;
    var idSet = new Set(ids);
    getRowChecksByName(name).forEach(function (checkbox) {
      checkbox.checked = idSet.has(String(checkbox.value));
    });
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
  }

  function getSelectedContactsPersonFilterValues() {
    var values = Array.isArray(window.__contactsPersonFilter) ? window.__contactsPersonFilter.slice() : [CONTACTS_PERSON_FILTER_ALL];
    return values.length ? values : [CONTACTS_PERSON_FILTER_ALL];
  }

  function getExplicitContactsPersonFilterValues(values) {
    return (values || getSelectedContactsPersonFilterValues()).filter(function (value) {
      return value && value !== CONTACTS_PERSON_FILTER_ALL;
    });
  }

  function setSelectedContactsPersonFilterValues(values) {
    var explicitValues = getExplicitContactsPersonFilterValues(values);
    window.__contactsPersonFilter = explicitValues.length ? explicitValues : [CONTACTS_PERSON_FILTER_ALL];
    if (window.UIPref) {
      window.UIPref.set(CONTACTS_PERSON_FILTER_PREF_KEY, window.__contactsPersonFilter);
    }
  }

  function resetContactsRegistryPages() {
    CONTACTS_FILTER_TABLES.forEach(function (name) {
      var cfg = TABLE_CONFIG[name];
      var input = cfg && cfg.pageInputId ? document.getElementById(cfg.pageInputId) : null;
      if (input) input.value = '1';
    });
  }

  function appendContactsPersonFilter(parts) {
    var values = getSelectedContactsPersonFilterValues();
    if (!values.length || values.includes(CONTACTS_PERSON_FILTER_ALL)) return;
    parts.push('prs_ids=' + encodeURIComponent(values.join(',')));
  }

  function buildContactsTableUrl(name) {
    var cfg = TABLE_CONFIG[name];
    if (!cfg) return '';
    var parts = [];
    appendContactsPersonFilter(parts);
    var pageInput = cfg.pageInputId ? document.getElementById(cfg.pageInputId) : null;
    var pageValue = pageInput ? String(pageInput.value || '').trim() : '';
    if (cfg.pageParam && pageValue) {
      parts.push(cfg.pageParam + '=' + encodeURIComponent(pageValue));
    }
    return cfg.url + (parts.length ? ('?' + parts.join('&')) : '');
  }

  function refreshTable(name) {
    var cfg = TABLE_CONFIG[name];
    if (!cfg || !window.htmx) return Promise.resolve();
    return htmx.ajax('GET', buildContactsTableUrl(name), { target: cfg.target, swap: cfg.swap });
  }

  function refreshTables(names) {
    var items = Array.from(new Set((names || []).filter(Boolean)));
    var currentTable = SECTION_TABLE_MAP[window.__currentContactsSection || ''];
    if (currentTable && items.includes(currentTable)) {
      items = items.filter(function (name) { return name !== currentTable; });
      items.push(currentTable);
    }
    return Promise.resolve().then(async function () {
      for (var i = 0; i < items.length; i++) {
        await refreshTable(items[i]);
      }
    });
  }

  function activateInlineScripts(container) {
    if (!container) return;
    container.querySelectorAll('script').forEach(function (script) {
      var replacement = document.createElement('script');
      Array.from(script.attributes).forEach(function (attr) {
        replacement.setAttribute(attr.name, attr.value);
      });
      replacement.textContent = script.textContent;
      script.parentNode.replaceChild(replacement, script);
    });
  }

  function parseTelCountryMeta(form) {
    if (!form || !form.dataset) return {};
    try {
      return JSON.parse(form.dataset.countryMeta || '{}');
    } catch (error) {
      return {};
    }
  }

  function syncContactsModalSize(scope) {
    var container = scope instanceof Element ? scope : document;
    var modal = container.closest ? container.closest('#contacts-modal') : null;
    if (!modal) {
      modal = document.getElementById('contacts-modal');
    }
    if (!modal) return;
    var dialog = modal.querySelector('.modal-dialog');
    if (!dialog) return;
    var form = modal.querySelector('.modal-content form');
    var targetSize = form && form.dataset ? (form.dataset.modalSize || '').trim() : '';
    dialog.classList.remove('modal-sm', 'modal-lg', 'modal-xl', 'modal-fullscreen', 'modal-xxl');
    if (targetSize) {
      dialog.classList.add('modal-' + targetSize);
    } else {
      dialog.classList.add('modal-lg');
    }
  }

  function initPositionForms(container) {
    var scope = container || document;
    var forms = [];
    if (scope instanceof Element && scope.matches && scope.matches('form[data-position-form="1"]')) {
      forms = [scope];
    } else if (scope.querySelectorAll) {
      forms = Array.from(scope.querySelectorAll('form[data-position-form="1"]'));
    }
    forms.forEach(function (form) {
      if (!form || form.dataset.positionFormBound === '1') return;
      var searchUrl = form.dataset.lerSearchUrl || '';
      var input = form.querySelector('#psn-organization-input');
      var list = form.querySelector('#psn-organization-ler-ac-list');
      var identifierField = form.querySelector('#psn-organization-identifier-field');
      var registrationNumberField = form.querySelector('#psn-organization-registration-number-field');
      if (!searchUrl || !input || !list || !identifierField || !registrationNumberField) return;

      form.dataset.positionFormBound = '1';
      var debounce = null;
      var results = [];
      var picking = false;

      function escapeHtml(value) {
        return String(value || '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
      }

      function highlight(text, query) {
        if (!query) return escapeHtml(text);
        var escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return escapeHtml(text).replace(new RegExp('(' + escaped + ')', 'gi'), '<mark>$1</mark>');
      }

      function clearOrganizationMeta() {
        identifierField.value = '';
        registrationNumberField.value = '';
      }

      function hideList() {
        list.classList.remove('show');
        list.innerHTML = '';
        results = [];
      }

      function render(items, query, totalCount) {
        results = items;
        if (!items.length) {
          hideList();
          return;
        }
        var visible = items.slice(0, 3);
        var html = visible.map(function (item, index) {
          var main = highlight(item.short_name || '', query);
          var parts = [item.full_name, item.identifier, item.registration_number].filter(Boolean);
          var sub = parts.length ? highlight(parts.join(' · '), query) : '';
          return '<div class="ler-ac-item js-position-org-search-item" data-idx="' + index + '">'
            + '<div class="ler-ac-main">' + main + '</div>'
            + (sub ? '<div class="ler-ac-sub">' + sub + '</div>' : '')
            + '</div>';
        }).join('');
        var remaining = totalCount - visible.length;
        if (remaining > 0) {
          html += '<div class="ler-ac-item ler-ac-more">Найдено ещё ' + remaining + ' юрлиц</div>';
        }
        list.innerHTML = html;
        list.classList.add('show');
      }

      function pick(item) {
        input.value = item.short_name || '';
        identifierField.value = item.identifier || '';
        registrationNumberField.value = item.registration_number || '';
        hideList();
      }

      input.addEventListener('input', function () {
        var query = String(input.value || '').trim();
        clearOrganizationMeta();
        if (debounce) clearTimeout(debounce);
        if (query.length < 1) {
          hideList();
          return;
        }
        debounce = setTimeout(function () {
          fetch(searchUrl + '?q=' + encodeURIComponent(query), {
            headers: { 'X-Requested-With': 'fetch' },
          })
            .then(function (response) { return response.json(); })
            .then(function (data) {
              render(data.results || [], query, data.total_count || 0);
            })
            .catch(function () {
              hideList();
            });
        }, 200);
      });

      list.addEventListener('mousedown', function (event) {
        event.preventDefault();
        picking = true;
        var itemNode = event.target.closest('.js-position-org-search-item');
        if (!itemNode) return;
        var idx = parseInt(itemNode.dataset.idx, 10);
        if (results[idx]) pick(results[idx]);
      });

      list.addEventListener('click', function (event) {
        var itemNode = event.target.closest('.js-position-org-search-item');
        if (!itemNode) return;
        var idx = parseInt(itemNode.dataset.idx, 10);
        if (results[idx]) pick(results[idx]);
        picking = false;
      });

      input.addEventListener('blur', function () {
        if (picking) {
          picking = false;
          return;
        }
        window.setTimeout(hideList, 200);
      });

      input.addEventListener('focus', function () {
        if (results.length && String(input.value || '').trim().length >= 1) {
          list.classList.add('show');
        }
      });
    });
  }

  async function initContactsPersonMasterFilter(forceReload) {
    var dropdown = document.getElementById('master-contacts-prs-filter-dropdown');
    var toggle = document.getElementById('contacts-prs-filter-toggle');
    var menu = dropdown && dropdown.querySelector ? dropdown.querySelector('.classifiers-bsn-filter-menu') : null;
    var selectedContainer = document.getElementById('contacts-prs-filter-selected');
    var searchInput = document.getElementById('contacts-prs-filter-search');
    var searchList = document.getElementById('contacts-prs-filter-search-list');
    var clearButton = document.getElementById('contacts-prs-filter-clear');
    var applyButton = document.getElementById('contacts-prs-filter-apply');
    var hintNode = document.getElementById('contacts-prs-filter-hint');
    var labelNode = document.querySelector('.js-contacts-prs-filter-label');
    if (!dropdown || !toggle || !menu || !selectedContainer || !searchInput || !searchList || !clearButton || !applyButton) return;

    var state = dropdown.__prsFilterState || {
      cache: {},
      draftValues: [],
      searchResults: [],
      searchTotalCount: 0,
      searchDebounce: null,
      picking: false,
    };
    dropdown.__prsFilterState = state;

    function escapeHtml(value) {
      return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function highlight(text, query) {
      if (!query) return escapeHtml(text);
      var escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      return escapeHtml(text).replace(new RegExp('(' + escapedQuery + ')', 'gi'), '<mark>$1</mark>');
    }

    function hideSearchResults() {
      searchList.classList.remove('show');
      searchList.innerHTML = '';
      state.searchResults = [];
      state.searchTotalCount = 0;
    }

    function updateLabel(values) {
      if (!labelNode) return;
      var explicitValues = getExplicitContactsPersonFilterValues(values);
      if (!explicitValues.length) {
        labelNode.textContent = 'Все';
        return;
      }
      if (explicitValues.length === 1) {
        var item = state.cache[explicitValues[0]];
        labelNode.textContent = (item && (item.summary_label || item.formatted_id)) || '1 выбрано';
        return;
      }
      labelNode.textContent = explicitValues.length + ' выбрано';
    }

    async function fetchFilterItems(params) {
      var url = new URL(CONTACTS_PERSON_FILTER_OPTIONS_URL, window.location.origin);
      Object.keys(params || {}).forEach(function (key) {
        var value = params[key];
        if (Array.isArray(value)) {
          value.forEach(function (item) {
            if (item !== undefined && item !== null && item !== '') url.searchParams.append(key, item);
          });
        } else if (value !== undefined && value !== null && value !== '') {
          url.searchParams.set(key, value);
        }
      });
      var resp = await fetch(url.toString(), {
        headers: { 'X-Requested-With': 'fetch' },
      });
      return resp.json();
    }

    async function ensureItemDetails(values, forceFetch) {
      var explicitValues = getExplicitContactsPersonFilterValues(values);
      var missing = explicitValues.filter(function (value) {
        return forceFetch || !state.cache[value];
      });
      if (!missing.length) return;
      try {
        var payload = await fetchFilterItems({ ids: missing });
        var items = Array.isArray(payload.results) ? payload.results : [];
        items.forEach(function (item) {
          state.cache[String(item.id)] = item;
        });
      } catch (error) {}
    }

    function renderSelectedValues() {
      var values = getExplicitContactsPersonFilterValues(state.draftValues);
      if (!values.length) {
        selectedContainer.innerHTML = '';
        selectedContainer.classList.add('d-none');
        if (hintNode) hintNode.classList.remove('d-none');
        return;
      }
      selectedContainer.classList.remove('d-none');
      if (hintNode) hintNode.classList.add('d-none');
      selectedContainer.innerHTML = values.map(function (value, index) {
        var item = state.cache[value] || { formatted_id: value, label: value };
        var inputId = 'contacts-prs-filter-selected-' + value + '-' + index;
        return '<div class="form-check mb-2">'
          + '<input class="form-check-input js-contacts-prs-filter-selected" type="checkbox" checked value="' + escapeHtml(value) + '" id="' + escapeHtml(inputId) + '">'
          + '<label class="form-check-label" for="' + escapeHtml(inputId) + '">' + escapeHtml(item.label || item.formatted_id || value) + '</label>'
          + '</div>';
      }).join('');
    }

    function renderSearchResults(query) {
      searchList.innerHTML = '';
      if (!state.searchResults.length) {
        hideSearchResults();
        return;
      }
      var visible = state.searchResults.slice(0, 3);
      var html = visible.map(function (item, index) {
        return '<div class="ler-ac-item js-contacts-prs-search-item" data-idx="' + index + '">'
          + '<div class="ler-ac-main">' + highlight(item.label || '', query) + '</div>'
          + '</div>';
      }).join('');
      if (state.searchTotalCount > 3) {
        html += '<div class="ler-ac-item ler-ac-more">Найдено еще ' + (state.searchTotalCount - 3) + ' записей</div>';
      }
      searchList.innerHTML = html;
      searchList.classList.add('show');
      searchList.style.width = '100%';
      searchList.style.minWidth = '100%';
    }

    function resetDraftFromApplied() {
      state.draftValues = getExplicitContactsPersonFilterValues();
      renderSelectedValues();
      hideSearchResults();
      searchInput.value = '';
    }

    async function searchItems(query) {
      try {
        var payload = await fetchFilterItems({ q: query });
        var results = Array.isArray(payload.results) ? payload.results : [];
        results.forEach(function (item) {
          state.cache[String(item.id)] = item;
        });
        state.searchResults = results;
        state.searchTotalCount = payload.total_count || results.length;
        renderSearchResults(query);
      } catch (error) {
        hideSearchResults();
      }
    }

    async function applySelection() {
      var nextValues = getExplicitContactsPersonFilterValues(state.draftValues);
      await ensureItemDetails(nextValues, false);
      setSelectedContactsPersonFilterValues(nextValues);
      updateLabel(nextValues);
      resetContactsRegistryPages();
      await refreshTables(CONTACTS_FILTER_TABLES);
      if (window.bootstrap && window.bootstrap.Dropdown) {
        window.bootstrap.Dropdown.getOrCreateInstance(toggle).hide();
      }
    }

    await ensureItemDetails(getSelectedContactsPersonFilterValues(), !!forceReload);
    updateLabel(getSelectedContactsPersonFilterValues());

    if (dropdown.dataset.prsFilterLoaded === '1') return;

    searchInput.addEventListener('input', function () {
      var query = (searchInput.value || '').trim();
      if (state.searchDebounce) clearTimeout(state.searchDebounce);
      if (query.length < 1) {
        hideSearchResults();
        return;
      }
      state.searchDebounce = setTimeout(function () {
        searchItems(query);
      }, 150);
    });

    searchInput.addEventListener('focus', function () {
      var query = (searchInput.value || '').trim();
      if (query) searchInput.dispatchEvent(new Event('input'));
    });

    searchInput.addEventListener('blur', function () {
      if (state.picking) {
        state.picking = false;
        return;
      }
      window.setTimeout(hideSearchResults, 150);
    });

    searchList.addEventListener('mousedown', function (event) {
      event.preventDefault();
      state.picking = true;
      var itemNode = event.target.closest('.js-contacts-prs-search-item');
      if (!itemNode) return;
      var idx = parseInt(itemNode.dataset.idx, 10);
      var item = state.searchResults[idx];
      if (!item) return;
      var value = String(item.id);
      if (!state.draftValues.includes(value)) state.draftValues.push(value);
      state.cache[value] = item;
      renderSelectedValues();
      searchInput.value = '';
      hideSearchResults();
    });

    selectedContainer.addEventListener('change', function (event) {
      var checkbox = event.target.closest('.js-contacts-prs-filter-selected');
      if (!checkbox) return;
      var value = String(checkbox.value || '');
      state.draftValues = state.draftValues.filter(function (item) { return item !== value; });
      renderSelectedValues();
    });

    clearButton.addEventListener('click', function () {
      state.draftValues = [];
      searchInput.value = '';
      hideSearchResults();
      renderSelectedValues();
    });

    applyButton.addEventListener('click', function () {
      applySelection().catch(function () {});
    });

    dropdown.addEventListener('shown.bs.dropdown', function () {
      ensureItemDetails(getSelectedContactsPersonFilterValues(), false).then(function () {
        resetDraftFromApplied();
        window.setTimeout(function () { searchInput.focus(); }, 0);
      });
    });

    dropdown.addEventListener('hide.bs.dropdown', function () {
      resetDraftFromApplied();
    });

    dropdown.dataset.prsFilterLoaded = '1';
  }

  function getLibPhone() {
    return window.libphonenumber || window['libphonenumber-js'] || null;
  }

  function getGoogleLibPhone() {
    return window.i18n && window.i18n.phonenumbers ? window.i18n.phonenumbers : null;
  }

  function initTelPhoneForms(container) {
    var scope = container || document;
    var forms = [];
    if (scope instanceof Element && scope.matches && scope.matches('form[data-tel-phone-form="1"]')) {
      forms = [scope];
    } else if (scope.querySelectorAll) {
      forms = Array.from(scope.querySelectorAll('form[data-tel-phone-form="1"]'));
    }
    forms.forEach(function (form) {
      if (!form || form.dataset.telPhoneBound === '1') return;

      var typeSelect = form.querySelector('#tel-type-select');
      var countrySelect = form.querySelector('#tel-country-select');
      var countryWrap = form.querySelector('#tel-country-wrap');
      var codeInput = form.querySelector('#tel-code-field');
      var phoneInput = form.querySelector('#tel-phone-field');
      var phoneWrap = form.querySelector('#tel-phone-wrap');
      var regionInput = form.querySelector('#tel-region-field');
      var regionWrap = form.querySelector('#tel-region-wrap');
      var extensionWrap = form.querySelector('#tel-extension-wrap');
      var flagBadge = form.querySelector('#tel-flag-badge');
      var lookupUrl = form.dataset.ruLandlineLookupUrl || '';
      var countryMeta = parseTelCountryMeta(form);
      if (!typeSelect || !countrySelect || !codeInput || !phoneInput) return;

      form.dataset.telPhoneBound = '1';
      var codeIti = null;
      var phoneIti = null;
      var phoneFormattingInProgress = false;
      var landlineLookupToken = 0;
      var ruLandlineShapeHint = null;
      var ruRegionLookupTimer = null;
      form.__lastTelPhoneInputTs = null;

      function cancelPendingRuLookup() {
        landlineLookupToken += 1;
      }

      function cancelScheduledRuRegionLookup() {
        if (ruRegionLookupTimer) {
          window.clearTimeout(ruRegionLookupTimer);
          ruRegionLookupTimer = null;
        }
      }

      function scheduleRuRegionLookup() {
        cancelScheduledRuRegionLookup();
        ruRegionLookupTimer = window.setTimeout(function () {
          ruRegionLookupTimer = null;
          syncRuRegistryLookup(String(phoneInput.value || ''), { applyFormattedNumber: true });
        }, 160);
      }

      function metaForCountryId(countryId) {
        return countryMeta[String(countryId)] || null;
      }

      function selectedMeta() {
        return metaForCountryId(countrySelect.value);
      }

      function findCountryIdByIso2(iso2) {
        var normalized = String(iso2 || '').toLowerCase();
        return Object.keys(countryMeta).find(function (countryId) {
          return String((countryMeta[countryId] || {}).iso2 || '').toLowerCase() === normalized;
        }) || '';
      }

      function syncCountrySelectByIso2(iso2) {
        var countryId = findCountryIdByIso2(iso2);
        if (countryId && countrySelect.value !== countryId) {
          countrySelect.value = countryId;
        }
      }

      function selectedPhoneType() {
        return String(typeSelect.value || 'mobile');
      }

      function isLandline() {
        return selectedPhoneType() === 'landline';
      }

      function isRussianRegistryPhone() {
        var meta = selectedMeta();
        return !!meta && String(meta.iso2 || '').toLowerCase() === 'ru';
      }

      function isRussianLandline() {
        return isLandline() && isRussianRegistryPhone();
      }

      function shouldShowRegionField() {
        return isRussianRegistryPhone();
      }

      function currentPlaceholder(selectedMeta) {
        if (!selectedMeta) return '';
        return isLandline() ? (selectedMeta.landlinePlaceholder || '') : (selectedMeta.mobilePlaceholder || '');
      }

      function syncPhoneTypeUi() {
        if (countryWrap) {
          countryWrap.classList.toggle('col-md-9', !shouldShowRegionField());
          countryWrap.classList.toggle('col-md-2', shouldShowRegionField());
        }
        if (regionWrap) {
          regionWrap.classList.toggle('d-none', !shouldShowRegionField());
          regionWrap.classList.toggle('col-md-7', shouldShowRegionField());
        }
        if (extensionWrap) {
          extensionWrap.classList.toggle('d-none', !isLandline());
        }
      }

      function fallbackSyncCodeFromCountry() {
        var currentMeta = selectedMeta();
        codeInput.value = currentMeta && currentMeta.dialCode ? currentMeta.dialCode : '';
        if (flagBadge) {
          flagBadge.textContent = currentMeta && currentMeta.flag ? currentMeta.flag : '--';
        }
        phoneInput.placeholder = currentPlaceholder(currentMeta);
      }

      function syncWidgetsFromCountry() {
        var selectedMeta = metaForCountryId(countrySelect.value);
        if (!selectedMeta) {
          codeInput.value = '';
          if (flagBadge) flagBadge.textContent = '--';
          return;
        }
        if (codeIti && selectedMeta.iso2) {
          codeIti.setCountry(selectedMeta.iso2);
        }
        if (phoneIti && selectedMeta.iso2 && !isLandline()) {
          phoneIti.setCountry(selectedMeta.iso2);
        }
        codeInput.value = selectedMeta.dialCode || '';
        if (flagBadge) {
          flagBadge.textContent = selectedMeta.flag || '--';
        }
      }

      function formatNumberAsYouType(rawValue) {
        var selectedMeta = metaForCountryId(countrySelect.value);
        var libPhone = getLibPhone();
        if (isLandline()) {
          return rawValue;
        }
        if (!selectedMeta || !selectedMeta.iso2) {
          return rawValue;
        }
        if (String(selectedMeta.iso2).toLowerCase() === 'ru') {
          return formatRuLocalNumber(rawValue);
        }
        if (!libPhone || !libPhone.AsYouType) {
          return rawValue;
        }
        try {
          var formatter = new libPhone.AsYouType(String(selectedMeta.iso2).toUpperCase());
          return formatter.input(rawValue) || rawValue;
        } catch (error) {
          return rawValue;
        }
      }

      function stripCountryCodeFromInput(rawValue) {
        var selectedMeta = metaForCountryId(countrySelect.value);
        var value = String(rawValue || '').trim();
        if (!selectedMeta || !selectedMeta.dialCode || !value) return value;
        var dialCode = String(selectedMeta.dialCode);
        var compactValue = value.replace(/[\s\-()]/g, '');
        var compactCode = dialCode.replace(/\s/g, '');
        var digitsCode = compactCode.replace(/^\+/, '');
        if (compactValue.indexOf(compactCode) === 0) {
          return value.slice(dialCode.length).trim().replace(/^[\s\-()]+/, '');
        }
        if (digitsCode && compactValue.indexOf(digitsCode) === 0 && value.indexOf(digitsCode) === 0) {
          var nextChar = value.charAt(digitsCode.length);
          if (nextChar && /\D/.test(nextChar)) {
            return value.slice(digitsCode.length).trim().replace(/^[\s\-()]+/, '');
          }
        }
        return value;
      }

      function stripNationalPrefixFromInput(rawValue) {
        var selectedMeta = metaForCountryId(countrySelect.value);
        var value = String(rawValue || '').trim();
        if (!selectedMeta || String(selectedMeta.iso2 || '').toLowerCase() !== 'ru' || !value) {
          return value;
        }
        var digits = value.replace(/\D/g, '');
        if (digits.length === 11 && (digits.charAt(0) === '7' || digits.charAt(0) === '8')) {
          digits = digits.slice(1);
        }
        return digits;
      }

      function formatRuLocalNumber(rawValue) {
        var digits = stripNationalPrefixFromInput(stripCountryCodeFromInput(rawValue));
        if (digits.length > 10) {
          digits = digits.slice(-10);
        }
        if (digits.length <= 3) {
          return '(' + digits;
        }
        if (digits.length <= 6) {
          return '(' + digits.slice(0, 3) + ') ' + digits.slice(3);
        }
        if (digits.length <= 8) {
          return '(' + digits.slice(0, 3) + ') ' + digits.slice(3, 6) + '-' + digits.slice(6);
        }
        return '(' + digits.slice(0, 3) + ') ' + digits.slice(3, 6) + '-' + digits.slice(6, 8) + '-' + digits.slice(8, 10);
      }

      function clearRegionField() {
        if (regionInput) {
          regionInput.value = '';
        }
      }

      function clearRuLandlineShapeHint() {
        ruLandlineShapeHint = null;
      }

      function baseLandlineValue(rawValue) {
        return isRussianLandline()
          ? stripNationalPrefixFromInput(stripCountryCodeFromInput(rawValue))
          : stripCountryCodeFromInput(rawValue);
      }

      function formatRuSubscriberDigits(subscriberDigits, subscriberLength) {
        var digits = String(subscriberDigits || '').replace(/\D/g, '').slice(0, subscriberLength);
        if (!digits) return '';
        var groups = {
          7: [3, 2, 2],
          6: [2, 2, 2],
          5: [1, 2, 2],
        };
        var pattern = groups[subscriberLength];
        if (!pattern) return digits;
        var parts = [];
        var cursor = 0;
        pattern.forEach(function (size) {
          var chunk = digits.slice(cursor, cursor + size);
          if (!chunk) return;
          parts.push(chunk);
          cursor += size;
        });
        return parts.join('-');
      }

      function formatRuLandlineByShape(digits, areaCodeLength, subscriberLength) {
        var normalized = String(digits || '').replace(/\D/g, '').slice(0, 10);
        if (!normalized) return '';
        var codeLen = Math.max(1, Math.min(Number(areaCodeLength) || 3, Math.min(5, normalized.length)));
        var expectedSubscriber = Math.max(1, Number(subscriberLength) || Math.max(1, 10 - codeLen));
        var areaCode = normalized.slice(0, codeLen);
        var subscriberDigits = normalized.slice(codeLen, codeLen + expectedSubscriber);
        if (normalized.length <= codeLen) {
          return '(' + areaCode;
        }
        return ('(' + areaCode + ') ' + formatRuSubscriberDigits(subscriberDigits, expectedSubscriber)).trim();
      }

      function optimisticRuLandlineShape(digits) {
        var normalized = String(digits || '').replace(/\D/g, '').slice(0, 10);
        if (!normalized) return { areaCodeLength: 3, subscriberLength: 7 };
        if (ruLandlineShapeHint) {
          var hintDigits = String(ruLandlineShapeHint.digits || '');
          var hintAreaCode = String(ruLandlineShapeHint.areaCode || '');
          if (
            !hintDigits ||
            normalized.indexOf(hintDigits) === 0 ||
            hintDigits.indexOf(normalized) === 0 ||
            (hintAreaCode && normalized.indexOf(hintAreaCode) === 0)
          ) {
            return {
              areaCodeLength: ruLandlineShapeHint.areaCodeLength || 3,
              subscriberLength: ruLandlineShapeHint.subscriberLength || Math.max(1, 10 - (ruLandlineShapeHint.areaCodeLength || 3)),
            };
          }
        }
        if (normalized.length <= 5) {
          return {
            areaCodeLength: normalized.length,
            subscriberLength: Math.max(1, 10 - normalized.length),
          };
        }
        return { areaCodeLength: 3, subscriberLength: 7 };
      }

      function formatRuLandlineOptimistically(rawValue) {
        var normalized = baseLandlineValue(rawValue);
        var shape = optimisticRuLandlineShape(normalized);
        return formatRuLandlineByShape(normalized, shape.areaCodeLength, shape.subscriberLength);
      }

      function seedRuLandlineShapeHintFromCurrentValue() {
        if (!isRussianLandline()) return;
        var rawValue = String(phoneInput.value || '').trim();
        var normalized = baseLandlineValue(rawValue);
        if (!normalized) return;
        var match = rawValue.match(/^\((\d{3,5})\)/);
        if (!match) return;
        var areaCode = match[1];
        ruLandlineShapeHint = {
          digits: normalized,
          areaCode: areaCode,
          areaCodeLength: areaCode.length,
          subscriberLength: Math.max(1, 10 - areaCode.length),
        };
      }

      async function fetchRuLandlineLookup(rawValue) {
        if (!lookupUrl) return { result: null, stale: false };
        var requestToken = ++landlineLookupToken;
        var response = await fetch(lookupUrl + '?phone_number=' + encodeURIComponent(rawValue), {
          method: 'GET',
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        }).catch(function () {
          return null;
        });
        if (requestToken !== landlineLookupToken) {
          return { result: null, stale: true };
        }
        if (!response || !response.ok) {
          return { result: null, stale: false };
        }
        return response.json().then(function (payload) {
          return { result: payload, stale: false };
        }).catch(function () {
          return { result: null, stale: false };
        });
      }

      async function syncRuRegistryLookup(rawValue, options) {
        var config = options || {};
        var normalized = baseLandlineValue(rawValue);
        if (!normalized) {
          cancelPendingRuLookup();
          clearRuLandlineShapeHint();
          clearRegionField();
          phoneInput.value = '';
          fallbackSyncCodeFromCountry();
          return;
        }
        var lookupResponse = await fetchRuLandlineLookup(normalized);
        if (lookupResponse && lookupResponse.stale) {
          return;
        }
        var result = lookupResponse ? lookupResponse.result : null;
        if (!result) {
          if (config.applyFormattedNumber) {
            phoneInput.value = formatRuLandlineOptimistically(normalized);
          }
          clearRegionField();
          fallbackSyncCodeFromCountry();
          return;
        }
        if (result.area_code && result.subscriber_length) {
          ruLandlineShapeHint = {
            digits: result.digits || normalized,
            areaCode: result.area_code,
            areaCodeLength: String(result.area_code).length,
            subscriberLength: Number(result.subscriber_length) || Math.max(1, 10 - String(result.area_code).length),
          };
        }
        if (config.applyFormattedNumber && result.formatted_number) {
          phoneInput.value = result.formatted_number;
        } else if (!config.applyFormattedNumber) {
          // keep the current input formatting for RU mobile numbers
        } else {
          phoneInput.value = formatRuLandlineOptimistically(result.digits || normalized);
        }
        if (config.applyFormattedNumber && document.activeElement === phoneInput && typeof phoneInput.setSelectionRange === 'function') {
          var caret = phoneInput.value.length;
          phoneInput.setSelectionRange(caret, caret);
        }
        if (result.unique && result.region) {
          if (regionInput) {
            regionInput.value = result.region || '';
          }
        } else {
          clearRegionField();
        }
        fallbackSyncCodeFromCountry();
      }

      async function normalizePhoneValue() {
        cancelScheduledRuRegionLookup();
        var rawValue = String(phoneInput.value || '').trim();
        if (!rawValue) {
          cancelPendingRuLookup();
          clearRuLandlineShapeHint();
          clearRegionField();
          fallbackSyncCodeFromCountry();
          return;
        }

        rawValue = stripCountryCodeFromInput(rawValue);
        if (isLandline()) {
          if (isRussianLandline()) {
            await syncRuRegistryLookup(rawValue, { applyFormattedNumber: true });
          } else {
            cancelPendingRuLookup();
            clearRuLandlineShapeHint();
            phoneInput.value = rawValue;
            clearRegionField();
            fallbackSyncCodeFromCountry();
          }
          return;
        }
        rawValue = stripNationalPrefixFromInput(rawValue);

        var formatted = formatNumberAsYouType(rawValue);
        if (formatted && formatted !== phoneInput.value) {
          phoneInput.value = formatted;
        }

        if (phoneIti) {
          try {
            phoneIti.setNumber(rawValue);
            var selectedCountry = phoneIti.getSelectedCountryData();
            if (selectedCountry && selectedCountry.iso2) {
              syncCountrySelectByIso2(selectedCountry.iso2);
            }
          } catch (error) {
          }
        }

        if (isRussianRegistryPhone()) {
          await syncRuRegistryLookup(rawValue, { applyFormattedNumber: false });
        } else {
          cancelPendingRuLookup();
          clearRuLandlineShapeHint();
          clearRegionField();
        }
        fallbackSyncCodeFromCountry();
      }

      function formatPhoneValueWhileTyping(event) {
        if (event && form.__lastTelPhoneInputTs === event.timeStamp) return;
        if (event) {
          form.__lastTelPhoneInputTs = event.timeStamp;
        }
        if (phoneFormattingInProgress) return;
        if (isLandline()) {
          var landlineRawValue = String(phoneInput.value || '');
          var landlineDigits = baseLandlineValue(landlineRawValue);
          if (!landlineDigits.trim()) {
            cancelScheduledRuRegionLookup();
            cancelPendingRuLookup();
            clearRuLandlineShapeHint();
            clearRegionField();
            phoneInput.value = '';
            fallbackSyncCodeFromCountry();
            return;
          }
          if (isRussianLandline()) {
            clearRegionField();
            var optimisticFormatted = formatRuLandlineOptimistically(landlineRawValue);
            if (optimisticFormatted && optimisticFormatted !== phoneInput.value) {
              phoneInput.value = optimisticFormatted;
              if (document.activeElement === phoneInput && typeof phoneInput.setSelectionRange === 'function') {
                var optimisticCaret = optimisticFormatted.length;
                phoneInput.setSelectionRange(optimisticCaret, optimisticCaret);
              }
            }
            scheduleRuRegionLookup();
          } else {
            cancelScheduledRuRegionLookup();
            cancelPendingRuLookup();
            clearRuLandlineShapeHint();
            clearRegionField();
          }
          fallbackSyncCodeFromCountry();
          return;
        }
        var rawValue = stripNationalPrefixFromInput(stripCountryCodeFromInput(String(phoneInput.value || '')));
        if (!rawValue.trim()) {
          cancelScheduledRuRegionLookup();
          cancelPendingRuLookup();
          clearRuLandlineShapeHint();
          clearRegionField();
          phoneInput.value = '';
          fallbackSyncCodeFromCountry();
          return;
        }

        try {
          phoneFormattingInProgress = true;
          var start = phoneInput.selectionStart || rawValue.length;
          var formattedPrefix = formatNumberAsYouType(rawValue.slice(0, start));
          var formattedValue = formatNumberAsYouType(rawValue);
          if (formattedValue) {
            phoneInput.value = formattedValue;
            var nextCaret = formattedPrefix ? formattedPrefix.length : formattedValue.length;
            phoneInput.setSelectionRange(nextCaret, nextCaret);
          }
        } catch (error) {
        } finally {
          phoneFormattingInProgress = false;
        }

        if (isRussianRegistryPhone()) {
          cancelScheduledRuRegionLookup();
          syncRuRegistryLookup(rawValue, { applyFormattedNumber: false });
        } else {
          cancelScheduledRuRegionLookup();
          cancelPendingRuLookup();
          clearRuLandlineShapeHint();
          clearRegionField();
        }
        fallbackSyncCodeFromCountry();
      }

      countrySelect.addEventListener('change', function () {
        cancelScheduledRuRegionLookup();
        cancelPendingRuLookup();
        clearRuLandlineShapeHint();
        syncPhoneTypeUi();
        syncWidgetsFromCountry();
        clearRegionField();
        normalizePhoneValue();
      });
      typeSelect.addEventListener('change', function () {
        cancelScheduledRuRegionLookup();
        cancelPendingRuLookup();
        clearRuLandlineShapeHint();
        syncPhoneTypeUi();
        clearRegionField();
        fallbackSyncCodeFromCountry();
        normalizePhoneValue();
      });

      phoneInput.addEventListener('blur', function () {
        cancelScheduledRuRegionLookup();
        normalizePhoneValue();
      });
      phoneInput.addEventListener('input', formatPhoneValueWhileTyping);
      form.__telPhoneHandleInput = formatPhoneValueWhileTyping;
      form.__telPhoneNormalize = normalizePhoneValue;
      form.addEventListener('submit', function () {
        if (!shouldShowRegionField()) {
          clearRegionField();
        }
        fallbackSyncCodeFromCountry();
      });

      if (window.intlTelInput) {
        try {
          var loadUtils = function () {
            return import('https://cdn.jsdelivr.net/npm/intl-tel-input@26.3.1/dist/js/utils.js');
          };

          codeIti = window.intlTelInput(codeInput, {
            allowDropdown: true,
            autoPlaceholder: 'off',
            formatAsYouType: false,
            loadUtils: loadUtils,
            nationalMode: false,
            strictMode: false,
            useFullscreenPopup: false,
          });

          phoneIti = window.intlTelInput(phoneInput, {
            allowDropdown: false,
            autoPlaceholder: 'polite',
            loadUtils: loadUtils,
            nationalMode: true,
            strictMode: false,
            useFullscreenPopup: false,
          });

          codeInput.addEventListener('countrychange', function () {
            var selectedCountry = codeIti.getSelectedCountryData();
            if (selectedCountry && selectedCountry.iso2) {
              syncCountrySelectByIso2(selectedCountry.iso2);
              clearRuLandlineShapeHint();
              syncPhoneTypeUi();
              syncWidgetsFromCountry();
              normalizePhoneValue();
            }
          });
        } catch (error) {
          codeIti = null;
          phoneIti = null;
        }
      }

      syncPhoneTypeUi();
      syncWidgetsFromCountry();
      seedRuLandlineShapeHintFromCurrentValue();
      fallbackSyncCodeFromCountry();
    });
  }

  document.addEventListener('change', function (event) {
    var countrySelect = event.target && event.target.closest ? event.target.closest('form[data-tel-phone-form="1"] #tel-country-select') : null;
    if (!countrySelect) return;
    var form = countrySelect.closest('form[data-tel-phone-form="1"]');
    if (!form) return;
    initTelPhoneForms(form);

    var codeInput = form.querySelector('#tel-code-field');
    var typeSelect = form.querySelector('#tel-type-select');
    var phoneInput = form.querySelector('#tel-phone-field');
    var flagBadge = form.querySelector('#tel-flag-badge');
    var countryMeta = parseTelCountryMeta(form);
    var selectedMeta = countryMeta[String(countrySelect.value)] || null;
    var phoneType = String(typeSelect && typeSelect.value ? typeSelect.value : 'mobile');

    if (codeInput) {
      codeInput.value = selectedMeta && selectedMeta.dialCode ? selectedMeta.dialCode : '';
    }
    if (phoneInput) {
      phoneInput.placeholder = selectedMeta ? (phoneType === 'landline' ? (selectedMeta.landlinePlaceholder || '') : (selectedMeta.mobilePlaceholder || '')) : '';
    }
    if (flagBadge) {
      flagBadge.textContent = selectedMeta && selectedMeta.flag ? selectedMeta.flag : '--';
    }
  });

  document.addEventListener('change', function (event) {
    var typeSelect = event.target && event.target.closest ? event.target.closest('form[data-tel-phone-form="1"] #tel-type-select') : null;
    if (!typeSelect) return;
    var form = typeSelect.closest('form[data-tel-phone-form="1"]');
    if (!form) return;
    initTelPhoneForms(form);
  });

  document.addEventListener('input', function (event) {
    var phoneInput = event.target && event.target.closest ? event.target.closest('form[data-tel-phone-form="1"] #tel-phone-field') : null;
    if (!phoneInput) return;
    var form = phoneInput.closest('form[data-tel-phone-form="1"]');
    if (!form) return;
    initTelPhoneForms(form);
    if (typeof form.__telPhoneHandleInput === 'function') {
      form.__telPhoneHandleInput(event);
    }
  });

  function openModalContent(url, targetSelector) {
    var target = document.querySelector(targetSelector);
    if (!url || !target) return Promise.resolve();
    return fetch(url, {
      method: 'GET',
      credentials: 'same-origin',
      headers: { 'HX-Request': 'true' },
    }).then(async function (response) {
      if (!response.ok) {
        var text = await response.text();
        window.alert(text || 'Операцию не удалось выполнить.');
        return;
      }
      target.innerHTML = await response.text();
      if (window.htmx && typeof window.htmx.process === 'function') {
        window.htmx.process(target);
      }
      activateInlineScripts(target);
      initPositionForms(target);
      initTelPhoneForms(target);
      var modalEl = target.closest('.modal');
      if (modalEl && window.bootstrap) {
        window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
      }
    });
  }

  function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      var cookies = document.cookie.split(';');
      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function switchSection(key) {
    window.__currentContactsSection = key;
    document.querySelectorAll('#contacts .contacts-section-content').forEach(function (node) {
      node.classList.add('d-none');
    });
    var target = document.getElementById('cnt-content-' + key);
    if (target) target.classList.remove('d-none');
    var title = document.getElementById('contacts-section-title');
    if (title) title.textContent = SECTION_TITLES[key] || 'База контактов';
    var tableName = SECTION_TABLE_MAP[key];
    if (tableName && getExplicitContactsPersonFilterValues().length) {
      refreshTable(tableName).catch(function () {});
      return;
    }
    if (key === 'persons') {
      document.body.dispatchEvent(new CustomEvent('contacts-persons:load'));
    }
    if (key === 'citizenships') {
      document.body.dispatchEvent(new CustomEvent('contacts-citizenships:load'));
    }
    if (key === 'positions') {
      document.body.dispatchEvent(new CustomEvent('contacts-positions:load'));
    }
    if (key === 'phones') {
      document.body.dispatchEvent(new CustomEvent('contacts-phones:load'));
    }
    if (key === 'emails') {
      document.body.dispatchEvent(new CustomEvent('contacts-emails:load'));
    }
  }

  function activateSectionLink(key) {
    var sidebar = document.getElementById('contacts-second-sidebar-list');
    if (!sidebar) return;
    sidebar.querySelectorAll('.list-group-item').forEach(function (link) {
      link.classList.remove('active');
    });
    var activeLink = sidebar.querySelector('[data-contacts-section="' + key + '"]');
    if (activeLink) activeLink.classList.add('active');
  }

  document.addEventListener('DOMContentLoaded', function () {
    initContactsPersonMasterFilter(false).catch(function () {});
    syncContactsModalSize(document);
    initPositionForms(document);
    initTelPhoneForms(document);
    var sidebar = document.getElementById('contacts-second-sidebar-list');
    if (sidebar && !sidebar.dataset.bound) {
      sidebar.dataset.bound = '1';
      sidebar.addEventListener('click', function (event) {
        var link = event.target.closest('.list-group-item');
        if (!link) return;
        event.preventDefault();
        var key = link.dataset.contactsSection || 'persons';
        activateSectionLink(key);
        switchSection(key);
        if (window.UIPref) window.UIPref.set('contacts:section', key);
      });
    }

    var saved = window.UIPref ? window.UIPref.get('contacts:section', null) : null;
    var initial = saved && SECTION_TABLE_MAP[saved] ? saved : 'persons';
    activateSectionLink(initial);
    switchSection(initial);
    if (getExplicitContactsPersonFilterValues().length) {
      resetContactsRegistryPages();
      refreshTables(CONTACTS_FILTER_TABLES).catch(function () {});
    }
  });

  document.addEventListener('change', function (event) {
    var master = event.target.closest('input.form-check-input[data-actions-id][data-target-name]');
    if (!master || !inContacts(master)) return;
    var name = master.dataset.targetName;
    getRowChecksByName(name).forEach(function (checkbox) { checkbox.checked = master.checked; });
    master.indeterminate = false;
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
  });

  document.addEventListener('change', function (event) {
    var rowCheckbox = event.target.closest('tbody input.form-check-input[name]');
    if (!rowCheckbox || !inContacts(rowCheckbox)) return;
    var name = rowCheckbox.name;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
  });

  document.addEventListener('click', function (event) {
    var button = event.target.closest('button[data-panel-action]');
    if (!button || !inContacts(button)) return;
    var panel = button.closest('#prs-actions, #ctz-actions, #psn-actions, #tel-actions, #eml-actions');
    if (!panel) return;
    var master = paneOf(panel) && paneOf(panel).querySelector('input.form-check-input[data-actions-id]');
    var name = (master && master.dataset ? master.dataset.targetName : '') || PANEL_NAME_MAP[panel.id] || '';
    if (!name) return;
    var checked = getCheckedByName(name);
    if (!checked.length) return;
    var action = button.dataset.panelAction;

    if (action === 'edit') {
      var editUrl = checked[0].closest('tr') && checked[0].closest('tr').dataset ? checked[0].closest('tr').dataset.editUrl : '';
      if (!editUrl) return;
      openModalContent(editUrl, '#contacts-modal .modal-content');
      return;
    }

    if (action === 'delete') {
      if (!window.confirm('Удалить ' + checked.length + ' строк(у/и)?')) return;
      var deleteUrls = checked.map(function (item) {
        var row = item.closest('tr');
        return row && row.dataset ? row.dataset.deleteUrl : '';
      }).filter(Boolean);
      Promise.resolve().then(async function () {
        for (var i = 0; i < deleteUrls.length; i++) {
          var response = await fetch(deleteUrls[i], {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken'), 'HX-Request': 'true' },
          });
          if (!response.ok) {
            var text = await response.text();
            window.alert(text || 'Операцию не удалось выполнить.');
            break;
          }
        }
        await refreshTable(name);
        if (name === 'prs-select') await refreshTable('ctz-select');
        if (name === 'prs-select') await refreshTable('psn-select');
        if (name === 'prs-select') await refreshTable('tel-select');
        if (name === 'prs-select') await refreshTable('eml-select');
      });
      return;
    }

    if (action === 'up' || action === 'down') {
      rememberSelection(name);
      var urls = checked.map(function (item) {
        var row = item.closest('tr');
        if (!row || !row.dataset) return '';
        return action === 'up' ? row.dataset.moveUpUrl : row.dataset.moveDownUrl;
      }).filter(Boolean);
      if (action === 'down') urls.reverse();
      Promise.resolve().then(async function () {
        for (var i = 0; i < urls.length; i++) {
          await fetch(urls[i], {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken'), 'HX-Request': 'true' },
          });
        }
        await refreshTable(name);
        restoreSelection(name);
      });
    }
  });

  document.body.addEventListener('contacts-updated', function (event) {
    var detail = event.detail || {};
    refreshTables(detail.affected || []).catch(function () {});
  });

  document.body.addEventListener('htmx:configRequest', function (event) {
    var detail = event && event.detail ? event.detail : null;
    var target = detail && detail.target;
    if (!target || !(target instanceof Element)) return;
    if (!target.matches('#contacts-persons-table-wrap, #contacts-citizenships-table-wrap, #contacts-positions-table-wrap, #contacts-phones-table-wrap, #contacts-emails-table-wrap')) {
      return;
    }
    var values = getSelectedContactsPersonFilterValues();
    if (!values.length || values.includes(CONTACTS_PERSON_FILTER_ALL)) {
      if (detail.parameters) delete detail.parameters.prs_ids;
      return;
    }
    if (detail.parameters) {
      detail.parameters.prs_ids = values.join(',');
    }
  });

  document.body.addEventListener('htmx:configRequest', function (event) {
    var detail = event && event.detail ? event.detail : null;
    var target = detail && detail.target;
    var path = detail && detail.path ? String(detail.path) : '';
    if (!target || !(target instanceof Element)) return;
    if (!target.matches('#contacts-modal .modal-content')) return;
    if (!/\/contacts\/(ctz|psn|tel|eml)\/create\/$/.test(path)) return;
    var values = getSelectedContactsPersonFilterValues();
    if (!values.length || values.includes(CONTACTS_PERSON_FILTER_ALL)) {
      if (detail.parameters) delete detail.parameters.prs_ids;
      return;
    }
    if (detail.parameters) {
      detail.parameters.prs_ids = values.join(',');
    }
  });

  document.body.addEventListener('shown.bs.tab', function (event) {
    var trigger = event.target;
    if (!trigger || trigger.getAttribute('href') !== '#contacts') return;
    initContactsPersonMasterFilter(false).catch(function () {});
    var section = window.__currentContactsSection || 'persons';
    var tableName = SECTION_TABLE_MAP[section];
    if (tableName) refreshTable(tableName).catch(function () {});
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    if (!event || !event.target || !(event.target instanceof Element)) return;
    syncContactsModalSize(event.target);
    initPositionForms(event.target);
    initTelPhoneForms(event.target);
  });
})();
