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

  // ---------------------------------------------------------------------
  // «Призрак» диаграммы на время перерисовки #projects-pane.
  //
  // Любое сохранение в разделе (а также обновление самого графика) целиком
  // перерисовывает #projects-pane через htmx. Новая разметка приходит с
  // пустым скрытым редактором, после чего диаграмма заново запрашивается
  // fetch'ем и монтируется — между этими моментами пользователь видел, как
  // область графика схлопывается, показывает «Загрузка диаграммы…» и спустя
  // ~0,5 с появляется снова. Чтобы этого не было, перед swap снимаем
  // статическую копию видимой диаграммы (inert, без id/name/hx-атрибутов),
  // сразу после swap кладём её поверх нового контейнера, фиксируя его высоту,
  // и убираем копию, когда новая диаграмма отрисована (или по тайм-ауту).
  // Живой редактор и экземпляр Gantt при этом живут ровно так же, как и
  // раньше — копия чисто визуальная.
  // ---------------------------------------------------------------------
  const GHOST_CLASS = 'project-schedule-gantt-ghost';
  const WRAP_PENDING_CLASS = 'project-schedule-gantt-wrap--pending';
  const GHOST_MAX_LIFETIME_MS = 10000;
  let pendingGhost = null;   // снято в htmx:beforeSwap, ждёт вставки
  let activeGhost = null;    // вставлено в новый wrap, ждёт готовности графика

  function ganttIsBusy() {
    // Во время drag'n'drop или открытого lightbox статическая копия была бы
    // неточной — в этих случаях работаем как раньше, без призрака.
    return document.body.classList.contains('typical-service-term-gantt-row-dragging')
      || !!document.querySelector('.gantt_cal_light, .gantt_cal_cover, .gantt_drag_marker');
  }

  function captureGanttGhost(oldRoot) {
    if (!oldRoot || getCurrentView(oldRoot) !== VIEW_GANTT) return null;
    const wrap = oldRoot.querySelector('#project-schedule-gantt-wrap');
    if (!wrap || wrap.classList.contains('d-none')) return null;
    if (ganttIsBusy()) return null;

    // Если предыдущая перерисовка ещё не завершилась, повторно используем
    // уже существующую копию — не клонируем wrap вместе с призраком внутри.
    const existingGhost = wrap.querySelector(':scope > .' + GHOST_CLASS);
    if (existingGhost) {
      const keptScrolls = [];
      existingGhost.querySelectorAll('*').forEach(function (el) {
        if (el.scrollLeft || el.scrollTop) keptScrolls.push({ el: el, left: el.scrollLeft, top: el.scrollTop });
      });
      existingGhost.remove();
      return { ghost: existingGhost, height: parseFloat(existingGhost.style.height) || 0, scrolls: keptScrolls };
    }

    const editor = wrap.querySelector('#typical-service-term-gantt-editor');
    const chart = editor && editor.querySelector('#typical-service-term-gantt');
    if (!editor || editor.classList.contains('d-none')) return null;
    if (editor.classList.contains('typical-service-term-gantt-editor--fullscreen')) return null;
    if (!chart || !chart.querySelector('.gantt_container')) return null;
    const height = wrap.getBoundingClientRect().height;
    if (!(height > 40)) return null;

    const ghost = wrap.cloneNode(true);

    // Пары «оригинал → копия» снимаем до любых удалений, пока структуры
    // деревьев совпадают: позиции прокрутки и значения полей cloneNode не
    // переносит, а без них копия визуально «прыгнула» бы к началу шкалы.
    const sourceNodes = wrap.querySelectorAll('*');
    const ghostNodes = ghost.querySelectorAll('*');
    const scrolls = [];
    for (let i = 0; i < sourceNodes.length && i < ghostNodes.length; i += 1) {
      const src = sourceNodes[i];
      const dst = ghostNodes[i];
      if (src.scrollLeft || src.scrollTop) {
        scrolls.push({ el: dst, left: src.scrollLeft, top: src.scrollTop });
      }
      if ((src.tagName === 'INPUT' || src.tagName === 'TEXTAREA' || src.tagName === 'SELECT')
          && 'value' in dst && src.type !== 'checkbox' && src.type !== 'radio') {
        try { dst.value = src.value; } catch (_) { /* noop */ }
      }
    }

    // Копия не должна быть видна ни одному селектору приложения и htmx:
    // убираем id/name/for, hx-* и data-*-атрибуты, поведенческие js-* классы,
    // скрипты и служебные узлы Gantt.
    ghost.querySelectorAll('script, .gantt_cal_light, .gantt_cal_cover, .gantt_drag_marker, .modal')
      .forEach(function (node) { node.remove(); });
    const all = [ghost].concat(Array.prototype.slice.call(ghost.querySelectorAll('*')));
    all.forEach(function (node) {
      Array.prototype.slice.call(node.attributes).forEach(function (attr) {
        const name = attr.name;
        if (name === 'id' || name === 'name' || name === 'for' || name === 'tabindex'
            || name.indexOf('hx-') === 0 || name.indexOf('data-') === 0
            || name.indexOf('on') === 0) {
          node.removeAttribute(name);
        }
      });
      if (node.classList && node.classList.length) {
        Array.prototype.slice.call(node.classList).forEach(function (cls) {
          if (cls.indexOf('js-') === 0) node.classList.remove(cls);
        });
      }
    });
    ghost.classList.remove('d-none', 'project-schedule-gantt-wrap');
    ghost.classList.add(GHOST_CLASS);
    ghost.setAttribute('aria-hidden', 'true');
    ghost.setAttribute('inert', '');
    ghost.style.height = Math.round(height) + 'px';
    return { ghost: ghost, height: height, scrolls: scrolls };
  }

  function finishGanttGhost() {
    const state = activeGhost;
    activeGhost = null;
    if (!state) return;
    if (state.timer) window.clearTimeout(state.timer);
    if (state.ghost && state.ghost.parentNode) state.ghost.parentNode.removeChild(state.ghost);
    const wrap = state.wrap;
    if (wrap) {
      wrap.classList.remove(WRAP_PENDING_CLASS);
      wrap.style.minHeight = '';
    }
  }

  function restoreGanttScrollFromGhost(state) {
    // Новая диаграмма монтируется с прокруткой в начало шкалы; переносим на
    // неё положение полос прокрутки с копии, чтобы картинка не «прыгала».
    // Предпочтительно через gantt.scrollTo(); запасной путь — скроллбары
    // dhtmlx, данные тогда синхронизирует его штатный обработчик scroll.
    if (!state || !state.wrap || !state.scrolls) return;
    const chart = state.wrap.querySelector('#typical-service-term-gantt');
    if (!chart || !chart.querySelector('.gantt_container')) return;
    let x = null;
    let y = null;
    state.scrolls.forEach(function (item) {
      const cls = item.el && item.el.classList;
      if (!cls) return;
      if (cls.contains('gantt_hor_scroll') && item.left) x = item.left;
      if (cls.contains('gantt_ver_scroll') && item.top) y = item.top;
    });
    if (x === null && y === null) return;
    const api = ganttApi();
    const gantt = api && typeof api.getInstance === 'function' ? api.getInstance() : null;
    if (gantt && typeof gantt.scrollTo === 'function') {
      // Штатный API: синхронно обновляет и внутреннее состояние dhtmlx, и
      // DOM — позиция переживает последующие gantt.render() (календарь,
      // маркеры), которые редактор запускает отложенно.
      gantt.scrollTo(x, y);
      return;
    }
    const hor = x !== null ? chart.querySelector('.gantt_hor_scroll') : null;
    const ver = y !== null ? chart.querySelector('.gantt_ver_scroll') : null;
    if (hor) hor.scrollLeft = x;
    if (ver) ver.scrollTop = y;
  }

  function finishGanttGhostAfterFrame() {
    // Даём один кадр пост-монтажным rAF-коллбэкам редактора (выравнивание
    // линий связей, маркеры) выполниться до снятия копии; сам rAF отрабатывает
    // до отрисовки, так что промежуточного кадра пользователь не увидит.
    if (!activeGhost) return;
    try { restoreGanttScrollFromGhost(activeGhost); } catch (_) { /* noop */ }
    window.requestAnimationFrame(finishGanttGhost);
  }

  function mountGanttGhost(newRoot) {
    const state = pendingGhost;
    pendingGhost = null;
    if (!state || !newRoot) return;
    const wrap = newRoot.querySelector('#project-schedule-gantt-wrap');
    if (!wrap) return;
    finishGanttGhost();

    // Переключаем вид синхронно, в той же задаче, что и swap: таблица не
    // успеет мелькнуть даже если requestAnimationFrame(init) задержится.
    const tableWrap = newRoot.querySelector('.project-schedule-table-wrap');
    if (tableWrap) tableWrap.classList.add('d-none');
    wrap.classList.remove('d-none');
    const label = newRoot.querySelector('.js-project-schedule-view-label');
    if (label) label.textContent = 'График';
    const titleIcon = newRoot.querySelector('.js-project-schedule-title-icon');
    if (titleIcon) {
      titleIcon.classList.remove('bi-table');
      titleIcon.classList.add('bi-calendar-week');
    }

    wrap.classList.add(WRAP_PENDING_CLASS);
    wrap.style.minHeight = Math.round(state.height) + 'px';
    wrap.insertBefore(state.ghost, wrap.firstChild);
    // Позиции прокрутки применяем микрозадачей: в момент afterSettle секция
    // «Определение границ» ещё может быть скрыта (её показывает другой
    // обработчик afterSettle), а у элемента без layout scrollLeft обнуляется.
    // Микрозадача выполнится до конца текущей задачи — до отрисовки кадра.
    const scrolls = state.scrolls;
    Promise.resolve().then(function () {
      scrolls.forEach(function (item) {
        try {
          item.el.scrollLeft = item.left;
          item.el.scrollTop = item.top;
        } catch (_) { /* noop */ }
      });
    });
    activeGhost = {
      ghost: state.ghost,
      wrap: wrap,
      scrolls: scrolls,
      timer: window.setTimeout(finishGanttGhost, GHOST_MAX_LIFETIME_MS),
    };
  }

  function openGanttForSelected(root) {
    const api = ganttApi();
    if (!api) {
      finishGanttGhost();
      return;
    }
    const config = getSelectedConfig(root);
    if (!config || !config.ganttUrl) {
      api.close();
      showEmptyHint(root, true);
      finishGanttGhost();
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
      const opening = api.open({
        ganttUrl: config.ganttUrl,
        termId: config.projectId,
        productLabel: config.productLabel,
        // The editor is rendered in place of the table inside the visible
        // "График проекта" section, so we don't want the chart's default
        // scrollIntoView behaviour to jerk the page down.
        noScroll: true,
      });
      // open() — async-функция: промис резолвится после отрисовки новой
      // диаграммы (или после вывода ошибки в message bar). В обоих случаях
      // копия больше не нужна.
      if (activeGhost) {
        Promise.resolve(opening).then(finishGanttGhostAfterFrame, finishGanttGhostAfterFrame);
      }
    } catch (_) {
      finishGanttGhost();
      /* surfaced inside the editor's own message bar */
    }
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
      finishGanttGhost();
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

  // Снимок видимой диаграммы — пока старая разметка ещё в документе.
  document.body.addEventListener('htmx:beforeSwap', function (event) {
    const target = event.detail && event.detail.target;
    if (!(target instanceof Element) || target.id !== 'projects-pane') return;
    if (event.detail && event.detail.shouldSwap === false) return;
    pendingGhost = null;
    try { pendingGhost = captureGanttGhost(target); } catch (_) { pendingGhost = null; }
  });

  // Вставляем копию в afterSettle (фаза capture — раньше остальных
  // обработчиков). Именно в settle, а не в afterSwap: htmx на этапе settle
  // восстанавливает атрибуты новых узлов с id (handleAttributes), и классы /
  // min-height, выставленные на #project-schedule-gantt-wrap раньше, были бы
  // стёрты. С defaultSettleDelay = 0 settle идёт в той же задаче, что и swap,
  // так что кадра с пустой областью графика не возникает.
  document.body.addEventListener('htmx:afterSettle', function (event) {
    if (!(event.target instanceof Element) || event.target.id !== 'projects-pane') {
      return;
    }
    try { mountGanttGhost(event.target); } catch (_) { pendingGhost = null; finishGanttGhost(); }
  }, true);

  document.body.addEventListener('htmx:afterSettle', function (event) {
    if (event.target && event.target.id === 'projects-pane') {
      // The editor markup was just re-rendered; reset our wiring.
      window.requestAnimationFrame(init);
    }
  });
})();
