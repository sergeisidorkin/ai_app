// Project schedule Gantt — view switch + delegation to TypicalServiceTermGantt.
//
// The "График проекта" Gantt is functionally identical to the
// "Типовые сроки оказания услуг" editor: same toolbar (hide non-working,
// calendar days, timebox, free dates, project bounds, scale, fullscreen),
// same grid columns, same calendar settings modal, same Save/Cancel.
//
// To guarantee parity (and avoid duplicating thousands of lines of
// implementation) we reuse the EXACT same #typical-service-term-gantt-editor
// markup inside #projects-pane and drive it via the public API exposed by
// policy-panels.js — window.TypicalServiceTermGantt. Each open() creates a
// fresh independent GanttEngine.create() instance under the hood, so the
// two editors never share state.

(function () {
  'use strict';

  const VIEW_PREF_KEY = 'projects:scheduleView';
  const VIEW_TABLE = 'table';
  const VIEW_GANTT = 'gantt';

  function pane() {
    // Multiple Bootstrap tabs render the same panel ids; pick the projects
    // pane (this module is projects-only) — querySelectorAll lets us prefer
    // the latest if the partial was hot-swapped.
    var all = document.querySelectorAll('#projects-pane');
    return all.length > 1 ? all[all.length - 1] : all[0] || null;
  }

  function uiPrefGet(key, fallback) {
    if (window.UIPref && typeof window.UIPref.get === 'function') {
      try { return window.UIPref.get(key, fallback); } catch (_) { /* noop */ }
    }
    return fallback;
  }

  function uiPrefSet(key, value) {
    if (window.UIPref && typeof window.UIPref.set === 'function') {
      try { window.UIPref.set(key, value); } catch (_) { /* noop */ }
    }
  }

  function getCurrentView(root) {
    const radio = root.querySelector('.js-project-schedule-view:checked');
    return radio && radio.value === VIEW_GANTT ? VIEW_GANTT : VIEW_TABLE;
  }

  function getSelectedRadio(root) {
    return root.querySelector('.js-project-schedule-filter:checked');
  }

  function getSelectedConfig(root) {
    const radio = getSelectedRadio(root);
    if (!radio || !radio.value) return null;
    return {
      projectId: radio.value,
      ganttUrl: radio.dataset.ganttUrl || '',
      productLabel: (radio.dataset.fullLabel || radio.dataset.summaryLabel || '').trim(),
    };
  }

  function showEmptyHint(root, visible) {
    const empty = root.querySelector('#project-schedule-gantt-empty');
    if (empty) empty.classList.toggle('d-none', !visible);
  }

  function ganttApi() {
    return window.TypicalServiceTermGantt || null;
  }

  function openGanttForSelected(root) {
    const api = ganttApi();
    if (!api) return;
    const config = getSelectedConfig(root);
    if (!config || !config.ganttUrl) {
      api.close();
      showEmptyHint(root, true);
      return;
    }
    showEmptyHint(root, false);
    // Two listeners (custom event + direct radio change) can both schedule
    // an open() in the same tick — dedupe so the heavy fetch+render pipeline
    // only runs once per actually-distinct request. We tag the editor with
    // the in-flight URL and skip identical follow-ups while it's pending.
    const editor = root.querySelector('#typical-service-term-gantt-editor');
    if (editor && editor.dataset.scheduleGanttPendingUrl === config.ganttUrl) {
      return;
    }
    if (editor) editor.dataset.scheduleGanttPendingUrl = config.ganttUrl;
    try {
      api.open({
        ganttUrl: config.ganttUrl,
        termId: config.projectId,
        productLabel: config.productLabel,
        // The editor is rendered in place of the table inside the visible
        // "График проекта" section, so we don't want the chart's default
        // scrollIntoView behaviour to jerk the page down.
        noScroll: true,
      });
    } catch (_) { /* surfaced inside the editor's own message bar */ }
    // Clear the pending tag on the next macro-task — by then api.open()'s
    // own async fetch has already kicked off and any duplicate calls
    // arriving in this same animation frame have been suppressed.
    setTimeout(function () {
      if (editor) delete editor.dataset.scheduleGanttPendingUrl;
    }, 0);
  }

  function closeGantt() {
    const api = ganttApi();
    if (api) api.close();
  }

  function setView(root, view) {
    const normalized = view === VIEW_GANTT ? VIEW_GANTT : VIEW_TABLE;
    const isGantt = normalized === VIEW_GANTT;
    const tableWrap = root.querySelector('.project-schedule-table-wrap');
    const ganttWrap = root.querySelector('#project-schedule-gantt-wrap');
    const label = root.querySelector('.js-project-schedule-view-label');
    const titleIcon = root.querySelector('.js-project-schedule-title-icon');

    if (tableWrap) tableWrap.classList.toggle('d-none', isGantt);
    if (ganttWrap) ganttWrap.classList.toggle('d-none', !isGantt);
    if (label) label.textContent = isGantt ? 'График' : 'Таблица';
    if (titleIcon) {
      // Swap heading icon between table/gantt views: bi-table ↔ bi-calendar-week.
      titleIcon.classList.toggle('bi-table', !isGantt);
      titleIcon.classList.toggle('bi-calendar-week', isGantt);
    }

    root.querySelectorAll('.js-project-schedule-view').forEach(function (input) {
      input.checked = (input.value === normalized);
    });
    uiPrefSet(VIEW_PREF_KEY, normalized);

    if (isGantt) {
      window.requestAnimationFrame(function () { openGanttForSelected(root); });
    } else {
      closeGantt();
    }
  }

  function init() {
    const root = pane();
    if (!root) return;
    const dropdown = root.querySelector('#project-schedule-view-dropdown');
    if (!dropdown || dropdown.dataset.bound === '1') return;
    dropdown.dataset.bound = '1';

    dropdown.addEventListener('change', function (event) {
      const input = event.target.closest('.js-project-schedule-view');
      if (!input) return;
      setView(root, input.value);
    });

    if (root.dataset.scheduleGanttFilterBound !== '1') {
      root.dataset.scheduleGanttFilterBound = '1';
      // Reload the Gantt when the project filter changes. We listen for BOTH:
      //   1) "project-schedule-filter-changed" — the existing custom event;
      //   2) the underlying `change` event on the project-filter radios via
      //      delegation on the stable pane (#projects-pane is never re-created,
      //      only its innerHTML is swapped, so this listener survives htmx).
      // Direct delegation guarantees the Gantt always reloads when the user
      // picks another project, even if some path doesn't dispatch the custom
      // event (e.g. programmatic filter resets via __syncProjectScheduleFilter).
      function reloadIfGanttView() {
        if (getCurrentView(root) !== VIEW_GANTT) return;
        window.requestAnimationFrame(function () { openGanttForSelected(root); });
      }
      root.addEventListener('project-schedule-filter-changed', reloadIfGanttView);
      root.addEventListener('change', function (event) {
        var input = event.target && event.target.closest && event.target.closest('.js-project-schedule-filter');
        if (!input || !root.contains(input) || !input.checked) return;
        reloadIfGanttView();
      });
    }

    // When the user clicks "Отмена" in the editor (handler is inside
    // policy-panels.js), revert the view selector back to "Таблица" so the
    // table reappears instead of an empty wrap.
    const cancelBtn = root.querySelector('#typical-service-term-gantt-cancel-btn');
    if (cancelBtn && cancelBtn.dataset.projectScheduleBound !== '1') {
      cancelBtn.dataset.projectScheduleBound = '1';
      cancelBtn.addEventListener('click', function () {
        // Defer so the editor's own cancel handler runs first.
        window.requestAnimationFrame(function () { setView(root, VIEW_TABLE); });
      });
    }

    const initialView = uiPrefGet(VIEW_PREF_KEY, VIEW_TABLE);
    setView(root, initialView === VIEW_GANTT ? VIEW_GANTT : VIEW_TABLE);
  }

  document.addEventListener('DOMContentLoaded', init);
  document.body.addEventListener('htmx:afterSettle', function (event) {
    if (event.target && event.target.id === 'projects-pane') {
      // The editor markup was just re-rendered; reset our wiring.
      window.requestAnimationFrame(init);
    }
  });
})();
