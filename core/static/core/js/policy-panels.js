(function () {
  if (window.__policyPanelBound) return;
  window.__policyPanelBound = true;

  window.__tableSel = window.__tableSel || {};
  window.__tableSelLast = window.__tableSelLast || null;

  function pane() {
    var all = document.querySelectorAll('#policy-pane');
    return all.length > 1 ? all[all.length - 1] : all[0] || null;
  }
  const qa = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  const csrftoken = getCookie('csrftoken');
  var P = window.UIPref;
  const POLICY_FILTER_ALL = '__all__';
  const POLICY_FILTER_PREF_KEY = 'policy:masterFilters';
  const POLICY_FILTER_ORDER = ['consulting', 'category', 'subtype', 'product'];
  const POLICY_FILTER_CONFIG = {
    consulting: {
      dropdownId: 'master-policy-consulting-filter-dropdown',
      listId: 'policy-consulting-filter-list',
      allId: 'policy-consulting-filter-all',
      labelSelector: '.js-policy-consulting-filter-label',
      dataKey: 'consultingType',
    },
    category: {
      dropdownId: 'master-policy-category-filter-dropdown',
      listId: 'policy-category-filter-list',
      allId: 'policy-category-filter-all',
      labelSelector: '.js-policy-category-filter-label',
      dataKey: 'serviceCategory',
    },
    subtype: {
      dropdownId: 'master-policy-subtype-filter-dropdown',
      listId: 'policy-subtype-filter-list',
      allId: 'policy-subtype-filter-all',
      labelSelector: '.js-policy-subtype-filter-label',
      dataKey: 'serviceSubtype',
    },
    product: {
      dropdownId: 'master-policy-product-filter-dropdown',
      listId: 'policy-product-filter-list',
      allId: 'policy-product-filter-all',
      labelSelector: '.js-policy-product-filter-label',
      dataKey: 'productId',
    },
  };
  window.__policyMasterFilters = window.__policyMasterFilters || (
    P ? P.get(POLICY_FILTER_PREF_KEY, null) : null
  ) || {};
  window.__policyTypicalServiceCompositionWrapActive =
    typeof window.__policyTypicalServiceCompositionWrapActive === 'boolean'
      ? window.__policyTypicalServiceCompositionWrapActive
      : (P ? P.get('policy:typicalServiceCompositionWrapActive', true) : true);
  window.__policySpecialtyTariffsSpecialtiesCollapsed =
    typeof window.__policySpecialtyTariffsSpecialtiesCollapsed === 'boolean'
      ? window.__policySpecialtyTariffsSpecialtiesCollapsed
      : (P ? P.get('policy:specialtyTariffsSpecialtiesCollapsed', false) : false);
  const TYPICAL_SERVICE_TERM_GANTT_SCALE_PREF_KEY = 'policy:typical-service-term-gantt-scale';
  const TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY = 'policy:typical-service-term-gantt-grid-width';
  const TYPICAL_SERVICE_TERM_GANTT_COLUMNS_PREF_KEY = 'policy:typical-service-term-gantt-columns';
  const TYPICAL_SERVICE_TERM_GANTT_DEFAULT_SCALE = 'week';
  const TYPICAL_SERVICE_TERM_GANTT_SELECTION_NAME = 'typical-service-term-select';

  function initTypicalServiceCompositionWrapToggle() {
    const toggle = document.getElementById('typical-service-compositions-wrap-toggle');
    const table = document.getElementById('typical-service-compositions-table');
    if (!toggle || !table) return;
    const active = !!window.__policyTypicalServiceCompositionWrapActive;
    toggle.classList.toggle('active', active);
    table.classList.toggle('clf-truncated', active);
  }

  function specialtyCountLabel(count) {
    var n = Number(count) || 0;
    var mod10 = Math.abs(n % 10);
    if (mod10 === 1) return n + ' специальность';
    if (mod10 >= 2 && mod10 <= 4) return n + ' специальности';
    return n + ' специальностей';
  }

  function collapseSpecialtyTariffsSpecialties() {
    const root = pane();
    if (!root) return;
    const toggle = root.querySelector('#specialty-tariffs-specialties-toggle');
    const cells = qa('.specialty-tariffs-specialties-cell', root);
    const collapsed = !!window.__policySpecialtyTariffsSpecialtiesCollapsed;

    cells.forEach(function (cell) {
      const count = Number(cell.dataset.specialtyCount || '0');
      if (cell.dataset.originalSpecialtiesHtml === undefined) {
        cell.dataset.originalSpecialtiesHtml = cell.innerHTML;
      }
      if (collapsed && count > 1) {
        cell.textContent = specialtyCountLabel(count);
      } else {
        cell.innerHTML = cell.dataset.originalSpecialtiesHtml;
      }
    });

    if (toggle) {
      toggle.classList.toggle('active', collapsed);
      const icon = toggle.querySelector('i');
      if (icon) icon.className = collapsed ? 'bi bi-arrows-expand' : 'bi bi-arrows-collapse';
    }
  }

  function syncPolicyProductSelectDisplay(select) {
    const shell = select?.closest('.policy-product-select-shell');
    const display = shell?.querySelector('.policy-product-select-display');
    if (!display) return;
    const selected = select.options[select.selectedIndex];
    const hasValue = !!String(selected?.value || '').trim();
    const shortLabel = String(selected?.dataset?.shortLabel || '').trim();
    const fallbackLabel = String(selected?.textContent || '').trim();
    display.textContent = hasValue ? (shortLabel || fallbackLabel) : (fallbackLabel || '---------');
    display.classList.toggle('is-placeholder', !hasValue);
  }

  function enhancePolicyProductSelect(select) {
    if (!select || select.dataset.policyProductEnhanced === '1') {
      if (select) syncPolicyProductSelectDisplay(select);
      return;
    }
    const parent = select.parentElement;
    if (!parent) return;
    const shell = document.createElement('div');
    shell.className = 'policy-product-select-shell';
    parent.insertBefore(shell, select);
    shell.appendChild(select);
    const display = document.createElement('div');
    display.className = 'policy-product-select-display';
    shell.appendChild(display);
    select.dataset.policyProductEnhanced = '1';
    select.addEventListener('change', function () {
      syncPolicyProductSelectDisplay(select);
    });
    syncPolicyProductSelectDisplay(select);
  }

  function initPolicyProductSelects(root) {
    qa('select.policy-product-select', root).forEach(function (select) {
      enhancePolicyProductSelect(select);
    });
  }

  function bindPolicyFilterMenuWidth(dropdown) {
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
      menu.style.minWidth = Math.max(controlWidth, 200, widestLabel + checkboxWidth + 64) + 'px';
    });
  }

  function normalizeFilterValue(value) {
    return String(value || '').trim();
  }

  function escapePolicyHtml(value) {
    return String(value || '').replace(/[&<>"']/g, function (char) {
      return ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
      })[char];
    });
  }

  function parsePolicyGanttDate(value) {
    if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
    const raw = normalizeFilterValue(value);
    if (!raw) return null;
    const isoMatch = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
    if (isoMatch) return new Date(Number(isoMatch[1]), Number(isoMatch[2]) - 1, Number(isoMatch[3]));
    const dotMatch = raw.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
    if (dotMatch) return new Date(Number(dotMatch[3]), Number(dotMatch[2]) - 1, Number(dotMatch[1]));
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function addPolicyGanttDays(date, days) {
    const next = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    next.setDate(next.getDate() + days);
    return next;
  }

  function filterStateWithDefaults(source) {
    const state = {};
    POLICY_FILTER_ORDER.forEach(function (key) {
      const values = Array.isArray(source?.[key]) ? source[key].map(normalizeFilterValue).filter(Boolean) : [];
      state[key] = values.length ? values : [POLICY_FILTER_ALL];
    });
    return state;
  }

  function filterMatches(value, values) {
    return values.includes(POLICY_FILTER_ALL) || !values.length || values.includes(normalizeFilterValue(value));
  }

  function safeFilterId(key, value, index) {
    return 'policy-' + key + '-filter-' + index + '-' + String(value).replace(/[^a-zA-Z0-9_-]/g, '-');
  }

  function addOption(options, seen, value, label, extra) {
    const normalizedValue = normalizeFilterValue(value);
    if (!normalizedValue || seen.has(normalizedValue)) return;
    seen.add(normalizedValue);
    options.push(Object.assign({
      value: normalizedValue,
      label: normalizeFilterValue(label) || normalizedValue,
    }, extra || {}));
  }

  function getPolicyProductCatalog(root) {
    const products = [];
    const seen = new Set();
    qa('tr[data-policy-filter-row="1"][data-product-id][data-consulting-type-ref]', root).forEach(function (row) {
      const id = normalizeFilterValue(row.dataset.productId);
      if (!id || seen.has(id)) return;
      seen.add(id);
      products.push({
        id: id,
        label: normalizeFilterValue(row.dataset.productLabel) || id,
        consulting: normalizeFilterValue(row.dataset.consultingType),
        category: normalizeFilterValue(row.dataset.serviceCategory),
        subtype: normalizeFilterValue(row.dataset.serviceSubtype),
        consultingRef: normalizeFilterValue(row.dataset.consultingTypeRef),
        categoryRef: normalizeFilterValue(row.dataset.serviceCategoryRef),
        subtypeRef: normalizeFilterValue(row.dataset.serviceSubtypeRef),
      });
    });
    return products;
  }

  function buildPolicyFilterOptions(rows, products) {
    const options = {
      consulting: [],
      category: [],
      subtype: [],
      product: [],
    };
    const seen = {
      consulting: new Set(),
      category: new Set(),
      subtype: new Set(),
      product: new Set(),
    };
    rows.forEach(function (row) {
      addOption(options.consulting, seen.consulting, row.dataset.consultingType, row.dataset.consultingType);
      addOption(options.category, seen.category, row.dataset.serviceCategory, row.dataset.serviceCategory);
      addOption(options.subtype, seen.subtype, row.dataset.serviceSubtype, row.dataset.serviceSubtype);
    });
    products.forEach(function (product) {
      addOption(options.consulting, seen.consulting, product.consulting, product.consulting);
      addOption(options.category, seen.category, product.category, product.category);
      addOption(options.subtype, seen.subtype, product.subtype, product.subtype);
      addOption(options.product, seen.product, product.id, product.label, {
        consulting: product.consulting,
        category: product.category,
        subtype: product.subtype,
      });
    });
    return options;
  }

  function rowMatchesPolicySelection(row, state) {
    const consulting = normalizeFilterValue(row.dataset.consultingType);
    const category = normalizeFilterValue(row.dataset.serviceCategory);
    const subtype = normalizeFilterValue(row.dataset.serviceSubtype);
    return filterMatches(consulting, state.consulting)
      && filterMatches(category, state.category)
      && filterMatches(subtype, state.subtype);
  }

  function entityMatchesPolicyAvailability(entity, key, state, selectedProducts) {
    if (key !== 'consulting' && !filterMatches(entity.consulting, state.consulting)) return false;
    if (key !== 'category' && !filterMatches(entity.category, state.category)) return false;
    if (key !== 'subtype' && !filterMatches(entity.subtype, state.subtype)) return false;
    if (key !== 'product' && !state.product.includes(POLICY_FILTER_ALL)) {
      if (entity.productId) return state.product.includes(entity.productId);
      return selectedProducts.some(function (product) {
        return product.consulting === entity.consulting
          && product.category === entity.category
          && product.subtype === entity.subtype;
      });
    }
    return true;
  }

  function getAvailablePolicyValues(key, rows, products, state) {
    const values = new Set();
    const selectedProducts = state.product.includes(POLICY_FILTER_ALL)
      ? []
      : products.filter(function (product) { return state.product.includes(product.id); });
    rows.forEach(function (row) {
      const entity = {
        consulting: normalizeFilterValue(row.dataset.consultingType),
        category: normalizeFilterValue(row.dataset.serviceCategory),
        subtype: normalizeFilterValue(row.dataset.serviceSubtype),
        productId: normalizeFilterValue(row.dataset.productId),
      };
      if (entityMatchesPolicyAvailability(entity, key, state, selectedProducts)) {
        values.add(normalizeFilterValue(row.dataset[POLICY_FILTER_CONFIG[key].dataKey]));
      }
    });
    products.forEach(function (product) {
      const entity = {
        consulting: product.consulting,
        category: product.category,
        subtype: product.subtype,
        productId: product.id,
      };
      if (entityMatchesPolicyAvailability(entity, key, state, selectedProducts)) {
        const value = key === 'consulting'
          ? product.consulting
          : (key === 'category' ? product.category : (key === 'subtype' ? product.subtype : product.id));
        values.add(normalizeFilterValue(value));
      }
    });
    values.delete('');
    return values;
  }

  function getPolicyFilterChecks(key) {
    const dropdown = document.getElementById(POLICY_FILTER_CONFIG[key].dropdownId);
    return dropdown ? Array.from(dropdown.querySelectorAll('.js-policy-master-filter[data-filter-key="' + key + '"]')) : [];
  }

  function selectOnlyPolicyAll(checks) {
    checks.forEach(function (cb) {
      cb.checked = cb.value === POLICY_FILTER_ALL;
    });
    return [POLICY_FILTER_ALL];
  }

  function normalizePolicySelection(key, checks, values, availableValues) {
    let nextValues = (Array.isArray(values) ? values : [])
      .map(normalizeFilterValue)
      .filter(Boolean);
    if (!nextValues.length || nextValues.includes(POLICY_FILTER_ALL)) {
      return selectOnlyPolicyAll(checks);
    }
    nextValues = nextValues.filter(function (value) {
      return availableValues.has(value);
    });
    if (!nextValues.length) return selectOnlyPolicyAll(checks);
    const set = new Set(nextValues);
    checks.forEach(function (cb) {
      cb.checked = set.has(cb.value);
    });
    return nextValues;
  }

  function updatePolicyFilterLabel(key, values) {
    const labelNode = document.querySelector(POLICY_FILTER_CONFIG[key].labelSelector);
    if (!labelNode) return;
    if (!values.length || values.includes(POLICY_FILTER_ALL)) {
      labelNode.textContent = 'Все';
      return;
    }
    if (values.length === 1) {
      const input = getPolicyFilterChecks(key).find(function (cb) { return cb.value === values[0]; });
      labelNode.textContent = input?.dataset?.summaryLabel || '1 выбрано';
      return;
    }
    labelNode.textContent = values.length + ' выбрано';
  }

  function renderPolicyFilterOptions(options) {
    POLICY_FILTER_ORDER.forEach(function (key) {
      const cfg = POLICY_FILTER_CONFIG[key];
      const dropdown = document.getElementById(cfg.dropdownId);
      const list = document.getElementById(cfg.listId);
      if (!dropdown || !list) return;
      bindPolicyFilterMenuWidth(dropdown);
      list.innerHTML = '';
      options[key].forEach(function (item, index) {
        const div = document.createElement('div');
        div.className = key === 'product' ? 'form-check policy-master-product-option' : 'form-check';
        const input = document.createElement('input');
        input.className = 'form-check-input js-policy-master-filter';
        input.type = 'checkbox';
        input.value = item.value;
        input.id = safeFilterId(key, item.value, index);
        input.dataset.filterKey = key;
        input.dataset.summaryLabel = item.label;
        input.dataset.fullLabel = item.label;
        const label = document.createElement('label');
        label.className = key === 'product' ? 'form-check-label text-nowrap' : 'form-check-label';
        label.htmlFor = input.id;
        label.textContent = item.label;
        div.appendChild(input);
        div.appendChild(label);
        list.appendChild(div);
      });
    });
  }

  function collectPolicyFilterStateFromChecks() {
    const state = {};
    POLICY_FILTER_ORDER.forEach(function (key) {
      state[key] = getPolicyFilterChecks(key)
        .filter(function (cb) { return cb.checked; })
        .map(function (cb) { return cb.value; });
    });
    return filterStateWithDefaults(state);
  }

  function setPolicyFilterAvailability(key, availableValues) {
    getPolicyFilterChecks(key).forEach(function (cb) {
      if (cb.value === POLICY_FILTER_ALL) {
        cb.disabled = false;
        return;
      }
      const available = availableValues.has(cb.value);
      const item = cb.closest('.form-check');
      if (item) item.classList.toggle('d-none', !available);
      cb.disabled = !available;
      if (!available) cb.checked = false;
    });
  }

  function syncAllPolicySelectionStates(root) {
    const names = new Set();
    qa('input.form-check-input[data-target-name]', root).forEach(function (master) {
      names.add(master.dataset.targetName);
    });
    names.forEach(function (name) {
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
    });
    syncTypicalServiceTermGanttEditButton();
  }

  function applyPolicyMasterFilters(root, rows, products, requestedState) {
    const state = filterStateWithDefaults(requestedState);
    POLICY_FILTER_ORDER.forEach(function (key) {
      const checks = getPolicyFilterChecks(key);
      const availableValues = getAvailablePolicyValues(key, rows, products, state);
      setPolicyFilterAvailability(key, availableValues);
      state[key] = normalizePolicySelection(key, checks, state[key], availableValues);
    });
    const selectedProductIds = state.product.includes(POLICY_FILTER_ALL) ? [] : state.product;
    const selectedProducts = products.filter(function (product) {
      return selectedProductIds.includes(product.id);
    });
    rows.forEach(function (row) {
      let visible = rowMatchesPolicySelection(row, state);
      if (visible && selectedProductIds.length) {
        const rowProductId = normalizeFilterValue(row.dataset.productId);
        if (rowProductId) {
          visible = selectedProductIds.includes(rowProductId);
        } else {
          visible = selectedProducts.some(function (product) {
            return product.consulting === normalizeFilterValue(row.dataset.consultingType)
              && product.category === normalizeFilterValue(row.dataset.serviceCategory)
              && product.subtype === normalizeFilterValue(row.dataset.serviceSubtype);
          });
        }
      }
      row.classList.toggle('d-none', !visible);
      row.querySelectorAll('input.form-check-input[name]').forEach(function (cb) {
        if (cb.dataset.policyOriginalDisabled === undefined) {
          cb.dataset.policyOriginalDisabled = cb.disabled ? '1' : '0';
        }
        cb.disabled = cb.dataset.policyOriginalDisabled === '1' || !visible;
        if (!visible) cb.checked = false;
      });
    });
    POLICY_FILTER_ORDER.forEach(function (key) {
      updatePolicyFilterLabel(key, state[key]);
    });
    window.__policyMasterFilters = state;
    if (P) P.set(POLICY_FILTER_PREF_KEY, state);
    syncAllPolicySelectionStates(root);
  }

  function initPolicyMasterFilters() {
    const root = pane();
    if (!root) return;
    const missing = POLICY_FILTER_ORDER.some(function (key) {
      const cfg = POLICY_FILTER_CONFIG[key];
      return !document.getElementById(cfg.dropdownId) || !document.getElementById(cfg.listId);
    });
    if (missing) return;

    const rows = qa('tr[data-policy-filter-row="1"]', root);
    const products = getPolicyProductCatalog(root);
    renderPolicyFilterOptions(buildPolicyFilterOptions(rows, products));
    const savedState = filterStateWithDefaults(window.__policyMasterFilters);

    POLICY_FILTER_ORDER.forEach(function (key) {
      const checks = getPolicyFilterChecks(key);
      const selected = new Set(savedState[key]);
      checks.forEach(function (cb) {
        cb.checked = selected.has(cb.value);
        cb.onchange = function (event) {
          const changed = event.target;
          if (changed.value === POLICY_FILTER_ALL && changed.checked) {
            selectOnlyPolicyAll(checks);
          } else if (changed.value === POLICY_FILTER_ALL && !changed.checked) {
            const first = checks.find(function (item) { return item.value !== POLICY_FILTER_ALL && !item.disabled; });
            if (first) first.checked = true;
          } else if (changed.checked) {
            const allCb = document.getElementById(POLICY_FILTER_CONFIG[key].allId);
            if (allCb) allCb.checked = false;
          }
          const nextState = collectPolicyFilterStateFromChecks();
          if (key === 'product') {
            const selectedProducts = nextState.product.filter(function (value) { return value !== POLICY_FILTER_ALL; });
            if (selectedProducts.length === 1) {
              const product = products.find(function (item) { return item.id === selectedProducts[0]; });
              if (product) {
                if (product.consulting) nextState.consulting = [product.consulting];
                if (product.category) nextState.category = [product.category];
                if (product.subtype) nextState.subtype = [product.subtype];
              }
            }
          }
          applyPolicyMasterFilters(root, rows, products, nextState);
        };
      });
    });
    applyPolicyMasterFilters(root, rows, products, savedState);
  }

  function getSelectedPolicyMasterProduct() {
    const root = pane();
    if (!root) return null;
    const state = filterStateWithDefaults(window.__policyMasterFilters);
    const productValues = state.product || [];
    if (productValues.length !== 1 || productValues[0] === POLICY_FILTER_ALL) return null;
    return getPolicyProductCatalog(root).find(function (product) {
      return product.id === productValues[0];
    }) || null;
  }

  function getMasterForPanel(panel) {
    const id = panel?.id;
    if (!id) return null;
    return pane()?.querySelector(`input.form-check-input[data-actions-id="${CSS.escape(id)}"]`) || null;
  }
  function getNameForPanel(panel) {
    const master = getMasterForPanel(panel);
    return master?.dataset?.targetName || null;
  }
  function getRowChecksByName(name) {
    const root = pane();
    return qa(`tbody input.form-check-input[name="${CSS.escape(name)}"]`, root).filter(function (box) {
      const tr = box.closest('tr');
      return !box.disabled && !tr?.classList.contains('d-none');
    });
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

  function getTypicalServiceTermSelectedRow() {
    const checked = getCheckedByName(TYPICAL_SERVICE_TERM_GANTT_SELECTION_NAME);
    return checked.length === 1 ? checked[0].closest('tr') : null;
  }

  function syncTypicalServiceTermGanttEditButton() {
    const root = pane();
    if (!root) return;
    const button = root.querySelector('[data-typical-service-term-gantt-edit]');
    if (!button) return;
    const row = getTypicalServiceTermSelectedRow();
    const ganttUrl = normalizeFilterValue(row?.dataset?.ganttUrl);
    const enabled = !!row && !!ganttUrl;
    button.disabled = !enabled;
    button.classList.toggle('d-none', !enabled);
    button.dataset.ganttUrl = enabled ? ganttUrl : '';
    button.dataset.termId = enabled ? normalizeFilterValue(row.querySelector('input[name="typical-service-term-select"]')?.value) : '';
    button.dataset.productLabel = enabled ? normalizeFilterValue(row.dataset.productLabel || row.children[1]?.textContent) : '';
  }

  function getTypicalServiceTermGanttScale(root) {
    const activeButton = root?.querySelector('.js-typical-service-term-gantt-scale.active');
    const savedScale = P ? P.get(TYPICAL_SERVICE_TERM_GANTT_SCALE_PREF_KEY, TYPICAL_SERVICE_TERM_GANTT_DEFAULT_SCALE) : TYPICAL_SERVICE_TERM_GANTT_DEFAULT_SCALE;
    const scale = activeButton?.dataset?.scale || savedScale;
    return ['day', 'week', 'month', 'quarter'].includes(scale) ? scale : TYPICAL_SERVICE_TERM_GANTT_DEFAULT_SCALE;
  }

  function getTypicalServiceTermGanttGridWidth() {
    const defaultWidth = 820;
    const saved = P ? Number(P.get(TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY, defaultWidth)) : defaultWidth;
    return Number.isFinite(saved) ? Math.max(360, Math.min(1200, Math.round(saved))) : defaultWidth;
  }

  function getTypicalServiceTermGanttColumnWidths() {
    const saved = P ? P.get(TYPICAL_SERVICE_TERM_GANTT_COLUMNS_PREF_KEY, {}) : {};
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
  }

  function typicalServiceTermGanttColumn(name, fallbackWidth, extra) {
    const widths = getTypicalServiceTermGanttColumnWidths();
    const savedWidth = Number(widths[name]);
    const width = Number.isFinite(savedWidth)
      ? Math.max(44, Math.min(600, Math.round(savedWidth)))
      : fallbackWidth;
    return Object.assign({ name: name, width: width, resize: true }, extra || {});
  }

  function saveTypicalServiceTermGanttColumns(gantt) {
    if (!P || !Array.isArray(gantt?.config?.columns)) return;
    const widths = {};
    gantt.config.columns.forEach(function (column) {
      if (!column?.name || !Number.isFinite(Number(column.width))) return;
      widths[column.name] = Math.round(Number(column.width));
    });
    P.set(TYPICAL_SERVICE_TERM_GANTT_COLUMNS_PREF_KEY, widths);
  }

  function getTypicalServiceTermGanttColumnsWidth(gantt) {
    if (!Array.isArray(gantt?.config?.columns)) return getTypicalServiceTermGanttGridWidth();
    const width = gantt.config.columns.reduce(function (total, column) {
      return total + (Number(column.width) || 0);
    }, 0);
    return Math.max(360, Math.min(1200, Math.round(width || getTypicalServiceTermGanttGridWidth())));
  }

  function getTypicalServiceTermGanttWbsCode(gantt, task) {
    if (!gantt || !task) return '';
    try {
      if (typeof gantt.getWBSCode === 'function') return gantt.getWBSCode(task) || '';
    } catch (_) { /* fall back to row index */ }
    const index = Number(task.$index);
    return Number.isFinite(index) ? String(index + 1) : '';
  }

  function typicalServiceTermGanttGridValueHtml(value, className) {
    return '<span class="' + className + '">' + escapePolicyHtml(value) + '</span>';
  }

  function getTypicalServiceTermGanttLinkTypeCode(gantt, link) {
    const types = gantt?.config?.links || {};
    const type = link?.type;
    if (String(type) === String(types.start_to_start)) return 'НН';
    if (String(type) === String(types.finish_to_finish)) return 'ОО';
    if (String(type) === String(types.start_to_finish)) return 'НО';
    return 'ОН';
  }

  function formatTypicalServiceTermGanttPredecessors(gantt, task) {
    if (!gantt || !task || typeof gantt.getLinks !== 'function') return '';
    const taskId = String(task.id);
    return gantt.getLinks()
      .filter(function (link) {
        return String(link?.target) === taskId;
      })
      .map(function (link) {
        let sourceTask = null;
        try {
          sourceTask = typeof gantt.getTask === 'function' ? gantt.getTask(link.source) : null;
        } catch (_) {
          sourceTask = null;
        }
        const wbs = getTypicalServiceTermGanttWbsCode(gantt, sourceTask);
        return wbs ? wbs + getTypicalServiceTermGanttLinkTypeCode(gantt, link) : '';
      })
      .filter(Boolean)
      .join(', ');
  }

  function formatTypicalServiceTermGanttDuration(task) {
    const duration = Number(task?.duration);
    const value = Number.isFinite(duration) ? Math.round(duration) : '';
    return typicalServiceTermGanttGridValueHtml(value, 'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--duration');
  }

  function formatTypicalServiceTermGanttProgress(task) {
    const progress = Math.max(0, Math.min(1, Number(task?.progress) || 0));
    return typicalServiceTermGanttGridValueHtml(Math.round(progress * 100) + '%', 'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--progress');
  }

  function installTypicalServiceTermGanttColumnResizeHandles(gantt, chart) {
    if (!gantt || !chart) return;
    const syncTimelineHorizontalScrollbar = function () {
      const timeline = chart.querySelector('.gantt_task');
      const scrollbar = gantt.$ui?.getView?.('scrollHor')?.$view;
      if (!timeline || !scrollbar) return;
      const chartRect = chart.getBoundingClientRect();
      const timelineRect = timeline.getBoundingClientRect();
      scrollbar.style.marginLeft = Math.round(timelineRect.left - chartRect.left) + 'px';
      scrollbar.style.width = Math.max(0, Math.round(timelineRect.width)) + 'px';
    };
    const syncGridHandle = function () {
      const grid = chart.querySelector('.gantt_grid');
      let handle = chart.querySelector('.typical-service-term-gantt-grid-resizer');
      if (!grid) {
        if (handle) handle.remove();
        return;
      }
      if (!handle) {
        handle = document.createElement('span');
        handle.className = 'typical-service-term-gantt-grid-resizer';
        handle.setAttribute('aria-hidden', 'true');
        chart.appendChild(handle);
      }
      const chartRect = chart.getBoundingClientRect();
      const gridRect = grid.getBoundingClientRect();
      const gridScale = chart.querySelector('.gantt_grid_scale');
      const gridScaleRect = gridScale?.getBoundingClientRect();
      handle.style.left = Math.round(gridRect.right - chartRect.left) + 'px';
      handle.style.top = gridScaleRect ? Math.round(gridScaleRect.bottom - chartRect.top) + 'px' : '0px';
      syncTimelineHorizontalScrollbar();
    };
    syncGridHandle();
    let lastColumnHandleSeen = false;
    chart.querySelectorAll('.gantt_grid_scale .gantt_grid_head_cell[data-column-index]').forEach(function (cell) {
      if (cell.classList.contains('gantt_last_cell')) {
        cell.querySelectorAll('.typical-service-term-gantt-column-resizer').forEach(function (handle) {
          handle.remove();
        });
        let lastHandle = chart.querySelector('.typical-service-term-gantt-column-resizer--last');
        if (!lastHandle) {
          lastHandle = document.createElement('span');
          lastHandle.className = 'typical-service-term-gantt-column-resizer typical-service-term-gantt-column-resizer--last';
          lastHandle.setAttribute('aria-hidden', 'true');
          chart.appendChild(lastHandle);
        }
        const chartRect = chart.getBoundingClientRect();
        const cellRect = cell.getBoundingClientRect();
        lastHandle.dataset.columnIndex = cell.dataset.columnIndex || '';
        lastHandle.style.left = Math.round(cellRect.right - chartRect.left - 8) + 'px';
        lastHandle.style.top = Math.round(cellRect.top - chartRect.top) + 'px';
        lastHandle.style.height = Math.round(cellRect.height) + 'px';
        lastColumnHandleSeen = true;
        return;
      }
      if (cell.querySelector('.typical-service-term-gantt-column-resizer')) return;
      const handle = document.createElement('span');
      handle.className = 'typical-service-term-gantt-column-resizer';
      handle.dataset.columnIndex = cell.dataset.columnIndex || '';
      handle.setAttribute('aria-hidden', 'true');
      cell.appendChild(handle);
    });
    if (!lastColumnHandleSeen) {
      chart.querySelector('.typical-service-term-gantt-column-resizer--last')?.remove();
    }

    if (chart.dataset.typicalServiceTermGanttColumnResizeBound === '1') return;
    chart.dataset.typicalServiceTermGanttColumnResizeBound = '1';
    chart.addEventListener('mousedown', function (event) {
      const gridResizer = event.target?.closest?.('.typical-service-term-gantt-grid-resizer, .gantt_resizer, .gantt_grid_resize_wrap');
      if (!gridResizer || !chart.contains(gridResizer)) return;
      if (gridResizer.classList.contains('typical-service-term-gantt-grid-resizer')) {
        event.preventDefault();
        event.stopPropagation();
        const startX = event.clientX;
        const startWidth = Number(gantt.config.grid_width) || getTypicalServiceTermGanttGridWidth();
        const chartWidth = chart.getBoundingClientRect().width || 1200;
        const maxWidth = Math.max(360, Math.min(1200, Math.round(chartWidth - 240)));
        gridResizer.classList.add('is-resizing');

        const onMove = function (moveEvent) {
          gantt.config.grid_width = Math.max(360, Math.min(maxWidth, Math.round(startWidth + moveEvent.clientX - startX)));
          gantt.setSizes();
          syncGridHandle();
          syncTimelineHorizontalScrollbar();
          installTypicalServiceTermGanttColumnResizeHandles(gantt, chart);
          alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
        };

        const onUp = function () {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          gridResizer.classList.remove('is-resizing');
          syncGridHandle();
          syncTimelineHorizontalScrollbar();
          installTypicalServiceTermGanttColumnResizeHandles(gantt, chart);
          alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
          if (P) {
            P.set(TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY, Math.round(Number(gantt.config.grid_width) || getTypicalServiceTermGanttGridWidth()));
          }
        };

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp, { once: true });
        return;
      }
      gridResizer.classList.add('is-resizing');
      document.addEventListener('mouseup', function () {
        gridResizer.classList.remove('is-resizing');
      }, { once: true });
    });
    chart.addEventListener('mousedown', function (event) {
      const handle = event.target?.closest?.('.typical-service-term-gantt-column-resizer');
      if (!handle || !chart.contains(handle)) return;
      const index = Number(handle.dataset.columnIndex);
      const column = gantt.config.columns?.[index];
      if (!column) return;

      event.preventDefault();
      event.stopPropagation();
      const startX = event.clientX;
      const startWidth = Number(column.width) || handle.parentElement?.offsetWidth || 80;
      const startGridWidth = Number(gantt.config.grid_width) || getTypicalServiceTermGanttGridWidth();
      const minWidth = Number(column.min_width) || 44;
      const maxWidth = Number(column.max_width) || 600;
      chart.classList.add('typical-service-term-gantt-column-resizing');
      handle.classList.add('is-resizing');

      const onMove = function (moveEvent) {
        const nextWidth = Math.max(minWidth, Math.min(maxWidth, Math.round(startWidth + moveEvent.clientX - startX)));
        if (nextWidth === column.width) return;
        column.width = nextWidth;
        gantt.config.grid_width = Math.max(360, Math.min(1200, Math.round(startGridWidth + nextWidth - startWidth)));
        gantt.render();
        installTypicalServiceTermGanttColumnResizeHandles(gantt, chart);
        alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
      };

      const onUp = function () {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        chart.classList.remove('typical-service-term-gantt-column-resizing');
        handle.classList.remove('is-resizing');
        alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
        if (P) {
          P.set(TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY, Math.round(Number(gantt.config.grid_width) || getTypicalServiceTermGanttColumnsWidth(gantt)));
        }
        saveTypicalServiceTermGanttColumns(gantt);
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp, { once: true });
    });
  }

  function installTypicalServiceTermGanttLightboxDblClick(gantt, chart) {
    if (!gantt || !chart || chart.dataset.typicalServiceTermGanttDblClickBound === '1') return;
    chart.dataset.typicalServiceTermGanttDblClickBound = '1';
    const taskIdFromEvent = function (event) {
      if (event.target?.closest?.('.gantt_grid_head_cell, .gantt_add, .typical-service-term-gantt-column-resizer, .typical-service-term-gantt-grid-resizer')) {
        return '';
      }
      const taskElement = event.target?.closest?.('.gantt_task_line, .gantt_row, .gantt_cell, .gantt_task_row');
      if (!taskElement || !chart.contains(taskElement)) return '';
      const taskAttribute = gantt.config.task_attribute || 'data-task-id';
      const taskNode = event.target?.closest?.('[' + taskAttribute + ']');
      const taskId = (taskNode && chart.contains(taskNode) ? taskNode.getAttribute(taskAttribute) : '') || gantt.locate(event) || gantt.locate(taskElement);
      if (!taskId || (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(taskId))) return '';
      return taskId;
    };
    const openTaskLightbox = function (event, taskId) {
      event.preventDefault();
      event.stopPropagation();
      if (typeof gantt.showLightbox === 'function') {
        gantt.showLightbox(taskId);
      }
    };
    const handleSyntheticDoubleClick = function (event, stateKey) {
      if (event.button && event.button !== 0) return;
      const taskId = taskIdFromEvent(event);
      if (!taskId) return;
      const now = Date.now();
      const last = chart[stateKey] || {};
      const isSecondClick = last.taskId === taskId
        && now - last.time < 450
        && Math.abs((last.x || 0) - event.clientX) < 8
        && Math.abs((last.y || 0) - event.clientY) < 8;
      chart[stateKey] = { taskId: taskId, time: now, x: event.clientX, y: event.clientY };
      if (isSecondClick) {
        chart[stateKey] = {};
        openTaskLightbox(event, taskId);
      }
    };
    chart.addEventListener('mousedown', function (event) {
      handleSyntheticDoubleClick(event, '_typicalServiceTermGanttLastMouseDown');
    }, true);
    chart.addEventListener('click', function (event) {
      handleSyntheticDoubleClick(event, '_typicalServiceTermGanttLastClick');
    }, true);
    chart.addEventListener('dblclick', function (event) {
      const taskId = taskIdFromEvent(event);
      if (!taskId) return;
      openTaskLightbox(event, taskId);
    }, true);
  }

  function escapeTypicalServiceTermGanttSelectorValue(value) {
    const raw = String(value || '');
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(raw);
    return raw.replace(/["\\]/g, '\\$&');
  }

  function getTypicalServiceTermGanttDomTaskId(target) {
    const node = target?.closest?.('[data-task-id], [task_id]');
    if (!node) return '';
    return node.getAttribute('data-task-id') || node.getAttribute('task_id') || '';
  }

  function setTypicalServiceTermGanttHoveredRow(chart, taskId) {
    const normalizedTaskId = String(taskId || '');
    chart?.querySelectorAll('.typical-service-term-gantt-hover-row').forEach(function (node) {
      node.classList.remove('typical-service-term-gantt-hover-row');
    });
    if (!chart || !normalizedTaskId) return;

    const escapedTaskId = escapeTypicalServiceTermGanttSelectorValue(normalizedTaskId);
    const selector = '[data-task-id="' + escapedTaskId + '"], [task_id="' + escapedTaskId + '"]';
    chart.querySelectorAll(selector).forEach(function (node) {
      if (!node.classList.contains('gantt_row') && !node.classList.contains('gantt_task_row') && !node.classList.contains('gantt_task_line')) return;
      node.classList.add('typical-service-term-gantt-hover-row');
    });
  }

  function selectTypicalServiceTermGanttTaskSilently(gantt, chart, taskId) {
    if (!gantt || !chart) return;
    const tasksStore = gantt.$data?.tasksStore;
    const normalizedTaskId = String(taskId || '');
    if (!tasksStore || !normalizedTaskId) return;
    const previousSelectedId = typeof gantt.getSelectedId === 'function' ? gantt.getSelectedId() : null;
    if (previousSelectedId && String(previousSelectedId) === normalizedTaskId) return;
    const previousSkipRefresh = tasksStore._skip_refresh;
    tasksStore._skip_refresh = true;
    try {
      gantt.selectTask(normalizedTaskId);
    } finally {
      tasksStore._skip_refresh = previousSkipRefresh;
    }
    const buildSelectorForId = function (escapedId) {
      return [
        '.gantt_task_line[task_id="' + escapedId + '"]',
        '.gantt_task_line[data-task-id="' + escapedId + '"]',
        '.gantt_row[task_id="' + escapedId + '"]',
        '.gantt_row[data-task-id="' + escapedId + '"]',
        '.gantt_task_row[task_id="' + escapedId + '"]',
        '.gantt_task_row[data-task-id="' + escapedId + '"]',
      ].join(', ');
    };
    if (previousSelectedId && String(previousSelectedId) !== normalizedTaskId) {
      const escapedPrev = escapeTypicalServiceTermGanttSelectorValue(String(previousSelectedId));
      chart.querySelectorAll(buildSelectorForId(escapedPrev)).forEach(function (node) {
        node.classList.remove('gantt_selected');
      });
    }
    const escapedNew = escapeTypicalServiceTermGanttSelectorValue(normalizedTaskId);
    chart.querySelectorAll(buildSelectorForId(escapedNew)).forEach(function (node) {
      node.classList.add('gantt_selected');
    });
  }

  function setTypicalServiceTermGanttActiveRow(chart, taskId) {
    const normalizedTaskId = String(taskId || '');
    chart?.querySelectorAll('.typical-service-term-gantt-active-row').forEach(function (node) {
      node.classList.remove('typical-service-term-gantt-active-row');
    });
    if (!chart) return;
    if (!normalizedTaskId) {
      delete chart.dataset.activeTaskId;
      return;
    }
    chart.dataset.activeTaskId = normalizedTaskId;

    const escapedTaskId = escapeTypicalServiceTermGanttSelectorValue(normalizedTaskId);
    const selector = '[data-task-id="' + escapedTaskId + '"], [task_id="' + escapedTaskId + '"]';
    chart.querySelectorAll(selector).forEach(function (node) {
      if (!node.classList.contains('gantt_row') && !node.classList.contains('gantt_task_row') && !node.classList.contains('gantt_task_line')) return;
      node.classList.add('typical-service-term-gantt-active-row');
    });
  }

  function alignTypicalServiceTermGanttLinkHandles(chart) {
    if (!chart) return;
    chart.querySelectorAll('.gantt_task_line[data-task-id], .gantt_task_line[task_id]').forEach(function (taskNode) {
      const taskId = getTypicalServiceTermGanttDomTaskId(taskNode);
      if (!taskId) return;
      const escapedTaskId = escapeTypicalServiceTermGanttSelectorValue(taskId);
      const row = chart.querySelector(
        '.gantt_task_bg .gantt_task_row[data-task-id="' + escapedTaskId + '"], ' +
        '.gantt_task_bg .gantt_task_row[task_id="' + escapedTaskId + '"]'
      );
      if (!row) return;
      const taskRect = taskNode.getBoundingClientRect();
      const rowRect = row.getBoundingClientRect();
      const rowCenterInTask = rowRect.top + (rowRect.height / 2) - taskRect.top;
      taskNode.querySelectorAll('.gantt_link_control').forEach(function (control) {
        control.style.top = rowCenterInTask + 'px';
      });
    });
  }

  function patchTypicalServiceTermGanttLinkDirStart(gantt) {
    const timeline = gantt?.$ui?.getView?.('timeline');
    if (!timeline?._linksDnD) return null;
    if (timeline._linksDnD.$policyDirStartPatched) return timeline._linksDnD;
    const linksDnD = timeline._linksDnD;
    const liveTarget = { x: 0, y: 0 };
    let hasOverride = false;
    Object.defineProperty(linksDnD, '_dir_start', {
      configurable: true,
      get: function () { return liveTarget; },
      set: function (value) {
        if (!hasOverride && value && typeof value === 'object') {
          liveTarget.x = Number(value.x) || 0;
          liveTarget.y = Number(value.y) || 0;
        }
      },
    });
    linksDnD.$setPolicyDirStartOverride = function (value) {
      if (value && typeof value === 'object') {
        liveTarget.x = Number(value.x) || 0;
        liveTarget.y = Number(value.y) || 0;
        hasOverride = true;
      } else {
        hasOverride = false;
      }
    };
    linksDnD.$policyDirStartPatched = true;
    return linksDnD;
  }

  function bindTypicalServiceTermGanttLinkSourceState(gantt, chart) {
    if (!chart) return;
    patchTypicalServiceTermGanttLinkDirStart(gantt);
    if (chart.dataset.typicalServiceTermGanttLinkSourceBound === '1') return;
    chart.dataset.typicalServiceTermGanttLinkSourceBound = '1';

    const tasksStore = gantt?.$data?.tasksStore;
    if (tasksStore && typeof tasksStore.attachEvent === 'function' && !tasksStore.$policyTypicalServiceTermLinkSourceBound) {
      tasksStore.$policyTypicalServiceTermLinkSourceBound = true;
      tasksStore.attachEvent('onStoreUpdated', function (id) {
        const currentChart = document.getElementById('typical-service-term-gantt');
        if (!currentChart || !currentChart.classList.contains('typical-service-term-gantt-link-dragging')) return true;
        const reapply = currentChart.$policyTypicalServiceTermReapplyLinkSource;
        if (typeof reapply !== 'function') return true;
        const sourceTaskId = currentChart.dataset.linkSourceTaskId;
        if (sourceTaskId && id !== undefined && id !== null && String(id) !== sourceTaskId) return true;
        reapply();
        requestAnimationFrame(reapply);
        return true;
      });
    }

    const setDirStartOverride = function (value) {
      const linksDnD = patchTypicalServiceTermGanttLinkDirStart(gantt);
      if (linksDnD && typeof linksDnD.$setPolicyDirStartOverride === 'function') {
        linksDnD.$setPolicyDirStartOverride(value);
      }
    };

    const computePointCenterRelativeToLinks = function (point) {
      const reference = gantt?.$task_links || gantt?.$task_bg || gantt?.$task_bars || gantt?.$task_data;
      if (!reference || !point || !document.body.contains(point)) return null;
      const pointRect = point.getBoundingClientRect();
      const refRect = reference.getBoundingClientRect();
      return {
        x: pointRect.left + (pointRect.width / 2) - refRect.left,
        y: pointRect.top + (pointRect.height / 2) - refRect.top,
      };
    };

    let activePoint = null;
    let activeTaskId = '';
    let activeProperty = '';
    let dragMoveHandler = null;
    let dragRaf = 0;

    const getPointAtEvent = function (event) {
      const directPoint = event?.target?.closest?.('.gantt_link_control .gantt_link_point');
      if (directPoint && chart.contains(directPoint)) return directPoint;
      const elementAtPoint = document.elementFromPoint(event.clientX, event.clientY);
      const point = elementAtPoint?.closest?.('.gantt_link_control .gantt_link_point');
      return point && chart.contains(point) ? point : null;
    };

    const findActivePointInDom = function () {
      if (!activeTaskId) return null;
      const escapedTaskId = escapeTypicalServiceTermGanttSelectorValue(activeTaskId);
      const taskSelector = '.gantt_task_line[data-task-id="' + escapedTaskId + '"], .gantt_task_line[task_id="' + escapedTaskId + '"]';
      const propertySelector = activeProperty ? '[data-bind-property="' + activeProperty + '"]' : '';
      return chart.querySelector(taskSelector + ' .gantt_link_control' + propertySelector + ' .gantt_link_point');
    };

    const refreshTargetPoint = function (event) {
      chart.querySelectorAll('.typical-service-term-gantt-link-target-point').forEach(function (point) {
        point.classList.remove('typical-service-term-gantt-link-target-point');
      });
      const point = getPointAtEvent(event);
      if (point && point !== activePoint && chart.contains(point)) {
        point.classList.add('typical-service-term-gantt-link-target-point');
      }
    };

    const findActiveBarInDom = function () {
      if (!activeTaskId) return null;
      const escapedTaskId = escapeTypicalServiceTermGanttSelectorValue(activeTaskId);
      return chart.querySelector('.gantt_task_line[data-task-id="' + escapedTaskId + '"], .gantt_task_line[task_id="' + escapedTaskId + '"]');
    };

    const markActiveSourceBar = function () {
      if (!activeTaskId) return;
      const sideClass = activeProperty === 'start_date'
        ? 'typical-service-term-gantt-link-from-start'
        : 'typical-service-term-gantt-link-from-end';
      chart.querySelectorAll('.typical-service-term-gantt-link-source-bar').forEach(function (bar) {
        bar.classList.remove(
          'typical-service-term-gantt-link-source-bar',
          'typical-service-term-gantt-link-from-start',
          'typical-service-term-gantt-link-from-end',
        );
      });
      const bar = findActiveBarInDom();
      if (bar) {
        bar.classList.add('typical-service-term-gantt-link-source-bar', sideClass);
      }
    };

    const reapplyActivePointState = function () {
      if (!activeTaskId) return;
      let pointForClass = activePoint && document.body.contains(activePoint) ? activePoint : null;
      if (!pointForClass) {
        pointForClass = findActivePointInDom();
        if (pointForClass) activePoint = pointForClass;
      }
      if (pointForClass) pointForClass.classList.add('typical-service-term-gantt-link-source-point');
      markActiveSourceBar();
    };
    chart.$policyTypicalServiceTermReapplyLinkSource = reapplyActivePointState;

    const scheduleRefresh = function (event) {
      if (dragRaf) return;
      dragRaf = requestAnimationFrame(function () {
        dragRaf = 0;
        reapplyActivePointState();
        refreshTargetPoint(event);
      });
    };

    const clearActiveState = function () {
      chart.classList.remove('typical-service-term-gantt-link-dragging');
      activePoint = null;
      activeTaskId = '';
      activeProperty = '';
      delete chart.dataset.linkSourceTaskId;
      delete chart.dataset.linkSourceProperty;
      chart.querySelectorAll('.typical-service-term-gantt-link-source-point').forEach(function (point) {
        point.classList.remove('typical-service-term-gantt-link-source-point');
      });
      chart.querySelectorAll('.typical-service-term-gantt-link-target-point').forEach(function (point) {
        point.classList.remove('typical-service-term-gantt-link-target-point');
      });
      chart.querySelectorAll('.typical-service-term-gantt-link-source-bar').forEach(function (bar) {
        bar.classList.remove(
          'typical-service-term-gantt-link-source-bar',
          'typical-service-term-gantt-link-from-start',
          'typical-service-term-gantt-link-from-end',
        );
      });
      setDirStartOverride(null);
      if (dragMoveHandler) {
        document.removeEventListener('mousemove', dragMoveHandler, true);
        dragMoveHandler = null;
      }
      if (dragRaf) {
        cancelAnimationFrame(dragRaf);
        dragRaf = 0;
      }
    };

    chart.addEventListener('mousedown', function (event) {
      const eventPoint = event.target?.closest?.('.gantt_link_point');
      if (!eventPoint) return;
      const control = eventPoint.closest('.gantt_link_control');
      const taskId = getTypicalServiceTermGanttDomTaskId(eventPoint);
      if (!control || !taskId) return;
      clearActiveState();
      activeTaskId = taskId;
      activeProperty = normalizeFilterValue(control.getAttribute('data-bind-property'));
      chart.classList.add('typical-service-term-gantt-link-dragging');
      chart.dataset.linkSourceTaskId = activeTaskId;
      chart.dataset.linkSourceProperty = activeProperty;
      const livePoint = chart.contains(eventPoint) ? eventPoint : findActivePointInDom();
      if (livePoint) {
        activePoint = livePoint;
        livePoint.classList.add('typical-service-term-gantt-link-source-point');
        const center = computePointCenterRelativeToLinks(livePoint);
        if (center) setDirStartOverride(center);
      }
      markActiveSourceBar();
      reapplyActivePointState();
      requestAnimationFrame(reapplyActivePointState);
      dragMoveHandler = scheduleRefresh;
      document.addEventListener('mousemove', dragMoveHandler, true);
      document.addEventListener('mouseup', clearActiveState, { once: true });
    }, true);
  }

  function bindTypicalServiceTermGanttRowHighlight(gantt, chart) {
    if (!gantt || !chart) return;
    if (chart.dataset.typicalServiceTermGanttRowHighlightBound !== '1') {
      chart.dataset.typicalServiceTermGanttRowHighlightBound = '1';
      chart.addEventListener('mouseover', function (event) {
        setTypicalServiceTermGanttHoveredRow(chart, getTypicalServiceTermGanttDomTaskId(event.target));
      });
      chart.addEventListener('mouseleave', function () {
        setTypicalServiceTermGanttHoveredRow(chart, '');
      });
      const activateRow = function (event) {
        const taskId = getTypicalServiceTermGanttDomTaskId(event.target);
        if (!taskId) return;
        const isLinkPointInteraction = !!event.target?.closest?.('.gantt_link_point');
        if (typeof gantt.selectTask === 'function') {
          if (isLinkPointInteraction && event.type === 'mousedown') {
            selectTypicalServiceTermGanttTaskSilently(gantt, chart, taskId);
          } else {
            gantt.selectTask(taskId);
          }
        }
        setTypicalServiceTermGanttActiveRow(chart, taskId);
        requestAnimationFrame(function () { setTypicalServiceTermGanttActiveRow(chart, taskId); });
        window.setTimeout(function () { setTypicalServiceTermGanttActiveRow(chart, taskId); }, 0);
      };
      chart.addEventListener('mousedown', activateRow, true);
      chart.addEventListener('click', activateRow, true);
    }
    if (!gantt.$policyTypicalServiceTermRowHighlightEventIds) {
      const reapplyActiveRow = function () {
        const currentChart = document.getElementById('typical-service-term-gantt');
        if (currentChart?.dataset.activeTaskId) {
          requestAnimationFrame(function () {
            setTypicalServiceTermGanttActiveRow(currentChart, currentChart.dataset.activeTaskId);
          });
        }
      };
      gantt.$policyTypicalServiceTermRowHighlightEventIds = [
        gantt.attachEvent('onDataRender', function () {
          reapplyActiveRow();
          requestAnimationFrame(function () {
            alignTypicalServiceTermGanttLinkHandles(document.getElementById('typical-service-term-gantt'));
          });
        }),
        gantt.attachEvent('onGanttScroll', function () {
          reapplyActiveRow();
          requestAnimationFrame(function () {
            alignTypicalServiceTermGanttLinkHandles(document.getElementById('typical-service-term-gantt'));
          });
        }),
        gantt.attachEvent('onTaskClick', function (id) {
          if (id !== undefined && id !== null && typeof gantt.selectTask === 'function') {
            gantt.selectTask(id);
          }
          const currentChart = document.getElementById('typical-service-term-gantt');
          setTypicalServiceTermGanttActiveRow(currentChart, id);
          requestAnimationFrame(function () { setTypicalServiceTermGanttActiveRow(currentChart, id); });
          return true;
        }),
      ];
    }
  }

  function clearTypicalServiceTermGanttSelection() {
    const gantt = getTypicalServiceTermGanttInstance();
    const chart = document.getElementById('typical-service-term-gantt');
    setTypicalServiceTermGanttActiveRow(chart, '');
    if (!gantt || typeof gantt.getSelectedId !== 'function' || typeof gantt.unselectTask !== 'function') return;
    const selectedId = gantt.getSelectedId();
    if (selectedId === undefined || selectedId === null || selectedId === '') return;
    gantt.unselectTask(selectedId);
  }

  function bindTypicalServiceTermGanttSelectionReset(root) {
    if (!root) return;
    if (root.$policyTypicalServiceTermGanttSelectionResetBound) return;
    root.$policyTypicalServiceTermGanttSelectionResetBound = true;
    document.addEventListener('click', function (event) {
      const editor = root.querySelector('#typical-service-term-gantt-editor');
      const chart = root.querySelector('#typical-service-term-gantt');
      if (!editor || editor.classList.contains('d-none')) return;
      if (editor.contains(event.target) || chart?.contains(event.target)) return;
      if (event.target?.closest?.('.gantt_cal_light, .gantt_cal_cover, .gantt_modal_box')) return;
      clearTypicalServiceTermGanttSelection();
    });
  }

  function syncTypicalServiceTermGanttScaleButtons(root, scale) {
    qa('.js-typical-service-term-gantt-scale', root).forEach(function (button) {
      const active = button.dataset.scale === scale;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function applyTypicalServiceTermGanttScale(gantt, scale) {
    const monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
    const shortMonthNames = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];
    const formatWeekRange = function (date) {
      const end = addPolicyGanttDays(date, 6);
      if (date.getMonth() === end.getMonth() && date.getFullYear() === end.getFullYear()) {
        return gantt.date.date_to_str('%d')(date) + '-' + gantt.date.date_to_str('%d.%m')(end);
      }
      return gantt.date.date_to_str('%d.%m')(date) + '-' + gantt.date.date_to_str('%d.%m')(end);
    };

    if (scale === 'day') {
      gantt.config.scale_height = 54;
      gantt.config.min_column_width = 36;
      gantt.config.scales = [
        { unit: 'month', step: 1, format: function (date) { return monthNames[date.getMonth()] + ' ' + date.getFullYear(); } },
        { unit: 'day', step: 1, format: '%d' },
      ];
      return;
    }

    if (scale === 'month') {
      gantt.config.scale_height = 54;
      gantt.config.min_column_width = 64;
      gantt.config.scales = [
        { unit: 'year', step: 1, format: '%Y' },
        { unit: 'month', step: 1, format: function (date) { return shortMonthNames[date.getMonth()]; } },
      ];
      return;
    }

    if (scale === 'quarter') {
      gantt.config.scale_height = 54;
      gantt.config.min_column_width = 92;
      gantt.config.scales = [
        { unit: 'year', step: 1, format: '%Y' },
        { unit: 'quarter', step: 1, format: function (date) { return 'Q' + (Math.floor(date.getMonth() / 3) + 1); } },
      ];
      return;
    }

    gantt.config.scale_height = 54;
    gantt.config.min_column_width = 72;
    gantt.config.scales = [
      { unit: 'month', step: 1, format: function (date) { return monthNames[date.getMonth()] + ' ' + date.getFullYear(); } },
      { unit: 'week', step: 1, format: formatWeekRange },
    ];
  }

  function loadTypicalServiceTermGanttAssets() {
    if (window.Gantt || window.gantt) return Promise.resolve(true);
    if (window.__policyTypicalServiceTermGanttAssetsLoading) {
      return window.__policyTypicalServiceTermGanttAssetsLoading;
    }

    const cssHref = '/static/vendor/dhtmlx-gantt/dhtmlxgantt.css?v=9.1.4';
    if (!document.querySelector('link[href*="vendor/dhtmlx-gantt/dhtmlxgantt.css"]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = cssHref;
      document.head.appendChild(link);
    }

    window.__policyTypicalServiceTermGanttAssetsLoading = new Promise(function (resolve) {
      const existingScript = document.querySelector('script[src*="vendor/dhtmlx-gantt/dhtmlxgantt.js"]');
      if (existingScript) {
        existingScript.addEventListener('load', function () { resolve(!!(window.Gantt || window.gantt)); }, { once: true });
        existingScript.addEventListener('error', function () { resolve(false); }, { once: true });
        window.setTimeout(function () { resolve(!!(window.Gantt || window.gantt)); }, 2500);
        return;
      }

      const script = document.createElement('script');
      script.src = '/static/vendor/dhtmlx-gantt/dhtmlxgantt.js?v=9.1.4';
      script.onload = function () { resolve(!!(window.Gantt || window.gantt)); };
      script.onerror = function () { resolve(false); };
      document.head.appendChild(script);
    });
    return window.__policyTypicalServiceTermGanttAssetsLoading;
  }

  function getTypicalServiceTermGanttInstance() {
    if (window.__policyTypicalServiceTermGantt) return window.__policyTypicalServiceTermGantt;
    if (window.Gantt && typeof window.Gantt.getGanttInstance === 'function') {
      window.__policyTypicalServiceTermGantt = window.Gantt.getGanttInstance();
      return window.__policyTypicalServiceTermGantt;
    }
    if (window.gantt && typeof window.gantt.init === 'function') {
      window.__policyTypicalServiceTermGantt = window.gantt;
      return window.__policyTypicalServiceTermGantt;
    }
    return window.__policyTypicalServiceTermGantt;
  }

  function ensureTypicalServiceTermGanttPeriodBlock(gantt) {
    if (!gantt || gantt.$policyTypicalServiceTermPeriodBlockRegistered) return;
    gantt.$policyTypicalServiceTermPeriodBlockRegistered = true;
    const formatDate = gantt.date.date_to_str('%Y-%m-%d');
    const parseDate = gantt.date.str_to_date('%Y-%m-%d');
    const calculateDuration = function (startDate, endDate, task) {
      if (!(startDate instanceof Date) || !(endDate instanceof Date)) return 0;
      if (task?.type === gantt.config.types.milestone) return 0;
      if (typeof gantt.calculateDuration === 'function') {
        return Math.max(0, Math.round(Number(gantt.calculateDuration({
          start_date: startDate,
          end_date: endDate,
          task: task,
        })) || 0));
      }
      return Math.max(0, Math.round((endDate.getTime() - startDate.getTime()) / 86400000));
    };
    const calculateEndDate = function (startDate, duration, task) {
      if (!(startDate instanceof Date)) return null;
      const safeDuration = Math.max(0, Math.round(Number(duration) || 0));
      if (typeof gantt.calculateEndDate === 'function') {
        return gantt.calculateEndDate({ start_date: startDate, duration: safeDuration, task: task });
      }
      const endDate = new Date(startDate);
      endDate.setDate(endDate.getDate() + safeDuration);
      return endDate;
    };
    const calculateStartDate = function (endDate, duration, task) {
      if (!(endDate instanceof Date)) return null;
      const safeDuration = Math.max(0, Math.round(Number(duration) || 0));
      if (typeof gantt.calculateEndDate === 'function') {
        return gantt.calculateEndDate({ start_date: endDate, duration: -safeDuration, task: task });
      }
      const startDate = new Date(endDate);
      startDate.setDate(startDate.getDate() - safeDuration);
      return startDate;
    };
    gantt.form_blocks.policy_period = {
      render: function (section) {
        return '<div class="gantt_cal_ltext gantt_section_' + section.name + ' policy-gantt-period">' +
          '<div class="policy-gantt-period-grid">' +
          '<div class="policy-gantt-period-field">' +
          '<label class="form-label" for="policy-gantt-period-start">Начало' +
          '<i class="bi bi-lock-fill ms-1 policy-gantt-period-lock policy-gantt-period-start-lock d-none" role="button" title="Начало заблокировано"></i>' +
          '</label>' +
          '<input type="date" id="policy-gantt-period-start" class="form-control policy-gantt-period-start">' +
          '</div>' +
          '<div class="policy-gantt-period-field">' +
          '<label class="form-label" for="policy-gantt-period-end">Окончание</label>' +
          '<input type="date" id="policy-gantt-period-end" class="form-control policy-gantt-period-end">' +
          '</div>' +
          '<div class="policy-gantt-period-field">' +
          '<label class="form-label" for="policy-gantt-period-duration">Длительность' +
          '<i class="bi bi-lock-fill ms-1 policy-gantt-period-lock policy-gantt-period-duration-lock" role="button" title="Разблокировать ввод длительности"></i>' +
          '</label>' +
          '<input type="number" id="policy-gantt-period-duration" class="form-control policy-gantt-period-duration readonly-field" min="0" step="1" readonly tabindex="-1">' +
          '</div>' +
          '<div class="policy-gantt-period-field policy-gantt-period-months-field">' +
          '<div class="form-label policy-gantt-period-label-spacer" aria-hidden="true">&nbsp;</div>' +
          '<input type="text" class="form-control policy-gantt-period-duration-months readonly-field" readonly tabindex="-1" aria-label="Длительность в месяцах">' +
          '</div>' +
          '</div>' +
          '</div>';
      },
      set_value: function (node, value, task) {
        const startInput = node.querySelector('.policy-gantt-period-start');
        const endInput = node.querySelector('.policy-gantt-period-end');
        const durationInput = node.querySelector('.policy-gantt-period-duration');
        const durationMonthsInput = node.querySelector('.policy-gantt-period-duration-months');
        const startLock = node.querySelector('.policy-gantt-period-start-lock');
        const durationLock = node.querySelector('.policy-gantt-period-duration-lock');
        if (!startInput || !endInput || !durationInput) return;
        const startDate = task?.start_date instanceof Date ? task.start_date : new Date();
        const endDate = task?.end_date instanceof Date
          ? task.end_date
          : (Number(task?.duration) > 0 && typeof gantt.calculateEndDate === 'function'
            ? gantt.calculateEndDate({ start_date: startDate, duration: Number(task.duration), task: task })
            : startDate);
        startInput.value = formatDate(startDate);
        endInput.value = formatDate(endDate);
        let durationEditMode = false;
        const setReadonly = function (input, locked) {
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
        };
        const syncDurationMonths = function () {
          if (!durationMonthsInput) return;
          const days = Math.max(0, Number(String(durationInput.value || '').replace(',', '.')) || 0);
          const months = days / 30;
          durationMonthsInput.value = months.toFixed(1).replace('.', ',') + ' мес.';
        };
        const applyLockState = function () {
          setReadonly(startInput, durationEditMode);
          setReadonly(durationInput, !durationEditMode);
          if (startLock) {
            startLock.classList.toggle('d-none', !durationEditMode);
            startLock.title = durationEditMode ? 'Начало заблокировано' : '';
          }
          if (durationLock) {
            durationLock.classList.toggle('bi-lock-fill', !durationEditMode);
            durationLock.classList.toggle('bi-unlock-fill', durationEditMode);
            durationLock.title = durationEditMode
              ? 'Заблокировать длительность'
              : 'Разблокировать ввод длительности';
          }
        };
        const syncDuration = function () {
          const nextStart = startInput.value ? parseDate(startInput.value) : startDate;
          const nextEnd = endInput.value ? parseDate(endInput.value) : nextStart;
          durationInput.value = String(calculateDuration(nextStart, nextEnd, task));
          syncDurationMonths();
        };
        const syncEndKeepingDuration = function () {
          if (durationEditMode) return;
          const nextStart = startInput.value ? parseDate(startInput.value) : null;
          if (!nextStart) return;
          const nextEnd = calculateEndDate(nextStart, durationInput.value, task);
          if (nextEnd) endInput.value = formatDate(nextEnd);
          syncDurationMonths();
        };
        const syncStartKeepingDuration = function () {
          if (durationEditMode) {
            syncDuration();
            return;
          }
          const nextEnd = endInput.value ? parseDate(endInput.value) : null;
          if (!nextEnd) return;
          const nextStart = calculateStartDate(nextEnd, durationInput.value, task);
          if (nextStart) startInput.value = formatDate(nextStart);
        };
        const syncEndFromDuration = function () {
          syncDurationMonths();
          if (!durationEditMode) return;
          const nextStart = startInput.value ? parseDate(startInput.value) : startDate;
          if (!nextStart) return;
          const nextEnd = calculateEndDate(nextStart, durationInput.value, task);
          if (nextEnd) endInput.value = formatDate(nextEnd);
        };
        const toggleDurationEditMode = function () {
          durationEditMode = !durationEditMode;
          if (!durationEditMode) {
            syncDuration();
          }
          applyLockState();
          if (durationEditMode) {
            durationInput.focus();
            durationInput.select?.();
          }
        };
        startLock?.addEventListener('click', toggleDurationEditMode);
        durationLock?.addEventListener('click', toggleDurationEditMode);
        startInput.addEventListener('input', syncEndKeepingDuration);
        startInput.addEventListener('change', syncEndKeepingDuration);
        endInput.addEventListener('input', syncStartKeepingDuration);
        endInput.addEventListener('change', syncStartKeepingDuration);
        durationInput.addEventListener('input', syncEndFromDuration);
        durationInput.addEventListener('change', syncEndFromDuration);
        applyLockState();
        syncDuration();
        syncDurationMonths();
      },
      get_value: function (node, task) {
        return task;
      },
      focus: function (node) {
        node.querySelector('.policy-gantt-period-start')?.focus();
      },
    };
  }

  function cleanupTypicalServiceTermGanttLightboxArtifacts() {
    document.querySelectorAll('.gantt_cal_cover').forEach(function (cover) {
      const lightbox = cover.querySelector('.gantt_cal_light');
      if (!lightbox || lightbox.offsetParent === null) {
        cover.remove();
      }
    });
    document.querySelectorAll('.gantt_cal_light').forEach(function (lightbox) {
      if (!document.body.contains(lightbox) || lightbox.offsetParent !== null) return;
      lightbox.remove();
    });
  }

  function findTypicalServiceTermGanttDragColumnsRect(gantt) {
    if (!gantt) return null;
    const grid = typeof gantt.$ui?.getView === 'function' ? gantt.$ui.getView('grid') : null;
    const gridData = grid?.$grid_data || gantt.$grid_data || null;
    const gridScale = grid?.$grid_scale || gantt.$grid_scale || null;
    if (!gridData && !gridScale) return null;
    const firstRow = gridData?.querySelector('.gantt_row');
    const firstCell = firstRow?.querySelector('.gantt_cell:first-child');
    const secondCell = firstRow?.querySelector('.gantt_cell:nth-child(2)');
    let rect;
    if (firstCell && secondCell) {
      const firstRect = firstCell.getBoundingClientRect();
      const secondRect = secondCell.getBoundingClientRect();
      const left = Math.min(firstRect.left, secondRect.left);
      const right = Math.max(firstRect.right, secondRect.right);
      rect = { left: left, width: right - left };
    } else {
      const firstHeadCell = gridScale?.querySelector('.gantt_grid_head_cell:first-child');
      const secondHeadCell = gridScale?.querySelector('.gantt_grid_head_cell:nth-child(2)');
      if (firstHeadCell && secondHeadCell) {
        const firstRect = firstHeadCell.getBoundingClientRect();
        const secondRect = secondHeadCell.getBoundingClientRect();
        const left = Math.min(firstRect.left, secondRect.left);
        const right = Math.max(firstRect.right, secondRect.right);
        rect = { left: left, width: right - left };
      } else if (firstCell || firstHeadCell || gridData || gridScale) {
        const baseRect = (firstCell || firstHeadCell || gridData || gridScale).getBoundingClientRect();
        const columnsWidth = Array.isArray(gantt.config?.columns)
          ? (Number(gantt.config.columns[0]?.width) || 0) + (Number(gantt.config.columns[1]?.width) || 0)
          : 0;
        rect = { left: baseRect.left, width: columnsWidth || baseRect.width };
      } else {
        return null;
      }
    }
    return {
      left: rect.left + (window.scrollX || 0),
      width: rect.width,
    };
  }

  function renderTypicalServiceTermGanttDragPreview(gantt, marker, taskId, dragRect) {
    if (!marker || !taskId) return;
    let task = null;
    try {
      task = typeof gantt?.getTask === 'function' ? gantt.getTask(taskId) : null;
    } catch (_) {
      task = null;
    }
    if (!task) return;
    const wbs = getTypicalServiceTermGanttWbsCode(gantt, task);
    const text = normalizeFilterValue(task.text) || gantt?.locale?.labels?.new_task || 'Новая задача';
    marker.classList.add('typical-service-term-gantt-row-drag-preview');
    if (marker.dataset.policyPreviewTaskId !== String(taskId)) {
      marker.dataset.policyPreviewTaskId = String(taskId);
      marker.innerHTML = '<div class="typical-service-term-gantt-row-drag-preview-content">' +
        '<span class="typical-service-term-gantt-row-drag-preview-wbs">' + escapePolicyHtml(wbs) + '</span>' +
        '<span class="typical-service-term-gantt-row-drag-preview-text">' + escapePolicyHtml(text) + '</span>' +
        '</div>';
    }
    marker.style.width = dragRect.width + 'px';
    marker.style.maxWidth = dragRect.width + 'px';
  }

  function constrainTypicalServiceTermGanttDragMarkers(gantt, taskId) {
    const dragRect = findTypicalServiceTermGanttDragColumnsRect(gantt);
    if (!dragRect || dragRect.width <= 0) return;
    document.querySelectorAll('.gantt_drag_marker.gantt_grid_dnd_marker').forEach(function (marker) {
      marker.style.setProperty('left', dragRect.left + 'px', 'important');
      marker.style.setProperty('width', dragRect.width + 'px', 'important');
      marker.style.setProperty('max-width', dragRect.width + 'px', 'important');
      marker.style.setProperty('overflow', 'visible', 'important');
      const inner = marker.firstElementChild;
      if (inner) {
        inner.style.setProperty('width', '100%', 'important');
        inner.style.setProperty('max-width', '100%', 'important');
      }
    });
    document.querySelectorAll('.gantt_drag_marker:not(.gantt_grid_dnd_marker)').forEach(function (marker) {
      if (marker.querySelector(':scope > .gantt_link_tooltip')) return;
      if (!marker.querySelector('.gantt_row') && !marker.classList.contains('typical-service-term-gantt-row-drag-preview')) return;
      renderTypicalServiceTermGanttDragPreview(gantt, marker, taskId, dragRect);
    });
  }

  function bindTypicalServiceTermGanttRowDragMarkerOverrides(gantt) {
    if (!gantt || gantt._policyTypicalServiceTermRowDragOverridesBound) return;
    gantt._policyTypicalServiceTermRowDragOverridesBound = true;
    const state = {
      dragging: false,
      pageX: 0,
      pageY: 0,
      rafId: 0,
      draggedId: null,
      targetParent: null,
    };
    const PREVIEW_OFFSET_X = 0;
    const PREVIEW_OFFSET_Y = 22;
    const onPointerMove = function (event) {
      state.pageX = event.pageX;
      state.pageY = event.pageY;
    };
    const positionPreview = function () {
      document.querySelectorAll('.gantt_drag_marker:not(.gantt_grid_dnd_marker)').forEach(function (marker) {
        if (marker.querySelector(':scope > .gantt_link_tooltip')) return;
        if (!marker.querySelector('.gantt_row') && !marker.classList.contains('typical-service-term-gantt-row-drag-preview')) return;
        marker.style.left = (state.pageX + PREVIEW_OFFSET_X) + 'px';
        marker.style.top = (state.pageY + PREVIEW_OFFSET_Y) + 'px';
      });
    };
    const isInvalidChildOf = function (draggedId, parentId) {
      if (draggedId === undefined || draggedId === null) return false;
      if (parentId === undefined || parentId === null) return false;
      if (String(parentId) === String(draggedId)) return true;
      if (typeof gantt.getParent !== 'function' || typeof gantt.isTaskExists !== 'function') return false;
      let current = parentId;
      let safety = 0;
      while (current !== undefined && current !== null && safety++ < 1000) {
        if (String(current) === String(draggedId)) return true;
        if (!gantt.isTaskExists(current)) break;
        const parentOfCurrent = gantt.getParent(current);
        if (parentOfCurrent === current) break;
        current = parentOfCurrent;
      }
      return false;
    };
    const applyDenyState = function () {
      const deny = isInvalidChildOf(state.draggedId, state.targetParent);
      document.querySelectorAll('.gantt_drag_marker.gantt_grid_dnd_marker').forEach(function (marker) {
        const isChildMode = !!marker.querySelector('.gantt_grid_dnd_marker_folder');
        marker.classList.toggle('typical-service-term-gantt-row-drag-deny', deny && isChildMode);
      });
    };
    const tick = function () {
      if (!state.dragging) {
        state.rafId = 0;
        return;
      }
      constrainTypicalServiceTermGanttDragMarkers(gantt, state.draggedId);
      positionPreview();
      applyDenyState();
      state.rafId = requestAnimationFrame(tick);
    };
    if (typeof gantt.attachEvent === 'function') {
      gantt.attachEvent('onRowDragStart', function (id, target, event) {
        if (event && typeof event.pageX === 'number') {
          state.pageX = event.pageX;
          state.pageY = event.pageY;
        }
        state.dragging = true;
        state.draggedId = id;
        state.targetParent = null;
        document.body.classList.add('typical-service-term-gantt-row-dragging');
        document.addEventListener('mousemove', onPointerMove, true);
        if (!state.rafId) state.rafId = requestAnimationFrame(tick);
        return true;
      });
      gantt.attachEvent('onRowDragMove', function (id, parent) {
        state.draggedId = id;
        state.targetParent = parent;
        return true;
      });
      gantt.attachEvent('onRowDragEnd', function () {
        state.dragging = false;
        state.draggedId = null;
        state.targetParent = null;
        document.body.classList.remove('typical-service-term-gantt-row-dragging');
        document.removeEventListener('mousemove', onPointerMove, true);
        if (state.rafId) {
          cancelAnimationFrame(state.rafId);
          state.rafId = 0;
        }
        return true;
      });
    }
  }

  function getTypicalServiceTermGanttLinkSides(gantt, link) {
    const types = gantt?.config?.links || { finish_to_start: '0', start_to_start: '1', finish_to_finish: '2', start_to_finish: '3' };
    const linkType = link?.type;
    let fromStart = false;
    let toStart = false;
    if (linkType === types.start_to_start || String(linkType) === String(types.start_to_start)) {
      fromStart = true;
      toStart = true;
    } else if (linkType === types.finish_to_finish || String(linkType) === String(types.finish_to_finish)) {
      fromStart = false;
      toStart = false;
    } else if (linkType === types.start_to_finish || String(linkType) === String(types.start_to_finish)) {
      fromStart = true;
      toStart = false;
    } else {
      fromStart = false;
      toStart = true;
    }
    return { fromStart: fromStart, toStart: toStart };
  }

  function alignTypicalServiceTermGanttMilestoneLinks(gantt, chart) {
    if (!gantt || !chart || typeof gantt.posFromDate !== 'function') return;
    const isWeekScale = chart.classList.contains('typical-service-term-gantt-scale-week');
    const DIAMOND_HALF = isWeekScale ? 4 : 6;
    const arrowSize = (gantt.config && gantt.config.link_arrow_size) || 12;
    const linkNodes = chart.querySelectorAll(
      '.gantt_task_link.typical-service-term-gantt-link-from-milestone, .gantt_task_link.typical-service-term-gantt-link-to-milestone'
    );
    linkNodes.forEach(function (node) {
      const linkId = node.getAttribute('link_id') || node.getAttribute('data-link-id');
      if (!linkId) return;
      let link;
      try {
        link = gantt.getLink(linkId);
      } catch (_) {
        return;
      }
      if (!link) return;
      let src;
      let tgt;
      try {
        src = gantt.getTask(link.source);
        tgt = gantt.getTask(link.target);
      } catch (_) {
        return;
      }
      if (!src || !tgt) return;
      const srcIsMilestone = src.type === 'milestone';
      const tgtIsMilestone = tgt.type === 'milestone';
      if (!srcIsMilestone && !tgtIsMilestone) return;

      const sides = getTypicalServiceTermGanttLinkSides(gantt, link);
      const srcDate = sides.fromStart ? src.start_date : src.end_date;
      const tgtDate = sides.toStart ? tgt.start_date : tgt.end_date;
      const srcRefDate = srcDate || src.start_date;
      const tgtRefDate = tgtDate || tgt.start_date;
      if (!srcRefDate || !tgtRefDate) return;

      const srcCenter = gantt.posFromDate(srcRefDate);
      const tgtCenter = gantt.posFromDate(tgtRefDate);
      const srcEdge = srcIsMilestone ? srcCenter + (sides.fromStart ? -DIAMOND_HALF : DIAMOND_HALF) : null;
      const tgtEdge = tgtIsMilestone ? tgtCenter + (sides.toStart ? -DIAMOND_HALF : DIAMOND_HALF) : null;

      const wrappers = Array.from(node.querySelectorAll('.gantt_line_wrapper'));
      if (!wrappers.length) return;
      const horizontalWrappers = wrappers.filter(function (w) {
        const inner = w.firstElementChild;
        return inner && (inner.style.height === '2px' || parseInt(inner.style.height, 10) <= 2);
      });
      if (!horizontalWrappers.length) return;

      const arrow = node.querySelector('.gantt_link_arrow');
      const isArrowRight = arrow && arrow.classList.contains('gantt_link_arrow_right');
      const isArrowLeft = arrow && arrow.classList.contains('gantt_link_arrow_left');

      if (tgtIsMilestone && arrow && tgtEdge !== null) {
        const currentLeft = parseFloat(arrow.style.left) || 0;
        let desiredLeft = currentLeft;
        if (isArrowRight) {
          desiredLeft = tgtEdge - arrowSize;
        } else if (isArrowLeft) {
          // dhtmlx для direction=left делает arrowX -= 2 и arrowY -= 1 — компенсируем
          // оба сдвига, чтобы тик стрелки попадал точно в правую грань ромба
          desiredLeft = tgtEdge + 2;
          if (arrow.dataset.policyMilestoneTopAdjusted !== '1') {
            const currentTop = parseFloat(arrow.style.top) || 0;
            arrow.style.top = (currentTop + 1) + 'px';
            arrow.dataset.policyMilestoneTopAdjusted = '1';
          }
        }
        if (Number.isFinite(desiredLeft) && Math.abs(desiredLeft - currentLeft) >= 0.5) {
          const dx = desiredLeft - currentLeft;
          arrow.style.left = desiredLeft + 'px';
          // путь рендерится в порядке source→target, поэтому горизонтальная
          // секция, соединяющаяся со стрелкой, всегда последняя в DOM
          const targetWrapper = horizontalWrappers[horizontalWrappers.length - 1];
          if (targetWrapper) {
            const wrapperLeft = parseFloat(targetWrapper.style.left) || 0;
            const wrapperWidth = parseFloat(targetWrapper.style.width) || 0;
            const inner = targetWrapper.firstElementChild;
            const innerWidth = inner ? (parseFloat(inner.style.width) || 0) : 0;
            if (isArrowRight) {
              const newWidth = Math.max(0, wrapperWidth + dx);
              targetWrapper.style.width = newWidth + 'px';
              if (inner) inner.style.width = Math.max(0, innerWidth + dx) + 'px';
            } else {
              const newLeft = wrapperLeft + dx;
              const newWidth = Math.max(0, wrapperWidth - dx);
              targetWrapper.style.left = newLeft + 'px';
              targetWrapper.style.width = newWidth + 'px';
              if (inner) inner.style.width = Math.max(0, innerWidth - dx) + 'px';
            }
          }
        }
      }

      if (srcIsMilestone && srcEdge !== null) {
        // первая горизонтальная секция всегда соединяется с источником
        const sourceWrapper = horizontalWrappers[0];
        if (sourceWrapper) {
          const wrapperLeft = parseFloat(sourceWrapper.style.left) || 0;
          const wrapperWidth = parseFloat(sourceWrapper.style.width) || 0;
          const inner = sourceWrapper.firstElementChild;
          const innerWidth = inner ? (parseFloat(inner.style.width) || 0) : 0;
          if (isArrowRight) {
            const dx = srcEdge - wrapperLeft;
            const newLeft = srcEdge;
            const newWidth = Math.max(0, wrapperWidth - dx);
            if (Math.abs(dx) >= 0.5) {
              sourceWrapper.style.left = newLeft + 'px';
              sourceWrapper.style.width = newWidth + 'px';
              if (inner) inner.style.width = Math.max(0, innerWidth - dx) + 'px';
            }
          } else {
            const wrapperRight = wrapperLeft + wrapperWidth;
            const dx = srcEdge - wrapperRight;
            const newWidth = Math.max(0, wrapperWidth + dx);
            if (Math.abs(dx) >= 0.5) {
              sourceWrapper.style.width = newWidth + 'px';
              if (inner) inner.style.width = Math.max(0, innerWidth + dx) + 'px';
            }
          }
        }
      }
    });
  }

  function bindTypicalServiceTermGanttMilestoneLinkAlign(gantt, chart) {
    if (!gantt || !chart || gantt._policyTypicalServiceTermMilestoneLinksBound) return;
    gantt._policyTypicalServiceTermMilestoneLinksBound = true;
    const apply = function () {
      requestAnimationFrame(function () {
        alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
      });
    };
    if (typeof gantt.attachEvent === 'function') {
      gantt.attachEvent('onDataRender', apply);
      gantt.attachEvent('onGanttScroll', apply);
      gantt.attachEvent('onAfterTaskUpdate', apply);
      gantt.attachEvent('onAfterLinkAdd', apply);
      gantt.attachEvent('onAfterLinkUpdate', apply);
      gantt.attachEvent('onAfterLinkDelete', apply);
      gantt.attachEvent('onTaskDrag', apply);
      gantt.attachEvent('onAfterTaskDrag', apply);
      gantt.attachEvent('onAfterTaskMove', apply);
      gantt.attachEvent('onRowDragEnd', apply);
    }
  }

  function configureTypicalServiceTermGantt(root) {
    const gantt = getTypicalServiceTermGanttInstance();
    if (!gantt) return null;
    ensureTypicalServiceTermGanttPeriodBlock(gantt);
    const scale = getTypicalServiceTermGanttScale(root);
    syncTypicalServiceTermGanttScaleButtons(root, scale);

    gantt.config.readonly = false;
    gantt.config.date_format = '%Y-%m-%d';
    gantt.config.fit_tasks = true;
    gantt.config.autosize = 'y';
    gantt.config.row_height = 34;
    gantt.config.bar_height = 20;
    gantt.config.grid_resize = true;
    gantt.config.keep_grid_width = false;
    gantt.config.layout = {
      css: 'gantt_container',
      rows: [
        {
          cols: [
            { view: 'grid', scrollY: 'scrollVer' },
            { resizer: true, width: 7 },
            { view: 'timeline', scrollX: 'scrollHor', scrollY: 'scrollVer' },
            { view: 'scrollbar', id: 'scrollVer' },
          ],
        },
        { view: 'scrollbar', id: 'scrollHor', height: 20 },
      ],
    };
    gantt.config.drag_links = true;
    gantt.config.drag_move = true;
    gantt.config.drag_resize = true;
    gantt.config.drag_progress = true;
    gantt.config.order_branch = 'marker';
    gantt.config.order_branch_free = true;
    gantt.config.select_task = true;
    gantt.config.details_on_dblclick = true;
    const formatGridDate = gantt.date.date_to_str('%d.%m.%y');
    gantt.config.columns = [
      typicalServiceTermGanttColumn('wbs', 92, {
        label: '№',
        align: 'center',
        min_width: 76,
        max_width: 120,
        template: function (task) {
          return typicalServiceTermGanttGridValueHtml(
            getTypicalServiceTermGanttWbsCode(gantt, task),
            'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--wbs'
          );
        },
      }),
      typicalServiceTermGanttColumn('text', 300, { label: 'Задача', tree: true, align: 'left', min_width: 160 }),
      typicalServiceTermGanttColumn('start_date', 92, {
        label: 'Начало',
        align: 'center',
        min_width: 76,
        template: function (task) {
          return task.start_date instanceof Date ? formatGridDate(task.start_date) : '';
        },
      }),
      typicalServiceTermGanttColumn('end_date', 92, {
        label: 'Оконч.',
        align: 'center',
        min_width: 76,
        template: function (task) {
          return task.end_date instanceof Date ? formatGridDate(task.end_date) : '';
        },
      }),
      typicalServiceTermGanttColumn('duration', 64, {
        label: 'Длит.',
        align: 'center',
        min_width: 54,
        template: formatTypicalServiceTermGanttDuration,
      }),
      typicalServiceTermGanttColumn('predecessors', 92, {
        label: 'Предш.',
        align: 'center',
        min_width: 72,
        template: function (task) {
          return typicalServiceTermGanttGridValueHtml(
            formatTypicalServiceTermGanttPredecessors(gantt, task),
            'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--predecessors'
          );
        },
      }),
      typicalServiceTermGanttColumn('progress', 72, {
        label: 'Прогр.',
        align: 'center',
        min_width: 64,
        template: formatTypicalServiceTermGanttProgress,
      }),
      typicalServiceTermGanttColumn('add', 44, { label: '', min_width: 44, max_width: 72 }),
    ];
    gantt.config.grid_width = Math.max(getTypicalServiceTermGanttGridWidth(), getTypicalServiceTermGanttColumnsWidth(gantt));
    gantt.locale.labels.section_description = 'Описание';
    gantt.locale.labels.section_type = 'Тип';
    gantt.locale.labels.section_period = 'Начало';
    gantt.locale.labels.new_task = 'Новая задача';
    gantt.locale.labels.type_task = 'Задача';
    gantt.locale.labels.type_project = 'Проект';
    gantt.locale.labels.type_milestone = 'Веха';
    gantt.locale.labels.gantt_save_btn = 'Сохранить';
    gantt.locale.labels.gantt_cancel_btn = 'Отмена';
    gantt.locale.labels.gantt_delete_btn = 'Удалить';
    gantt.config.lightbox.sections = [
      { name: 'description', height: 70, map_to: 'text', type: 'textarea', focus: true },
      {
        name: 'type',
        type: 'select',
        map_to: 'type',
        options: [
          { key: gantt.config.types.task, label: 'Задача' },
          { key: gantt.config.types.project, label: 'Проект' },
          { key: gantt.config.types.milestone, label: 'Веха' },
        ],
      },
      {
        name: 'period',
        type: 'policy_period',
        map_to: 'auto',
      },
    ];
    if (!gantt.$policyTypicalServiceTermLightboxEventsBound) {
      gantt.$policyTypicalServiceTermLightboxEventsBound = true;
      gantt.attachEvent('onLightboxSave', function (id, task) {
        const lightbox = typeof gantt.getLightbox === 'function' ? gantt.getLightbox() : null;
        const startValue = lightbox?.querySelector('.policy-gantt-period-start')?.value;
        const endValue = lightbox?.querySelector('.policy-gantt-period-end')?.value;
        const parseDate = gantt.date.str_to_date('%Y-%m-%d');
        if (startValue) task.start_date = parseDate(startValue);
        if (endValue) task.end_date = parseDate(endValue);
        if (task.type === gantt.config.types.milestone) {
          task.duration = 0;
          if (task.start_date instanceof Date) {
            task.end_date = new Date(task.start_date.getFullYear(), task.start_date.getMonth(), task.start_date.getDate());
          }
        } else if (task.start_date instanceof Date && task.end_date instanceof Date && typeof gantt.calculateDuration === 'function') {
          task.duration = Math.max(0, Math.round(Number(gantt.calculateDuration({
            start_date: task.start_date,
            end_date: task.end_date,
            task: task,
          })) || 0));
        }
        return true;
      });
      gantt.attachEvent('onAfterLightbox', function () {
        cleanupTypicalServiceTermGanttLightboxArtifacts();
        return true;
      });
      gantt.attachEvent('onTaskDblClick', function (id) {
        if (typeof gantt.showLightbox === 'function') {
          gantt.showLightbox(id);
        }
        return false;
      });
    }
    if (!gantt.$policyTypicalServiceTermResizeEventsBound) {
      gantt.$policyTypicalServiceTermResizeEventsBound = true;
      gantt.attachEvent('onGridResizeEnd', function (oldWidth, newWidth) {
        if (P && Number.isFinite(Number(newWidth))) {
          P.set(TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY, Math.round(Number(newWidth)));
        }
        return true;
      });
      gantt.attachEvent('onColumnResizeEnd', function () {
        saveTypicalServiceTermGanttColumns(gantt);
        return true;
      });
    }
    applyTypicalServiceTermGanttScale(gantt, scale);
    gantt.templates.task_class = function (start, end, task) {
      if (task.type === 'milestone') return 'typical-service-term-gantt-milestone';
      if (task.system_key === 'preliminary_report' || task.system_key === 'final_report' || task.is_report_bar) {
        return 'typical-service-term-gantt-report-bar';
      }
      return '';
    };
    gantt.templates.link_direction_class = function (from, from_start, to, to_start) {
      let cls = 'typical-service-term-gantt-link-direction';
      if (to !== undefined && to !== null && from !== undefined && from !== null) {
        try {
          const allowed = typeof gantt.isLinkAllowed === 'function'
            ? gantt.isLinkAllowed(from, to, from_start, to_start)
            : true;
          if (!allowed) cls += ' typical-service-term-gantt-link-direction-deny';
        } catch (e) { /* keep default class */ }
      }
      return cls;
    };
    gantt.templates.task_text = function (start, end, task) {
      if (start instanceof Date && end instanceof Date) {
        const diffDays = (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24);
        if (diffDays < 5) return '';
      } else if (typeof task?.duration === 'number' && task.duration < 5) {
        return '';
      }
      return escapePolicyHtml(task.text || '');
    };
    gantt.templates.link_class = function (link) {
      try {
        const src = typeof gantt.getTask === 'function' && link?.source !== undefined ? gantt.getTask(link.source) : null;
        const tgt = typeof gantt.getTask === 'function' && link?.target !== undefined ? gantt.getTask(link.target) : null;
        return [
          src?.type === 'milestone' ? 'typical-service-term-gantt-link-from-milestone' : '',
          tgt?.type === 'milestone' ? 'typical-service-term-gantt-link-to-milestone' : '',
        ].filter(Boolean).join(' ');
      } catch (_) {
        return '';
      }
    };
    gantt.templates.drag_link = function (from, fromStart, to, toStart) {
      const fromTask = typeof gantt.getTask === 'function' && from !== undefined && from !== null ? gantt.getTask(from) : null;
      const toTask = typeof gantt.getTask === 'function' && to !== undefined && to !== null ? gantt.getTask(to) : null;
      let html = '';
      if (fromTask) {
        html += '<div>' + escapePolicyHtml(fromTask.text || '') + ' <span class="text-muted">(' + (fromStart ? 'начало' : 'окончание') + ')</span></div>';
      }
      if (toTask) {
        html += '<div>' + escapePolicyHtml(toTask.text || '') + ' <span class="text-muted">(' + (toStart ? 'начало' : 'окончание') + ')</span></div>';
      }
      return html;
    };
    bindTypicalServiceTermGanttRowDragMarkerOverrides(gantt);
    if (typeof gantt._delete_link_confirm === 'function' && !gantt._policyTypicalServiceTermLinkConfirmPatched) {
      gantt._policyTypicalServiceTermLinkConfirmPatched = true;
      gantt._delete_link_confirm = function (params) {
        const linkObj = params?.link;
        const fromTask = linkObj && typeof gantt.getTask === 'function' ? gantt.getTask(linkObj.source) : null;
        const toTask = linkObj && typeof gantt.getTask === 'function' ? gantt.getTask(linkObj.target) : null;
        const fromText = fromTask ? escapePolicyHtml(fromTask.text || '') : '';
        const toText = toTask ? escapePolicyHtml(toTask.text || '') : '';
        const message = 'Связь <b>' + fromText + '</b> &mdash; <b>' + toText + '</b> будет удалена.';
        gantt.confirm({
          text: message,
          ok: 'Удалить',
          cancel: 'Отмена',
          callback: function (result) {
            if (result && params && typeof params.callback === 'function') params.callback();
          },
        });
      };
    }
    return gantt;
  }

  function showTypicalServiceTermGanttMessage(root, text, isError) {
    const message = root?.querySelector('#typical-service-term-gantt-message');
    if (!message) return;
    message.textContent = text || '';
    message.classList.toggle('d-none', !text);
    message.classList.toggle('text-danger', !!isError);
    message.classList.toggle('text-muted', !isError);
  }

  function normalizeTypicalServiceTermGanttDates(ganttData) {
    const data = Array.isArray(ganttData?.data) ? ganttData.data : [];
    data.forEach(function (task) {
      const start = parsePolicyGanttDate(task.start_date);
      const end = parsePolicyGanttDate(task.end_date);
      if (start) task.start_date = start;
      if (end) task.end_date = end;
    });
    return {
      data: data,
      links: Array.isArray(ganttData?.links) ? ganttData.links : [],
      meta: ganttData?.meta && typeof ganttData.meta === 'object' ? ganttData.meta : {},
    };
  }

  function renderTypicalServiceTermGantt(root, payload, context) {
    const editor = root?.querySelector('#typical-service-term-gantt-editor');
    const chart = root?.querySelector('#typical-service-term-gantt');
    const subtitle = root?.querySelector('#typical-service-term-gantt-subtitle');
    if (!editor || !chart) return;

    const gantt = configureTypicalServiceTermGantt(root);
    if (!gantt) {
      showTypicalServiceTermGanttMessage(root, 'DHTMLX Gantt не загружен.', true);
      return;
    }

    const ganttData = normalizeTypicalServiceTermGanttDates(payload?.gantt || {});
    editor.dataset.currentTermId = normalizeFilterValue(context?.termId);
    editor.dataset.currentGanttUrl = normalizeFilterValue(context?.ganttUrl);
    editor._typicalServiceTermGanttMeta = ganttData.meta || {};
    if (subtitle) {
      subtitle.textContent = context?.productLabel
        ? 'Продукт: ' + context.productLabel
        : 'Редактирование типового срока оказания услуг.';
    }
    editor.classList.remove('d-none');
    showTypicalServiceTermGanttMessage(root, '', false);
    chart.classList.toggle('typical-service-term-gantt-scale-day', getTypicalServiceTermGanttScale(root) === 'day');
    chart.classList.toggle('typical-service-term-gantt-scale-week', getTypicalServiceTermGanttScale(root) === 'week');
    chart.classList.toggle('typical-service-term-gantt-scale-month', getTypicalServiceTermGanttScale(root) === 'month');
    chart.classList.toggle('typical-service-term-gantt-scale-quarter', getTypicalServiceTermGanttScale(root) === 'quarter');
    gantt.init(chart);
    gantt.clearAll();
    gantt.parse({ data: ganttData.data, links: ganttData.links });
    gantt.render();
    installTypicalServiceTermGanttColumnResizeHandles(gantt, chart);
    installTypicalServiceTermGanttLightboxDblClick(gantt, chart);
    bindTypicalServiceTermGanttLinkSourceState(gantt, chart);
    bindTypicalServiceTermGanttRowHighlight(gantt, chart);
    bindTypicalServiceTermGanttMilestoneLinkAlign(gantt, chart);
    requestAnimationFrame(function () {
      alignTypicalServiceTermGanttLinkHandles(chart);
      alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
    });
  }

  async function openTypicalServiceTermGanttEditor(button) {
    const root = pane();
    if (!root || !button || button.disabled) return;
    const ganttUrl = normalizeFilterValue(button.dataset.ganttUrl);
    if (!ganttUrl) return;
    const editor = root.querySelector('#typical-service-term-gantt-editor');
    if (editor) editor.classList.remove('d-none');
    showTypicalServiceTermGanttMessage(root, 'Загрузка диаграммы…', false);
    try {
      const assetsLoaded = await loadTypicalServiceTermGanttAssets();
      if (!assetsLoaded) throw new Error('DHTMLX Gantt не загружен.');
      const response = await fetch(ganttUrl, { headers: { 'Accept': 'application/json' } });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || 'Не удалось загрузить диаграмму.');
      renderTypicalServiceTermGantt(root, payload, {
        ganttUrl: ganttUrl,
        termId: button.dataset.termId,
        productLabel: button.dataset.productLabel,
      });
      editor?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      showTypicalServiceTermGanttMessage(root, error.message || 'Не удалось загрузить диаграмму.', true);
    }
  }

  function serializeTypicalServiceTermGantt(root) {
    const gantt = getTypicalServiceTermGanttInstance();
    if (!gantt) return null;
    const editor = root.querySelector('#typical-service-term-gantt-editor');
    const formatDate = gantt.date.date_to_str('%Y-%m-%d');
    const tasks = [];
    gantt.eachTask(function (task) {
      const item = {};
      Object.keys(task).forEach(function (key) {
        if (key.charAt(0) === '$' || typeof task[key] === 'function') return;
        if (task[key] instanceof Date) {
          item[key] = formatDate(task[key]);
        } else {
          item[key] = task[key];
        }
      });
      if (task.start_date) item.start_date = formatDate(task.start_date);
      if (task.end_date) item.end_date = formatDate(task.end_date);
      tasks.push(item);
    });
    const links = typeof gantt.getLinks === 'function' ? gantt.getLinks().map(function (link) {
      const item = {};
      Object.keys(link).forEach(function (key) {
        if (key.charAt(0) === '$' || typeof link[key] === 'function') return;
        item[key] = link[key];
      });
      return item;
    }) : [];
    const meta = Object.assign({}, editor?._typicalServiceTermGanttMeta || {});
    if (!meta.base_date && tasks.length) {
      meta.base_date = tasks
        .map(function (task) { return normalizeFilterValue(task.start_date); })
        .filter(Boolean)
        .sort()[0] || '';
    }
    return { data: tasks, links: links, meta: meta };
  }

  async function saveTypicalServiceTermGantt() {
    const root = pane();
    if (!root) return;
    const editor = root.querySelector('#typical-service-term-gantt-editor');
    const saveButton = root.querySelector('#typical-service-term-gantt-save-btn');
    const ganttUrl = normalizeFilterValue(editor?.dataset?.currentGanttUrl);
    if (!editor || !ganttUrl) return;
    const payload = serializeTypicalServiceTermGantt(root);
    if (!payload) {
      showTypicalServiceTermGanttMessage(root, 'DHTMLX Gantt не загружен.', true);
      return;
    }
    saveButton.disabled = true;
    showTypicalServiceTermGanttMessage(root, 'Сохранение диаграммы…', false);
    try {
      const response = await fetch(ganttUrl, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'X-CSRFToken': csrftoken,
        },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Не удалось сохранить диаграмму.');
      window.__tableSel[TYPICAL_SERVICE_TERM_GANTT_SELECTION_NAME] = [];
      if (window.__tableSelLast === TYPICAL_SERVICE_TERM_GANTT_SELECTION_NAME) {
        window.__tableSelLast = null;
      }
      rememberPolicyScrollPosition();
      await htmx.ajax('GET', '/policy/policy/partial/', { target: '#policy-pane', swap: 'outerHTML' });
    } catch (error) {
      showTypicalServiceTermGanttMessage(root, error.message || 'Не удалось сохранить диаграмму.', true);
      saveButton.disabled = false;
    }
  }

  function cancelTypicalServiceTermGantt() {
    const root = pane();
    if (!root) return;
    const editor = root.querySelector('#typical-service-term-gantt-editor');
    const saveButton = root.querySelector('#typical-service-term-gantt-save-btn');
    const gantt = getTypicalServiceTermGanttInstance();
    if (gantt && typeof gantt.hideLightbox === 'function') {
      gantt.hideLightbox();
    }
    cleanupTypicalServiceTermGanttLightboxArtifacts();
    if (gantt && typeof gantt.clearAll === 'function') {
      gantt.clearAll();
    }
    if (editor) {
      editor.classList.add('d-none');
      editor.dataset.currentTermId = '';
      editor.dataset.currentGanttUrl = '';
      editor._typicalServiceTermGanttMeta = {};
    }
    if (saveButton) saveButton.disabled = false;
    showTypicalServiceTermGanttMessage(root, '', false);
    window.__tableSel[TYPICAL_SERVICE_TERM_GANTT_SELECTION_NAME] = [];
    if (window.__tableSelLast === TYPICAL_SERVICE_TERM_GANTT_SELECTION_NAME) {
      window.__tableSelLast = null;
    }
    getRowChecksByName(TYPICAL_SERVICE_TERM_GANTT_SELECTION_NAME).forEach(function (box) {
      if (box.checked) {
        box.checked = false;
        box.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    syncTypicalServiceTermGanttEditButton();
  }

  function hideTypicalServiceTermGanttLightbox() {
    const gantt = getTypicalServiceTermGanttInstance();
    if (gantt && typeof gantt.hideLightbox === 'function') {
      gantt.hideLightbox();
    }
    cleanupTypicalServiceTermGanttLightboxArtifacts();
  }

  function initTypicalServiceTermGanttEditor(root) {
    syncTypicalServiceTermGanttEditButton();
    syncTypicalServiceTermGanttScaleButtons(root, getTypicalServiceTermGanttScale(root));
    bindTypicalServiceTermGanttSelectionReset(root);
    qa('.js-typical-service-term-gantt-scale', root).forEach(function (button) {
      if (button.dataset.bound === '1') return;
      button.dataset.bound = '1';
      button.addEventListener('click', function () {
        const scale = button.dataset.scale || TYPICAL_SERVICE_TERM_GANTT_DEFAULT_SCALE;
        if (P) P.set(TYPICAL_SERVICE_TERM_GANTT_SCALE_PREF_KEY, scale);
        syncTypicalServiceTermGanttScaleButtons(root, scale);
        const gantt = getTypicalServiceTermGanttInstance();
        const editor = root.querySelector('#typical-service-term-gantt-editor');
        if (gantt && editor && !editor.classList.contains('d-none')) {
          configureTypicalServiceTermGantt(root);
          const chart = root.querySelector('#typical-service-term-gantt');
          if (chart) {
            chart.classList.toggle('typical-service-term-gantt-scale-day', scale === 'day');
            chart.classList.toggle('typical-service-term-gantt-scale-week', scale === 'week');
            chart.classList.toggle('typical-service-term-gantt-scale-month', scale === 'month');
            chart.classList.toggle('typical-service-term-gantt-scale-quarter', scale === 'quarter');
          }
          gantt.render();
          installTypicalServiceTermGanttColumnResizeHandles(gantt, chart);
          requestAnimationFrame(function () {
            alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
            requestAnimationFrame(function () {
              alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
            });
          });
        }
      });
    });
    const saveButton = root.querySelector('#typical-service-term-gantt-save-btn');
    if (saveButton && saveButton.dataset.bound !== '1') {
      saveButton.dataset.bound = '1';
      saveButton.addEventListener('click', saveTypicalServiceTermGantt);
    }
    const cancelButton = root.querySelector('#typical-service-term-gantt-cancel-btn');
    if (cancelButton && cancelButton.dataset.bound !== '1') {
      cancelButton.dataset.bound = '1';
      cancelButton.addEventListener('click', cancelTypicalServiceTermGantt);
    }
    if (!window.__policyTypicalServiceTermGanttEscapeBound) {
      window.__policyTypicalServiceTermGanttEscapeBound = true;
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
          hideTypicalServiceTermGanttLightbox();
        }
      });
    }
  }

  function rememberPolicyScrollPosition() {
    window.__policyScrollRestoreY = window.scrollY || window.pageYOffset || 0;
  }

  // Делегирование: клики по кнопкам панелей
  document.addEventListener('click', async (e) => {
    const root = pane();
    if (!root) return;
    const wrapToggle = e.target.closest('#typical-service-compositions-wrap-toggle');
    if (wrapToggle && root.contains(wrapToggle)) {
      const table = document.getElementById('typical-service-compositions-table');
      if (!table) return;
      table.classList.toggle('clf-truncated');
      const active = table.classList.contains('clf-truncated');
      wrapToggle.classList.toggle('active', active);
      window.__policyTypicalServiceCompositionWrapActive = active;
      if (P) P.set('policy:typicalServiceCompositionWrapActive', active);
      return;
    }
    const specialtyToggle = e.target.closest('#specialty-tariffs-specialties-toggle');
    if (specialtyToggle && root.contains(specialtyToggle)) {
      window.__policySpecialtyTariffsSpecialtiesCollapsed = !window.__policySpecialtyTariffsSpecialtiesCollapsed;
      collapseSpecialtyTariffsSpecialties();
      if (P) P.set('policy:specialtyTariffsSpecialtiesCollapsed', !!window.__policySpecialtyTariffsSpecialtiesCollapsed);
      return;
    }
    const ganttEditButton = e.target.closest('[data-typical-service-term-gantt-edit]');
    if (ganttEditButton && root.contains(ganttEditButton)) {
      e.preventDefault();
      openTypicalServiceTermGanttEditor(ganttEditButton);
      return;
    }
    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;
    e.preventDefault();
    const panel = btn.closest('div[id$="-actions"]');
    if (!panel) return;
    const action = btn.dataset.panelAction; // "up" | "down" | "edit" | "delete"
    const name = getNameForPanel(panel);
    if (!name) return;

    const checked = getCheckedByName(name);
    if (!checked.length) return;

    // сохраняем выбор ТОЛЬКО для текущей таблицы
    window.__tableSel[name] = checked.map(ch => String(ch.value));
    window.__tableSelLast = name;

    if (action === 'edit') {
      const first = checked[0];
      const tr = first.closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;
      await htmx.ajax('GET', url, { target: '#policy-modal .modal-content', swap: 'innerHTML' });
      // На случай если модалка не перерисовывает pane — поддержим видимость панели
      ensureActionsVisibility(name);
      return;
    }

    if (action === 'delete') {
      if (!confirm(`Удалить ${checked.length} строк(у/и)?`)) return;
      btn.blur();
      rememberPolicyScrollPosition();
      const urls = checked.map(ch => ch.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#policy-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      return;
    }

    if (action === 'up' || action === 'down') {
      btn.blur();
      rememberPolicyScrollPosition();
      let urls = checked
        .map(ch => ch.closest('tr')?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'])
        .filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#policy-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      // Пока ждём перерисовку, не прячем панель (на случай без перерисовки)
      ensureActionsVisibility(name);
      return;
    }
  });

  // Делегирование: мастер-чекбокс
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
    syncTypicalServiceTermGanttEditButton();
  });

  // Делегирование: чекбоксы строк
  document.addEventListener('change', (e) => {
    const root = pane();
    if (!root) return;
    const rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (!rowCb || !root.contains(rowCb)) return;
    const name = rowCb.name;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
    syncTypicalServiceTermGanttEditButton();
  });

  document.body.addEventListener('htmx:configRequest', function (e) {
    const root = pane();
    const elt = e.detail?.elt;
    if (!root || !elt || !root.contains(elt)) return;
    const hxGet = normalizeFilterValue(elt.getAttribute('hx-get'));
    if (!hxGet) return;
    const prefillCreateUrls = [
      '/policy/policy/product/create/',
      '/policy/policy/section/create/',
      '/policy/policy/structure/create/',
      '/policy/policy/service-goal-report/create/',
      '/policy/policy/typical-service-composition/create/',
      '/policy/policy/typical-service-term/create/',
      '/policy/policy/tariff/create/',
    ];
    if (!prefillCreateUrls.some(function (url) { return hxGet.indexOf(url) !== -1; })) return;
    const product = getSelectedPolicyMasterProduct();
    if (!product) return;
    e.detail.parameters = e.detail.parameters || {};
    e.detail.parameters.product = product.id;
    e.detail.parameters.consulting_type_ref = product.consultingRef;
    e.detail.parameters.service_category_ref = product.categoryRef;
    e.detail.parameters.service_subtype_ref = product.subtypeRef;
  });

  // CSV result modal helper
  function showPolicyCsvResult(html) {
    var body = document.getElementById('policy-csv-result-body');
    var modalEl = document.getElementById('policy-csv-result-modal');
    if (!body || !modalEl) { alert(html); return; }
    body.innerHTML = html;
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  async function handlePolicyCsvUpload(uploadUrl, file) {
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
        showPolicyCsvResult(html);
        await htmx.ajax('GET', '/policy/policy/partial/', { target: '#policy-pane', swap: 'innerHTML' });
      } else {
        showPolicyCsvResult('<div class="text-danger"><strong>Ошибка:</strong> ' +
          (data.error || 'Неизвестная ошибка').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
      }
    } catch (err) {
      showPolicyCsvResult('<div class="text-danger"><strong>Ошибка загрузки:</strong> ' +
        err.message.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
    }
  }

  document.addEventListener('click', function (e) {
    var mapping = {
      'products-csv-upload-btn': 'products-csv-file-input',
      'service-goal-reports-csv-upload-btn': 'service-goal-reports-csv-file-input',
      'sections-csv-upload-btn': 'sections-csv-file-input',
      'structures-csv-upload-btn': 'structures-csv-file-input',
      'tariffs-csv-upload-btn': 'tariffs-csv-file-input',
      'typical-service-compositions-csv-upload-btn': 'typical-service-compositions-csv-file-input',
      'typical-service-terms-csv-upload-btn': 'typical-service-terms-csv-file-input',
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
      'products-csv-file-input': '/policy/policy/product/csv-upload/',
      'service-goal-reports-csv-file-input': '/policy/policy/service-goal-report/csv-upload/',
      'sections-csv-file-input': '/policy/policy/section/csv-upload/',
      'structures-csv-file-input': '/policy/policy/structure/csv-upload/',
      'tariffs-csv-file-input': '/policy/policy/tariff/csv-upload/',
      'typical-service-compositions-csv-file-input': '/policy/policy/typical-service-composition/csv-upload/',
      'typical-service-terms-csv-file-input': '/policy/policy/typical-service-term/csv-upload/',
    };
    var url = mapping[e.target.id];
    if (!url) return;
    var file = e.target.files[0];
    if (!file) return;
    await handlePolicyCsvUpload(url, file);
  });

  // Восстановление выбора только для таблицы, где было действие
  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (!(e.target && e.target.id === 'policy-pane')) return;
    const restoreY = window.__policyScrollRestoreY;
    if (typeof restoreY === 'number') {
      requestAnimationFrame(function () {
        window.scrollTo(0, restoreY);
      });
      window.__policyScrollRestoreY = null;
    }
    initTypicalServiceCompositionWrapToggle();
    collapseSpecialtyTariffsSpecialties();
    initPolicyMasterFilters();
    initTypicalServiceTermGanttEditor(e.target);
    const last = window.__tableSelLast;
    if (!last) return;
    const ids = (window.__tableSel && window.__tableSel[last]) || [];
    const set = new Set(ids || []);
    getRowChecksByName(last).forEach(b => { b.checked = set.has(String(b.value)); });
    updateMasterStateFor(last);
    updateRowHighlightFor(last);
    ensureActionsVisibility(last); // <- панель должна остаться видимой при отмеченных чекбоксах
    syncTypicalServiceTermGanttEditButton();
    try { delete window.__tableSel[last]; } catch(e) { window.__tableSel[last] = []; }
    window.__tableSelLast = null;
  });

  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (!e.target) return;
    initPolicyProductSelects(e.target);
  });

  initPolicyProductSelects(document);
  initTypicalServiceCompositionWrapToggle();
  collapseSpecialtyTariffsSpecialties();
  initPolicyMasterFilters();
  initTypicalServiceTermGanttEditor(document);
})();