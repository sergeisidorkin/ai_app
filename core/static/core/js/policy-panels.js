(function () {
  if (window.__policyPanelBound) return;
  window.__policyPanelBound = true;

  window.__tableSel = window.__tableSel || {};
  window.__tableSelLast = window.__tableSelLast || null;

  function pane() {
    // The typical-service-term-gantt editor is reused (with the same ids) by
    // other sections of the application — currently the projects' "График
    // проекта" Gantt. Both panes (#policy-pane and #projects-pane) live in
    // the DOM at once (Bootstrap tabs), so we need to pick the pane the user
    // is actually looking at — the one whose ancestor tab-pane has the
    // `.active` class. Fall back to whichever pane has the editor open
    // (`d-none` removed), then to the policy pane for backwards compatibility.
    var policyAll = document.querySelectorAll('#policy-pane');
    var policyPane = policyAll.length > 1 ? policyAll[policyAll.length - 1] : policyAll[0] || null;
    var projectsAll = document.querySelectorAll('#projects-pane');
    var projectsPane = projectsAll.length > 1 ? projectsAll[projectsAll.length - 1] : projectsAll[0] || null;
    function isVisible(el) {
      if (!el) return false;
      var tab = el.closest ? el.closest('.tab-pane') : null;
      if (tab) return tab.classList.contains('active');
      // No tab ancestor → assume it's standalone-visible.
      return true;
    }
    function editorOpen(el) {
      if (!el) return false;
      var ed = el.querySelector('#typical-service-term-gantt-editor');
      return !!(ed && !ed.classList.contains('d-none'));
    }
    var policyVisible = isVisible(policyPane);
    var projectsVisible = isVisible(projectsPane);
    if (projectsPane && projectsVisible && !policyVisible) return projectsPane;
    if (policyPane && policyVisible && !projectsVisible) return policyPane;
    // Both visible (shouldn't happen for tabs) or neither — disambiguate by
    // which editor is currently open.
    var policyOpen = editorOpen(policyPane);
    var projectsOpen = editorOpen(projectsPane);
    if (projectsOpen && !policyOpen) return projectsPane;
    if (policyOpen && !projectsOpen) return policyPane;
    return policyPane || projectsPane || null;
  }

  function typicalServiceTermGanttEditorEl() {
    var p = pane();
    return (p && p.querySelector('#typical-service-term-gantt-editor'))
      || document.getElementById('typical-service-term-gantt-editor');
  }

  function typicalServiceTermGanttChartEl() {
    var p = pane();
    return (p && p.querySelector('#typical-service-term-gantt'))
      || document.getElementById('typical-service-term-gantt');
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
  function readPolicyMasterFilterPrefs() {
    return P ? P.get(POLICY_FILTER_PREF_KEY, null) : null;
  }

  window.__policyMasterFilters = window.__policyMasterFilters
    || filterStateWithDefaults(readPolicyMasterFilterPrefs());
  window.__policyTypicalServiceCompositionWrapActive =
    typeof window.__policyTypicalServiceCompositionWrapActive === 'boolean'
      ? window.__policyTypicalServiceCompositionWrapActive
      : (P ? P.get('policy:typicalServiceCompositionWrapActive', true) : true);
  window.__policySpecialtyTariffsSpecialtiesCollapsed =
    typeof window.__policySpecialtyTariffsSpecialtiesCollapsed === 'boolean'
      ? window.__policySpecialtyTariffsSpecialtiesCollapsed
      : (P ? P.get('policy:specialtyTariffsSpecialtiesCollapsed', false) : false);
  const TYPICAL_SERVICE_TERM_GANTT_SCALE_PREF_KEY = 'policy:typical-service-term-gantt-scale';
  const TYPICAL_SERVICE_TERM_GANTT_TIMEBOX_PREF_KEY = 'policy:typical-service-term-gantt-timebox';
  const TYPICAL_SERVICE_TERM_GANTT_SNAP_TO_GRID_PREF_KEY = 'policy:typical-service-term-gantt-snap-to-grid';
  const TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY = 'policy:typical-service-term-gantt-grid-width';
  const TYPICAL_SERVICE_TERM_GANTT_COLUMNS_PREF_KEY = 'policy:typical-service-term-gantt-columns';
  const TYPICAL_SERVICE_TERM_GANTT_CALENDAR_DAYS_PREF_KEY = 'policy:typical-service-term-gantt-calendar-days';
  const TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PREF_KEY = 'policy:typical-service-term-gantt-calendar-kind';
  const TYPICAL_SERVICE_TERM_GANTT_CALENDAR_COUNTRY_PREF_KEY = 'policy:typical-service-term-gantt-calendar-country';
  const TYPICAL_SERVICE_TERM_GANTT_HIDE_NON_WORKING_PREF_KEY = 'policy:typical-service-term-gantt-hide-non-working';
  const TYPICAL_SERVICE_TERM_GANTT_DEFAULT_SCALE = 'week';
  const TYPICAL_SERVICE_TERM_GANTT_DEFAULT_COUNTRY_ALPHA2 = 'RU';
  const TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT = 'abstract';
  const TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION = 'production';
  const TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_EXECUTOR = 'executor';
  const TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE = 'resource_name';
  const TYPICAL_SERVICE_TERM_GANTT_ABSTRACT_BASE_YEAR = 2026;
  const TYPICAL_SERVICE_TERM_GANTT_CALENDAR_BG_CLASS = 'typical-service-term-gantt-non-working-day-bg';
  const TYPICAL_SERVICE_TERM_GANTT_CALENDAR_OVERLAY_CLASS = 'typical-service-term-gantt-non-working-overlay';
  const TYPICAL_SERVICE_TERM_GANTT_GRID_LINE_CLASS = 'typical-service-term-gantt-grid-line';
  const TYPICAL_SERVICE_TERM_GANTT_SELECTION_NAME = 'typical-service-term-select';
  const TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE = 'service_section';
  const TYPICAL_SERVICE_TERM_GANTT_COLLAPSED_COLUMN_WIDTH = 16;
  const TYPICAL_SERVICE_TERM_GANTT_NON_COLLAPSIBLE_COLUMNS = ['wbs', 'text', 'add'];
  const TYPICAL_SERVICE_TERM_GANTT_WEEKDAY_LABELS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
  const TYPICAL_SERVICE_TERM_GANTT_SYSTEM_TASK_NAMES = {
    source_data: 'Исходные данные',
    source_data_asset: 'Актив',
    preliminary_report: 'Предварительный отчёт',
    preliminary_report_asset: 'Актив',
    preliminary_report_submission: 'Отправка Предварительного отчёта',
    final_report: 'Итоговый отчёт',
  };
  window.__policyTypicalServiceTermGanttSnapToGrid =
    typeof window.__policyTypicalServiceTermGanttSnapToGrid === 'boolean'
      ? window.__policyTypicalServiceTermGanttSnapToGrid
      : (P ? !!P.get(TYPICAL_SERVICE_TERM_GANTT_SNAP_TO_GRID_PREF_KEY, false) : false);
  window.__policyTypicalServiceTermGanttTimebox =
    typeof window.__policyTypicalServiceTermGanttTimebox === 'boolean'
      ? window.__policyTypicalServiceTermGanttTimebox
      : (P ? !!P.get(TYPICAL_SERVICE_TERM_GANTT_TIMEBOX_PREF_KEY, false) : false);
  // Default mode: working days. The calendar3 button switches to calendar-days mode.
  window.__policyTypicalServiceTermGanttCalendarDaysMode =
    typeof window.__policyTypicalServiceTermGanttCalendarDaysMode === 'boolean'
      ? window.__policyTypicalServiceTermGanttCalendarDaysMode
      : (P ? !!P.get(TYPICAL_SERVICE_TERM_GANTT_CALENDAR_DAYS_PREF_KEY, false) : false);
  // When true (and working-days mode is on) the timeline collapses non-working
  // time via DHTMLX `skip_off_time`. Disabled while calendar-days mode is on.
  window.__policyTypicalServiceTermGanttHideNonWorkingDays =
    typeof window.__policyTypicalServiceTermGanttHideNonWorkingDays === 'boolean'
      ? window.__policyTypicalServiceTermGanttHideNonWorkingDays
      : (P ? !!P.get(TYPICAL_SERVICE_TERM_GANTT_HIDE_NON_WORKING_PREF_KEY, false) : false);
  window.__policyTypicalServiceTermGanttCalendarKind =
    [TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT, TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION].includes(
      window.__policyTypicalServiceTermGanttCalendarKind
    )
      ? window.__policyTypicalServiceTermGanttCalendarKind
      : (P ? P.get(TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PREF_KEY, TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION) : TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION);
  if (![TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT, TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION].includes(window.__policyTypicalServiceTermGanttCalendarKind)) {
    window.__policyTypicalServiceTermGanttCalendarKind = TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION;
  }
  window.__policyTypicalServiceTermGanttExecutorDisplay =
    [TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_EXECUTOR, TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE].includes(
      window.__policyTypicalServiceTermGanttExecutorDisplay
    )
      ? window.__policyTypicalServiceTermGanttExecutorDisplay
      : (window.__policyTypicalServiceTermGanttCalendarKind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT
        ? TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE
        : TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_EXECUTOR);
  // Production calendar country id used to resolve working/non-working days.
  // Numeric primary key of an OKSMCountry row from the Справочники module.
  window.__policyTypicalServiceTermGanttCalendarCountryId =
    (typeof window.__policyTypicalServiceTermGanttCalendarCountryId === 'number'
      && Number.isFinite(window.__policyTypicalServiceTermGanttCalendarCountryId))
      ? window.__policyTypicalServiceTermGanttCalendarCountryId
      : (P ? Number(P.get(TYPICAL_SERVICE_TERM_GANTT_CALENDAR_COUNTRY_PREF_KEY, NaN)) : NaN);
  if (!Number.isFinite(window.__policyTypicalServiceTermGanttCalendarCountryId)) {
    window.__policyTypicalServiceTermGanttCalendarCountryId = null;
  }
  // Cached calendar-day datasets keyed by countryId+year. Each entry is a
  // Promise resolving to a { workingDays:Set, nonWorkingDays:Set, ... } object.
  window.__policyTypicalServiceTermGanttCalendarCache =
    window.__policyTypicalServiceTermGanttCalendarCache || new Map();
  // List of supported countries from the classifiers endpoint; refreshed lazily.
  window.__policyTypicalServiceTermGanttCalendarCountriesPromise =
    window.__policyTypicalServiceTermGanttCalendarCountriesPromise || null;
  window.__policyTypicalServiceTermGanttSessionId =
    Number(window.__policyTypicalServiceTermGanttSessionId) || 0;

  function beginTypicalServiceTermGanttSession(editor) {
    window.__policyTypicalServiceTermGanttSessionId += 1;
    const sessionId = window.__policyTypicalServiceTermGanttSessionId;
    if (editor) editor.dataset.typicalServiceTermGanttSessionId = String(sessionId);
    return sessionId;
  }

  function getTypicalServiceTermGanttSessionId(root) {
    const editor = root?.querySelector?.('#typical-service-term-gantt-editor');
    const value = Number(editor?.dataset?.typicalServiceTermGanttSessionId);
    return Number.isFinite(value) ? value : null;
  }

  function isTypicalServiceTermGanttSessionCurrent(root, gantt, sessionId, expectedKind, expectedCountryId) {
    if (!Number.isFinite(sessionId)) return false;
    if (gantt !== window.__policyTypicalServiceTermGantt) return false;
    if (getTypicalServiceTermGanttSessionId(root) !== sessionId) return false;
    if (expectedKind && getTypicalServiceTermGanttCalendarKind() !== expectedKind) return false;
    if (
      expectedKind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION &&
      Number.isFinite(expectedCountryId) &&
      getTypicalServiceTermGanttCalendarCountryId() !== Number(expectedCountryId)
    ) {
      return false;
    }
    return true;
  }

  function policyGanttAttachEvent(eventName, handler) {
    const g = getTypicalServiceTermGanttInstance();
    if (!g || typeof g.attachEvent !== 'function') return null;
    return g.attachEvent(eventName, handler);
  }

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

  function isTypicalServiceTermGanttManagedTask(task) {
    return pane()?.id === 'projects-pane' &&
      ['work_volume', 'performer', 'checklist_section'].includes(normalizeFilterValue(task?.managed_source));
  }

  function isTypicalServiceTermGanttManagedPerformerTask(task) {
    return pane()?.id === 'projects-pane' && normalizeFilterValue(task?.managed_source) === 'performer';
  }

  function isTypicalServiceTermGanttManagedAssetTask(task) {
    return pane()?.id === 'projects-pane' && normalizeFilterValue(task?.managed_source) === 'work_volume';
  }

  function isTypicalServiceTermGanttManagedChecklistSectionTask(task) {
    return pane()?.id === 'projects-pane' && normalizeFilterValue(task?.managed_source) === 'checklist_section';
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

  function normalizeTypicalServiceTermGanttSectionOptions(sections) {
    return normalizeTypicalServiceTermGanttSectionCatalog(sections).map(function (item) {
      return item.label;
    });
  }

  function normalizeTypicalServiceTermGanttTextOptions(options) {
    const seen = new Set();
    return (Array.isArray(options) ? options : [])
      .map(function (item) {
        if (typeof item === 'string') return item;
        return item?.label || item?.name || item?.specialty || '';
      })
      .map(normalizeFilterValue)
      .filter(function (label) {
        if (!label || seen.has(label)) return false;
        seen.add(label);
        return true;
      });
  }

  function normalizeTypicalServiceTermGanttSectionSpecialties(specialties) {
    const seen = new Set();
    return (Array.isArray(specialties) ? specialties : [])
      .map(function (item) {
        const label = normalizeFilterValue(
          typeof item === 'string'
            ? item
            : (item?.label || item?.specialty || item?.name || '')
        );
        if (!label || seen.has(label)) return null;
        seen.add(label);
        return {
          label: label,
          rank: Number(item?.rank) || 0,
        };
      })
      .filter(Boolean);
  }

  function normalizeTypicalServiceTermGanttSectionCatalog(sections) {
    const seen = new Set();
    return (Array.isArray(sections) ? sections : [])
      .map(function (item) {
        const label = normalizeFilterValue(
          typeof item === 'string'
            ? item
            : (item?.label || item?.name_ru || item?.name || '')
        );
        if (!label || seen.has(label)) return null;
        seen.add(label);
        return {
          id: normalizeFilterValue(item?.id),
          label: label,
          specialties: normalizeTypicalServiceTermGanttSectionSpecialties(item?.specialties),
        };
      })
      .filter(Boolean);
  }

  function normalizeTypicalServiceTermGanttExecutorCatalog(executors) {
    const byValue = new Map();
    (Array.isArray(executors) ? executors : []).forEach(function (item) {
      const label = normalizeFilterValue(typeof item === 'string' ? item : (item?.label || item?.name || ''));
      const value = normalizeFilterValue(typeof item === 'string' ? item : (item?.value || item?.id || label));
      if (!label || !value) return;
      const current = byValue.get(value) || { value: value, label: label, specialties: [] };
      const seenSpecialties = new Set(current.specialties);
      normalizeTypicalServiceTermGanttTextOptions(item?.specialties).forEach(function (specialty) {
        if (seenSpecialties.has(specialty)) return;
        current.specialties.push(specialty);
        seenSpecialties.add(specialty);
      });
      byValue.set(value, current);
    });
    return Array.from(byValue.values());
  }

  function getTypicalServiceTermGanttSectionOptions() {
    const editor = getTypicalServiceTermGanttCurrentEditor();
    return getTypicalServiceTermGanttSectionCatalog(editor).map(function (item) {
      return item.label;
    });
  }

  function getTypicalServiceTermGanttSectionCatalog(editorArg) {
    const editor = editorArg || getTypicalServiceTermGanttCurrentEditor();
    return normalizeTypicalServiceTermGanttSectionCatalog(
      editor?._typicalServiceTermGanttSectionCatalog || editor?._typicalServiceTermGanttSections
    );
  }

  function getTypicalServiceTermGanttSectionByLabel(label) {
    const normalized = normalizeFilterValue(label);
    return getTypicalServiceTermGanttSectionCatalog().find(function (item) {
      return item.label === normalized;
    }) || null;
  }

  function getTypicalServiceTermGanttTaskSectionName(task) {
    const explicitSectionName = normalizeFilterValue(task?.service_section_name || task?.section_name);
    if (explicitSectionName) return explicitSectionName;
    const text = normalizeFilterValue(task?.text);
    return getTypicalServiceTermGanttSectionByLabel(text) ? text : '';
  }

  function getTypicalServiceTermGanttExecutorCatalog(editorArg) {
    const editor = editorArg || getTypicalServiceTermGanttCurrentEditor();
    return normalizeTypicalServiceTermGanttExecutorCatalog(editor?._typicalServiceTermGanttExecutors);
  }

  function getTypicalServiceTermGanttExecutorLabel(value) {
    const normalized = normalizeFilterValue(value);
    if (!normalized) return '';
    const executor = getTypicalServiceTermGanttExecutorCatalog().find(function (item) {
      return item.value === normalized || item.label === normalized;
    });
    return executor?.label || normalized;
  }

  function getTypicalServiceTermGanttSpecialtyOptions() {
    const editor = getTypicalServiceTermGanttCurrentEditor();
    return normalizeTypicalServiceTermGanttTextOptions(editor?._typicalServiceTermGanttSpecialties);
  }

  function getTypicalServiceTermGanttExecutorOptions(specialty) {
    const normalizedSpecialty = normalizeFilterValue(specialty);
    if (!normalizedSpecialty) return [];
    return getTypicalServiceTermGanttExecutorCatalog()
      .filter(function (item) {
        return item.specialties.indexOf(normalizedSpecialty) !== -1;
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

  function formatPolicyGanttDateInput(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
    const year = String(date.getFullYear()).padStart(4, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return year + '-' + month + '-' + day;
  }

  function parseTypicalServiceTermGanttDateInput(value) {
    if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
    const raw = normalizeFilterValue(value);
    if (!raw) return null;
    const dotMatch = raw.match(/^(\d{1,2})\.(\d{1,2})\.(\d{1,4})$/);
    if (dotMatch) {
      const parsedYear = Number(dotMatch[3]) || 1;
      let actualYear;
      if (isTypicalServiceTermGanttAbstractCalendar()) {
        actualYear = parsedYear >= TYPICAL_SERVICE_TERM_GANTT_ABSTRACT_BASE_YEAR
          ? parsedYear
          : TYPICAL_SERVICE_TERM_GANTT_ABSTRACT_BASE_YEAR + Math.max(1, parsedYear) - 1;
      } else {
        actualYear = parsedYear < 100 ? 2000 + parsedYear : parsedYear;
      }
      return new Date(actualYear, Number(dotMatch[2]) - 1, Number(dotMatch[1]));
    }
    if (!isTypicalServiceTermGanttAbstractCalendar()) return parsePolicyGanttDate(value);
    const isoMatch = raw.match(/^(\d{1,4})-(\d{1,2})-(\d{1,2})/);
    if (!isoMatch) return parsePolicyGanttDate(value);
    const parsedYear = Number(isoMatch[1]) || 1;
    if (parsedYear >= TYPICAL_SERVICE_TERM_GANTT_ABSTRACT_BASE_YEAR) return parsePolicyGanttDate(value);
    const abstractYear = Math.max(1, parsedYear);
    return new Date(
      TYPICAL_SERVICE_TERM_GANTT_ABSTRACT_BASE_YEAR + abstractYear - 1,
      Number(isoMatch[2]) - 1,
      Number(isoMatch[3])
    );
  }

  function formatTypicalServiceTermGanttDateInput(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
    const year = isTypicalServiceTermGanttAbstractCalendar()
      ? String(getTypicalServiceTermGanttAbstractYearNumber(date)).padStart(2, '0').slice(-2)
      : String(date.getFullYear()).padStart(4, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return day + '.' + month + '.' + year;
  }

  function formatTypicalServiceTermGanttPickerDateInput(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
    if (!isTypicalServiceTermGanttAbstractCalendar()) return formatPolicyGanttDateInput(date);
    const year = String(getTypicalServiceTermGanttAbstractYearNumber(date)).padStart(4, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return year + '-' + month + '-' + day;
  }

  function syncTypicalServiceTermGanttDateInputFormats(root) {
    const scope = root || document;
    scope.querySelectorAll('.typical-service-term-gantt-date-input-wrap input').forEach(function (input) {
      if (typeof input.$policyTypicalServiceTermSyncDateInputFormat === 'function') {
        input.$policyTypicalServiceTermSyncDateInputFormat();
      }
    });
  }

  function formatTypicalServiceTermGanttTypedDateValue(value) {
    const yearLength = isTypicalServiceTermGanttAbstractCalendar() ? 2 : 4;
    const digits = String(value || '').replace(/\D/g, '').slice(0, 4 + yearLength);
    if (!digits) return '';
    const day = digits.slice(0, 2);
    const month = digits.slice(2, 4);
    const yearDigits = digits.slice(4, 4 + yearLength);
    return [day, month, yearDigits].filter(Boolean).join('.');
  }

  function syncTypicalServiceTermGanttDateInputPickerState(input) {
    const picker = input?.$policyTypicalServiceTermDatePicker;
    if (!input || !picker) return;
    const disabled = !!(input.disabled || input.readOnly || input.$policyTypicalServiceTermDatePickerLocked);
    const icon = picker.parentElement?.querySelector('.typical-service-term-gantt-date-picker-icon');
    picker.disabled = disabled;
    picker.style.pointerEvents = disabled ? 'none' : 'auto';
    picker.style.cursor = 'default';
    if (icon) icon.style.opacity = disabled ? '0.45' : '1';
  }

  function bindTypicalServiceTermGanttDateInput(input) {
    if (!input || input.$policyTypicalServiceTermDateInputBound) return;
    input.$policyTypicalServiceTermDateInputBound = true;
    let wrapper = input.parentElement?.classList?.contains('typical-service-term-gantt-date-input-wrap')
      ? input.parentElement
      : null;
    if (!wrapper) {
      wrapper = document.createElement('div');
      wrapper.className = 'typical-service-term-gantt-date-input-wrap';
      wrapper.style.position = 'relative';
      wrapper.style.display = 'block';
      input.parentNode.insertBefore(wrapper, input);
      wrapper.appendChild(input);
    }
    input.type = 'text';
    input.inputMode = 'numeric';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.setAttribute('spellcheck', 'false');
    input.setAttribute('autocorrect', 'off');
    input.setAttribute('autocapitalize', 'off');
    input.style.paddingRight = '2.25rem';
    input.style.cursor = 'default';

    wrapper.querySelectorAll('.typical-service-term-gantt-date-picker-addon').forEach(function (node) {
      node.remove();
    });
    const icon = document.createElement('i');
    icon.className = 'bi bi-calendar typical-service-term-gantt-date-picker-addon typical-service-term-gantt-date-picker-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.style.position = 'absolute';
    icon.style.right = '0.7rem';
    icon.style.top = '50%';
    icon.style.transform = 'translateY(-50%)';
    icon.style.color = '#6c757d';
    icon.style.pointerEvents = 'none';

    const picker = document.createElement('input');
    picker.type = 'date';
    picker.tabIndex = -1;
    picker.setAttribute('aria-label', input.getAttribute('aria-label') || input.id || 'Выбрать дату');
    picker.className = 'typical-service-term-gantt-date-picker-addon typical-service-term-gantt-native-date-picker';
    picker.style.position = 'absolute';
    picker.style.right = '0.25rem';
    picker.style.top = '50%';
    picker.style.transform = 'translateY(-50%)';
    picker.style.width = '2rem';
    picker.style.height = 'calc(100% - 4px)';
    picker.style.opacity = '0';
    picker.style.cursor = 'default';
    picker.style.border = '0';
    picker.style.padding = '0';
    picker.style.background = 'transparent';
    wrapper.appendChild(icon);
    icon.insertAdjacentElement('afterend', picker);
    input.$policyTypicalServiceTermDatePicker = picker;

    const getDateInputYearLength = function () {
      return isTypicalServiceTermGanttAbstractCalendar() ? 2 : 4;
    };
    const getDateInputPlaceholder = function () {
      return getDateInputYearLength() === 2 ? 'дд.мм.гг' : 'дд.мм.гггг';
    };
    const syncDateInputPlaceholder = function () {
      input.placeholder = getDateInputPlaceholder();
    };
    syncDateInputPlaceholder();
    input.$policyTypicalServiceTermSyncDateInputFormat = function () {
      const parsed = parseTypicalServiceTermGanttDateInput(input.value);
      if (parsed) input.value = formatTypicalServiceTermGanttDateInput(parsed);
      syncDateInputPlaceholder();
      syncPicker();
    };
    const getDateInputTextForHitTest = function () {
      return isSegmentEditableText() ? input.value : getDateInputPlaceholder();
    };
    const isDateInputLocked = function () {
      return !!(input.readOnly || input.disabled || input.$policyTypicalServiceTermDatePickerLocked);
    };
    const measureDateInputText = function (text) {
      const styles = window.getComputedStyle ? window.getComputedStyle(input) : null;
      const canvas = bindTypicalServiceTermGanttDateInput.$measureCanvas
        || (bindTypicalServiceTermGanttDateInput.$measureCanvas = document.createElement('canvas'));
      const ctx = canvas.getContext('2d');
      if (!ctx) return String(text || '').length * 8;
      ctx.font = styles?.font || [
        styles?.fontStyle,
        styles?.fontVariant,
        styles?.fontWeight,
        styles?.fontSize,
        styles?.fontFamily,
      ].filter(Boolean).join(' ') || '14px sans-serif';
      return ctx.measureText(String(text || '')).width;
    };
    const getDefaultDate = function () {
      const value = typeof input.$policyTypicalServiceTermDatePickerDefaultDate === 'function'
        ? input.$policyTypicalServiceTermDatePickerDefaultDate()
        : input.$policyTypicalServiceTermDatePickerDefaultDate;
      return value instanceof Date && !Number.isNaN(value.getTime()) ? value : null;
    };
    const syncPicker = function () {
      const parsed = parseTypicalServiceTermGanttDateInput(input.value) || getDefaultDate();
      picker.value = parsed ? formatTypicalServiceTermGanttPickerDateInput(parsed) : '';
    };
    const normalizeVisible = function () {
      if (input.$policyTypicalServiceTermDateMaskActive && isSegmentEditableText() && !isCompleteDateText()) {
        input.value = '';
        input.$policyTypicalServiceTermDateMaskActive = false;
        syncPicker();
        return;
      }
      const parsed = parseTypicalServiceTermGanttDateInput(input.value);
      if (parsed) input.value = formatTypicalServiceTermGanttDateInput(parsed);
      syncPicker();
    };
    const formatTypedValue = function () {
      if (input.$policyTypicalServiceTermDateSegmentEditing) {
        syncPicker();
        return;
      }
      input.$policyTypicalServiceTermDateMaskActive = false;
      const formatted = formatTypicalServiceTermGanttTypedDateValue(input.value);
      if (input.value !== formatted) {
        input.value = formatted;
        input.setSelectionRange?.(formatted.length, formatted.length);
      }
      syncPicker();
    };
    const segments = [
      { name: 'day', start: 0, end: 2, next: 'month', maxFirst: 3, max: 31, length: 2 },
      { name: 'month', start: 3, end: 5, next: 'year', maxFirst: 1, max: 12, length: 2 },
      { name: 'year', start: 6, end: function () { return 6 + getDateInputYearLength(); }, next: null, maxFirst: 9, max: function () { return getDateInputYearLength() === 2 ? 99 : 9999; }, length: getDateInputYearLength },
    ];
    const getSegmentEnd = function (segment) {
      return typeof segment?.end === 'function' ? segment.end() : segment?.end;
    };
    const getSegmentLength = function (segment) {
      return typeof segment?.length === 'function' ? segment.length() : segment?.length;
    };
    const getSegmentMax = function (segment) {
      return typeof segment?.max === 'function' ? segment.max() : segment?.max;
    };
    const getSegmentByName = function (name) {
      return segments.find(function (segment) { return segment.name === name; }) || null;
    };
    const getSegmentByCaret = function () {
      const pos = Number(input.selectionStart);
      if (!Number.isFinite(pos)) return null;
      if (pos <= 2) return getSegmentByName('day');
      if (pos <= 5) return getSegmentByName('month');
      return getSegmentByName('year');
    };
    const getSegmentByPointer = function (event) {
      if (!event || !Number.isFinite(Number(event.clientX))) return null;
      const rect = input.getBoundingClientRect();
      const styles = window.getComputedStyle ? window.getComputedStyle(input) : null;
      const paddingLeft = parseFloat(styles?.paddingLeft || '0') || 0;
      const text = getDateInputTextForHitTest();
      const x = Math.max(0, Number(event.clientX) - rect.left - paddingLeft);
      const widthUntil = function (index) {
        return measureDateInputText(text.slice(0, index));
      };
      const dayCenter = widthUntil(0) + (widthUntil(2) - widthUntil(0)) / 2;
      const monthCenter = widthUntil(3) + (widthUntil(5) - widthUntil(3)) / 2;
      const yearEnd = 6 + getDateInputYearLength();
      const yearCenter = widthUntil(6) + (widthUntil(yearEnd) - widthUntil(6)) / 2;
      const dayMonthBoundary = (dayCenter + monthCenter) / 2;
      const monthYearBoundary = (monthCenter + yearCenter) / 2;
      if (x <= dayMonthBoundary) return getSegmentByName('day');
      if (x <= monthYearBoundary) return getSegmentByName('month');
      return getSegmentByName('year');
    };
    const getSelectedSegment = function () {
      const start = Number(input.selectionStart);
      const end = Number(input.selectionEnd);
      return segments.find(function (segment) {
        return start === segment.start && end === getSegmentEnd(segment);
      }) || null;
    };
    const isCompleteDateText = function () {
      return getDateInputYearLength() === 2
        ? /^\d{2}\.\d{2}\.\d{2}$/.test(input.value || '')
        : /^\d{2}\.\d{2}\.\d{4}$/.test(input.value || '');
    };
    const isSegmentEditableText = function () {
      return getDateInputYearLength() === 2
        ? /^(\d{2}|дд)\.(\d{2}|мм)\.(\d{2}|гг)$/.test(input.value || '')
        : /^(\d{2}|дд)\.(\d{2}|мм)\.(\d{4}|гггг)$/.test(input.value || '');
    };
    const selectDateSegment = function (segment) {
      if (!segment || typeof input.setSelectionRange !== 'function') return;
      input.setSelectionRange(segment.start, getSegmentEnd(segment));
      input.$policyTypicalServiceTermDateSelectedSegment = segment.name;
    };
    const ensureEditableMask = function () {
      if (input.value) return;
      input.value = getDateInputPlaceholder();
      input.$policyTypicalServiceTermDateMaskActive = true;
    };
    const selectSegmentFromClick = function (event) {
      if (isDateInputLocked()) return;
      let segment = getSegmentByPointer(event);
      if (!input.value) {
        ensureEditableMask();
      }
      if (!isSegmentEditableText()) return;
      if (!segment) segment = getSegmentByCaret();
      selectDateSegment(segment);
    };
    const handleSegmentPointerDown = function (event) {
      if (isDateInputLocked()) return;
      if (event?.target?.closest?.('.typical-service-term-gantt-date-picker-addon')) return;
      if (event && Number.isFinite(Number(event.clientX)) && Number.isFinite(Number(event.clientY))) {
        const rect = input.getBoundingClientRect();
        if (
          event.clientX < rect.left ||
          event.clientX > rect.right ||
          event.clientY < rect.top ||
          event.clientY > rect.bottom
        ) {
          return;
        }
      }
      event.preventDefault();
      input.focus({ preventScroll: true });
      selectSegmentFromClick(event);
    };
    const replaceDateSegment = function (segment, rawValue, advance, options) {
      const value = Math.max(0, Math.min(getSegmentMax(segment), Number(rawValue) || 0));
      const allowZero = !!options?.allowZero;
      const safeValue = segment.name === 'year' || allowZero
        ? value
        : Math.max(1, value);
      const length = getSegmentLength(segment);
      const part = String(safeValue).padStart(length, '0').slice(-length);
      input.value = input.value.slice(0, segment.start) + part + input.value.slice(getSegmentEnd(segment));
      input.$policyTypicalServiceTermDateMaskActive = !isCompleteDateText();
      syncPicker();
      const nextSegment = advance && segment.next ? getSegmentByName(segment.next) : segment;
      selectDateSegment(nextSegment);
      input.$policyTypicalServiceTermDateSegmentEditing = true;
      try {
        input.dispatchEvent(new Event('input', { bubbles: true }));
      } finally {
        input.$policyTypicalServiceTermDateSegmentEditing = false;
      }
    };
    const setDateSegmentPending = function (segment, digit) {
      input.$policyTypicalServiceTermDateSegmentPending = {
        segment: segment.name,
        digit: digit,
        at: Date.now(),
      };
    };
    const clearDateSegmentPending = function () {
      input.$policyTypicalServiceTermDateSegmentPending = null;
    };
    const isFreshPendingForSegment = function (pending, segment, now) {
      return !!(
        pending &&
        pending.segment === segment.name &&
        now - pending.at < 1500
      );
    };
    const applyYearSegmentDigit = function (segment, digit, now) {
      const pending = input.$policyTypicalServiceTermDateSegmentPending;
      if (getDateInputYearLength() === 4) {
        const pendingDigits = isFreshPendingForSegment(pending, segment, now) ? pending.digit : '';
        const digits = (pendingDigits + digit).slice(0, 4);
        const complete = digits.length >= 4;
        replaceDateSegment(segment, digits, false, { allowZero: true });
        if (complete) {
          clearDateSegmentPending();
        } else {
          input.$policyTypicalServiceTermDateSegmentPending = {
            segment: segment.name,
            digit: digits,
            at: now,
          };
        }
        return;
      }
      let rawValue;
      if (isFreshPendingForSegment(pending, segment, now)) {
        rawValue = pending.digit + digit;
        clearDateSegmentPending();
      } else {
        rawValue = '0' + digit;
        setDateSegmentPending(segment, digit);
      }
      replaceDateSegment(segment, rawValue, false, { allowZero: true });
    };
    const applyMonthSegmentDigit = function (segment, digit, now) {
      const pending = input.$policyTypicalServiceTermDateSegmentPending;
      if (isFreshPendingForSegment(pending, segment, now)) {
        if (pending.digit === '1' && Number(digit) > 2) {
          clearDateSegmentPending();
          const yearSegment = getSegmentByName('year');
          selectDateSegment(yearSegment);
          applyYearSegmentDigit(yearSegment, digit, now);
          return;
        }
        replaceDateSegment(segment, pending.digit + digit, true, { allowZero: true });
        clearDateSegmentPending();
        return;
      }
      if (digit === '0' || digit === '1') {
        replaceDateSegment(segment, '0' + digit, false, { allowZero: true });
        setDateSegmentPending(segment, digit);
        return;
      }
      replaceDateSegment(segment, '0' + digit, true, { allowZero: true });
      clearDateSegmentPending();
    };
    const applyDaySegmentDigit = function (segment, digit, now) {
      const pending = input.$policyTypicalServiceTermDateSegmentPending;
      if (isFreshPendingForSegment(pending, segment, now)) {
        replaceDateSegment(segment, pending.digit + digit, true, { allowZero: true });
        clearDateSegmentPending();
        return;
      }
      if (digit === '0' || Number(digit) <= 3) {
        replaceDateSegment(segment, '0' + digit, false, { allowZero: true });
        setDateSegmentPending(segment, digit);
        return;
      }
      replaceDateSegment(segment, '0' + digit, true, { allowZero: true });
      clearDateSegmentPending();
    };
    const handleSegmentKeydown = function (event) {
      if (!event || isDateInputLocked()) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const selectedSegment = getSelectedSegment();
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        if (!isSegmentEditableText() || !selectedSegment) return;
        event.preventDefault();
        const direction = event.key === 'ArrowRight' ? 1 : -1;
        const index = segments.findIndex(function (segment) { return segment.name === selectedSegment.name; });
        const nextIndex = Math.max(0, Math.min(segments.length - 1, index + direction));
        selectDateSegment(segments[nextIndex]);
        return;
      }
      if (!/^\d$/.test(event.key)) {
        input.$policyTypicalServiceTermDateSegmentPending = null;
        return;
      }
      if (!input.value) {
        ensureEditableMask();
        const fallbackSegment = getSegmentByName(input.$policyTypicalServiceTermDateSelectedSegment) || getSegmentByName('day');
        selectDateSegment(fallbackSegment);
      }
      if (!isSegmentEditableText() || !getSelectedSegment()) return;
      event.preventDefault();
      const activeSegment = getSelectedSegment();
      const digit = event.key;
      const now = Date.now();
      if (activeSegment.name === 'day') {
        applyDaySegmentDigit(activeSegment, digit, now);
      } else if (activeSegment.name === 'month') {
        applyMonthSegmentDigit(activeSegment, digit, now);
      } else {
        applyYearSegmentDigit(activeSegment, digit, now);
      }
    };
    const preparePickerInteraction = function (event) {
      syncTypicalServiceTermGanttDateInputPickerState(input);
      if (input.readOnly || input.disabled || picker.disabled) {
        if (event) {
          event.preventDefault();
          event.stopPropagation();
        }
        return;
      }
      syncPicker();
    };

    picker.addEventListener('change', function () {
      const parsed = parseTypicalServiceTermGanttDateInput(picker.value);
      input.value = parsed ? formatTypicalServiceTermGanttDateInput(parsed) : '';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
    picker.addEventListener('pointerdown', preparePickerInteraction);
    picker.addEventListener('mousedown', preparePickerInteraction);
    picker.addEventListener('click', preparePickerInteraction);
    wrapper.addEventListener('mousedown', handleSegmentPointerDown);
    input.addEventListener('click', function () {
      const event = arguments[0];
      window.setTimeout(function () { selectSegmentFromClick(event); }, 0);
    });
    input.addEventListener('keydown', handleSegmentKeydown);
    input.addEventListener('input', formatTypedValue);
    input.addEventListener('change', function () {
      input.$policyTypicalServiceTermDateSegmentPending = null;
      normalizeVisible();
    });
    input.addEventListener('blur', function () {
      input.$policyTypicalServiceTermDateSegmentPending = null;
      normalizeVisible();
    });
    syncPicker();
    syncTypicalServiceTermGanttDateInputPickerState(input);
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

  function applyPolicyMasterFilters(root, rows, products, requestedState, options) {
    options = options || {};
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
    if (P && options.persist !== false && rows.length) {
      P.set(POLICY_FILTER_PREF_KEY, state);
    }
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
    if (!rows.length) return;
    const products = getPolicyProductCatalog(root);
    renderPolicyFilterOptions(buildPolicyFilterOptions(rows, products));
    const savedState = filterStateWithDefaults(readPolicyMasterFilterPrefs() || window.__policyMasterFilters);

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

  function isTypicalServiceTermGanttSnapToGridEnabled() {
    return !!window.__policyTypicalServiceTermGanttSnapToGrid;
  }

  function setTypicalServiceTermGanttSnapToGridEnabled(enabled) {
    window.__policyTypicalServiceTermGanttSnapToGrid = !!enabled;
    if (P) P.set(TYPICAL_SERVICE_TERM_GANTT_SNAP_TO_GRID_PREF_KEY, !!enabled);
  }

  function isTypicalServiceTermGanttTimeboxEnabled() {
    return !!window.__policyTypicalServiceTermGanttTimebox;
  }

  function setTypicalServiceTermGanttTimeboxEnabled(enabled) {
    window.__policyTypicalServiceTermGanttTimebox = !!enabled;
    if (P) P.set(TYPICAL_SERVICE_TERM_GANTT_TIMEBOX_PREF_KEY, !!enabled);
  }

  function getTypicalServiceTermGanttGridWidth() {
    const defaultWidth = 820;
    const saved = P ? Number(P.get(TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY, defaultWidth)) : defaultWidth;
    return Number.isFinite(saved) ? Math.max(80, Math.min(1200, Math.round(saved))) : defaultWidth;
  }

  function getTypicalServiceTermGanttColumnsTotalWidth(gantt) {
    if (!Array.isArray(gantt?.config?.columns)) return 0;
    return gantt.config.columns.reduce(function (total, column) {
      return total + (Number(column.width) || 0);
    }, 0);
  }

  function isTypicalServiceTermGanttGridNarrow(gantt) {
    const desired = Number(gantt?.$policyTypicalServiceTermDesiredGridWidth) || 0;
    const minSum = getTypicalServiceTermGanttColumnsMinWidth(gantt);
    if (desired > 0 && minSum > 0 && desired < minSum) return true;
    const total = getTypicalServiceTermGanttColumnsTotalWidth(gantt);
    const gridWidth = Number(gantt?.config?.grid_width) || 0;
    return gridWidth > 0 && total > 0 && gridWidth < total - 1;
  }

  function getTypicalServiceTermGanttColumnWidths() {
    const saved = P ? P.get(TYPICAL_SERVICE_TERM_GANTT_COLUMNS_PREF_KEY, {}) : {};
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
  }

  function getTypicalServiceTermGanttCollapsedColumns() {
    const saved = getTypicalServiceTermGanttColumnWidths();
    const collapsed = saved.__collapsed;
    return collapsed && typeof collapsed === 'object' && !Array.isArray(collapsed) ? collapsed : {};
  }

  function isTypicalServiceTermGanttColumnNameCollapsible(name) {
    return !!name && TYPICAL_SERVICE_TERM_GANTT_NON_COLLAPSIBLE_COLUMNS.indexOf(String(name)) === -1;
  }

  function getTypicalServiceTermGanttColumnCollapsedWidth(column) {
    const configured = Number(column?.collapsed_width);
    return Number.isFinite(configured) && configured > 0
      ? Math.round(configured)
      : TYPICAL_SERVICE_TERM_GANTT_COLLAPSED_COLUMN_WIDTH;
  }

  function isTypicalServiceTermGanttColumnCollapsed(column) {
    return !!(column && column.$policyTypicalServiceTermCollapsed);
  }

  function getTypicalServiceTermGanttColumnExpandedWidth(column) {
    const saved = Number(column?.$policyTypicalServiceTermExpandedWidth);
    const min = Number(column?.min_width) || 44;
    const max = Number(column?.max_width) || 600;
    const fallback = Number(column?.width) || min;
    const value = Number.isFinite(saved) && saved > 0 ? saved : fallback;
    return Math.max(min, Math.min(max, Math.round(value)));
  }

  function typicalServiceTermGanttColumn(name, fallbackWidth, extra) {
    const widths = getTypicalServiceTermGanttColumnWidths();
    const collapsedColumns = getTypicalServiceTermGanttCollapsedColumns();
    const savedWidth = Number(widths[name]);
    const minWidth = Number.isFinite(Number(extra?.min_width)) ? Number(extra.min_width) : 44;
    const maxWidth = Number.isFinite(Number(extra?.max_width)) ? Number(extra.max_width) : 600;
    const expandedWidth = Number.isFinite(savedWidth)
      ? Math.max(minWidth, Math.min(maxWidth, Math.round(savedWidth)))
      : fallbackWidth;
    const collapsible = isTypicalServiceTermGanttColumnNameCollapsible(name) && extra?.collapsible !== false;
    const collapsed = collapsible && !!collapsedColumns[name];
    const column = Object.assign({
      name: name,
      width: collapsed ? TYPICAL_SERVICE_TERM_GANTT_COLLAPSED_COLUMN_WIDTH : expandedWidth,
      resize: true,
    }, extra || {});
    if (collapsible) {
      column.collapsed_width = TYPICAL_SERVICE_TERM_GANTT_COLLAPSED_COLUMN_WIDTH;
      column.$policyTypicalServiceTermCollapsible = true;
      column.$policyTypicalServiceTermCollapsed = collapsed;
      column.$policyTypicalServiceTermExpandedWidth = expandedWidth;
    }
    return column;
  }

  function saveTypicalServiceTermGanttColumns(gantt) {
    if (!P || !Array.isArray(gantt?.config?.columns)) return;
    const widths = {};
    const collapsed = {};
    gantt.config.columns.forEach(function (column) {
      if (!column?.name || !Number.isFinite(Number(column.width))) return;
      widths[column.name] = isTypicalServiceTermGanttColumnCollapsed(column)
        ? getTypicalServiceTermGanttColumnExpandedWidth(column)
        : Math.round(Number(column.width));
      if (isTypicalServiceTermGanttColumnCollapsed(column)) collapsed[column.name] = true;
    });
    widths.__collapsed = collapsed;
    P.set(TYPICAL_SERVICE_TERM_GANTT_COLUMNS_PREF_KEY, widths);
  }

  function getTypicalServiceTermGanttColumnsWidth(gantt) {
    if (!Array.isArray(gantt?.config?.columns)) return getTypicalServiceTermGanttGridWidth();
    const width = gantt.config.columns.reduce(function (total, column) {
      return total + (Number(column.width) || 0);
    }, 0);
    return Math.max(80, Math.min(1200, Math.round(width || getTypicalServiceTermGanttGridWidth())));
  }

  function getTypicalServiceTermGanttWbsCode(gantt, task) {
    if (!gantt || !task) return '';
    if (typeof gantt.getParent === 'function' && typeof gantt.getChildren === 'function') {
      const parts = [];
      let taskId = task.id;
      let guard = 0;
      while (
        taskId !== undefined &&
        taskId !== null &&
        taskId !== '' &&
        taskId !== gantt.config?.root_id &&
        guard < 50
      ) {
        guard += 1;
        const parentId = gantt.getParent(taskId);
        const siblings = (gantt.getChildren(parentId) || []).filter(function (siblingId) {
          try {
            const sibling = typeof gantt.getTask === 'function' ? gantt.getTask(siblingId) : null;
            return sibling?.type !== gantt.config?.types?.placeholder;
          } catch (_) {
            return true;
          }
        });
        const siblingIndex = siblings.findIndex(function (siblingId) {
          return String(siblingId) === String(taskId);
        });
        if (siblingIndex < 0) break;
        parts.unshift(String(siblingIndex + 1));
        taskId = parentId;
      }
      if (parts.length) return parts.join('.');
    }
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

  function getTypicalServiceTermGanttLinkTypeOptions(gantt) {
    const types = gantt?.config?.links || { finish_to_start: '0', start_to_start: '1', finish_to_finish: '2', start_to_finish: '3' };
    return [
      { key: String(types.finish_to_start), code: 'ОН', label: 'ОН' },
      { key: String(types.start_to_start), code: 'НН', label: 'НН' },
      { key: String(types.finish_to_finish), code: 'ОО', label: 'ОО' },
      { key: String(types.start_to_finish), code: 'НО', label: 'НО' },
    ];
  }

  function normalizeTypicalServiceTermGanttLinkType(gantt, value) {
    const raw = normalizeFilterValue(value);
    const options = getTypicalServiceTermGanttLinkTypeOptions(gantt);
    return options.some(function (option) { return option.key === raw; }) ? raw : options[0].key;
  }

  function normalizeTypicalServiceTermGanttLag(value) {
    const lag = Number(String(value ?? '').replace(',', '.'));
    return Number.isFinite(lag) ? Math.round(lag) : 0;
  }

  function formatTypicalServiceTermGanttLag(lag) {
    const normalized = normalizeTypicalServiceTermGanttLag(lag);
    if (!normalized) return '';
    return (normalized > 0 ? '+' : '') + normalized;
  }

  function normalizeTypicalServiceTermGanttLagMode(value) {
    return String(value || '').toLowerCase() === 'auto' ? 'auto' : 'fixed';
  }

  function computeTypicalServiceTermGanttEffectiveLag(gantt, sourceTask, targetTask, linkType) {
    if (!sourceTask || !targetTask) return null;
    if (!(sourceTask.start_date instanceof Date) || !(sourceTask.end_date instanceof Date)) return null;
    if (!(targetTask.start_date instanceof Date) || !(targetTask.end_date instanceof Date)) return null;
    const types = gantt?.config?.links || {};
    const dayDiff = function (a, b) {
      return Math.round((a.getTime() - b.getTime()) / 86400000);
    };
    const linkTypeStr = String(linkType);
    if (linkTypeStr === String(types.start_to_start)) return dayDiff(targetTask.start_date, sourceTask.start_date);
    if (linkTypeStr === String(types.finish_to_finish)) return dayDiff(targetTask.end_date, sourceTask.end_date);
    if (linkTypeStr === String(types.start_to_finish)) return dayDiff(targetTask.end_date, sourceTask.start_date);
    return dayDiff(targetTask.start_date, sourceTask.end_date);
  }

  function getTypicalServiceTermGanttDisplayLag(gantt, link) {
    if (!link) return 0;
    const mode = normalizeTypicalServiceTermGanttLagMode(link.lag_mode);
    if (mode === 'fixed') return normalizeTypicalServiceTermGanttLag(link.lag);
    if (!gantt || typeof gantt.getTask !== 'function') return normalizeTypicalServiceTermGanttLag(link.lag);
    let sourceTask = null;
    let targetTask = null;
    try {
      sourceTask = gantt.getTask(link.source);
      targetTask = gantt.getTask(link.target);
    } catch (_) {
      sourceTask = null;
      targetTask = null;
    }
    const effective = computeTypicalServiceTermGanttEffectiveLag(gantt, sourceTask, targetTask, link.type);
    return Number.isFinite(effective) ? effective : normalizeTypicalServiceTermGanttLag(link.lag);
  }

  function formatTypicalServiceTermGanttPredecessors(gantt, task) {
    if (!gantt || !task || typeof gantt.getLinks !== 'function') return '';
    const taskId = String(task.id);
    return gantt.getLinks()
      .filter(function (link) {
        return String(link?.target) === taskId || String(link?.source) === taskId;
      })
      .map(function (link) {
        const otherId = String(link?.target) === taskId ? link?.source : link?.target;
        let otherTask = null;
        try {
          otherTask = typeof gantt.getTask === 'function' ? gantt.getTask(otherId) : null;
        } catch (_) {
          otherTask = null;
        }
        const wbs = getTypicalServiceTermGanttWbsCode(gantt, otherTask);
        return wbs ? wbs + getTypicalServiceTermGanttLinkTypeCode(gantt, link) + formatTypicalServiceTermGanttLag(getTypicalServiceTermGanttDisplayLag(gantt, link)) : '';
      })
      .filter(Boolean)
      .join(', ');
  }

  function formatTypicalServiceTermGanttDuration(task) {
    const duration = Number(task?.duration);
    const value = Number.isFinite(duration) ? Math.round(duration) : '';
    return typicalServiceTermGanttGridValueHtml(value, 'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--duration');
  }

  function calculateTypicalServiceTermGanttCalendarDurationDays(startDate, endDate, task) {
    if (!(startDate instanceof Date) || Number.isNaN(startDate.getTime())) return null;
    if (!(endDate instanceof Date) || Number.isNaN(endDate.getTime())) return null;
    if (task?.type === 'milestone') return 0;
    const msPerDay = 24 * 60 * 60 * 1000;
    const startUtc = Date.UTC(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
    const endUtc = Date.UTC(endDate.getFullYear(), endDate.getMonth(), endDate.getDate());
    return Math.max(0, Math.round((endUtc - startUtc) / msPerDay));
  }

  function formatTypicalServiceTermGanttCalendarDuration(task) {
    const value = calculateTypicalServiceTermGanttCalendarDurationDays(
      parsePolicyGanttDate(task?.start_date),
      parsePolicyGanttDate(task?.end_date),
      task
    );
    return typicalServiceTermGanttGridValueHtml(value === null ? '' : value, 'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--duration');
  }

  function getTypicalServiceTermGanttTaskHeaderHtml() {
    return '<span class="typical-service-term-gantt-task-header">' +
      '<span class="typical-service-term-gantt-task-header-title">Задача</span>' +
      '<span class="typical-service-term-gantt-outline-controls" aria-label="Уровень раскрытия задач">' +
      [1, 2, 3, 4].map(function (level) {
        return '<button type="button" class="typical-service-term-gantt-outline-btn" data-gantt-outline-level="' + level + '" title="Показать до уровня ' + level + '">' + level + '</button>';
      }).join('') +
      '</span>' +
      '</span>';
  }

  function formatTypicalServiceTermGanttProgress(task) {
    const progress = Math.max(0, Math.min(1, Number(task?.progress) || 0));
    return typicalServiceTermGanttGridValueHtml(Math.round(progress * 100) + '%', 'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--progress');
  }

  function formatTypicalServiceTermGanttShortDate(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
    if (isTypicalServiceTermGanttAbstractCalendar()) {
      return String(date.getDate()).padStart(2, '0') + '.' +
        String(date.getMonth() + 1).padStart(2, '0') + '.' +
        String(getTypicalServiceTermGanttAbstractYearNumber(date)).padStart(2, '0').slice(-2);
    }
    return String(date.getDate()).padStart(2, '0') + '.' +
      String(date.getMonth() + 1).padStart(2, '0') + '.' +
      String(date.getFullYear()).padStart(4, '0');
  }

  function formatTypicalServiceTermGanttGridDate(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
    const year = isTypicalServiceTermGanttAbstractCalendar()
      ? String(getTypicalServiceTermGanttAbstractYearNumber(date)).padStart(2, '0').slice(-2)
      : String(date.getFullYear()).slice(-2);
    return String(date.getDate()).padStart(2, '0') + '.' +
      String(date.getMonth() + 1).padStart(2, '0') + '.' +
      year;
  }

  function formatTypicalServiceTermGanttWeekdayDate(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
    return '<span class="typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--weekday-date">' +
      '<span class="typical-service-term-gantt-weekday-label">' + TYPICAL_SERVICE_TERM_GANTT_WEEKDAY_LABELS[date.getDay()] + '</span> ' +
      escapePolicyHtml(formatTypicalServiceTermGanttGridDate(date)) +
      '</span>';
  }

  function formatTypicalServiceTermGanttDeadline(task) {
    const deadline = parsePolicyGanttDate(task?.deadline);
    return typicalServiceTermGanttGridValueHtml(
      deadline ? formatTypicalServiceTermGanttShortDate(deadline) : '',
      'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--deadline'
    );
  }

  function formatTypicalServiceTermGanttSpecialty(task) {
    return typicalServiceTermGanttGridValueHtml(
      task?.specialty || '',
      'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--specialty'
    );
  }

  function formatTypicalServiceTermGanttExecutor(task) {
    const value = getTypicalServiceTermGanttExecutorDisplayMode() === TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE
      ? (task?.resource_name || task?.resourceName || '')
      : getTypicalServiceTermGanttExecutorLabel(task?.executor);
    return typicalServiceTermGanttGridValueHtml(
      value,
      'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--executor'
    );
  }

  function getTypicalServiceTermGanttConstraintOptions() {
    return [
      { key: '', code: '', label: 'Нет ограничения' },
      { key: 'asap', code: 'ASAP', label: 'Как можно раньше' },
      { key: 'alap', code: 'ALAP', label: 'Как можно позже' },
      { key: 'snet', code: 'SNET', label: 'Начать не раньше' },
      { key: 'snlt', code: 'SNLT', label: 'Начать не позже' },
      { key: 'fnet', code: 'FNET', label: 'Закончить не раньше' },
      { key: 'fnlt', code: 'FNLT', label: 'Закончить не позже' },
      { key: 'mso', code: 'MSO', label: 'Фиксированное начало' },
      { key: 'mfo', code: 'MFO', label: 'Фиксированное окончание' },
    ];
  }

  function normalizeTypicalServiceTermGanttConstraintType(value) {
    const raw = normalizeFilterValue(value).toLowerCase();
    return getTypicalServiceTermGanttConstraintOptions().some(function (option) {
      return option.key === raw && raw;
    }) ? raw : '';
  }

  function getTypicalServiceTermGanttConstraintOption(type) {
    const normalized = normalizeTypicalServiceTermGanttConstraintType(type);
    return getTypicalServiceTermGanttConstraintOptions().find(function (option) {
      return option.key === normalized;
    }) || getTypicalServiceTermGanttConstraintOptions()[0];
  }

  function clearTypicalServiceTermGanttTaskConstraint(gantt, taskId) {
    if (!gantt || taskId === undefined || taskId === null) return false;
    let task = null;
    try {
      task = typeof gantt.getTask === 'function' ? gantt.getTask(taskId) : null;
    } catch (_) {
      task = null;
    }
    if (!task) return false;
    task.constraint_type = '';
    task.constraint_date = null;
    delete task.constraint_type;
    delete task.constraint_date;
    try {
      if (typeof gantt.updateTask === 'function') {
        gantt.updateTask(task.id);
      } else if (typeof gantt.refreshTask === 'function') {
        gantt.refreshTask(task.id);
      }
    } catch (_) {
      // The task may be in the middle of DHTMLX lightbox commit; render below is enough.
    }
    const chart = pane()?.querySelector('#typical-service-term-gantt');
    renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
    return true;
  }

  function formatTypicalServiceTermGanttConstraint(task) {
    const type = normalizeTypicalServiceTermGanttConstraintType(task?.constraint_type);
    if (!type) {
      return typicalServiceTermGanttGridValueHtml('', 'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--constraint');
    }
    const option = getTypicalServiceTermGanttConstraintOption(type);
    const constraintDate = parsePolicyGanttDate(task?.constraint_date);
    const value = option.code + (constraintDate ? ' ' + formatTypicalServiceTermGanttShortDate(constraintDate) : '');
    return typicalServiceTermGanttGridValueHtml(value, 'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--constraint');
  }

  function isTypicalServiceTermGanttDeadlineMissed(task) {
    const deadline = parsePolicyGanttDate(task?.deadline);
    const endDate = parsePolicyGanttDate(task?.end_date);
    if (!deadline || !endDate) return false;
    return endDate.getTime() > deadline.getTime();
  }

  // Returns the sum of `min_width` across grid columns; used as the threshold below which
  // the grid switches into "narrow mode" — dhtmlxGantt itself can't shrink the cell below
  // that, so the visual narrowing is then done via a CSS overlay scrollbar (see
  // syncTypicalServiceTermGanttNarrowMode).
  function getTypicalServiceTermGanttColumnsMinWidth(gantt) {
    if (!Array.isArray(gantt?.config?.columns)) return 0;
    return gantt.config.columns.reduce(function (total, column) {
      if (isTypicalServiceTermGanttColumnCollapsed(column)) {
        return total + getTypicalServiceTermGanttColumnCollapsedWidth(column);
      }
      const min = Number(column.min_width);
      const width = Number(column.width);
      const v = Number.isFinite(min) && min > 0 ? min : (Number.isFinite(width) ? width : 0);
      return total + v;
    }, 0);
  }

  function syncTypicalServiceTermGanttNarrowMode(gantt, chart) {
    if (!gantt || !chart) return;
    const editor = chart.closest('.typical-service-term-gantt-editor') || chart;
    const minSum = getTypicalServiceTermGanttColumnsMinWidth(gantt);
    const desired = Number(gantt?.$policyTypicalServiceTermDesiredGridWidth)
      || Number(gantt?.config?.grid_width)
      || 0;
    const isNarrow = desired > 0 && minSum > 0 && desired < minSum;
    editor.classList.toggle('typical-service-term-gantt-editor--grid-narrow', isNarrow);
  }

  function patchTypicalServiceTermGanttGridLimits(gantt) {
    if (!gantt || typeof gantt.$ui?.getView !== 'function') return false;
    const gridView = gantt.$ui.getView('grid');
    if (!gridView) return false;
    // Mark the grid as scrollable + elastic so dhtmlxGantt's setSize keeps the inner
    // grid_scale width tied to the natural columns sum while letting the outer cell width
    // freely shrink — this is what gives us the horizontal overflow scrollbar in the
    // narrow phase below the column min_widths sum.
    if (gridView.$config) gridView.$config.scrollable = true;
    if (gridView.$policyTypicalServiceTermLimitsPatched) return false;
    const originalLimits = typeof gridView._getGridWidthLimits === 'function'
      ? gridView._getGridWidthLimits.bind(gridView)
      : null;
    if (!originalLimits) return false;
    gridView.$policyTypicalServiceTermLimitsPatched = true;
    // Drop the lower bound so onBeforeResize doesn't snap grid_width back up to the
    // column min_widths sum.
    gridView._getGridWidthLimits = function () {
      const limits = originalLimits();
      return [0, limits ? limits[1] : undefined];
    };
    // gridView.refresh() (called at the end of setSize) invokes _calculateGridWidth which
    // — when all columns have explicit widths and autofit is off — forcibly resets
    // gantt.config.grid_width AND the grid cell width back to the columns sum. That
    // defeats our narrow-phase (desired < minSum) logic. Wrap it to restore both values
    // whenever the user intentionally wants the cell narrower than the columns sum.
    if (typeof gridView._calculateGridWidth === 'function') {
      const originalCalc = gridView._calculateGridWidth.bind(gridView);
      gridView._calculateGridWidth = function () {
        originalCalc();
        const desired = Number(gantt.$policyTypicalServiceTermDesiredGridWidth) || 0;
        if (desired <= 0) return;
        if (Number(gantt.config?.grid_width) !== desired) {
          gantt.config.grid_width = desired;
        }
        if (gridView.$config && gridView.$config.width !== desired - 1) {
          gridView.$config.width = Math.max(0, desired - 1);
        }
        if (gridView.$parent && gridView.$parent.$config) {
          // Mirror the cell width too so the next layout pass keeps the cell narrowed.
          gridView.$parent.$config.width = desired;
        }
      };
    }
    // gridView.getSize() reports `scrollWidth` as the viewport width (= $config.width),
    // so dhtmlx's ScrollbarCell._getScrollSize() never detects horizontal overflow even
    // when the inner $grid_scale / $grid_data are wider than the viewport (Phase 2).
    // Patch getSize so scrollWidth reflects the actual columns sum — that's what the
    // scrollbar's "should I show?" check compares against the viewport width.
    //
    // Only do this in the true narrow phase (desired < min-widths sum). In the
    // interpolated phase (minSum <= desired < naturalSum) the columns sum tracks
    // `desired` ± rounding, while `_calculateGridWidth` (patched above) pins
    // gridView.$config.width to `desired - 1`. That always leaves colsSum a pixel
    // or two above the viewport, which would otherwise convince DHTMLX the grid
    // still overflows — keeping the horizontal scrollbar visible after the user
    // dragged the divider back out of the narrow phase.
    if (typeof gridView.getSize === 'function') {
      const originalGetSize = gridView.getSize.bind(gridView);
      gridView.getSize = function () {
        const size = originalGetSize();
        if (gridView.$config && gridView.$config.scrollable && Array.isArray(gantt.config?.columns)) {
          let colsSum = 0;
          let minSum = 0;
          for (let i = 0; i < gantt.config.columns.length; i++) {
            const col = gantt.config.columns[i];
            colsSum += Number(col.width) || 0;
            if (isTypicalServiceTermGanttColumnCollapsed(col)) {
              minSum += getTypicalServiceTermGanttColumnCollapsedWidth(col);
            } else {
              const m = Number(col.min_width);
              minSum += Number.isFinite(m) && m > 0 ? m : (Number(col.width) || 0);
            }
          }
          const desired = Number(gantt.$policyTypicalServiceTermDesiredGridWidth) || 0;
          const inNarrow = desired > 0 && minSum > 0 && desired < minSum;
          if (inNarrow && colsSum > (size.scrollWidth || 0)) {
            size.scrollWidth = colsSum;
          }
        }
        return size;
      };
    }
    return true;
  }

  // Snapshot of the per-column "natural" widths (what they were when the grid was first
  // configured); used by applyTypicalServiceTermGanttColumnsForWidth to know how far each
  // column can grow before columns are at full width.
  function getTypicalServiceTermGanttColumnNaturals(gantt) {
    if (!Array.isArray(gantt?.config?.columns)) return [];
    if (!Array.isArray(gantt.$policyTypicalServiceTermColumnNaturals)
        || gantt.$policyTypicalServiceTermColumnNaturals.length !== gantt.config.columns.length) {
      gantt.$policyTypicalServiceTermColumnNaturals = gantt.config.columns.map(function (col) {
        const expanded = Number(col?.$policyTypicalServiceTermExpandedWidth);
        if (Number.isFinite(expanded) && expanded > 0) return expanded;
        const n = Number(col?.width);
        const m = Number(col?.min_width);
        return Number.isFinite(n) && n > 0 ? n : (Number.isFinite(m) && m > 0 ? m : 0);
      });
    }
    return gantt.$policyTypicalServiceTermColumnNaturals;
  }

  // Distributes `desired` total across the grid columns:
  //   * desired ≥ natural sum  → keep columns at their natural widths;
  //   * minSum ≤ desired < natural sum → linear interpolation between min and natural;
  //   * desired < minSum        → keep columns at their min_widths so the dhtmlxGantt
  //     elastic+scrollable branch produces an inner overflow scrollbar.
  function applyTypicalServiceTermGanttColumnsForWidth(gantt, desired) {
    if (!Array.isArray(gantt?.config?.columns)) return;
    const cols = gantt.config.columns;
    const naturals = getTypicalServiceTermGanttColumnNaturals(gantt);
    let naturalSum = 0;
    let minSum = 0;
    for (let i = 0; i < cols.length; i++) {
      const collapsed = isTypicalServiceTermGanttColumnCollapsed(cols[i]);
      const min = collapsed
        ? getTypicalServiceTermGanttColumnCollapsedWidth(cols[i])
        : Number(cols[i].min_width) || 0;
      const nat = collapsed ? min : Number(naturals[i]) || min;
      minSum += min;
      naturalSum += nat;
    }
    const span = Math.max(1, naturalSum - minSum);
    for (let i = 0; i < cols.length; i++) {
      const collapsed = isTypicalServiceTermGanttColumnCollapsed(cols[i]);
      const min = collapsed
        ? getTypicalServiceTermGanttColumnCollapsedWidth(cols[i])
        : Number(cols[i].min_width) || 0;
      const nat = collapsed ? min : Number(naturals[i]) || min;
      let next;
      if (desired >= naturalSum) {
        next = nat;
      } else if (desired >= minSum) {
        const ratio = (desired - minSum) / span;
        next = Math.round(min + (nat - min) * ratio);
      } else {
        next = min;
      }
      if (next !== cols[i].width) cols[i].width = next;
    }
  }

  function restoreTypicalServiceTermGanttGridWidth(gantt) {
    if (!gantt) return;
    const savedGridWidth = (typeof P !== 'undefined' && P)
      ? Number(P.get(TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY, NaN))
      : NaN;
    if (!Number.isFinite(savedGridWidth)) return;
    const target = Math.max(80, Math.min(1200, Math.round(savedGridWidth)));
    gantt.$policyTypicalServiceTermDesiredGridWidth = target;
    applyTypicalServiceTermGanttColumnsForWidth(gantt, target);
    if (Number(gantt.config?.grid_width) === target) return;
    gantt.config.grid_width = target;
    if (typeof gantt.setSizes === 'function') gantt.setSizes();
  }

  function isTypicalServiceTermGanttColumnCollapsible(column) {
    return !!(column?.$policyTypicalServiceTermCollapsible && isTypicalServiceTermGanttColumnNameCollapsible(column.name));
  }

  function syncTypicalServiceTermGanttColumnCollapseState(gantt, chart) {
    if (!gantt || !chart || !Array.isArray(gantt.config?.columns)) return;
    const columns = gantt.config.columns;
    chart.querySelectorAll('.gantt_grid_scale .gantt_grid_head_cell[data-column-index]').forEach(function (cell) {
      const index = Number(cell.dataset.columnIndex);
      const column = columns[index];
      const collapsible = isTypicalServiceTermGanttColumnCollapsible(column);
      const collapsed = collapsible && isTypicalServiceTermGanttColumnCollapsed(column);
      cell.classList.toggle('typical-service-term-gantt-grid-column--collapsible', collapsible);
      cell.classList.toggle('typical-service-term-gantt-grid-column--collapsed', collapsed);
      let button = cell.querySelector(':scope > .typical-service-term-gantt-column-collapse-btn');
      if (!collapsible) {
        if (button) button.remove();
        return;
      }
      if (!button) {
        button = document.createElement('button');
        button.type = 'button';
        button.className = 'typical-service-term-gantt-column-collapse-btn';
        button.dataset.columnIndex = String(index);
        cell.appendChild(button);
      }
      button.dataset.columnIndex = String(index);
      button.innerHTML = '<i class="bi bi-' + (collapsed ? 'plus-square' : 'dash-square') + '" aria-hidden="true"></i>';
      button.title = collapsed ? 'Развернуть столбец' : 'Свернуть столбец';
      button.setAttribute('aria-label', button.title);
      button.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    });
    columns.forEach(function (column, index) {
      if (!column?.name) return;
      const selector = [
        '.gantt_grid_data .gantt_cell[data-column-name="' + escapeTypicalServiceTermGanttSelectorValue(column.name) + '"]',
        '.gantt_grid_data .gantt_row .gantt_cell:nth-child(' + (index + 1) + ')',
      ].join(', ');
      chart.querySelectorAll(selector).forEach(function (cell) {
        cell.classList.toggle(
          'typical-service-term-gantt-grid-column--collapsed',
          isTypicalServiceTermGanttColumnCollapsible(column) && isTypicalServiceTermGanttColumnCollapsed(column)
        );
      });
    });
  }

  function resyncTypicalServiceTermGanttColumnCollapseStateSoon(gantt, chart) {
    if (!gantt || !chart) return;
    const sync = function () {
      if (!document.body.contains(chart)) return;
      syncTypicalServiceTermGanttColumnCollapseState(gantt, chart);
    };
    sync();
    requestAnimationFrame(function () {
      sync();
      requestAnimationFrame(sync);
    });
    [0, 50, 150, 300, 600].forEach(function (delay) {
      setTimeout(sync, delay);
    });
  }

  function installTypicalServiceTermGanttColumnCollapseObserver(gantt, chart) {
    if (!gantt || !chart || typeof MutationObserver !== 'function') return;
    const gridData = chart.querySelector('.gantt_grid_data');
    if (!gridData) return;
    if (gantt.$policyTypicalServiceTermColumnCollapseObserverTarget === gridData) return;
    if (gantt.$policyTypicalServiceTermColumnCollapseObserver) {
      try { gantt.$policyTypicalServiceTermColumnCollapseObserver.disconnect(); } catch (_) { /* ignore */ }
    }
    let scheduled = false;
    const observer = new MutationObserver(function () {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(function () {
        scheduled = false;
        resyncTypicalServiceTermGanttColumnCollapseStateSoon(gantt, chart);
      });
    });
    observer.observe(gridData, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'style'],
    });
    gantt.$policyTypicalServiceTermColumnCollapseObserver = observer;
    gantt.$policyTypicalServiceTermColumnCollapseObserverTarget = gridData;
  }

  function toggleTypicalServiceTermGanttColumnCollapsed(gantt, chart, index) {
    if (!gantt || !chart || !Array.isArray(gantt.config?.columns)) return;
    const column = gantt.config.columns[index];
    if (!isTypicalServiceTermGanttColumnCollapsible(column)) return;
    const oldWidth = Number(column.width) || getTypicalServiceTermGanttColumnCollapsedWidth(column);
    if (isTypicalServiceTermGanttColumnCollapsed(column)) {
      column.$policyTypicalServiceTermCollapsed = false;
      column.width = getTypicalServiceTermGanttColumnExpandedWidth(column);
    } else {
      const currentExpanded = Number(column.width);
      if (Number.isFinite(currentExpanded) && currentExpanded > getTypicalServiceTermGanttColumnCollapsedWidth(column)) {
        column.$policyTypicalServiceTermExpandedWidth = Math.round(currentExpanded);
      }
      column.$policyTypicalServiceTermCollapsed = true;
      column.width = getTypicalServiceTermGanttColumnCollapsedWidth(column);
    }
    const nextWidth = Number(column.width) || oldWidth;
    if (Array.isArray(gantt.$policyTypicalServiceTermColumnNaturals)
        && gantt.$policyTypicalServiceTermColumnNaturals.length > index
        && !isTypicalServiceTermGanttColumnCollapsed(column)) {
      gantt.$policyTypicalServiceTermColumnNaturals[index] = nextWidth;
      column.$policyTypicalServiceTermExpandedWidth = nextWidth;
    }
    const desiredBase = Number(gantt.$policyTypicalServiceTermDesiredGridWidth)
      || Number(gantt.config?.grid_width)
      || getTypicalServiceTermGanttColumnsWidth(gantt);
    const desired = Math.max(80, Math.min(1200, Math.round(desiredBase + nextWidth - oldWidth)));
    gantt.$policyTypicalServiceTermDesiredGridWidth = desired;
    gantt.config.grid_width = desired;
    if (typeof gantt.render === 'function') {
      gantt.render();
    } else if (typeof gantt.setSizes === 'function') {
      gantt.setSizes();
    }
    syncTypicalServiceTermGanttNarrowMode(gantt, chart);
    installTypicalServiceTermGanttColumnResizeHandles(gantt, chart);
    alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
    if (P) P.set(TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY, desired);
    saveTypicalServiceTermGanttColumns(gantt);
  }

  function installTypicalServiceTermGanttColumnResizeHandles(gantt, chart) {
    if (!gantt || !chart) return;
    if (patchTypicalServiceTermGanttGridLimits(gantt)) {
      // Init may have clamped grid_width back up to the natural minimum before the patch
      // landed; restore the user's saved width so narrow mode persists across reloads.
      restoreTypicalServiceTermGanttGridWidth(gantt);
    }
    const editor = chart.closest('.typical-service-term-gantt-editor') || chart;
    const syncTimelineHorizontalScrollbar = function () {
      // Use the layout *cells* rather than the inner .gantt_grid / .gantt_task —
      // in narrow mode `.gantt_grid` is `display: inline-block` and its rect
      // tracks the visible columns sum (clipped by overflow) instead of the
      // cell, so a scrollbar sized to it would either fall short of the
      // divider or overshoot it. The cell rects always go edge-to-edge to the
      // divider, which is the alignment we want.
      //
      // marginLeft is set relative to the scrollbar's own parent layout cell
      // (not the chart). When only one of the two scrollbars is needed,
      // dhtmlxGantt gives the visible scrollbar's parent the full bottom row,
      // so its parent already sits at chart left and a chart-relative offset
      // would also work. But when BOTH scrollbars are visible, the bottom row
      // holds two cells side by side and the timeline scrollbar's parent
      // already starts to the right of the chart's left edge — using a
      // chart-relative offset would double-count that and push the timeline
      // scrollbar far past where it should sit.
      const positionScrollbar = function (cell, scrollbar) {
        if (!cell || !scrollbar) return;
        const cellRect = cell.getBoundingClientRect();
        const parent = scrollbar.parentElement;
        const parentRect = parent ? parent.getBoundingClientRect() : { left: cellRect.left };
        scrollbar.style.marginLeft = Math.round(cellRect.left - parentRect.left) + 'px';
        scrollbar.style.width = Math.max(0, Math.round(cellRect.width)) + 'px';
      };
      positionScrollbar(
        chart.querySelector('.gantt_layout_cell.grid_cell'),
        gantt.$ui?.getView?.('gridScrollHor')?.$view
      );
      positionScrollbar(
        chart.querySelector('.gantt_layout_cell.timeline_cell'),
        gantt.$ui?.getView?.('scrollHor')?.$view
      );
    };
    const syncGridHandle = function () {
      const grid = chart.querySelector('.gantt_grid');
      // Drop any stale handle attached to the chart from a previous version.
      chart.querySelectorAll(':scope > .typical-service-term-gantt-grid-resizer').forEach(function (node) {
        if (node.parentElement === chart) node.remove();
      });
      let handle = editor.querySelector(':scope > .typical-service-term-gantt-grid-resizer');
      if (!grid) {
        if (handle) handle.remove();
        editor.classList.remove('typical-service-term-gantt-editor--grid-narrow');
        return;
      }
      if (!handle) {
        handle = document.createElement('span');
        handle.className = 'typical-service-term-gantt-grid-resizer';
        handle.setAttribute('aria-hidden', 'true');
        editor.appendChild(handle);
      }
      const isNarrow = isTypicalServiceTermGanttGridNarrow(gantt);
      handle.classList.toggle('typical-service-term-gantt-grid-resizer--narrow', isNarrow);
      editor.classList.toggle('typical-service-term-gantt-editor--grid-narrow', isNarrow);
      // Apply the narrow-mode CSS BEFORE measuring so getBoundingClientRect reflects the
      // visually-cropped grid width.
      syncTypicalServiceTermGanttNarrowMode(gantt, chart);
      const editorRect = editor.getBoundingClientRect();
      const gridRect = grid.getBoundingClientRect();
      const gridScale = chart.querySelector('.gantt_grid_scale');
      const gridScaleRect = gridScale?.getBoundingClientRect();
      const gridData = chart.querySelector('.gantt_grid_data');
      const gridDataRect = gridData?.getBoundingClientRect();
      const toolbar = editor.querySelector('.typical-service-term-gantt-toolbar');
      const toolbarRect = toolbar?.getBoundingClientRect();
      // In narrow mode .gantt_grid is already visually cropped via CSS to the visible
      // grid width, so gridRect.right corresponds to the user-visible edge in both modes.
      handle.style.left = Math.round(gridRect.right - editorRect.left) + 'px';
      if (isNarrow && toolbarRect) {
        handle.style.top = Math.max(0, Math.round(toolbarRect.bottom - editorRect.top) - 1) + 'px';
      } else if (gridScaleRect) {
        handle.style.top = Math.max(0, Math.round(gridScaleRect.bottom - editorRect.top) - 1) + 'px';
      } else {
        handle.style.top = '0px';
      }
      if (gridDataRect) {
        handle.style.bottom = Math.max(0, Math.round(editorRect.bottom - gridDataRect.bottom)) + 'px';
      } else {
        handle.style.bottom = '0px';
      }
      syncTimelineHorizontalScrollbar();
    };
    syncGridHandle();
    syncTypicalServiceTermGanttColumnCollapseState(gantt, chart);
    installTypicalServiceTermGanttColumnCollapseObserver(gantt, chart);
    let lastColumnHandleSeen = false;
    const headerCells = chart.querySelectorAll('.gantt_grid_scale .gantt_grid_head_cell[data-column-index]');
    headerCells.forEach(function (cell, index) {
      const columnIndex = Number(cell.dataset.columnIndex);
      const column = gantt.config?.columns?.[columnIndex];
      if (isTypicalServiceTermGanttColumnCollapsed(column)) {
        cell.querySelectorAll('.typical-service-term-gantt-column-resizer').forEach(function (handle) {
          handle.remove();
        });
        return;
      }
      const isLastHeaderCell = cell.classList.contains('gantt_last_cell') || index === headerCells.length - 1;
      if (isLastHeaderCell) {
        cell.querySelectorAll('.typical-service-term-gantt-column-resizer').forEach(function (handle) {
          handle.remove();
        });
        chart.querySelectorAll('.typical-service-term-gantt-column-resizer--last').forEach(function (handle) {
          handle.remove();
        });
        let lastHandle = editor.querySelector(':scope > .typical-service-term-gantt-column-resizer--last');
        if (!lastHandle) {
          lastHandle = document.createElement('span');
          lastHandle.className = 'typical-service-term-gantt-column-resizer typical-service-term-gantt-column-resizer--last';
          lastHandle.setAttribute('aria-hidden', 'true');
          editor.appendChild(lastHandle);
        }
        const cellRect = cell.getBoundingClientRect();
        const grid = chart.querySelector('.gantt_grid');
        const gridRect = grid?.getBoundingClientRect();
        lastHandle.dataset.columnIndex = cell.dataset.columnIndex || '';
        lastHandle.style.display = '';
        lastHandle.style.left = Math.round((gridRect?.right || cellRect.right) - editor.getBoundingClientRect().left) + 'px';
        lastHandle.style.top = Math.round(cellRect.top - editor.getBoundingClientRect().top) + 'px';
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
      editor.querySelector(':scope > .typical-service-term-gantt-column-resizer--last')?.remove();
    }

    if (!gantt.$policyTypicalServiceTermColumnHandlesEventsBound && typeof gantt.attachEvent === 'function') {
      gantt.$policyTypicalServiceTermColumnHandlesEventsBound = true;
      const reinstall = function () {
        const currentChart = typicalServiceTermGanttChartEl();
        if (!currentChart) return true;
        requestAnimationFrame(function () {
          installTypicalServiceTermGanttColumnResizeHandles(gantt, currentChart);
        });
        return true;
      };
      policyGanttAttachEvent('onDataRender', reinstall);
      policyGanttAttachEvent('onGanttRender', reinstall);
      policyGanttAttachEvent('onAfterTaskUpdate', reinstall);
      policyGanttAttachEvent('onAfterTaskAdd', reinstall);
      policyGanttAttachEvent('onAfterTaskDelete', reinstall);
      policyGanttAttachEvent('onAfterTaskDrag', reinstall);
      policyGanttAttachEvent('onAfterTaskMove', reinstall);
      policyGanttAttachEvent('onRowDragEnd', reinstall);
      policyGanttAttachEvent('onAfterLinkAdd', reinstall);
      policyGanttAttachEvent('onAfterLinkUpdate', reinstall);
      policyGanttAttachEvent('onAfterLinkDelete', reinstall);
    }

    if (editor.dataset.typicalServiceTermGanttColumnResizeBound === '1') return;
    editor.dataset.typicalServiceTermGanttColumnResizeBound = '1';
    // The mousedown listener is bound exactly once per editor DOM element. The
    // `gantt` / `chart` references it captures from the outer call live for the
    // entire lifetime of that editor — but the underlying gantt INSTANCE can be
    // disposed and re-created out from under us (htmx swaps the policy pane on
    // save and our htmx:afterSwap hook calls disposeTypicalServiceTermGanttInstance
    // when the bound container leaves the document). After dispose, GanttEngine.dispose
    // swaps `setSizes / render / refreshData` for no-ops; if a stale closure over the
    // disposed instance is still attached to the (still-mounted) editor we'd
    // visually drag the blue handle but `setSizes()` would do nothing — exactly
    // the "blue divider moves alone, timeline doesn't follow" symptom. The
    // `resolveGantt` / `resolveChart` helpers below always look up the live
    // instance and the live chart container so we never operate on a stranded
    // reference.
    const resolveGantt = function () {
      const live = window.__policyTypicalServiceTermGantt;
      if (live && !live.$gantt_engine_disposed && typeof live.setSizes === 'function') {
        return live;
      }
      return getTypicalServiceTermGanttInstance();
    };
    const resolveChart = function () {
      return typicalServiceTermGanttChartEl() || chart;
    };
    editor.addEventListener('click', function (event) {
      const button = event.target?.closest?.('.typical-service-term-gantt-column-collapse-btn');
      if (!button || !editor.contains(button)) return;
      event.preventDefault();
      event.stopPropagation();
      const liveChart = resolveChart();
      ensureTypicalServiceTermGanttOwnership(liveChart);
      const liveGantt = resolveGantt();
      const index = Number(button.dataset.columnIndex);
      toggleTypicalServiceTermGanttColumnCollapsed(liveGantt, liveChart, index);
    });
    editor.addEventListener('mousedown', function (event) {
      const gridResizer = event.target?.closest?.('.typical-service-term-gantt-grid-resizer, .gantt_resizer, .gantt_grid_resize_wrap');
      if (!gridResizer || !editor.contains(gridResizer)) return;
      if (gridResizer.classList.contains('typical-service-term-gantt-grid-resizer')) {
        event.preventDefault();
        event.stopPropagation();
        const liveChart = resolveChart();
        // Another section (e.g. proposals' payment chart) may have stolen the
        // shared dhtmlxGantt instance from our chart host since the editor was
        // last opened — check ownership before driving setSizes(), otherwise
        // we would resize the stranger's gantt and leave our chart blank.
        ensureTypicalServiceTermGanttOwnership(liveChart);
        const liveGantt = resolveGantt();
        if (!liveGantt || typeof liveGantt.setSizes !== 'function') return;
        const editorRectAtStart = editor.getBoundingClientRect();
        const handleStartLeft = parseFloat(gridResizer.style.left) || 0;
        const handleGrabOffset = (event.clientX - editorRectAtStart.left) - handleStartLeft;
        const chartWidth = liveChart.getBoundingClientRect().width || 1200;
        const maxWidth = Math.max(80, Math.min(1200, Math.round(chartWidth - 240)));
        gridResizer.classList.add('is-resizing');

        const applyDesiredWidth = function (desired) {
          // Re-resolve every frame so a mid-drag htmx swap (or stale closure) can't
          // strand us on a disposed instance whose setSizes is a no-op.
          const g = resolveGantt();
          const c = resolveChart();
          if (!g || typeof g.setSizes !== 'function') return;
          g.$policyTypicalServiceTermDesiredGridWidth = desired;
          // Phase 1 (proportional column shrink) and phase 2 (columns at min_width with
          // overflow scroll) are both implemented by pre-distributing column widths here
          // and letting dhtmlxGantt's grid_elastic_columns + scrollable=true branch flow
          // the layout cells around the resulting cell width.
          applyTypicalServiceTermGanttColumnsForWidth(g, desired);
          g.config.grid_width = desired;
          g.setSizes();
          syncTypicalServiceTermGanttNarrowMode(g, c);
          syncGridHandle();
          syncTimelineHorizontalScrollbar();
          installTypicalServiceTermGanttColumnResizeHandles(g, c);
          alignTypicalServiceTermGanttMilestoneLinks(g, c);
        };

        const onMove = function (moveEvent) {
          // Always derive the desired width from the absolute cursor position relative to
          // the editor — this keeps the divider glued to the cursor even if dhtmlxGantt
          // briefly normalises grid_width inside setSizes.
          const editorRect = editor.getBoundingClientRect();
          const desiredRaw = (moveEvent.clientX - editorRect.left) - handleGrabOffset;
          const desired = Math.max(80, Math.min(maxWidth, Math.round(desiredRaw)));
          applyDesiredWidth(desired);
          // Pin the visible divider to the cursor regardless of what syncGridHandle just
          // measured — guarantees no perceived "stuck" feeling even if the underlying
          // layout still has to settle after this move.
          gridResizer.style.left = desired + 'px';
        };

        const onUp = function () {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          gridResizer.classList.remove('is-resizing');
          const g = resolveGantt();
          const c = resolveChart();
          if (g && typeof g.setSizes === 'function') {
            syncTypicalServiceTermGanttNarrowMode(g, c);
            syncGridHandle();
            syncTimelineHorizontalScrollbar();
            installTypicalServiceTermGanttColumnResizeHandles(g, c);
            alignTypicalServiceTermGanttMilestoneLinks(g, c);
          }
          if (P && g) {
            const persisted = Math.round(Number(g.$policyTypicalServiceTermDesiredGridWidth)
              || Number(g.config.grid_width)
              || getTypicalServiceTermGanttGridWidth());
            P.set(TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY, persisted);
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
    editor.addEventListener('mousedown', function (event) {
      const handle = event.target?.closest?.('.typical-service-term-gantt-column-resizer');
      if (!handle || !editor.contains(handle)) return;
      const liveGantt = resolveGantt();
      const liveChart = resolveChart();
      if (!liveGantt || typeof liveGantt.render !== 'function') return;
      const index = Number(handle.dataset.columnIndex);
      const column = liveGantt.config.columns?.[index];
      if (!column) return;

      event.preventDefault();
      event.stopPropagation();
      const startX = event.clientX;
      const startWidth = Number(column.width) || handle.parentElement?.offsetWidth || 80;
      const startGridWidth = Number(liveGantt.config.grid_width) || getTypicalServiceTermGanttGridWidth();
      const minWidth = Number(column.min_width) || 44;
      const maxWidth = Number(column.max_width) || 600;
      liveChart.classList.add('typical-service-term-gantt-column-resizing');
      handle.classList.add('is-resizing');

      const onMove = function (moveEvent) {
        const g = resolveGantt();
        const c = resolveChart();
        if (!g || typeof g.render !== 'function') return;
        const nextWidth = Math.max(minWidth, Math.min(maxWidth, Math.round(startWidth + moveEvent.clientX - startX)));
        if (nextWidth === column.width) return;
        column.width = nextWidth;
        // Treat the user's manual column resize as the new "natural" width for that column
        // so subsequent divider drags interpolate between min and this updated width.
        if (Array.isArray(g.$policyTypicalServiceTermColumnNaturals)
            && g.$policyTypicalServiceTermColumnNaturals.length > index) {
          g.$policyTypicalServiceTermColumnNaturals[index] = nextWidth;
        }
        if (isTypicalServiceTermGanttColumnCollapsible(column)) {
          column.$policyTypicalServiceTermExpandedWidth = nextWidth;
        }
        const desired = Math.max(80, Math.min(1200, Math.round(startGridWidth + nextWidth - startWidth)));
        g.$policyTypicalServiceTermDesiredGridWidth = desired;
        g.config.grid_width = desired;
        g.render();
        installTypicalServiceTermGanttColumnResizeHandles(g, c);
        alignTypicalServiceTermGanttMilestoneLinks(g, c);
      };

      const onUp = function () {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        const g = resolveGantt();
        const c = resolveChart();
        c.classList.remove('typical-service-term-gantt-column-resizing');
        handle.classList.remove('is-resizing');
        if (g) {
          alignTypicalServiceTermGanttMilestoneLinks(g, c);
          if (P) {
            P.set(TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY, Math.round(Number(g.$policyTypicalServiceTermDesiredGridWidth) || Number(g.config.grid_width) || getTypicalServiceTermGanttColumnsWidth(g)));
          }
          saveTypicalServiceTermGanttColumns(g);
        }
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp, { once: true });
    });
  }

  function refreshTypicalServiceTermGanttInteractiveChrome(gantt, chart) {
    if (!gantt || !chart) return;
    const refresh = function () {
      if (!document.body.contains(chart) || chart.offsetParent === null) return;
      try {
        installTypicalServiceTermGanttColumnResizeHandles(gantt, chart);
        alignTypicalServiceTermGanttLinkHandles(chart);
        alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
        renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
      } catch (_) {
        // The Gantt DOM can still be settling after a render/apply-scale cycle.
      }
    };
    requestAnimationFrame(function () {
      refresh();
      requestAnimationFrame(refresh);
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

  function syncTypicalServiceTermGanttDeadlineMarkerState(chart) {
    if (!chart) return;
    const hoveredTaskId = String(chart.dataset.hoverTaskId || '');
    const activeTaskId = String(chart.dataset.activeTaskId || '');
    chart.querySelectorAll('.typical-service-term-gantt-deadline-marker').forEach(function (marker) {
      const markerTaskId = String(marker.dataset.taskId || '');
      marker.classList.toggle('typical-service-term-gantt-deadline-marker--hover', !!markerTaskId && markerTaskId === hoveredTaskId);
      marker.classList.toggle('typical-service-term-gantt-deadline-marker--active', !!markerTaskId && markerTaskId === activeTaskId);
    });
  }

  function setTypicalServiceTermGanttHoveredRow(chart, taskId, showDeadlineMarker) {
    const normalizedTaskId = String(taskId || '');
    chart?.querySelectorAll('.typical-service-term-gantt-hover-row').forEach(function (node) {
      node.classList.remove('typical-service-term-gantt-hover-row');
    });
    if (!chart) return;
    if (!normalizedTaskId) {
      delete chart.dataset.hoverTaskId;
      syncTypicalServiceTermGanttDeadlineMarkerState(chart);
      return;
    }
    if (showDeadlineMarker) {
      chart.dataset.hoverTaskId = normalizedTaskId;
    } else {
      delete chart.dataset.hoverTaskId;
    }

    const escapedTaskId = escapeTypicalServiceTermGanttSelectorValue(normalizedTaskId);
    const selector = '[data-task-id="' + escapedTaskId + '"], [task_id="' + escapedTaskId + '"]';
    chart.querySelectorAll(selector).forEach(function (node) {
      if (!node.classList.contains('gantt_row') && !node.classList.contains('gantt_task_row') && !node.classList.contains('gantt_task_line')) return;
      node.classList.add('typical-service-term-gantt-hover-row');
    });
    syncTypicalServiceTermGanttDeadlineMarkerState(chart);
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
    syncTypicalServiceTermGanttColumnCollapseState(gantt, chart);
    requestAnimationFrame(function () {
      syncTypicalServiceTermGanttColumnCollapseState(gantt, chart);
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
      syncTypicalServiceTermGanttDeadlineMarkerState(chart);
      return;
    }
    chart.dataset.activeTaskId = normalizedTaskId;

    const escapedTaskId = escapeTypicalServiceTermGanttSelectorValue(normalizedTaskId);
    const selector = '[data-task-id="' + escapedTaskId + '"], [task_id="' + escapedTaskId + '"]';
    chart.querySelectorAll(selector).forEach(function (node) {
      if (!node.classList.contains('gantt_row') && !node.classList.contains('gantt_task_row') && !node.classList.contains('gantt_task_line')) return;
      node.classList.add('typical-service-term-gantt-active-row');
    });
    syncTypicalServiceTermGanttDeadlineMarkerState(chart);
    const gantt = window.__policyTypicalServiceTermGantt;
    if (gantt && !gantt.$gantt_engine_disposed) {
      syncTypicalServiceTermGanttColumnCollapseState(gantt, chart);
      requestAnimationFrame(function () {
        syncTypicalServiceTermGanttColumnCollapseState(gantt, chart);
      });
    }
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
        const currentChart = typicalServiceTermGanttChartEl();
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
        const showDeadlineMarker = !!event.target?.closest?.('.gantt_task_line, .typical-service-term-gantt-deadline-marker');
        setTypicalServiceTermGanttHoveredRow(chart, getTypicalServiceTermGanttDomTaskId(event.target), showDeadlineMarker);
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
        const currentChart = typicalServiceTermGanttChartEl();
        if (currentChart?.dataset.activeTaskId) {
          requestAnimationFrame(function () {
            setTypicalServiceTermGanttActiveRow(currentChart, currentChart.dataset.activeTaskId);
          });
        }
      };
      gantt.$policyTypicalServiceTermRowHighlightEventIds = [
        policyGanttAttachEvent('onDataRender', function () {
          reapplyActiveRow();
          requestAnimationFrame(function () {
            alignTypicalServiceTermGanttLinkHandles(typicalServiceTermGanttChartEl());
          });
        }),
        policyGanttAttachEvent('onGanttScroll', function () {
          reapplyActiveRow();
          requestAnimationFrame(function () {
            alignTypicalServiceTermGanttLinkHandles(typicalServiceTermGanttChartEl());
          });
        }),
        policyGanttAttachEvent('onTaskClick', function (id) {
          if (id !== undefined && id !== null && typeof gantt.selectTask === 'function') {
            gantt.selectTask(id);
          }
          const currentChart = typicalServiceTermGanttChartEl();
          setTypicalServiceTermGanttActiveRow(currentChart, id);
          requestAnimationFrame(function () { setTypicalServiceTermGanttActiveRow(currentChart, id); });
          return true;
        }),
        policyGanttAttachEvent('onTaskSelected', function (id) {
          const currentChart = typicalServiceTermGanttChartEl();
          setTypicalServiceTermGanttActiveRow(currentChart, id);
          return true;
        }),
        policyGanttAttachEvent('onTaskUnselected', function () {
          requestAnimationFrame(function () {
            const currentChart = typicalServiceTermGanttChartEl();
            const selectedId = typeof gantt.getSelectedId === 'function' ? gantt.getSelectedId() : null;
            if (selectedId === undefined || selectedId === null || selectedId === '') {
              setTypicalServiceTermGanttActiveRow(currentChart, '');
            }
          });
          return true;
        }),
      ];
    }
  }

  function syncTypicalServiceTermGanttOutlineButtons(chart) {
    if (!chart) return;
    const activeLevel = normalizeFilterValue(chart.dataset.ganttOutlineLevel);
    chart.querySelectorAll('.typical-service-term-gantt-outline-btn').forEach(function (button) {
      const active = activeLevel && button.dataset.ganttOutlineLevel === activeLevel;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function applyTypicalServiceTermGanttOutlineLevel(gantt, chart, level) {
    if (!gantt || !chart || typeof gantt.eachTask !== 'function') return;
    const targetLevel = Math.max(1, Math.min(4, Math.round(Number(level) || 1)));
    chart.dataset.ganttOutlineApplying = '1';
    gantt.eachTask(function (task) {
      if (!task || typeof gantt.hasChild !== 'function' || !gantt.hasChild(task.id)) return;
      task.$open = getTypicalServiceTermGanttVisualLevel(gantt, task) < targetLevel;
    });
    chart.dataset.ganttOutlineLevel = String(targetLevel);
    if (typeof gantt.render === 'function') gantt.render();
    // In fullscreen the chart container is a fixed pixel box (computed from
    // viewport - toolbar - footer), so when the visible row count changes
    // the internal dhtmlxGantt layout must be re-sized to use that full
    // height for its data area. Without this the data view keeps the
    // pre-expansion height and the newly visible rows fall behind the
    // bottom (toolbar/footer/edge), with an unnecessary internal scrollbar
    // appearing on the right.
    refreshTypicalServiceTermGanttFullscreenLayout(chart);
    requestAnimationFrame(function () {
      delete chart.dataset.ganttOutlineApplying;
      syncTypicalServiceTermGanttOutlineButtons(chart);
    });
  }

  // Re-applies the fullscreen frame sizing for the typical-service-term
  // Gantt: when the editor is in fullscreen mode, the chart's pixel height
  // and dhtmlxGantt's `setSizes()` must be re-computed after every
  // structural change (row open/close, outline level change, add/remove).
  // No-op when fullscreen is not active or when no editor is present.
  function refreshTypicalServiceTermGanttFullscreenLayout(chart) {
    const editor = chart?.closest?.('.typical-service-term-gantt-editor')
      || typicalServiceTermGanttEditorEl();
    if (!editor || !editor.classList.contains('typical-service-term-gantt-editor--fullscreen')) return;
    const root = pane();
    if (!root) return;
    requestAnimationFrame(function () {
      refreshTypicalServiceTermGanttFrame(root);
    });
  }

  function bindTypicalServiceTermGanttOutlineControls(gantt, chart) {
    if (!gantt || !chart || chart.dataset.typicalServiceTermGanttOutlineBound === '1') return;
    chart.dataset.typicalServiceTermGanttOutlineBound = '1';
    chart.addEventListener('click', function (event) {
      const button = event.target?.closest?.('.typical-service-term-gantt-outline-btn');
      if (!button || !chart.contains(button)) return;
      event.preventDefault();
      event.stopPropagation();
      applyTypicalServiceTermGanttOutlineLevel(gantt, chart, button.dataset.ganttOutlineLevel);
    }, true);
    if (typeof gantt.attachEvent === 'function' && !gantt.$policyTypicalServiceTermOutlineControlsBound) {
      gantt.$policyTypicalServiceTermOutlineControlsBound = true;
      policyGanttAttachEvent('onDataRender', function () {
        requestAnimationFrame(function () {
          syncTypicalServiceTermGanttOutlineButtons(chart);
        });
        return true;
      });
      const clearOutlineLevel = function () {
        if (chart.dataset.ganttOutlineApplying === '1') {
          // Outline-level button is handling this expansion/collapse cycle
          // itself (including the fullscreen-layout refresh). Stay out of
          // the way so we don't fight over a half-applied state.
          return true;
        }
        delete chart.dataset.ganttOutlineLevel;
        requestAnimationFrame(function () {
          syncTypicalServiceTermGanttOutlineButtons(chart);
        });
        // When the user toggles a branch open/closed manually (chevron in
        // the grid) while the editor is fullscreen, the chart's pixel box
        // doesn't change — but dhtmlxGantt's data view internally keeps
        // the pre-toggle height until setSizes() runs, leaving a stray
        // internal scrollbar and the new rows tucked under the fullscreen
        // edge. Re-apply the fullscreen frame so the data area uses the
        // entire available height again.
        refreshTypicalServiceTermGanttFullscreenLayout(chart);
        return true;
      };
      policyGanttAttachEvent('onTaskOpened', clearOutlineLevel);
      policyGanttAttachEvent('onTaskClosed', clearOutlineLevel);
    }
  }

  function clearTypicalServiceTermGanttSelection() {
    const gantt = getTypicalServiceTermGanttInstance();
    const chart = typicalServiceTermGanttChartEl();
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
      if (chart?.contains(event.target)) return;
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

  function syncTypicalServiceTermGanttFreeDatesToggle(root) {
    const enabled = isTypicalServiceTermGanttSnapToGridEnabled();
    const button = root?.querySelector('#typical-service-term-gantt-free-dates-btn');
    const chart = root?.querySelector('#typical-service-term-gantt');
    if (button) {
      button.classList.toggle('active', enabled);
      button.setAttribute('aria-pressed', enabled ? 'true' : 'false');
      button.setAttribute(
        'aria-label',
        enabled
          ? 'Выключить привязку сроков к сетке'
          : 'Включить привязку сроков к сетке'
      );
      button.title = enabled
        ? 'Привязка сроков к сетке включена'
        : 'Свободное изменение сроков без привязки к сетке';
    }
    if (chart) chart.classList.toggle('typical-service-term-gantt-snap-to-grid', enabled);
  }

  function syncTypicalServiceTermGanttTimeboxToggle(root) {
    const enabled = isTypicalServiceTermGanttTimeboxEnabled();
    const button = root?.querySelector('#typical-service-term-gantt-timebox-btn');
    const chart = root?.querySelector('#typical-service-term-gantt');
    if (button) {
      button.classList.toggle('active', enabled);
      button.setAttribute('aria-pressed', enabled ? 'true' : 'false');
      button.setAttribute(
        'aria-label',
        enabled ? 'Выключить режим таймбокса' : 'Включить режим таймбокса'
      );
      button.title = enabled
        ? 'Режим таймбокса включен'
        : 'Режим таймбокса: подгонять цепочку к фиксированной вехе';
    }
    if (chart) chart.classList.toggle('typical-service-term-gantt-timebox', enabled);
  }

  function applyTypicalServiceTermGanttDragRounding(gantt, root) {
    if (!gantt?.config) return;
    const snapToGrid = isTypicalServiceTermGanttSnapToGridEnabled();
    gantt.config.round_dnd_dates = snapToGrid;
    gantt.config.time_step = snapToGrid ? 24 * 60 : 1;
    syncTypicalServiceTermGanttFreeDatesToggle(root);
  }

  // ---------------------------------------------------------------------------
  //  Production-calendar working/non-working day support
  // ---------------------------------------------------------------------------
  //
  //  The Gantt is normally in "working days" mode: durations and date math go
  //  through the DHTMLX work_time calendar so weekends/holidays are skipped
  //  and rendered as shaded vertical stripes. The calendar3 toggle (top
  //  toolbar) flips the chart into "calendar days" mode, which restores the
  //  legacy behaviour where every day counts. The Settings modal (footer)
  //  selects which production-calendar country drives the working-days mode.

  function isTypicalServiceTermGanttCalendarDaysMode() {
    return !!window.__policyTypicalServiceTermGanttCalendarDaysMode;
  }

  function isTypicalServiceTermGanttWorkingDaysMode() {
    return !isTypicalServiceTermGanttCalendarDaysMode();
  }

  function normalizeTypicalServiceTermGanttCalendarKind(value) {
    return String(value || '') === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT
      ? TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT
      : TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION;
  }

  function getTypicalServiceTermGanttCalendarKind() {
    return normalizeTypicalServiceTermGanttCalendarKind(window.__policyTypicalServiceTermGanttCalendarKind);
  }

  function setTypicalServiceTermGanttCalendarKind(kind, options) {
    const normalized = normalizeTypicalServiceTermGanttCalendarKind(kind);
    window.__policyTypicalServiceTermGanttCalendarKind = normalized;
    if (P && options?.persist !== false) P.set(TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PREF_KEY, normalized);
  }

  function isTypicalServiceTermGanttAbstractCalendar() {
    return getTypicalServiceTermGanttCalendarKind() === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT;
  }

  function normalizeTypicalServiceTermGanttExecutorDisplayMode(value) {
    return String(value || '') === TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE
      ? TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE
      : TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_EXECUTOR;
  }

  function getTypicalServiceTermGanttExecutorDisplayMode() {
    return normalizeTypicalServiceTermGanttExecutorDisplayMode(window.__policyTypicalServiceTermGanttExecutorDisplay);
  }

  function setTypicalServiceTermGanttExecutorDisplayMode(value) {
    window.__policyTypicalServiceTermGanttExecutorDisplay = normalizeTypicalServiceTermGanttExecutorDisplayMode(value);
  }

  function getTypicalServiceTermGanttMetaCalendarKind(meta) {
    const value = meta && typeof meta === 'object' ? meta.calendar_kind : null;
    if (value === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT ||
      value === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION) {
      return value;
    }
    return null;
  }

  function getTypicalServiceTermGanttMetaExecutorDisplayMode(meta) {
    const value = meta && typeof meta === 'object' ? meta.executor_display : null;
    if (value === TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_EXECUTOR ||
      value === TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE) {
      return value;
    }
    return null;
  }

  function defaultTypicalServiceTermGanttCalendarKindForRoot(root) {
    return root?.id === 'projects-pane'
      ? TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION
      : TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT;
  }

  function withDefaultTypicalServiceTermGanttMeta(ganttData, root) {
    const source = ganttData && typeof ganttData === 'object' ? ganttData : {};
    const meta = Object.assign({}, source.meta && typeof source.meta === 'object' ? source.meta : {});
    if (!getTypicalServiceTermGanttMetaCalendarKind(meta)) {
      meta.calendar_kind = defaultTypicalServiceTermGanttCalendarKindForRoot(root);
    }
    if (!getTypicalServiceTermGanttMetaExecutorDisplayMode(meta)) {
      meta.executor_display = meta.calendar_kind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT
        ? TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE
        : TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_EXECUTOR;
    }
    return Object.assign({}, source, { meta: meta });
  }

  function applyTypicalServiceTermGanttMetaCalendarSettings(meta) {
    const kind = getTypicalServiceTermGanttMetaCalendarKind(meta);
    if (kind) setTypicalServiceTermGanttCalendarKind(kind, { persist: false });
    const displayMode = getTypicalServiceTermGanttMetaExecutorDisplayMode(meta);
    setTypicalServiceTermGanttExecutorDisplayMode(displayMode || (
      getTypicalServiceTermGanttCalendarKind() === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT
        ? TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE
        : TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_EXECUTOR
    ));
    const countryId = Number(meta?.calendar_country_id);
    if (kind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION && Number.isFinite(countryId)) {
      setTypicalServiceTermGanttCalendarCountryId(countryId);
    }
  }

  function syncTypicalServiceTermGanttMetaCalendarSettings(meta) {
    if (!meta || typeof meta !== 'object') return meta;
    meta.calendar_kind = getTypicalServiceTermGanttCalendarKind();
    const countryId = getTypicalServiceTermGanttCalendarCountryId();
    if (meta.calendar_kind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION && Number.isFinite(countryId)) {
      meta.calendar_country_id = countryId;
    } else {
      delete meta.calendar_country_id;
    }
    meta.executor_display = getTypicalServiceTermGanttExecutorDisplayMode();
    return meta;
  }

  function prepareTypicalServiceTermGanttWorkTimeForCurrentCalendar(gantt) {
    if (!gantt || isTypicalServiceTermGanttCalendarDaysMode()) {
      applyTypicalServiceTermGanttWorkTime(gantt, null);
      return;
    }
    if (isTypicalServiceTermGanttAbstractCalendar()) {
      const dataset = buildTypicalServiceTermGanttAbstractCalendarDataset(gantt);
      window.__policyTypicalServiceTermGanttActiveCalendar = dataset;
      applyTypicalServiceTermGanttWorkTime(gantt, dataset);
      return;
    }
    window.__policyTypicalServiceTermGanttActiveCalendar = null;
    applyTypicalServiceTermGanttWorkTime(gantt, null);
  }

  function setTypicalServiceTermGanttCalendarDaysMode(enabled) {
    window.__policyTypicalServiceTermGanttCalendarDaysMode = !!enabled;
    if (P) P.set(TYPICAL_SERVICE_TERM_GANTT_CALENDAR_DAYS_PREF_KEY, !!enabled);
  }

  function isTypicalServiceTermGanttHideNonWorkingDays() {
    // Hiding non-working time only makes sense alongside the working-days
    // calendar — in calendar-days mode the chart is unaware of holidays and
    // there is nothing to collapse.
    if (isTypicalServiceTermGanttCalendarDaysMode()) return false;
    return !!window.__policyTypicalServiceTermGanttHideNonWorkingDays;
  }

  function setTypicalServiceTermGanttHideNonWorkingDays(enabled) {
    window.__policyTypicalServiceTermGanttHideNonWorkingDays = !!enabled;
    if (P) P.set(TYPICAL_SERVICE_TERM_GANTT_HIDE_NON_WORKING_PREF_KEY, !!enabled);
  }

  // The open-source dhtmlxGantt build keeps `gantt.config.skip_off_time` in the
  // public config dictionary but only honours it inside the export pipeline.
  // The on-screen renderer goes through `scaleHelper.processIgnores`, which by
  // default just resets `ignore_x` — meaning columns never actually collapse.
  // We re-implement the export-side branch directly on the timeline view's
  // scaleHelper so the visible timeline collapses non-working days exactly the
  // way the PRO build would. Date math (calculateDuration / calculateEndDate)
  // is unaffected because it goes through the calendar API, not the scale.
  function installTypicalServiceTermGanttSkipOffTimePatch(gantt) {
    if (!gantt || !gantt.$ui || typeof gantt.$ui.getView !== 'function') return;
    let timelineView = null;
    try { timelineView = gantt.$ui.getView('timeline'); } catch (_) { return; }
    if (!timelineView || !timelineView.$scaleHelper) return;
    const scaleHelper = timelineView.$scaleHelper;
    if (scaleHelper.$policyProcessIgnoresPatched) return;
    const originalProcessIgnores = scaleHelper.processIgnores;
    scaleHelper.processIgnores = function patchedProcessIgnores(scaleConfig) {
      scaleConfig.ignore_x = {};
      const skip = !!gantt.config?.skip_off_time;
      const ignoreFn = typeof gantt.ignore_time === 'function' ? gantt.ignore_time : null;
      if (!skip && !ignoreFn) {
        scaleConfig.display_count = scaleConfig.count;
        return;
      }
      const traceX = scaleConfig.trace_x || [];
      let displayCount = 0;
      let ignored = false;
      for (let idx = 0; idx < traceX.length; idx++) {
        const date = traceX[idx];
        let skipCell = false;
        if (ignoreFn) {
          try { skipCell = !!ignoreFn.call(gantt, date); } catch (_) { skipCell = false; }
        }
        if (!skipCell && skip && typeof this._ignore_time_config === 'function') {
          try {
            skipCell = !!this._ignore_time_config.call(gantt, date, scaleConfig);
          } catch (_) {
            skipCell = false;
          }
        }
        if (skipCell) {
          scaleConfig.ignore_x[date.valueOf()] = true;
          ignored = true;
        } else {
          displayCount++;
        }
      }
      if (ignored) scaleConfig.ignored_colls = true;
      scaleConfig.display_count = displayCount;
    };
    scaleHelper.$policyProcessIgnoresPatched = true;
    scaleHelper.$policyOrigProcessIgnores = originalProcessIgnores;

    // For week/month/quarter scales we tack on a hidden day-level row at the
    // bottom of `gantt.config.scales` so that `processIgnores` has day-grain
    // cells to collapse. The default `splitSize` would still allocate that row
    // its share of `scale_height`, leaving an empty stripe under the header.
    // Override it to give the hidden row 0px while the visible rows split the
    // full scale_height between themselves.
    if (typeof scaleHelper.splitSize === 'function' && !scaleHelper.$policySplitSizePatched) {
      const originalSplitSize = scaleHelper.splitSize;
      scaleHelper.splitSize = function patchedSplitSize(totalHeight, count) {
        const scales = (gantt.config && Array.isArray(gantt.config.scales)) ? gantt.config.scales : [];
        const lastScale = scales[scales.length - 1];
        const hiddenLast = !!(lastScale && lastScale.$policyHiddenDayScale);
        if (hiddenLast && count === scales.length && count >= 2) {
          const sizes = originalSplitSize.call(this, totalHeight, count - 1);
          sizes.push(0);
          return sizes;
        }
        return originalSplitSize.call(this, totalHeight, count);
      };
      scaleHelper.$policySplitSizePatched = true;
      scaleHelper.$policyOrigSplitSize = originalSplitSize;
    }
  }

  function syncTypicalServiceTermGanttHideNonWorkingToggle(root) {
    const button = root?.querySelector('#typical-service-term-gantt-hide-non-working-btn');
    if (!button) return;
    const calendarDays = isTypicalServiceTermGanttCalendarDaysMode();
    const active = isTypicalServiceTermGanttHideNonWorkingDays();
    button.disabled = calendarDays;
    button.classList.toggle('disabled', calendarDays);
    button.classList.toggle('active', active && !calendarDays);
    button.setAttribute('aria-pressed', active && !calendarDays ? 'true' : 'false');
    const chart = root?.querySelector('#typical-service-term-gantt');
    if (chart) {
      const scale = getTypicalServiceTermGanttScale(root);
      const hidden = !calendarDays && active && scale !== 'day';
      chart.classList.toggle('typical-service-term-gantt-hidden-day-cells', hidden);
    }
    if (calendarDays) {
      button.setAttribute(
        'aria-label',
        'Свернуть нерабочие дни недоступно в режиме календарных дней'
      );
      button.title = 'Сначала включите режим рабочих дней, чтобы скрыть нерабочие дни';
    } else if (active) {
      button.setAttribute('aria-label', 'Показать нерабочие дни на таймлайне');
      button.title = 'Нерабочие дни свёрнуты. Нажмите, чтобы снова показать их на таймлайне';
    } else {
      button.setAttribute('aria-label', 'Свернуть нерабочие дни на таймлайне');
      button.title = 'Свернуть нерабочие дни: выходные и праздники не показываются на таймлайне';
    }
  }

  function getTypicalServiceTermGanttCalendarCountryId() {
    const id = window.__policyTypicalServiceTermGanttCalendarCountryId;
    return Number.isFinite(id) ? id : null;
  }

  function setTypicalServiceTermGanttCalendarCountryId(id) {
    const normalized = Number.isFinite(Number(id)) ? Number(id) : null;
    window.__policyTypicalServiceTermGanttCalendarCountryId = normalized;
    if (P) {
      if (normalized === null) {
        P.set(TYPICAL_SERVICE_TERM_GANTT_CALENDAR_COUNTRY_PREF_KEY, '');
      } else {
        P.set(TYPICAL_SERVICE_TERM_GANTT_CALENDAR_COUNTRY_PREF_KEY, normalized);
      }
    }
  }

  function syncTypicalServiceTermGanttCalendarDaysToggle(root) {
    const enabled = isTypicalServiceTermGanttCalendarDaysMode();
    const button = root?.querySelector('#typical-service-term-gantt-calendar-days-btn');
    const chart = root?.querySelector('#typical-service-term-gantt');
    if (button) {
      button.classList.toggle('active', enabled);
      button.setAttribute('aria-pressed', enabled ? 'true' : 'false');
      button.setAttribute(
        'aria-label',
        enabled
          ? 'Выключить режим календарных дней (включить рабочие дни)'
          : 'Включить режим календарных дней'
      );
      button.title = enabled
        ? 'Режим календарных дней включён: производственный календарь не учитывается'
        : 'Режим рабочих дней: длительности считаются с учётом производственного календаря';
    }
    if (chart) {
      chart.classList.toggle('typical-service-term-gantt-calendar-days', enabled);
      chart.classList.toggle('typical-service-term-gantt-working-days', !enabled);
      // Marker for CSS: hides day-level vertical borders inside the chart area
      // when we splice a hidden day sub-scale at week/month/quarter scales.
      const scale = getTypicalServiceTermGanttScale(root);
      const hidden = !enabled && isTypicalServiceTermGanttHideNonWorkingDays() && scale !== 'day';
      chart.classList.toggle('typical-service-term-gantt-hidden-day-cells', hidden);
    }
  }

  function fetchTypicalServiceTermGanttCalendarCountries() {
    if (window.__policyTypicalServiceTermGanttCalendarCountriesPromise) {
      return window.__policyTypicalServiceTermGanttCalendarCountriesPromise;
    }
    window.__policyTypicalServiceTermGanttCalendarCountriesPromise = fetch(
      '/classifiers/pc/countries.json',
      { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' }
    )
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (payload) {
        if (!payload || !payload.ok) {
          throw new Error(payload?.error || 'Не удалось загрузить список стран.');
        }
        return payload;
      })
      .catch(function (error) {
        window.__policyTypicalServiceTermGanttCalendarCountriesPromise = null;
        throw error;
      });
    return window.__policyTypicalServiceTermGanttCalendarCountriesPromise;
  }

  function typicalServiceTermGanttCalendarCacheKey(countryId, yearFrom, yearTo) {
    return String(countryId) + ':' + yearFrom + '-' + yearTo;
  }

  function fetchTypicalServiceTermGanttCalendarRange(countryId, yearFrom, yearTo) {
    if (!Number.isFinite(countryId)) return Promise.reject(new Error('country not selected'));
    const key = typicalServiceTermGanttCalendarCacheKey(countryId, yearFrom, yearTo);
    const cache = window.__policyTypicalServiceTermGanttCalendarCache;
    const cached = cache.get(key);
    if (cached) return cached;
    const url = '/classifiers/pc/calendar.json?country_id=' + encodeURIComponent(countryId) +
      '&year_from=' + encodeURIComponent(yearFrom) +
      '&year_to=' + encodeURIComponent(yearTo);
    const promise = fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (payload) {
        if (!payload || !payload.ok) {
          throw new Error(payload?.error || 'Не удалось загрузить производственный календарь.');
        }
        const nonWorkingDays = new Set();
        const workingDays = new Set();
        const holidayNames = new Map();
        (Array.isArray(payload.days) ? payload.days : []).forEach(function (item) {
          if (!item || !item.date) return;
          if (item.is_working_day) {
            workingDays.add(item.date);
          } else {
            nonWorkingDays.add(item.date);
            if (item.holiday_name) holidayNames.set(item.date, item.holiday_name);
          }
        });
        return {
          country: payload.country || null,
          yearFrom: payload.year_from || yearFrom,
          yearTo: payload.year_to || yearTo,
          nonWorkingDays: nonWorkingDays,
          workingDays: workingDays,
          holidayNames: holidayNames,
        };
      })
      .catch(function (error) {
        cache.delete(key);
        throw error;
      });
    cache.set(key, promise);
    return promise;
  }

  function buildTypicalServiceTermGanttAbstractCalendarDataset(gantt) {
    const nonWorkingDays = new Set();
    const holidayNames = new Map();
    const now = new Date();
    const start = gantt?.config?.start_date instanceof Date
      ? gantt.config.start_date
      : new Date(TYPICAL_SERVICE_TERM_GANTT_ABSTRACT_BASE_YEAR, 0, 1);
    const end = gantt?.config?.end_date instanceof Date
      ? gantt.config.end_date
      : new Date(Math.max(TYPICAL_SERVICE_TERM_GANTT_ABSTRACT_BASE_YEAR + 1, now.getFullYear() + 1), 0, 1);
    const cursor = new Date(start.getFullYear(), start.getMonth(), start.getDate());
    const stopAt = new Date(end.getFullYear(), end.getMonth(), end.getDate());
    let safety = 0;
    while (cursor.getTime() <= stopAt.getTime() && safety < 5000) {
      const day = cursor.getDay();
      if (day === 0 || day === 6) {
        const iso = formatPolicyGanttDateInput(cursor);
        nonWorkingDays.add(iso);
        holidayNames.set(iso, 'Выходной день');
      }
      cursor.setDate(cursor.getDate() + 1);
      safety += 1;
    }
    return {
      country: { short_name: 'Условный календарь' },
      yearFrom: start.getFullYear(),
      yearTo: end.getFullYear(),
      nonWorkingDays: nonWorkingDays,
      workingDays: new Set(),
      holidayNames: holidayNames,
      abstract: true,
    };
  }

  function getTypicalServiceTermGanttCalendarYearRange(gantt, root) {
    const editor = root?.querySelector('#typical-service-term-gantt-editor');
    const meta = editor?._typicalServiceTermGanttMeta || {};
    const now = new Date();
    const startCandidate = parsePolicyGanttDate(meta.project_start)
      || parsePolicyGanttDate(meta.base_date)
      || (gantt && gantt.config && gantt.config.start_date instanceof Date ? gantt.config.start_date : null)
      || new Date(now.getFullYear(), 0, 1);
    const endCandidate = parsePolicyGanttDate(meta.project_end)
      || (gantt && gantt.config && gantt.config.end_date instanceof Date ? gantt.config.end_date : null)
      || new Date(now.getFullYear() + 1, 0, 1);
    let yearFrom = startCandidate.getFullYear() - 1;
    let yearTo = endCandidate.getFullYear() + 1;
    if (yearTo < yearFrom) {
      const tmp = yearFrom;
      yearFrom = yearTo;
      yearTo = tmp;
    }
    if (yearTo - yearFrom > 10) yearTo = yearFrom + 10;
    return { yearFrom: yearFrom, yearTo: yearTo };
  }

  function applyTypicalServiceTermGanttWorkTime(gantt, dataset) {
    if (!gantt || typeof gantt.setWorkTime !== 'function') return;
    const workingDaysMode = isTypicalServiceTermGanttWorkingDaysMode();
    gantt.config.work_time = workingDaysMode;
    gantt.config.correct_work_time = workingDaysMode;
    // skip_off_time collapses non-working time slots on the timeline; only
    // meaningful together with work_time. In calendar-days mode we always show
    // every day so date math stays calendar-based.
    gantt.config.skip_off_time = workingDaysMode && isTypicalServiceTermGanttHideNonWorkingDays();
    installTypicalServiceTermGanttSkipOffTimePatch(gantt);
    // Drop any per-date overrides we applied previously so switching country
    // (or toggling working-days off) doesn't leave stale holidays in place.
    const previousDates = gantt.$policyTypicalServiceTermWorkTimeDates;
    if (previousDates && typeof previousDates.forEach === 'function'
      && typeof gantt.unsetWorkTime === 'function') {
      previousDates.forEach(function (iso) {
        const parsed = parsePolicyGanttDate(iso);
        if (!parsed) return;
        try { gantt.unsetWorkTime({ date: parsed }); } catch (_) { /* ignore */ }
      });
    }
    gantt.$policyTypicalServiceTermWorkTimeDates = new Set();
    [0, 1, 2, 3, 4, 5, 6].forEach(function (day) {
      try {
        // In working-days mode: 0/6 (Sun/Sat) are non-working, others working.
        if (day === 0 || day === 6) {
          gantt.setWorkTime({ day: day, hours: false });
        } else {
          gantt.setWorkTime({ day: day, hours: true });
        }
      } catch (_) {
        // The GPL build may throw on unsupported edge cases; ignore.
      }
    });
    if (!workingDaysMode || !dataset) return;
    // Apply explicit per-date overrides from the production calendar so the
    // chart respects national holidays, переноса and any country whose weekend
    // pattern differs from Sat/Sun.
    const applied = gantt.$policyTypicalServiceTermWorkTimeDates;
    const applyDate = function (iso, hours) {
      const parsed = parsePolicyGanttDate(iso);
      if (!parsed) return;
      try {
        gantt.setWorkTime({ date: parsed, hours: hours });
        applied.add(iso);
      } catch (_) { /* ignore */ }
    };
    if (dataset.nonWorkingDays && typeof dataset.nonWorkingDays.forEach === 'function') {
      dataset.nonWorkingDays.forEach(function (iso) { applyDate(iso, false); });
    }
    if (dataset.workingDays && typeof dataset.workingDays.forEach === 'function') {
      // Without these explicit calls, working Saturdays/Sundays (e.g. when the
      // government moves a workday in Russia) would stay shaded because of the
      // weekend baseline above.
      dataset.workingDays.forEach(function (iso) {
        const parsed = parsePolicyGanttDate(iso);
        if (!parsed) return;
        const dayOfWeek = parsed.getDay();
        if (dayOfWeek === 0 || dayOfWeek === 6) applyDate(iso, true);
      });
    }
  }

  function isTypicalServiceTermGanttCalendarWorkingDate(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return false;
    if (isTypicalServiceTermGanttCalendarDaysMode()) return true;
    const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const iso = formatPolicyGanttDateInput(day);
    const dataset = window.__policyTypicalServiceTermGanttActiveCalendar;
    if (dataset?.workingDays?.has?.(iso)) return true;
    if (dataset?.nonWorkingDays?.has?.(iso)) return false;
    const dayOfWeek = day.getDay();
    return dayOfWeek !== 0 && dayOfWeek !== 6;
  }

  function getNextTypicalServiceTermGanttWorkingDate(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return null;
    const cursor = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    let safety = 0;
    while (!isTypicalServiceTermGanttCalendarWorkingDate(cursor) && safety < 3700) {
      cursor.setDate(cursor.getDate() + 1);
      safety += 1;
    }
    return new Date(cursor);
  }

  function hasTypicalServiceTermGanttHardDateConstraint(task) {
    const type = normalizeTypicalServiceTermGanttConstraintType(task?.constraint_type);
    return !!type && type !== 'asap' && type !== 'alap';
  }

  function captureTypicalServiceTermGanttCalendarTransitionBaseline(gantt) {
    if (window.GanttEngine && typeof window.GanttEngine.captureCalendarTransitionBaseline === 'function') {
      return window.GanttEngine.captureCalendarTransitionBaseline(gantt, {
        isSummaryTask: function (ganttInstance, task) {
          return isTypicalServiceTermGanttSummaryTask(ganttInstance, task);
        },
      });
    }
    if (!gantt || typeof gantt.eachTask !== 'function') return null;
    const durations = {};
    gantt.eachTask(function (task) {
      if (!task || task.id === undefined || task.id === null) return;
      if (isTypicalServiceTermGanttSummaryTask(gantt, task)) return;
      let duration = Number(task.duration);
      if (!Number.isFinite(duration) && task.start_date instanceof Date && task.end_date instanceof Date) {
        duration = calculateTypicalServiceTermGanttDuration(gantt, task.start_date, task.end_date, task);
      }
      durations[String(task.id)] = Math.max(0, Math.round(Number(duration) || 0));
    });
    return { durations: durations };
  }

  function getTypicalServiceTermGanttPreservedDuration(baseline, task) {
    if (!baseline || !task) return Math.max(0, Math.round(Number(task?.duration) || 0));
    const value = baseline.durations?.[String(task.id)];
    return Math.max(0, Math.round(Number(value) || 0));
  }

  function setTypicalServiceTermGanttTaskStartWithDuration(gantt, task, nextStart, duration, snapStart) {
    if (!task || !(nextStart instanceof Date) || Number.isNaN(nextStart.getTime())) return false;
    const startDate = snapStart === false
      ? new Date(nextStart.getFullYear(), nextStart.getMonth(), nextStart.getDate())
      : getNextTypicalServiceTermGanttWorkingDate(nextStart);
    if (!(startDate instanceof Date) || Number.isNaN(startDate.getTime())) return false;
    const safeDuration = task.type === gantt?.config?.types?.milestone
      ? 0
      : Math.max(0, Math.round(Number(duration) || 0));
    const nextEnd = task.type === gantt?.config?.types?.milestone
      ? new Date(startDate)
      : calculateTypicalServiceTermGanttEndDate(gantt, startDate, safeDuration, task);
    if (!(nextEnd instanceof Date) || Number.isNaN(nextEnd.getTime())) return false;
    const changed =
      !(task.start_date instanceof Date) ||
      !(task.end_date instanceof Date) ||
      task.start_date.valueOf() !== startDate.valueOf() ||
      task.end_date.valueOf() !== nextEnd.valueOf() ||
      Number(task.duration || 0) !== safeDuration;
    task.start_date = new Date(startDate);
    task.end_date = new Date(nextEnd);
    task.duration = safeDuration;
    return changed;
  }

  function setTypicalServiceTermGanttTaskEndWithDuration(gantt, task, nextEnd, duration) {
    if (!task || !(nextEnd instanceof Date) || Number.isNaN(nextEnd.getTime())) return false;
    const endDate = new Date(nextEnd.getFullYear(), nextEnd.getMonth(), nextEnd.getDate());
    const safeDuration = task.type === gantt?.config?.types?.milestone
      ? 0
      : Math.max(0, Math.round(Number(duration) || 0));
    const nextStart = task.type === gantt?.config?.types?.milestone
      ? new Date(endDate)
      : calculateTypicalServiceTermGanttStartDate(gantt, endDate, safeDuration, task);
    if (!(nextStart instanceof Date) || Number.isNaN(nextStart.getTime())) return false;
    const changed =
      !(task.start_date instanceof Date) ||
      !(task.end_date instanceof Date) ||
      task.start_date.valueOf() !== nextStart.valueOf() ||
      task.end_date.valueOf() !== endDate.valueOf() ||
      Number(task.duration || 0) !== safeDuration;
    task.start_date = new Date(nextStart);
    task.end_date = new Date(endDate);
    task.duration = safeDuration;
    return changed;
  }

  function applyTypicalServiceTermGanttCalendarTransitionSchedule(gantt, baseline) {
    if (window.GanttEngine && typeof window.GanttEngine.applyCalendarTransitionSchedule === 'function') {
      return window.GanttEngine.applyCalendarTransitionSchedule(gantt, baseline, {
        isSummaryTask: function (ganttInstance, task) {
          return isTypicalServiceTermGanttSummaryTask(ganttInstance, task);
        },
        getNextWorkingDate: function (date) {
          return getNextTypicalServiceTermGanttWorkingDate(date);
        },
        parentRollup: function (ganttInstance) {
          applyTypicalServiceTermGanttParentRollup(ganttInstance);
        },
        schedulingFlag: '$policyTypicalServiceTermSchedulingActive',
      });
    }
    if (!gantt || !baseline || typeof gantt.eachTask !== 'function') return false;
    const links = typeof gantt.getLinks === 'function' ? (gantt.getLinks() || []) : [];
    const types = gantt.config?.links || { finish_to_start: '0', start_to_start: '1', finish_to_finish: '2', start_to_finish: '3' };
    const fixedLinks = links.filter(function (link) {
      return normalizeTypicalServiceTermGanttLagMode(link?.lag_mode) === 'fixed';
    });
    const incomingFixed = {};
    fixedLinks.forEach(function (link) {
      const targetId = String(link?.target ?? '');
      if (targetId) incomingFixed[targetId] = true;
    });

    const changedTaskIds = [];
    const rememberChanged = function (taskId) {
      if (changedTaskIds.indexOf(taskId) === -1) changedTaskIds.push(taskId);
    };
    const canMoveTask = function (task) {
      return !!task
        && !isTypicalServiceTermGanttSummaryTask(gantt, task)
        && !hasTypicalServiceTermGanttHardDateConstraint(task)
        && !getTypicalServiceTermGanttFixedMilestoneDate(gantt, task);
    };

    const apply = function () {
      gantt.eachTask(function (task) {
        if (!canMoveTask(task) || incomingFixed[String(task.id)]) return;
        if (!(task.start_date instanceof Date)) return;
        const duration = getTypicalServiceTermGanttPreservedDuration(baseline, task);
        if (setTypicalServiceTermGanttTaskStartWithDuration(gantt, task, task.start_date, duration, true)) {
          rememberChanged(task.id);
        }
      });

      const maxPasses = Math.max(fixedLinks.length + 1, 2);
      for (let pass = 0; pass < maxPasses; pass += 1) {
        let changedInPass = false;
        fixedLinks.forEach(function (link) {
          let source;
          let target;
          try {
            source = typeof gantt.getTask === 'function' ? gantt.getTask(link.source) : null;
            target = typeof gantt.getTask === 'function' ? gantt.getTask(link.target) : null;
          } catch (_) {
            source = null;
            target = null;
          }
          if (!source || !target || !canMoveTask(target)) return;
          if (!(source.start_date instanceof Date) || !(source.end_date instanceof Date)) return;
          if (!(target.start_date instanceof Date) || !(target.end_date instanceof Date)) return;
          const linkType = String(link.type);
          const lag = normalizeTypicalServiceTermGanttLag(link.lag);
          const duration = getTypicalServiceTermGanttPreservedDuration(baseline, target);
          let changed = false;
          if (linkType === String(types.start_to_start)) {
            changed = setTypicalServiceTermGanttTaskStartWithDuration(gantt, target, addPolicyGanttDays(source.start_date, lag), duration, false);
          } else if (linkType === String(types.finish_to_finish)) {
            changed = setTypicalServiceTermGanttTaskEndWithDuration(gantt, target, addPolicyGanttDays(source.end_date, lag), duration);
          } else if (linkType === String(types.start_to_finish)) {
            changed = setTypicalServiceTermGanttTaskEndWithDuration(gantt, target, addPolicyGanttDays(source.start_date, lag), duration);
          } else {
            changed = setTypicalServiceTermGanttTaskStartWithDuration(gantt, target, addPolicyGanttDays(source.end_date, lag), duration, false);
          }
          if (changed) {
            changedInPass = true;
            rememberChanged(target.id);
          }
        });
        if (!changedInPass) break;
      }

      applyTypicalServiceTermGanttParentRollup(gantt);
      changedTaskIds.forEach(function (id) {
        if (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(id)) return;
        if (typeof gantt.updateTask === 'function') gantt.updateTask(id);
      });
    };

    const wasSchedulingActive = gantt.$policyTypicalServiceTermSchedulingActive;
    gantt.$policyTypicalServiceTermSchedulingActive = true;
    try {
      if (typeof gantt.batchUpdate === 'function') {
        gantt.batchUpdate(apply);
      } else {
        apply();
      }
    } finally {
      gantt.$policyTypicalServiceTermSchedulingActive = wasSchedulingActive;
    }
    return changedTaskIds.length > 0;
  }

  // When the hidden day-level sub-scale is active, the chart background is
  // composed of one cell per working day. Their default vertical separators
  // would create a thicket of day-grain lines at week/month/quarter scales,
  // so site.css suppresses them. To keep the chart readable we re-draw
  // gridlines only at the visible scale boundaries (start of every week /
  // month / quarter), as absolute-positioned divs on top of `.gantt_task_bg`.
  function refreshTypicalServiceTermGanttGridLines(gantt, chart, root) {
    if (!gantt || !chart) return;
    const layer = gantt.$task_bg || chart.querySelector('.gantt_task_bg');
    if (!layer) return;
    layer.querySelectorAll('.' + TYPICAL_SERVICE_TERM_GANTT_GRID_LINE_CLASS).forEach(function (node) {
      node.remove();
    });
    if (!chart.classList.contains('typical-service-term-gantt-hidden-day-cells')) return;
    if (typeof gantt.posFromDate !== 'function') return;
    const scale = getTypicalServiceTermGanttScale(root || pane());
    if (scale === 'day') return;
    const start = gantt.config?.start_date instanceof Date ? gantt.config.start_date : null;
    const end = gantt.config?.end_date instanceof Date ? gantt.config.end_date : null;
    if (!start || !end) return;
    const height = getTypicalServiceTermGanttTimelineLayerHeight(gantt, chart, layer);
    if (!height) return;
    layer.style.minHeight = Math.max(1, Math.round(height)) + 'px';
    const cursor = new Date(start.getFullYear(), start.getMonth(), start.getDate());
    const stopAt = new Date(end.getFullYear(), end.getMonth(), end.getDate());
    const advance = function () {
      if (scale === 'week') {
        cursor.setDate(cursor.getDate() + 7);
      } else if (scale === 'month') {
        cursor.setMonth(cursor.getMonth() + 1);
      } else if (scale === 'quarter') {
        cursor.setMonth(cursor.getMonth() + 3);
      } else {
        cursor.setDate(cursor.getDate() + 1);
      }
    };
    // Snap to the first boundary at or after `start`.
    if (scale === 'week') {
      // dhtmlxGantt aligns weeks to Monday (start_on_monday: true).
      const offsetDays = (cursor.getDay() + 6) % 7;
      cursor.setDate(cursor.getDate() - offsetDays);
      if (cursor < start) cursor.setDate(cursor.getDate() + 7);
    } else if (scale === 'month') {
      cursor.setDate(1);
      if (cursor < start) cursor.setMonth(cursor.getMonth() + 1);
    } else if (scale === 'quarter') {
      const m = cursor.getMonth();
      cursor.setMonth(m - (m % 3));
      cursor.setDate(1);
      if (cursor < start) cursor.setMonth(cursor.getMonth() + 3);
    }
    let safety = 0;
    while (cursor.getTime() <= stopAt.getTime() && safety < 2000) {
      let x;
      try {
        x = gantt.posFromDate(new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate()));
      } catch (_) {
        x = NaN;
      }
      if (Number.isFinite(x)) {
        const line = document.createElement('div');
        line.className = TYPICAL_SERVICE_TERM_GANTT_GRID_LINE_CLASS;
        line.style.left = Math.round(x) + 'px';
        line.style.height = Math.max(1, Math.round(height)) + 'px';
        line.setAttribute('aria-hidden', 'true');
        layer.appendChild(line);
      }
      advance();
      safety++;
    }
  }

  function getTypicalServiceTermGanttTimelineLayerHeight(gantt, chart, layer) {
    const getRectHeight = function (node) {
      if (!node || typeof node.getBoundingClientRect !== 'function') return 0;
      const rect = node.getBoundingClientRect();
      return Number.isFinite(rect.height) ? rect.height : 0;
    };
    const taskData = chart?.querySelector('.gantt_task_data');
    const dataArea = chart?.querySelector('.gantt_data_area');
    const taskArea = chart?.querySelector('.gantt_task');
    const timelineCell = chart?.querySelector('.gantt_layout_cell.timeline_cell');
    const candidates = [
      layer?.scrollHeight,
      layer?.offsetHeight,
      layer?.clientHeight,
      getRectHeight(layer),
      taskData?.scrollHeight,
      taskData?.offsetHeight,
      taskData?.clientHeight,
      getRectHeight(taskData),
      dataArea?.scrollHeight,
      dataArea?.offsetHeight,
      dataArea?.clientHeight,
      getRectHeight(dataArea),
      taskArea?.scrollHeight,
      taskArea?.offsetHeight,
      taskArea?.clientHeight,
      getRectHeight(taskArea),
      timelineCell?.scrollHeight,
      timelineCell?.offsetHeight,
      timelineCell?.clientHeight,
      getRectHeight(timelineCell),
      gantt?.$task_data?.scrollHeight,
      gantt?.$task_data?.offsetHeight,
      gantt?.$task_data?.clientHeight,
      getRectHeight(gantt?.$task_data),
    ];
    return Math.max.apply(null, candidates.map(function (value) {
      return Number.isFinite(Number(value)) ? Number(value) : 0;
    }));
  }

  function getTypicalServiceTermGanttNonWorkingOverlay(chart) {
    const dataArea = chart?.querySelector('.gantt_data_area');
    if (!dataArea) return null;
    let overlay = dataArea.querySelector(':scope > .' + TYPICAL_SERVICE_TERM_GANTT_CALENDAR_OVERLAY_CLASS);
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = TYPICAL_SERVICE_TERM_GANTT_CALENDAR_OVERLAY_CLASS;
      overlay.setAttribute('aria-hidden', 'true');
      dataArea.appendChild(overlay);
    }
    return overlay;
  }

  function refreshTypicalServiceTermGanttNonWorkingShading(gantt, chart) {
    if (!gantt || !chart) return;
    // Always refresh the synthetic scale-boundary gridlines alongside the
    // non-working-day stripes — they share the same trigger points (render,
    // mode toggles, country switches).
    refreshTypicalServiceTermGanttGridLines(gantt, chart, pane());
    const layer = gantt.$task_bg || chart.querySelector('.gantt_task_bg');
    if (!layer) return;
    layer.querySelectorAll('.' + TYPICAL_SERVICE_TERM_GANTT_CALENDAR_BG_CLASS).forEach(function (node) {
      node.remove();
    });
    const overlay = getTypicalServiceTermGanttNonWorkingOverlay(chart);
    overlay?.querySelectorAll?.('.' + TYPICAL_SERVICE_TERM_GANTT_CALENDAR_BG_CLASS).forEach(function (node) {
      node.remove();
    });
    if (isTypicalServiceTermGanttCalendarDaysMode()) {
      if (overlay) overlay.remove();
      return;
    }
    // When non-working time is collapsed via skip_off_time the chart no longer
    // dedicates any width to weekends/holidays — drawing stripes would just
    // double-up on the working-day cells, so bail out.
    if (gantt.config && gantt.config.skip_off_time) return;
    const dataset = window.__policyTypicalServiceTermGanttActiveCalendar;
    if (!dataset || !dataset.nonWorkingDays || !dataset.nonWorkingDays.size) return;
    if (typeof gantt.posFromDate !== 'function') return;
    const scale = getTypicalServiceTermGanttScale(pane());
    // DHTMLX rounds `start_date`/`end_date` outward to the nearest scale unit
    // boundary at render time (e.g. quarter-aligned at the "Квартал" scale).
    // The actually rendered range lives on `gantt.getState().min_date` /
    // `max_date` — use that so non-working-day stripes cover the whole visible
    // timeline, including the trailing portion of the last scale unit.
    let renderState = null;
    try {
      renderState = typeof gantt.getState === 'function' ? gantt.getState() : null;
    } catch (_) {
      renderState = null;
    }
    const stateStart = renderState?.min_date instanceof Date ? renderState.min_date : null;
    const stateEnd = renderState?.max_date instanceof Date ? renderState.max_date : null;
    const configStart = gantt.config?.start_date instanceof Date ? gantt.config.start_date : null;
    const configEnd = gantt.config?.end_date instanceof Date ? gantt.config.end_date : null;
    const start = stateStart || configStart;
    const end = stateEnd || configEnd;
    if (!start || !end) return;
    const height = getTypicalServiceTermGanttTimelineLayerHeight(gantt, chart, layer);
    if (!height) return;
    layer.style.minHeight = Math.max(1, Math.round(height)) + 'px';
    const targetLayer = overlay || layer;
    const targetWidth = Math.max(
      layer.scrollWidth || 0,
      layer.offsetWidth || 0,
      chart.querySelector('.gantt_data_area')?.scrollWidth || 0,
      chart.querySelector('.gantt_task')?.scrollWidth || 0
    );
    targetLayer.style.height = Math.max(1, Math.round(height)) + 'px';
    if (targetWidth) targetLayer.style.width = Math.max(1, Math.round(targetWidth)) + 'px';
    const dataArea = chart.querySelector('.gantt_data_area');
    if (dataArea) dataArea.style.minHeight = Math.max(1, Math.round(height)) + 'px';
    const cursor = new Date(start.getFullYear(), start.getMonth(), start.getDate());
    // Both `state.max_date` and our snapped `config.end_date` are treated as
    // exclusive upper bounds (start of the day/unit right after the last
    // visible one), so iterate strictly before them.
    const stopAt = new Date(end.getFullYear(), end.getMonth(), end.getDate());
    while (cursor.getTime() < stopAt.getTime()) {
      const iso = formatPolicyGanttDateInput(cursor);
      if (dataset.nonWorkingDays.has(iso)) {
        let left;
        let right;
        try {
          left = gantt.posFromDate(new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate()));
          const nextDay = new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate() + 1);
          right = gantt.posFromDate(nextDay);
        } catch (_) {
          left = NaN;
          right = NaN;
        }
        if (Number.isFinite(left) && Number.isFinite(right) && right > left) {
          const stripe = document.createElement('div');
          stripe.className = TYPICAL_SERVICE_TERM_GANTT_CALENDAR_BG_CLASS;
          stripe.classList.add('typical-service-term-gantt-non-working-day-bg--' + scale);
          stripe.style.left = Math.round(left) + 'px';
          stripe.style.width = Math.max(1, Math.round(right - left)) + 'px';
          stripe.style.height = Math.max(1, Math.round(height)) + 'px';
          const holidayName = dataset.holidayNames && dataset.holidayNames.get(iso);
          stripe.title = holidayName ? holidayName : 'Нерабочий день';
          stripe.setAttribute('aria-hidden', 'true');
          targetLayer.appendChild(stripe);
        }
      }
      cursor.setDate(cursor.getDate() + 1);
    }
  }

  function syncTypicalServiceTermGanttCalendarData(gantt, root, options) {
    if (!gantt) return Promise.resolve(null);
    const opts = options || {};
    const chart = root ? root.querySelector('#typical-service-term-gantt') : null;
    const sessionId = getTypicalServiceTermGanttSessionId(root);
    const expectedKind = getTypicalServiceTermGanttCalendarKind();
    const expectedCountryId = getTypicalServiceTermGanttCalendarCountryId();
    // In calendar-days mode we still want the country selection persisted, but
    // we don't apply work_time at all so durations stay calendar-based.
    if (isTypicalServiceTermGanttCalendarDaysMode()) {
      window.__policyTypicalServiceTermGanttActiveCalendar = null;
      applyTypicalServiceTermGanttWorkTime(gantt, null);
      applyTypicalServiceTermGanttProjectBounds(gantt, root?.querySelector('#typical-service-term-gantt-editor')?._typicalServiceTermGanttMeta || {});
      if (chart) refreshTypicalServiceTermGanttNonWorkingShading(gantt, chart);
      if (opts.render !== false && typeof gantt.render === 'function') {
        try { gantt.render(); } catch (_) { /* ignore */ }
        if (chart) refreshTypicalServiceTermGanttInteractiveChrome(gantt, chart);
      }
      return Promise.resolve(null);
    }
    if (isTypicalServiceTermGanttAbstractCalendar()) {
      const dataset = buildTypicalServiceTermGanttAbstractCalendarDataset(gantt);
      window.__policyTypicalServiceTermGanttActiveCalendar = dataset;
      applyTypicalServiceTermGanttWorkTime(gantt, dataset);
      applyTypicalServiceTermGanttProjectBounds(gantt, root?.querySelector('#typical-service-term-gantt-editor')?._typicalServiceTermGanttMeta || {});
      if (typeof gantt.render === 'function' && opts.render !== false) {
        try { gantt.render(); } catch (_) { /* ignore */ }
        if (chart) refreshTypicalServiceTermGanttInteractiveChrome(gantt, chart);
      }
      if (chart) {
        requestAnimationFrame(function () {
          refreshTypicalServiceTermGanttNonWorkingShading(gantt, chart);
        });
      }
      return Promise.resolve(dataset);
    }
    const countryId = getTypicalServiceTermGanttCalendarCountryId();
    if (!Number.isFinite(countryId)) {
      // No country selected yet — resolve the default from the server once and
      // re-enter this function with the populated id.
      return fetchTypicalServiceTermGanttCalendarCountries()
        .then(function (payload) {
          if (!isTypicalServiceTermGanttSessionCurrent(root, gantt, sessionId, expectedKind, expectedCountryId)) {
            return null;
          }
          let defaultId = payload && Number.isFinite(payload.default_id) ? Number(payload.default_id) : null;
          if (!Number.isFinite(defaultId) && Array.isArray(payload?.items) && payload.items.length) {
            // Fall back to the first supported country; prefer Russia by alpha2.
            const russia = payload.items.find(function (item) {
              return String(item.alpha2 || '').toUpperCase() === TYPICAL_SERVICE_TERM_GANTT_DEFAULT_COUNTRY_ALPHA2;
            });
            defaultId = russia ? russia.id : payload.items[0].id;
          }
          if (Number.isFinite(defaultId)) {
            setTypicalServiceTermGanttCalendarCountryId(defaultId);
            return syncTypicalServiceTermGanttCalendarData(gantt, root, opts);
          }
          return null;
        })
        .catch(function () { return null; });
    }
    const range = getTypicalServiceTermGanttCalendarYearRange(gantt, root);
    return fetchTypicalServiceTermGanttCalendarRange(countryId, range.yearFrom, range.yearTo)
      .then(function (dataset) {
        if (!isTypicalServiceTermGanttSessionCurrent(root, gantt, sessionId, expectedKind, countryId)) {
          return null;
        }
        window.__policyTypicalServiceTermGanttActiveCalendar = dataset;
        applyTypicalServiceTermGanttWorkTime(gantt, dataset);
        const editor = root?.querySelector('#typical-service-term-gantt-editor');
        applyTypicalServiceTermGanttProjectBounds(gantt, editor?._typicalServiceTermGanttMeta || {});
        if (opts.calendarTransitionBaseline) {
          const changed = applyTypicalServiceTermGanttCalendarTransitionSchedule(gantt, opts.calendarTransitionBaseline);
          if (changed) {
            applyTypicalServiceTermGanttProjectBounds(gantt, editor?._typicalServiceTermGanttMeta || {});
          }
        }
        if (typeof gantt.render === 'function' && opts.render !== false) {
          try { gantt.render(); } catch (_) { /* ignore */ }
          if (chart) refreshTypicalServiceTermGanttInteractiveChrome(gantt, chart);
        }
        if (chart) {
          requestAnimationFrame(function () {
            refreshTypicalServiceTermGanttNonWorkingShading(gantt, chart);
          });
        }
        return dataset;
      })
      .catch(function (error) {
        if (!isTypicalServiceTermGanttSessionCurrent(root, gantt, sessionId, expectedKind, countryId)) {
          return null;
        }
        if (window.console && console.warn) {
          console.warn('[policy] production calendar fetch failed:', error);
        }
        window.__policyTypicalServiceTermGanttActiveCalendar = null;
        applyTypicalServiceTermGanttWorkTime(gantt, null);
        if (chart) refreshTypicalServiceTermGanttNonWorkingShading(gantt, chart);
        if (chart) refreshTypicalServiceTermGanttInteractiveChrome(gantt, chart);
        return null;
      });
  }

  function dateOnlyTypicalServiceTermGanttValue(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return null;
    return new Date(date.getFullYear(), date.getMonth(), date.getDate());
  }

  function bindTypicalServiceTermGanttFreeResizeDates(gantt) {
    if (!gantt || gantt.$policyTypicalServiceTermFreeResizeDatesBound || typeof gantt.attachEvent !== 'function') return;
    gantt.$policyTypicalServiceTermFreeResizeDatesBound = true;
    policyGanttAttachEvent('onTaskDrag', function (id, mode, task) {
      const resizeMode = gantt.config?.drag_mode?.resize || 'resize';
      if (isTypicalServiceTermGanttSnapToGridEnabled() || String(mode) !== String(resizeMode) || !task) return true;
      const dragState = typeof gantt.getState === 'function' ? (gantt.getState('tasksDnd') || {}) : {};
      gantt.$policyTypicalServiceTermLastFreeResize = {
        id: String(id),
        fromStart: !!dragState.drag_from_start,
        startDate: dateOnlyTypicalServiceTermGanttValue(task.start_date),
        endDate: dateOnlyTypicalServiceTermGanttValue(task.end_date),
      };
      return true;
    });
    policyGanttAttachEvent('onAfterTaskDrag', function (id, mode) {
      const resizeMode = gantt.config?.drag_mode?.resize || 'resize';
      const lastResize = gantt.$policyTypicalServiceTermLastFreeResize;
      delete gantt.$policyTypicalServiceTermLastFreeResize;
      if (isTypicalServiceTermGanttSnapToGridEnabled() || String(mode) !== String(resizeMode) || !lastResize || String(lastResize.id) !== String(id)) {
        return true;
      }
      let task;
      try {
        task = typeof gantt.getTask === 'function' ? gantt.getTask(id) : null;
      } catch (_) {
        task = null;
      }
      if (!task) return true;
      if (lastResize.fromStart && lastResize.startDate) {
        task.start_date = lastResize.startDate;
      } else if (!lastResize.fromStart && lastResize.endDate) {
        task.end_date = lastResize.endDate;
      }
      if (task.start_date instanceof Date && task.end_date instanceof Date) {
        if (task.end_date < task.start_date) task.end_date = new Date(task.start_date);
        task.duration = task.type === gantt.config?.types?.milestone
          ? 0
          : calculateTypicalServiceTermGanttDuration(gantt, task.start_date, task.end_date, task);
      }
      if (typeof gantt.updateTask === 'function') gantt.updateTask(id);
      return true;
    });
  }

  function formatTypicalServiceTermGanttOrdinal(value) {
    return Math.max(1, Math.round(Number(value) || 1)) + '-й';
  }

  function getTypicalServiceTermGanttAbstractYearNumber(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return 1;
    return Math.max(1, date.getFullYear() - TYPICAL_SERVICE_TERM_GANTT_ABSTRACT_BASE_YEAR + 1);
  }

  function getTypicalServiceTermGanttAbstractMonthNumber(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return 1;
    return date.getMonth() + 1;
  }

  function getTypicalServiceTermGanttAbstractQuarterNumber(date) {
    return Math.max(1, Math.floor(date.getMonth() / 3) + 1);
  }

  function getTypicalServiceTermGanttAbstractWeekNumber(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return 1;
    const base = new Date(TYPICAL_SERVICE_TERM_GANTT_ABSTRACT_BASE_YEAR, 0, 1);
    const msPerWeek = 7 * 24 * 60 * 60 * 1000;
    const absoluteWeek = Math.max(1, Math.floor((dateOnlyTypicalServiceTermGanttValue(date) - base) / msPerWeek) + 1);
    return ((absoluteWeek - 1) % 4) + 1;
  }

  function applyTypicalServiceTermGanttScale(gantt, scale) {
    if (gantt && gantt.config) gantt.config.$ganttEngineScale = scale;
    const monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
    const shortMonthNames = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];
    const abstractCalendar = isTypicalServiceTermGanttAbstractCalendar();
    const formatAbstractYear = function (date) {
      if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '1-й год';
      return Math.max(0, date.getFullYear() - TYPICAL_SERVICE_TERM_GANTT_ABSTRACT_BASE_YEAR + 1) + '-й год';
    };
    const formatAbstractMonth = function (date) {
      return formatTypicalServiceTermGanttOrdinal(getTypicalServiceTermGanttAbstractMonthNumber(date)) + ' месяц';
    };
    const formatAbstractMonthShort = function (date) {
      return formatTypicalServiceTermGanttOrdinal(getTypicalServiceTermGanttAbstractMonthNumber(date)) + ' мес.';
    };
    const formatAbstractQuarter = function (date) {
      return formatTypicalServiceTermGanttOrdinal(getTypicalServiceTermGanttAbstractQuarterNumber(date)) + ' кв.';
    };
    const formatAbstractWeek = function (date) {
      return getTypicalServiceTermGanttAbstractWeekNumber(date) + '-я нед.';
    };
    const formatWeekRange = function (date) {
      if (abstractCalendar) return formatAbstractWeek(date);
      const end = addPolicyGanttDays(date, 6);
      if (date.getMonth() === end.getMonth() && date.getFullYear() === end.getFullYear()) {
        return gantt.date.date_to_str('%d')(date) + '-' + gantt.date.date_to_str('%d.%m')(end);
      }
      return gantt.date.date_to_str('%d.%m')(date) + '-' + gantt.date.date_to_str('%d.%m')(end);
    };

    // A hidden day-level scale keeps the rendered range day-grained even when
    // visible labels are week/month/quarter. Without it, DHTMLX rounds
    // config.start_date/end_date to whole visible scale units and can show an
    // entire adjacent quarter/month despite our minimal padding rules.
    //
    // When non-working days should be collapsed, the dhtmlxGantt scale model
    // only collapses cells whose entire step is non-working. Week/month/quarter
    // cells contain working days, so they are never collapsed on their own.
    // Trick: bolt a hidden day-level sub-scale at the bottom of `scales`. The
    // renderer runs `processIgnores` on the LAST scale, which marks
    // non-working days as ignored (width = 0), and then `alineScaleColumns`
    // shrinks the visible week/month/quarter columns above to the sum of
    // working-day widths. `installTypicalServiceTermGanttSkipOffTimePatch`
    // overrides `splitSize` so the hidden row gets 0px of header height.
    const useHiddenDayScale = scale !== 'day';
    const hiddenDayScaleConfig = {
      unit: 'day',
      step: 1,
      format: function () { return ''; },
      css: function () { return 'typical-service-term-gantt-hidden-day-cell'; },
      $policyHiddenDayScale: true,
    };

    if (scale === 'day') {
      gantt.config.scale_height = 54;
      gantt.config.min_column_width = 36;
      gantt.config.scales = [
        { unit: 'month', step: 1, format: abstractCalendar ? formatAbstractMonth : function (date) { return monthNames[date.getMonth()] + ' ' + date.getFullYear(); } },
        { unit: 'day', step: 1, format: '%d' },
      ];
      return;
    }

    if (scale === 'month') {
      gantt.config.scale_height = 54;
      gantt.config.min_column_width = 5;
      gantt.config.scales = [
        { unit: 'year', step: 1, format: abstractCalendar ? formatAbstractYear : '%Y' },
        { unit: 'month', step: 1, format: abstractCalendar ? formatAbstractMonthShort : function (date) { return shortMonthNames[date.getMonth()]; } },
      ];
      if (useHiddenDayScale) gantt.config.scales.push(hiddenDayScaleConfig);
      return;
    }

    if (scale === 'quarter') {
      gantt.config.scale_height = 54;
      gantt.config.min_column_width = 3;
      gantt.config.scales = [
        { unit: 'year', step: 1, format: abstractCalendar ? formatAbstractYear : '%Y' },
        { unit: 'quarter', step: 1, format: abstractCalendar ? formatAbstractQuarter : function (date) { return 'Q' + (Math.floor(date.getMonth() / 3) + 1); } },
      ];
      if (useHiddenDayScale) gantt.config.scales.push(hiddenDayScaleConfig);
      return;
    }

    gantt.config.scale_height = 54;
    gantt.config.min_column_width = 14;
    gantt.config.scales = [
      { unit: 'month', step: 1, format: abstractCalendar ? formatAbstractMonth : function (date) { return monthNames[date.getMonth()] + ' ' + date.getFullYear(); } },
      { unit: 'week', step: 1, format: formatWeekRange },
    ];
    if (useHiddenDayScale) gantt.config.scales.push(hiddenDayScaleConfig);
  }

  function loadTypicalServiceTermGanttAssets() {
    if (window.__policyTypicalServiceTermGanttAssetsLoading) {
      return window.__policyTypicalServiceTermGanttAssetsLoading;
    }

    const cssHref = '/static/gantt_engine/dhtmlxgantt.css?v=20260511-1';
    const cssLoaded = new Promise(function (resolve) {
      let link = document.querySelector('link[href*="gantt_engine/dhtmlxgantt.css"]');
      if (link?.sheet) {
        resolve(true);
        return;
      }
      if (!link) {
        link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = cssHref;
        link.addEventListener('load', function () { resolve(true); }, { once: true });
        link.addEventListener('error', function () { resolve(false); }, { once: true });
        document.head.appendChild(link);
      } else {
        link.addEventListener('load', function () { resolve(true); }, { once: true });
        link.addEventListener('error', function () { resolve(false); }, { once: true });
      }
      window.setTimeout(function () { resolve(!!link.sheet); }, 2500);
    });

    function engineReady() {
      return !!(window.GanttEngine && typeof window.GanttEngine.create === 'function');
    }

    window.__policyTypicalServiceTermGanttAssetsLoading = new Promise(function (resolve) {
      const resolveWhenReady = function (scriptLoaded) {
        cssLoaded.then(function (styleLoaded) {
          resolve(!!scriptLoaded && !!styleLoaded && engineReady());
        });
      };
      if (engineReady()) {
        resolveWhenReady(true);
        return;
      }
      const existingScript = document.querySelector('script[src*="gantt_engine/dhtmlxgantt.js"]');
      if (existingScript) {
        existingScript.addEventListener('load', function () { resolveWhenReady(true); }, { once: true });
        existingScript.addEventListener('error', function () { resolve(false); }, { once: true });
        window.setTimeout(function () { resolveWhenReady(engineReady()); }, 2500);
        return;
      }

      const script = document.createElement('script');
      script.src = '/static/gantt_engine/dhtmlxgantt.js?v=20260511-1';
      script.onload = function () { resolveWhenReady(true); };
      script.onerror = function () { resolve(false); };
      document.head.appendChild(script);
    });
    return window.__policyTypicalServiceTermGanttAssetsLoading;
  }

  // The typical-service-term section owns its OWN Gantt instance built via
  // window.GanttEngine.create(). No more shared singleton — see
  // gantt_engine_app/static/gantt_engine/gantt-engine.js.
  function getTypicalServiceTermGanttInstance() {
    if (window.__policyTypicalServiceTermGantt) return window.__policyTypicalServiceTermGantt;
    if (window.GanttEngine && typeof window.GanttEngine.create === 'function') {
      const instance = window.GanttEngine.create();
      if (instance) {
        window.__policyTypicalServiceTermGantt = instance;
        return instance;
      }
    }
    return null;
  }

  function disposeTypicalServiceTermGanttInstance() {
    const editor = getTypicalServiceTermGanttCurrentEditor();
    if (editor?._typicalServiceTermGanttResources) {
      try { editor._typicalServiceTermGanttResources.dispose(); } catch (_) { /* noop */ }
      editor._typicalServiceTermGanttResources = null;
    }
    if (window.__policyTypicalServiceTermGanttResources) {
      try { window.__policyTypicalServiceTermGanttResources.dispose(); } catch (_) { /* noop */ }
      window.__policyTypicalServiceTermGanttResources = null;
    }
    const gantt = window.__policyTypicalServiceTermGantt;
    if (!gantt) return;
    try {
      if (typeof gantt.hideLightbox === 'function') gantt.hideLightbox();
      if (typeof gantt.clearAll === 'function') gantt.clearAll();
    } catch (_) {
      // A partially initialized DHTMLX instance can throw during cleanup.
    }
    if (window.GanttEngine && typeof window.GanttEngine.dispose === 'function') {
      window.GanttEngine.dispose(gantt);
    }
    window.__policyTypicalServiceTermGantt = null;
  }

  function resetTypicalServiceTermGanttInstance() {
    disposeTypicalServiceTermGanttInstance();
    return getTypicalServiceTermGanttInstance();
  }

  function getTypicalServiceTermGanttContainer(gantt) {
    return gantt?.$container || gantt?.$root || gantt?.$layout?.$container || null;
  }

  function snapshotTypicalServiceTermGanttData(gantt) {
    if (!gantt) return null;
    const data = [];
    if (typeof gantt.eachTask === 'function') {
      gantt.eachTask(function (task) {
        const item = {};
        Object.keys(task).forEach(function (key) {
          if (key.charAt(0) === '$' || typeof task[key] === 'function') return;
          item[key] = task[key];
        });
        data.push(item);
      });
    }
    const links = typeof gantt.getLinks === 'function'
      ? gantt.getLinks().map(function (link) { return Object.assign({}, link); })
      : [];
    return { data: data, links: links };
  }

  function getTypicalServiceTermGanttCurrentEditor() {
    const root = pane();
    return root ? root.querySelector('#typical-service-term-gantt-editor') : null;
  }

  function captureTypicalServiceTermGanttOpenState(gantt, editor) {
    const targetEditor = editor || getTypicalServiceTermGanttCurrentEditor();
    if (!gantt || !targetEditor || typeof gantt.eachTask !== 'function') return [];
    const openTaskIds = [];
    gantt.eachTask(function (task) {
      const hasChildren = typeof gantt.hasChild === 'function' && gantt.hasChild(task.id);
      if (hasChildren && task.$open) openTaskIds.push(String(task.id));
    });
    targetEditor._typicalServiceTermGanttOpenTaskIds = openTaskIds;
    return openTaskIds;
  }

  function restoreTypicalServiceTermGanttOpenState(gantt, editor) {
    const targetEditor = editor || getTypicalServiceTermGanttCurrentEditor();
    const openTaskIds = Array.isArray(targetEditor?._typicalServiceTermGanttOpenTaskIds)
      ? targetEditor._typicalServiceTermGanttOpenTaskIds
      : [];
    if (!gantt || !openTaskIds.length || typeof gantt.eachTask !== 'function') return;
    const openSet = new Set(openTaskIds.map(String));
    gantt.eachTask(function (task) {
      if (typeof gantt.hasChild === 'function' && gantt.hasChild(task.id)) {
        task.$open = openSet.has(String(task.id));
      }
    });
  }

  function captureTypicalServiceTermGanttData(gantt) {
    const editor = getTypicalServiceTermGanttCurrentEditor();
    if (!editor) return;
    captureTypicalServiceTermGanttOpenState(gantt, editor);
    const snapshot = snapshotTypicalServiceTermGanttData(gantt);
    if (snapshot) {
      editor._typicalServiceTermGanttData = snapshot;
    }
  }

  function getTypicalServiceTermGanttCachedData() {
    const editor = getTypicalServiceTermGanttCurrentEditor();
    return (editor && editor._typicalServiceTermGanttData) || null;
  }

  function applyTypicalServiceTermGanttPostMount(gantt, root, chart) {
    if (!gantt || !chart) return;
    const editor = root?.querySelector('#typical-service-term-gantt-editor');
    restoreTypicalServiceTermGanttOpenState(gantt, editor);
    prepareTypicalServiceTermGanttWorkTimeForCurrentCalendar(gantt);
    applyTypicalServiceTermGanttProjectBounds(gantt, editor?._typicalServiceTermGanttMeta || {});
    syncTypicalServiceTermGanttScheduling(gantt);
    syncTypicalServiceTermGanttParentProgress(gantt);
    syncTypicalServiceTermGanttCalendarDaysToggle(root);
    syncTypicalServiceTermGanttHideNonWorkingToggle(root);
    installTypicalServiceTermGanttSkipOffTimePatch(gantt);
    gantt.render();
    installTypicalServiceTermGanttOwnershipWatchdog(chart);
    installTypicalServiceTermGanttColumnResizeHandles(gantt, chart);
    installTypicalServiceTermGanttLightboxDblClick(gantt, chart);
    bindTypicalServiceTermGanttLinkSourceState(gantt, chart);
    bindTypicalServiceTermGanttRowHighlight(gantt, chart);
    bindTypicalServiceTermGanttOutlineControls(gantt, chart);
    bindTypicalServiceTermGanttMilestoneLinkAlign(gantt, chart);
    bindTypicalServiceTermGanttDeadlineLayer(gantt, chart);
    bindTypicalServiceTermGanttDeadlineDrag(gantt, chart);
    requestAnimationFrame(function () {
      alignTypicalServiceTermGanttLinkHandles(chart);
      alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
      renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
    });
    stabilizeTypicalServiceTermGanttLayout(gantt, chart);
    // Resolve country-specific non-working days asynchronously; the call
    // re-renders the chart and lays down the shading stripes once data lands.
    syncTypicalServiceTermGanttCalendarData(gantt, root, { render: true });
  }

  // Used to be a registration call into the (now removed) GanttHost singleton
  // coordinator. With per-instance Gantt engines each section owns its own
  // instance, so no registration is needed. Kept as a no-op so legacy callers
  // remain harmless; once all call sites are cleaned up the stub can go too.
  function ensureTypicalServiceTermGanttSectionRegistered() {
    /* no-op: see gantt_engine_app/static/gantt_engine/gantt-engine.js */
  }

  // (Re)mounts the typical-service-term Gantt into `chart`:
  //   1. ensure we have a section-owned instance (created lazily on first
  //      call to getTypicalServiceTermGanttInstance);
  //   2. apply section-specific config / templates / lightbox blocks (this
  //      is idempotent — repeated calls just overwrite the same config keys);
  //   3. init the instance into `chart` and parse cached data;
  //   4. run the section's post-mount helpers (event bindings, calendars,
  //      milestone link alignment, etc.).
  //
  // IMPORTANT: we deliberately reuse the SAME Gantt instance across re-mounts
  // (scale changes, edit re-opens, etc.) and never call destructor() here.
  // Many user-interaction handlers (column-resize divider drag, etc.) capture
  // `gantt` in their closure at bind time — destroying the instance under
  // their feet would leave them operating on a corpse and DHTMLX would throw
  // from inside refreshData/render. The instance is only torn down via
  // disposeTypicalServiceTermGanttInstance() when its host container leaves
  // the DOM (htmx:afterSwap handler at the bottom of this file).
  //
  // Callers must set `editor._typicalServiceTermGanttData` BEFORE calling this
  // so step 3 has something to parse — `renderTypicalServiceTermGantt` does.
  function mountTypicalServiceTermGantt(root, chart) {
    if (!chart || !root) return null;
    // If we have a stale instance bound to a different (detached) DOM node,
    // tear it down before binding to the fresh container — closures over the
    // detached node are about to be GC'd anyway with the old subtree.
    const existing = window.__policyTypicalServiceTermGantt;
    if (existing) {
      const boundContainer = existing.$container || existing.$root
        || (existing.$layout && existing.$layout.$container) || null;
      if (boundContainer && boundContainer !== chart && !document.body.contains(boundContainer)) {
        disposeTypicalServiceTermGanttInstance();
      }
    }
    const instance = configureTypicalServiceTermGantt(root);
    if (!instance) return null;
    // DHTMLX's `init(container)` rebuilds the UI on `container` and is safe
    // to call repeatedly on the same instance — closures over `instance` stay
    // valid.
    chart.innerHTML = '';
    instance.init(chart);
    const cached = getTypicalServiceTermGanttCachedData();
    if (cached && (cached.data || cached.links)) {
      try {
        instance.clearAll();
        instance.parse({ data: cached.data || [], links: cached.links || [] });
      } catch (err) {
        try { console.error('[policy-gantt] parse failed:', err); } catch (_) {}
      }
    }
    applyTypicalServiceTermGanttPostMount(instance, root, chart);
    return instance;
  }

  // Returns true if our chart host currently has a mounted dhtmlxGantt layout
  // (the .gantt_container DOM tree). With per-instance engines this is purely
  // informational — nothing else can yank the layout away anymore.
  function isTypicalServiceTermGanttMounted(chart) {
    if (!chart) return false;
    return !!chart.querySelector('.gantt_container');
  }

  // Used to defend against other sections "stealing" the shared singleton.
  // With per-instance engines no other section can touch our instance, so
  // this collapses to "make sure our chart is mounted, otherwise mount it".
  function ensureTypicalServiceTermGanttOwnership(chart) {
    if (!chart) return false;
    if (isTypicalServiceTermGanttMounted(chart)) return true;
    const editor = chart.closest('.typical-service-term-gantt-editor');
    if (editor && editor.classList.contains('d-none')) return false;
    const root = pane();
    if (root) mountTypicalServiceTermGantt(root, chart);
    return isTypicalServiceTermGanttMounted(chart);
  }

  // No-op kept so existing call sites compile. The watchdog used to fight
  // singleton contention; per-instance engines have nothing to fight.
  function installTypicalServiceTermGanttOwnershipWatchdog(/* chart */) {
    /* no-op */
  }

  function ensureTypicalServiceTermGanttPeriodBlock(gantt) {
    if (!gantt || gantt.$policyTypicalServiceTermPeriodBlockRegistered) return;
    gantt.$policyTypicalServiceTermPeriodBlockRegistered = true;
    const formatDate = formatTypicalServiceTermGanttDateInput;
    const parseDate = parseTypicalServiceTermGanttDateInput;
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
          '<input type="text" id="policy-gantt-period-start" class="form-control policy-gantt-period-start" inputmode="numeric">' +
          '</div>' +
          '<div class="policy-gantt-period-field">' +
          '<label class="form-label" for="policy-gantt-period-end">Окончание' +
          '<i class="bi bi-lock ms-1 policy-gantt-period-lock policy-gantt-period-end-lock d-none" title="Окончание рассчитывается по подзадачам"></i>' +
          '</label>' +
          '<input type="text" id="policy-gantt-period-end" class="form-control policy-gantt-period-end" inputmode="numeric">' +
          '</div>' +
          '<div class="policy-gantt-period-field">' +
          '<label class="form-label" for="policy-gantt-period-duration">Длительность, раб. дн.' +
          '<i class="bi bi-lock-fill ms-1 policy-gantt-period-lock policy-gantt-period-duration-lock" role="button" title="Разблокировать ввод длительности"></i>' +
          '<i class="bi bi-calendar3-range ms-1 policy-gantt-period-timebox-adjust" role="button" title="Не сжимать в режиме таймбокса"></i>' +
          '</label>' +
          '<input type="number" id="policy-gantt-period-duration" class="form-control policy-gantt-period-duration readonly-field" min="0" step="1" readonly tabindex="-1">' +
          '</div>' +
          '<div class="policy-gantt-period-field policy-gantt-period-months-field">' +
          '<div class="form-label policy-gantt-period-label-spacer" aria-hidden="true">&nbsp;</div>' +
          '<input type="text" class="form-control policy-gantt-period-duration-months readonly-field" readonly tabindex="-1" aria-label="Длительность в месяцах">' +
          '</div>' +
          '<div class="policy-gantt-period-field policy-gantt-period-progress-field">' +
          '<label class="form-label" for="policy-gantt-period-progress">Прогресс, проц.</label>' +
          '<input type="number" id="policy-gantt-period-progress" class="form-control policy-gantt-period-progress" min="0" max="100" step="1">' +
          '</div>' +
          '<div class="policy-gantt-period-field">' +
          '<label class="form-label" for="policy-gantt-period-calendar-duration">Длительность, календ. дн.</label>' +
          '<input type="number" id="policy-gantt-period-calendar-duration" class="form-control policy-gantt-period-calendar-duration readonly-field" min="0" step="1" readonly tabindex="-1">' +
          '</div>' +
          '<div class="policy-gantt-period-field policy-gantt-period-calendar-months-field">' +
          '<div class="form-label policy-gantt-period-label-spacer" aria-hidden="true">&nbsp;</div>' +
          '<input type="text" class="form-control policy-gantt-period-calendar-duration-months readonly-field" readonly tabindex="-1" aria-label="Длительность в месяцах календарных дней">' +
          '</div>' +
          '<div class="policy-gantt-period-field">' +
          '<label class="form-label" for="policy-gantt-period-deadline">Дедлайн</label>' +
          '<input type="text" id="policy-gantt-period-deadline" class="form-control policy-gantt-period-deadline" inputmode="numeric">' +
          '</div>' +
          '<div class="policy-gantt-period-field policy-gantt-period-constraint-date-field">' +
          '<label class="form-label" for="policy-gantt-period-constraint-date">Дата ограничения</label>' +
          '<input type="text" id="policy-gantt-period-constraint-date" class="form-control policy-gantt-period-constraint-date" inputmode="numeric">' +
          '</div>' +
          '<div class="policy-gantt-period-field policy-gantt-period-constraint-type-field">' +
          '<label class="form-label" for="policy-gantt-period-constraint-type">Ограничение</label>' +
          '<select id="policy-gantt-period-constraint-type" class="form-select policy-gantt-period-constraint-type">' +
          getTypicalServiceTermGanttConstraintOptions().map(function (option) {
            return '<option value="' + escapePolicyHtml(option.key) + '">' + escapePolicyHtml(option.label) + '</option>';
          }).join('') +
          '</select>' +
          '</div>' +
          '</div>' +
          '</div>';
      },
      set_value: function (node, value, task) {
        const resetElement = function (element) {
          if (!element || !element.parentNode) return element;
          const clone = element.cloneNode(true);
          element.parentNode.replaceChild(clone, element);
          return clone;
        };
        let startInput = resetElement(node.querySelector('.policy-gantt-period-start'));
        let endInput = resetElement(node.querySelector('.policy-gantt-period-end'));
        let durationInput = resetElement(node.querySelector('.policy-gantt-period-duration'));
        let progressInput = resetElement(node.querySelector('.policy-gantt-period-progress'));
        let deadlineInput = resetElement(node.querySelector('.policy-gantt-period-deadline'));
        let constraintTypeInput = resetElement(node.querySelector('.policy-gantt-period-constraint-type'));
        let constraintDateInput = resetElement(node.querySelector('.policy-gantt-period-constraint-date'));
        const durationMonthsInput = node.querySelector('.policy-gantt-period-duration-months');
        const calendarDurationInput = node.querySelector('.policy-gantt-period-calendar-duration');
        const calendarDurationMonthsInput = node.querySelector('.policy-gantt-period-calendar-duration-months');
        let startLock = resetElement(node.querySelector('.policy-gantt-period-start-lock'));
        const endLock = node.querySelector('.policy-gantt-period-end-lock');
        let durationLock = resetElement(node.querySelector('.policy-gantt-period-duration-lock'));
        let timeboxAdjust = resetElement(node.querySelector('.policy-gantt-period-timebox-adjust'));
        if (!startInput || !endInput || !durationInput) return;
        const startDate = task?.start_date instanceof Date ? task.start_date : new Date();
        const endDate = task?.end_date instanceof Date
          ? task.end_date
          : (Number(task?.duration) > 0 && typeof gantt.calculateEndDate === 'function'
            ? gantt.calculateEndDate({ start_date: startDate, duration: Number(task.duration), task: task })
            : startDate);
        startInput.$policyTypicalServiceTermDatePickerDefaultDate = startDate;
        endInput.$policyTypicalServiceTermDatePickerDefaultDate = endDate;
        if (deadlineInput) deadlineInput.$policyTypicalServiceTermDatePickerDefaultDate = endDate;
        if (constraintDateInput) constraintDateInput.$policyTypicalServiceTermDatePickerDefaultDate = startDate;
        [startInput, endInput, deadlineInput, constraintDateInput].forEach(bindTypicalServiceTermGanttDateInput);
        startInput.value = formatDate(startDate);
        endInput.value = formatDate(endDate);
        if (progressInput) {
          const progress = isTypicalServiceTermGanttSummaryTask(gantt, task)
            ? (syncTypicalServiceTermGanttParentProgress(gantt), Math.max(0, Math.min(1, Number(task?.progress) || 0)))
            : Math.max(0, Math.min(1, Number(task?.progress) || 0));
          progressInput.value = String(Math.round(progress * 100));
        }
        if (deadlineInput) deadlineInput.value = formatDate(parseDate(task?.deadline));
        if (constraintTypeInput) constraintTypeInput.value = normalizeTypicalServiceTermGanttConstraintType(task?.constraint_type);
        if (constraintDateInput) constraintDateInput.value = formatDate(parseDate(task?.constraint_date));
        let durationEditMode = false;
        let timeboxAdjustMode = task?.timebox_adjustable !== false;
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
          syncTypicalServiceTermGanttDateInputPickerState(input);
        };
        const setDatePickerLocked = function (input, locked) {
          if (!input) return;
          input.$policyTypicalServiceTermDatePickerLocked = !!locked;
          syncTypicalServiceTermGanttDateInputPickerState(input);
        };
        const syncConstraintDateState = function () {
          if (!constraintTypeInput || !constraintDateInput) return;
          const type = normalizeTypicalServiceTermGanttConstraintType(constraintTypeInput.value);
          const needsDate = !!type && type !== 'asap' && type !== 'alap';
          constraintDateInput.disabled = !needsDate;
          constraintDateInput.classList.toggle('readonly-field', !needsDate);
          if (!needsDate) constraintDateInput.value = '';
          syncTypicalServiceTermGanttDateInputPickerState(constraintDateInput);
        };
        const isParentTaskType = function () {
          const lightbox = node.closest?.('.gantt_cal_light') || document.querySelector('.gantt_cal_light');
          const typeSelect = lightbox?.querySelector('.gantt_section_type select, select[name="type"], select');
          const selectedType = normalizeFilterValue(typeSelect?.value || task?.type);
          const hasChildren = task?.id !== undefined
            && typeof gantt.hasChild === 'function'
            && gantt.hasChild(task.id);
          return selectedType === gantt.config.types.project || hasChildren;
        };
        const syncDurationMonths = function () {
          if (!durationMonthsInput) return;
          const days = Math.max(0, Number(String(durationInput.value || '').replace(',', '.')) || 0);
          const months = days / 30;
          durationMonthsInput.value = months.toFixed(1).replace('.', ',') + ' мес.';
        };
        const syncCalendarDurationFields = function () {
          const nextStart = startInput.value ? parseDate(startInput.value) : startDate;
          const nextEnd = endInput.value ? parseDate(endInput.value) : nextStart;
          const days = calculateTypicalServiceTermGanttCalendarDurationDays(nextStart, nextEnd, task);
          if (calendarDurationInput) calendarDurationInput.value = days === null ? '' : String(days);
          if (calendarDurationMonthsInput) {
            calendarDurationMonthsInput.value = days === null ? '' : (days / 30).toFixed(1).replace('.', ',') + ' мес.';
          }
        };
        const clampProgressInput = function () {
          if (!progressInput) return;
          const value = Number(String(progressInput.value || '').replace(',', '.'));
          if (!Number.isFinite(value)) return;
          progressInput.value = String(Math.max(0, Math.min(100, Math.round(value))));
        };
        const applyLockState = function () {
          const parentTaskType = isParentTaskType();
          const managedChecklistSectionTask = isTypicalServiceTermGanttManagedChecklistSectionTask(task);
          node.classList.toggle('policy-gantt-period-parent-task', parentTaskType);
          setReadonly(startInput, parentTaskType);
          startInput.classList.toggle('readonly-field', parentTaskType || durationEditMode);
          startInput.setAttribute('aria-readonly', (parentTaskType || durationEditMode) ? 'true' : 'false');
          setReadonly(endInput, parentTaskType);
          endInput.classList.toggle('readonly-field', parentTaskType || !durationEditMode);
          endInput.setAttribute('aria-readonly', (parentTaskType || !durationEditMode) ? 'true' : 'false');
          setReadonly(durationInput, parentTaskType || !durationEditMode);
          setReadonly(progressInput, parentTaskType || managedChecklistSectionTask);
          if (managedChecklistSectionTask && progressInput) {
            progressInput.title = 'Прогресс рассчитывается по статусам IMCM «Предоставлено» в таблице «Статусы запросов».';
          }
          setDatePickerLocked(startInput, parentTaskType || durationEditMode);
          setDatePickerLocked(endInput, parentTaskType || !durationEditMode);
          if (parentTaskType && progressInput) {
            syncTypicalServiceTermGanttParentProgress(gantt);
            progressInput.value = String(Math.round(Math.max(0, Math.min(1, Number(task?.progress) || 0)) * 100));
          }
          if (startLock) {
            startLock.classList.toggle('d-none', !(parentTaskType || durationEditMode));
            startLock.classList.toggle('bi-lock', parentTaskType);
            startLock.classList.toggle('bi-lock-fill', !parentTaskType);
            startLock.classList.toggle('policy-gantt-period-lock-fixed', parentTaskType);
            startLock.removeAttribute('role');
            if (!parentTaskType) startLock.setAttribute('role', 'button');
            startLock.title = parentTaskType
              ? 'Начало рассчитывается по подзадачам'
              : (durationEditMode ? 'Вернуться к редактированию начала' : '');
          }
          if (endLock) {
            endLock.classList.toggle('d-none', !parentTaskType);
            endLock.classList.toggle('policy-gantt-period-lock-fixed', parentTaskType);
            endLock.title = parentTaskType ? 'Окончание рассчитывается по подзадачам' : '';
          }
          if (durationLock) {
            durationLock.classList.toggle('bi-lock', parentTaskType);
            durationLock.classList.toggle('bi-lock-fill', !parentTaskType && !durationEditMode);
            durationLock.classList.toggle('bi-unlock-fill', !parentTaskType && durationEditMode);
            durationLock.classList.toggle('policy-gantt-period-lock-fixed', parentTaskType);
            durationLock.removeAttribute('role');
            if (!parentTaskType) durationLock.setAttribute('role', 'button');
            durationLock.title = parentTaskType
              ? 'Длительность рассчитывается по подзадачам'
              : (durationEditMode
                ? 'Заблокировать длительность'
                : 'Разблокировать ввод длительности');
          }
          if (timeboxAdjust) {
            timeboxAdjust.classList.toggle('policy-gantt-period-lock-fixed', parentTaskType);
            timeboxAdjust.classList.toggle('policy-gantt-period-timebox-adjust--active', !parentTaskType && timeboxAdjustMode);
            timeboxAdjust.classList.remove('bi-calendar3-range-fill');
            timeboxAdjust.classList.add('bi-calendar3-range');
            const timeboxActiveColor = !parentTaskType && timeboxAdjustMode;
            const timeboxBaseColor = timeboxActiveColor ? '#075D94' : '#adb5bd';
            timeboxAdjust.style.setProperty('color', timeboxBaseColor, 'important');
            timeboxAdjust.dataset.policyTimeboxBaseColor = timeboxBaseColor;
            if (!timeboxAdjust.$policyTimeboxHoverBound) {
              timeboxAdjust.$policyTimeboxHoverBound = true;
              timeboxAdjust.addEventListener('mouseenter', function () {
                timeboxAdjust.style.setProperty('color', '#075D94', 'important');
              });
              timeboxAdjust.addEventListener('mouseleave', function () {
                const baseColor = timeboxAdjust.dataset.policyTimeboxBaseColor || '#adb5bd';
                timeboxAdjust.style.setProperty('color', baseColor, 'important');
              });
            }
            timeboxAdjust.removeAttribute('role');
            if (!parentTaskType) timeboxAdjust.setAttribute('role', 'button');
            timeboxAdjust.title = parentTaskType
              ? 'Настройка таймбокса недоступна для родительской задачи'
              : (timeboxAdjustMode
                ? 'Сжимать в режиме таймбокса'
                : 'Не сжимать в режиме таймбокса');
          }
        };
        const syncDuration = function () {
          if (isParentTaskType()) {
            durationInput.value = String(calculateDuration(startDate, endDate, task));
            syncDurationMonths();
            syncCalendarDurationFields();
            return;
          }
          const nextStart = startInput.value ? parseDate(startInput.value) : startDate;
          const nextEnd = endInput.value ? parseDate(endInput.value) : nextStart;
          durationInput.value = String(calculateDuration(nextStart, nextEnd, task));
          syncDurationMonths();
          syncCalendarDurationFields();
        };
        const syncEndKeepingDuration = function () {
          if (isParentTaskType() || durationEditMode) return;
          const nextStart = startInput.value ? parseDate(startInput.value) : null;
          if (!nextStart) return;
          const nextEnd = calculateEndDate(nextStart, durationInput.value, task);
          if (nextEnd) endInput.value = formatDate(nextEnd);
          syncDurationMonths();
          syncCalendarDurationFields();
        };
        const syncStartKeepingDuration = function () {
          if (isParentTaskType()) return;
          if (durationEditMode) {
            syncDuration();
            return;
          }
          const nextEnd = endInput.value ? parseDate(endInput.value) : null;
          if (!nextEnd) return;
          const nextStart = calculateStartDate(nextEnd, durationInput.value, task);
          if (nextStart) startInput.value = formatDate(nextStart);
          syncCalendarDurationFields();
        };
        const syncEndFromDuration = function () {
          syncDurationMonths();
          if (isParentTaskType() || !durationEditMode) return;
          const nextStart = startInput.value ? parseDate(startInput.value) : startDate;
          if (!nextStart) return;
          const nextEnd = calculateEndDate(nextStart, durationInput.value, task);
          if (nextEnd) endInput.value = formatDate(nextEnd);
          syncCalendarDurationFields();
        };
        const toggleDurationEditMode = function (event) {
          if (event) {
            event.preventDefault();
            event.stopPropagation();
          }
          if (isParentTaskType()) return;
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
        const toggleTimeboxAdjustMode = function (event) {
          if (event) {
            event.preventDefault();
            event.stopPropagation();
          }
          if (isParentTaskType()) return;
          timeboxAdjustMode = !timeboxAdjustMode;
          applyLockState();
        };
        startLock?.addEventListener('click', toggleDurationEditMode);
        durationLock?.addEventListener('click', toggleDurationEditMode);
        timeboxAdjust?.addEventListener('click', toggleTimeboxAdjustMode);
        startInput.addEventListener('input', syncEndKeepingDuration);
        startInput.addEventListener('change', syncEndKeepingDuration);
        endInput.addEventListener('input', syncStartKeepingDuration);
        endInput.addEventListener('change', syncStartKeepingDuration);
        durationInput.addEventListener('input', syncEndFromDuration);
        durationInput.addEventListener('change', syncEndFromDuration);
        progressInput?.addEventListener('change', clampProgressInput);
        constraintTypeInput?.addEventListener('change', syncConstraintDateState);
        const lightbox = node.closest?.('.gantt_cal_light') || document.querySelector('.gantt_cal_light');
        const typeSelect = lightbox?.querySelector('.gantt_section_type select, select[name="type"], select');
        if (typeSelect?.$policyTypicalServiceTermPeriodChangeHandler) {
          typeSelect.removeEventListener('change', typeSelect.$policyTypicalServiceTermPeriodChangeHandler);
        }
        const typeChangeHandler = function () {
          applyLockState();
          syncDuration();
        };
        if (typeSelect) {
          typeSelect.$policyTypicalServiceTermPeriodChangeHandler = typeChangeHandler;
          typeSelect.addEventListener('change', typeChangeHandler);
        }
        applyLockState();
        syncConstraintDateState();
        syncDuration();
        syncDurationMonths();
        syncCalendarDurationFields();
      },
      get_value: function (node, task) {
        const constraintTypeValue = normalizeTypicalServiceTermGanttConstraintType(
          node.querySelector('.policy-gantt-period-constraint-type')?.value
        );
        const constraintDateValue = node.querySelector('.policy-gantt-period-constraint-date')?.value;
        if (constraintTypeValue) {
          if (gantt.$policyTypicalServiceTermClearedConstraintTaskIds && task?.id !== undefined && task?.id !== null) {
            delete gantt.$policyTypicalServiceTermClearedConstraintTaskIds[String(task.id)];
          }
          task.constraint_type = constraintTypeValue;
          if (constraintDateValue && constraintTypeValue !== 'asap' && constraintTypeValue !== 'alap') {
            task.constraint_date = parseDate(constraintDateValue);
          } else {
            delete task.constraint_date;
          }
        } else {
          gantt.$policyTypicalServiceTermClearedConstraintTaskIds = gantt.$policyTypicalServiceTermClearedConstraintTaskIds || {};
          if (task?.id !== undefined && task?.id !== null) {
            gantt.$policyTypicalServiceTermClearedConstraintTaskIds[String(task.id)] = true;
          }
          delete task.constraint_type;
          delete task.constraint_date;
        }
        return task;
      },
      focus: function (node) {
        node.querySelector('.policy-gantt-period-start')?.focus();
      },
    };
  }

  function ensureTypicalServiceTermGanttTaskNameBlock(gantt) {
    if (!gantt || gantt.$policyTypicalServiceTermTaskNameBlockRegistered) return;
    gantt.$policyTypicalServiceTermTaskNameBlockRegistered = true;
    const getLockedSystemTaskName = function (task) {
      const systemKey = normalizeFilterValue(task?.system_key);
      if (isTypicalServiceTermGanttManagedTask(task)) return normalizeFilterValue(task?.text);
      return TYPICAL_SERVICE_TERM_GANTT_SYSTEM_TASK_NAMES[systemKey] || '';
    };
    gantt.form_blocks.policy_task_name = {
      render: function (section) {
        return '<div class="gantt_cal_ltext gantt_section_' + section.name + ' policy-gantt-task-name">' +
          '<div class="policy-gantt-task-name-section-field d-none">' +
          '<label class="form-label" for="policy-gantt-task-name-section">Название раздела (услуг)</label>' +
          '<select id="policy-gantt-task-name-section" class="form-select policy-gantt-task-name-select" aria-label="Название раздела (услуг)"></select>' +
          '</div>' +
          '<div class="policy-gantt-task-name-text-field">' +
          '<label class="form-label" for="policy-gantt-task-name-text">Название</label>' +
          '<textarea id="policy-gantt-task-name-text" class="form-control policy-gantt-task-name-text" rows="1" aria-label="Название"></textarea>' +
          '</div>' +
          '</div>';
      },
      set_value: function (node, value, task) {
        const textarea = node.querySelector('.policy-gantt-task-name-text');
        const select = node.querySelector('.policy-gantt-task-name-select');
        const sectionField = node.querySelector('.policy-gantt-task-name-section-field');
        if (!textarea || !select || !sectionField) return;
        const outerLabel = node.previousElementSibling;
        if (outerLabel?.classList?.contains('gantt_cal_lsection')) {
          outerLabel.classList.add('policy-gantt-hidden-section-label');
          outerLabel.setAttribute('aria-hidden', 'true');
        }

        const getTypeSelect = function () {
          const lightbox = node.closest?.('.gantt_cal_light') || document.querySelector('.gantt_cal_light');
          return lightbox?.querySelector('.gantt_section_type select, select[name="type"]') || null;
        };
        const isServiceSectionType = function () {
          return normalizeFilterValue(getTypeSelect()?.value || task?.type) === TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE;
        };
        const lockedSystemTaskName = getLockedSystemTaskName(task);
        const managedPerformerTask = isTypicalServiceTermGanttManagedPerformerTask(task);
        const renderOptions = function (selectedValue) {
          const options = getTypicalServiceTermGanttSectionOptions();
          const currentValue = normalizeFilterValue(selectedValue || select.value || getTypicalServiceTermGanttTaskSectionName(task));
          if (!options.length) {
            select.innerHTML = '<option value="">Нет доступных разделов</option>';
            select.disabled = true;
            return [];
          }
          select.disabled = false;
          select.innerHTML = options.map(function (label) {
            return '<option value="' + escapePolicyHtml(label) + '">' + escapePolicyHtml(label) + '</option>';
          }).join('');
          select.value = options.indexOf(currentValue) === -1 ? options[0] : currentValue;
          return options;
        };
        const initialSectionName = getTypicalServiceTermGanttTaskSectionName(task);
        const initialText = normalizeFilterValue(lockedSystemTaskName || value || task?.text);
        const initialDisplayName = initialSectionName && initialText === initialSectionName ? '' : initialText;
        let lastSectionMode = isServiceSectionType();
        const syncMode = function (clearOnExitSection) {
          const sectionMode = isServiceSectionType();
          renderOptions();
          if (managedPerformerTask) {
            select.disabled = true;
            select.classList.add('readonly-field');
            select.title = 'Раздел управляется таблицей «Исполнители».';
          }
          sectionField.classList.toggle('d-none', !sectionMode);
          node.classList.toggle('policy-gantt-task-name--single-field', !sectionMode);
          if (!sectionMode && clearOnExitSection) {
            textarea.value = '';
          }
          lastSectionMode = sectionMode;
        };

        textarea.value = initialDisplayName;
        textarea.readOnly = !!lockedSystemTaskName;
        textarea.classList.toggle('readonly-field', !!lockedSystemTaskName);
        textarea.title = lockedSystemTaskName
          ? (isTypicalServiceTermGanttManagedAssetTask(task)
            ? 'Название актива управляется таблицей «Объем услуг: активы».'
            : 'Название системной задачи нельзя изменить.')
          : '';
        renderOptions(initialSectionName);

        const typeSelect = getTypeSelect();
        if (typeSelect?.$policyTypicalServiceTermNameChangeHandler) {
          typeSelect.removeEventListener('change', typeSelect.$policyTypicalServiceTermNameChangeHandler);
        }
        if (typeSelect) {
          typeSelect.$policyTypicalServiceTermNameChangeHandler = function () {
            syncMode(lastSectionMode);
          };
          typeSelect.addEventListener('change', typeSelect.$policyTypicalServiceTermNameChangeHandler);
        }
        syncMode(false);
      },
      get_value: function (node, task) {
        const lockedSystemTaskName = getLockedSystemTaskName(task);
        if (lockedSystemTaskName) {
          if (!isTypicalServiceTermGanttManagedPerformerTask(task)) {
            delete task.service_section_name;
            delete task.section_name;
          }
          task.text = lockedSystemTaskName;
          return lockedSystemTaskName;
        }
        const textarea = node.querySelector('.policy-gantt-task-name-text');
        const select = node.querySelector('.policy-gantt-task-name-select');
        const lightbox = node.closest?.('.gantt_cal_light') || document.querySelector('.gantt_cal_light');
        const typeSelect = lightbox?.querySelector('.gantt_section_type select, select[name="type"]') || null;
        const sectionMode = normalizeFilterValue(typeSelect?.value || task?.type) === TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE;
        if (sectionMode) {
          const sectionName = normalizeFilterValue(select?.value);
          const displayName = normalizeFilterValue(textarea?.value);
          task.service_section_name = sectionName;
          task.text = displayName || sectionName;
          return task.text;
        }
        const value = normalizeFilterValue(textarea?.value);
        delete task.service_section_name;
        delete task.section_name;
        task.text = value;
        return value;
      },
      focus: function (node) {
        const control = node.querySelector('.policy-gantt-task-name-select:not(:disabled), .policy-gantt-task-name-text:not([readonly])');
        control?.focus();
      },
    };
  }

  function ensureTypicalServiceTermGanttAssignmentBlock(gantt) {
    if (!gantt || gantt.$policyTypicalServiceTermAssignmentBlockRegistered) return;
    gantt.$policyTypicalServiceTermAssignmentBlockRegistered = true;
    gantt.form_blocks.policy_assignment = {
      render: function (section) {
        return '<div class="gantt_cal_ltext gantt_section_' + section.name + ' policy-gantt-assignment">' +
          '<div class="policy-gantt-assignment-grid">' +
          '<div class="policy-gantt-assignment-field">' +
          '<label class="form-label" for="policy-gantt-specialty-select">Специальность</label>' +
          '<select id="policy-gantt-specialty-select" class="form-select policy-gantt-specialty-select" aria-label="Специальность"></select>' +
          '</div>' +
          '<div class="policy-gantt-assignment-field">' +
          '<label class="form-label" for="policy-gantt-executor-select">Исполнитель</label>' +
          '<select id="policy-gantt-executor-select" class="form-select policy-gantt-executor-select" aria-label="Исполнитель"></select>' +
          '</div>' +
          '</div>' +
          '</div>';
      },
      set_value: function (node, value, task) {
        const specialtySelect = node.querySelector('.policy-gantt-specialty-select');
        const executorSelect = node.querySelector('.policy-gantt-executor-select');
        if (!specialtySelect || !executorSelect) return;

        const normalizeOption = function (option) {
          const value = normalizeFilterValue(
            typeof option === 'string'
              ? option
              : (option?.value || option?.id || option?.label || option?.name || '')
          );
          const label = normalizeFilterValue(
            typeof option === 'string'
              ? option
              : (option?.label || option?.name || option?.value || option?.id || '')
          );
          if (!value || !label) return null;
          return { value: value, label: label };
        };
        const normalizeOptions = function (options) {
          const seen = new Set();
          return (Array.isArray(options) ? options : [])
            .map(normalizeOption)
            .filter(function (option) {
              if (!option || seen.has(option.value)) return false;
              seen.add(option.value);
              return true;
            });
        };
        const optionHtml = function (options) {
          return '<option value=""></option>' + options.map(function (option) {
            return '<option value="' + escapePolicyHtml(option.value) + '">' +
              escapePolicyHtml(option.label) + '</option>';
          }).join('');
        };
        const setSelectOptions = function (select, options, selectedValue, preserveSelected) {
          const normalizedOptions = normalizeOptions(options);
          const currentValue = normalizeFilterValue(selectedValue);
          if (preserveSelected && currentValue && !normalizedOptions.some(function (option) {
            return option.value === currentValue || option.label === currentValue;
          })) {
            normalizedOptions.push({ value: currentValue, label: currentValue });
          }
          select.innerHTML = optionHtml(normalizedOptions);
          const selectedOption = normalizedOptions.find(function (option) {
            return option.value === currentValue || option.label === currentValue;
          });
          select.value = selectedOption ? selectedOption.value : '';
          return normalizedOptions;
        };
        const getLightbox = function () {
          return node.closest?.('.gantt_cal_light') || document.querySelector('.gantt_cal_light');
        };
        const getTypeSelect = function () {
          const lightbox = getLightbox();
          return lightbox?.querySelector('.gantt_section_type select, select[name="type"]') || null;
        };
        const getNameSelect = function () {
          const lightbox = getLightbox();
          return lightbox?.querySelector('.policy-gantt-task-name-select') || null;
        };
        const getSelectedSectionName = function () {
          const nameSelect = getNameSelect();
          return normalizeFilterValue(nameSelect?.value || getTypicalServiceTermGanttTaskSectionName(task));
        };
        const isServiceSectionType = function () {
          return normalizeFilterValue(getTypeSelect()?.value || task?.type) === TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE;
        };
        const isParentTask = function () {
          return isTypicalServiceTermGanttSummaryTask(gantt, task);
        };
        const isManagedPerformerTask = function () {
          return isTypicalServiceTermGanttManagedPerformerTask(task);
        };
        const isManagedAssignmentTask = function () {
          return isTypicalServiceTermGanttManagedPerformerTask(task)
            || isTypicalServiceTermGanttManagedChecklistSectionTask(task);
        };
        const applyReadonly = function (select, locked) {
          select.disabled = !!locked;
          select.classList.toggle('readonly-field', !!locked);
          if (locked && isManagedAssignmentTask()) {
            select.title = isTypicalServiceTermGanttManagedChecklistSectionTask(task)
              ? 'Для разделов «Исходные данные» исполнитель и специальность не назначаются: это задача заказчика.'
              : 'Поле управляется таблицей «Исполнители».';
          } else if (!locked) {
            select.title = '';
          }
        };
        const syncExecutorOptions = function (forceDefault) {
          const specialty = normalizeFilterValue(specialtySelect.value);
          const currentValue = normalizeFilterValue(executorSelect.value || task?.executor);
          setSelectOptions(
            executorSelect,
            getTypicalServiceTermGanttExecutorOptions(specialty),
            forceDefault ? '' : currentValue,
            isManagedAssignmentTask()
          );
          applyReadonly(executorSelect, isParentTask() || !specialty || isManagedAssignmentTask());
        };
        const applySpecialtyState = function (forceDefault) {
          if (isParentTask()) {
            setSelectOptions(specialtySelect, getTypicalServiceTermGanttSpecialtyOptions(), '');
            setSelectOptions(executorSelect, [], '');
            applyReadonly(specialtySelect, true);
            applyReadonly(executorSelect, true);
            return;
          }
          const currentValue = normalizeFilterValue(specialtySelect.value || task?.specialty);
          if (!isServiceSectionType()) {
            setSelectOptions(specialtySelect, getTypicalServiceTermGanttSpecialtyOptions(), forceDefault ? '' : currentValue);
            applyReadonly(specialtySelect, isManagedAssignmentTask());
            return;
          }

          const section = getTypicalServiceTermGanttSectionByLabel(getSelectedSectionName());
          const sectionSpecialties = (section?.specialties || []).map(function (item) { return item.label; });
          if (!sectionSpecialties.length) {
            setSelectOptions(specialtySelect, [], '');
            applyReadonly(specialtySelect, true);
            return;
          }

          setSelectOptions(specialtySelect, sectionSpecialties, currentValue, isManagedAssignmentTask());
          if (sectionSpecialties.length === 1) {
            specialtySelect.value = sectionSpecialties[0];
            applyReadonly(specialtySelect, true);
            return;
          }
          if (forceDefault || sectionSpecialties.indexOf(specialtySelect.value) === -1) {
            specialtySelect.value = sectionSpecialties[0];
          }
          applyReadonly(specialtySelect, isManagedAssignmentTask());
        };

        applySpecialtyState(false);
        syncExecutorOptions(false);
        specialtySelect.addEventListener('change', function () {
          syncExecutorOptions(true);
        });

        const typeSelect = getTypeSelect();
        if (typeSelect?.$policyTypicalServiceTermAssignmentChangeHandler) {
          typeSelect.removeEventListener('change', typeSelect.$policyTypicalServiceTermAssignmentChangeHandler);
        }
        if (typeSelect) {
          const typeChangeHandler = function () {
            requestAnimationFrame(function () {
              applySpecialtyState(true);
              syncExecutorOptions(true);
            });
          };
          typeSelect.$policyTypicalServiceTermAssignmentChangeHandler = typeChangeHandler;
          typeSelect.addEventListener('change', typeChangeHandler);
        }
        const nameSelect = getNameSelect();
        if (nameSelect?.$policyTypicalServiceTermAssignmentChangeHandler) {
          nameSelect.removeEventListener('change', nameSelect.$policyTypicalServiceTermAssignmentChangeHandler);
        }
        if (nameSelect) {
          const nameChangeHandler = function () {
            applySpecialtyState(true);
            syncExecutorOptions(true);
          };
          nameSelect.$policyTypicalServiceTermAssignmentChangeHandler = nameChangeHandler;
          nameSelect.addEventListener('change', nameChangeHandler);
        }
      },
      get_value: function (node, task) {
        if (isTypicalServiceTermGanttManagedPerformerTask(task) || isTypicalServiceTermGanttManagedChecklistSectionTask(task)) {
          return task;
        }
        if (isTypicalServiceTermGanttSummaryTask(gantt, task)) {
          task.specialty = '';
          task.executor = '';
          delete task.resource_id;
          delete task.resource_name;
          return task;
        }
        const specialty = normalizeFilterValue(node.querySelector('.policy-gantt-specialty-select')?.value);
        const executor = normalizeFilterValue(node.querySelector('.policy-gantt-executor-select')?.value);
        task.specialty = specialty;
        task.executor = executor;
        return task;
      },
      focus: function (node) {
        node.querySelector('.policy-gantt-specialty-select')?.focus();
      },
    };
  }

  function ensureTypicalServiceTermGanttLinksBlock(gantt) {
    if (!gantt || gantt.$policyTypicalServiceTermLinksBlockRegistered) return;
    gantt.$policyTypicalServiceTermLinksBlockRegistered = true;
    gantt.form_blocks.policy_links = {
      render: function (section) {
        return '<div class="gantt_cal_ltext gantt_section_' + section.name + ' policy-gantt-links">' +
          '<div class="policy-gantt-links-title">Связи</div>' +
          '<div class="policy-gantt-links-editor">' +
          '<div class="table-responsive">' +
          '<table class="table table-sm align-middle policy-gantt-links-table">' +
          '<thead><tr>' +
          '<th class="policy-gantt-links-check-col"></th>' +
          '<th>Название задачи</th>' +
          '<th>Тип связи</th>' +
          '<th>Лаг</th>' +
          '</tr></thead>' +
          '<tbody class="policy-gantt-links-tbody"></tbody>' +
          '</table>' +
          '</div>' +
          '<div class="d-flex align-items-stretch gap-2 policy-gantt-links-actions-row">' +
          '<button type="button" class="btn btn-sm policy-gantt-links-add-btn">' +
          '<i class="bi bi-plus-circle me-2"></i>Добавить связь' +
          '</button>' +
          '<div class="policy-gantt-links-row-actions d-none d-flex">' +
          '<div class="btn-group">' +
          '<button type="button" class="btn btn-outline-primary btn-sm policy-gantt-links-up-btn" title="Переместить вверх" aria-label="Переместить вверх">' +
          '<i class="bi bi-arrow-up-square"></i>' +
          '</button>' +
          '<button type="button" class="btn btn-outline-primary btn-sm policy-gantt-links-down-btn" title="Переместить вниз" aria-label="Переместить вниз">' +
          '<i class="bi bi-arrow-down-square"></i>' +
          '</button>' +
          '<button type="button" class="btn btn-outline-danger btn-sm policy-gantt-links-delete-btn" title="Удалить" aria-label="Удалить">' +
          '<i class="bi bi-x-square"></i>' +
          '</button>' +
          '</div>' +
          '</div>' +
          '</div>' +
          '</div>' +
          '</div>';
      },
      set_value: function (node, value, task) {
        const tbody = node.querySelector('.policy-gantt-links-tbody');
        const addBtn = node.querySelector('.policy-gantt-links-add-btn');
        const actions = node.querySelector('.policy-gantt-links-row-actions');
        const upBtn = node.querySelector('.policy-gantt-links-up-btn');
        const downBtn = node.querySelector('.policy-gantt-links-down-btn');
        const deleteBtn = node.querySelector('.policy-gantt-links-delete-btn');
        if (!tbody || !addBtn || !task) return;
        const currentTaskId = String(task.id || '');
        const linkTypes = getTypicalServiceTermGanttLinkTypeOptions(gantt);
        const taskOptions = [];
        if (typeof gantt.eachTask === 'function') {
          gantt.eachTask(function (item) {
            if (!item || String(item.id) === currentTaskId) return;
            const wbs = getTypicalServiceTermGanttWbsCode(gantt, item);
            const text = normalizeFilterValue(item.text) || gantt?.locale?.labels?.new_task || 'Новая задача';
            taskOptions.push({
              id: String(item.id),
              label: (wbs ? wbs + ' ' : '') + text,
            });
          });
        }

        const renderOptions = function (options, selectedValue) {
          const selected = String(selectedValue ?? '');
          return options.map(function (option) {
            return '<option value="' + escapePolicyHtml(option.id ?? option.key) + '"' +
              (String(option.id ?? option.key) === selected ? ' selected' : '') + '>' +
              escapePolicyHtml(option.label) +
              '</option>';
          }).join('');
        };
        const getCurrentTaskLiveDates = function () {
          const lightbox = node.closest?.('.gantt_cal_light') || document.querySelector('.gantt_cal_light');
          const startInput = lightbox?.querySelector('.policy-gantt-period-start');
          const endInput = lightbox?.querySelector('.policy-gantt-period-end');
          const currentStart = (startInput && parseTypicalServiceTermGanttDateInput(startInput.value))
            || (task.start_date instanceof Date ? task.start_date : null);
          const currentEnd = (endInput && parseTypicalServiceTermGanttDateInput(endInput.value))
            || (task.end_date instanceof Date ? task.end_date : null);
          if (!(currentStart instanceof Date) || !(currentEnd instanceof Date)) return null;
          return { start_date: currentStart, end_date: currentEnd };
        };
        const computeRowEffectiveLag = function (row) {
          const sourceId = normalizeFilterValue(row.querySelector('.policy-gantt-links-source')?.value);
          const linkType = normalizeTypicalServiceTermGanttLinkType(gantt, row.querySelector('.policy-gantt-links-type')?.value);
          if (!sourceId) return null;
          let related = null;
          try {
            related = typeof gantt.getTask === 'function' ? gantt.getTask(sourceId) : null;
          } catch (_) {
            related = null;
          }
          if (!related) return null;
          const liveTask = getCurrentTaskLiveDates() || task;
          const direction = row.dataset.direction === 'outgoing' ? 'outgoing' : 'incoming';
          const sourceTask = direction === 'outgoing' ? liveTask : related;
          const targetTask = direction === 'outgoing' ? related : liveTask;
          const effective = computeTypicalServiceTermGanttEffectiveLag(gantt, sourceTask, targetTask, linkType);
          return Number.isFinite(effective) ? effective : null;
        };
        const applyLagModeToRow = function (row) {
          const mode = row.dataset.lagMode === 'fixed' ? 'fixed' : 'auto';
          const lagInput = row.querySelector('.policy-gantt-links-lag');
          const fixedBtn = row.querySelector('.policy-gantt-links-lag-mode-fixed');
          const autoBtn = row.querySelector('.policy-gantt-links-lag-mode-auto');
          const fixedIcon = fixedBtn?.querySelector('i');
          const autoIcon = autoBtn?.querySelector('i');
          if (!lagInput) return;
          if (mode === 'auto') {
            const effective = computeRowEffectiveLag(row);
            lagInput.value = effective === null ? '' : String(effective);
            lagInput.readOnly = true;
            lagInput.tabIndex = -1;
            lagInput.classList.add('readonly-field');
          } else {
            lagInput.readOnly = false;
            lagInput.removeAttribute('tabindex');
            lagInput.classList.remove('readonly-field');
          }
          if (fixedBtn) {
            fixedBtn.classList.toggle('policy-gantt-links-lag-mode-btn--active', mode === 'fixed');
            fixedBtn.setAttribute('title', mode === 'fixed'
              ? 'Лаг зафиксирован вручную. Нажмите для возврата к автоопределению.'
              : 'Зафиксировать значение лага вручную.');
            fixedBtn.setAttribute('aria-pressed', mode === 'fixed' ? 'true' : 'false');
          }
          if (autoBtn) {
            autoBtn.classList.toggle('policy-gantt-links-lag-mode-btn--active', mode === 'auto');
            autoBtn.setAttribute('title', mode === 'auto'
              ? 'Лаг определяется автоматически по фактическим датам.'
              : 'Включить автоматическое определение лага.');
            autoBtn.setAttribute('aria-pressed', mode === 'auto' ? 'true' : 'false');
          }
          if (fixedIcon) fixedIcon.className = mode === 'fixed' ? 'bi bi-file-lock-fill' : 'bi bi-file-lock';
          if (autoIcon) autoIcon.className = mode === 'auto' ? 'bi bi-calculator-fill' : 'bi bi-calculator';
        };
        const refreshAutoLagDisplays = function () {
          Array.from(tbody.querySelectorAll('.policy-gantt-links-row')).forEach(function (row) {
            if (row.dataset.lagMode === 'fixed') return;
            applyLagModeToRow(row);
          });
        };
        const makeRow = function (link) {
          const row = document.createElement('tr');
          const linkId = normalizeFilterValue(link?.id);
          const direction = String(link?.source) === currentTaskId ? 'outgoing' : 'incoming';
          const relatedTaskId = direction === 'outgoing'
            ? String(link?.target || taskOptions[0]?.id || '')
            : String(link?.source || taskOptions[0]?.id || '');
          const linkType = normalizeTypicalServiceTermGanttLinkType(gantt, link?.type);
          const lag = normalizeTypicalServiceTermGanttLag(link?.lag);
          const lagMode = normalizeTypicalServiceTermGanttLagMode(link?.lag_mode);
          row.className = 'policy-gantt-links-row';
          row.dataset.linkId = linkId;
          row.dataset.direction = direction;
          row.dataset.lagMode = lagMode;
          row.innerHTML =
            '<td class="policy-gantt-links-check-cell">' +
            '<div class="form-check policy-gantt-links-check-wrap">' +
            '<input type="checkbox" class="form-check-input policy-gantt-links-check" aria-label="Выделить связь">' +
            '</div>' +
            '</td>' +
            '<td>' +
            '<select class="form-select policy-gantt-links-source" aria-label="Название задачи">' +
            renderOptions(taskOptions, relatedTaskId) +
            '</select>' +
            '</td>' +
            '<td>' +
            '<select class="form-select policy-gantt-links-type" aria-label="Тип связи">' +
            renderOptions(linkTypes.map(function (option) {
              return { id: option.key, label: option.label };
            }), linkType) +
            '</select>' +
            '</td>' +
            '<td>' +
            '<div class="policy-gantt-links-lag-wrap">' +
            '<button type="button" class="btn btn-link policy-gantt-links-lag-mode-btn policy-gantt-links-lag-mode-fixed" tabindex="-1">' +
            '<i class="bi bi-file-lock"></i>' +
            '</button>' +
            '<button type="button" class="btn btn-link policy-gantt-links-lag-mode-btn policy-gantt-links-lag-mode-auto" tabindex="-1">' +
            '<i class="bi bi-calculator"></i>' +
            '</button>' +
            '<input type="number" class="form-control policy-gantt-links-lag" step="1" value="' + escapePolicyHtml(String(lag)) + '" aria-label="Лаг">' +
            '</div>' +
            '</td>';
          row.querySelector('.policy-gantt-links-source').disabled = !taskOptions.length;
          row.querySelector('.policy-gantt-links-type').disabled = !taskOptions.length;
          row.querySelector('.policy-gantt-links-lag').disabled = !taskOptions.length;
          const fixedBtn = row.querySelector('.policy-gantt-links-lag-mode-fixed');
          const autoBtn = row.querySelector('.policy-gantt-links-lag-mode-auto');
          if (fixedBtn) fixedBtn.disabled = !taskOptions.length;
          if (autoBtn) autoBtn.disabled = !taskOptions.length;
          applyLagModeToRow(row);
          return row;
        };
        const getCheckedRows = function () {
          return Array.from(tbody.querySelectorAll('.policy-gantt-links-row')).filter(function (row) {
            return !!row.querySelector('.policy-gantt-links-check')?.checked;
          });
        };
        const getLightbox = function () {
          return node.closest?.('.gantt_cal_light') || document.querySelector('.gantt_cal_light');
        };
        const maxDate = function (dates) {
          return dates
            .filter(function (date) { return date instanceof Date && !Number.isNaN(date.getTime()); })
            .sort(function (left, right) { return right - left; })[0] || null;
        };
        const updateDurationMonths = function (durationInput, monthsInput) {
          if (!durationInput || !monthsInput) return;
          const days = Math.max(0, Number(String(durationInput.value || '').replace(',', '.')) || 0);
          monthsInput.value = (days / 30).toFixed(1).replace('.', ',') + ' мес.';
        };
        const updateCalendarDurationFields = function (startInput, endInput, calendarDurationInput, calendarMonthsInput) {
          const startDate = parseTypicalServiceTermGanttDateInput(startInput?.value);
          const endDate = parseTypicalServiceTermGanttDateInput(endInput?.value);
          const days = calculateTypicalServiceTermGanttCalendarDurationDays(startDate, endDate, task);
          if (calendarDurationInput) calendarDurationInput.value = days === null ? '' : String(days);
          if (calendarMonthsInput) {
            calendarMonthsInput.value = days === null ? '' : (days / 30).toFixed(1).replace('.', ',') + ' мес.';
          }
        };
        const syncPeriodFromRows = function () {
          const lightbox = getLightbox();
          const periodNode = lightbox?.querySelector('.policy-gantt-period');
          if (!periodNode || periodNode.classList.contains('policy-gantt-period-parent-task')) return;
          const startInput = lightbox.querySelector('.policy-gantt-period-start');
          const endInput = lightbox.querySelector('.policy-gantt-period-end');
          const durationInput = lightbox.querySelector('.policy-gantt-period-duration');
          const monthsInput = lightbox.querySelector('.policy-gantt-period-duration-months');
          const calendarDurationInput = lightbox.querySelector('.policy-gantt-period-calendar-duration');
          const calendarMonthsInput = lightbox.querySelector('.policy-gantt-period-calendar-duration-months');
          if (!startInput || !endInput) return;
          const linkTypesConfig = gantt.config?.links || {};
          const startBounds = [];
          const endBounds = [];
          Array.from(tbody.querySelectorAll('.policy-gantt-links-row')).forEach(function (row) {
            if (row.dataset.direction === 'outgoing') return;
            if (row.dataset.lagMode !== 'fixed') return;
            const sourceId = normalizeFilterValue(row.querySelector('.policy-gantt-links-source')?.value);
            if (!sourceId) return;
            let sourceTask = null;
            try {
              sourceTask = typeof gantt.getTask === 'function' ? gantt.getTask(sourceId) : null;
            } catch (_) {
              sourceTask = null;
            }
            if (!sourceTask || !(sourceTask.start_date instanceof Date) || !(sourceTask.end_date instanceof Date)) return;
            const lag = normalizeTypicalServiceTermGanttLag(row.querySelector('.policy-gantt-links-lag')?.value);
            const linkType = normalizeTypicalServiceTermGanttLinkType(gantt, row.querySelector('.policy-gantt-links-type')?.value);
            if (linkType === String(linkTypesConfig.start_to_start)) {
              startBounds.push(addPolicyGanttDays(sourceTask.start_date, lag));
            } else if (linkType === String(linkTypesConfig.finish_to_finish)) {
              endBounds.push(addPolicyGanttDays(sourceTask.end_date, lag));
            } else if (linkType === String(linkTypesConfig.start_to_finish)) {
              endBounds.push(addPolicyGanttDays(sourceTask.start_date, lag));
            } else {
              startBounds.push(addPolicyGanttDays(sourceTask.end_date, lag));
            }
          });
          const startBound = maxDate(startBounds);
          const endBound = maxDate(endBounds);
          if (!startBound && !endBound) return;
          const currentStart = parseTypicalServiceTermGanttDateInput(startInput.value) || (task.start_date instanceof Date ? task.start_date : null);
          const currentEnd = parseTypicalServiceTermGanttDateInput(endInput.value) || (task.end_date instanceof Date ? task.end_date : null);
          const taskType = normalizeFilterValue(lightbox.querySelector('.gantt_section_type select, select[name="type"]')?.value || task.type);
          const duration = taskType === gantt.config?.types?.milestone
            ? 0
            : Math.max(0, Math.round(Number(durationInput?.value) || (
              currentStart && currentEnd ? calculateTypicalServiceTermGanttDuration(gantt, currentStart, currentEnd, task) : Number(task.duration || 0)
            )));
          let nextStart = currentStart || startBound || (endBound ? calculateTypicalServiceTermGanttStartDate(gantt, endBound, duration, task) : null);
          let nextEnd = currentEnd || (nextStart ? calculateTypicalServiceTermGanttEndDate(gantt, nextStart, duration, task) : null);
          if (endBound) {
            const startFromEnd = calculateTypicalServiceTermGanttStartDate(gantt, endBound, duration, task);
            nextStart = startFromEnd instanceof Date ? startFromEnd : nextStart;
            nextEnd = endBound;
          }
          if (startBound) {
            nextStart = startBound;
            nextEnd = calculateTypicalServiceTermGanttEndDate(gantt, nextStart, duration, task);
          }
          if (!(nextStart instanceof Date) || !(nextEnd instanceof Date)) return;
          startInput.value = formatTypicalServiceTermGanttDateInput(nextStart);
          endInput.value = formatTypicalServiceTermGanttDateInput(nextEnd);
          if (durationInput) durationInput.value = String(duration);
          updateDurationMonths(durationInput, monthsInput);
          updateCalendarDurationFields(startInput, endInput, calendarDurationInput, calendarMonthsInput);
          refreshAutoLagDisplays();
        };
        const schedulePeriodSync = function () {
          requestAnimationFrame(syncPeriodFromRows);
        };
        const handleLagInput = function (row) {
          if (row.dataset.lagMode !== 'fixed') {
            row.dataset.lagMode = 'fixed';
            applyLagModeToRow(row);
          }
          schedulePeriodSync();
        };
        const setRowLagMode = function (row, nextMode) {
          const target = nextMode === 'fixed' ? 'fixed' : 'auto';
          if (row.dataset.lagMode === target) return;
          row.dataset.lagMode = target;
          applyLagModeToRow(row);
          if (target === 'fixed') schedulePeriodSync();
        };
        const handleStructuralChange = function (row) {
          applyLagModeToRow(row);
          schedulePeriodSync();
        };
        const bindRowEvents = function (row) {
          row.querySelector('.policy-gantt-links-check')?.addEventListener('change', syncActions);
          row.querySelector('.policy-gantt-links-source')?.addEventListener('change', function () { handleStructuralChange(row); });
          row.querySelector('.policy-gantt-links-type')?.addEventListener('change', function () { handleStructuralChange(row); });
          const lagInput = row.querySelector('.policy-gantt-links-lag');
          lagInput?.addEventListener('input', function () { handleLagInput(row); });
          lagInput?.addEventListener('change', function () { handleLagInput(row); });
          row.querySelector('.policy-gantt-links-lag-mode-fixed')?.addEventListener('click', function (event) {
            event.preventDefault();
            setRowLagMode(row, 'fixed');
          });
          row.querySelector('.policy-gantt-links-lag-mode-auto')?.addEventListener('click', function (event) {
            event.preventDefault();
            setRowLagMode(row, 'auto');
          });
        };
        const syncActions = function () {
          const checkedRows = getCheckedRows();
          if (actions) actions.classList.toggle('d-none', !checkedRows.length);
          const singleRow = checkedRows.length === 1 ? checkedRows[0] : null;
          if (upBtn) upBtn.disabled = !singleRow || !singleRow.previousElementSibling;
          if (downBtn) downBtn.disabled = !singleRow || !singleRow.nextElementSibling;
          if (deleteBtn) deleteBtn.disabled = !checkedRows.length;
        };

        tbody.innerHTML = '';
        const relatedLinks = typeof gantt.getLinks === 'function'
          ? gantt.getLinks().filter(function (link) {
            return String(link?.target) === currentTaskId || String(link?.source) === currentTaskId;
          })
          : [];
        relatedLinks.forEach(function (link) {
          const row = makeRow(link);
          tbody.appendChild(row);
          bindRowEvents(row);
        });
        addBtn.disabled = !taskOptions.length;
        addBtn.addEventListener('click', function () {
          if (!taskOptions.length) return;
          const row = makeRow({ source: taskOptions[0].id, target: currentTaskId, type: linkTypes[0].key, lag: 0, lag_mode: 'fixed' });
          tbody.appendChild(row);
          bindRowEvents(row);
          syncActions();
        });
        upBtn?.addEventListener('click', function () {
          const row = getCheckedRows()[0];
          if (!row || !row.previousElementSibling) return;
          tbody.insertBefore(row, row.previousElementSibling);
          syncActions();
        });
        downBtn?.addEventListener('click', function () {
          const row = getCheckedRows()[0];
          if (!row || !row.nextElementSibling) return;
          tbody.insertBefore(row.nextElementSibling, row);
          syncActions();
        });
        deleteBtn?.addEventListener('click', function () {
          getCheckedRows().forEach(function (row) { row.remove(); });
          syncActions();
          syncPeriodFromRows();
        });
        syncActions();
      },
      get_value: function (node, task) {
        return task;
      },
      focus: function (node) {
        node.querySelector('.policy-gantt-links-source')?.focus();
      },
    };
  }

  function serializeTypicalServiceTermGanttLightboxLinks(lightbox, currentTaskId, gantt) {
    const normalizedCurrentTaskId = String(currentTaskId || '');
    if (!lightbox || !normalizedCurrentTaskId) return [];
    return Array.from(lightbox.querySelectorAll('.policy-gantt-links-row'))
      .map(function (row, index) {
        const relatedTaskId = normalizeFilterValue(row.querySelector('.policy-gantt-links-source')?.value);
        if (!relatedTaskId || relatedTaskId === normalizedCurrentTaskId) return null;
        const isOutgoing = row.dataset.direction === 'outgoing';
        const source = isOutgoing ? normalizedCurrentTaskId : relatedTaskId;
        const target = isOutgoing ? relatedTaskId : normalizedCurrentTaskId;
        const lagMode = row.dataset.lagMode === 'fixed' ? 'fixed' : 'auto';
        return {
          id: normalizeFilterValue(row.dataset.linkId) || ('typical-service-term-link-' + normalizedCurrentTaskId + '-' + index + '-' + Date.now()),
          source: source,
          target: target,
          type: normalizeTypicalServiceTermGanttLinkType(gantt, row.querySelector('.policy-gantt-links-type')?.value),
          lag: normalizeTypicalServiceTermGanttLag(row.querySelector('.policy-gantt-links-lag')?.value),
          lag_mode: lagMode,
        };
      })
      .filter(Boolean);
  }

  function applyTypicalServiceTermGanttLightboxLinks(gantt, lightbox, currentTaskId) {
    if (!gantt || !lightbox || !currentTaskId || typeof gantt.getLinks !== 'function') return;
    const normalizedCurrentTaskId = String(currentTaskId);
    const nextLinks = serializeTypicalServiceTermGanttLightboxLinks(lightbox, normalizedCurrentTaskId, gantt);
    const apply = function () {
      (gantt.getLinks() || [])
        .filter(function (link) {
          return String(link?.target) === normalizedCurrentTaskId || String(link?.source) === normalizedCurrentTaskId;
        })
        .forEach(function (link) {
          if (link?.id !== undefined && typeof gantt.deleteLink === 'function') {
            gantt.deleteLink(link.id);
          }
        });
      nextLinks.forEach(function (link) {
        if (typeof gantt.addLink === 'function') {
          gantt.addLink(link);
        }
      });
      if (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(normalizedCurrentTaskId)) return;
      if (typeof gantt.updateTask === 'function') {
        gantt.updateTask(normalizedCurrentTaskId);
      } else if (typeof gantt.refreshData === 'function') {
        gantt.refreshData();
      }
    };
    if (typeof gantt.batchUpdate === 'function') {
      gantt.batchUpdate(apply);
    } else {
      apply();
    }
    gantt.$policyTypicalServiceTermPendingLinkReschedule = String(normalizedCurrentTaskId);
  }

  function rememberTypicalServiceTermGanttFixedDragBaseline(gantt, taskId) {
    if (!gantt || !taskId || typeof gantt.getTask !== 'function') return;
    let task = null;
    try { task = gantt.getTask(taskId); } catch (_) { task = null; }
    if (!task || !(task.start_date instanceof Date)) return;
    gantt.$policyTypicalServiceTermDragBaseline = {
      id: String(taskId),
      start: new Date(task.start_date),
    };
  }

  function applyTypicalServiceTermGanttSnapNewLink(gantt, link) {
    if (!gantt || !link || typeof gantt.getTask !== 'function') return false;
    if (normalizeTypicalServiceTermGanttLagMode(link.lag_mode) !== 'fixed') return false;
    let source = null;
    let target = null;
    try { source = gantt.getTask(link.source); } catch (_) { source = null; }
    try { target = gantt.getTask(link.target); } catch (_) { target = null; }
    if (!source || !target) return false;
    if (isTypicalServiceTermGanttSummaryTask(gantt, target)) return false;
    if (!(source.start_date instanceof Date) || !(source.end_date instanceof Date)) return false;
    if (!(target.start_date instanceof Date) || !(target.end_date instanceof Date)) return false;
    const types = gantt.config?.links || { finish_to_start: '0', start_to_start: '1', finish_to_finish: '2', start_to_finish: '3' };
    const linkType = String(link.type);
    const lag = normalizeTypicalServiceTermGanttLag(link.lag);
    let changed = false;
    const wasActive = gantt.$policyTypicalServiceTermSchedulingActive;
    gantt.$policyTypicalServiceTermSchedulingActive = true;
    try {
      if (linkType === String(types.start_to_start)) {
        const bound = addPolicyGanttDays(source.start_date, lag);
        if (target.start_date.valueOf() !== bound.valueOf()) {
          changed = setTypicalServiceTermGanttTaskStart(gantt, target, bound);
        }
      } else if (linkType === String(types.finish_to_finish)) {
        const bound = addPolicyGanttDays(source.end_date, lag);
        if (target.end_date.valueOf() !== bound.valueOf()) {
          changed = setTypicalServiceTermGanttTaskEnd(gantt, target, bound);
        }
      } else if (linkType === String(types.start_to_finish)) {
        const bound = addPolicyGanttDays(source.start_date, lag);
        if (target.end_date.valueOf() !== bound.valueOf()) {
          changed = setTypicalServiceTermGanttTaskEnd(gantt, target, bound);
        }
      } else {
        const bound = addPolicyGanttDays(source.end_date, lag);
        if (target.start_date.valueOf() !== bound.valueOf()) {
          changed = setTypicalServiceTermGanttTaskStart(gantt, target, bound);
        }
      }
    } finally {
      gantt.$policyTypicalServiceTermSchedulingActive = wasActive;
    }
    if (changed && typeof gantt.updateTask === 'function') {
      try { gantt.updateTask(target.id); } catch (_) { /* noop */ }
    }
    return changed;
  }

  function applyTypicalServiceTermGanttRigidDragShift(gantt, taskId) {
    if (!gantt || !taskId) return false;
    if (typeof gantt.getTask !== 'function' || typeof gantt.getLinks !== 'function') return false;
    const baseline = gantt.$policyTypicalServiceTermDragBaseline;
    if (!baseline || baseline.id !== String(taskId)) {
      delete gantt.$policyTypicalServiceTermDragBaseline;
      return false;
    }
    delete gantt.$policyTypicalServiceTermDragBaseline;
    let draggedTask = null;
    try { draggedTask = gantt.getTask(taskId); } catch (_) { draggedTask = null; }
    if (!draggedTask || !(draggedTask.start_date instanceof Date)) return false;
    const deltaDays = Math.round((draggedTask.start_date.getTime() - baseline.start.getTime()) / 86400000);
    if (!deltaDays) return false;
    const links = gantt.getLinks() || [];
    const fixedLinks = links.filter(function (link) {
      return normalizeTypicalServiceTermGanttLagMode(link.lag_mode) === 'fixed';
    });
    if (!fixedLinks.length) return false;
    const draggedKey = String(taskId);
    const visited = new Set([draggedKey]);
    const queue = [draggedKey];
    const changedIds = [];
    while (queue.length) {
      const currentId = queue.shift();
      fixedLinks.forEach(function (link) {
        const sourceId = String(link.source);
        const targetId = String(link.target);
        let neighborId = null;
        if (sourceId === currentId) {
          neighborId = targetId;
        } else if (targetId === currentId) {
          neighborId = sourceId;
        } else {
          return;
        }
        if (visited.has(neighborId)) return;
        visited.add(neighborId);
        let neighborTask = null;
        try { neighborTask = gantt.getTask(neighborId); } catch (_) { neighborTask = null; }
        if (!neighborTask) return;
        if (isTypicalServiceTermGanttSummaryTask(gantt, neighborTask)) {
          queue.push(neighborId);
          return;
        }
        if (getTypicalServiceTermGanttFixedMilestoneDate(gantt, neighborTask)) {
          return;
        }
        // Capture the original working-day duration BEFORE shifting dates. Shifting
        // by calendar days alone can change the working-day count when the new
        // [start, end) window covers a different number of weekends/holidays — and
        // the subsequent auto-scheduling pass would then read this corrupted
        // duration via gantt.calculateDuration() and force-shrink downstream tasks
        // (sometimes all the way to 0). Recomputing end_date from the original
        // working duration keeps calculateDuration(new_start, new_end) stable.
        const isMilestoneNeighbor = neighborTask.type === gantt?.config?.types?.milestone;
        const originalWorkingDuration = isMilestoneNeighbor
          ? 0
          : getTypicalServiceTermGanttTaskDuration(gantt, neighborTask);
        if (neighborTask.start_date instanceof Date) {
          neighborTask.start_date = addPolicyGanttDays(neighborTask.start_date, deltaDays);
        }
        if (isMilestoneNeighbor) {
          if (neighborTask.start_date instanceof Date) {
            neighborTask.end_date = new Date(neighborTask.start_date);
          }
          neighborTask.duration = 0;
        } else if (neighborTask.start_date instanceof Date) {
          const recomputedEnd = calculateTypicalServiceTermGanttEndDate(
            gantt,
            neighborTask.start_date,
            originalWorkingDuration,
            neighborTask
          );
          if (recomputedEnd instanceof Date && !Number.isNaN(recomputedEnd.getTime())) {
            neighborTask.end_date = recomputedEnd;
          } else if (neighborTask.end_date instanceof Date) {
            neighborTask.end_date = addPolicyGanttDays(neighborTask.end_date, deltaDays);
          }
          neighborTask.duration = originalWorkingDuration;
        } else if (neighborTask.end_date instanceof Date) {
          neighborTask.end_date = addPolicyGanttDays(neighborTask.end_date, deltaDays);
        }
        changedIds.push(neighborId);
        queue.push(neighborId);
      });
    }
    if (!changedIds.length) return false;
    const apply = function () {
      changedIds.forEach(function (id) {
        if (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(id)) return;
        if (typeof gantt.updateTask === 'function') gantt.updateTask(id);
      });
    };
    const wasSchedulingActive = gantt.$policyTypicalServiceTermSchedulingActive;
    gantt.$policyTypicalServiceTermSchedulingActive = true;
    try {
      if (typeof gantt.batchUpdate === 'function') {
        gantt.batchUpdate(apply);
      } else {
        apply();
      }
    } finally {
      gantt.$policyTypicalServiceTermSchedulingActive = wasSchedulingActive;
    }
    if (typeof applyTypicalServiceTermGanttParentRollup === 'function') {
      applyTypicalServiceTermGanttParentRollup(gantt);
    }
    return true;
  }

  function applyTypicalServiceTermGanttPostLightboxReschedule(gantt) {
    if (!gantt) return;
    const pendingId = gantt.$policyTypicalServiceTermPendingLinkReschedule;
    if (!pendingId) return;
    delete gantt.$policyTypicalServiceTermPendingLinkReschedule;
    const reschedule = function () {
      if (typeof applyTypicalServiceTermGanttParentRollup === 'function') applyTypicalServiceTermGanttParentRollup(gantt);
      if (typeof applyTypicalServiceTermGanttConstraints === 'function') applyTypicalServiceTermGanttConstraints(gantt);
      if (typeof applyTypicalServiceTermGanttAutoScheduling === 'function') applyTypicalServiceTermGanttAutoScheduling(gantt, {});
      if (typeof applyTypicalServiceTermGanttAlapScheduling === 'function') applyTypicalServiceTermGanttAlapScheduling(gantt);
      if (typeof applyTypicalServiceTermGanttConstraints === 'function') applyTypicalServiceTermGanttConstraints(gantt);
      if (typeof applyTypicalServiceTermGanttParentRollup === 'function') applyTypicalServiceTermGanttParentRollup(gantt);
    };
    const wasSchedulingActive = gantt.$policyTypicalServiceTermSchedulingActive;
    gantt.$policyTypicalServiceTermSchedulingActive = false;
    try {
      if (typeof gantt.batchUpdate === 'function') {
        gantt.batchUpdate(reschedule);
      } else {
        reschedule();
      }
    } finally {
      gantt.$policyTypicalServiceTermSchedulingActive = wasSchedulingActive;
    }
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
      policyGanttAttachEvent('onRowDragStart', function (id, target, event) {
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
      policyGanttAttachEvent('onRowDragMove', function (id, parent) {
        state.draggedId = id;
        state.targetParent = parent;
        return true;
      });
      policyGanttAttachEvent('onRowDragEnd', function () {
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
    // Visible diamond is a 12×12 square rotated 45° (see `.typical-service-term-gantt-milestone
    // .gantt_task_content` in site.css), so its visible half-width on the timeline axis is
    // `6 * sqrt(2) ≈ 8.485`. Anything smaller leaves a visible gap between the diamond's
    // edge and the start/end of the dependency line because dhtmlxGantt renders link lines
    // on a layer above the task bars (so the line is *not* hidden by the diamond — we need
    // it to land exactly on the visible edge, not inside).
    const DIAMOND_HALF = 6 * Math.SQRT2;
    const arrowSize = (gantt.config && gantt.config.link_arrow_size) || 12;
    // The visible inner line sits inside its wrapper offset by `(wrapper_size - line_size)/2`
    // (DhtmlxGantt's `get_line_sizes` applies a margin-left of that amount). We need to
    // account for that offset when re-aligning the wrapper so the visible line — not the
    // wrapper — lands exactly on the diamond's edge.
    const linkLineWidth = (gantt.config && gantt.config.link_line_width) || 2;
    const linkWrapperWidth = (gantt.config && gantt.config.link_wrapper_width) || 20;
    const innerOffset = Math.max(0, (linkWrapperWidth - linkLineWidth) / 2);
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
        // Видимый «носик» иконки-стрелки сдвинут на ~2px внутрь относительно края
        // её бокса (dhtmlx ставит box так, чтобы box.right = endpoint + 2, и носик
        // попадает на endpoint, т.е. tipOffset = 2). Учитываем это, чтобы носик
        // попадал точно на грань видимого ромба, а не на край прямоугольного бокса.
        const arrowTipOffset = 2;
        let desiredLeft = currentLeft;
        if (isArrowRight) {
          // Хотим: visible_tip = box.right - tipOffset = tgtEdge
          // ⇒ box.right = tgtEdge + tipOffset
          // ⇒ box.left = tgtEdge + tipOffset - arrowSize
          desiredLeft = tgtEdge - arrowSize + arrowTipOffset;
        } else if (isArrowLeft) {
          // Хотим: visible_tip = box.left + tipOffset = tgtEdge
          // ⇒ box.left = tgtEdge - tipOffset
          desiredLeft = tgtEdge - arrowTipOffset;
          if (arrow.dataset.policyMilestoneTopAdjusted !== '1') {
            // dhtmlx для direction=left делает arrowY -= 1 — компенсируем,
            // чтобы вертикальный центр иконки совпадал с линией связи
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
            // Anchor the visible inner line's left edge exactly on the diamond's right
            // edge: visibleLeft = wrapperLeft + innerOffset, so wrapperLeft must be
            // `srcEdge - innerOffset`. Width shrinks by the same delta so the line's
            // right end (which connects to the rest of the path) stays put. Always run
            // — without it the line either has a visible gap (when DhtmlxGantt anchors
            // outside the diamond) or appears to start from the diamond's center (when
            // DhtmlxGantt anchors inside, since link lines render on top of bars).
            const desiredWrapperLeft = srcEdge - innerOffset;
            const dx = desiredWrapperLeft - wrapperLeft;
            if (Math.abs(dx) >= 0.5) {
              const newWidth = Math.max(0, wrapperWidth - dx);
              sourceWrapper.style.left = desiredWrapperLeft + 'px';
              sourceWrapper.style.width = newWidth + 'px';
              if (inner) inner.style.width = Math.max(0, innerWidth - dx) + 'px';
            }
          } else {
            // Mirror for backward links: anchor the visible inner line's right edge on
            // the diamond's left edge. The wrapper's left stays put; width changes so
            // its right end (which equals the visible line's right end + innerOffset)
            // lands at `srcEdge + innerOffset`.
            const desiredWrapperRight = srcEdge + innerOffset;
            const dx = desiredWrapperRight - (wrapperLeft + wrapperWidth);
            if (Math.abs(dx) >= 0.5) {
              const newWidth = Math.max(0, wrapperWidth + dx);
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
      policyGanttAttachEvent('onDataRender', apply);
      policyGanttAttachEvent('onGanttScroll', apply);
      policyGanttAttachEvent('onAfterTaskUpdate', apply);
      policyGanttAttachEvent('onAfterLinkAdd', apply);
      policyGanttAttachEvent('onAfterLinkUpdate', apply);
      policyGanttAttachEvent('onAfterLinkDelete', apply);
      policyGanttAttachEvent('onTaskDrag', apply);
      policyGanttAttachEvent('onAfterTaskDrag', apply);
      policyGanttAttachEvent('onAfterTaskMove', apply);
      policyGanttAttachEvent('onRowDragEnd', apply);
    }
  }

  function renderTypicalServiceTermGanttTimeMarkers(gantt, chart) {
    if (!gantt || !chart || typeof gantt.eachTask !== 'function') return;
    // GanttEngine.dispose() in gantt-engine.js calls clearAll() before swapping
    // render/setSizes for no-ops. Many code paths in this file schedule the
    // marker renderer via requestAnimationFrame after a render/scheduling pass —
    // those frames can fire AFTER an htmx swap has disposed the instance. The
    // captured `gantt` reference is then a husk: `eachTask` is still a function,
    // but its internal tasksStore tree has been cleared and DHTMLX's getChildren
    // dereferences a now-null branch (`Cannot read properties of null (reading '0')`).
    // Bail out explicitly on disposed/empty stores instead of letting the
    // exception bubble up and break subsequent renders.
    if (gantt.$gantt_engine_disposed) return;
    const tasksStore = gantt.$data && gantt.$data.tasksStore;
    if (!tasksStore || tasksStore.exists === undefined) return;
    const layer = gantt.$task_deadlines || gantt.$task_data;
    if (!layer) return;
    layer.querySelectorAll('.typical-service-term-gantt-deadline-marker, .typical-service-term-gantt-constraint-marker').forEach(function (node) {
      node.remove();
    });
    if (typeof gantt.posFromDate !== 'function' || typeof gantt.getTaskTop !== 'function') return;

    try {
      gantt.eachTask(function (task) {
      const deadline = parsePolicyGanttDate(task.deadline);
      const constraintDate = parsePolicyGanttDate(task.constraint_date);
      const constraintType = normalizeTypicalServiceTermGanttConstraintType(task.constraint_type);
      let top;
      try {
        top = gantt.getTaskTop(task.id);
      } catch (_) {
        return;
      }
      if (!Number.isFinite(top)) return;
      let barTop = top;
      let barHeight = Number(gantt.config?.bar_height) || 20;
      try {
        const taskPosition = typeof gantt.getTaskPosition === 'function' ? gantt.getTaskPosition(task) : null;
        if (Number.isFinite(taskPosition?.top)) barTop = taskPosition.top;
        if (Number.isFinite(taskPosition?.height)) barHeight = taskPosition.height;
      } catch (_) {
        barTop = top;
      }
      try {
        const taskNode = typeof gantt.getTaskNode === 'function' ? gantt.getTaskNode(task.id) : null;
        if (taskNode && Number.isFinite(taskNode.offsetTop)) barTop = taskNode.offsetTop;
        if (taskNode && Number.isFinite(taskNode.offsetHeight) && taskNode.offsetHeight > 0) barHeight = taskNode.offsetHeight;
      } catch (_) {
        // Fall back to DHTMLX coordinates when the task node has not been mounted yet.
      }

      if (constraintDate && constraintType) {
        let constraintLeft;
        try {
          constraintLeft = gantt.posFromDate(constraintDate);
        } catch (_) {
          constraintLeft = NaN;
        }
        if (Number.isFinite(constraintLeft)) {
          const option = getTypicalServiceTermGanttConstraintOption(constraintType);
          const marker = document.createElement('div');
          const startConstraint = constraintType === 'snet' || constraintType === 'snlt' || constraintType === 'mso';
          marker.className = 'typical-service-term-gantt-constraint-marker ' +
            (startConstraint
              ? 'typical-service-term-gantt-constraint-marker--start'
              : 'typical-service-term-gantt-constraint-marker--finish');
          marker.style.left = Math.round(constraintLeft) + 'px';
          marker.style.top = Math.round(barTop + (barHeight / 2) - 6) + 'px';
          marker.title = 'Ограничение: ' + option.code + ' ' + formatTypicalServiceTermGanttShortDate(constraintDate);
          marker.setAttribute('aria-hidden', 'true');
          layer.appendChild(marker);
        }
      }

      if (deadline) {
        let deadlineLeft;
        try {
          deadlineLeft = gantt.posFromDate(deadline);
        } catch (_) {
          deadlineLeft = NaN;
        }
        if (Number.isFinite(deadlineLeft)) {
          const marker = document.createElement('div');
          marker.className = 'typical-service-term-gantt-deadline-marker' +
            (isTypicalServiceTermGanttDeadlineMissed(task) ? ' typical-service-term-gantt-deadline-marker--missed' : '');
          marker.dataset.taskId = String(task.id);
          marker.setAttribute('data-task-id', String(task.id));
          marker.style.left = Math.round(deadlineLeft) + 'px';
          marker.style.top = Math.round(Math.max(0, barTop - 3.5)) + 'px';
          marker.title = 'Дедлайн: ' + formatTypicalServiceTermGanttShortDate(deadline);
          marker.setAttribute('aria-hidden', 'true');
          marker.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="9" viewBox="0 0 12 9" fill="none" aria-hidden="true">' +
            '<path d="M5.58397 1.52543C5.78189 1.22856 6.21811 1.22856 6.41602 1.52543L10.5475 7.72265C10.769 8.05493 10.5308 8.5 10.1315 8.5L1.86852 8.5C1.46917 8.5 1.23097 8.05493 1.45249 7.72265L5.58397 1.52543Z" fill="var(--dhx-gantt-progress-handle-background)" stroke="var(--dhx-gantt-progress-handle-border)"/>' +
            '</svg>';
          layer.appendChild(marker);
        }
      }
      });
    } catch (_) {
      // Defence-in-depth: even with the disposal/store guards above, DHTMLX can
      // throw from inside eachTask when the chart DOM is mid-teardown
      // (e.g. between clearAll and the next render). Swallowing the error here
      // keeps the rAF chain from breaking subsequent renders of the live chart.
      return;
    }
    syncTypicalServiceTermGanttDeadlineMarkerState(chart);
    renderTypicalServiceTermGanttProjectBoundaryMarkers(gantt, chart);
    refreshTypicalServiceTermGanttNonWorkingShading(gantt, chart);
  }

  function renderTypicalServiceTermGanttProjectBoundaryMarkers(gantt, chart) {
    if (!gantt || !chart || typeof gantt.posFromDate !== 'function') return;
    const layer = gantt.$task_bg || chart.querySelector('.gantt_task_bg');
    if (!layer) return;
    layer.querySelectorAll('.typical-service-term-gantt-project-boundary-line').forEach(function (node) {
      node.remove();
    });
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const boundaries = [
      { type: 'start', date: parsePolicyGanttDate(gantt.$policyTypicalServiceTermProjectStart), title: 'Начало проекта' },
      { type: 'end', date: parsePolicyGanttDate(gantt.$policyTypicalServiceTermProjectEnd), title: 'Конец проекта' },
      { type: 'today', date: today, title: 'Текущая дата' },
    ];
    const height = Math.max(layer.scrollHeight || 0, layer.offsetHeight || 0, chart.querySelector('.gantt_task_data')?.scrollHeight || 0);
    boundaries.forEach(function (boundary) {
      if (!boundary.date) return;
      let left;
      try {
        left = gantt.posFromDate(boundary.date);
      } catch (_) {
        left = NaN;
      }
      if (!Number.isFinite(left)) return;
      const marker = document.createElement('div');
      marker.className = 'typical-service-term-gantt-project-boundary-line typical-service-term-gantt-project-boundary-line--' + boundary.type;
      marker.style.left = Math.round(left) + 'px';
      marker.style.height = Math.max(1, Math.round(height)) + 'px';
      marker.title = boundary.title + ': ' + formatTypicalServiceTermGanttShortDate(boundary.date);
      marker.setAttribute('aria-hidden', 'true');
      layer.appendChild(marker);
    });
  }

  function bindTypicalServiceTermGanttDeadlineDrag(gantt, chart) {
    if (!gantt || !chart || chart.dataset.typicalServiceTermGanttDeadlineDragBound === '1') return;
    chart.dataset.typicalServiceTermGanttDeadlineDragBound = '1';

    const getDeadlineDateFromEvent = function (event) {
      const layer = gantt.$task_deadlines || gantt.$task_data;
      if (!layer || typeof gantt.dateFromPos !== 'function') return null;
      const layerRect = layer.getBoundingClientRect();
      const position = Math.max(0, event.clientX - layerRect.left);
      const date = gantt.dateFromPos(position);
      if (!(date instanceof Date) || Number.isNaN(date.getTime())) return null;
      return new Date(date.getFullYear(), date.getMonth(), date.getDate());
    };

    const updateMarkerPosition = function (marker, task, deadline) {
      if (!marker || !task || !(deadline instanceof Date) || Number.isNaN(deadline.getTime())) return;
      if (typeof gantt.posFromDate === 'function') {
        const left = gantt.posFromDate(deadline);
        if (Number.isFinite(left)) marker.style.left = Math.round(left) + 'px';
      }
      marker.title = 'Дедлайн: ' + formatTypicalServiceTermGanttShortDate(deadline);
      marker.classList.toggle(
        'typical-service-term-gantt-deadline-marker--missed',
        isTypicalServiceTermGanttDeadlineMissed(Object.assign({}, task, { deadline: deadline }))
      );
    };

    const updateDeadlineGridCell = function (task) {
      const columns = Array.isArray(gantt.config?.columns) ? gantt.config.columns : [];
      const deadlineColumnIndex = columns.findIndex(function (column) {
        return column?.name === 'deadline';
      });
      if (deadlineColumnIndex < 0) return;
      const escapedTaskId = escapeTypicalServiceTermGanttSelectorValue(task.id);
      const row = chart.querySelector(
        '.gantt_grid_data .gantt_row[data-task-id="' + escapedTaskId + '"], ' +
        '.gantt_grid_data .gantt_row[task_id="' + escapedTaskId + '"]'
      );
      const cell = row?.querySelector('.gantt_cell:nth-child(' + (deadlineColumnIndex + 1) + ')');
      if (cell) cell.innerHTML = formatTypicalServiceTermGanttDeadline(task);
    };

    chart.addEventListener('mousedown', function (event) {
      const marker = event.target?.closest?.('.typical-service-term-gantt-deadline-marker');
      if (!marker || !chart.contains(marker)) return;
      const taskId = marker.dataset.taskId || getTypicalServiceTermGanttDomTaskId(marker);
      if (!taskId || (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(taskId))) return;
      const task = typeof gantt.getTask === 'function' ? gantt.getTask(taskId) : null;
      if (!task) return;

      event.preventDefault();
      event.stopPropagation();
      if (typeof gantt.selectTask === 'function') gantt.selectTask(taskId);
      setTypicalServiceTermGanttActiveRow(chart, taskId);

      let lastDeadline = parsePolicyGanttDate(task.deadline);
      marker.classList.add('typical-service-term-gantt-deadline-marker--dragging');
      chart.classList.add('typical-service-term-gantt-deadline-dragging');
      document.body.classList.add('typical-service-term-gantt-deadline-dragging');

      const applyEventDate = function (moveEvent) {
        moveEvent.preventDefault();
        moveEvent.stopPropagation();
        const deadline = getDeadlineDateFromEvent(moveEvent);
        if (!deadline) return;
        lastDeadline = deadline;
        task.deadline = deadline;
        updateDeadlineGridCell(task);
        updateMarkerPosition(marker, task, deadline);
      };

      const finishDrag = function (upEvent) {
        document.removeEventListener('mousemove', applyEventDate, true);
        document.removeEventListener('mouseup', finishDrag, true);
        if (upEvent) applyEventDate(upEvent);
        marker.classList.remove('typical-service-term-gantt-deadline-marker--dragging');
        chart.classList.remove('typical-service-term-gantt-deadline-dragging');
        document.body.classList.remove('typical-service-term-gantt-deadline-dragging');
        if (lastDeadline) {
          task.deadline = lastDeadline;
          if (typeof gantt.updateTask === 'function') {
            gantt.updateTask(taskId);
          } else if (typeof gantt.refreshData === 'function') {
            gantt.refreshData();
          }
          requestAnimationFrame(function () {
            renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
            setTypicalServiceTermGanttActiveRow(chart, taskId);
          });
        }
      };

      document.addEventListener('mousemove', applyEventDate, true);
      document.addEventListener('mouseup', finishDrag, true);
    }, true);
  }

  function bindTypicalServiceTermGanttDeadlineLayer(gantt, chart) {
    if (!gantt || !chart || gantt._policyTypicalServiceTermDeadlineLayerBound) return;
    gantt._policyTypicalServiceTermDeadlineLayerBound = true;
    const apply = function () {
      requestAnimationFrame(function () {
        renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
      });
    };
    if (typeof gantt.attachEvent === 'function') {
      policyGanttAttachEvent('onDataRender', apply);
      policyGanttAttachEvent('onGanttScroll', apply);
      policyGanttAttachEvent('onAfterTaskAdd', apply);
      policyGanttAttachEvent('onAfterTaskUpdate', apply);
      policyGanttAttachEvent('onAfterTaskDelete', apply);
      policyGanttAttachEvent('onTaskDrag', apply);
      policyGanttAttachEvent('onAfterTaskDrag', apply);
      policyGanttAttachEvent('onAfterTaskMove', apply);
      policyGanttAttachEvent('onRowDragEnd', apply);
    }
  }

  function stabilizeTypicalServiceTermGanttLayout(gantt, chart) {
    if (!gantt || !chart) return;
    const refresh = function () {
      if (!document.body.contains(chart) || chart.offsetParent === null) return;
      try {
        installTypicalServiceTermGanttColumnResizeHandles(gantt, chart);
        alignTypicalServiceTermGanttLinkHandles(chart);
        alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
        renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
      } catch (_) {
        // DHTMLX may still be settling its first layout pass.
      }
    };
    requestAnimationFrame(function () {
      refresh();
      requestAnimationFrame(refresh);
    });
    [150, 500, 1200, 2500].forEach(function (delay) {
      window.setTimeout(refresh, delay);
    });
  }

  function getTypicalServiceTermGanttTaskDepth(gantt, taskId) {
    if (!gantt || !taskId || typeof gantt.getParent !== 'function') return 0;
    let depth = 0;
    let parentId = gantt.getParent(taskId);
    while (
      parentId !== undefined &&
      parentId !== null &&
      parentId !== '' &&
      parentId !== gantt.config?.root_id &&
      typeof gantt.isTaskExists === 'function' &&
      gantt.isTaskExists(parentId)
    ) {
      depth += 1;
      parentId = gantt.getParent(parentId);
    }
    return depth;
  }

  function getTypicalServiceTermGanttVisualLevel(gantt, task) {
    if (!gantt || !task) return 0;
    return Math.max(0, Math.min(7, getTypicalServiceTermGanttTaskDepth(gantt, task.id) + 1));
  }

  function calculateTypicalServiceTermGanttDuration(gantt, startDate, endDate, task) {
    if (!(startDate instanceof Date) || !(endDate instanceof Date)) return 0;
    if (task?.type === gantt?.config?.types?.milestone) return 0;
    if (typeof gantt?.calculateDuration === 'function') {
      return Math.max(0, Math.round(Number(gantt.calculateDuration({
        start_date: startDate,
        end_date: endDate,
        task: task,
      })) || 0));
    }
    return Math.max(0, Math.round((endDate.getTime() - startDate.getTime()) / 86400000));
  }

  function calculateTypicalServiceTermGanttEndDate(gantt, startDate, duration, task) {
    if (!(startDate instanceof Date)) return null;
    const safeDuration = Math.max(0, Math.round(Number(duration) || 0));
    if (typeof gantt?.calculateEndDate === 'function') {
      return gantt.calculateEndDate({ start_date: startDate, duration: safeDuration, task: task });
    }
    const endDate = new Date(startDate);
    endDate.setDate(endDate.getDate() + safeDuration);
    return endDate;
  }

  function calculateTypicalServiceTermGanttStartDate(gantt, endDate, duration, task) {
    if (!(endDate instanceof Date)) return null;
    const safeDuration = Math.max(0, Math.round(Number(duration) || 0));
    if (typeof gantt?.calculateEndDate === 'function') {
      return gantt.calculateEndDate({ start_date: endDate, duration: -safeDuration, task: task });
    }
    const startDate = new Date(endDate);
    startDate.setDate(startDate.getDate() - safeDuration);
    return startDate;
  }

  function getTypicalServiceTermGanttTaskDuration(gantt, task) {
    if (!task) return 0;
    if (task.type === gantt?.config?.types?.milestone) return 0;
    if (task.start_date instanceof Date && task.end_date instanceof Date) {
      return calculateTypicalServiceTermGanttDuration(gantt, task.start_date, task.end_date, task);
    }
    return Math.max(0, Math.round(Number(task.duration) || 0));
  }

  function rememberTypicalServiceTermGanttTimeboxBaseline(gantt, taskId) {
    if (!gantt || !taskId || !isTypicalServiceTermGanttTimeboxEnabled() || typeof gantt.getTask !== 'function') return;
    let task;
    try {
      task = gantt.getTask(taskId);
    } catch (_) {
      task = null;
    }
    if (!task || task.type === gantt.config?.types?.milestone || isTypicalServiceTermGanttSummaryTask(gantt, task)) return;
    gantt.$policyTypicalServiceTermTimeboxBaselines = gantt.$policyTypicalServiceTermTimeboxBaselines || {};
    const key = String(taskId);
    if (Number.isFinite(Number(gantt.$policyTypicalServiceTermTimeboxBaselines[key]))) return;
    gantt.$policyTypicalServiceTermTimeboxBaselines[key] = getTypicalServiceTermGanttTaskDuration(gantt, task);
  }

  function getTypicalServiceTermGanttFixedMilestoneDate(gantt, task) {
    if (!task || task.type !== gantt?.config?.types?.milestone) return null;
    const type = normalizeTypicalServiceTermGanttConstraintType(task.constraint_type);
    if (type !== 'mso' && type !== 'mfo') return null;
    return dateOnlyTypicalServiceTermGanttValue(parsePolicyGanttDate(task.constraint_date));
  }

  function isTypicalServiceTermGanttTimeboxAdjustable(task) {
    return task?.timebox_adjustable !== false;
  }

  function isTypicalServiceTermGanttFsNoLagLink(gantt, link) {
    const types = gantt?.config?.links || { finish_to_start: '0' };
    const linkType = link?.type === undefined || link?.type === null || link?.type === ''
      ? String(types.finish_to_start)
      : String(link.type);
    if (linkType !== String(types.finish_to_start)) return false;
    const lag = Number(link?.lag || 0);
    return !Number.isFinite(lag) || lag === 0;
  }

  function getTypicalServiceTermGanttSingleTimeboxChain(gantt, editedTaskId) {
    if (!gantt || !editedTaskId || typeof gantt.getTask !== 'function' || typeof gantt.getLinks !== 'function') return null;
    const links = (gantt.getLinks() || []).filter(function (link) {
      return isTypicalServiceTermGanttFsNoLagLink(gantt, link);
    });
    if (!links.length) return null;

    const incoming = {};
    const outgoing = {};
    links.forEach(function (link) {
      const source = String(link.source);
      const target = String(link.target);
      if (!source || !target) return;
      (outgoing[source] = outgoing[source] || []).push(link);
      (incoming[target] = incoming[target] || []).push(link);
    });

    const chainIds = [String(editedTaskId)];
    const seen = { [String(editedTaskId)]: true };
    let headId = String(editedTaskId);
    while ((incoming[headId] || []).length) {
      if (incoming[headId].length !== 1) return null;
      const sourceId = String(incoming[headId][0].source);
      if (seen[sourceId]) return null;
      seen[sourceId] = true;
      chainIds.unshift(sourceId);
      headId = sourceId;
    }

    let tailId = String(editedTaskId);
    while ((outgoing[tailId] || []).length) {
      if (outgoing[tailId].length !== 1) return null;
      const targetId = String(outgoing[tailId][0].target);
      if (seen[targetId]) return null;
      seen[targetId] = true;
      chainIds.push(targetId);
      tailId = targetId;
      let tailTask;
      try {
        tailTask = gantt.getTask(tailId);
      } catch (_) {
        tailTask = null;
      }
      if (getTypicalServiceTermGanttFixedMilestoneDate(gantt, tailTask)) break;
    }

    const tasks = [];
    for (let index = 0; index < chainIds.length; index += 1) {
      let task;
      try {
        task = gantt.getTask(chainIds[index]);
      } catch (_) {
        task = null;
      }
      if (!task || !(task.start_date instanceof Date) || !(task.end_date instanceof Date)) return null;
      tasks.push(task);
    }

    const finalTask = tasks[tasks.length - 1];
    const fixedDate = getTypicalServiceTermGanttFixedMilestoneDate(gantt, finalTask);
    if (!fixedDate || !tasks.some(function (task) { return String(task.id) === String(editedTaskId); })) return null;
    return { tasks: tasks, fixedMilestone: finalTask, fixedDate: fixedDate };
  }

  function distributeTypicalServiceTermGanttTimeboxDurations(availableDuration, tasks, getOldDuration) {
    const items = tasks.map(function (task, index) {
      const oldDuration = Math.max(0, Math.round(Number(getOldDuration(task)) || 0));
      const minDuration = 1;
      return { task: task, index: index, oldDuration: oldDuration, minDuration: minDuration };
    });
    const minTotal = items.reduce(function (total, item) { return total + item.minDuration; }, 0);
    if (availableDuration < minTotal) return null;

    let remaining = availableDuration - minTotal;
    const weightedTotal = items.reduce(function (total, item) {
      return total + Math.max(0, item.oldDuration - item.minDuration);
    }, 0);
    let allocatedTotal = minTotal;

    items.forEach(function (item) {
      const weight = weightedTotal > 0 ? Math.max(0, item.oldDuration - item.minDuration) : 1;
      const totalWeight = weightedTotal > 0 ? weightedTotal : items.length;
      const raw = totalWeight > 0 ? (remaining * weight / totalWeight) : 0;
      const extra = Math.floor(raw);
      item.duration = item.minDuration + extra;
      item.remainder = raw - extra;
      allocatedTotal += extra;
    });

    let leftover = availableDuration - allocatedTotal;
    items
      .slice()
      .sort(function (left, right) {
        if (right.remainder !== left.remainder) return right.remainder - left.remainder;
        return left.index - right.index;
      })
      .forEach(function (item) {
        if (leftover <= 0) return;
        item.duration += 1;
        leftover -= 1;
      });

    const result = {};
    items.forEach(function (item) {
      result[String(item.task.id)] = item.duration;
    });
    return result;
  }

  function applyTypicalServiceTermGanttTimeboxScheduling(gantt, editedTaskId) {
    if (!gantt || gantt.$policyTypicalServiceTermTimeboxActive || !isTypicalServiceTermGanttTimeboxEnabled()) return false;
    const baselineMap = gantt.$policyTypicalServiceTermTimeboxBaselines || {};
    const baselineKey = String(editedTaskId);
    const oldEditedDuration = baselineMap[baselineKey];
    delete baselineMap[baselineKey];
    if (!Number.isFinite(Number(oldEditedDuration))) return false;

    let editedTask;
    try {
      editedTask = typeof gantt.getTask === 'function' ? gantt.getTask(editedTaskId) : null;
    } catch (_) {
      editedTask = null;
    }
    if (!editedTask || editedTask.type === gantt.config?.types?.milestone || isTypicalServiceTermGanttSummaryTask(gantt, editedTask)) return false;

    const requestedEditedDuration = getTypicalServiceTermGanttTaskDuration(gantt, editedTask);

    const chain = getTypicalServiceTermGanttSingleTimeboxChain(gantt, editedTaskId);
    if (!chain) return false;
    const chainStart = dateOnlyTypicalServiceTermGanttValue(chain.tasks[0].start_date);
    if (!chainStart || chain.fixedDate < chainStart) return false;

    const adjustableTasks = chain.tasks.filter(function (task) {
      return task !== chain.fixedMilestone && task.type !== gantt.config?.types?.milestone;
    });
    if (!adjustableTasks.length || !adjustableTasks.some(function (task) { return String(task.id) === String(editedTaskId); })) return false;
    if (adjustableTasks.some(function (task) { return isTypicalServiceTermGanttSummaryTask(gantt, task); })) return false;

    const otherTasks = adjustableTasks.filter(function (task) {
      return String(task.id) !== String(editedTaskId);
    });
    const compressibleTasks = otherTasks.filter(isTypicalServiceTermGanttTimeboxAdjustable);
    const fixedDurationById = {};
    const fixedOtherDuration = otherTasks.reduce(function (total, task) {
      if (isTypicalServiceTermGanttTimeboxAdjustable(task)) return total;
      const duration = Math.max(1, getTypicalServiceTermGanttTaskDuration(gantt, task));
      fixedDurationById[String(task.id)] = duration;
      return total + duration;
    }, 0);

    const totalWindowDuration = calculateTypicalServiceTermGanttDuration(gantt, chainStart, chain.fixedDate, { type: gantt.config?.types?.task || 'task' });
    const minCompressibleDuration = compressibleTasks.length;
    const maxEditedDuration = totalWindowDuration - fixedOtherDuration - minCompressibleDuration;
    if (maxEditedDuration < 1) return false;
    const editedDuration = Math.max(1, Math.min(requestedEditedDuration, maxEditedDuration));
    const availableForOthers = totalWindowDuration - editedDuration - fixedOtherDuration;
    if (availableForOthers < 0) return false;
    const durationById = distributeTypicalServiceTermGanttTimeboxDurations(
      availableForOthers,
      compressibleTasks,
      function (task) { return getTypicalServiceTermGanttTaskDuration(gantt, task); }
    );
    if (!durationById) return false;
    durationById[String(editedTaskId)] = editedDuration;
    Object.keys(fixedDurationById).forEach(function (id) {
      durationById[id] = fixedDurationById[id];
    });

    const changedTaskIds = [];
    const rememberChanged = function (task, startDate, endDate, duration) {
      const changed =
        !(task.start_date instanceof Date) ||
        !(task.end_date instanceof Date) ||
        task.start_date.valueOf() !== startDate.valueOf() ||
        task.end_date.valueOf() !== endDate.valueOf() ||
        Number(task.duration || 0) !== Number(duration || 0);
      task.start_date = new Date(startDate);
      task.end_date = new Date(endDate);
      task.duration = duration;
      if (changed) changedTaskIds.push(task.id);
    };

    const apply = function () {
      let cursor = new Date(chainStart);
      chain.tasks.forEach(function (task) {
        if (task === chain.fixedMilestone) {
          rememberChanged(task, chain.fixedDate, chain.fixedDate, 0);
          cursor = new Date(chain.fixedDate);
          return;
        }
        if (task.type === gantt.config?.types?.milestone) {
          rememberChanged(task, cursor, cursor, 0);
          return;
        }
        const duration = Math.max(0, Math.round(Number(durationById[String(task.id)]) || 0));
        const nextEnd = calculateTypicalServiceTermGanttEndDate(gantt, cursor, duration, task);
        if (!(nextEnd instanceof Date)) return;
        rememberChanged(task, cursor, nextEnd, duration);
        cursor = new Date(nextEnd);
      });

      changedTaskIds.forEach(function (id) {
        if (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(id)) return;
        if (typeof gantt.updateTask === 'function') gantt.updateTask(id);
      });
    };

    gantt.$policyTypicalServiceTermTimeboxActive = true;
    try {
      if (typeof gantt.batchUpdate === 'function') {
        gantt.batchUpdate(apply);
      } else {
        apply();
      }
    } finally {
      gantt.$policyTypicalServiceTermTimeboxActive = false;
    }
    return changedTaskIds.length > 0;
  }

  function applyTypicalServiceTermGanttFixedMilestoneTimeboxes(gantt) {
    if (!gantt || !isTypicalServiceTermGanttTimeboxEnabled() || typeof gantt.getLinks !== 'function' || typeof gantt.getTask !== 'function') return false;
    const links = (gantt.getLinks() || []).filter(function (link) {
      return isTypicalServiceTermGanttFsNoLagLink(gantt, link);
    });
    if (!links.length) return false;

    const incoming = {};
    links.forEach(function (link) {
      const target = String(link?.target ?? '');
      if (!target) return;
      (incoming[target] = incoming[target] || []).push(link);
    });

    const changedTaskIds = [];
    const rememberChanged = function (id) {
      if (changedTaskIds.indexOf(id) === -1) changedTaskIds.push(id);
    };
    const canTimeboxTask = function (task) {
      return !!task
        && task.type !== gantt.config?.types?.milestone
        && !isTypicalServiceTermGanttSummaryTask(gantt, task)
        && !hasTypicalServiceTermGanttHardDateConstraint(task)
        && isTypicalServiceTermGanttTimeboxAdjustable(task)
        && task.start_date instanceof Date
        && task.end_date instanceof Date;
    };
    const setTaskWindow = function (task, startDate, endDate, duration) {
      const changed =
        !(task.start_date instanceof Date) ||
        !(task.end_date instanceof Date) ||
        task.start_date.valueOf() !== startDate.valueOf() ||
        task.end_date.valueOf() !== endDate.valueOf() ||
        Number(task.duration || 0) !== Number(duration || 0);
      task.start_date = new Date(startDate);
      task.end_date = new Date(endDate);
      task.duration = duration;
      if (changed) rememberChanged(task.id);
    };

    const applyForMilestone = function (milestone) {
      const fixedDate = getTypicalServiceTermGanttFixedMilestoneDate(gantt, milestone);
      if (!fixedDate) return false;

      const taskMap = {};
      const visit = function (taskId) {
        const sourceLinks = incoming[String(taskId)] || [];
        sourceLinks.forEach(function (link) {
          let source = null;
          try { source = gantt.getTask(link.source); } catch (_) { source = null; }
          if (!source) return;
          if (!canTimeboxTask(source)) return;
          const sourceId = String(source.id);
          if (taskMap[sourceId]) return;
          taskMap[sourceId] = source;
          visit(sourceId);
        });
      };
      visit(milestone.id);

      const tasks = Object.keys(taskMap).map(function (id) { return taskMap[id]; });
      if (!tasks.length) return false;

      const taskIds = new Set(tasks.map(function (task) { return String(task.id); }));
      const levelsById = {};
      const visiting = {};
      const levelFor = function (task) {
        const taskId = String(task.id);
        if (Number.isFinite(levelsById[taskId])) return levelsById[taskId];
        if (visiting[taskId]) return 0;
        visiting[taskId] = true;
        let level = 0;
        (incoming[taskId] || []).forEach(function (link) {
          const sourceId = String(link.source);
          if (!taskIds.has(sourceId)) return;
          const sourceTask = taskMap[sourceId];
          if (!sourceTask) return;
          level = Math.max(level, levelFor(sourceTask) + 1);
        });
        visiting[taskId] = false;
        levelsById[taskId] = level;
        return level;
      };
      tasks.forEach(levelFor);

      const roots = tasks.filter(function (task) { return levelFor(task) === 0; });
      const chainStart = roots.reduce(function (minDate, task) {
        if (!(task.start_date instanceof Date)) return minDate;
        return !minDate || task.start_date < minDate ? task.start_date : minDate;
      }, null);
      if (!chainStart || fixedDate <= chainStart) return false;

      const totalWindowDuration = calculateTypicalServiceTermGanttDuration(gantt, chainStart, fixedDate, { type: gantt.config?.types?.task || 'task' });
      const maxLevel = tasks.reduce(function (max, task) { return Math.max(max, levelFor(task)); }, 0);
      const segments = [];
      for (let level = 0; level <= maxLevel; level += 1) {
        const levelTasks = tasks.filter(function (task) { return levelFor(task) === level; });
        if (!levelTasks.length) continue;
        const oldDuration = Math.max.apply(null, levelTasks.map(function (task) {
          return Math.max(1, getTypicalServiceTermGanttTaskDuration(gantt, task));
        }));
        segments.push({
          id: 'timebox-segment-' + level,
          level: level,
          tasks: levelTasks,
          oldDuration: oldDuration,
        });
      }
      if (!segments.length || totalWindowDuration < segments.length) return false;

      const durationBySegment = distributeTypicalServiceTermGanttTimeboxDurations(
        totalWindowDuration,
        segments,
        function (segment) { return segment.oldDuration; }
      );
      if (!durationBySegment) return false;

      let cursor = new Date(chainStart);
      segments.forEach(function (segment) {
        const duration = Math.max(1, Math.round(Number(durationBySegment[String(segment.id)]) || 1));
        const nextEnd = calculateTypicalServiceTermGanttEndDate(gantt, cursor, duration, { type: gantt.config?.types?.task || 'task' });
        if (!(nextEnd instanceof Date)) return;
        segment.tasks.forEach(function (task) {
          setTaskWindow(task, cursor, nextEnd, duration);
        });
        cursor = new Date(nextEnd);
      });
      return true;
    };

    if (typeof gantt.eachTask !== 'function') return false;
    gantt.eachTask(function (task) {
      if (getTypicalServiceTermGanttFixedMilestoneDate(gantt, task)) {
        applyForMilestone(task);
      }
    });

    changedTaskIds.forEach(function (id) {
      if (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(id)) return;
      if (typeof gantt.updateTask === 'function') gantt.updateTask(id);
    });
    return changedTaskIds.length > 0;
  }

  function applyTypicalServiceTermGanttParentRollup(gantt) {
    if (!gantt || gantt.$policyTypicalServiceTermParentRollupActive || typeof gantt.eachTask !== 'function') return;
    const summaryTasks = [];
    gantt.eachTask(function (task) {
      if (typeof gantt.hasChild === 'function' && gantt.hasChild(task.id)) {
        summaryTasks.push(task);
      } else if (task.type === gantt.config?.types?.project) {
        task.type = gantt.config.types.task;
      }
    });
    if (!summaryTasks.length) return;

    gantt.$policyTypicalServiceTermParentRollupActive = true;
    const changedTaskIds = [];
    const apply = function () {
      summaryTasks
        .sort(function (left, right) {
          return getTypicalServiceTermGanttTaskDepth(gantt, right.id) - getTypicalServiceTermGanttTaskDepth(gantt, left.id);
        })
        .forEach(function (task) {
          let minStart = null;
          let maxEnd = null;
          gantt.eachTask(function (child) {
            if (child.id === task.id) return;
            if (child.start_date instanceof Date && (!minStart || child.start_date < minStart)) {
              minStart = child.start_date;
            }
            if (child.end_date instanceof Date && (!maxEnd || child.end_date > maxEnd)) {
              maxEnd = child.end_date;
            }
          }, task.id);
          if (!minStart || !maxEnd) return;

          const nextStart = new Date(minStart);
          const nextEnd = new Date(maxEnd);
          const nextDuration = calculateTypicalServiceTermGanttDuration(gantt, nextStart, nextEnd, task);
          const nextType = task.type === gantt.config?.types?.milestone
            ? task.type
            : (task.type === TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE
              ? task.type
              : (gantt.config?.types?.project || 'project'));
          const changed =
            !(task.start_date instanceof Date) ||
            !(task.end_date instanceof Date) ||
            task.start_date.valueOf() !== nextStart.valueOf() ||
            task.end_date.valueOf() !== nextEnd.valueOf() ||
            Number(task.duration || 0) !== nextDuration ||
            task.type !== nextType;
          task.start_date = nextStart;
          task.end_date = nextEnd;
          task.duration = nextDuration;
          task.type = nextType;
          if (changed) changedTaskIds.push(task.id);
        });
      changedTaskIds.forEach(function (id) {
        if (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(id)) return;
        if (typeof gantt.updateTask === 'function') gantt.updateTask(id);
      });
    };
    if (typeof gantt.batchUpdate === 'function') {
      gantt.batchUpdate(apply);
    } else {
      apply();
    }
    gantt.$policyTypicalServiceTermParentRollupActive = false;
  }

  function setTypicalServiceTermGanttTaskStart(gantt, task, nextStart) {
    if (!task || !(nextStart instanceof Date)) return false;
    const duration = getTypicalServiceTermGanttTaskDuration(gantt, task);
    const nextEnd = task.type === gantt?.config?.types?.milestone
      ? new Date(nextStart)
      : calculateTypicalServiceTermGanttEndDate(gantt, nextStart, duration, task);
    if (!(nextEnd instanceof Date)) return false;
    const changed =
      !(task.start_date instanceof Date) ||
      !(task.end_date instanceof Date) ||
      task.start_date.valueOf() !== nextStart.valueOf() ||
      task.end_date.valueOf() !== nextEnd.valueOf();
    task.start_date = new Date(nextStart);
    task.end_date = new Date(nextEnd);
    task.duration = task.type === gantt?.config?.types?.milestone ? 0 : duration;
    return changed;
  }

  function setTypicalServiceTermGanttTaskEnd(gantt, task, nextEnd) {
    if (!task || !(nextEnd instanceof Date)) return false;
    const duration = getTypicalServiceTermGanttTaskDuration(gantt, task);
    const nextStart = task.type === gantt?.config?.types?.milestone
      ? new Date(nextEnd)
      : calculateTypicalServiceTermGanttStartDate(gantt, nextEnd, duration, task);
    if (!(nextStart instanceof Date)) return false;
    const changed =
      !(task.start_date instanceof Date) ||
      !(task.end_date instanceof Date) ||
      task.start_date.valueOf() !== nextStart.valueOf() ||
      task.end_date.valueOf() !== nextEnd.valueOf();
    task.start_date = new Date(nextStart);
    task.end_date = new Date(nextEnd);
    task.duration = task.type === gantt?.config?.types?.milestone ? 0 : duration;
    return changed;
  }

  function isTypicalServiceTermGanttSummaryTask(gantt, task) {
    return !!(task && typeof gantt?.hasChild === 'function' && gantt.hasChild(task.id));
  }

  function syncTypicalServiceTermGanttParentProgress(gantt) {
    if (!gantt || typeof gantt.eachTask !== 'function' || typeof gantt.getChildren !== 'function' || typeof gantt.getTask !== 'function') return [];
    const changedTaskIds = [];
    const visited = new Set();
    const syncTask = function (task) {
      if (!task || task.id === undefined || task.id === null) return Math.max(0, Math.min(1, Number(task?.progress) || 0));
      const taskId = String(task.id);
      if (visited.has(taskId)) return Math.max(0, Math.min(1, Number(task.progress) || 0));
      visited.add(taskId);
      const childIds = gantt.getChildren(task.id) || [];
      if (!childIds.length) return Math.max(0, Math.min(1, Number(task.progress) || 0));
      const childProgressValues = childIds.map(function (childId) {
        try {
          return syncTask(gantt.getTask(childId));
        } catch (_) {
          return null;
        }
      }).filter(function (value) {
        return Number.isFinite(value);
      });
      const nextProgress = childProgressValues.length
        ? childProgressValues.reduce(function (total, value) { return total + value; }, 0) / childProgressValues.length
        : 0;
      if (Math.abs((Number(task.progress) || 0) - nextProgress) > 0.0001) {
        task.progress = nextProgress;
        changedTaskIds.push(task.id);
      }
      return nextProgress;
    };
    gantt.eachTask(function (task) {
      if (isTypicalServiceTermGanttSummaryTask(gantt, task)) syncTask(task);
    });
    return changedTaskIds;
  }

  function applyTypicalServiceTermGanttConstraints(gantt) {
    if (!gantt || typeof gantt.eachTask !== 'function') return;
    const changedTaskIds = [];
    const rememberChanged = function (taskId) {
      if (changedTaskIds.indexOf(taskId) === -1) changedTaskIds.push(taskId);
    };

    gantt.eachTask(function (task) {
      if (!task || isTypicalServiceTermGanttSummaryTask(gantt, task)) return;
      const type = normalizeTypicalServiceTermGanttConstraintType(task.constraint_type);
      const constraintDate = parsePolicyGanttDate(task.constraint_date);
      if (!type || type === 'asap' || type === 'alap' || !constraintDate) return;
      if (!(task.start_date instanceof Date) || !(task.end_date instanceof Date)) return;

      let changed = false;
      if ((type === 'snet' || type === 'mso') && task.start_date.valueOf() !== constraintDate.valueOf()) {
        if (type === 'mso' || task.start_date < constraintDate) {
          changed = setTypicalServiceTermGanttTaskStart(gantt, task, constraintDate);
        }
      } else if (type === 'snlt' && task.start_date > constraintDate) {
        changed = setTypicalServiceTermGanttTaskStart(gantt, task, constraintDate);
      } else if ((type === 'fnet' || type === 'mfo') && task.end_date.valueOf() !== constraintDate.valueOf()) {
        if (type === 'mfo' || task.end_date < constraintDate) {
          changed = setTypicalServiceTermGanttTaskEnd(gantt, task, constraintDate);
        }
      } else if (type === 'fnlt' && task.end_date > constraintDate) {
        changed = setTypicalServiceTermGanttTaskEnd(gantt, task, constraintDate);
      }

      if (changed) rememberChanged(task.id);
    });

    changedTaskIds.forEach(function (id) {
      if (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(id)) return;
      if (typeof gantt.updateTask === 'function') gantt.updateTask(id);
    });
  }

  function applyTypicalServiceTermGanttAlapScheduling(gantt) {
    if (!gantt || typeof gantt.getLinks !== 'function' || typeof gantt.getTask !== 'function') return;
    const links = gantt.getLinks();
    if (!Array.isArray(links) || !links.length) return;
    const types = gantt.config?.links || { finish_to_start: '0', start_to_start: '1', finish_to_finish: '2', start_to_finish: '3' };
    const changedTaskIds = [];
    const maxPasses = Math.max(links.length + 1, 2);

    const rememberChanged = function (taskId) {
      if (changedTaskIds.indexOf(taskId) === -1) changedTaskIds.push(taskId);
    };
    const earlierDate = function (left, right) {
      if (!(left instanceof Date)) return right instanceof Date ? right : null;
      if (!(right instanceof Date)) return left;
      return left < right ? left : right;
    };

    for (let pass = 0; pass < maxPasses; pass += 1) {
      let changedInPass = false;
      gantt.eachTask(function (task) {
        if (!task || normalizeTypicalServiceTermGanttConstraintType(task.constraint_type) !== 'alap') return;
        if (isTypicalServiceTermGanttSummaryTask(gantt, task)) return;
        if (!(task.start_date instanceof Date) || !(task.end_date instanceof Date)) return;

        let latestStartBound = null;
        let latestEndBound = parsePolicyGanttDate(gantt.$policyTypicalServiceTermProjectEnd);
        links.forEach(function (link) {
          if (String(link.source) !== String(task.id)) return;
          if (normalizeTypicalServiceTermGanttLagMode(link.lag_mode) !== 'fixed') return;
          let successor;
          try {
            successor = gantt.getTask(link.target);
          } catch (_) {
            successor = null;
          }
          if (!successor || !(successor.start_date instanceof Date) || !(successor.end_date instanceof Date)) return;
          const linkType = String(link.type);
          const lag = normalizeTypicalServiceTermGanttLag(link.lag);
          if (linkType === String(types.start_to_start)) {
            latestStartBound = earlierDate(latestStartBound, addPolicyGanttDays(successor.start_date, -lag));
          } else if (linkType === String(types.finish_to_finish)) {
            latestEndBound = earlierDate(latestEndBound, addPolicyGanttDays(successor.end_date, -lag));
          } else if (linkType === String(types.start_to_finish)) {
            latestStartBound = earlierDate(latestStartBound, addPolicyGanttDays(successor.end_date, -lag));
          } else {
            latestEndBound = earlierDate(latestEndBound, addPolicyGanttDays(successor.start_date, -lag));
          }
        });

        if (!latestStartBound && !latestEndBound) return;
        const duration = getTypicalServiceTermGanttTaskDuration(gantt, task);
        let latestStart = latestStartBound ? new Date(latestStartBound) : null;
        if (latestEndBound) {
          const startFromEndBound = task.type === gantt?.config?.types?.milestone
            ? new Date(latestEndBound)
            : calculateTypicalServiceTermGanttStartDate(gantt, latestEndBound, duration, task);
          latestStart = earlierDate(latestStart, startFromEndBound);
        }
        if (!(latestStart instanceof Date) || Number.isNaN(latestStart.getTime())) return;

        const changed = setTypicalServiceTermGanttTaskStart(gantt, task, latestStart);
        if (changed) {
          changedInPass = true;
          rememberChanged(task.id);
        }
      });

      if (!changedInPass) break;
      applyTypicalServiceTermGanttParentRollup(gantt);
    }

    changedTaskIds.forEach(function (id) {
      if (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(id)) return;
      if (typeof gantt.updateTask === 'function') gantt.updateTask(id);
    });
  }

  function applyTypicalServiceTermGanttAutoScheduling(gantt, options) {
    if (!gantt || typeof gantt.getLinks !== 'function' || typeof gantt.getTask !== 'function') return;
    const links = gantt.getLinks();
    if (!Array.isArray(links) || !links.length) return;
    const types = gantt.config?.links || { finish_to_start: '0', start_to_start: '1', finish_to_finish: '2', start_to_finish: '3' };
    const skipIncomingTargetId = options?.skipIncomingTargetId !== undefined && options?.skipIncomingTargetId !== null
      ? String(options.skipIncomingTargetId)
      : '';
    const changedTaskIds = [];
    const maxPasses = Math.max(links.length + 1, 2);

    const rememberChanged = function (taskId) {
      if (changedTaskIds.indexOf(taskId) === -1) changedTaskIds.push(taskId);
    };

    for (let pass = 0; pass < maxPasses; pass += 1) {
      let changedInPass = false;
      links.forEach(function (link) {
        if (normalizeTypicalServiceTermGanttLagMode(link.lag_mode) !== 'fixed') return;
        let source;
        let target;
        try {
          source = gantt.getTask(link.source);
          target = gantt.getTask(link.target);
        } catch (_) {
          return;
        }
        if (!source || !target || isTypicalServiceTermGanttSummaryTask(gantt, target)) return;
        if (skipIncomingTargetId && String(target.id) === skipIncomingTargetId) return;
        if (getTypicalServiceTermGanttFixedMilestoneDate(gantt, target)) return;
        if (!(source.start_date instanceof Date) || !(source.end_date instanceof Date)) return;
        if (!(target.start_date instanceof Date) || !(target.end_date instanceof Date)) return;

        const linkType = String(link.type);
        const lag = normalizeTypicalServiceTermGanttLag(link.lag);
        let changed = false;
        if (linkType === String(types.start_to_start)) {
          const bound = addPolicyGanttDays(source.start_date, lag);
          if (target.start_date.valueOf() !== bound.valueOf()) {
            changed = setTypicalServiceTermGanttTaskStart(gantt, target, bound);
          }
        } else if (linkType === String(types.finish_to_finish)) {
          const bound = addPolicyGanttDays(source.end_date, lag);
          if (target.end_date.valueOf() !== bound.valueOf()) {
            changed = setTypicalServiceTermGanttTaskEnd(gantt, target, bound);
          }
        } else if (linkType === String(types.start_to_finish)) {
          const bound = addPolicyGanttDays(source.start_date, lag);
          if (target.end_date.valueOf() !== bound.valueOf()) {
            changed = setTypicalServiceTermGanttTaskEnd(gantt, target, bound);
          }
        } else {
          const bound = addPolicyGanttDays(source.end_date, lag);
          if (target.start_date.valueOf() !== bound.valueOf()) {
            changed = setTypicalServiceTermGanttTaskStart(gantt, target, bound);
          }
        }

        if (changed) {
          changedInPass = true;
          rememberChanged(target.id);
        }
      });

      if (!changedInPass) break;
      applyTypicalServiceTermGanttParentRollup(gantt);
    }

    changedTaskIds.forEach(function (id) {
      if (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(id)) return;
      if (typeof gantt.updateTask === 'function') gantt.updateTask(id);
    });
  }

  function syncTypicalServiceTermGanttScheduling(gantt, options) {
    if (!gantt || gantt.$policyTypicalServiceTermSchedulingActive || gantt.$policyTypicalServiceTermTimeboxActive) return;
    gantt.$policyTypicalServiceTermSchedulingActive = true;
    try {
      const apply = function () {
        applyTypicalServiceTermGanttParentRollup(gantt);
        applyTypicalServiceTermGanttConstraints(gantt);
        applyTypicalServiceTermGanttFixedMilestoneTimeboxes(gantt);
        applyTypicalServiceTermGanttAutoScheduling(gantt, options || {});
        applyTypicalServiceTermGanttAlapScheduling(gantt);
        applyTypicalServiceTermGanttConstraints(gantt);
        applyTypicalServiceTermGanttParentRollup(gantt);
      };
      if (typeof gantt.batchUpdate === 'function') {
        gantt.batchUpdate(apply);
      } else {
        apply();
      }
    } finally {
      gantt.$policyTypicalServiceTermSchedulingActive = false;
    }
  }

  function bindTypicalServiceTermGanttParentRollup(gantt) {
    if (!gantt || gantt.$policyTypicalServiceTermParentRollupBound || typeof gantt.attachEvent !== 'function') return;
    gantt.$policyTypicalServiceTermParentRollupBound = true;
    const apply = function (options) {
      syncTypicalServiceTermGanttScheduling(gantt, options || {});
      applyTypicalServiceTermGanttProjectBounds(gantt);
      return true;
    };
    policyGanttAttachEvent('onParse', apply);
    policyGanttAttachEvent('onAfterTaskAdd', apply);
    policyGanttAttachEvent('onAfterTaskUpdate', function (id) {
      return apply({ skipIncomingTargetId: id });
    });
    policyGanttAttachEvent('onBeforeTaskDrag', function (id, mode) {
      const moveMode = gantt.config?.drag_mode?.move || 'move';
      if (String(mode) === String(moveMode)) {
        rememberTypicalServiceTermGanttFixedDragBaseline(gantt, id);
      } else {
        delete gantt.$policyTypicalServiceTermDragBaseline;
      }
      return true;
    });
    policyGanttAttachEvent('onAfterTaskDrag', function (id, mode) {
      const moveMode = gantt.config?.drag_mode?.move || 'move';
      if (String(mode) === String(moveMode)) {
        applyTypicalServiceTermGanttRigidDragShift(gantt, id);
        return apply({ skipIncomingTargetId: id });
      }
      delete gantt.$policyTypicalServiceTermDragBaseline;
      return apply();
    });
    policyGanttAttachEvent('onAfterTaskMove', function (id) {
      return apply({ skipIncomingTargetId: id });
    });
    policyGanttAttachEvent('onRowDragEnd', function (id) {
      return apply({ skipIncomingTargetId: id });
    });
    policyGanttAttachEvent('onAfterTaskDelete', apply);
    policyGanttAttachEvent('onAfterLinkAdd', function (id, link) {
      let stored = null;
      try { stored = typeof gantt.getLink === 'function' ? gantt.getLink(id) : null; } catch (_) { stored = null; }
      const targets = [link, stored].filter(function (item) { return item && typeof item === 'object'; });
      targets.forEach(function (item) {
        if (item.lag === undefined || item.lag === null || item.lag === '') item.lag = 0;
        if (!item.lag_mode) item.lag_mode = 'fixed';
      });
      applyTypicalServiceTermGanttSnapNewLink(gantt, stored || link);
      const result = apply();
      if (typeof requestAnimationFrame === 'function') {
        requestAnimationFrame(function () { apply(); });
      }
      return result;
    });
    policyGanttAttachEvent('onAfterLinkUpdate', apply);
    policyGanttAttachEvent('onAfterLinkDelete', apply);
  }

  function bindTypicalServiceTermGanttTimeboxScheduling(gantt) {
    if (!gantt || gantt.$policyTypicalServiceTermTimeboxBound || typeof gantt.attachEvent !== 'function') return;
    gantt.$policyTypicalServiceTermTimeboxBound = true;
    policyGanttAttachEvent('onBeforeLightbox', function (id) {
      rememberTypicalServiceTermGanttTimeboxBaseline(gantt, id);
      return true;
    });
    policyGanttAttachEvent('onBeforeTaskDrag', function (id) {
      rememberTypicalServiceTermGanttTimeboxBaseline(gantt, id);
      return true;
    });
    policyGanttAttachEvent('onAfterTaskDrag', function (id) {
      applyTypicalServiceTermGanttTimeboxScheduling(gantt, id);
      return true;
    });
    policyGanttAttachEvent('onAfterTaskUpdate', function (id) {
      applyTypicalServiceTermGanttTimeboxScheduling(gantt, id);
      return true;
    });
  }

  function applyTypicalServiceTermGanttNewTaskDefaults(gantt, task) {
    const projectStart = parsePolicyGanttDate(gantt?.$policyTypicalServiceTermProjectStart);
    if (!task || !projectStart) return;
    task.start_date = new Date(projectStart);
    if (task.type === gantt?.config?.types?.milestone) {
      task.duration = 0;
      task.end_date = new Date(projectStart);
      return;
    }
    const duration = Math.max(1, Math.round(Number(task.duration) || 1));
    task.duration = duration;
    const nextEnd = calculateTypicalServiceTermGanttEndDate(gantt, projectStart, duration, task);
    task.end_date = nextEnd instanceof Date ? nextEnd : addPolicyGanttDays(projectStart, duration);
  }

  function bindTypicalServiceTermGanttNewTaskDefaults(gantt) {
    if (!gantt || gantt.$policyTypicalServiceTermNewTaskDefaultsBound || typeof gantt.attachEvent !== 'function') return;
    gantt.$policyTypicalServiceTermNewTaskDefaultsBound = true;
    policyGanttAttachEvent('onTaskCreated', function (task) {
      applyTypicalServiceTermGanttNewTaskDefaults(gantt, task);
      return true;
    });
    policyGanttAttachEvent('onBeforeTaskAdd', function (id, task) {
      applyTypicalServiceTermGanttNewTaskDefaults(gantt, task);
      return true;
    });
  }

  function configureTypicalServiceTermGantt(root) {
    const gantt = getTypicalServiceTermGanttInstance();
    if (!gantt) return null;
    ensureTypicalServiceTermGanttTaskNameBlock(gantt);
    ensureTypicalServiceTermGanttAssignmentBlock(gantt);
    ensureTypicalServiceTermGanttPeriodBlock(gantt);
    ensureTypicalServiceTermGanttLinksBlock(gantt);
    const scale = getTypicalServiceTermGanttScale(root);
    syncTypicalServiceTermGanttScaleButtons(root, scale);
    const editor = root?.querySelector('#typical-service-term-gantt-editor');
    const meta = editor?._typicalServiceTermGanttMeta || {};

    gantt.config.readonly = false;
    gantt.config.date_format = '%Y-%m-%d';
    // The visible range is managed explicitly to keep project/task padding stable.
    gantt.config.fit_tasks = false;
    gantt.config.autosize = 'y';
    gantt.config.container_resize_timeout = 120;
    gantt.config.row_height = 34;
    gantt.config.bar_height = 20;
    // The custom resizer handle (see installTypicalServiceTermGanttColumnResizeHandles)
    // owns the divider drag, so the built-in grid_resize is left disabled to avoid two
    // overlapping handlers fighting over the grid width.
    gantt.config.grid_resize = false;
    gantt.config.keep_grid_width = false;
    // grid_elastic_columns + the patched grid view (scrollable=true,
    // _getGridWidthLimits=[0, undef]) lets the divider freely shrink the grid cell while
    // we distribute the column widths ourselves (see
    // applyTypicalServiceTermGanttColumnsForWidth) so column widths track the divider in
    // phase 1 and stay at their min in phase 2 (overflow scroll).
    gantt.config.grid_elastic_columns = true;
    // The grid and the timeline get their own horizontal scrollbars (`gridScrollHor`,
    // `scrollHor`) sitting in a shared bottom row. We position both manually via JS so
    // they align under their respective cells regardless of the divider position.
    gantt.config.layout = {
      css: 'gantt_container',
      rows: [
        {
          cols: [
            { view: 'grid', scrollX: 'gridScrollHor', scrollY: 'scrollVer' },
            { resizer: true, width: 7 },
            { view: 'timeline', scrollX: 'scrollHor', scrollY: 'scrollVer' },
            { view: 'scrollbar', id: 'scrollVer' },
          ],
        },
        {
          // dhtmlxGantt defaults scrollbars sitting inside a `cols` parent to
          // vertical; we explicitly force horizontal scroll so each one tracks
          // its linked view's X overflow. The bottom row also gets a fixed
          // height — without it, dhtmlxGantt strips the per-cell `height: 20`
          // and the bottom row stretches to fill leftover container space,
          // which is what produced the large white gap above the scrollbars.
          height: 20,
          cols: [
            { view: 'scrollbar', id: 'gridScrollHor', scroll: 'x', height: 20 },
            { view: 'scrollbar', id: 'scrollHor', scroll: 'x', height: 20 },
          ],
        },
      ],
    };
    gantt.config.drag_links = true;
    gantt.config.drag_move = true;
    gantt.config.drag_resize = true;
    gantt.config.drag_progress = true;
    // Working-days vs calendar-days mode is reflected in DHTMLX `work_time`.
    // The actual non-working dates (country-specific holidays) are pushed via
    // setWorkTime() once syncTypicalServiceTermGanttCalendarData resolves the
    // production calendar from /classifiers/pc/calendar.json.
    gantt.config.work_time = isTypicalServiceTermGanttWorkingDaysMode();
    gantt.config.correct_work_time = isTypicalServiceTermGanttWorkingDaysMode();
    gantt.config.skip_off_time = isTypicalServiceTermGanttWorkingDaysMode()
      && isTypicalServiceTermGanttHideNonWorkingDays();
    applyTypicalServiceTermGanttDragRounding(gantt, root);
    gantt.config.order_branch = 'marker';
    gantt.config.order_branch_free = true;
    // Summary and link scheduling are implemented locally for the open-source DHTMLX build.
    gantt.config.auto_types = true;
    // Keep native PRO scheduling off; syncTypicalServiceTermGanttScheduling handles links.
    // apply_constraints only lets DHTMLX include constraint dates in the visible time range.
    gantt.config.auto_scheduling = { enabled: false, apply_constraints: true };
    // Native deadlines extend the visible scale; custom renderer below keeps visuals platform-independent.
    gantt.config.deadlines = true;
    gantt.config.constraint_types = {
      ASAP: 'asap',
      ALAP: 'alap',
      SNET: 'snet',
      SNLT: 'snlt',
      FNET: 'fnet',
      FNLT: 'fnlt',
      MSO: 'mso',
      MFO: 'mfo',
    };
    gantt.config.types.service_section = TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE;
    gantt.config.select_task = true;
    gantt.config.details_on_dblclick = true;
    applyTypicalServiceTermGanttProjectBounds(gantt, meta);
    gantt.config.columns = [
      typicalServiceTermGanttColumn('wbs', 132, {
        label: '<span class="typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--wbs">№</span>',
        align: 'center',
        min_width: 60,
        max_width: 220,
        template: function (task) {
          return typicalServiceTermGanttGridValueHtml(
            getTypicalServiceTermGanttWbsCode(gantt, task),
            'typical-service-term-gantt-grid-value typical-service-term-gantt-grid-value--wbs'
          );
        },
      }),
      typicalServiceTermGanttColumn('text', 300, { label: getTypicalServiceTermGanttTaskHeaderHtml(), tree: true, align: 'left', min_width: 190 }),
      typicalServiceTermGanttColumn('start_date', 122, {
        label: 'Начало',
        align: 'center',
        min_width: 118,
        template: function (task) {
          return formatTypicalServiceTermGanttWeekdayDate(task.start_date);
        },
      }),
      typicalServiceTermGanttColumn('end_date', 122, {
        label: 'Оконч.',
        align: 'center',
        min_width: 118,
        template: function (task) {
          return formatTypicalServiceTermGanttWeekdayDate(task.end_date);
        },
      }),
      typicalServiceTermGanttColumn('specialty', 150, {
        label: 'Специальность',
        align: 'left',
        min_width: 128,
        template: formatTypicalServiceTermGanttSpecialty,
      }),
      typicalServiceTermGanttColumn('executor', 130, {
        label: 'Исполнитель',
        align: 'left',
        min_width: 110,
        template: formatTypicalServiceTermGanttExecutor,
      }),
      typicalServiceTermGanttColumn('deadline', 92, {
        label: 'Дедл.',
        align: 'center',
        min_width: 81,
        template: formatTypicalServiceTermGanttDeadline,
      }),
      typicalServiceTermGanttColumn('constraint', 116, {
        label: 'Огр.',
        align: 'center',
        min_width: 96,
        template: formatTypicalServiceTermGanttConstraint,
      }),
      typicalServiceTermGanttColumn('duration', 64, {
        label: 'Длит.',
        align: 'center',
        min_width: 54,
        template: formatTypicalServiceTermGanttDuration,
      }),
      typicalServiceTermGanttColumn('calendar_duration', 70, {
        label: 'Длит.*',
        align: 'center',
        min_width: 60,
        template: formatTypicalServiceTermGanttCalendarDuration,
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
    const savedGridWidth = P ? Number(P.get(TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY, NaN)) : NaN;
    const desiredInitial = Number.isFinite(savedGridWidth)
      ? Math.max(80, Math.min(1200, Math.round(savedGridWidth)))
      : getTypicalServiceTermGanttColumnsWidth(gantt);
    gantt.$policyTypicalServiceTermDesiredGridWidth = desiredInitial;
    // Snapshot the natural per-column widths before we start distributing for phase 1/2.
    getTypicalServiceTermGanttColumnNaturals(gantt);
    applyTypicalServiceTermGanttColumnsForWidth(gantt, desiredInitial);
    gantt.config.grid_width = desiredInitial;
    gantt.locale.labels.section_name = '';
    gantt.locale.labels.section_assignment = '';
    gantt.locale.labels.section_links = '';
    gantt.locale.labels.section_type = 'Тип';
    gantt.locale.labels.section_period = 'Начало';
    gantt.locale.labels.new_task = 'Новая задача';
    gantt.locale.labels.type_task = 'Задача';
    gantt.locale.labels.type_project = 'Родительская задача';
    gantt.locale.labels.type_milestone = 'Веха';
    gantt.locale.labels.type_service_section = 'Раздел (услуга)';
    gantt.locale.labels.gantt_save_btn = 'Сохранить';
    gantt.locale.labels.gantt_cancel_btn = 'Отмена';
    gantt.locale.labels.gantt_delete_btn = 'Удалить';
    gantt.config.lightbox.sections = [
      {
        name: 'type',
        type: 'select',
        map_to: 'type',
        options: [
          { key: gantt.config.types.task, label: 'Задача' },
          { key: gantt.config.types.project, label: 'Родительская задача' },
          { key: gantt.config.types.milestone, label: 'Веха' },
          { key: TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE, label: 'Раздел (услуга)' },
        ],
      },
      { name: 'name', height: 104, map_to: 'text', type: 'policy_task_name', focus: true },
      { name: 'assignment', height: 74, map_to: 'auto', type: 'policy_assignment' },
      {
        name: 'period',
        type: 'policy_period',
        map_to: 'auto',
      },
      { name: 'links', height: 180, map_to: 'auto', type: 'policy_links' },
    ];
    if (!gantt.$policyTypicalServiceTermLightboxEventsBound) {
      gantt.$policyTypicalServiceTermLightboxEventsBound = true;
      const resyncCollapsedColumnsAfterLightbox = function () {
        const currentChart = pane()?.querySelector('#typical-service-term-gantt');
        if (!currentChart) return;
        resyncTypicalServiceTermGanttColumnCollapseStateSoon(gantt, currentChart);
      };
      policyGanttAttachEvent('onLightboxSave', function (id, task) {
        rememberTypicalServiceTermGanttTimeboxBaseline(gantt, id);
        const lightbox = typeof gantt.getLightbox === 'function' ? gantt.getLightbox() : null;
        if (normalizeFilterValue(task?.type) === TYPICAL_SERVICE_TERM_GANTT_SERVICE_SECTION_TYPE) {
          const sectionName = normalizeFilterValue(lightbox?.querySelector('.policy-gantt-task-name-select')?.value || task?.service_section_name);
          const displayName = normalizeFilterValue(lightbox?.querySelector('.policy-gantt-task-name-text')?.value);
          if (!sectionName || getTypicalServiceTermGanttSectionOptions().indexOf(sectionName) === -1) {
            const message = 'Выберите раздел (услугу) из списка для выбранного продукта.';
            if (typeof gantt.alert === 'function') {
              gantt.alert({ text: message });
            } else {
              window.alert(message);
            }
            return false;
          }
          task.service_section_name = sectionName;
          task.text = displayName || sectionName;
        }
        if (!isTypicalServiceTermGanttManagedPerformerTask(task) && !isTypicalServiceTermGanttManagedChecklistSectionTask(task)) {
          const specialtyValue = normalizeFilterValue(lightbox?.querySelector('.policy-gantt-specialty-select')?.value);
          const executorValue = normalizeFilterValue(lightbox?.querySelector('.policy-gantt-executor-select')?.value);
          task.specialty = specialtyValue;
          task.executor = executorValue;
        }
        const startValue = lightbox?.querySelector('.policy-gantt-period-start')?.value;
        const endValue = lightbox?.querySelector('.policy-gantt-period-end')?.value;
        const progressValue = lightbox?.querySelector('.policy-gantt-period-progress')?.value;
        const timeboxAdjustActive = !!lightbox?.querySelector('.policy-gantt-period-timebox-adjust--active');
        const deadlineValue = lightbox?.querySelector('.policy-gantt-period-deadline')?.value;
        const constraintTypeValue = normalizeTypicalServiceTermGanttConstraintType(
          lightbox?.querySelector('.policy-gantt-period-constraint-type')?.value
        );
        const constraintDateValue = lightbox?.querySelector('.policy-gantt-period-constraint-date')?.value;
        const parseDate = parseTypicalServiceTermGanttDateInput;
        if (startValue) task.start_date = parseDate(startValue);
        if (endValue) task.end_date = parseDate(endValue);
        if (isTypicalServiceTermGanttSummaryTask(gantt, task)) {
          syncTypicalServiceTermGanttParentProgress(gantt);
        } else if (isTypicalServiceTermGanttManagedChecklistSectionTask(task)) {
          task.progress = Math.max(0, Math.min(1, Number(task?.progress) || 0));
        } else {
          const progressPercent = Number(String(progressValue || '').replace(',', '.'));
          task.progress = Number.isFinite(progressPercent)
            ? Math.max(0, Math.min(100, progressPercent)) / 100
            : 0;
        }
        if (timeboxAdjustActive) {
          task.timebox_adjustable = true;
        } else {
          task.timebox_adjustable = false;
        }
        if (deadlineValue) {
          task.deadline = parseDate(deadlineValue);
        } else {
          // DHTMLX merges the lightbox values back into the stored task via
          // gantt.mixin(target, source, true), which iterates over the source
          // object — `delete task.deadline` would be silently dropped because
          // the property never makes it into the iteration, leaving the previous
          // deadline on the stored task. Setting an explicit null forces mixin
          // to overwrite it, and downstream parsePolicyGanttDate(null) returns
          // null, so all rendering / serialization paths treat it as cleared.
          task.deadline = null;
        }
        if (constraintTypeValue) {
          if (gantt.$policyTypicalServiceTermClearedConstraintTaskIds) {
            delete gantt.$policyTypicalServiceTermClearedConstraintTaskIds[String(id)];
          }
          task.constraint_type = constraintTypeValue;
          if (constraintDateValue && constraintTypeValue !== 'asap' && constraintTypeValue !== 'alap') {
            task.constraint_date = parseDate(constraintDateValue);
          } else {
            task.constraint_date = null;
            delete task.constraint_date;
          }
        } else {
          gantt.$policyTypicalServiceTermClearedConstraintTaskIds = gantt.$policyTypicalServiceTermClearedConstraintTaskIds || {};
          gantt.$policyTypicalServiceTermClearedConstraintTaskIds[String(id)] = true;
          task.constraint_type = '';
          task.constraint_date = null;
          delete task.constraint_type;
          delete task.constraint_date;
        }
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
        applyTypicalServiceTermGanttLightboxLinks(gantt, lightbox, id);
        syncTypicalServiceTermGanttParentProgress(gantt);
        refreshTypicalServiceTermGanttResources(pane());
        requestAnimationFrame(function () {
          if (gantt.$policyTypicalServiceTermClearedConstraintTaskIds?.[String(id)]) {
            clearTypicalServiceTermGanttTaskConstraint(gantt, id);
            delete gantt.$policyTypicalServiceTermClearedConstraintTaskIds[String(id)];
          }
          const chart = pane()?.querySelector('#typical-service-term-gantt');
          renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
        });
        return true;
      });
      policyGanttAttachEvent('onAfterLightbox', function () {
        cleanupTypicalServiceTermGanttLightboxArtifacts();
        applyTypicalServiceTermGanttPostLightboxReschedule(gantt);
        return true;
      });
      policyGanttAttachEvent('onLightbox', function () {
        resyncCollapsedColumnsAfterLightbox();
        return true;
      });
      policyGanttAttachEvent('onTaskDblClick', function (id) {
        if (typeof gantt.showLightbox === 'function') {
          gantt.showLightbox(id);
        }
        resyncCollapsedColumnsAfterLightbox();
        return false;
      });
    }
    if (!gantt.$policyTypicalServiceTermParentProgressBound) {
      gantt.$policyTypicalServiceTermParentProgressBound = true;
      const syncParentProgress = function () {
        const changedIds = syncTypicalServiceTermGanttParentProgress(gantt);
        if (typeof gantt.refreshTask === 'function') {
          changedIds.forEach(function (taskId) {
            try { gantt.refreshTask(taskId); } catch (_) { /* task may have been removed */ }
          });
        }
        return true;
      };
      policyGanttAttachEvent('onAfterTaskUpdate', syncParentProgress);
      policyGanttAttachEvent('onAfterTaskDrag', syncParentProgress);
      policyGanttAttachEvent('onAfterTaskAdd', syncParentProgress);
      policyGanttAttachEvent('onAfterTaskDelete', syncParentProgress);
      policyGanttAttachEvent('onParse', syncParentProgress);
    }
    if (!gantt.$policyTypicalServiceTermResizeEventsBound) {
      gantt.$policyTypicalServiceTermResizeEventsBound = true;
      policyGanttAttachEvent('onGridResizeEnd', function (oldWidth, newWidth) {
        if (P && Number.isFinite(Number(newWidth))) {
          P.set(TYPICAL_SERVICE_TERM_GANTT_GRID_WIDTH_PREF_KEY, Math.round(Number(newWidth)));
        }
        return true;
      });
      policyGanttAttachEvent('onColumnResizeEnd', function () {
        saveTypicalServiceTermGanttColumns(gantt);
        return true;
      });
    }
    applyTypicalServiceTermGanttScale(gantt, scale);
    gantt.templates.task_class = function (start, end, task) {
      const classes = [];
      if (task.type === 'milestone') classes.push('typical-service-term-gantt-milestone');
      const visualLevel = getTypicalServiceTermGanttVisualLevel(gantt, task);
      if (visualLevel > 0) classes.push('typical-service-term-gantt-level-' + visualLevel);
      if (task.type === gantt.config.types.project || isTypicalServiceTermGanttSummaryTask(gantt, task)) {
        classes.push('typical-service-term-gantt-parent-bar');
      }
      if (isTypicalServiceTermGanttDeadlineMissed(task)) classes.push('typical-service-term-gantt-deadline-missed');
      return classes.join(' ');
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
      const currentScale = getTypicalServiceTermGanttScale(pane());
      const fallbackIsParent = isTypicalServiceTermGanttSummaryTask(gantt, task);
      const labelVisibility = window.GanttEngine &&
        typeof window.GanttEngine.getTaskLabelVisibility === 'function'
        ? window.GanttEngine.getTaskLabelVisibility(gantt, start, end, task, {
          scale: currentScale,
          isSummaryTask: function () { return fallbackIsParent; },
        })
        : { text: true, parentLock: fallbackIsParent };
      const text = labelVisibility.text ? escapePolicyHtml(task.text || '') : '';
      if (isTypicalServiceTermGanttSummaryTask(gantt, task)) {
        return (labelVisibility.text ? '<span class="typical-service-term-gantt-task-text">' + text + '</span>' : '') +
          (labelVisibility.parentLock ? '<i class="bi bi-lock typical-service-term-gantt-parent-lock" aria-hidden="true"></i>' : '');
      }
      if (!labelVisibility.text) return '';
      return text;
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
    bindTypicalServiceTermGanttFreeResizeDates(gantt);
    bindTypicalServiceTermGanttParentRollup(gantt);
    bindTypicalServiceTermGanttTimeboxScheduling(gantt);
    bindTypicalServiceTermGanttNewTaskDefaults(gantt);
    if (!gantt.$policyTypicalServiceTermManagedTaskGuardsBound) {
      gantt.$policyTypicalServiceTermManagedTaskGuardsBound = true;
      policyGanttAttachEvent('onBeforeTaskDelete', function (_id, task) {
        if (!isTypicalServiceTermGanttManagedTask(task)) return true;
        window.alert('Эта задача управляется таблицами «Объем услуг: активы», «Исполнители» или «Статусы запросов». Удалите или измените соответствующую строку в таблице.');
        return false;
      });
      policyGanttAttachEvent('onBeforeTaskDrag', function (id, mode) {
        const progressMode = gantt.config?.drag_mode?.progress || 'progress';
        if (String(mode) !== String(progressMode)) return true;
        let task = null;
        try { task = gantt.getTask(id); } catch (_) { task = null; }
        return !isTypicalServiceTermGanttManagedChecklistSectionTask(task);
      });
    }
    if (typeof gantt._delete_task_confirm === 'function' && !gantt._policyTypicalServiceTermTaskConfirmPatched) {
      gantt._policyTypicalServiceTermTaskConfirmPatched = true;
      gantt._delete_task_confirm = function (params) {
        gantt.confirm({
          text: 'Задача будет удалена без возможности восстановления. Вы уверены?',
          ok: 'Удалить',
          cancel: 'Отмена',
          callback: function (result) {
            if (result && params && typeof params.callback === 'function') params.callback();
          },
        });
      };
    }
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

  function normalizeTypicalServiceTermGanttMeta(meta, tasks) {
    const normalized = Object.assign({}, meta && typeof meta === 'object' ? meta : {});
    const calendarKind = getTypicalServiceTermGanttMetaCalendarKind(normalized);
    if (calendarKind) {
      normalized.calendar_kind = calendarKind;
    } else {
      delete normalized.calendar_kind;
      delete normalized.calendar_country_id;
    }
    if (calendarKind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION) {
      const countryId = Number(normalized.calendar_country_id);
      if (Number.isFinite(countryId)) {
        normalized.calendar_country_id = countryId;
      } else {
        delete normalized.calendar_country_id;
      }
    }
    const starts = [];
    const ends = [];
    (Array.isArray(tasks) ? tasks : []).forEach(function (task) {
      const start = parsePolicyGanttDate(task?.start_date);
      const end = parsePolicyGanttDate(task?.end_date);
      if (start) starts.push(start);
      if (end) ends.push(end);
    });
    const minStart = starts.length ? new Date(Math.min.apply(null, starts.map(function (date) { return date.getTime(); }))) : null;
    const maxEnd = ends.length ? new Date(Math.max.apply(null, ends.map(function (date) { return date.getTime(); }))) : null;
    const projectStart = parsePolicyGanttDate(normalized.project_start) || parsePolicyGanttDate(normalized.base_date) || minStart;
    let projectEnd = parsePolicyGanttDate(normalized.project_end) || maxEnd || projectStart;
    if (projectStart && projectEnd && projectEnd < projectStart) projectEnd = new Date(projectStart);
    if (projectStart) normalized.project_start = formatPolicyGanttDateInput(projectStart);
    if (projectEnd) normalized.project_end = formatPolicyGanttDateInput(projectEnd);
    return normalized;
  }

  function ensureTypicalServiceTermGanttResources(root, gantt) {
    const editor = root?.querySelector('#typical-service-term-gantt-editor');
    const container = root?.querySelector('#typical-service-term-gantt-resources');
    const toggleButton = root?.querySelector('#typical-service-term-gantt-resources-btn');
    if (!editor || !container || !toggleButton || !gantt) return null;
    if (!window.GanttEngine || typeof window.GanttEngine.createResources !== 'function') {
      toggleButton.disabled = true;
      toggleButton.title = 'Модуль ресурсов Ганта не загружен';
      return null;
    }
    if (editor._typicalServiceTermGanttResources) {
      try { editor._typicalServiceTermGanttResources.dispose(); } catch (_) { /* noop */ }
      editor._typicalServiceTermGanttResources = null;
    }
    toggleButton.disabled = false;
    toggleButton.title = 'Ресурсы проекта';
    toggleButton.classList.remove('active');
    toggleButton.setAttribute('aria-pressed', 'false');
    toggleButton.setAttribute('aria-expanded', 'false');
    container.classList.add('d-none');
    editor._typicalServiceTermGanttResources = window.GanttEngine.createResources({
      gantt: gantt,
      root: editor,
      toggleButton: toggleButton,
      container: container,
      meta: editor._typicalServiceTermGanttMeta || {},
      catalogs: {
        specialties: editor._typicalServiceTermGanttSpecialties || [],
        executors: editor._typicalServiceTermGanttExecutors || [],
      },
      fields: {
        specialty: 'specialty',
        executor: 'executor',
        resourceId: 'resource_id',
        resourceName: 'resource_name',
      },
      getTaskNumber: function (task, instance) {
        return getTypicalServiceTermGanttWbsCode(instance || gantt, task);
      },
      getTaskLabel: function (task) {
        return normalizeFilterValue(task?.text) || 'Новая задача';
      },
      getTaskDuration: function (task, instance) {
        return getTypicalServiceTermGanttTaskDuration(instance || gantt, task);
      },
      isAssignableTask: function (task, instance) {
        return task?.type !== instance?.config?.types?.placeholder;
      },
      isTaskDisabled: function (task, instance, context) {
        const activeGantt = instance || gantt;
        if (isTypicalServiceTermGanttSummaryTask(activeGantt, task)) return true;
        const specialty = normalizeFilterValue(context?.specialty);
        if (!specialty) return false;
        let sectionName = getTypicalServiceTermGanttTaskSectionName(task);
        let cursor = task;
        const visited = new Set();
        while (!sectionName && cursor && cursor.parent && String(cursor.parent) !== '0') {
          const parentId = String(cursor.parent);
          if (visited.has(parentId)) break;
          visited.add(parentId);
          try {
            cursor = activeGantt.getTask(parentId);
          } catch (_) {
            cursor = null;
          }
          sectionName = getTypicalServiceTermGanttTaskSectionName(cursor);
        }
        if (!sectionName) return false;
        const section = getTypicalServiceTermGanttSectionByLabel(sectionName);
        const sectionSpecialties = (section?.specialties || []).map(function (item) {
          return normalizeFilterValue(item?.label);
        }).filter(Boolean);
        return !!sectionSpecialties.length && sectionSpecialties.indexOf(specialty) === -1;
      },
      onChange: function () {
        captureTypicalServiceTermGanttData(gantt);
      },
      onToggle: function () {
        refreshTypicalServiceTermGanttResourceLayout(root);
      },
    });
    window.__policyTypicalServiceTermGanttResources = editor._typicalServiceTermGanttResources;
    return editor._typicalServiceTermGanttResources;
  }

  function refreshTypicalServiceTermGanttResources(root) {
    const editor = root?.querySelector('#typical-service-term-gantt-editor') || getTypicalServiceTermGanttCurrentEditor();
    if (!editor?._typicalServiceTermGanttResources) return;
    try { editor._typicalServiceTermGanttResources.refreshFromGantt(); } catch (_) { /* noop */ }
  }

  function refreshTypicalServiceTermGanttResourceLayout(root) {
    const currentRoot = root || pane();
    const chart = currentRoot?.querySelector('#typical-service-term-gantt');
    const gantt = getTypicalServiceTermGanttInstance();
    if (!currentRoot || !chart || !gantt) return;
    const refresh = function () {
      if (!document.body.contains(chart)) return;
      try {
        if (typeof gantt.setSizes === 'function') gantt.setSizes();
        installTypicalServiceTermGanttColumnResizeHandles(gantt, chart);
        alignTypicalServiceTermGanttLinkHandles(chart);
        alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
        renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
      } catch (_) {
        // The resource panel may be toggled while DHTMLX is still settling.
      }
    };
    requestAnimationFrame(function () {
      refresh();
      requestAnimationFrame(refresh);
    });
  }

  function getTypicalServiceTermGanttTaskDateRange(gantt, tasks) {
    const starts = [];
    const ends = [];
    const collect = function (task) {
      const start = parsePolicyGanttDate(task?.start_date);
      const end = parsePolicyGanttDate(task?.end_date);
      if (start) starts.push(start);
      if (end) ends.push(end);
    };
    if (Array.isArray(tasks)) {
      tasks.forEach(collect);
    } else if (typeof gantt?.eachTask === 'function') {
      gantt.eachTask(collect);
    }
    return {
      start: starts.length ? new Date(Math.min.apply(null, starts.map(function (date) { return date.getTime(); }))) : null,
      end: ends.length ? new Date(Math.max.apply(null, ends.map(function (date) { return date.getTime(); }))) : null,
    };
  }

  function applyTypicalServiceTermGanttProjectBounds(gantt, meta, tasks) {
    if (!gantt) return;
    const projectStart = parsePolicyGanttDate(meta?.project_start) || parsePolicyGanttDate(gantt.$policyTypicalServiceTermProjectStart);
    const projectEnd = parsePolicyGanttDate(meta?.project_end) || parsePolicyGanttDate(gantt.$policyTypicalServiceTermProjectEnd);
    const taskRange = getTypicalServiceTermGanttTaskDateRange(gantt, tasks);
    const scale = getTypicalServiceTermGanttScale(pane());
    if (projectStart) {
      gantt.$policyTypicalServiceTermProjectStart = projectStart;
    } else {
      delete gantt.$policyTypicalServiceTermProjectStart;
    }
    if (projectEnd) {
      gantt.$policyTypicalServiceTermProjectEnd = projectEnd;
    } else {
      delete gantt.$policyTypicalServiceTermProjectEnd;
    }
    if (window.GanttEngine && typeof window.GanttEngine.applyTimelineRange === 'function') {
      window.GanttEngine.applyTimelineRange(gantt, {
        scale: scale,
        taskRange: taskRange,
        projectStart: projectStart,
        projectEnd: projectEnd,
        paddingFractions: { month: 0.5, quarter: 0.125 },
        preventWholeAdjacentUnit: true,
      });
      return;
    }
    const rangeStart = taskRange.start || projectStart || null;
    const rangeEnd = taskRange.end || projectEnd || null;
    gantt.config.start_date = rangeStart || undefined;
    gantt.config.end_date = rangeEnd || undefined;
  }

  function syncTypicalServiceTermGanttProjectBoundInputs(root) {
    const editor = root?.querySelector('#typical-service-term-gantt-editor');
    if (!editor) return;
    const meta = editor._typicalServiceTermGanttMeta || {};
    const startInput = editor.querySelector('.typical-service-term-gantt-project-start');
    const endInput = editor.querySelector('.typical-service-term-gantt-project-end');
    const projectStart = parsePolicyGanttDate(meta.project_start);
    const projectEnd = parsePolicyGanttDate(meta.project_end);
    if (startInput) startInput.$policyTypicalServiceTermDatePickerDefaultDate = projectStart || projectEnd;
    if (endInput) endInput.$policyTypicalServiceTermDatePickerDefaultDate = projectEnd || projectStart;
    [startInput, endInput].forEach(bindTypicalServiceTermGanttDateInput);
    if (startInput) startInput.value = formatTypicalServiceTermGanttDateInput(projectStart);
    if (endInput) endInput.value = formatTypicalServiceTermGanttDateInput(projectEnd);
  }

  function bindTypicalServiceTermGanttProjectBounds(root) {
    const editor = root?.querySelector('#typical-service-term-gantt-editor');
    if (!editor || editor.dataset.typicalServiceTermGanttProjectBoundsBound === '1') return;
    editor.dataset.typicalServiceTermGanttProjectBoundsBound = '1';
    const apply = function () {
      const gantt = getTypicalServiceTermGanttInstance();
      const chart = root.querySelector('#typical-service-term-gantt');
      const meta = editor._typicalServiceTermGanttMeta || {};
      const startValue = editor.querySelector('.typical-service-term-gantt-project-start')?.value;
      const endValue = editor.querySelector('.typical-service-term-gantt-project-end')?.value;
      const projectStart = parseTypicalServiceTermGanttDateInput(startValue);
      let projectEnd = parseTypicalServiceTermGanttDateInput(endValue);
      if (projectStart) meta.project_start = formatPolicyGanttDateInput(projectStart);
      if (projectEnd && projectStart && projectEnd < projectStart) projectEnd = new Date(projectStart);
      if (projectEnd) meta.project_end = formatPolicyGanttDateInput(projectEnd);
      editor._typicalServiceTermGanttMeta = meta;
      syncTypicalServiceTermGanttProjectBoundInputs(root);
      if (!gantt) return;
      syncTypicalServiceTermGanttScheduling(gantt);
      applyTypicalServiceTermGanttProjectBounds(gantt, meta);
      if (typeof gantt.render === 'function') gantt.render();
      if (chart) {
        requestAnimationFrame(function () {
          alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
          renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
        });
      }
      syncTypicalServiceTermGanttCalendarData(gantt, root, { render: false });
    };
    editor.querySelectorAll('.typical-service-term-gantt-project-start, .typical-service-term-gantt-project-end').forEach(function (input) {
      bindTypicalServiceTermGanttDateInput(input);
      input.addEventListener('change', apply);
    });
  }

  function normalizeTypicalServiceTermGanttDates(ganttData) {
    const data = Array.isArray(ganttData?.data) ? ganttData.data : [];
    data.forEach(function (task) {
      const start = parsePolicyGanttDate(task.start_date);
      const end = parsePolicyGanttDate(task.end_date);
      const deadline = parsePolicyGanttDate(task.deadline);
      const constraintDate = parsePolicyGanttDate(task.constraint_date);
      if (start) task.start_date = start;
      if (end) task.end_date = end;
      if (deadline) task.deadline = deadline;
      task.constraint_type = normalizeTypicalServiceTermGanttConstraintType(task.constraint_type);
      if (!task.constraint_type) {
        delete task.constraint_type;
        delete task.constraint_date;
      } else if (constraintDate && task.constraint_type !== 'asap' && task.constraint_type !== 'alap') {
        task.constraint_date = constraintDate;
      } else {
        delete task.constraint_date;
      }
    });
    return {
      data: data,
      links: Array.isArray(ganttData?.links) ? ganttData.links : [],
      meta: normalizeTypicalServiceTermGanttMeta(ganttData?.meta, data),
    };
  }

  function renderTypicalServiceTermGantt(root, payload, context) {
    const editor = root?.querySelector('#typical-service-term-gantt-editor');
    const chart = root?.querySelector('#typical-service-term-gantt');
    const subtitle = root?.querySelector('#typical-service-term-gantt-subtitle');
    if (!editor || !chart) return;
    const sessionId = Number.isFinite(Number(context?.sessionId))
      ? Number(context.sessionId)
      : beginTypicalServiceTermGanttSession(editor);
    editor.dataset.typicalServiceTermGanttSessionId = String(sessionId);

    const ganttData = normalizeTypicalServiceTermGanttDates(
      withDefaultTypicalServiceTermGanttMeta(payload?.gantt || {}, root)
    );
    editor.dataset.currentTermId = normalizeFilterValue(context?.termId);
    editor.dataset.currentGanttUrl = normalizeFilterValue(context?.ganttUrl);
    editor._typicalServiceTermGanttMeta = ganttData.meta || {};
    editor._typicalServiceTermGanttSavedMeta = Object.assign({}, editor._typicalServiceTermGanttMeta);
    applyTypicalServiceTermGanttMetaCalendarSettings(editor._typicalServiceTermGanttMeta);
    editor._typicalServiceTermGanttData = {
      data: ganttData.data,
      links: ganttData.links,
    };
    editor._typicalServiceTermGanttOpenTaskIds = normalizeTypicalServiceTermGanttSectionOptions(
      ganttData.data
        .filter(function (task) { return !!task.$open; })
        .map(function (task) { return String(task.id); })
    );
    editor._typicalServiceTermGanttSectionCatalog = normalizeTypicalServiceTermGanttSectionCatalog(payload?.section_options);
    editor._typicalServiceTermGanttSections = editor._typicalServiceTermGanttSectionCatalog.map(function (item) {
      return item.label;
    });
    editor._typicalServiceTermGanttSpecialties = normalizeTypicalServiceTermGanttTextOptions(payload?.specialty_options);
    editor._typicalServiceTermGanttExecutors = normalizeTypicalServiceTermGanttExecutorCatalog(payload?.executor_options);

    syncTypicalServiceTermGanttProjectBoundInputs(root);
    bindTypicalServiceTermGanttProjectBounds(root);
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

    const gantt = mountTypicalServiceTermGantt(root, chart);
    if (!gantt) {
      showTypicalServiceTermGanttMessage(root, 'DHTMLX Gantt не загружен.', true);
      return;
    }
    ensureTypicalServiceTermGanttResources(root, gantt);
  }

  async function openTypicalServiceTermGanttEditor(button) {
    const root = pane();
    if (!root || !button || button.disabled) return;
    const ganttUrl = normalizeFilterValue(button.dataset.ganttUrl);
    if (!ganttUrl) return;
    const editor = root.querySelector('#typical-service-term-gantt-editor');
    const sessionId = beginTypicalServiceTermGanttSession(editor);
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
        sessionId: sessionId,
      });
      // Auto-scroll the editor into view by default — useful when opened from
      // a button below the fold (e.g. the policy-pane "Редактировать" buttons).
      // Callers that already have the editor in view (e.g. the projects-pane
      // "Вид: График" toggle) can opt out via dataset.noScroll = '1' on the
      // trigger element.
      if (button.dataset.noScroll !== '1') {
        editor?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } catch (error) {
      showTypicalServiceTermGanttMessage(root, error.message || 'Не удалось загрузить диаграмму.', true);
    }
  }

  function serializeTypicalServiceTermGantt(root) {
    const gantt = getTypicalServiceTermGanttInstance();
    if (!gantt) return null;
    syncTypicalServiceTermGanttScheduling(gantt);
    syncTypicalServiceTermGanttParentProgress(gantt);
    const editor = root.querySelector('#typical-service-term-gantt-editor');
    const formatDate = formatPolicyGanttDateInput;
    const tasks = [];
    gantt.eachTask(function (task) {
      if (!normalizeTypicalServiceTermGanttConstraintType(task?.constraint_type)) {
        delete task.constraint_type;
        delete task.constraint_date;
      }
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
    const projectStart = parseTypicalServiceTermGanttDateInput(editor?.querySelector('.typical-service-term-gantt-project-start')?.value);
    let projectEnd = parseTypicalServiceTermGanttDateInput(editor?.querySelector('.typical-service-term-gantt-project-end')?.value);
    if (projectStart) meta.project_start = formatDate(projectStart);
    if (projectEnd && projectStart && projectEnd < projectStart) projectEnd = new Date(projectStart);
    if (projectEnd) meta.project_end = formatDate(projectEnd);
    syncTypicalServiceTermGanttMetaCalendarSettings(meta);
    if (editor?._typicalServiceTermGanttResources) {
      editor._typicalServiceTermGanttResources.serializeMeta(meta);
    }
    if (!meta.base_date && tasks.length) {
      meta.base_date = tasks
        .map(function (task) { return normalizeFilterValue(task.start_date); })
        .filter(Boolean)
        .sort()[0] || '';
    }
    return { data: tasks, links: links, meta: meta };
  }

  function setTypicalServiceTermGanttSaveLoading(saveButton, isLoading) {
    if (!(saveButton instanceof HTMLButtonElement)) return;
    if (isLoading) {
      if (saveButton.dataset.loading === '1') return;
      saveButton.dataset.loading = '1';
      saveButton.dataset.originalHtml = saveButton.innerHTML;
      saveButton.disabled = true;
      saveButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Сохранение...';
      return;
    }
    if (saveButton.dataset.originalHtml) {
      saveButton.innerHTML = saveButton.dataset.originalHtml;
      delete saveButton.dataset.originalHtml;
    }
    saveButton.disabled = false;
    delete saveButton.dataset.loading;
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
    setTypicalServiceTermGanttSaveLoading(saveButton, true);
    showTypicalServiceTermGanttMessage(root, '', false);
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
      setTypicalServiceTermGanttFullscreen(root, false);
      rememberPolicyScrollPosition();
      var refreshUrl = normalizeFilterValue(editor?.dataset?.refreshUrl) || '/policy/policy/partial/';
      var refreshTarget = normalizeFilterValue(editor?.dataset?.refreshTarget) || '#policy-pane';
      await htmx.ajax('GET', refreshUrl, { target: refreshTarget, swap: 'outerHTML' });
    } catch (error) {
      showTypicalServiceTermGanttMessage(root, error.message || 'Не удалось сохранить диаграмму.', true);
      setTypicalServiceTermGanttSaveLoading(saveButton, false);
    }
  }

  function cancelTypicalServiceTermGantt() {
    const root = pane();
    if (!root) return;
    const editor = root.querySelector('#typical-service-term-gantt-editor');
    const saveButton = root.querySelector('#typical-service-term-gantt-save-btn');
    const gantt = window.__policyTypicalServiceTermGantt;
    setTypicalServiceTermGanttFullscreen(root, false);
    if (gantt && typeof gantt.hideLightbox === 'function') {
      gantt.hideLightbox();
    }
    cleanupTypicalServiceTermGanttLightboxArtifacts();
    if (editor) {
      beginTypicalServiceTermGanttSession(editor);
      applyTypicalServiceTermGanttMetaCalendarSettings(editor._typicalServiceTermGanttSavedMeta || editor._typicalServiceTermGanttMeta || {});
      editor.classList.add('d-none');
      editor.dataset.currentTermId = '';
      editor.dataset.currentGanttUrl = '';
      editor._typicalServiceTermGanttMeta = {};
      editor._typicalServiceTermGanttSavedMeta = {};
      editor._typicalServiceTermGanttData = null;
      editor._typicalServiceTermGanttSectionCatalog = [];
      editor._typicalServiceTermGanttSections = [];
      editor._typicalServiceTermGanttSpecialties = [];
      editor._typicalServiceTermGanttExecutors = [];
      if (editor._typicalServiceTermGanttResources) {
        try { editor._typicalServiceTermGanttResources.dispose(); } catch (_) { /* noop */ }
        editor._typicalServiceTermGanttResources = null;
        window.__policyTypicalServiceTermGanttResources = null;
      }
    }
    // Editor is being closed — but we deliberately KEEP the section's Gantt
    // instance alive. Its chart container is still in the DOM (just hidden via
    // .d-none on the editor), and we want re-opens to reuse the same instance
    // so that any DOM event handlers that captured `gantt` in their closure
    // (column-resize, etc.) remain valid. Full disposal happens in the
    // htmx:afterSwap handler at the bottom of this file when the host
    // container actually leaves the document.
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
    const gantt = window.__policyTypicalServiceTermGantt;
    if (gantt && typeof gantt.hideLightbox === 'function') {
      gantt.hideLightbox();
    }
    cleanupTypicalServiceTermGanttLightboxArtifacts();
  }

  // In fullscreen the typical-service-term Gantt uses the same
  // `autosize: 'y'` sizing strategy as the regular (in-flow) editor: the
  // gantt container shrinks/grows to the actual content height, so the
  // grid/timeline horizontal scrollbars always sit directly below the
  // last row (and travel with row open/close + outline level changes,
  // just like outside of fullscreen). The fullscreen overlay then makes
  // the EDITOR itself scrollable when the gantt exceeds the viewport,
  // with toolbar and footer pinned at top/bottom via `position: sticky`
  // (see site.css). This keeps the scrollbar behaviour consistent
  // regardless of which control triggered the layout change (scale
  // toggle, outline level, manual row open/close, etc.).
  function refreshTypicalServiceTermGanttFrame(root) {
    const editor = root?.querySelector('#typical-service-term-gantt-editor');
    const chart = root?.querySelector('#typical-service-term-gantt');
    if (!editor || !chart || editor.classList.contains('d-none')) return;
    // Never impose an inline pixel height — fullscreen relies on the
    // editor-level scrollbar plus dhtmlxGantt's own autosize behaviour.
    chart.style.height = '';
    const gantt = window.__policyTypicalServiceTermGantt;
    if (!gantt) return;
    captureTypicalServiceTermGanttOpenState(gantt, editor);
    gantt.config.autosize = 'y';
    if (typeof gantt.setSizes === 'function') gantt.setSizes();
    restoreTypicalServiceTermGanttOpenState(gantt, editor);
    if (typeof gantt.render === 'function') gantt.render();
    requestAnimationFrame(function () {
      installTypicalServiceTermGanttColumnResizeHandles(gantt, chart);
      alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
      renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
    });
  }

  function setTypicalServiceTermGanttFullscreen(root, active) {
    const editor = root?.querySelector('#typical-service-term-gantt-editor');
    const button = root?.querySelector('#typical-service-term-gantt-fullscreen-btn');
    if (!editor) return;
    const currentGantt = getTypicalServiceTermGanttInstance();
    if (currentGantt) captureTypicalServiceTermGanttOpenState(currentGantt, editor);
    const nextActive = !!active && !editor.classList.contains('d-none');
    editor.classList.toggle('typical-service-term-gantt-editor--fullscreen', nextActive);
    document.body.classList.toggle('typical-service-term-gantt-fullscreen-active', nextActive);
    if (button) {
      const icon = button.querySelector('i');
      button.setAttribute(
        'aria-label',
        nextActive ? 'Вернуть диаграмму в обычный режим' : 'Развернуть диаграмму на весь экран'
      );
      button.title = nextActive ? 'Вернуть диаграмму в обычный режим' : 'Развернуть диаграмму на весь экран';
      icon?.classList.toggle('bi-arrows-fullscreen', !nextActive);
      icon?.classList.toggle('bi-fullscreen-exit', nextActive);
    }
    requestAnimationFrame(function () {
      refreshTypicalServiceTermGanttFrame(root);
    });
  }

  function getTypicalServiceTermGanttSettingsModalElement() {
    return document.getElementById('typical-service-term-gantt-settings-modal');
  }

  function syncTypicalServiceTermGanttSettingsCalendarKindFields() {
    const kindSelect = document.getElementById('typical-service-term-gantt-settings-calendar-kind');
    const countryField = document.getElementById('typical-service-term-gantt-settings-country-field');
    const executorDisplaySelect = document.getElementById('typical-service-term-gantt-settings-executor-display');
    const kind = normalizeTypicalServiceTermGanttCalendarKind(kindSelect?.value || getTypicalServiceTermGanttCalendarKind());
    if (kindSelect) kindSelect.value = kind;
    if (executorDisplaySelect && !executorDisplaySelect.value) {
      executorDisplaySelect.value = kind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT
        ? TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE
        : getTypicalServiceTermGanttExecutorDisplayMode();
    }
    if (countryField) {
      countryField.classList.toggle('d-none', kind !== TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION);
    }
  }

  function populateTypicalServiceTermGanttSettingsCountrySelect(payload) {
    const select = document.getElementById('typical-service-term-gantt-settings-country');
    if (!select) return;
    const items = Array.isArray(payload?.items) ? payload.items : [];
    const selectedId = getTypicalServiceTermGanttCalendarCountryId();
    let defaultId = Number.isFinite(payload?.default_id) ? Number(payload.default_id) : null;
    if (!Number.isFinite(defaultId)) {
      const russia = items.find(function (item) {
        return String(item.alpha2 || '').toUpperCase() === TYPICAL_SERVICE_TERM_GANTT_DEFAULT_COUNTRY_ALPHA2;
      });
      defaultId = russia ? russia.id : (items[0] ? items[0].id : null);
    }
    select.innerHTML = '';
    if (!items.length) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'Нет поддерживаемых стран';
      select.appendChild(opt);
      select.disabled = true;
      return;
    }
    select.disabled = false;
    items.forEach(function (item) {
      const opt = document.createElement('option');
      opt.value = String(item.id);
      const code = item.alpha2 || item.code || '';
      opt.textContent = code ? (item.short_name + ' (' + code + ')') : item.short_name;
      select.appendChild(opt);
    });
    select.dataset.loaded = '1';
    const targetId = Number.isFinite(selectedId) ? selectedId : defaultId;
    if (Number.isFinite(targetId)) {
      select.value = String(targetId);
      if (!Number.isFinite(selectedId)) {
        // Persist the resolved default so subsequent sessions keep using it.
        setTypicalServiceTermGanttCalendarCountryId(targetId);
      }
    }
  }

  function loadTypicalServiceTermGanttSettingsCountries() {
    const select = document.getElementById('typical-service-term-gantt-settings-country');
    if (select) {
      select.disabled = true;
      select.dataset.loaded = '';
      select.innerHTML = '<option value="">Загрузка списка стран…</option>';
    }
    return fetchTypicalServiceTermGanttCalendarCountries()
      .then(function (payload) {
        populateTypicalServiceTermGanttSettingsCountrySelect(payload);
        return payload;
      })
      .catch(function (error) {
        if (select) {
          select.innerHTML = '<option value="">Не удалось загрузить список стран</option>';
          select.disabled = true;
          select.dataset.loaded = '';
        }
        setTypicalServiceTermGanttSettingsStatus(
          error?.message || 'Не удалось загрузить список стран.',
          'error'
        );
        throw error;
      });
  }

  function setTypicalServiceTermGanttSettingsStatus(message, kind) {
    const status = document.getElementById('typical-service-term-gantt-settings-status');
    if (!status) return;
    status.textContent = message || '';
    status.classList.remove('text-danger', 'text-success', 'text-muted');
    if (!message) {
      status.classList.add('text-muted');
      return;
    }
    if (kind === 'error') {
      status.classList.add('text-danger');
    } else if (kind === 'success') {
      status.classList.add('text-success');
    } else {
      status.classList.add('text-muted');
    }
  }

  function initTypicalServiceTermGanttSettingsModal() {
    if (window.__policyTypicalServiceTermGanttSettingsModalBound) return;
    const modalEl = getTypicalServiceTermGanttSettingsModalElement();
    if (!modalEl) return;
    window.__policyTypicalServiceTermGanttSettingsModalBound = true;
    const applyBtn = document.getElementById('typical-service-term-gantt-settings-apply-btn');
    const kindSelect = document.getElementById('typical-service-term-gantt-settings-calendar-kind');
    if (kindSelect) {
      kindSelect.addEventListener('change', function () {
        const executorDisplaySelect = document.getElementById('typical-service-term-gantt-settings-executor-display');
        if (executorDisplaySelect &&
          normalizeTypicalServiceTermGanttCalendarKind(kindSelect.value) === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT) {
          executorDisplaySelect.value = TYPICAL_SERVICE_TERM_GANTT_EXECUTOR_DISPLAY_RESOURCE;
        }
        syncTypicalServiceTermGanttSettingsCalendarKindFields();
        if (normalizeTypicalServiceTermGanttCalendarKind(kindSelect.value) === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION) {
          const countrySelect = document.getElementById('typical-service-term-gantt-settings-country');
          if (!countrySelect?.dataset.loaded) {
            loadTypicalServiceTermGanttSettingsCountries().catch(function () { /* status is set by loader */ });
          }
        } else {
          setTypicalServiceTermGanttSettingsStatus('');
        }
      });
    }
    if (applyBtn) {
      applyBtn.addEventListener('click', function () {
        const kind = normalizeTypicalServiceTermGanttCalendarKind(
          document.getElementById('typical-service-term-gantt-settings-calendar-kind')?.value
        );
        const executorDisplay = normalizeTypicalServiceTermGanttExecutorDisplayMode(
          document.getElementById('typical-service-term-gantt-settings-executor-display')?.value
        );
        const select = document.getElementById('typical-service-term-gantt-settings-country');
        const newId = select && select.value ? Number(select.value) : null;
        if (kind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION && !Number.isFinite(newId)) {
          setTypicalServiceTermGanttSettingsStatus('Выберите страну.', 'error');
          return;
        }
        const previousKind = getTypicalServiceTermGanttCalendarKind();
        const root = pane();
        const gantt = getTypicalServiceTermGanttInstance();
        const editor = root?.querySelector('#typical-service-term-gantt-editor');
        if (editor && !getTypicalServiceTermGanttMetaCalendarKind(editor._typicalServiceTermGanttSavedMeta)) {
          editor._typicalServiceTermGanttSavedMeta = Object.assign({}, editor._typicalServiceTermGanttMeta || {}, {
            calendar_kind: previousKind,
            calendar_country_id: getTypicalServiceTermGanttCalendarCountryId(),
            executor_display: getTypicalServiceTermGanttExecutorDisplayMode(),
          });
        }
        const calendarTransitionBaseline = gantt &&
          previousKind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT &&
          kind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION
          ? captureTypicalServiceTermGanttCalendarTransitionBaseline(gantt)
          : null;
        setTypicalServiceTermGanttCalendarKind(kind, { persist: false });
        setTypicalServiceTermGanttExecutorDisplayMode(executorDisplay);
        if (editor) {
          editor._typicalServiceTermGanttMeta = Object.assign({}, editor._typicalServiceTermGanttMeta || {}, {
            calendar_kind: kind,
            executor_display: executorDisplay,
          });
        }
        setTypicalServiceTermGanttCalendarDaysMode(false);
        if (kind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION) {
          setTypicalServiceTermGanttCalendarCountryId(newId);
          setTypicalServiceTermGanttSettingsStatus('Загрузка производственного календаря…');
        } else {
          setTypicalServiceTermGanttSettingsStatus('Применение условного календаря…');
        }
        syncTypicalServiceTermGanttProjectBoundInputs(root);
        syncTypicalServiceTermGanttDateInputFormats(root);
        syncTypicalServiceTermGanttCalendarDaysToggle(root);
        syncTypicalServiceTermGanttHideNonWorkingToggle(root);
        if (gantt) {
          applyTypicalServiceTermGanttProjectBounds(gantt, editor?._typicalServiceTermGanttMeta || {});
          applyTypicalServiceTermGanttScale(gantt, getTypicalServiceTermGanttScale(root));
          if (typeof gantt.render === 'function') gantt.render();
        }
        const promise = gantt
          ? syncTypicalServiceTermGanttCalendarData(gantt, root, {
            render: true,
            calendarTransitionBaseline: calendarTransitionBaseline,
          })
          : Promise.resolve(null);
        Promise.resolve(promise)
          .then(function (dataset) {
            if (kind === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_ABSTRACT) {
              setTypicalServiceTermGanttSettingsStatus('Применено: условный календарь.', 'success');
            } else if (dataset) {
              setTypicalServiceTermGanttSettingsStatus(
                'Применено: ' + (dataset.country?.short_name || '') +
                  ' (' + dataset.yearFrom + '–' + dataset.yearTo + ').',
                'success'
              );
            } else {
              setTypicalServiceTermGanttSettingsStatus(
                'Календарь применён. Откройте диаграмму, чтобы увидеть изменения.',
                'success'
              );
            }
            window.setTimeout(function () {
              if (!window.bootstrap) return;
              const instance = window.bootstrap.Modal.getInstance(modalEl);
              if (instance) instance.hide();
            }, 400);
          })
          .catch(function (error) {
            setTypicalServiceTermGanttSettingsStatus(
              error?.message || 'Не удалось применить настройки.',
              'error'
            );
          });
      });
    }
  }

  function openTypicalServiceTermGanttSettingsModal() {
    const modalEl = getTypicalServiceTermGanttSettingsModalElement();
    if (!modalEl || !window.bootstrap) return;
    // The modal is included inside policy-pane (which lives inside the
    // Bootstrap "products" tab). When the user opens the editor from a
    // different tab (e.g. "projects"), the products tab has display:none on
    // an ancestor, hiding the modal too while still rendering its backdrop.
    // Hoist the modal to <body> on first open so it's always visible.
    if (modalEl.parentElement !== document.body) {
      document.body.appendChild(modalEl);
    }
    initTypicalServiceTermGanttSettingsModal();
    setTypicalServiceTermGanttSettingsStatus('');
    const kindSelect = document.getElementById('typical-service-term-gantt-settings-calendar-kind');
    if (kindSelect) kindSelect.value = getTypicalServiceTermGanttCalendarKind();
    const executorDisplaySelect = document.getElementById('typical-service-term-gantt-settings-executor-display');
    if (executorDisplaySelect) executorDisplaySelect.value = getTypicalServiceTermGanttExecutorDisplayMode();
    syncTypicalServiceTermGanttSettingsCalendarKindFields();
    const select = document.getElementById('typical-service-term-gantt-settings-country');
    if (getTypicalServiceTermGanttCalendarKind() === TYPICAL_SERVICE_TERM_GANTT_CALENDAR_KIND_PRODUCTION) {
      loadTypicalServiceTermGanttSettingsCountries().catch(function () { /* status is set by loader */ });
    } else if (select && !select.dataset.loaded) {
      select.disabled = true;
      select.innerHTML = '<option value="">Выберите производственный календарь</option>';
    }
    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  function initTypicalServiceTermGanttEditor(root) {
    syncTypicalServiceTermGanttEditButton();
    syncTypicalServiceTermGanttScaleButtons(root, getTypicalServiceTermGanttScale(root));
    syncTypicalServiceTermGanttTimeboxToggle(root);
    syncTypicalServiceTermGanttFreeDatesToggle(root);
    syncTypicalServiceTermGanttCalendarDaysToggle(root);
    syncTypicalServiceTermGanttHideNonWorkingToggle(root);
    bindTypicalServiceTermGanttSelectionReset(root);
    qa('.js-typical-service-term-gantt-scale', root).forEach(function (button) {
      if (button.dataset.bound === '1') return;
      button.dataset.bound = '1';
      button.addEventListener('click', function () {
        const scale = button.dataset.scale || TYPICAL_SERVICE_TERM_GANTT_DEFAULT_SCALE;
        if (P) P.set(TYPICAL_SERVICE_TERM_GANTT_SCALE_PREF_KEY, scale);
        const editor = root.querySelector('#typical-service-term-gantt-editor');
        if (!editor || editor.classList.contains('d-none')) return;
        const chart = root.querySelector('#typical-service-term-gantt');
        const currentGantt = getTypicalServiceTermGanttInstance();
        if (currentGantt) captureTypicalServiceTermGanttOpenState(currentGantt, editor);
        syncTypicalServiceTermGanttScaleButtons(root, scale);
        if (chart) {
          chart.classList.toggle('typical-service-term-gantt-scale-day', scale === 'day');
          chart.classList.toggle('typical-service-term-gantt-scale-week', scale === 'week');
          chart.classList.toggle('typical-service-term-gantt-scale-month', scale === 'month');
          chart.classList.toggle('typical-service-term-gantt-scale-quarter', scale === 'quarter');
        }
        // Scale change is structural (new gantt.config.scales) — we re-mount
        // the section's instance from scratch so all derived layout state is
        // rebuilt cleanly. Cached data (editor._typicalServiceTermGanttData)
        // was captured by snapshotTypicalServiceTermGanttData() up-stream;
        // here we make sure it's up to date with what the user has been
        // editing, then dispose and re-mount.
        let currentGanttBeforeRemount = window.__policyTypicalServiceTermGantt;
        if (currentGanttBeforeRemount) {
          captureTypicalServiceTermGanttData(currentGanttBeforeRemount);
        }
        let gantt = chart ? mountTypicalServiceTermGantt(root, chart) : null;
        if (!gantt || !chart) return;
        restoreTypicalServiceTermGanttOpenState(gantt, editor);
        requestAnimationFrame(function () {
          if (typeof gantt.render === 'function') gantt.render();
          alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
          renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
          requestAnimationFrame(function () {
            alignTypicalServiceTermGanttMilestoneLinks(gantt, chart);
            renderTypicalServiceTermGanttTimeMarkers(gantt, chart);
          });
        });
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
    const fullscreenButton = root.querySelector('#typical-service-term-gantt-fullscreen-btn');
    if (fullscreenButton && fullscreenButton.dataset.bound !== '1') {
      fullscreenButton.dataset.bound = '1';
      fullscreenButton.addEventListener('click', function () {
        const editor = root.querySelector('#typical-service-term-gantt-editor');
        setTypicalServiceTermGanttFullscreen(
          root,
          !(editor && editor.classList.contains('typical-service-term-gantt-editor--fullscreen'))
        );
      });
    }
    const freeDatesButton = root.querySelector('#typical-service-term-gantt-free-dates-btn');
    if (freeDatesButton && freeDatesButton.dataset.bound !== '1') {
      freeDatesButton.dataset.bound = '1';
      freeDatesButton.addEventListener('click', function () {
        setTypicalServiceTermGanttSnapToGridEnabled(!isTypicalServiceTermGanttSnapToGridEnabled());
        const gantt = getTypicalServiceTermGanttInstance();
        applyTypicalServiceTermGanttDragRounding(gantt, root);
        if (gantt && typeof gantt.render === 'function') gantt.render();
      });
    }
    const timeboxButton = root.querySelector('#typical-service-term-gantt-timebox-btn');
    if (timeboxButton && timeboxButton.dataset.bound !== '1') {
      timeboxButton.dataset.bound = '1';
      timeboxButton.addEventListener('click', function () {
        setTypicalServiceTermGanttTimeboxEnabled(!isTypicalServiceTermGanttTimeboxEnabled());
        syncTypicalServiceTermGanttTimeboxToggle(root);
      });
    }
    const calendarDaysButton = root.querySelector('#typical-service-term-gantt-calendar-days-btn');
    if (calendarDaysButton && calendarDaysButton.dataset.bound !== '1') {
      calendarDaysButton.dataset.bound = '1';
      calendarDaysButton.addEventListener('click', function () {
        setTypicalServiceTermGanttCalendarDaysMode(!isTypicalServiceTermGanttCalendarDaysMode());
        syncTypicalServiceTermGanttCalendarDaysToggle(root);
        syncTypicalServiceTermGanttHideNonWorkingToggle(root);
        const gantt = getTypicalServiceTermGanttInstance();
        if (!gantt) return;
        // The hidden day sub-scale presence depends on whether we're in
        // working-days mode + hide-non-working, so refresh the scale config.
        applyTypicalServiceTermGanttScale(gantt, getTypicalServiceTermGanttScale(root));
        syncTypicalServiceTermGanttCalendarData(gantt, root, { render: true });
      });
    }
    const hideNonWorkingButton = root.querySelector('#typical-service-term-gantt-hide-non-working-btn');
    if (hideNonWorkingButton && hideNonWorkingButton.dataset.bound !== '1') {
      hideNonWorkingButton.dataset.bound = '1';
      hideNonWorkingButton.addEventListener('click', function () {
        if (isTypicalServiceTermGanttCalendarDaysMode()) return;
        setTypicalServiceTermGanttHideNonWorkingDays(!isTypicalServiceTermGanttHideNonWorkingDays());
        syncTypicalServiceTermGanttHideNonWorkingToggle(root);
        const gantt = getTypicalServiceTermGanttInstance();
        if (!gantt) return;
        // At week/month/quarter scales we splice in (or remove) a hidden
        // day-level sub-scale to drive the collapsing. Re-apply the scale
        // config so `gantt.config.scales` reflects the new state before the
        // re-render.
        applyTypicalServiceTermGanttScale(gantt, getTypicalServiceTermGanttScale(root));
        applyTypicalServiceTermGanttWorkTime(gantt, window.__policyTypicalServiceTermGanttActiveCalendar || null);
        try { if (typeof gantt.render === 'function') gantt.render(); } catch (_) { /* ignore */ }
        const chart = root.querySelector('#typical-service-term-gantt');
        if (chart) refreshTypicalServiceTermGanttNonWorkingShading(gantt, chart);
      });
    }
    const settingsButton = root.querySelector('#typical-service-term-gantt-settings-btn');
    if (settingsButton && settingsButton.dataset.bound !== '1') {
      settingsButton.dataset.bound = '1';
      settingsButton.addEventListener('click', function () {
        openTypicalServiceTermGanttSettingsModal();
      });
    }
    initTypicalServiceTermGanttSettingsModal();
    if (!window.__policyTypicalServiceTermGanttEscapeBound) {
      window.__policyTypicalServiceTermGanttEscapeBound = true;
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
          const currentRoot = pane();
          const editor = currentRoot?.querySelector('#typical-service-term-gantt-editor');
          if (editor?.classList.contains('typical-service-term-gantt-editor--fullscreen')) {
            setTypicalServiceTermGanttFullscreen(currentRoot, false);
            event.preventDefault();
            return;
          }
          hideTypicalServiceTermGanttLightbox();
        }
      });
    }
    if (!window.__policyTypicalServiceTermGanttFullscreenResizeBound) {
      window.__policyTypicalServiceTermGanttFullscreenResizeBound = true;
      window.addEventListener('resize', function () {
        const currentRoot = pane();
        const editor = currentRoot?.querySelector('#typical-service-term-gantt-editor');
        if (editor?.classList.contains('typical-service-term-gantt-editor--fullscreen')) {
          refreshTypicalServiceTermGanttFrame(currentRoot);
        }
      });
    }
    // Per-instance engine: no cross-section re-acquire needed when the
    // #policy tab is shown — our chart's gantt instance is still attached to
    // its own container regardless of which tab was previously visible.
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
    // Project-schedule action buttons live inside #projects-pane and are
    // handled by projects-panels.js. The two pane()s share button selectors,
    // so without this guard a click on the project-schedule edit/up/down/delete
    // would be processed twice (once here, once there) — opening BOTH the
    // policy-modal AND the projects-modal and stacking two backdrops.
    const ownerPane = btn.closest('#policy-pane, #projects-pane');
    if (ownerPane && ownerPane.id !== 'policy-pane') return;
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

  async function handlePolicyTableUpload(uploadUrl, file) {
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
        var html;
        if (typeof data.updated === 'number') {
          html = '<div class="mb-2"><strong>Создано строк: ' + data.created +
            '; обновлено строк: ' + data.updated + '</strong></div>';
        } else {
          html = '<div class="mb-2"><strong>Загружено строк: ' + data.created + '</strong></div>';
        }
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
      'typical-service-compositions-docx-upload-btn': 'typical-service-compositions-docx-file-input',
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
      'typical-service-compositions-docx-file-input': '/policy/policy/typical-service-composition/docx-upload/',
      'typical-service-terms-csv-file-input': '/policy/policy/typical-service-term/csv-upload/',
    };
    var url = mapping[e.target.id];
    if (!url) return;
    var file = e.target.files[0];
    if (!file) return;
    await handlePolicyTableUpload(url, file);
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

  // After an htmx swap, the policy pane (and our chart container with it) may
  // have been replaced by a fresh DOM node. Our cached Gantt instance is
  // bound to the OLD detached node, so any subsequent operation would target
  // a phantom. Detect that and dispose the instance — a fresh one will be
  // created lazily next time the user opens the editor.
  document.body.addEventListener('htmx:afterSwap', function () {
    const gantt = window.__policyTypicalServiceTermGantt;
    if (!gantt) return;
    const boundContainer = gantt.$container || gantt.$root
      || (gantt.$layout && gantt.$layout.$container) || null;
    if (boundContainer && document.body.contains(boundContainer)) return;
    disposeTypicalServiceTermGanttInstance();
  });

  // The editor markup is replicated inside the projects pane for the
  // "График проекта" Gantt. Re-initialise handlers when that pane swaps.
  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (!(e.target && e.target.id === 'projects-pane')) return;
    try { initTypicalServiceTermGanttEditor(e.target); } catch (_) { /* noop */ }
  });

  initPolicyProductSelects(document);
  initTypicalServiceCompositionWrapToggle();
  collapseSpecialtyTariffsSpecialties();
  initPolicyMasterFilters();
  initTypicalServiceTermGanttEditor(document);

  // Public API so other panes (currently the projects "График проекта") can
  // drive the same typical-service-term-gantt editor without duplicating its
  // huge implementation. Pass either an HTMLElement (a button with the usual
  // dataset) or a plain options object.
  window.TypicalServiceTermGantt = {
    open: function (buttonOrOptions) {
      var trigger = buttonOrOptions;
      if (!(buttonOrOptions instanceof HTMLElement)) {
        var options = buttonOrOptions || {};
        trigger = document.createElement('button');
        if (options.ganttUrl) trigger.dataset.ganttUrl = String(options.ganttUrl);
        if (options.termId !== undefined && options.termId !== null) {
          trigger.dataset.termId = String(options.termId);
        }
        if (options.productLabel) trigger.dataset.productLabel = String(options.productLabel);
        // Honored by openTypicalServiceTermGanttEditor — when truthy the
        // editor is NOT auto-scrolled into view after rendering.
        if (options.noScroll) trigger.dataset.noScroll = '1';
      }
      // Ensure editor handlers are bound on whichever pane is currently
      // active. We pass the active pane (returned by pane()) so that
      // root.querySelector(...) resolves to the editor INSIDE that pane —
      // critical when both #policy-pane and #projects-pane render the
      // editor with the same ids (Bootstrap tab siblings).
      try {
        var currentPane = pane();
        if (currentPane) initTypicalServiceTermGanttEditor(currentPane);
      } catch (_) { /* noop */ }
      return openTypicalServiceTermGanttEditor(trigger);
    },
    close: function () {
      try { cancelTypicalServiceTermGantt(); } catch (_) { /* noop */ }
    },
    isOpen: function () {
      var editor = typicalServiceTermGanttEditorEl();
      return !!(editor && !editor.classList.contains('d-none'));
    },
    refresh: function () {
      var pane2 = pane();
      if (!pane2) return;
      var editor = pane2.querySelector('#typical-service-term-gantt-editor');
      var url = editor && editor.dataset ? editor.dataset.currentGanttUrl : '';
      if (!url) return;
      try {
        var trigger = document.createElement('button');
        trigger.dataset.ganttUrl = url;
        if (editor.dataset.currentTermId) trigger.dataset.termId = editor.dataset.currentTermId;
        return openTypicalServiceTermGanttEditor(trigger);
      } catch (_) { /* noop */ }
    },
  };
})();