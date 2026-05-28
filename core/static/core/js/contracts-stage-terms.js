(function () {
  function attachContractStageTerms(node) {
    const termsTbody = node?.querySelector("#contract-stage-terms-tbody");
    if (!node || !termsTbody || node.dataset.contractStageTermsBound === "1") return;
    node.dataset.contractStageTermsBound = "1";

    let reportTermsEditMode = false;
    const lockIcons = Array.from(node.querySelectorAll(".js-proposal-report-terms-lock"));

    const getStageTermRows = () => Array.from(termsTbody.querySelectorAll(".proposal-stage-terms-row"));
    const getStageDelayRows = () => Array.from(termsTbody.querySelectorAll(".proposal-stage-delay-row"));
    const getTotalsRow = () => termsTbody.querySelector(".proposal-stage-terms-total-row");

    function parseDecimal(value) {
      const raw = String(value || "").trim().replace(/\s+/g, "").replace(",", ".");
      if (!raw) return null;
      const parsed = Number(raw);
      return Number.isFinite(parsed) ? parsed : null;
    }

    function parseInteger(value) {
      const raw = String(value || "").trim().replace(/\s+/g, "");
      if (!raw || !/^[+-]?\d+$/.test(raw)) return null;
      const parsed = Number.parseInt(raw, 10);
      return Number.isFinite(parsed) ? parsed : null;
    }

    function parseDate(value) {
      const raw = String(value || "").trim();
      if (!raw) return null;
      const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (isoMatch) {
        return new Date(Number(isoMatch[1]), Number(isoMatch[2]) - 1, Number(isoMatch[3]));
      }
      const displayMatch = raw.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
      if (displayMatch) {
        return new Date(Number(displayMatch[3]), Number(displayMatch[2]) - 1, Number(displayMatch[1]));
      }
      return null;
    }

    function startOfDay(date) {
      return new Date(date.getFullYear(), date.getMonth(), date.getDate());
    }

    function addDays(date, days) {
      const next = new Date(date.getTime());
      next.setDate(next.getDate() + days);
      return startOfDay(next);
    }

    function addDecimalMonths(date, months) {
      const safeMonths = Number.isFinite(months) ? Math.max(months, 0) : 0;
      const wholeMonths = Math.trunc(safeMonths);
      const fractionalMonths = safeMonths - wholeMonths;
      const baseDate = startOfDay(date);
      const targetMonthStart = new Date(baseDate.getFullYear(), baseDate.getMonth() + wholeMonths, 1);
      const targetMonthEndDay = new Date(targetMonthStart.getFullYear(), targetMonthStart.getMonth() + 1, 0).getDate();
      const day = Math.min(baseDate.getDate(), targetMonthEndDay);
      const wholeDate = new Date(targetMonthStart.getFullYear(), targetMonthStart.getMonth(), day);
      return addDays(wholeDate, Math.round(fractionalMonths * 30));
    }

    function subtractDecimalMonths(date, months) {
      const safeMonths = Number.isFinite(months) ? Math.max(months, 0) : 0;
      const wholeMonths = Math.trunc(safeMonths);
      const fractionalMonths = safeMonths - wholeMonths;
      const fractionalDays = Math.round(fractionalMonths * 30);
      const baseDate = addDays(startOfDay(date), -fractionalDays);
      const targetMonthStart = new Date(baseDate.getFullYear(), baseDate.getMonth() - wholeMonths, 1);
      const targetMonthEndDay = new Date(targetMonthStart.getFullYear(), targetMonthStart.getMonth() + 1, 0).getDate();
      const day = Math.min(baseDate.getDate(), targetMonthEndDay);
      return new Date(targetMonthStart.getFullYear(), targetMonthStart.getMonth(), day);
    }

    function addDecimalWeeks(date, weeks) {
      const safeWeeks = Number.isFinite(weeks) ? Math.max(weeks, 0) : 0;
      return addDays(date, Math.round(safeWeeks * 7));
    }

    function subtractDecimalWeeks(date, weeks) {
      const safeWeeks = Number.isFinite(weeks) ? Math.max(weeks, 0) : 0;
      return addDays(date, -Math.round(safeWeeks * 7));
    }

    function formatDecimal(value) {
      return Number.isFinite(value) ? (Math.round(value * 10) / 10).toFixed(1) : "";
    }

    function formatDateIso(date) {
      const year = String(date.getFullYear()).padStart(4, "0");
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      return `${year}-${month}-${day}`;
    }

    function normalizeDecimalInput(input) {
      if (!input) return null;
      const parsed = parseDecimal(input.value);
      input.value = parsed === null ? "" : formatDecimal(parsed);
      return parsed;
    }

    function normalizeIntegerInput(input) {
      if (!input) return null;
      const parsed = parseInteger(input.value);
      input.value = parsed === null ? "" : String(parsed);
      return parsed;
    }

    function setDateFieldValue(input, isoValue) {
      if (!input) return;
      if (!isoValue) {
        input.value = "";
        if (input._flatpickr) input._flatpickr.clear(false);
        if (window.$ && $.fn && $.fn.datepicker && input.dataset.hasPicker === "1") {
          $(input).datepicker("update", "");
        }
        return;
      }
      const date = parseDate(isoValue);
      if (!date) return;
      if (input._flatpickr) {
        input._flatpickr.setDate(formatDateIso(date), false, "Y-m-d");
        return;
      }
      if (window.$ && $.fn && $.fn.datepicker && input.dataset.hasPicker === "1") {
        const displayValue = `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}.${date.getFullYear()}`;
        $(input).datepicker("update", displayValue);
        return;
      }
      input.value = formatDateIso(date);
    }

    function setReadonly(input, locked, options) {
      if (!input) return;
      input.readOnly = locked;
      input.classList.toggle("readonly-field", locked);
      if (locked) {
        input.setAttribute("readonly", "");
        input.tabIndex = -1;
      } else {
        input.removeAttribute("readonly");
        input.removeAttribute("tabindex");
      }
      if (options?.lockPicker) {
        if (input._flatpickr) input._flatpickr.set("clickOpens", !locked);
        input.style.pointerEvents = locked ? "none" : "";
      }
    }

    function getStageDelayRowForTermRow(row) {
      const nextRow = row?.nextElementSibling;
      return nextRow?.classList?.contains("proposal-stage-delay-row") ? nextRow : null;
    }

    function getDefaultEvaluationDate() {
      const today = new Date();
      const year = today.getFullYear();
      const julyFirst = new Date(year, 6, 1);
      return today < julyFirst ? new Date(year, 0, 1) : new Date(year, 5, 1);
    }

    function getSharedEvaluationDateValue(preferredValue) {
      const preferredDate = parseDate(preferredValue);
      if (preferredDate) return formatDateIso(preferredDate);
      const firstInput = getStageTermRows()[0]?.querySelector(".proposal-stage-evaluation-date");
      const firstDate = parseDate(firstInput?.value) || getDefaultEvaluationDate();
      return formatDateIso(firstDate);
    }

    let isSyncingEvaluationDates = false;

    function syncStageEvaluationDates(preferredValue) {
      if (isSyncingEvaluationDates) return;
      isSyncingEvaluationDates = true;
      const sharedValue = getSharedEvaluationDateValue(preferredValue);
      try {
        getStageTermRows().forEach((row) => {
          const evaluationInput = row.querySelector(".proposal-stage-evaluation-date");
          if (evaluationInput) setDateFieldValue(evaluationInput, sharedValue);
        });
      } finally {
        isSyncingEvaluationDates = false;
      }
    }

    function applyLockState() {
      getStageTermRows().forEach((row) => {
        setReadonly(row.querySelector(".proposal-stage-preliminary-report-date"), reportTermsEditMode, { lockPicker: true });
        setReadonly(row.querySelector(".proposal-stage-final-report-date"), reportTermsEditMode, { lockPicker: true });
        setReadonly(row.querySelector(".proposal-stage-service-term-months"), !reportTermsEditMode);
        setReadonly(row.querySelector(".proposal-stage-final-report-term-weeks"), !reportTermsEditMode);
      });
      lockIcons.forEach((icon) => {
        icon.classList.toggle("bi-lock-fill", !reportTermsEditMode);
        icon.classList.toggle("bi-unlock-fill", reportTermsEditMode);
        icon.title = reportTermsEditMode ? "Заблокировать ввод сроков" : "Разблокировать ввод сроков";
      });
    }

    function syncStageTerms() {
      const termRows = getStageTermRows();
      const states = termRows.map((row) => {
        const monthsInput = row.querySelector(".proposal-stage-service-term-months");
        const weeksInput = row.querySelector(".proposal-stage-final-report-term-weeks");
        const delayInput = getStageDelayRowForTermRow(row)?.querySelector(".proposal-stage-next-delay-days");
        const months = normalizeDecimalInput(monthsInput);
        const weeks = normalizeDecimalInput(weeksInput);
        return {
          row,
          monthsInput,
          weeksInput,
          preliminaryInput: row.querySelector(".proposal-stage-preliminary-report-date"),
          finalInput: row.querySelector(".proposal-stage-final-report-date"),
          evaluationInput: row.querySelector(".proposal-stage-evaluation-date"),
          delayInput,
          months,
          weeks,
          nextDelayDays: parseInteger(delayInput?.value) || 0,
          preliminaryDate: parseDate(row.querySelector(".proposal-stage-preliminary-report-date")?.value),
          finalDate: parseDate(row.querySelector(".proposal-stage-final-report-date")?.value),
          shouldForceDatesFromTerms: row.dataset.forceDatesFromTerms === "1",
          manualDateSource: String(row.dataset.manualDateSource || "").trim(),
          calculatedPreliminaryDate: null,
          calculatedFinalDate: null,
        };
      });

      function applyStateDates(state) {
        setDateFieldValue(
          state.preliminaryInput,
          state.calculatedPreliminaryDate ? formatDateIso(state.calculatedPreliminaryDate) : ""
        );
        setDateFieldValue(
          state.finalInput,
          state.calculatedFinalDate ? formatDateIso(state.calculatedFinalDate) : ""
        );
      }

      function applyNextStageDelay(date, state) {
        if (!date) return date;
        return state.nextDelayDays ? addDays(date, state.nextDelayDays) : date;
      }

      function computeForwardDates(startDate, state) {
        if (state.months === null) {
          state.calculatedPreliminaryDate = null;
          state.calculatedFinalDate = null;
          return applyNextStageDelay(startDate, state);
        }
        state.calculatedPreliminaryDate = addDecimalMonths(startDate, state.months);
        if (state.weeks === null) {
          state.calculatedFinalDate = null;
          return applyNextStageDelay(state.calculatedPreliminaryDate, state);
        }
        state.calculatedFinalDate = addDecimalWeeks(state.calculatedPreliminaryDate, state.weeks);
        return applyNextStageDelay(state.calculatedFinalDate, state);
      }

      if (reportTermsEditMode) {
        let startDate = parseDate(getSharedEvaluationDateValue());
        states.forEach((state) => {
          startDate = computeForwardDates(startDate, state);
          applyStateDates(state);
          delete state.row.dataset.forceDatesFromTerms;
          delete state.row.dataset.manualDateSource;
        });
      } else {
        let baseStartDate = parseDate(getSharedEvaluationDateValue());
        const manualIndex = states.findIndex((state) => {
          if (state.manualDateSource === "preliminary") return !!state.preliminaryDate && state.months !== null;
          if (state.manualDateSource === "final") return !!state.finalDate && state.weeks !== null;
          return false;
        });

        if (manualIndex >= 0) {
          const manualState = states[manualIndex];
          let manualStageStartDate = null;
          if (manualState.manualDateSource === "preliminary") {
            manualState.calculatedPreliminaryDate = manualState.preliminaryDate;
            manualState.calculatedFinalDate = manualState.weeks !== null
              ? addDecimalWeeks(manualState.preliminaryDate, manualState.weeks)
              : null;
            manualStageStartDate = manualState.preliminaryDate && manualState.months !== null
              ? subtractDecimalMonths(manualState.preliminaryDate, manualState.months)
              : null;
          } else {
            manualState.calculatedFinalDate = manualState.finalDate;
            manualState.calculatedPreliminaryDate = manualState.weeks !== null
              ? subtractDecimalWeeks(manualState.finalDate, manualState.weeks)
              : null;
            manualStageStartDate = manualState.calculatedPreliminaryDate && manualState.months !== null
              ? subtractDecimalMonths(manualState.calculatedPreliminaryDate, manualState.months)
              : null;
          }

          let rollingStartDate = manualStageStartDate;
          for (let index = manualIndex - 1; index >= 0; index -= 1) {
            const state = states[index];
            const stageEndDate = rollingStartDate && state.nextDelayDays
              ? addDays(rollingStartDate, -state.nextDelayDays)
              : rollingStartDate;
            state.calculatedFinalDate = stageEndDate;
            state.calculatedPreliminaryDate = stageEndDate && state.weeks !== null
              ? subtractDecimalWeeks(stageEndDate, state.weeks)
              : null;
            rollingStartDate = state.calculatedPreliminaryDate && state.months !== null
              ? subtractDecimalMonths(state.calculatedPreliminaryDate, state.months)
              : rollingStartDate;
          }

          if (rollingStartDate) baseStartDate = rollingStartDate;

          let forwardStartDate = applyNextStageDelay(
            manualState.calculatedFinalDate || manualState.calculatedPreliminaryDate || manualStageStartDate || baseStartDate,
            manualState
          );
          for (let index = manualIndex + 1; index < states.length; index += 1) {
            forwardStartDate = computeForwardDates(forwardStartDate, states[index]);
          }
          states.forEach(applyStateDates);
        } else {
          let startDate = baseStartDate;
          states.forEach((state) => {
            const shouldComputeFromTerms = state.shouldForceDatesFromTerms || (!state.preliminaryDate && !state.finalDate);
            if (shouldComputeFromTerms) {
              startDate = computeForwardDates(startDate, state);
              applyStateDates(state);
            } else {
              startDate = applyNextStageDelay(state.finalDate || state.preliminaryDate || startDate, state);
            }
          });
        }

        states.forEach((state) => {
          delete state.row.dataset.forceDatesFromTerms;
          delete state.row.dataset.manualDateSource;
        });
      }

      const totalsRow = getTotalsRow();
      if (!totalsRow) return;
      const totalMonths = termRows.reduce((sum, row) => {
        return sum + (parseDecimal(row.querySelector(".proposal-stage-service-term-months")?.value) || 0);
      }, 0);
      const totalWeeks = termRows.reduce((sum, row) => {
        return sum + (parseDecimal(row.querySelector(".proposal-stage-final-report-term-weeks")?.value) || 0);
      }, 0);
      const totalMonthsInput = totalsRow.querySelector(".proposal-stage-total-service-term-months");
      const totalWeeksInput = totalsRow.querySelector(".proposal-stage-total-final-report-term-weeks");
      if (totalMonthsInput) totalMonthsInput.value = termRows.length > 1 ? formatDecimal(totalMonths) : "";
      if (totalWeeksInput) totalWeeksInput.value = termRows.length > 1 ? formatDecimal(totalWeeks) : "";
      totalsRow.classList.toggle("d-none", termRows.length <= 1);
    }

    function bindTermsRows() {
      getStageTermRows().forEach((row) => {
        if (row.dataset.eventsBound === "1") return;
        row.dataset.eventsBound = "1";
        if (typeof window.initDatepickers === "function") {
          window.initDatepickers(row);
        }
        const monthsInput = row.querySelector(".proposal-stage-service-term-months");
        const weeksInput = row.querySelector(".proposal-stage-final-report-term-weeks");
        normalizeDecimalInput(monthsInput);
        normalizeDecimalInput(weeksInput);
        ["input", "change"].forEach((eventName) => {
          row.querySelector(".proposal-stage-evaluation-date")?.addEventListener(eventName, () => {
            syncStageEvaluationDates(row.querySelector(".proposal-stage-evaluation-date")?.value || "");
            getStageTermRows().forEach((item) => {
              item.dataset.forceDatesFromTerms = "1";
            });
            syncStageTerms();
          });
          monthsInput?.addEventListener(eventName, () => {
            row.dataset.forceDatesFromTerms = "1";
            syncStageTerms();
            if (eventName === "change") normalizeDecimalInput(monthsInput);
          });
          weeksInput?.addEventListener(eventName, () => {
            row.dataset.forceDatesFromTerms = "1";
            syncStageTerms();
            if (eventName === "change") normalizeDecimalInput(weeksInput);
          });
          row.querySelector(".proposal-stage-preliminary-report-date")?.addEventListener(eventName, () => {
            if (!reportTermsEditMode) {
              row.dataset.manualDateSource = "preliminary";
              syncStageTerms();
            }
          });
          row.querySelector(".proposal-stage-final-report-date")?.addEventListener(eventName, () => {
            if (!reportTermsEditMode) {
              row.dataset.manualDateSource = "final";
              syncStageTerms();
            }
          });
        });
      });
    }

    function bindStageDelayRows() {
      getStageDelayRows().forEach((row) => {
        if (row.dataset.eventsBound === "1") return;
        row.dataset.eventsBound = "1";
        const input = row.querySelector(".proposal-stage-next-delay-days");
        ["input", "change"].forEach((eventName) => {
          input?.addEventListener(eventName, () => {
            if (eventName === "change") normalizeIntegerInput(input);
            const termRows = getStageTermRows();
            const sourceIndex = termRows.indexOf(row.previousElementSibling);
            if (sourceIndex >= 0) {
              termRows.slice(sourceIndex + 1).forEach((termRow) => {
                termRow.dataset.forceDatesFromTerms = "1";
              });
            }
            syncStageTerms();
          });
        });
      });
    }

    lockIcons.forEach((icon) => {
      icon.addEventListener("click", () => {
        reportTermsEditMode = !reportTermsEditMode;
        applyLockState();
        getStageTermRows().forEach((row) => {
          row.dataset.forceDatesFromTerms = "1";
        });
        syncStageTerms();
      });
    });

    termsTbody.addEventListener("click", (event) => {
      const removeButton = event.target.closest(".proposal-stage-delay-remove");
      if (removeButton) {
        const delayRow = removeButton.closest(".proposal-stage-delay-row");
        const delayInput = delayRow?.querySelector(".proposal-stage-next-delay-days");
        if (!delayRow || !delayInput) return;
        delayInput.value = "0";
        delayRow.classList.add("d-none");
        const termRows = getStageTermRows();
        const sourceIndex = termRows.indexOf(delayRow.previousElementSibling);
        if (sourceIndex >= 0) {
          termRows.slice(sourceIndex + 1).forEach((termRow) => {
            termRow.dataset.forceDatesFromTerms = "1";
          });
        }
        syncStageTerms();
        return;
      }

      const addButton = event.target.closest(".proposal-stage-delay-add");
      if (!addButton) return;
      const termRow = addButton.closest(".proposal-stage-terms-row");
      if (!termRow) return;
      let delayRow = getStageDelayRowForTermRow(termRow);
      if (!delayRow) return;
      delayRow.classList.remove("d-none");
      bindStageDelayRows();
      const termRows = getStageTermRows();
      const sourceIndex = termRows.indexOf(termRow);
      if (sourceIndex >= 0) {
        termRows.slice(sourceIndex + 1).forEach((item) => {
          item.dataset.forceDatesFromTerms = "1";
        });
      }
      syncStageTerms();
      delayRow.querySelector(".proposal-stage-next-delay-days")?.focus();
    });

    node.__contractStageTermsApi = {
      sync() {
        bindTermsRows();
        bindStageDelayRows();
        applyLockState();
        syncStageTerms();
      },
    };

    bindTermsRows();
    bindStageDelayRows();
    applyLockState();
    syncStageTerms();
  }

  window.attachContractStageTerms = attachContractStageTerms;
})();
