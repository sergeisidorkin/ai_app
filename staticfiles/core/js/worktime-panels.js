(function () {
  if (window.__worktimePanelBound) return;
  window.__worktimePanelBound = true;
  var worktimeFlatpickrPromise = null;

  function qa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }
  function panels() { return qa('[data-worktime-panel]'); }

  function loadScriptOnce(src) {
    return new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[data-worktime-src="' + src + '"]');
      if (existing) {
        if (existing.dataset.loaded === '1') {
          resolve();
          return;
        }
        existing.addEventListener('load', function () { resolve(); }, { once: true });
        existing.addEventListener('error', function () { reject(new Error('Failed to load ' + src)); }, { once: true });
        return;
      }
      var script = document.createElement('script');
      script.src = src;
      script.async = true;
      script.dataset.worktimeSrc = src;
      script.addEventListener('load', function () {
        script.dataset.loaded = '1';
        resolve();
      }, { once: true });
      script.addEventListener('error', function () {
        reject(new Error('Failed to load ' + src));
      }, { once: true });
      document.head.appendChild(script);
    });
  }

  function ensureStyleOnce(href) {
    if (document.querySelector('link[data-worktime-href="' + href + '"]')) return;
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset.worktimeHref = href;
    document.head.appendChild(link);
  }

  function ensureWorktimeFlatpickr() {
    if (window.flatpickr) return Promise.resolve();
    if (worktimeFlatpickrPromise) return worktimeFlatpickrPromise;
    ensureStyleOnce('https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css');
    worktimeFlatpickrPromise = loadScriptOnce('https://cdn.jsdelivr.net/npm/flatpickr')
      .then(function () {
        return loadScriptOnce('https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/ru.js');
      })
      .catch(function () {
        worktimeFlatpickrPromise = null;
        throw new Error('Unable to initialize worktime flatpickr');
      });
    return worktimeFlatpickrPromise;
  }

  function startOfWeek(date) {
    var value = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    var weekday = value.getDay();
    var shift = weekday === 0 ? -6 : 1 - weekday;
    value.setDate(value.getDate() + shift);
    return value;
  }

  function endOfWeek(date) {
    var value = startOfWeek(date);
    value.setDate(value.getDate() + 6);
    return value;
  }

  function formatIsoDate(date) {
    var y = date.getFullYear();
    var m = String(date.getMonth() + 1).padStart(2, '0');
    var d = String(date.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + d;
  }

  function parseIsoDate(value) {
    if (!value) return null;
    var parts = String(value).split('-');
    if (parts.length !== 3) return null;
    var y = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10);
    var d = parseInt(parts[2], 10);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  }

  function clearWeekHighlight(fp) {
    if (!fp || !fp.daysContainer) return;
    qa('.flatpickr-day', fp.daysContainer).forEach(function (dayEl) {
      dayEl.classList.remove('worktime-week-selected');
    });
  }

  function clearWeekHover(fp) {
    if (!fp || !fp.daysContainer) return;
    qa('.flatpickr-day', fp.daysContainer).forEach(function (dayEl) {
      dayEl.classList.remove('worktime-week-hover');
    });
  }

  function highlightSelectedWeek(fp, selectedDate) {
    clearWeekHighlight(fp);
    if (!fp || !fp.daysContainer || !selectedDate) return;
    var weekStart = startOfWeek(selectedDate);
    var weekEnd = endOfWeek(selectedDate);
    qa('.flatpickr-day', fp.daysContainer).forEach(function (dayEl) {
      var dateObj = dayEl.dateObj;
      if (!dateObj) return;
      if (dateObj >= weekStart && dateObj <= weekEnd) {
        dayEl.classList.add('worktime-week-selected');
      }
    });
  }

  function highlightHoverWeek(fp, hoveredDate) {
    clearWeekHover(fp);
    if (!fp || !fp.daysContainer || !hoveredDate) return;
    var weekStart = startOfWeek(hoveredDate);
    var weekEnd = endOfWeek(hoveredDate);
    qa('.flatpickr-day', fp.daysContainer).forEach(function (dayEl) {
      var dateObj = dayEl.dateObj;
      if (!dateObj) return;
      if (dateObj >= weekStart && dateObj <= weekEnd) {
        dayEl.classList.add('worktime-week-hover');
      }
    });
  }

  function bindFlatpickrWeekHover(fp) {
    if (!fp || !fp.daysContainer || fp.daysContainer.dataset.worktimeWeekHoverBound === '1') return;
    fp.daysContainer.dataset.worktimeWeekHoverBound = '1';
    fp.daysContainer.addEventListener('mouseover', function (event) {
      var dayEl = event.target && event.target.closest ? event.target.closest('.flatpickr-day') : null;
      if (!dayEl || !fp.daysContainer.contains(dayEl)) return;
      highlightHoverWeek(fp, dayEl.dateObj);
    });
    fp.daysContainer.addEventListener('mouseleave', function () {
      clearWeekHover(fp);
    });
  }

  function hideWeekError(root) {
    var errorEl = root && root.querySelector('[data-worktime-client-error]');
    if (!errorEl) return;
    errorEl.classList.add('d-none');
    errorEl.textContent = '';
  }

  function showWeekError(root, message) {
    var errorEl = root && root.querySelector('[data-worktime-client-error]');
    if (!errorEl) return;
    errorEl.classList.add('d-none');
    errorEl.classList.remove('worktime-error-bump');
    errorEl.textContent = '';
    void errorEl.offsetWidth;
    errorEl.textContent = message;
    errorEl.classList.remove('d-none');
    errorEl.classList.add('worktime-error-bump');
    if (typeof errorEl.scrollIntoView === 'function') {
      errorEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    window.setTimeout(function () {
      errorEl.classList.remove('worktime-error-bump');
    }, 450);
  }

  function formatDisplayDate(date) {
    var d = String(date.getDate()).padStart(2, '0');
    var m = String(date.getMonth() + 1).padStart(2, '0');
    var y = String(date.getFullYear()).slice(-2);
    return d + '.' + m + '.' + y;
  }

  function formatWeekLabel(date) {
    var weekStart = startOfWeek(date);
    var weekEnd = endOfWeek(date);
    return 'с ' + formatDisplayDate(weekStart) + ' по ' + formatDisplayDate(weekEnd);
  }

  function updateWeekLabel(form, selectedDate) {
    var label = form && form.querySelector('[data-worktime-week-label]');
    if (!label || !selectedDate) return;
    label.textContent = formatWeekLabel(selectedDate);
  }

  function formatMonthPeriodLabel(dateObj) {
    if (!(dateObj instanceof Date) || Number.isNaN(dateObj.getTime())) return '';
    return MONTH_NAMES_RU[dateObj.getMonth()] + ', ' + dateObj.getFullYear() + ' г.';
  }

  function formatYearPeriodLabel(dateObj) {
    if (!(dateObj instanceof Date) || Number.isNaN(dateObj.getTime())) return '';
    return dateObj.getFullYear() + ' г.';
  }

  function pad2(value) {
    return String(value).padStart(2, '0');
  }

  function parseWorktimePeriodValue(value) {
    if (!value) return null;
    var rawValue = String(value).trim();
    var monthMatch = rawValue.match(/^(\d{4})-(\d{2})$/);
    if (monthMatch) {
      return new Date(parseInt(monthMatch[1], 10), parseInt(monthMatch[2], 10) - 1, 1);
    }
    var yearMatch = rawValue.match(/^(\d{4})$/);
    if (yearMatch) {
      return new Date(parseInt(yearMatch[1], 10), 0, 1);
    }
    return null;
  }

  function submitWorktimeGetForm(form) {
    if (!form) return;
    flushVisibleWorktimePendingState().finally(function () {
      if (form.matches && form.matches('[data-worktime-period-form]')) {
        persistWorktimeGeneralPreferences(form);
      }
      var target = form.closest('[data-worktime-panel]');
      if (window.htmx && target) {
        var url = form.getAttribute('hx-get') || form.getAttribute('action') || window.location.pathname;
        var params = new URLSearchParams(new FormData(form)).toString();
        var requestUrl = params ? (url + (url.indexOf('?') === -1 ? '?' : '&') + params) : url;
        target.setAttribute('hx-get', requestUrl);
        window.htmx.ajax('GET', requestUrl, {
          target: target,
          swap: form.getAttribute('hx-swap') || 'innerHTML'
        });
        return;
      }
      if (typeof form.requestSubmit === 'function') {
        form.requestSubmit();
        return;
      }
      var submitEvent = new Event('submit', { bubbles: true, cancelable: true });
      if (!form.dispatchEvent(submitEvent)) return;
      form.submit();
    });
  }

  function flushVisibleWorktimeAutosave() {
    if (!window.__worktimeAutosave || typeof window.__worktimeAutosave.flushVisible !== 'function') {
      return Promise.resolve(true);
    }
    return window.__worktimeAutosave.flushVisible();
  }

  function flushVisibleWorktimeRowOrder() {
    if (!window.__queuedRowOrder || typeof window.__queuedRowOrder.flushVisible !== 'function') {
      return Promise.resolve(true);
    }
    return window.__queuedRowOrder.flushVisible();
  }

  function flushVisibleWorktimePendingState() {
    return Promise.all([
      flushVisibleWorktimeAutosave(),
      flushVisibleWorktimeRowOrder()
    ]).then(function (results) {
      return results.every(Boolean);
    });
  }

  function persistWorktimeGeneralPreferences(form) {
    if (!form || !window.localStorage) return;
    try {
      var scaleInput = form.querySelector('[data-worktime-scale-value]');
      var breakdownInput = form.querySelector('[data-worktime-breakdown-value]');
      var histSortInput = form.querySelector('[data-worktime-hist-sort-value]');
      var periodInput = form.querySelector('[data-worktime-period-value]');
      var companyInput = form.querySelector('[data-worktime-company-value]');
      if (!scaleInput || !breakdownInput || !histSortInput || !periodInput) return;

      var scaleValue = String(scaleInput.value || '').toLowerCase() === 'year' ? 'year' : 'month';
      var breakdownValue = String(breakdownInput.value || '').toLowerCase() === 'activities' ? 'activities' : 'employees';
      var histSortValue = String(histSortInput.value || '').toLowerCase();
      var periodValue = String(periodInput.value || '').trim();
      var companyValue = String(companyInput && companyInput.value || '').trim();

      window.localStorage.setItem('worktime.general.scale', scaleValue);
      window.localStorage.setItem('worktime.general.breakdown', breakdownValue);
      if (histSortValue === 'asc' || histSortValue === 'desc') {
        window.localStorage.setItem('worktime.general.histSort', histSortValue);
      } else {
        window.localStorage.removeItem('worktime.general.histSort');
      }

      if (scaleValue === 'year') {
        var yearMatch = periodValue.match(/^(\d{4})/);
        if (yearMatch) {
          window.localStorage.setItem('worktime.general.period.year', yearMatch[1]);
        }
      } else {
        var monthMatch = periodValue.match(/^(\d{4})-(\d{2})$/);
        if (monthMatch) {
          window.localStorage.setItem('worktime.general.period.month', monthMatch[1] + '-' + monthMatch[2]);
        }
      }
      window.localStorage.setItem('worktime.general.companyFilter', companyValue || '__all__');
    } catch (error) {
      // Ignore localStorage access failures.
    }
  }

  var MONTH_NAMES_RU = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
  ];

  var MONTH_SHORT_NAMES_RU = [
    'янв', 'фев', 'мар', 'апр', 'май', 'июн',
    'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'
  ];

  function flatpickrLocale() {
    return (window.flatpickr && window.flatpickr.l10ns && window.flatpickr.l10ns.ru) || 'default';
  }

  function hideMonthPanel(fp) {
    if (!fp || !fp._worktimeMonthPanel) return;
    fp._worktimeMonthPanel.classList.add('d-none');
    if (fp.calendarContainer) fp.calendarContainer.classList.remove('worktime-month-panel-open');
    if (fp._worktimeHeaderBtn) fp._worktimeHeaderBtn.setAttribute('aria-expanded', 'false');
    syncWorktimeFlatpickrHeight(fp);
  }

  function syncMonthPanelYearScroll(fp, behavior) {
    if (!fp || !fp._worktimeYearList) return;
    var active = fp._worktimeYearList.querySelector('.worktime-flatpickr-current-year-option');
    if (!active) return;
    var firstYearRow = fp._worktimeYearList.querySelector('.worktime-flatpickr-year-option');
    var occlusionOffset = firstYearRow ? Math.round(firstYearRow.offsetHeight * 1.35) : 0;
    var nextTop = Math.max(0, active.offsetTop - occlusionOffset);
    if (behavior === 'smooth' && typeof fp._worktimeYearList.scrollTo === 'function') {
      fp._worktimeYearList.scrollTo({ top: nextTop, behavior: 'smooth' });
      return;
    }
    fp._worktimeYearList.scrollTop = nextTop;
  }

  function syncWorktimeFlatpickrHeader(fp, options) {
    if (!fp || !fp._worktimeHeaderBtn) return;
    var headerMonth = typeof fp._worktimeCommittedHeaderMonth === 'number' ? fp._worktimeCommittedHeaderMonth : fp.currentMonth;
    var headerYear = typeof fp._worktimeCommittedHeaderYear === 'number' ? fp._worktimeCommittedHeaderYear : fp.currentYear;
    if (fp._worktimeHeaderLabel) {
      fp._worktimeHeaderLabel.textContent = MONTH_NAMES_RU[headerMonth] + ', ' + headerYear + ' г.';
    }
    renderMonthPanel(fp);
    if (!(options && options.skipYearScroll)) {
      syncMonthPanelYearScroll(fp);
    }
  }

  function syncCommittedHeaderState(fp, dateObj) {
    if (!fp) return;
    var sourceDate = dateObj || (fp.selectedDates && fp.selectedDates[0]) || null;
    if (sourceDate instanceof Date && !Number.isNaN(sourceDate.getTime())) {
      fp._worktimeCommittedHeaderMonth = sourceDate.getMonth();
      fp._worktimeCommittedHeaderYear = sourceDate.getFullYear();
      return;
    }
    fp._worktimeCommittedHeaderMonth = fp.currentMonth;
    fp._worktimeCommittedHeaderYear = fp.currentYear;
  }

  function syncCommittedHeaderToVisibleMonth(fp) {
    if (!fp) return;
    fp._worktimeCommittedHeaderMonth = fp.currentMonth;
    fp._worktimeCommittedHeaderYear = fp.currentYear;
  }

  function wait(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
  }

  function animateYearListScroll(fp, duration, targetYear) {
    if (!fp || !fp._worktimeYearList) return Promise.resolve();
    var selector = typeof targetYear === 'number' ? '.worktime-flatpickr-year-option[data-year="' + targetYear + '"]' : '.worktime-flatpickr-current-year-option';
    var target = fp._worktimeYearList.querySelector(selector);
    if (!target) return Promise.resolve();
    var firstYearRow = fp._worktimeYearList.querySelector('.worktime-flatpickr-year-option');
    var occlusionOffset = firstYearRow ? Math.round(firstYearRow.offsetHeight * 1.35) : 0;
    var targetTop = Math.max(0, target.offsetTop - occlusionOffset);
    var startTop = fp._worktimeYearList.scrollTop;
    var delta = targetTop - startTop;
    if (!delta) return Promise.resolve();
    return new Promise(function (resolve) {
      var startedAt = null;
      function ease(progress) {
        return 1 - Math.pow(1 - progress, 3);
      }
      function step(timestamp) {
        if (startedAt === null) startedAt = timestamp;
        var elapsed = timestamp - startedAt;
        var progress = Math.min(elapsed / duration, 1);
        fp._worktimeYearList.scrollTop = startTop + (delta * ease(progress));
        if (progress < 1) {
          window.requestAnimationFrame(step);
          return;
        }
        resolve();
      }
      window.requestAnimationFrame(step);
    });
  }

  async function runYearTransition(fp, targetYear) {
    if (!fp || !fp._worktimeMonthGrid || !fp._worktimeYearList || fp._worktimeTransitioning) return;
    if (targetYear === fp.currentYear) return;
    fp._worktimeTransitioning = true;
    fp._worktimeMonthGrid.classList.add('worktime-flatpickr-month-grid-collapsed');
    await wait(460);
    await animateYearListScroll(fp, 900, targetYear);
    await wait(100);
    fp._worktimePanelSelectedYear = targetYear;
    fp._worktimePanelSelectedMonth = null;
    setFlatpickrMonthYear(fp, fp.currentMonth, targetYear, { skipYearScroll: true });
    await wait(80);
    fp._worktimeMonthGrid.classList.remove('worktime-flatpickr-month-grid-collapsed');
    await wait(420);
    fp._worktimeTransitioning = false;
  }

  function syncWorktimeFlatpickrWidth(fp) {
    if (!fp || !fp.calendarContainer || !fp._positionElement) return;
    var width = Math.ceil(fp._positionElement.getBoundingClientRect().width || 0);
    if (!width) return;
    fp.calendarContainer.style.width = width + 'px';
  }

  function syncWorktimeFlatpickrHeight(fp) {
    if (!fp || !fp.calendarContainer) return;
    var isMonthPanelOpen = fp.calendarContainer.classList.contains('worktime-month-panel-open');
    if (!isMonthPanelOpen) {
      var baseHeight = Math.ceil(fp.calendarContainer.offsetHeight || 0);
      if (!baseHeight) return;
      fp._worktimeBaseHeight = baseHeight;
      fp.calendarContainer.style.minHeight = baseHeight + 'px';
      fp.calendarContainer.style.height = '';
      return;
    }
    if (fp._worktimeBaseHeight) {
      fp.calendarContainer.style.height = fp._worktimeBaseHeight + 'px';
    }
  }

  function setFlatpickrMonthYear(fp, monthIndex, year, options) {
    if (!fp) return;
    var targetYear = typeof year === 'number' ? year : fp.currentYear;
    var targetMonth = typeof monthIndex === 'number' ? monthIndex : fp.currentMonth;
    if (typeof fp.jumpToDate === 'function') {
      fp.jumpToDate(new Date(targetYear, targetMonth, 1), false);
    } else {
      if (typeof year === 'number' && year !== fp.currentYear) {
        if (typeof fp.changeYear === 'function') {
          fp.changeYear(year);
        } else {
          fp.currentYear = year;
        }
      }
      if (typeof monthIndex === 'number') {
        if (monthIndex !== fp.currentMonth) {
          fp.changeMonth(monthIndex, false);
        } else {
          fp.redraw();
        }
      } else {
        fp.redraw();
      }
    }
    syncWorktimeFlatpickrHeader(fp, options);
    syncWorktimeFlatpickrHeight(fp);
  }

  function createYearOption(fp, year, isCurrent) {
    var yearBtn = document.createElement('button');
    yearBtn.type = 'button';
    yearBtn.className = 'worktime-flatpickr-year-option';
    if (isCurrent) {
      yearBtn.classList.add('worktime-flatpickr-current-year-option');
    }
    yearBtn.dataset.year = String(year);
    yearBtn.textContent = String(year);
    yearBtn.addEventListener('pointerdown', function (event) {
      event.preventDefault();
    });
    yearBtn.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      if (typeof event.currentTarget.blur === 'function') {
        event.currentTarget.blur();
      }
      var targetYear = parseInt(event.currentTarget.dataset.year, 10);
      if (targetYear === fp.currentYear) return;
      runYearTransition(fp, targetYear);
    });
    return yearBtn;
  }

  function renderMonthPanel(fp) {
    if (!fp || !fp._worktimeYearList || !fp._worktimeMonthGrid) return;
    var yearButtons = fp._worktimeYearList.querySelectorAll('.worktime-flatpickr-year-option');
    var activeYearButton = null;
    yearButtons.forEach(function (btn) {
      var isActive = parseInt(btn.dataset.year, 10) === fp.currentYear;
      btn.classList.toggle('worktime-flatpickr-current-year-option', isActive);
      if (isActive) activeYearButton = btn;
    });

    if (activeYearButton) {
      if (activeYearButton.nextSibling !== fp._worktimeMonthGrid) {
        fp._worktimeYearList.insertBefore(fp._worktimeMonthGrid, activeYearButton.nextSibling);
      }
    } else {
      fp._worktimeYearList.appendChild(fp._worktimeMonthGrid);
    }

    var activePanelYear = typeof fp._worktimePanelSelectedYear === 'number' ? fp._worktimePanelSelectedYear : fp.currentYear;
    var activePanelMonth = typeof fp._worktimePanelSelectedMonth === 'number' ? fp._worktimePanelSelectedMonth : null;
    Array.from(fp._worktimeMonthGrid.children).forEach(function (btn, index) {
      btn.classList.toggle('is-active', activePanelYear === fp.currentYear && activePanelMonth === index);
    });
  }

  function buildMonthPanel(fp) {
    var panel = document.createElement('div');
    panel.className = 'worktime-flatpickr-month-panel d-none';

    var yearList = document.createElement('div');
    yearList.className = 'worktime-flatpickr-year-list';
    panel.appendChild(yearList);

    for (var year = fp.currentYear - 40; year <= fp.currentYear + 40; year += 1) {
      yearList.appendChild(createYearOption(fp, year, year === fp.currentYear));
    }

    var monthGrid = document.createElement('div');
    monthGrid.className = 'worktime-flatpickr-month-grid';
    MONTH_NAMES_RU.forEach(function (monthName, index) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'worktime-flatpickr-month-option';
      btn.textContent = MONTH_SHORT_NAMES_RU[index];
      btn.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        fp._worktimePanelSelectedYear = fp.currentYear;
        fp._worktimePanelSelectedMonth = index;
        fp._worktimeCommittedHeaderYear = fp.currentYear;
        fp._worktimeCommittedHeaderMonth = index;
        setFlatpickrMonthYear(fp, index, fp.currentYear);
        hideMonthPanel(fp);
      });
      monthGrid.appendChild(btn);
    });

    fp._worktimeMonthPanel = panel;
    fp._worktimeMonthGrid = monthGrid;
    fp._worktimeYearList = yearList;
    renderMonthPanel(fp);
    return panel;
  }

  function buildFlatpickrFooter(fp, form) {
    var footer = document.createElement('div');
    footer.className = 'worktime-flatpickr-footer';

    function applyTodaySelection() {
      var today = new Date();
      fp._worktimePanelSelectedYear = today.getFullYear();
      fp._worktimePanelSelectedMonth = today.getMonth();
      syncCommittedHeaderState(fp, today);
      if (typeof fp.jumpToDate === 'function') {
        fp.jumpToDate(today, false);
      }
      fp.setDate(today, true, 'Y-m-d');
      syncWorktimeFlatpickrHeader(fp, { skipYearScroll: true });
      hideMonthPanel(fp);
    }

    var todayBtn = document.createElement('button');
    todayBtn.type = 'button';
    todayBtn.className = 'worktime-flatpickr-footer-btn';
    todayBtn.textContent = 'Сегодня';
    todayBtn.addEventListener('click', function () {
      applyTodaySelection();
    });

    var clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'worktime-flatpickr-footer-btn';
    clearBtn.textContent = 'Очистить';
    clearBtn.addEventListener('click', function () {
      applyTodaySelection();
    });

    footer.appendChild(todayBtn);
    footer.appendChild(clearBtn);
    fp._worktimeFooter = footer;
    return footer;
  }

  function ensureWorktimeFlatpickrHeader(fp) {
    if (!fp || !fp.calendarContainer || fp.calendarContainer.dataset.worktimeHeaderEnhanced === '1') return;
    var monthsWrap = fp.calendarContainer.querySelector('.flatpickr-months');
    var nativeMonth = monthsWrap && monthsWrap.querySelector('.flatpickr-month');
    var prevBtn = fp.prevMonthNav;
    var nextBtn = fp.nextMonthNav;
    if (!monthsWrap || !prevBtn || !nextBtn) return;

    fp.calendarContainer.dataset.worktimeHeaderEnhanced = '1';

    var headerRow = document.createElement('div');
    headerRow.className = 'worktime-flatpickr-header-row';

    var headerBtn = document.createElement('button');
    headerBtn.type = 'button';
    headerBtn.className = 'worktime-flatpickr-header-btn';
    headerBtn.setAttribute('aria-expanded', 'false');

    var headerLabel = document.createElement('span');
    headerBtn.appendChild(headerLabel);

    var headerCaret = document.createElement('i');
    headerCaret.className = 'bi bi-caret-down-fill worktime-flatpickr-header-caret';
    headerCaret.setAttribute('aria-hidden', 'true');
    headerBtn.appendChild(headerCaret);

    var navStack = document.createElement('div');
    navStack.className = 'worktime-flatpickr-nav-stack';

    prevBtn.classList.add('worktime-flatpickr-nav-btn');
    nextBtn.classList.add('worktime-flatpickr-nav-btn');
    prevBtn.innerHTML = '<i class="bi bi-arrow-up" aria-hidden="true"></i>';
    nextBtn.innerHTML = '<i class="bi bi-arrow-down" aria-hidden="true"></i>';

    navStack.appendChild(prevBtn);
    navStack.appendChild(nextBtn);
    headerRow.appendChild(headerBtn);
    headerRow.appendChild(navStack);
    if (nativeMonth) {
      nativeMonth.setAttribute('hidden', 'hidden');
      nativeMonth.setAttribute('aria-hidden', 'true');
    }
    monthsWrap.insertBefore(headerRow, monthsWrap.firstChild);
    monthsWrap.appendChild(buildMonthPanel(fp));
    fp.calendarContainer.appendChild(buildFlatpickrFooter(fp, fp._worktimeForm));

    fp._worktimeHeaderBtn = headerBtn;
    fp._worktimeHeaderLabel = headerLabel;

    headerBtn.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      var isOpen = !fp._worktimeMonthPanel.classList.contains('d-none');
      if (isOpen) {
        hideMonthPanel(fp);
        return;
      }
      fp._worktimePanelSelectedYear = fp.currentYear;
      fp._worktimePanelSelectedMonth = fp.currentMonth;
      fp._worktimeMonthPanel.classList.remove('d-none');
      if (fp.calendarContainer) fp.calendarContainer.classList.add('worktime-month-panel-open');
      headerBtn.setAttribute('aria-expanded', 'true');
      syncWorktimeFlatpickrHeader(fp);
      syncWorktimeFlatpickrHeight(fp);
    });

    fp.calendarContainer.addEventListener('click', function (event) {
      if (!fp._worktimeMonthPanel || fp._worktimeMonthPanel.classList.contains('d-none')) return;
      if (fp._worktimeMonthPanel.contains(event.target) || headerBtn.contains(event.target)) return;
      hideMonthPanel(fp);
    });

    document.addEventListener('click', function (event) {
      if (!fp.calendarContainer.contains(event.target)) {
        hideMonthPanel(fp);
      }
    });
  }

  function submitWeekSelection(form, selectedDate) {
    if (!form || !selectedDate) return;
    var hidden = form.querySelector('[data-worktime-week-value]');
    if (!hidden) return;
    var normalizedDate = startOfWeek(selectedDate);
    hidden.value = formatIsoDate(normalizedDate);
    var input = form.querySelector('[data-worktime-week-input]');
    if (input) input.value = hidden.value;
    updateWeekLabel(form, normalizedDate);
    submitWorktimeGetForm(form);
  }

  function renderWorktimeYearGrid(form) {
    var grid = form && form.querySelector('[data-worktime-period-year-grid]');
    var periodValueInput = form && form.querySelector('[data-worktime-period-value]');
    if (!grid || !periodValueInput) return;
    var selectedDate = parseWorktimePeriodValue(periodValueInput.value) || new Date();
    var anchorYear = parseInt(form.dataset.worktimePeriodAnchorYear || String(selectedDate.getFullYear()), 10);
    if (!anchorYear) anchorYear = selectedDate.getFullYear();
    grid.innerHTML = '';
    for (var year = anchorYear - 7; year <= anchorYear + 8; year += 1) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'worktime-flatpickr-year-option';
      if (year === selectedDate.getFullYear()) {
        btn.classList.add('worktime-flatpickr-current-year-option');
      }
      btn.textContent = String(year);
      btn.dataset.worktimePeriodYear = String(year);
      grid.appendChild(btn);
    }
  }

  function syncWorktimePeriodPicker(form) {
    if (!form) return;
    var scaleInput = form.querySelector('[data-worktime-scale-value]');
    var periodInput = form.querySelector('[data-worktime-period-value]');
    var panel = form.querySelector('[data-worktime-period-panel]');
    var monthGrid = form.querySelector('[data-worktime-period-month-grid]');
    var yearGrid = form.querySelector('[data-worktime-period-year-grid]');
    var label = form.querySelector('[data-worktime-period-label]');
    var title = form.querySelector('[data-worktime-period-title]');
    if (!scaleInput || !periodInput || !panel || !monthGrid || !yearGrid || !label || !title) return;

    var scale = scaleInput.value === 'year' ? 'year' : 'month';
    var selectedDate = parseWorktimePeriodValue(periodInput.value) || new Date();
    if (scale === 'month') {
      form.dataset.worktimeLastMonth = String(selectedDate.getMonth() + 1);
    }
    if (!form.dataset.worktimePeriodAnchorYear) {
      form.dataset.worktimePeriodAnchorYear = String(selectedDate.getFullYear());
    }

    label.textContent = scale === 'year' ? formatYearPeriodLabel(selectedDate) : formatMonthPeriodLabel(selectedDate);
    title.textContent = scale === 'year' ? 'Выберите год' : String(parseInt(form.dataset.worktimePeriodAnchorYear || String(selectedDate.getFullYear()), 10));

    monthGrid.hidden = scale === 'year';
    yearGrid.hidden = scale !== 'year';

    Array.from(monthGrid.querySelectorAll('[data-worktime-period-month]')).forEach(function (btn) {
      var isActive = scale === 'month' &&
        parseInt(btn.dataset.worktimePeriodMonth, 10) === (selectedDate.getMonth() + 1) &&
        parseInt(form.dataset.worktimePeriodAnchorYear || String(selectedDate.getFullYear()), 10) === selectedDate.getFullYear();
      btn.classList.toggle('is-active', !!isActive);
    });

    if (scale === 'year') {
      renderWorktimeYearGrid(form);
    }
  }

  function syncWorktimeBreakdownFilter(form) {
    if (!form) return;
    var breakdownInput = form.querySelector('[data-worktime-breakdown-value]');
    var breakdownLabel = form.querySelector('[data-worktime-breakdown-label]');
    if (!breakdownInput || !breakdownLabel) return;
    var breakdownValue = breakdownInput.value === 'activities' ? 'activities' : 'employees';
    breakdownInput.value = breakdownValue;
    breakdownLabel.textContent = breakdownValue === 'activities' ? 'по активностям' : 'по сотрудникам';
    form.querySelectorAll('[data-worktime-breakdown-option]').forEach(function (option) {
      option.checked = option.value === breakdownValue;
    });
  }

  function hideWorktimePeriodPanel(form) {
    var panel = form && form.querySelector('[data-worktime-period-panel]');
    if (!panel) return;
    panel.classList.add('d-none');
  }

  function initPeriodFilters(root) {
    var forms = qa('[data-worktime-period-form]', root || document);
    if (!forms.length) return;
    forms.forEach(function (form) {
      if (form.dataset.worktimePeriodBound === '1') return;
      form.dataset.worktimePeriodBound = '1';

      var scaleInput = form.querySelector('[data-worktime-scale-value]');
      var periodInput = form.querySelector('[data-worktime-period-value]');
      var toggle = form.querySelector('[data-worktime-period-toggle]');
      var panel = form.querySelector('[data-worktime-period-panel]');
      var monthGrid = form.querySelector('[data-worktime-period-month-grid]');
      var yearGrid = form.querySelector('[data-worktime-period-year-grid]');
      var prevBtn = form.querySelector('[data-worktime-period-prev]');
      var nextBtn = form.querySelector('[data-worktime-period-next]');
      if (!scaleInput || !periodInput || !toggle || !panel || !monthGrid || !yearGrid || !prevBtn || !nextBtn) return;

      syncWorktimePeriodPicker(form);
      syncWorktimeBreakdownFilter(form);

      toggle.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        if (panel.classList.contains('d-none')) {
          syncWorktimePeriodPicker(form);
          panel.classList.remove('d-none');
          return;
        }
        hideWorktimePeriodPanel(form);
      });

      form.querySelectorAll('[data-worktime-scale-option]').forEach(function (option) {
        option.addEventListener('change', function () {
          var selectedDate = parseWorktimePeriodValue(periodInput.value) || new Date();
          scaleInput.value = this.value;
          if (this.value === 'year') {
            periodInput.value = String(selectedDate.getFullYear());
            form.dataset.worktimePeriodAnchorYear = String(selectedDate.getFullYear());
          } else {
            var currentDate = new Date();
            periodInput.value = currentDate.getFullYear() + '-' + pad2(currentDate.getMonth() + 1);
            form.dataset.worktimePeriodAnchorYear = String(currentDate.getFullYear());
          }
          syncWorktimePeriodPicker(form);
          hideWorktimePeriodPanel(form);
          submitWorktimeGetForm(form);
        });
      });

      form.querySelectorAll('[data-worktime-breakdown-option]').forEach(function (option) {
        option.addEventListener('change', function () {
          var breakdownInput = form.querySelector('[data-worktime-breakdown-value]');
          if (!breakdownInput) return;
          breakdownInput.value = this.value === 'activities' ? 'activities' : 'employees';
          syncWorktimeBreakdownFilter(form);
          hideWorktimePeriodPanel(form);
          submitWorktimeGetForm(form);
        });
      });

      prevBtn.addEventListener('click', function (event) {
        event.preventDefault();
        var currentYear = parseInt(form.dataset.worktimePeriodAnchorYear || String((parseWorktimePeriodValue(periodInput.value) || new Date()).getFullYear()), 10);
        form.dataset.worktimePeriodAnchorYear = String(currentYear + (scaleInput.value === 'year' ? -12 : -1));
        syncWorktimePeriodPicker(form);
      });

      nextBtn.addEventListener('click', function (event) {
        event.preventDefault();
        var currentYear = parseInt(form.dataset.worktimePeriodAnchorYear || String((parseWorktimePeriodValue(periodInput.value) || new Date()).getFullYear()), 10);
        form.dataset.worktimePeriodAnchorYear = String(currentYear + (scaleInput.value === 'year' ? 12 : 1));
        syncWorktimePeriodPicker(form);
      });

      monthGrid.addEventListener('click', function (event) {
        var monthBtn = event.target && event.target.closest ? event.target.closest('[data-worktime-period-month]') : null;
        if (!monthBtn) return;
        event.preventDefault();
        var anchorYear = parseInt(form.dataset.worktimePeriodAnchorYear || String(new Date().getFullYear()), 10);
        periodInput.value = anchorYear + '-' + pad2(parseInt(monthBtn.dataset.worktimePeriodMonth, 10));
        syncWorktimePeriodPicker(form);
        hideWorktimePeriodPanel(form);
        submitWorktimeGetForm(form);
      });

      yearGrid.addEventListener('click', function (event) {
        var yearBtn = event.target && event.target.closest ? event.target.closest('[data-worktime-period-year]') : null;
        if (!yearBtn) return;
        event.preventDefault();
        periodInput.value = yearBtn.dataset.worktimePeriodYear;
        form.dataset.worktimePeriodAnchorYear = yearBtn.dataset.worktimePeriodYear;
        syncWorktimePeriodPicker(form);
        hideWorktimePeriodPanel(form);
        submitWorktimeGetForm(form);
      });
    });

    if (!window.__worktimePeriodOutsideBound) {
      window.__worktimePeriodOutsideBound = true;
      document.addEventListener('click', function (event) {
        qa('[data-worktime-period-form]').forEach(function (form) {
          if (!form.contains(event.target)) {
            hideWorktimePeriodPanel(form);
          }
        });
      });
    }
  }

  function initFlatpickrWeekFilter(form, input, toggle, maxWeekStart) {
    if (!window.flatpickr || !form || !input) return false;
    var initialDate = parseIsoDate(input.value) || new Date();
    var fp = window.flatpickr(input, {
      dateFormat: 'Y-m-d',
      defaultDate: initialDate,
      allowInput: false,
      disableMobile: true,
      clickOpens: false,
      locale: flatpickrLocale(),
      positionElement: toggle || input,
      onReady: function (_, __, instance) {
        instance._positionElement = toggle || input;
        instance._worktimeForm = form;
        syncCommittedHeaderState(instance, instance.selectedDates[0] || initialDate);
        ensureWorktimeFlatpickrHeader(instance);
        bindFlatpickrWeekHover(instance);
        updateWeekLabel(form, instance.selectedDates[0] || initialDate);
        highlightSelectedWeek(instance, instance.selectedDates[0]);
        syncWorktimeFlatpickrHeader(instance);
        syncWorktimeFlatpickrWidth(instance);
        syncWorktimeFlatpickrHeight(instance);
      },
      onMonthChange: function (_, __, instance) {
        highlightSelectedWeek(instance, instance.selectedDates[0]);
        if (instance._worktimeTransitioning) return;
        if (!instance.calendarContainer || !instance.calendarContainer.classList.contains('worktime-month-panel-open')) {
          syncCommittedHeaderToVisibleMonth(instance);
        }
        syncWorktimeFlatpickrHeader(instance);
        syncWorktimeFlatpickrHeight(instance);
      },
      onYearChange: function (_, __, instance) {
        highlightSelectedWeek(instance, instance.selectedDates[0]);
        if (instance._worktimeTransitioning) return;
        if (!instance.calendarContainer || !instance.calendarContainer.classList.contains('worktime-month-panel-open')) {
          syncCommittedHeaderToVisibleMonth(instance);
        }
        syncWorktimeFlatpickrHeader(instance);
        syncWorktimeFlatpickrHeight(instance);
      },
      onValueUpdate: function (_, __, instance) {
        highlightSelectedWeek(instance, instance.selectedDates[0]);
        if (instance._worktimeTransitioning) return;
        if (!instance.calendarContainer || !instance.calendarContainer.classList.contains('worktime-month-panel-open')) {
          syncCommittedHeaderState(instance);
        }
        syncWorktimeFlatpickrHeader(instance);
        syncWorktimeFlatpickrHeight(instance);
      },
      onChange: function (selectedDates, __, instance) {
        var selectedDate = selectedDates && selectedDates[0];
        if (!selectedDate) return;
        syncCommittedHeaderState(instance, selectedDate);
        var selectedWeekStart = startOfWeek(selectedDate);
        if (maxWeekStart && selectedWeekStart > maxWeekStart) {
          showWeekError(form.closest('[data-worktime-panel]'), 'Нельзя выбрать слишком далекую будущую неделю. Доступны текущая неделя и только две следующие.');
          var currentValue = form.querySelector('[data-worktime-week-value]');
          var fallbackDate = parseIsoDate(currentValue && currentValue.value) || maxWeekStart;
          instance.setDate(fallbackDate, false, 'Y-m-d');
          syncCommittedHeaderState(instance, fallbackDate);
          syncWorktimeFlatpickrHeader(instance, { skipYearScroll: true });
          highlightSelectedWeek(instance, fallbackDate);
          return;
        }
        hideWeekError(form.closest('[data-worktime-panel]'));
        hideMonthPanel(instance);
        submitWeekSelection(form, selectedDate);
      },
      onOpen: function (_, __, instance) {
        hideWeekError(form.closest('[data-worktime-panel]'));
        ensureWorktimeFlatpickrHeader(instance);
        syncWorktimeFlatpickrHeader(instance);
        syncWorktimeFlatpickrWidth(instance);
        syncWorktimeFlatpickrHeight(instance);
      },
    });
    if (toggle) {
      toggle.addEventListener('click', function () {
        flushVisibleWorktimeAutosave().finally(function () {
          fp.open();
        });
      });
    }
    input.dataset.hasPicker = '1';
    return true;
  }

  function initNativeWeekFilter(form, input, toggle, maxWeekStart) {
    if (!form || !input) return;
    input.type = 'date';
    input.dataset.hasPicker = '1';
    if (toggle) {
      toggle.addEventListener('click', function () {
        if (typeof input.showPicker === 'function') {
          input.showPicker();
        } else {
          input.click();
        }
      });
    }
    input.addEventListener('change', function () {
      var selectedDate = parseIsoDate(input.value);
      if (!selectedDate) return;
      var selectedWeekStart = startOfWeek(selectedDate);
      if (maxWeekStart && selectedWeekStart > maxWeekStart) {
        showWeekError(form.closest('[data-worktime-panel]'), 'Нельзя выбрать слишком далекую будущую неделю. Доступны текущая неделя и только две следующие.');
        var currentValue = form.querySelector('[data-worktime-week-value]');
        if (currentValue) input.value = currentValue.value;
        return;
      }
      hideWeekError(form.closest('[data-worktime-panel]'));
      submitWeekSelection(form, selectedDate);
    });
  }

  function initWeekFilters(root) {
    var forms = qa('[data-worktime-week-form]', root || document);
    if (!forms.length) return;
    if (!window.flatpickr) {
      ensureWorktimeFlatpickr().then(function () {
        initWeekFilters(root || document);
      }).catch(function () {
        forms.forEach(function (form) {
          if (form.dataset.weekPickerBound === '1') return;
          form.dataset.weekPickerBound = '1';
          var input = form.querySelector('[data-worktime-week-input]');
          var toggle = form.querySelector('[data-worktime-week-toggle]');
          var maxWeekStart = parseIsoDate(form.dataset.worktimeWeekMax);
          initNativeWeekFilter(form, input, toggle, maxWeekStart);
        });
      });
      return;
    }
    forms.forEach(function (form) {
      if (form.dataset.weekPickerBound === '1') return;
      form.dataset.weekPickerBound = '1';
      var input = form.querySelector('[data-worktime-week-input]');
      var toggle = form.querySelector('[data-worktime-week-toggle]');
      var maxWeekStart = parseIsoDate(form.dataset.worktimeWeekMax);
      if (!initFlatpickrWeekFilter(form, input, toggle, maxWeekStart)) {
        initNativeWeekFilter(form, input, toggle, maxWeekStart);
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initWeekFilters(document);
    initPeriodFilters(document);
  });

  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (!e.target) return;
    initWeekFilters(e.target);
    initPeriodFilters(e.target);
  });
})();
