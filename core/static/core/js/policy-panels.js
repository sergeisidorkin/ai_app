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
    const last = window.__tableSelLast;
    if (!last) return;
    const ids = (window.__tableSel && window.__tableSel[last]) || [];
    const set = new Set(ids || []);
    getRowChecksByName(last).forEach(b => { b.checked = set.has(String(b.value)); });
    updateMasterStateFor(last);
    updateRowHighlightFor(last);
    ensureActionsVisibility(last); // <- панель должна остаться видимой при отмеченных чекбоксах
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
})();