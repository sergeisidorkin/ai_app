(function () {
  function attachContractStageTerms(node) {
    const termsTbody = node?.querySelector("#contract-stage-terms-tbody");
    const evaluationTbody = node?.querySelector("#contract-stage-evaluation-tbody");
    if (!node || !termsTbody || node.dataset.contractStageTermsBound === "1") return;
    node.dataset.contractStageTermsBound = "1";

    let reportTermsEditMode = false;
    const termLockIcons = Array.from(node.querySelectorAll(".js-proposal-report-terms-lock"));
    const dateLockIcons = Array.from(node.querySelectorAll(".js-proposal-report-date-lock"));
    const contractDateInput = node.querySelector('[name="contract_date"]');
    const sourceDataTermUnits = new Set(["days", "weeks", "months"]);
    const defaultSourceDataTermUnit = "weeks";
    const preliminaryTermUnits = new Set(["months", "days", "weeks"]);
    const defaultPreliminaryTermUnit = "months";
    const finalTermUnits = new Set(["days", "weeks", "months"]);
    const defaultFinalTermUnit = "weeks";

    const getStageTermRows = () => Array.from(termsTbody.querySelectorAll(".proposal-stage-terms-row"));
    const getStageEvaluationRows = () => Array.from(
      evaluationTbody?.querySelectorAll(".proposal-stage-evaluation-row") || []
    );
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

    function getPreliminaryTermUnit(select) {
      const raw = String(select?.value || "").trim();
      return preliminaryTermUnits.has(raw) ? raw : defaultPreliminaryTermUnit;
    }

    function getSourceDataTermUnit(select) {
      const raw = String(select?.value || "").trim();
      return sourceDataTermUnits.has(raw) ? raw : defaultSourceDataTermUnit;
    }

    function getFinalTermUnit(select) {
      const raw = String(select?.value || "").trim();
      return finalTermUnits.has(raw) ? raw : defaultFinalTermUnit;
    }

    function formatPreliminaryTermValue(value, unit) {
      if (!Number.isFinite(value)) return "";
      if (unit === "days") return String(Math.round(Math.max(value, 0)));
      return formatDecimal(value);
    }

    function normalizePreliminaryTermInput(input, unit) {
      if (!input) return null;
      const parsed = parseDecimal(input.value);
      input.step = unit === "days" ? "1" : "0.1";
      input.inputMode = unit === "days" ? "numeric" : "decimal";
      if (parsed === null) {
        input.value = "";
        return null;
      }
      const normalized = unit === "days" ? Math.round(Math.max(parsed, 0)) : parsed;
      input.value = formatPreliminaryTermValue(normalized, unit);
      return normalized;
    }

    function normalizeSourceDataTermInput(input, unit) {
      return normalizePreliminaryTermInput(input, unit);
    }

    function normalizeFinalTermInput(input, unit) {
      return normalizePreliminaryTermInput(input, unit);
    }

    function addSourceDataTerm(date, value, unit) {
      if (unit === "days") return addDays(date, Math.round(Math.max(value, 0)));
      if (unit === "months") return addDecimalMonths(date, value);
      return addDecimalWeeks(date, value);
    }

    function subtractSourceDataTerm(date, value, unit) {
      if (unit === "days") return addDays(date, -Math.round(Math.max(value, 0)));
      if (unit === "months") return subtractDecimalMonths(date, value);
      return subtractDecimalWeeks(date, value);
    }

    function addPreliminaryTerm(date, value, unit) {
      if (unit === "days") return addDays(date, Math.round(Math.max(value, 0)));
      if (unit === "weeks") return addDecimalWeeks(date, value);
      return addDecimalMonths(date, value);
    }

    function subtractPreliminaryTerm(date, value, unit) {
      if (unit === "days") return addDays(date, -Math.round(Math.max(value, 0)));
      if (unit === "weeks") return subtractDecimalWeeks(date, value);
      return subtractDecimalMonths(date, value);
    }

    function addFinalTerm(date, value, unit) {
      if (unit === "days") return addDays(date, Math.round(Math.max(value, 0)));
      if (unit === "months") return addDecimalMonths(date, value);
      return addDecimalWeeks(date, value);
    }

    function subtractFinalTerm(date, value, unit) {
      if (unit === "days") return addDays(date, -Math.round(Math.max(value, 0)));
      if (unit === "months") return subtractDecimalMonths(date, value);
      return subtractDecimalWeeks(date, value);
    }

    function termValueToDays(value, unit) {
      const safeValue = Number.isFinite(value) ? Math.max(value, 0) : 0;
      if (unit === "months") return safeValue * 30;
      if (unit === "weeks") return safeValue * 7;
      return Math.round(safeValue);
    }

    function daysToTermValue(days, unit) {
      const safeDays = Number.isFinite(days) ? Math.max(days, 0) : 0;
      if (unit === "months") return safeDays / 30;
      if (unit === "weeks") return safeDays / 7;
      return Math.round(safeDays);
    }

    function setTotalTermValue(input, totalDays, unit) {
      if (!input) return;
      input.step = unit === "days" ? "1" : "0.1";
      input.inputMode = unit === "days" ? "numeric" : "decimal";
      input.value = Number.isFinite(totalDays)
        ? formatPreliminaryTermValue(daysToTermValue(totalDays, unit), unit)
        : "";
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

    function getDefaultEvaluationDateValue() {
      return formatDateIso(getDefaultEvaluationDate());
    }

    function getContractStartDateValue() {
      const contractDate = parseDate(node.querySelector('[name="contract_date"]')?.value);
      return contractDate ? formatDateIso(contractDate) : "";
    }

    let isSyncingContractDate = false;

    function syncContractDateFromCalculatedStart(date) {
      if (!contractDateInput || !date) return;
      const nextValue = formatDateIso(date);
      const currentDate = parseDate(contractDateInput.value);
      if (currentDate && formatDateIso(currentDate) === nextValue) return;
      isSyncingContractDate = true;
      try {
        setDateFieldValue(contractDateInput, nextValue);
      } finally {
        isSyncingContractDate = false;
      }
    }

    function syncStageEvaluationDates() {
      getStageEvaluationRows().forEach((row) => {
        const evaluationInput = row.querySelector(".proposal-stage-evaluation-date");
        const evaluationEnabled = getStageFieldToggleState(row, ".proposal-stage-evaluation-date-enabled");
        if (evaluationEnabled && evaluationInput && !parseDate(evaluationInput.value)) {
          setDateFieldValue(evaluationInput, getDefaultEvaluationDateValue());
        }
      });
    }

    function getStageFieldToggleState(row, hiddenSelector) {
      const hidden = hiddenSelector ? row.querySelector(hiddenSelector) : null;
      return String(hidden?.value || "true").toLowerCase() !== "false";
    }

    function refreshStageFieldLockIcons() {
      termLockIcons.concat(dateLockIcons).forEach((icon) => {
        const enabledSelector = icon.dataset.stageFieldEnabledSelector || "";
        if (!enabledSelector) {
          icon.classList.remove("is-stage-lock-disabled");
          return;
        }
        const relatedFlags = Array.from(node.querySelectorAll(enabledSelector));
        const hasDisabledField = relatedFlags.length > 0 && relatedFlags.every((field) => {
          return String(field.value || "true").toLowerCase() === "false";
        });
        icon.classList.toggle("is-stage-lock-disabled", hasDisabledField);
        if (hasDisabledField) {
          icon.classList.remove("bi-lock-fill", "bi-unlock-fill");
          icon.classList.add("bi-lock");
          icon.title = "Поле выключено";
        } else {
          icon.classList.remove("bi-lock");
          if (termLockIcons.includes(icon)) {
            icon.classList.toggle("bi-lock-fill", !reportTermsEditMode);
            icon.classList.toggle("bi-unlock-fill", reportTermsEditMode);
            icon.title = reportTermsEditMode ? "Заблокировать ввод сроков" : "Разблокировать ввод сроков";
          } else if (dateLockIcons.includes(icon)) {
            icon.classList.toggle("bi-lock-fill", reportTermsEditMode);
            icon.classList.toggle("bi-unlock-fill", !reportTermsEditMode);
            icon.title = reportTermsEditMode ? "Разблокировать ввод дат" : "Заблокировать ввод дат";
          }
        }
      });
    }

    function setFieldToggleValue(row, toggle, enabled, options) {
      const targetSelector = toggle.dataset.targetSelector || "";
      const unitSelector = toggle.dataset.unitSelector || "";
      const shellSelector = toggle.dataset.shellSelector || "";
      const hiddenSelector = toggle.dataset.hiddenSelector || "";
      const target = targetSelector ? row.querySelector(targetSelector) : null;
      const unit = unitSelector ? row.querySelector(unitSelector) : null;
      const shell = shellSelector ? row.querySelector(shellSelector) : null;
      const hidden = hiddenSelector ? row.querySelector(hiddenSelector) : null;
      const wrapper = toggle.closest(".proposal-stage-field-toggle-wrap");
      toggle.checked = enabled;
      if (hidden) hidden.value = enabled ? "true" : "false";
      wrapper?.classList.toggle("is-stage-field-disabled", !enabled);
      if (!enabled && options?.clear) {
        if (target?.classList.contains("js-date")) {
          setDateFieldValue(target, "");
        } else if (target) {
          target.value = "";
        }
      }
      const lockMode = toggle.dataset.lockMode || "";
      const targetIsDate = target?.classList.contains("js-date");
      const shouldLockTarget = !enabled || (
        lockMode === "none" ? false : (targetIsDate ? reportTermsEditMode : !reportTermsEditMode)
      );
      setReadonly(target, shouldLockTarget, {
        lockPicker: target?.classList.contains("js-date"),
      });
      if (unit) {
        const unitEditable = enabled && reportTermsEditMode;
        unit.tabIndex = unitEditable ? 0 : -1;
        unit.style.pointerEvents = unitEditable ? "" : "none";
        unit.setAttribute("aria-disabled", unitEditable ? "false" : "true");
      }
      shell?.classList.toggle("readonly-field", !enabled || !reportTermsEditMode);
      refreshStageFieldLockIcons();
    }

    function applyStageFieldToggleState(row, options) {
      row.querySelectorAll(".js-proposal-stage-field-toggle").forEach((toggle) => {
        const hiddenSelector = toggle.dataset.hiddenSelector || "";
        const hidden = hiddenSelector ? row.querySelector(hiddenSelector) : null;
        const enabled = String(hidden?.value || (toggle.checked ? "true" : "false")).toLowerCase() !== "false";
        setFieldToggleValue(row, toggle, enabled, options);
      });
    }

    function applyLockState() {
      setReadonly(contractDateInput, reportTermsEditMode, { lockPicker: true });
      getStageTermRows().forEach((row) => {
        setReadonly(row.querySelector(".proposal-stage-source-data-date"), reportTermsEditMode, { lockPicker: true });
        setReadonly(row.querySelector(".proposal-stage-preliminary-report-date"), reportTermsEditMode, { lockPicker: true });
        setReadonly(row.querySelector(".proposal-stage-final-report-date"), reportTermsEditMode, { lockPicker: true });
        const sourceDataTermInput = row.querySelector(".proposal-stage-source-data-term");
        const sourceDataTermUnit = row.querySelector(".proposal-stage-source-data-term-unit");
        const sourceDataTermShell = row.querySelector(".proposal-stage-source-data-term-shell");
        const preliminaryTermInput = row.querySelector(".proposal-stage-service-term-months");
        const preliminaryTermUnit = row.querySelector(".proposal-stage-preliminary-term-unit");
        const preliminaryTermShell = row.querySelector(".proposal-stage-preliminary-term-shell");
        const finalTermInput = row.querySelector(".proposal-stage-final-report-term-weeks");
        const finalTermUnit = row.querySelector(".proposal-stage-final-term-unit");
        const finalTermShell = row.querySelector(".proposal-stage-final-term-shell");
        setReadonly(sourceDataTermInput, !reportTermsEditMode);
        if (sourceDataTermUnit) {
          sourceDataTermUnit.tabIndex = reportTermsEditMode ? 0 : -1;
          sourceDataTermUnit.style.pointerEvents = reportTermsEditMode ? "" : "none";
          sourceDataTermUnit.setAttribute("aria-disabled", reportTermsEditMode ? "false" : "true");
        }
        sourceDataTermShell?.classList.toggle("readonly-field", !reportTermsEditMode);
        setReadonly(preliminaryTermInput, !reportTermsEditMode);
        if (preliminaryTermUnit) {
          preliminaryTermUnit.tabIndex = reportTermsEditMode ? 0 : -1;
          preliminaryTermUnit.style.pointerEvents = reportTermsEditMode ? "" : "none";
          preliminaryTermUnit.setAttribute("aria-disabled", reportTermsEditMode ? "false" : "true");
        }
        preliminaryTermShell?.classList.toggle("readonly-field", !reportTermsEditMode);
        setReadonly(finalTermInput, !reportTermsEditMode);
        if (finalTermUnit) {
          finalTermUnit.tabIndex = reportTermsEditMode ? 0 : -1;
          finalTermUnit.style.pointerEvents = reportTermsEditMode ? "" : "none";
          finalTermUnit.setAttribute("aria-disabled", reportTermsEditMode ? "false" : "true");
        }
        finalTermShell?.classList.toggle("readonly-field", !reportTermsEditMode);
        applyStageFieldToggleState(row);
      });
      refreshStageFieldLockIcons();
      termLockIcons.forEach((icon) => {
        if (icon.classList.contains("is-stage-lock-disabled")) return;
        icon.classList.remove("bi-lock");
        icon.classList.toggle("bi-lock-fill", !reportTermsEditMode);
        icon.classList.toggle("bi-unlock-fill", reportTermsEditMode);
        icon.title = reportTermsEditMode ? "Заблокировать ввод сроков" : "Разблокировать ввод сроков";
      });
      dateLockIcons.forEach((icon) => {
        if (icon.classList.contains("is-stage-lock-disabled")) return;
        icon.classList.remove("bi-lock");
        icon.classList.toggle("bi-lock-fill", reportTermsEditMode);
        icon.classList.toggle("bi-unlock-fill", !reportTermsEditMode);
        icon.title = reportTermsEditMode ? "Разблокировать ввод дат" : "Заблокировать ввод дат";
      });
    }

    function syncStageTerms() {
      const termRows = getStageTermRows();
      const states = termRows.map((row) => {
        const sourceDataTermInput = row.querySelector(".proposal-stage-source-data-term");
        const sourceDataTermUnitSelect = row.querySelector(".proposal-stage-source-data-term-unit");
        const monthsInput = row.querySelector(".proposal-stage-service-term-months");
        const termUnitSelect = row.querySelector(".proposal-stage-preliminary-term-unit");
        const weeksInput = row.querySelector(".proposal-stage-final-report-term-weeks");
        const finalTermUnitSelect = row.querySelector(".proposal-stage-final-term-unit");
        const delayInput = getStageDelayRowForTermRow(row)?.querySelector(".proposal-stage-next-delay-days");
        const sourceDataTermEnabled = getStageFieldToggleState(row, ".proposal-stage-source-data-term-enabled");
        const sourceDataDateEnabled = getStageFieldToggleState(row, ".proposal-stage-source-data-date-enabled");
        const preliminaryTermEnabled = getStageFieldToggleState(row, ".proposal-stage-service-term-months-enabled");
        const preliminaryDateEnabled = getStageFieldToggleState(row, ".proposal-stage-preliminary-report-date-enabled");
        const finalDateEnabled = getStageFieldToggleState(row, ".proposal-stage-final-report-date-enabled");
        const sourceDataTermUnit = getSourceDataTermUnit(sourceDataTermUnitSelect);
        const sourceDataTerm = sourceDataTermEnabled
          ? normalizeSourceDataTermInput(sourceDataTermInput, sourceDataTermUnit)
          : 0;
        const preliminaryTermUnit = getPreliminaryTermUnit(termUnitSelect);
        const preliminaryTerm = preliminaryTermEnabled
          ? normalizePreliminaryTermInput(monthsInput, preliminaryTermUnit)
          : 0;
        const finalTermUnit = getFinalTermUnit(finalTermUnitSelect);
        const finalTerm = normalizeFinalTermInput(weeksInput, finalTermUnit);
        return {
          row,
          sourceDataTermInput,
          sourceDataTermUnitSelect,
          monthsInput,
          termUnitSelect,
          weeksInput,
          finalTermUnitSelect,
          sourceDataInput: row.querySelector(".proposal-stage-source-data-date"),
          preliminaryInput: row.querySelector(".proposal-stage-preliminary-report-date"),
          finalInput: row.querySelector(".proposal-stage-final-report-date"),
          delayInput,
          sourceDataTerm,
          sourceDataTermUnit,
          sourceDataTermEnabled,
          sourceDataDateEnabled,
          preliminaryTerm,
          preliminaryTermUnit,
          preliminaryTermEnabled,
          preliminaryDateEnabled,
          finalDateEnabled,
          finalTerm,
          finalTermUnit,
          nextDelayDays: parseInteger(delayInput?.value) || 0,
          sourceDataDate: sourceDataDateEnabled
            ? parseDate(row.querySelector(".proposal-stage-source-data-date")?.value)
            : null,
          preliminaryDate: preliminaryDateEnabled
            ? parseDate(row.querySelector(".proposal-stage-preliminary-report-date")?.value)
            : null,
          finalDate: finalDateEnabled
            ? parseDate(row.querySelector(".proposal-stage-final-report-date")?.value)
            : null,
          shouldForceDatesFromTerms: row.dataset.forceDatesFromTerms === "1",
          manualDateSource: String(row.dataset.manualDateSource || "").trim(),
          calculatedSourceDataDate: null,
          calculatedPreliminaryDate: null,
          calculatedFinalDate: null,
        };
      });

      function applyStateDates(state) {
        setDateFieldValue(
          state.sourceDataInput,
          state.sourceDataDateEnabled && state.calculatedSourceDataDate ? formatDateIso(state.calculatedSourceDataDate) : ""
        );
        setDateFieldValue(
          state.preliminaryInput,
          state.preliminaryDateEnabled && state.calculatedPreliminaryDate ? formatDateIso(state.calculatedPreliminaryDate) : ""
        );
        setDateFieldValue(
          state.finalInput,
          state.finalDateEnabled && state.calculatedFinalDate ? formatDateIso(state.calculatedFinalDate) : ""
        );
      }

      function applyNextStageDelay(date, state) {
        if (!date) return date;
        return state.nextDelayDays ? addDays(date, state.nextDelayDays) : date;
      }

      function updateTotals() {
        const totalsRow = getTotalsRow();
        if (!totalsRow) return;
        const allStageFieldsDisabled = (selector) => (
          termRows.length > 0 && termRows.every((row) => !getStageFieldToggleState(row, selector))
        );
        const setTotalDisabledState = (field, disabled) => {
          if (!field) return;
          const shell = field.closest(".proposal-stage-total-term-shell");
          (shell || field).classList.toggle("proposal-stage-total-field-disabled", disabled);
        };
        const totalSourceDataInput = totalsRow.querySelector(".proposal-stage-total-source-data-term");
        const totalSourceDataUnit = getSourceDataTermUnit(
          totalsRow.querySelector(".proposal-stage-total-source-data-term-unit")
        );
        const totalMonthsInput = totalsRow.querySelector(".proposal-stage-total-service-term-months");
        const totalPreliminaryUnit = getPreliminaryTermUnit(
          totalsRow.querySelector(".proposal-stage-total-preliminary-term-unit")
        );
        const totalWeeksInput = totalsRow.querySelector(".proposal-stage-total-final-report-term-weeks");
        const totalFinalUnit = getFinalTermUnit(totalsRow.querySelector(".proposal-stage-total-final-term-unit"));
        const sourceDataTermDisabled = allStageFieldsDisabled(".proposal-stage-source-data-term-enabled");
        const sourceDataDateDisabled = allStageFieldsDisabled(".proposal-stage-source-data-date-enabled");
        const preliminaryTermDisabled = allStageFieldsDisabled(".proposal-stage-service-term-months-enabled");
        const preliminaryDateDisabled = allStageFieldsDisabled(".proposal-stage-preliminary-report-date-enabled");
        const finalDateDisabled = allStageFieldsDisabled(".proposal-stage-final-report-date-enabled");
        const totalSourceDataDays = termRows.reduce((sum, row) => {
          if (!getStageFieldToggleState(row, ".proposal-stage-source-data-term-enabled")) return sum;
          const unit = getSourceDataTermUnit(row.querySelector(".proposal-stage-source-data-term-unit"));
          return sum + termValueToDays(parseDecimal(row.querySelector(".proposal-stage-source-data-term")?.value), unit);
        }, 0);
        const totalPreliminaryDays = termRows.reduce((sum, row) => {
          if (!getStageFieldToggleState(row, ".proposal-stage-service-term-months-enabled")) return sum;
          const unit = getPreliminaryTermUnit(row.querySelector(".proposal-stage-preliminary-term-unit"));
          return sum + termValueToDays(parseDecimal(row.querySelector(".proposal-stage-service-term-months")?.value), unit);
        }, 0);
        const totalFinalDays = termRows.reduce((sum, row) => {
          const unit = getFinalTermUnit(row.querySelector(".proposal-stage-final-term-unit"));
          return sum + termValueToDays(parseDecimal(row.querySelector(".proposal-stage-final-report-term-weeks")?.value), unit);
        }, 0);
        setTotalTermValue(
          totalSourceDataInput,
          termRows.length > 1 && !sourceDataTermDisabled ? totalSourceDataDays : null,
          totalSourceDataUnit
        );
        setTotalTermValue(
          totalMonthsInput,
          termRows.length > 1 && !preliminaryTermDisabled ? totalPreliminaryDays : null,
          totalPreliminaryUnit
        );
        setTotalTermValue(totalWeeksInput, termRows.length > 1 ? totalFinalDays : null, totalFinalUnit);
        setTotalDisabledState(totalSourceDataInput, sourceDataTermDisabled);
        setTotalDisabledState(totalsRow.querySelector(".proposal-stage-total-source-data-date"), sourceDataDateDisabled);
        setTotalDisabledState(totalMonthsInput, preliminaryTermDisabled);
        setTotalDisabledState(
          totalsRow.querySelector(".proposal-stage-total-preliminary-report-date"),
          preliminaryDateDisabled
        );
        setTotalDisabledState(totalsRow.querySelector(".proposal-stage-total-final-report-date"), finalDateDisabled);
        totalsRow.classList.toggle("d-none", termRows.length <= 1);
      }

      function computeForwardDates(startDate, state) {
        if (state.sourceDataTerm === null) {
          state.calculatedSourceDataDate = null;
          state.calculatedPreliminaryDate = null;
          state.calculatedFinalDate = null;
          return applyNextStageDelay(startDate, state);
        }
        state.calculatedSourceDataDate = addSourceDataTerm(
          startDate,
          state.sourceDataTerm,
          state.sourceDataTermUnit
        );
        if (state.preliminaryTerm === null) {
          state.calculatedPreliminaryDate = null;
          state.calculatedFinalDate = null;
          return applyNextStageDelay(state.calculatedSourceDataDate, state);
        }
        state.calculatedPreliminaryDate = addPreliminaryTerm(
          state.calculatedSourceDataDate,
          state.preliminaryTerm,
          state.preliminaryTermUnit
        );
        if (state.finalTerm === null) {
          state.calculatedFinalDate = null;
          return applyNextStageDelay(state.calculatedPreliminaryDate, state);
        }
        state.calculatedFinalDate = addFinalTerm(
          state.calculatedPreliminaryDate,
          state.finalTerm,
          state.finalTermUnit
        );
        return applyNextStageDelay(state.calculatedFinalDate, state);
      }

      const contractStartDate = parseDate(getContractStartDateValue());
      if (!contractStartDate) {
        states.forEach((state) => {
          state.calculatedSourceDataDate = null;
          state.calculatedPreliminaryDate = null;
          state.calculatedFinalDate = null;
          applyStateDates(state);
          delete state.row.dataset.forceDatesFromTerms;
          delete state.row.dataset.manualDateSource;
        });
        updateTotals();
        return;
      }

      if (reportTermsEditMode) {
        let startDate = contractStartDate;
        states.forEach((state) => {
          startDate = computeForwardDates(startDate, state);
          applyStateDates(state);
          delete state.row.dataset.forceDatesFromTerms;
          delete state.row.dataset.manualDateSource;
        });
      } else {
        let baseStartDate = contractStartDate;
        const manualIndex = states.findIndex((state) => {
          if (state.manualDateSource === "source_data") {
            return state.sourceDataDateEnabled && !!state.sourceDataDate && state.sourceDataTerm !== null;
          }
          if (state.manualDateSource === "preliminary") {
            return state.preliminaryDateEnabled && !!state.preliminaryDate && state.preliminaryTerm !== null;
          }
          if (state.manualDateSource === "final") {
            return state.finalDateEnabled && !!state.finalDate && state.finalTerm !== null;
          }
          return false;
        });

        if (manualIndex >= 0) {
          const manualState = states[manualIndex];
          let manualStageStartDate = null;
          if (manualState.manualDateSource === "source_data") {
            manualState.calculatedSourceDataDate = manualState.sourceDataDate;
            manualState.calculatedPreliminaryDate = manualState.preliminaryTerm !== null
              ? addPreliminaryTerm(manualState.sourceDataDate, manualState.preliminaryTerm, manualState.preliminaryTermUnit)
              : null;
            manualState.calculatedFinalDate = manualState.calculatedPreliminaryDate && manualState.finalTerm !== null
              ? addFinalTerm(manualState.calculatedPreliminaryDate, manualState.finalTerm, manualState.finalTermUnit)
              : null;
            manualStageStartDate = manualState.sourceDataDate && manualState.sourceDataTerm !== null
              ? subtractSourceDataTerm(
                  manualState.sourceDataDate,
                  manualState.sourceDataTerm,
                  manualState.sourceDataTermUnit
                )
              : null;
          } else if (manualState.manualDateSource === "preliminary") {
            manualState.calculatedPreliminaryDate = manualState.preliminaryDate;
            manualState.calculatedSourceDataDate = manualState.preliminaryDate && manualState.preliminaryTerm !== null
              ? subtractPreliminaryTerm(
                  manualState.preliminaryDate,
                  manualState.preliminaryTerm,
                  manualState.preliminaryTermUnit
                )
              : null;
            manualState.calculatedFinalDate = manualState.finalTerm !== null
              ? addFinalTerm(manualState.preliminaryDate, manualState.finalTerm, manualState.finalTermUnit)
              : null;
            manualStageStartDate = manualState.calculatedSourceDataDate && manualState.sourceDataTerm !== null
              ? subtractSourceDataTerm(
                  manualState.calculatedSourceDataDate,
                  manualState.sourceDataTerm,
                  manualState.sourceDataTermUnit
                )
              : null;
          } else {
            manualState.calculatedFinalDate = manualState.finalDate;
            manualState.calculatedPreliminaryDate = manualState.finalTerm !== null
              ? subtractFinalTerm(manualState.finalDate, manualState.finalTerm, manualState.finalTermUnit)
              : null;
            manualState.calculatedSourceDataDate = manualState.calculatedPreliminaryDate && manualState.preliminaryTerm !== null
              ? subtractPreliminaryTerm(
                  manualState.calculatedPreliminaryDate,
                  manualState.preliminaryTerm,
                  manualState.preliminaryTermUnit
                )
              : null;
            manualStageStartDate = manualState.calculatedSourceDataDate && manualState.sourceDataTerm !== null
              ? subtractSourceDataTerm(
                  manualState.calculatedSourceDataDate,
                  manualState.sourceDataTerm,
                  manualState.sourceDataTermUnit
                )
              : null;
          }

          let rollingStartDate = manualStageStartDate;
          for (let index = manualIndex - 1; index >= 0; index -= 1) {
            const state = states[index];
            const stageEndDate = rollingStartDate && state.nextDelayDays
              ? addDays(rollingStartDate, -state.nextDelayDays)
              : rollingStartDate;
            state.calculatedFinalDate = stageEndDate;
            state.calculatedPreliminaryDate = stageEndDate && state.finalTerm !== null
              ? subtractFinalTerm(stageEndDate, state.finalTerm, state.finalTermUnit)
              : null;
            state.calculatedSourceDataDate = state.calculatedPreliminaryDate && state.preliminaryTerm !== null
              ? subtractPreliminaryTerm(state.calculatedPreliminaryDate, state.preliminaryTerm, state.preliminaryTermUnit)
              : null;
            rollingStartDate = state.calculatedSourceDataDate && state.sourceDataTerm !== null
              ? subtractSourceDataTerm(state.calculatedSourceDataDate, state.sourceDataTerm, state.sourceDataTermUnit)
              : rollingStartDate;
          }

          if (rollingStartDate) {
            baseStartDate = rollingStartDate;
            syncContractDateFromCalculatedStart(baseStartDate);
          }

          let forwardStartDate = applyNextStageDelay(
            manualState.calculatedFinalDate
              || manualState.calculatedPreliminaryDate
              || manualState.calculatedSourceDataDate
              || manualStageStartDate
              || baseStartDate,
            manualState
          );
          for (let index = manualIndex + 1; index < states.length; index += 1) {
            forwardStartDate = computeForwardDates(forwardStartDate, states[index]);
          }
          states.forEach(applyStateDates);
        } else {
          let startDate = baseStartDate;
          states.forEach((state) => {
            const shouldComputeFromTerms = (
              state.shouldForceDatesFromTerms
              || !state.finalDateEnabled
              || (!state.sourceDataDate && !state.preliminaryDate && !state.finalDate)
            );
            if (shouldComputeFromTerms) {
              startDate = computeForwardDates(startDate, state);
              applyStateDates(state);
            } else {
              startDate = applyNextStageDelay(
                state.finalDate || state.preliminaryDate || state.sourceDataDate || startDate,
                state
              );
            }
          });
        }

        states.forEach((state) => {
          delete state.row.dataset.forceDatesFromTerms;
          delete state.row.dataset.manualDateSource;
        });
      }

      updateTotals();
    }

    function bindTermsRows() {
      getStageTermRows().forEach((row) => {
        if (row.dataset.eventsBound === "1") return;
        row.dataset.eventsBound = "1";
        if (typeof window.initDatepickers === "function") {
          window.initDatepickers(row);
        }
        const sourceDataTermInput = row.querySelector(".proposal-stage-source-data-term");
        const sourceDataTermUnitSelect = row.querySelector(".proposal-stage-source-data-term-unit");
        const monthsInput = row.querySelector(".proposal-stage-service-term-months");
        const termUnitSelect = row.querySelector(".proposal-stage-preliminary-term-unit");
        const weeksInput = row.querySelector(".proposal-stage-final-report-term-weeks");
        const finalTermUnitSelect = row.querySelector(".proposal-stage-final-term-unit");
        normalizeSourceDataTermInput(sourceDataTermInput, getSourceDataTermUnit(sourceDataTermUnitSelect));
        normalizePreliminaryTermInput(monthsInput, getPreliminaryTermUnit(termUnitSelect));
        normalizeFinalTermInput(weeksInput, getFinalTermUnit(finalTermUnitSelect));
        applyStageFieldToggleState(row, { clear: true });
        ["input", "change"].forEach((eventName) => {
          sourceDataTermInput?.addEventListener(eventName, () => {
            row.dataset.forceDatesFromTerms = "1";
            syncStageTerms();
            if (eventName === "change") normalizeSourceDataTermInput(sourceDataTermInput, getSourceDataTermUnit(sourceDataTermUnitSelect));
          });
          sourceDataTermUnitSelect?.addEventListener(eventName, () => {
            row.dataset.forceDatesFromTerms = "1";
            normalizeSourceDataTermInput(sourceDataTermInput, getSourceDataTermUnit(sourceDataTermUnitSelect));
            syncStageTerms();
          });
          monthsInput?.addEventListener(eventName, () => {
            row.dataset.forceDatesFromTerms = "1";
            syncStageTerms();
            if (eventName === "change") normalizePreliminaryTermInput(monthsInput, getPreliminaryTermUnit(termUnitSelect));
          });
          termUnitSelect?.addEventListener(eventName, () => {
            row.dataset.forceDatesFromTerms = "1";
            normalizePreliminaryTermInput(monthsInput, getPreliminaryTermUnit(termUnitSelect));
            syncStageTerms();
          });
          weeksInput?.addEventListener(eventName, () => {
            row.dataset.forceDatesFromTerms = "1";
            syncStageTerms();
            if (eventName === "change") normalizeFinalTermInput(weeksInput, getFinalTermUnit(finalTermUnitSelect));
          });
          finalTermUnitSelect?.addEventListener(eventName, () => {
            row.dataset.forceDatesFromTerms = "1";
            normalizeFinalTermInput(weeksInput, getFinalTermUnit(finalTermUnitSelect));
            syncStageTerms();
          });
          row.querySelector(".proposal-stage-source-data-date")?.addEventListener(eventName, () => {
            if (!reportTermsEditMode && getStageFieldToggleState(row, ".proposal-stage-source-data-date-enabled")) {
              row.dataset.manualDateSource = "source_data";
              syncStageTerms();
            }
          });
          row.querySelector(".proposal-stage-preliminary-report-date")?.addEventListener(eventName, () => {
            if (!reportTermsEditMode && getStageFieldToggleState(row, ".proposal-stage-preliminary-report-date-enabled")) {
              row.dataset.manualDateSource = "preliminary";
              syncStageTerms();
            }
          });
          row.querySelector(".proposal-stage-final-report-date")?.addEventListener(eventName, () => {
            if (!reportTermsEditMode && getStageFieldToggleState(row, ".proposal-stage-final-report-date-enabled")) {
              row.dataset.manualDateSource = "final";
              syncStageTerms();
            }
          });
        });
        row.querySelectorAll(".js-proposal-stage-field-toggle").forEach((toggle) => {
          toggle.addEventListener("change", () => {
            setFieldToggleValue(row, toggle, toggle.checked, { clear: true });
            row.dataset.forceDatesFromTerms = "1";
            delete row.dataset.manualDateSource;
            syncStageTerms();
          });
        });
      });
    }

    function bindEvaluationRows() {
      getStageEvaluationRows().forEach((row) => {
        if (row.dataset.eventsBound === "1") return;
        row.dataset.eventsBound = "1";
        if (typeof window.initDatepickers === "function") {
          window.initDatepickers(row);
        }
        applyStageFieldToggleState(row, { clear: true });
        row.querySelectorAll(".js-proposal-stage-field-toggle").forEach((toggle) => {
          toggle.addEventListener("change", () => {
            setFieldToggleValue(row, toggle, toggle.checked, { clear: true });
            syncStageEvaluationDates();
          });
        });
      });
      syncStageEvaluationDates();
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

    function bindTotalsRow() {
      const totalsRow = getTotalsRow();
      if (!totalsRow || totalsRow.dataset.eventsBound === "1") return;
      totalsRow.dataset.eventsBound = "1";
      totalsRow.querySelectorAll(
        ".proposal-stage-total-source-data-term-unit, .proposal-stage-total-preliminary-term-unit, .proposal-stage-total-final-term-unit"
      ).forEach((select) => {
        select.addEventListener("change", syncStageTerms);
      });
    }

    if (contractDateInput && contractDateInput.dataset.contractTermsBound !== "1") {
      contractDateInput.dataset.contractTermsBound = "1";
      ["input", "change"].forEach((eventName) => {
        contractDateInput.addEventListener(eventName, () => {
          if (isSyncingContractDate) return;
          getStageTermRows().forEach((row) => {
            row.dataset.forceDatesFromTerms = "1";
            delete row.dataset.manualDateSource;
          });
          syncStageTerms();
        });
      });
    }

    termLockIcons.concat(dateLockIcons).forEach((icon) => {
      icon.addEventListener("click", () => {
        if (icon.classList.contains("is-stage-lock-disabled")) return;
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
        bindEvaluationRows();
        bindStageDelayRows();
        bindTotalsRow();
        applyLockState();
        syncStageEvaluationDates();
        syncStageTerms();
      },
    };

    bindTermsRows();
    bindEvaluationRows();
    bindStageDelayRows();
    bindTotalsRow();
    applyLockState();
    syncStageEvaluationDates();
    syncStageTerms();
  }

  window.attachContractStageTerms = attachContractStageTerms;
})();
