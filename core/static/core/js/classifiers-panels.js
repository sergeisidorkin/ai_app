(function () {
  if (window.__classifiersPanelBound) return;
  window.__classifiersPanelBound = true;

  window.__clTableSel = window.__clTableSel || {};
  window.__clTableSelLast = window.__clTableSelLast || null;

  const TABLE_CONFIG = {
    'ber-select': { target: '#business-entities-table-wrap', swap: 'innerHTML', url: '/classifiers/ber/table/', settleId: 'business-entities-table-wrap' },
    'bei-select': { target: '#business-entity-identifiers-table-wrap', swap: 'innerHTML', url: '/classifiers/bei/table/', settleId: 'business-entity-identifiers-table-wrap' },
    'bat-select': { target: '#business-entity-attributes-table-wrap', swap: 'innerHTML', url: '/classifiers/bat/table/', settleId: 'business-entity-attributes-table-wrap' },
    'bea-select': { target: '#business-entity-addresses-table-wrap', swap: 'innerHTML', url: '/classifiers/bea/table/', settleId: 'business-entity-addresses-table-wrap' },
    'brl-select': { target: '#business-entity-relations-table-wrap', swap: 'innerHTML', url: '/classifiers/brl/table/', settleId: 'business-entity-relations-table-wrap' },
    'oksm-select': { target: '#oksm-table-wrap', swap: 'innerHTML', url: '/classifiers/oksm/table/', settleId: 'oksm-table-wrap' },
    'okv-select': { target: '#okv-table-wrap', swap: 'innerHTML', url: '/classifiers/okv/table/', settleId: 'okv-table-wrap' },
    'lei-select': { target: '#lei-table-wrap', swap: 'innerHTML', url: '/classifiers/lei/table/', settleId: 'lei-table-wrap' },
    'pei-select': { target: '#pei-table-wrap', swap: 'innerHTML', url: '/classifiers/pei/table/', settleId: 'pei-table-wrap' },
    'numcap-select': { target: '#numcap-table-wrap', swap: 'innerHTML', url: '/classifiers/numcap/table/', settleId: 'numcap-table-wrap' },
    'katd-select': { target: '#katd-table-wrap', swap: 'innerHTML', url: '/classifiers/katd/table/', settleId: 'katd-table-wrap' },
    'rfs-select': { target: '#rfs-table-wrap', swap: 'innerHTML', url: '/classifiers/rfs/table/', settleId: 'rfs-table-wrap' },
    'lw-select': { target: '#lw-table-wrap', swap: 'innerHTML', url: '/classifiers/lw/table/', settleId: 'lw-table-wrap' },
    'ler-select': { target: '#ler-table-wrap', swap: 'innerHTML', url: '/classifiers/ler/table/', settleId: 'ler-table-wrap' },
  };
  const BUSINESS_REGISTRY_TABLES = [
    'ber-select',
    'bei-select',
    'bat-select',
    'ler-select',
    'bea-select',
    'brl-select',
  ];
  const BUSINESS_REGISTRY_MANUAL_REFRESH = {
    'ber-select': {
      delete: ['bei-select', 'ler-select', 'bea-select', 'brl-select'],
      up: [],
      down: [],
    },
    'bei-select': {
      delete: ['ler-select', 'bea-select'],
      up: [],
      down: [],
    },
    'bat-select': {
      delete: [],
      up: [],
      down: [],
    },
    'ler-select': {
      delete: [],
      up: [],
      down: [],
    },
    'bea-select': {
      delete: [],
      up: [],
      down: [],
    },
    'brl-select': {
      delete: [],
      up: [],
      down: [],
    },
  };

  const PANE_SELECTOR = '#classifiers-pane, #normatives-pane, #legal-entities-pane, #business-entities-pane, #business-entity-identifiers-pane, #business-entity-attributes-pane, #business-entity-addresses-pane, #business-entity-relations-pane';
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
  const WRAP_PREF_KEY_PREFIX = 'classifiers:wrap:';
  const SECTION_PREF_KEY_PREFIX = 'classifiers:section:';
  const BUSINESS_ENTITY_FILTER_ALL = '__all__';
  const BUSINESS_ENTITY_FILTER_PREF_KEY = 'classifiers:business-entity-filter';
  const BUSINESS_ENTITY_FILTER_OPTIONS_URL = '/classifiers/ber/filter-options/';
  const BUSINESS_REGISTRY_SECTION_SELECTOR = [
    '#clf-content-business-entities',
    '#clf-content-business-entity-identifiers',
    '#clf-content-business-entity-attributes',
    '#clf-content-legal-entities',
    '#clf-content-business-entity-addresses',
    '#clf-content-business-entity-relations',
  ].join(', ');
  window.__classifiersBusinessEntityFilter = window.__classifiersBusinessEntityFilter || (
    window.UIPref ? UIPref.get(BUSINESS_ENTITY_FILTER_PREF_KEY, [BUSINESS_ENTITY_FILTER_ALL]) : [BUSINESS_ENTITY_FILTER_ALL]
  );

  function getWrapPref(toggleId, defaultValue) {
    try {
      const raw = window.localStorage.getItem(WRAP_PREF_KEY_PREFIX + toggleId);
      if (raw === null) return defaultValue;
      return raw === '1';
    } catch (e) {
      return defaultValue;
    }
  }

  function setWrapPref(toggleId, active) {
    try {
      window.localStorage.setItem(WRAP_PREF_KEY_PREFIX + toggleId, active ? '1' : '0');
    } catch (e) {}
  }

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
    'rfs-wrap-toggle':  { wrap: 'rfs-table-wrap',  cellClass: 'rfs-source-cell' },
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

  function applyWrapState(toggleId, active) {
    const cfg = CLF_WRAP_CFG[toggleId];
    if (!cfg) return;
    const toggle = document.getElementById(toggleId);
    const wrap = document.getElementById(cfg.wrap);
    const table = wrap?.querySelector('table');
    if (!toggle || !table) return;

    table.classList.toggle('clf-truncated', active);
    toggle.classList.toggle('active', active);

    wrap.querySelectorAll('td.' + cfg.cellClass).forEach(td => {
      if (active) td.setAttribute('title', td.textContent.trim());
      else td.removeAttribute('title');
    });
  }

  function initClassifierWrapToggles() {
    Object.keys(CLF_WRAP_CFG).forEach(toggleId => {
      applyWrapState(toggleId, getWrapPref(toggleId, true));
    });
  }

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
    setWrapPref(toggle.id, active);

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

  function bindClassifiersFilterMenuWidth(dropdown) {
    if (!dropdown) return;
    if (window.bindProjectFilterMenuWidth) {
      window.bindProjectFilterMenuWidth(dropdown);
      return;
    }
    if (dropdown.dataset.projectMenuWidthBound === '1') return;
    dropdown.dataset.projectMenuWidthBound = '1';
    const menu = dropdown.querySelector('.project-filter-menu');
    if (!menu) return;
    dropdown.addEventListener('shown.bs.dropdown', function () {
      const labels = Array.from(menu.querySelectorAll('.form-check-label'));
      const widestLabel = labels.reduce(function (maxWidth, item) {
        return Math.max(maxWidth, Math.ceil(item.scrollWidth));
      }, 0);
      if (!widestLabel) return;
      const controlWidth = Math.ceil(dropdown.querySelector('.dropdown-toggle')?.offsetWidth || 200);
      const checkboxWidth = Math.ceil(menu.querySelector('.form-check-input')?.offsetWidth || 18);
      const contentWidth = widestLabel + checkboxWidth + 64;
      menu.style.minWidth = Math.max(controlWidth, 200, contentWidth) + 'px';
    });
  }

  function getSelectedBusinessEntityFilterValues() {
    const values = Array.isArray(window.__classifiersBusinessEntityFilter)
      ? window.__classifiersBusinessEntityFilter.filter(Boolean).map(String)
      : [];
    return values.length ? values : [BUSINESS_ENTITY_FILTER_ALL];
  }

  function getExplicitBusinessEntityFilterValues(values) {
    return (Array.isArray(values) ? values : getSelectedBusinessEntityFilterValues())
      .filter(Boolean)
      .map(String)
      .filter(function (value) { return value !== BUSINESS_ENTITY_FILTER_ALL; });
  }

  function setSelectedBusinessEntityFilterValues(values) {
    const explicitValues = getExplicitBusinessEntityFilterValues(values);
    const nextValues = explicitValues.length ? explicitValues : [BUSINESS_ENTITY_FILTER_ALL];
    window.__classifiersBusinessEntityFilter = nextValues;
    if (window.UIPref) UIPref.set(BUSINESS_ENTITY_FILTER_PREF_KEY, nextValues);
  }

  function resetBusinessRegistryPages() {
    ['ber-page-input', 'bei-page-input', 'ler-page-input', 'bea-page-input', 'brl-page-input'].forEach(function (id) {
      var input = document.getElementById(id);
      if (input) input.value = '1';
    });
  }

  function appendBusinessEntityFilter(parts) {
    const values = getSelectedBusinessEntityFilterValues();
    if (!values.length || values.includes(BUSINESS_ENTITY_FILTER_ALL)) return;
    parts.push('business_entity_ids=' + encodeURIComponent(values.join(',')));
  }

  function appendBusinessEntityFilterParameters(params) {
    const values = getSelectedBusinessEntityFilterValues();
    if (!values.length || values.includes(BUSINESS_ENTITY_FILTER_ALL)) return;
    params.business_entity_ids = values.join(',');
  }

  async function initBusinessEntityMasterFilter(forceReload) {
    const dropdown = document.getElementById('master-classifiers-bsn-filter-dropdown');
    const toggle = document.getElementById('classifiers-bsn-filter-toggle');
    const menu = dropdown?.querySelector('.classifiers-bsn-filter-menu');
    const selectedContainer = document.getElementById('classifiers-bsn-filter-selected');
    const searchInput = document.getElementById('classifiers-bsn-filter-search');
    const searchList = document.getElementById('classifiers-bsn-filter-search-list');
    const clearButton = document.getElementById('classifiers-bsn-filter-clear');
    const applyButton = document.getElementById('classifiers-bsn-filter-apply');
    const hintNode = document.getElementById('classifiers-bsn-filter-hint');
    const labelNode = document.querySelector('.js-classifiers-bsn-filter-label');
    if (!dropdown || !toggle || !menu || !selectedContainer || !searchInput || !searchList || !clearButton || !applyButton) return;

    bindClassifiersFilterMenuWidth(dropdown);

    const state = dropdown.__bsnFilterState || {
      cache: {},
      draftValues: [],
      searchResults: [],
      searchTotalCount: 0,
      searchDebounce: null,
      picking: false,
    };
    dropdown.__bsnFilterState = state;

    function hideSearchResults() {
      searchList.classList.remove('show');
      searchList.innerHTML = '';
      state.searchResults = [];
      state.searchTotalCount = 0;
      updateMenuWidth();
    }

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

    function updateLabel(values) {
      if (!labelNode) return;
      const explicitValues = getExplicitBusinessEntityFilterValues(values);
      if (!explicitValues.length) {
        labelNode.textContent = 'Все';
        return;
      }
      if (explicitValues.length === 1) {
        const item = state.cache[explicitValues[0]];
        labelNode.textContent = (item && (item.summary_label || item.formatted_id)) || '1 выбрано';
        return;
      }
      labelNode.textContent = explicitValues.length + ' выбрано';
    }

    function updateMenuWidth() {
      const viewportMax = Math.max(320, window.innerWidth - 32);
      const toggleWidth = Math.ceil(toggle.offsetWidth || 220);
      let contentWidth = 0;

      [
        selectedContainer,
        searchList,
        hintNode,
        applyButton,
      ].forEach(function (node) {
        if (node) contentWidth = Math.max(contentWidth, Math.ceil(node.scrollWidth || 0));
      });

      menu.querySelectorAll('.form-check, .form-check-label, .ler-ac-item').forEach(function (node) {
        contentWidth = Math.max(contentWidth, Math.ceil(node.scrollWidth || 0));
      });

      contentWidth = Math.max(contentWidth, Math.ceil(searchInput.scrollWidth || 0), 320);
      const width = Math.min(viewportMax, Math.max(toggleWidth, contentWidth + 40));
      menu.style.width = width + 'px';
      menu.style.minWidth = width + 'px';
      searchList.style.width = '100%';
      searchList.style.minWidth = '100%';
    }

    async function fetchFilterItems(params) {
      const url = new URL(BUSINESS_ENTITY_FILTER_OPTIONS_URL, window.location.origin);
      Object.keys(params || {}).forEach(function (key) {
        const value = params[key];
        if (Array.isArray(value)) {
          value.forEach(function (item) {
            if (item !== undefined && item !== null && item !== '') url.searchParams.append(key, item);
          });
        } else if (value !== undefined && value !== null && value !== '') {
          url.searchParams.set(key, value);
        }
      });
      const resp = await fetch(url.toString(), {
        headers: { 'X-Requested-With': 'fetch' },
      });
      return resp.json();
    }

    async function ensureItemDetails(values, forceFetch) {
      const explicitValues = getExplicitBusinessEntityFilterValues(values);
      const missing = explicitValues.filter(function (value) {
        return forceFetch || !state.cache[value];
      });
      if (!missing.length) return;
      try {
        const payload = await fetchFilterItems({ ids: missing });
        const items = Array.isArray(payload.results) ? payload.results : [];
        items.forEach(function (item) {
          state.cache[String(item.id)] = item;
        });
      } catch (e) {}
    }

    function renderSelectedValues() {
      const values = getExplicitBusinessEntityFilterValues(state.draftValues);
      if (!values.length) {
        selectedContainer.innerHTML = '';
        selectedContainer.classList.add('d-none');
        if (hintNode) hintNode.classList.remove('d-none');
        return;
      }
      selectedContainer.classList.remove('d-none');
      if (hintNode) hintNode.classList.add('d-none');
      selectedContainer.innerHTML = values.map(function (value, index) {
        const item = state.cache[value] || { formatted_id: value, label: value };
        const inputId = 'classifiers-bsn-filter-selected-' + value + '-' + index;
        return '<div class="form-check mb-2">'
          + '<input class="form-check-input js-classifiers-bsn-filter-selected" type="checkbox" checked value="' + escapeHtml(value) + '" id="' + escapeHtml(inputId) + '">'
          + '<label class="form-check-label" for="' + escapeHtml(inputId) + '">' + escapeHtml(item.label || item.formatted_id || value) + '</label>'
          + '</div>';
      }).join('');
      updateMenuWidth();
    }

    function renderSearchResults(query) {
      searchList.innerHTML = '';
      if (!state.searchResults.length) {
        hideSearchResults();
        return;
      }
      const visible = state.searchResults.slice(0, 3);
      let html = visible.map(function (item, index) {
        return '<div class="ler-ac-item js-classifiers-bsn-search-item" data-idx="' + index + '">'
          + '<div class="ler-ac-main">' + highlight(item.label || '', query) + '</div>'
          + '</div>';
      }).join('');
      if (state.searchTotalCount > 3) {
        html += '<div class="ler-ac-item ler-ac-more">Найдено еще ' + (state.searchTotalCount - 3) + ' бизнес-сущностей</div>';
      }
      searchList.innerHTML = html;
      searchList.classList.add('show');
      searchList.style.width = '100%';
      searchList.style.minWidth = '100%';
      updateMenuWidth();
    }

    function resetDraftFromApplied() {
      state.draftValues = getExplicitBusinessEntityFilterValues();
      renderSelectedValues();
      hideSearchResults();
      searchInput.value = '';
      updateMenuWidth();
    }

    async function searchItems(query) {
      try {
        const payload = await fetchFilterItems({ q: query });
        const results = Array.isArray(payload.results) ? payload.results : [];
        results.forEach(function (item) {
          state.cache[String(item.id)] = item;
        });
        state.searchResults = results;
        state.searchTotalCount = payload.total_count || results.length;
        renderSearchResults(query);
      } catch (e) {
        hideSearchResults();
      }
    }

    async function applySelection() {
      const nextValues = getExplicitBusinessEntityFilterValues(state.draftValues);
      await ensureItemDetails(nextValues, false);
      setSelectedBusinessEntityFilterValues(nextValues);
      updateLabel(nextValues);
      resetBusinessRegistryPages();
      const currentTableName = getCurrentBusinessRegistryTableName();
      if (currentTableName) {
        await refreshTable(currentTableName);
      }
      if (window.bootstrap && window.bootstrap.Dropdown) {
        window.bootstrap.Dropdown.getOrCreateInstance(toggle).hide();
      }
    }

    await ensureItemDetails(getSelectedBusinessEntityFilterValues(), !!forceReload);
    updateLabel(getSelectedBusinessEntityFilterValues());

    if (dropdown.dataset.bsnFilterLoaded === '1') return;

    searchInput.addEventListener('input', function () {
      const query = (searchInput.value || '').trim();
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
      const query = (searchInput.value || '').trim();
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
      const itemNode = event.target.closest('.js-classifiers-bsn-search-item');
      if (!itemNode) return;
      const idx = parseInt(itemNode.dataset.idx, 10);
      const item = state.searchResults[idx];
      if (!item) return;
      const value = String(item.id);
      if (!state.draftValues.includes(value)) state.draftValues.push(value);
      state.cache[value] = item;
      renderSelectedValues();
      searchInput.value = '';
      hideSearchResults();
    });

    searchList.addEventListener('click', function (event) {
      const itemNode = event.target.closest('.js-classifiers-bsn-search-item');
      if (!itemNode) return;
      event.preventDefault();
      state.picking = false;
    });

    selectedContainer.addEventListener('change', function (event) {
      const checkbox = event.target.closest('.js-classifiers-bsn-filter-selected');
      if (!checkbox) return;
      const value = String(checkbox.value || '');
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
      ensureItemDetails(getSelectedBusinessEntityFilterValues(), false).then(function () {
        resetDraftFromApplied();
        updateMenuWidth();
        window.setTimeout(function () { searchInput.focus(); }, 0);
      });
    });

    dropdown.addEventListener('hide.bs.dropdown', function () {
      resetDraftFromApplied();
    });

    window.addEventListener('resize', updateMenuWidth);

    dropdown.dataset.bsnFilterLoaded = '1';
  }

  function filterQueryString() {
    var parts = [];
    var oksmEl = document.getElementById('oksm-date-filter');
    var okvEl = document.getElementById('okv-date-filter');
    var katdEl = document.getElementById('katd-date-filter');
    var lwEl = document.getElementById('lw-date-filter');
    var beiEl = document.getElementById('bei-date-filter');
    var beiDuplicatesEl = document.getElementById('bei-duplicates-filter-input');
    var beaEl = document.getElementById('bea-date-filter');
    var lerEl = document.getElementById('ler-date-filter');
    var berPageEl = document.getElementById('ber-page-input');
    var beiPageEl = document.getElementById('bei-page-input');
    var lerPageEl = document.getElementById('ler-page-input');
    var beaPageEl = document.getElementById('bea-page-input');
    var brlPageEl = document.getElementById('brl-page-input');
    var numcapQEl = document.getElementById('numcap-q-filter');
    var numcapCodeEl = document.getElementById('numcap-code-filter');
    var numcapRegionEl = document.getElementById('numcap-region-filter');
    var numcapPageEl = document.getElementById('numcap-page-input');
    appendBusinessEntityFilter(parts);
    if (oksmEl) parts.push('oksm_date=' + encodeURIComponent(oksmEl.value));
    if (okvEl) parts.push('okv_date=' + encodeURIComponent(okvEl.value));
    if (katdEl) parts.push('date=' + encodeURIComponent(katdEl.value));
    if (lwEl) parts.push('lw_date=' + encodeURIComponent(lwEl.value));
    if (beiEl) parts.push('bei_date=' + encodeURIComponent(beiEl.value));
    if (beiDuplicatesEl) parts.push('bei_duplicates=' + encodeURIComponent(beiDuplicatesEl.value));
    if (beaEl) parts.push('bea_date=' + encodeURIComponent(beaEl.value));
    if (lerEl) parts.push('ler_date=' + encodeURIComponent(lerEl.value));
    if (numcapQEl && numcapQEl.value) parts.push('numcap_q=' + encodeURIComponent(numcapQEl.value));
    if (numcapCodeEl && numcapCodeEl.value) parts.push('numcap_code=' + encodeURIComponent(numcapCodeEl.value));
    if (numcapRegionEl && numcapRegionEl.value) parts.push('numcap_region=' + encodeURIComponent(numcapRegionEl.value));
    if (berPageEl) parts.push('ber_page=' + encodeURIComponent(berPageEl.value));
    if (beiPageEl) parts.push('bei_page=' + encodeURIComponent(beiPageEl.value));
    if (lerPageEl) parts.push('ler_page=' + encodeURIComponent(lerPageEl.value));
    if (beaPageEl) parts.push('bea_page=' + encodeURIComponent(beaPageEl.value));
    if (brlPageEl) parts.push('brl_page=' + encodeURIComponent(brlPageEl.value));
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

  async function refreshTables(names) {
    const unique = Array.from(new Set((names || []).filter(Boolean)));
    if (!unique.length) return;
    await Promise.all(unique.map(function (name) { return refreshTable(name); }));
  }

  let businessRegistryRefreshInFlight = null;
  let businessRegistryRefreshQueued = false;
  const BUSINESS_REGISTRY_SECTION_TABLE_MAP = {
    'business-entities': 'ber-select',
    'business-entity-identifiers': 'bei-select',
    'business-entity-attributes': 'bat-select',
    'legal-entities': 'ler-select',
    'business-entity-addresses': 'bea-select',
    'business-entity-relations': 'brl-select',
  };

  function getCurrentBusinessRegistryTableName() {
    const explicitSectionKey = window.__currentClassifiersSection;
    if (explicitSectionKey && BUSINESS_REGISTRY_SECTION_TABLE_MAP[explicitSectionKey]) {
      return BUSINESS_REGISTRY_SECTION_TABLE_MAP[explicitSectionKey];
    }
    const currentSection = document.querySelector('#classifiers .clf-section-content:not(.d-none)');
    if (!currentSection || !currentSection.id) return null;
    const sectionKey = currentSection.id.replace(/^clf-content-/, '');
    return BUSINESS_REGISTRY_SECTION_TABLE_MAP[sectionKey] || null;
  }

  async function refreshBusinessRegistryTablesLatest() {
    if (businessRegistryRefreshInFlight) {
      businessRegistryRefreshQueued = true;
      return businessRegistryRefreshInFlight;
    }

    businessRegistryRefreshInFlight = (async function run() {
      do {
        businessRegistryRefreshQueued = false;
        await refreshTables(BUSINESS_REGISTRY_TABLES);
      } while (businessRegistryRefreshQueued);
    })();

    try {
      await businessRegistryRefreshInFlight;
    } finally {
      businessRegistryRefreshInFlight = null;
    }
  }

  function getManualRefreshTargets(sourceName, action) {
    const mapping = BUSINESS_REGISTRY_MANUAL_REFRESH[sourceName];
    if (!mapping) return [];
    return mapping[action] || [];
  }

  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !inAnyPane(btn)) return;
    const panel = btn.closest('#ber-actions, #bei-actions, #bat-actions, #bea-actions, #brl-actions, #oksm-actions, #okv-actions, #lei-actions, #pei-actions, #numcap-actions, #katd-actions, #rfs-actions, #lw-actions, #ler-actions');
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
      let hasSuccessfulMutation = false;
      for (let i = 0; i < urls.length; i++) {
        const resp = await fetch(urlWithFilters(urls[i]), {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken, 'HX-Request': 'true' },
        }).catch(() => {});
        if (!resp) continue;
        if (!resp.ok) {
          let message = 'Операцию не удалось выполнить.';
          try {
            const text = await resp.text();
            if (text && text.trim()) message = text.trim();
          } catch (e) {}
          window.alert(message);
          break;
        }
        hasSuccessfulMutation = true;
      }
      await refreshTable(name);
      if (hasSuccessfulMutation && name === 'ber-select') {
        await initBusinessEntityMasterFilter(true);
      }
      if (hasSuccessfulMutation && BUSINESS_REGISTRY_TABLES.includes(name)) {
        await refreshTables(getManualRefreshTargets(name, 'delete'));
      }
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

  document.body.addEventListener('classifiers-updated', function (e) {
    const detail = e.detail || {};
    const source = detail.source;
    const group = detail.group;
    const affected = Array.isArray(detail.affected) ? detail.affected : [];
    if (group !== 'business-registries' || !BUSINESS_REGISTRY_TABLES.includes(source)) return;
    if (source === 'ber-select') {
      initBusinessEntityMasterFilter(true).catch(function () {});
    }
    refreshTables(affected).catch(function () {});
  });

  document.body.addEventListener('classifiers:section-shown', function (e) {
    const section = e.detail && e.detail.section;
    const tableName = BUSINESS_REGISTRY_SECTION_TABLE_MAP[section];
    if (!tableName) return;
    refreshTable(tableName).catch(function () {});
  });

  document.addEventListener('htmx:configRequest', function(e) {
    var modal = document.getElementById('classifiers-modal');
    var source = e.target;
    var inModal = !!(modal && modal.contains(source));
    var inClassifiersSection = !!(source && source.closest && source.closest('#classifiers'));
    if (!inModal && !inClassifiersSection) return;
    appendBusinessEntityFilterParameters(e.detail.parameters);
    if (!inModal) return;
    var oksmEl = document.getElementById('oksm-date-filter');
    var okvEl = document.getElementById('okv-date-filter');
    var katdEl = document.getElementById('katd-date-filter');
    var lwEl = document.getElementById('lw-date-filter');
    var beiEl = document.getElementById('bei-date-filter');
    var beiDuplicatesEl = document.getElementById('bei-duplicates-filter-input');
    var beaEl = document.getElementById('bea-date-filter');
    var lerEl = document.getElementById('ler-date-filter');
    var berPageEl = document.getElementById('ber-page-input');
    var beiPageEl = document.getElementById('bei-page-input');
    var lerPageEl = document.getElementById('ler-page-input');
    var beaPageEl = document.getElementById('bea-page-input');
    var brlPageEl = document.getElementById('brl-page-input');
    if (oksmEl) e.detail.parameters['oksm_date'] = oksmEl.value;
    if (okvEl) e.detail.parameters['okv_date'] = okvEl.value;
    if (katdEl) e.detail.parameters['date'] = katdEl.value;
    if (lwEl) e.detail.parameters['lw_date'] = lwEl.value;
    if (beiEl) e.detail.parameters['bei_date'] = beiEl.value;
    if (beiDuplicatesEl) e.detail.parameters['bei_duplicates'] = beiDuplicatesEl.value;
    if (beaEl) e.detail.parameters['bea_date'] = beaEl.value;
    if (lerEl) e.detail.parameters['ler_date'] = lerEl.value;
    if (berPageEl) e.detail.parameters['ber_page'] = berPageEl.value;
    if (beiPageEl) e.detail.parameters['bei_page'] = beiPageEl.value;
    if (lerPageEl) e.detail.parameters['ler_page'] = lerPageEl.value;
    if (beaPageEl) e.detail.parameters['bea_page'] = beaPageEl.value;
    if (brlPageEl) e.detail.parameters['brl_page'] = brlPageEl.value;
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

  function buildNonJsonError(resp, text) {
    var plain = (text || '')
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    var titleMatch = (text || '').match(/<title[^>]*>([\s\S]*?)<\/title>/i);
    var details = titleMatch && titleMatch[1] ? titleMatch[1].trim() : plain.slice(0, 220);
    var statusText = [resp.status, resp.statusText].filter(Boolean).join(' ');
    return new Error(details ? ('Сервер вернул ' + statusText + ': ' + details) : ('Сервер вернул ' + statusText));
  }

  async function readJsonResponse(resp) {
    var text = await resp.text();
    var contentType = resp.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      throw buildNonJsonError(resp, text);
    }
    try {
      return JSON.parse(text || '{}');
    } catch (err) {
      throw buildNonJsonError(resp, text);
    }
  }

  async function uploadCsvRequest(uploadUrl, formData) {
    var resp = await fetch(uploadUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrftoken },
      body: formData,
    });
    return readJsonResponse(resp);
  }

  async function handleCsvUpload(uploadUrl, files, refreshName, options) {
    var selectedFiles = Array.isArray(files) ? files : [files];
    var uploadOptions = options || {};
    try {
      var data;
      if (uploadOptions.sequential && selectedFiles.length > 1) {
        data = { ok: true, created: 0, skipped: 0, files: [] };
        for (var idx = 0; idx < selectedFiles.length; idx++) {
          var stepFormData = new FormData();
          stepFormData.append('csv_file', selectedFiles[idx]);
          if (uploadOptions.replaceFirstOnly) {
            stepFormData.append('replace', idx === 0 ? '1' : '0');
          }
          var stepData = await uploadCsvRequest(uploadUrl, stepFormData);
          if (!stepData.ok) {
            data = stepData;
            break;
          }
          data.created += stepData.created || 0;
          data.skipped += stepData.skipped || 0;
          if (stepData.updated) {
            data.updated = (data.updated || 0) + stepData.updated;
          }
          if (stepData.conflicts && stepData.conflicts.length) {
            data.conflicts = (data.conflicts || []).concat(stepData.conflicts);
          }
          if (stepData.warnings && stepData.warnings.length) {
            data.warnings = (data.warnings || []).concat(stepData.warnings);
          }
          if (stepData.files && stepData.files.length) {
            data.files = data.files.concat(stepData.files);
          }
        }
      } else {
        var formData = new FormData();
        if (selectedFiles.length > 1) {
          selectedFiles.forEach(function (file) {
            formData.append('csv_files', file);
          });
        } else if (selectedFiles[0]) {
          formData.append('csv_file', selectedFiles[0]);
        }
        data = await uploadCsvRequest(uploadUrl, formData);
      }
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
      'rfs-csv-upload-btn': 'rfs-csv-file-input',
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
      'numcap-csv-file-input': { url: '/classifiers/numcap/csv-upload/', refresh: 'numcap-select', sequential: true, replaceFirstOnly: true },
      'katd-csv-file-input': { url: '/classifiers/katd/csv-upload/', refresh: null },
      'rfs-csv-file-input':  { url: '/classifiers/rfs/csv-upload/',  refresh: 'rfs-select' },
      'lw-csv-file-input':   { url: '/classifiers/lw/csv-upload/',   refresh: 'lw-select' },
      'ler-csv-file-input':  { url: '/classifiers/ler/csv-upload/',  refresh: 'ler-select' },
    };
    var cfg = mapping[e.target.id];
    if (!cfg) return;
    var files = Array.from(e.target.files || []);
    if (!files.length) return;
    await handleCsvUpload(cfg.url, files.length > 1 ? files : files[0], cfg.refresh, cfg);
  });

  document.body.addEventListener('htmx:afterSettle', function (e) {
    const settleId = e.target && e.target.id;
    const last = window.__clTableSelLast;
    initClassifierWrapToggles();
    initClassifierSectionToggles();
    if (!last) return;
    const cfg = TABLE_CONFIG[last];
    const expectedId = cfg?.settleId || 'classifiers-pane';
    if (settleId !== expectedId && settleId !== 'classifiers-pane' && settleId !== 'normatives-pane' && settleId !== 'legal-entities-pane' && settleId !== 'business-entities-pane' && settleId !== 'business-entity-identifiers-pane') return;
    const ids = (window.__clTableSel && window.__clTableSel[last]) || [];
    const set = new Set(ids || []);
    getRowChecksByName(last).forEach(b => { b.checked = set.has(String(b.value)); });
    updateMasterStateFor(last);
    updateRowHighlightFor(last);
    ensureActionsVisibility(last);
    try { delete window.__clTableSel[last]; } catch(e) { window.__clTableSel[last] = []; }
    window.__clTableSelLast = null;
  });

  initClassifierWrapToggles();
  initClassifierSectionToggles();
  initBusinessEntityMasterFilter().catch(function () {});
})();
