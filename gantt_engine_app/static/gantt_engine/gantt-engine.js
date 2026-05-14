// Internal Gantt engine API.
//
// The vendored DHTMLX Gantt build (dhtmlxgantt.js) was patched at the very end
// to expose a factory (`base(extensions)`-style) alongside its legacy
// `window.gantt` singleton. Every section of the application that needs a
// Gantt chart should acquire its OWN independent instance via
// `GanttEngine.create()` and operate on that instance — there is no longer
// any shared "owner" arbitration.
//
// Public API:
//   GanttEngine.create()                         -> a fresh Gantt instance, or null if engine missing
//   GanttEngine.dispose(instance)                -> safely destroy an instance
//   GanttEngine.classesForMilestoneKind(task)    -> CSS classes for special
//                                                   milestone visuals shared
//                                                   across all instances
//   GanttEngine.captureCalendarTransitionBaseline(instance, options)
//                                                 -> capture task durations plus
//                                                    deadline/constraint offsets
//   GanttEngine.applyCalendarTransitionSchedule(instance, baseline, options)
//                                                 -> replay the captured offsets
//                                                    after a calendar switch
//   GanttEngine.applyTimelineRange(instance, options)
//                                                 -> apply shared visible
//                                                    timeline padding rules
//   GanttEngine.shouldShowTaskLabel(instance, start, end, task, options)
//                                                 -> shared scale-aware bar
//                                                    label visibility rule
//   GanttEngine.getTaskLabelVisibility(instance, start, end, task, options)
//                                                 -> shared visibility for
//                                                    label text/accessories
//   GanttEngine.createResources(options)          -> optional resources table
//                                                   extension, registered by
//                                                   gantt-resources.js
//
// The `classesForMilestoneKind` helper used to live in the (now removed)
// `gantt-host.js`. Visuals are owned by globally-scoped `.gantt-mk-*` rules in
// site.css, so any section that wants the shared "payment" diamond look just
// returns this string from its `gantt.templates.task_class`.

(function (window) {
  'use strict';

  if (window.GanttEngine && typeof window.GanttEngine.create === 'function'
      && typeof window.GanttEngine.dispose === 'function'
      && typeof window.GanttEngine.classesForMilestoneKind === 'function'
      && typeof window.GanttEngine.captureCalendarTransitionBaseline === 'function'
      && typeof window.GanttEngine.applyCalendarTransitionSchedule === 'function'
      && typeof window.GanttEngine.applyTimelineRange === 'function'
      && typeof window.GanttEngine.shouldShowTaskLabel === 'function'
      && typeof window.GanttEngine.getTaskLabelVisibility === 'function') {
    return;
  }

  var vendor = window.GanttEngine || null;

  function create() {
    if (!vendor || typeof vendor.create !== 'function') return null;
    try {
      return vendor.create();
    } catch (err) {
      try { console.error('[GanttEngine] create failed:', err); } catch (_) {}
      return null;
    }
  }

  // Soft "dispose" of a Gantt instance.
  //
  // We deliberately DO NOT call `instance.destructor()` here. The destructor
  // nulls out `$services` and other internals — but many call sites in the
  // application hold a reference to the Gantt in a closure (column-resize
  // drag handlers, document-level mousemove listeners during an in-flight
  // drag, htmx-driven re-renders that complete after a swap has detached the
  // chart, etc.). If we destruct the instance under those closures, the next
  // call to `gantt.render()` / `gantt.setSizes()` from inside the closure
  // crashes with `Cannot read properties of undefined (reading 'getService')`.
  //
  // Instead we:
  //   1. clear tasks/links (free task data and let DHTMLX's own onDataRender
  //      cycles settle on an empty store);
  //   2. fire `onDestroy` so anything that registered via
  //      `gantt.attachEvent('onDestroy', ...)` gets a chance to tear itself
  //      down — this stops the vendored skin-detection `setInterval` and
  //      other timers WITHOUT nulling `$services`;
  //   3. swap render-related methods (`render`, `setSizes`, `refreshData`,
  //      `refreshTask`, `refreshLink`) with no-ops so any stale closure that
  //      tries to render a frame on this orphaned instance gracefully does
  //      nothing instead of throwing from inside DHTMLX internals;
  //   4. mark the instance as disposed for any consumer that wants to test
  //      for it explicitly (`instance.$gantt_engine_disposed === true`).
  //
  // The instance itself is then garbage-collected once nothing holds a
  // reference to it (closures, DOM listeners, etc.) — usually right after
  // the next `mouseup` or htmx swap cycle.
  function dispose(instance) {
    if (!instance) return;
    try {
      if (typeof instance.hideLightbox === 'function') instance.hideLightbox();
    } catch (_) {}
    try {
      if (typeof instance.clearAll === 'function') instance.clearAll();
    } catch (err) {
      try { console.error('[GanttEngine] dispose clearAll failed:', err); } catch (_) {}
    }
    try {
      if (typeof instance.callEvent === 'function') instance.callEvent('onDestroy', []);
    } catch (_) {}
    var noop = function () { /* gantt-engine: disposed, no-op */ };
    try {
      instance.render = noop;
      instance.setSizes = noop;
      instance.refreshData = noop;
      instance.refreshTask = noop;
      instance.refreshLink = noop;
    } catch (_) {}
    try { instance.$gantt_engine_disposed = true; } catch (_) {}
  }

  // Supported kinds:
  //   payment  green diamond + halo (uses task.payment_percent /
  //            task.is_zero_payment to drive the modifier classes)
  function classesForMilestoneKind(task) {
    if (!task || task.type !== 'milestone' || !task.milestone_kind) return '';
    switch (task.milestone_kind) {
      case 'payment':
        return 'gantt-mk-payment' + (task.is_zero_payment ? ' gantt-mk-payment-zero' : '');
      default:
        return '';
    }
  }

  function dateOnly(value) {
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return new Date(value.getFullYear(), value.getMonth(), value.getDate());
    }
    if (typeof value === 'string') {
      var iso = value.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
      if (iso) return new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));
      var dotted = value.match(/^(\d{1,2})\.(\d{1,2})\.(\d{2,4})/);
      if (dotted) {
        var year = Number(dotted[3]);
        if (year < 100) year += 2000;
        return new Date(year, Number(dotted[2]) - 1, Number(dotted[1]));
      }
    }
    return null;
  }

  function addDays(date, days) {
    var next = dateOnly(date);
    if (!next) return null;
    next.setDate(next.getDate() + Math.round(Number(days) || 0));
    return next;
  }

  function scaleUnitStart(date, scale) {
    var out = dateOnly(date);
    if (!out) return null;
    if (scale === 'quarter') {
      out.setMonth(Math.floor(out.getMonth() / 3) * 3, 1);
    } else if (scale === 'month') {
      out.setDate(1);
    } else if (scale === 'week') {
      var monIdx = (out.getDay() + 6) % 7;
      out.setDate(out.getDate() - monIdx);
    }
    return out;
  }

  function scaleUnitEnd(date, scale) {
    var out = dateOnly(date);
    if (!out) return null;
    if (scale === 'quarter') {
      out.setMonth(Math.floor(out.getMonth() / 3) * 3 + 3, 1);
    } else if (scale === 'month') {
      out.setMonth(out.getMonth() + 1, 1);
    } else if (scale === 'week') {
      var monIdx = (out.getDay() + 6) % 7;
      out.setDate(out.getDate() - monIdx + 7);
    } else {
      out.setDate(out.getDate() + 1);
    }
    return out;
  }

  function addScaleUnit(date, scale, direction) {
    var next = dateOnly(date);
    if (!next) return null;
    var multiplier = direction < 0 ? -1 : 1;
    if (scale === 'week') {
      next.setDate(next.getDate() + (7 * multiplier));
    } else if (scale === 'month') {
      next.setMonth(next.getMonth() + multiplier);
    } else if (scale === 'quarter') {
      next.setMonth(next.getMonth() + (3 * multiplier));
    } else {
      next.setDate(next.getDate() + multiplier);
    }
    return next;
  }

  function addVisiblePaddingDate(gantt, date, days, direction, task) {
    var source = dateOnly(date);
    if (!source) return null;
    var safeDays = Math.max(1, Math.round(Number(days) || 1));
    if (gantt && gantt.config && gantt.config.work_time && gantt.config.skip_off_time) {
      var calculated = direction < 0
        ? calculateStartDate(gantt, source, safeDays, task)
        : calculateEndDate(gantt, source, safeDays, task);
      if (calculated) return calculated;
    }
    return addDays(source, direction < 0 ? -safeDays : safeDays);
  }

  function scaleRangePaddingDate(gantt, date, scale, direction, options) {
    var source = dateOnly(date);
    if (!source) return null;
    if (scale === 'day') return addVisiblePaddingDate(gantt, source, 1, direction, options && options.paddingTask);
    if (scale === 'week') return addVisiblePaddingDate(gantt, source, 7, direction, options && options.paddingTask);

    var unitStart = scaleUnitStart(source, scale);
    var unitEnd = scaleUnitEnd(source, scale);
    if (!unitStart || !unitEnd || unitEnd <= unitStart) return source;

    var unitDays = (unitEnd.getTime() - unitStart.getTime()) / 86400000;
    var fractions = Object.assign({ month: 0.5, quarter: 0.125 }, options && options.paddingFractions || {});
    var minGapDays = unitDays * (Number(fractions[scale]) || 0);
    var paddingDays = Math.max(1, Math.floor(minGapDays));
    return addVisiblePaddingDate(gantt, source, paddingDays, direction, options && options.paddingTask);
  }

  function collectTaskDateRange(gantt, tasks) {
    var starts = [];
    var ends = [];
    var collect = function (task) {
      var start = dateOnly(task && task.start_date);
      var end = dateOnly(task && task.end_date);
      if (start) starts.push(start);
      if (end) ends.push(end);
    };
    if (Array.isArray(tasks)) {
      tasks.forEach(collect);
    } else if (gantt && typeof gantt.eachTask === 'function') {
      try { gantt.eachTask(collect); } catch (_) {}
    }
    return {
      start: starts.length ? new Date(Math.min.apply(null, starts.map(function (date) { return date.getTime(); }))) : null,
      end: ends.length ? new Date(Math.max.apply(null, ends.map(function (date) { return date.getTime(); }))) : null,
    };
  }

  function applyTimelineRange(gantt, options) {
    if (!gantt) return { start: null, end: null };
    var opts = options || {};
    var scale = String(opts.scale || 'week');
    var taskRange = opts.taskRange || collectTaskDateRange(gantt, opts.tasks);
    var fallbackStart = dateOnly(opts.fallbackStart || opts.projectStart);
    var fallbackEnd = dateOnly(opts.fallbackEnd || opts.projectEnd);
    var explicitStart = dateOnly(opts.rangeStart);
    var explicitEnd = dateOnly(opts.rangeEnd);
    var rangeStart = explicitStart || [taskRange.start, fallbackStart]
      .filter(Boolean)
      .sort(function (left, right) { return left - right; })[0] || null;
    var rangeEnd = explicitEnd || [taskRange.end, fallbackEnd]
      .filter(Boolean)
      .sort(function (left, right) { return right - left; })[0] || null;
    var paddedStart = rangeStart ? scaleRangePaddingDate(gantt, rangeStart, scale, -1, opts) : null;
    var paddedEnd = rangeEnd ? scaleRangePaddingDate(gantt, rangeEnd, scale, 1, opts) : null;
    var visibleStart = paddedStart || null;
    var visibleEnd = paddedEnd || null;
    if (visibleStart) gantt.config.start_date = visibleStart;
    else delete gantt.config.start_date;
    if (visibleEnd) gantt.config.end_date = visibleEnd;
    else delete gantt.config.end_date;
    return { start: visibleStart, end: visibleEnd, rangeStart: rangeStart, rangeEnd: rangeEnd };
  }

  function taskCalendarDurationDays(startDate, endDate, task) {
    var start = dateOnly(startDate || (task && task.start_date));
    var end = dateOnly(endDate || (task && task.end_date));
    if (start && end) return Math.max(0, (end.getTime() - start.getTime()) / 86400000);
    var duration = Number(task && task.duration);
    return Number.isFinite(duration) ? Math.max(0, duration) : 0;
  }

  function shouldShowTaskLabel(gantt, startDate, endDate, task, options) {
    var opts = options || {};
    var thresholds = Object.assign({
      day: 5,
      week: 7,
      month: 21,
      quarter: 35,
    }, opts.thresholds || {});
    var scale = opts.scale;
    if (!scale && gantt && gantt.config) scale = gantt.config.$ganttEngineScale || gantt.config.scale_unit;
    scale = String(scale || '');
    var threshold = Number(thresholds[scale]) || 0;
    if (threshold <= 0) return true;
    return taskCalendarDurationDays(startDate, endDate, task) >= threshold;
  }

  function getTaskLabelVisibility(gantt, startDate, endDate, task, options) {
    var opts = options || {};
    return {
      text: shouldShowTaskLabel(gantt, startDate, endDate, task, opts),
      parentLock: isSummaryTask(gantt, task, opts),
    };
  }

  function isMilestone(gantt, task) {
    if (!task) return false;
    var milestoneType = gantt && gantt.config && gantt.config.types
      ? gantt.config.types.milestone
      : 'milestone';
    return String(task.type) === String(milestoneType);
  }

  function isSummaryTask(gantt, task, options) {
    if (!task) return false;
    if (options && typeof options.isSummaryTask === 'function') {
      return !!options.isSummaryTask(gantt, task);
    }
    return !!(typeof gantt?.hasChild === 'function' && gantt.hasChild(task.id));
  }

  function calculateDuration(gantt, startDate, endDate, task) {
    if (!(startDate instanceof Date) || !(endDate instanceof Date)) return 0;
    if (typeof gantt?.calculateDuration === 'function') {
      return Math.max(0, Math.round(Number(gantt.calculateDuration({
        start_date: startDate,
        end_date: endDate,
        task: task,
      })) || 0));
    }
    return Math.max(0, Math.round((endDate.getTime() - startDate.getTime()) / 86400000));
  }

  function calculateEndDate(gantt, startDate, duration, task) {
    if (!(startDate instanceof Date)) return null;
    var safeDuration = Math.round(Number(duration) || 0);
    if (typeof gantt?.calculateEndDate === 'function') {
      return dateOnly(gantt.calculateEndDate({ start_date: startDate, duration: safeDuration, task: task }));
    }
    return addDays(startDate, safeDuration);
  }

  function calculateStartDate(gantt, endDate, duration, task) {
    if (!(endDate instanceof Date)) return null;
    var safeDuration = Math.max(0, Math.round(Number(duration) || 0));
    if (typeof gantt?.calculateEndDate === 'function') {
      return dateOnly(gantt.calculateEndDate({ start_date: endDate, duration: -safeDuration, task: task }));
    }
    return addDays(endDate, -safeDuration);
  }

  function signedWorkingOffset(gantt, fromDate, toDate, task) {
    var from = dateOnly(fromDate);
    var to = dateOnly(toDate);
    if (!from || !to) return null;
    if (from.valueOf() === to.valueOf()) return 0;
    if (to > from) return calculateDuration(gantt, from, to, task);
    return -calculateDuration(gantt, to, from, task);
  }

  function dateFromWorkingOffset(gantt, anchorDate, offset, task) {
    var anchor = dateOnly(anchorDate);
    if (!anchor) return null;
    var safeOffset = Math.round(Number(offset) || 0);
    if (!safeOffset) return anchor;
    return calculateEndDate(gantt, anchor, safeOffset, task);
  }

  function getTaskDuration(gantt, task) {
    if (!task) return 0;
    if (isMilestone(gantt, task)) return 0;
    var start = dateOnly(task.start_date);
    var end = dateOnly(task.end_date);
    if (start && end) return calculateDuration(gantt, start, end, task);
    return Math.max(0, Math.round(Number(task.duration) || 0));
  }

  function getPreservedDuration(baseline, task) {
    if (!baseline || !task) return Math.max(0, Math.round(Number(task?.duration) || 0));
    var value = baseline.durations && baseline.durations[String(task.id)];
    return Math.max(0, Math.round(Number(value) || 0));
  }

  function normalizeLag(value) {
    var lag = Number(String(value ?? '').replace(',', '.'));
    return Number.isFinite(lag) ? Math.round(lag) : 0;
  }

  function normalizeLagMode(value) {
    return String(value || '').toLowerCase() === 'auto' ? 'auto' : 'fixed';
  }

  function normalizeConstraintType(value) {
    var raw = String(value || '').trim().toLowerCase();
    var allowed = {
      asap: true,
      alap: true,
      snet: true,
      snlt: true,
      fnet: true,
      fnlt: true,
      mso: true,
      mfo: true,
    };
    return allowed[raw] ? raw : '';
  }

  function getConstraintAnchor(type) {
    if (type === 'snet' || type === 'snlt' || type === 'mso') return 'start';
    if (type === 'fnet' || type === 'fnlt' || type === 'mfo') return 'end';
    return '';
  }

  function getAnchorDate(task, anchor) {
    return anchor === 'start' ? dateOnly(task?.start_date) : dateOnly(task?.end_date);
  }

  function captureRelativeDates(gantt, task) {
    var captured = {};
    var deadline = dateOnly(task.deadline);
    var deadlineAnchor = getAnchorDate(task, 'end');
    if (deadline && deadlineAnchor) {
      var deadlineOffset = signedWorkingOffset(gantt, deadlineAnchor, deadline, task);
      if (deadlineOffset !== null) {
        captured.deadline = { anchor: 'end', offset: deadlineOffset };
      }
    }

    var constraintType = normalizeConstraintType(task.constraint_type);
    var constraintDate = dateOnly(task.constraint_date);
    var constraintAnchorName = getConstraintAnchor(constraintType);
    var constraintAnchor = constraintAnchorName ? getAnchorDate(task, constraintAnchorName) : null;
    if (constraintType && constraintDate && constraintAnchor) {
      var constraintOffset = signedWorkingOffset(gantt, constraintAnchor, constraintDate, task);
      if (constraintOffset !== null) {
        captured.constraint = {
          type: constraintType,
          anchor: constraintAnchorName,
          offset: constraintOffset,
        };
      }
    }

    return captured.deadline || captured.constraint ? captured : null;
  }

  function captureCalendarTransitionBaseline(gantt, options) {
    if (!gantt || typeof gantt.eachTask !== 'function') return null;
    var opts = options || {};
    var durations = {};
    var relativeDates = {};
    gantt.eachTask(function (task) {
      if (!task || task.id === undefined || task.id === null) return;
      if (isSummaryTask(gantt, task, opts)) return;
      var duration = Number(task.duration);
      if (!Number.isFinite(duration)) duration = getTaskDuration(gantt, task);
      durations[String(task.id)] = Math.max(0, Math.round(Number(duration) || 0));
      var captured = captureRelativeDates(gantt, task);
      if (captured) relativeDates[String(task.id)] = captured;
    });
    return { durations: durations, relativeDates: relativeDates };
  }

  function getNextWorkingDate(gantt, date, task, options) {
    if (options && typeof options.getNextWorkingDate === 'function') {
      var fromConsumer = dateOnly(options.getNextWorkingDate(date, gantt, task));
      if (fromConsumer) return fromConsumer;
    }
    var cursor = dateOnly(date);
    if (!cursor) return null;
    if (typeof gantt?.isWorkTime !== 'function') return cursor;
    var safety = 0;
    while (safety < 3700) {
      var working = true;
      try {
        working = !!gantt.isWorkTime({ date: cursor, task: task });
      } catch (_) {
        try {
          working = !!gantt.isWorkTime(cursor);
        } catch (_) {
          working = true;
        }
      }
      if (working) return cursor;
      cursor = addDays(cursor, 1);
      safety += 1;
    }
    return cursor;
  }

  function setTaskStartWithDuration(gantt, task, nextStart, duration, snapStart, options) {
    if (!task) return false;
    var startDate = snapStart === false
      ? dateOnly(nextStart)
      : getNextWorkingDate(gantt, nextStart, task, options);
    if (!startDate) return false;
    var safeDuration = isMilestone(gantt, task) ? 0 : Math.max(0, Math.round(Number(duration) || 0));
    var nextEnd = isMilestone(gantt, task)
      ? new Date(startDate)
      : calculateEndDate(gantt, startDate, safeDuration, task);
    if (!nextEnd) return false;
    var changed =
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

  function setTaskEndWithDuration(gantt, task, nextEnd, duration) {
    if (!task) return false;
    var endDate = dateOnly(nextEnd);
    if (!endDate) return false;
    var safeDuration = isMilestone(gantt, task) ? 0 : Math.max(0, Math.round(Number(duration) || 0));
    var nextStart = isMilestone(gantt, task)
      ? new Date(endDate)
      : calculateStartDate(gantt, endDate, safeDuration, task);
    if (!nextStart) return false;
    var changed =
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

  function rememberChanged(changedTaskIds, taskId) {
    if (changedTaskIds.indexOf(taskId) === -1) changedTaskIds.push(taskId);
  }

  function applyRelativeDates(gantt, baseline, changedTaskIds) {
    var relativeDates = baseline && baseline.relativeDates ? baseline.relativeDates : {};
    Object.keys(relativeDates).forEach(function (id) {
      var task = null;
      try {
        task = typeof gantt.getTask === 'function' ? gantt.getTask(id) : null;
      } catch (_) {
        task = null;
      }
      if (!task) return;
      var captured = relativeDates[id];
      if (captured.deadline) {
        var deadlineAnchor = getAnchorDate(task, captured.deadline.anchor);
        var nextDeadline = dateFromWorkingOffset(gantt, deadlineAnchor, captured.deadline.offset, task);
        if (nextDeadline && (!(task.deadline instanceof Date) || task.deadline.valueOf() !== nextDeadline.valueOf())) {
          task.deadline = nextDeadline;
          rememberChanged(changedTaskIds, task.id);
        }
      }
      if (captured.constraint) {
        var constraintType = normalizeConstraintType(task.constraint_type) || captured.constraint.type;
        var constraintAnchor = getAnchorDate(task, captured.constraint.anchor);
        var nextConstraintDate = dateFromWorkingOffset(gantt, constraintAnchor, captured.constraint.offset, task);
        if (constraintType && nextConstraintDate) {
          task.constraint_type = constraintType;
          if (!(task.constraint_date instanceof Date) || task.constraint_date.valueOf() !== nextConstraintDate.valueOf()) {
            task.constraint_date = nextConstraintDate;
            rememberChanged(changedTaskIds, task.id);
          }
        }
      }
    });
  }

  function applyCalendarTransitionSchedule(gantt, baseline, options) {
    if (!gantt || !baseline || typeof gantt.eachTask !== 'function') return false;
    var opts = options || {};
    var links = typeof gantt.getLinks === 'function' ? (gantt.getLinks() || []) : [];
    var types = gantt.config?.links || { finish_to_start: '0', start_to_start: '1', finish_to_finish: '2', start_to_finish: '3' };
    var fixedLinks = links.filter(function (link) {
      return normalizeLagMode(link?.lag_mode) === 'fixed';
    });
    var incomingFixed = {};
    fixedLinks.forEach(function (link) {
      var targetId = String(link?.target ?? '');
      if (targetId) incomingFixed[targetId] = true;
    });

    var changedTaskIds = [];
    var canMoveTask = function (task) {
      return !!task && !isSummaryTask(gantt, task, opts);
    };

    var apply = function () {
      gantt.eachTask(function (task) {
        if (!canMoveTask(task) || incomingFixed[String(task.id)]) return;
        var taskStart = dateOnly(task.start_date);
        if (!taskStart) return;
        var duration = getPreservedDuration(baseline, task);
        if (setTaskStartWithDuration(gantt, task, taskStart, duration, true, opts)) {
          rememberChanged(changedTaskIds, task.id);
        }
      });

      var maxPasses = Math.max(fixedLinks.length + 1, 2);
      for (var pass = 0; pass < maxPasses; pass += 1) {
        var changedInPass = false;
        fixedLinks.forEach(function (link) {
          var source;
          var target;
          try {
            source = typeof gantt.getTask === 'function' ? gantt.getTask(link.source) : null;
            target = typeof gantt.getTask === 'function' ? gantt.getTask(link.target) : null;
          } catch (_) {
            source = null;
            target = null;
          }
          if (!source || !target || !canMoveTask(target)) return;
          var sourceStart = dateOnly(source.start_date);
          var sourceEnd = dateOnly(source.end_date);
          var targetStart = dateOnly(target.start_date);
          var targetEnd = dateOnly(target.end_date);
          if (!sourceStart || !sourceEnd || !targetStart || !targetEnd) return;
          var linkType = String(link.type);
          var lag = normalizeLag(link.lag);
          var duration = getPreservedDuration(baseline, target);
          var changed = false;
          if (linkType === String(types.start_to_start)) {
            changed = setTaskStartWithDuration(gantt, target, addDays(sourceStart, lag), duration, false, opts);
          } else if (linkType === String(types.finish_to_finish)) {
            changed = setTaskEndWithDuration(gantt, target, addDays(sourceEnd, lag), duration);
          } else if (linkType === String(types.start_to_finish)) {
            changed = setTaskEndWithDuration(gantt, target, addDays(sourceStart, lag), duration);
          } else {
            changed = setTaskStartWithDuration(gantt, target, addDays(sourceEnd, lag), duration, false, opts);
          }
          if (changed) {
            changedInPass = true;
            rememberChanged(changedTaskIds, target.id);
          }
        });
        if (!changedInPass) break;
      }

      if (typeof opts.parentRollup === 'function') opts.parentRollup(gantt);
      applyRelativeDates(gantt, baseline, changedTaskIds);
      changedTaskIds.forEach(function (id) {
        if (typeof gantt.isTaskExists === 'function' && !gantt.isTaskExists(id)) return;
        if (typeof gantt.updateTask === 'function') gantt.updateTask(id);
      });
    };

    var schedulingFlag = opts.schedulingFlag || null;
    var wasSchedulingActive;
    if (schedulingFlag) {
      wasSchedulingActive = gantt[schedulingFlag];
      gantt[schedulingFlag] = true;
    }
    try {
      if (typeof gantt.batchUpdate === 'function') {
        gantt.batchUpdate(apply);
      } else {
        apply();
      }
    } finally {
      if (schedulingFlag) gantt[schedulingFlag] = wasSchedulingActive;
    }
    return changedTaskIds.length > 0;
  }

  window.GanttEngine = {
    create: create,
    dispose: dispose,
    classesForMilestoneKind: classesForMilestoneKind,
    captureCalendarTransitionBaseline: captureCalendarTransitionBaseline,
    applyCalendarTransitionSchedule: applyCalendarTransitionSchedule,
    applyTimelineRange: applyTimelineRange,
    shouldShowTaskLabel: shouldShowTaskLabel,
    getTaskLabelVisibility: getTaskLabelVisibility,
    createResources: vendor && typeof vendor.createResources === 'function' ? vendor.createResources : undefined,
    gantt: vendor && vendor.gantt ? vendor.gantt : (window.gantt || null),
    version: vendor && vendor.version ? vendor.version : 'unknown',
  };
})(window);
