(function () {
  function fitReportTermsTable(node) {
    const group = node.querySelector(".contract-stage-report-terms-group");
    const table = group?.querySelector(".proposal-report-terms-table");
    if (!group || !table) return;
    const editor = group.closest(".proposal-terms-editor") || table;
    const limitRoot = editor.closest("#proposals-pane")
      || editor.closest(".proposal-form-page")
      || editor.closest(".contracts-project-form-page")
      || editor.closest(".card")
      || editor.closest(".registration-form-page")
      || editor;
    const groups = () => node.querySelectorAll(
      ".contract-stage-report-terms-group, .contract-stage-evaluation-terms-group"
    );
    const contentEdge = (root) => {
      const box = root.getBoundingClientRect();
      let right = box.left;
      const rootTable = root.querySelector("table");
      if (rootTable) right = Math.max(right, rootTable.getBoundingClientRect().right);
      root.querySelectorAll(
        ".proposal-stage-final-term-shell, .proposal-stage-delay-add, .proposal-stage-delay-action-slot"
      ).forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 || rect.height > 0) right = Math.max(right, rect.right);
      });
      return { left: box.left, right: box.right, contentRight: right };
    };
    const collapseKey = () => ["is-source-date-collapsed", "is-preliminary-date-collapsed", "is-final-date-collapsed"]
      .map((name) => (editor.classList.contains(name) ? "1" : "0"))
      .join("");
    const sourceInputs = () => Array.from(
      table.querySelectorAll(".proposal-stage-terms-row .proposal-stage-source-data-term")
    ).filter((input) => input.getClientRects().length);
    const sourceNumberFloor = () => {
      const input = sourceInputs()[0];
      if (!input || !input.parentElement) return 0;
      const probe = input.cloneNode(true);
      probe.style.position = "absolute";
      probe.style.left = "-9999px";
      probe.style.minWidth = "0";
      probe.style.visibility = "hidden";
      probe.style.width = "40px";
      input.parentElement.appendChild(probe);
      probe.value = "12.0";
      const needed = probe.scrollWidth + 1;
      probe.remove();
      return needed;
    };
    const measureSourceNumber = () => {
      const inputs = sourceInputs();
      if (!inputs.length) return Infinity;
      return Math.min(...inputs.map((input) => {
        const shell = input.closest(".proposal-stage-source-data-term-shell");
        const unit = shell?.querySelector("select");
        if (!shell || !unit) return input.clientWidth;
        return shell.clientWidth - unit.getBoundingClientRect().width;
      }));
    };
    const fullStageLabelWidth = (rem) => {
      const sample = table.querySelector(".proposal-stage-label-input");
      const canvas = fullStageLabelWidth.canvas || (fullStageLabelWidth.canvas = document.createElement("canvas"));
      const context = canvas.getContext("2d");
      context.font = sample ? getComputedStyle(sample).font : `${rem}px sans-serif`;
      let textWidth = context.measureText("Этап 1").width;
      table.querySelectorAll(".proposal-stage-label-input").forEach((input) => {
        const text = String(input.value || "");
        if (/^Этап\s+\d+$/.test(text)) textWidth = Math.max(textWidth, context.measureText(text).width);
      });
      return Math.ceil(textWidth + (0.75 * rem * 2) + 2 + (0.25 * rem));
    };
    const syncStageLabelCompact = (input) => {
      const compact = input.parentElement?.querySelector(".proposal-stage-label-compact");
      if (!compact) return;
      const text = String(input.value || "").trim();
      const stage = text.match(/^Этап\s+(\d+)$/);
      if (stage) compact.textContent = stage[1];
      else if (text === "Итого") compact.textContent = "∑";
      else if (text === "Все") compact.textContent = "∀";
      else compact.textContent = text;
    };
    const layoutAt = (stagePx, width, rem, stageFull) => {
      const stage = Math.max(1, Math.round(stagePx));
      editor.style.setProperty("--proposal-terms-stage", `${stage}px`);
      let fit = (width - 3.5 * rem - 2) / (width + 5 * stage);
      fit = Math.max(fit, 0.25);
      editor.style.setProperty("--proposal-terms-fit", String(fit));
      for (let pass = 0; pass < 4; pass += 1) {
        let extra = 0;
        let scalable = 1;
        const limitRight = limitRoot.getBoundingClientRect().right;
        groups().forEach((item) => {
          const edge = contentEdge(item);
          const overflow = edge.contentRight - (Math.min(edge.right, limitRight) - 1);
          if (overflow > extra) {
            extra = overflow;
            scalable = Math.max(edge.contentRight - edge.left - stage, 1);
          }
        });
        if (extra <= 1) break;
        fit = Math.max(0.25, fit * (scalable - extra) / scalable);
        editor.style.setProperty("--proposal-terms-fit", String(fit));
      }
      editor.classList.toggle("is-stage-labels-compact", stage < fullStageLabelWidth(rem) - 1);
      editor.querySelectorAll(".proposal-stage-label-input").forEach(syncStageLabelCompact);
      return stage;
    };
    const apply = () => {
      const width = group.clientWidth;
      if (!width) return;
      const key = `${Math.round(width)}|${collapseKey()}`;
      if (key === apply.lastKey) return;
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      const stageFull = 5.5 * rem;
      const stageMin = 2.75 * rem;
      layoutAt(stageFull, width, rem, stageFull);
      const floor = sourceNumberFloor();
      const fullNumber = measureSourceNumber();
      if (floor > 0 && fullNumber < floor) {
        layoutAt(stageMin, width, rem, stageFull);
        const compactNumber = measureSourceNumber();
        if (compactNumber > fullNumber + 0.5) {
          let lo = Math.round(stageMin);
          let hi = Math.round(stageFull) - 1;
          let best = lo;
          for (let step = 0; step < 8 && lo <= hi; step += 1) {
            const mid = Math.round((lo + hi) / 2);
            layoutAt(mid, width, rem, stageFull);
            if (measureSourceNumber() >= floor) {
              best = mid;
              lo = mid + 1;
            } else {
              hi = mid - 1;
            }
          }
          layoutAt(best, width, rem, stageFull);
        } else {
          layoutAt(stageFull, width, rem, stageFull);
        }
      }
      apply.lastKey = `${Math.round(group.clientWidth)}|${collapseKey()}`;
    };
    apply();
    if (group.dataset.termsFitBound === "1") return;
    group.dataset.termsFitBound = "1";
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(apply).observe(group);
    } else {
      window.addEventListener("resize", apply);
    }
    if (typeof MutationObserver !== "undefined" && editor.dataset.termsFitObserved !== "1") {
      editor.dataset.termsFitObserved = "1";
      new MutationObserver(apply).observe(editor, {
        attributes: true,
        attributeFilter: ["class"],
      });
    }
  }

  function attachContractStageTerms(node, options) {
    const settings = options || {};
    const termsTbody = node?.querySelector(settings.termsTbodySelector || "#contract-stage-terms-tbody");
    const evaluationTbody = node?.querySelector(settings.evaluationTbodySelector || "#contract-stage-evaluation-tbody");
    if (!node || !termsTbody || node.dataset.contractStageTermsBound === "1") return;
    node.dataset.contractStageTermsBound = "1";
    if (settings.groupByContract) node.dataset.registrationContractGroups = "1";

    let reportTermsEditMode = false;
    const termLockIcons = () => Array.from(node.querySelectorAll(".js-proposal-report-terms-lock"));
    const dateLockIcons = () => Array.from(node.querySelectorAll(".js-proposal-report-date-lock"));
    const contractDateInput = node.querySelector(settings.anchorSelector || '[name="contract_date"]');
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
    const keepDisabledStageDatesVisible = termsTbody.id === "registration-stage-terms-tbody"
      || termsTbody.id === "contract-stage-terms-tbody"
      || termsTbody.id === "proposal-stage-terms-tbody";
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

    function getDelayUnit(select) {
      const raw = String(select?.value || "").trim();
      return sourceDataTermUnits.has(raw) ? raw : "days";
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
      if (input.dataset.projectStartLocked === "1") locked = true;
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
      const contractDate = parseDate(contractDateInput?.value);
      return contractDate ? formatDateIso(contractDate) : "";
    }

    let isSyncingContractDate = false;

    function syncContractDateFromCalculatedStart(date) {
      if (!contractDateInput || !date || contractDateInput.dataset.projectStartLocked === "1") return;
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

    function evaluationCommonToggle() {
      return node.querySelector(".js-registration-evaluation-common");
    }

    function copySharedEvaluationValues(rows) {
      const source = rows[0];
      if (!source || rows.length < 2) return;
      const sourceDate = source.querySelector(".proposal-stage-evaluation-date");
      const sourceHidden = source.querySelector(".proposal-stage-evaluation-date-enabled");
      const enabled = String(sourceHidden?.value || "true").toLowerCase() !== "false";
      const dateValue = sourceDate?.value || "";
      rows.slice(1).forEach((row) => {
        const toggle = row.querySelector(".proposal-stage-evaluation-date-toggle");
        if (toggle) setFieldToggleValue(row, toggle, enabled, { clear: false });
        const date = row.querySelector(".proposal-stage-evaluation-date");
        if (date) setDateFieldValue(date, dateValue);
        const hidden = row.querySelector(".proposal-stage-evaluation-date-enabled");
        if (hidden) hidden.value = enabled ? "true" : "false";
      });
    }

    function applyEvaluationCommonMode() {
      const control = node.querySelector(".registration-evaluation-common");
      const toggle = evaluationCommonToggle();
      if (!control || !toggle) return;
      const rows = getStageEvaluationRows();
      const multiple = rows.length > 1;
      control.classList.toggle("d-none", !multiple);
      const common = multiple && toggle.checked;
      rows.forEach((row, index) => {
        row.classList.toggle("d-none", common && index > 0);
        if (index !== 0) return;
        const label = row.querySelector(".proposal-stage-label-input");
        if (label) {
          label.value = common ? "Все" : "Этап 1";
          const compact = label.parentElement?.querySelector(".proposal-stage-label-compact");
          if (compact) compact.textContent = common ? "∀" : "1";
        }
      });
      if (common) copySharedEvaluationValues(rows);
    }

    function bindEvaluationCommonToggle() {
      const toggle = evaluationCommonToggle();
      if (!toggle || toggle.dataset.eventsBound === "1") return;
      toggle.dataset.eventsBound = "1";
      toggle.addEventListener("change", () => {
        applyEvaluationCommonMode();
      });
    }

    function getStageFieldToggleState(row, hiddenSelector) {
      const hidden = hiddenSelector ? row.querySelector(hiddenSelector) : null;
      return String(hidden?.value || "true").toLowerCase() !== "false";
    }

    function refreshStageFieldLockIcons() {
      termLockIcons().concat(dateLockIcons()).forEach((icon) => {
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
          if (termLockIcons().includes(icon)) {
            icon.classList.toggle("bi-lock-fill", !reportTermsEditMode);
            icon.classList.toggle("bi-unlock-fill", reportTermsEditMode);
            icon.title = reportTermsEditMode ? "Заблокировать ввод сроков" : "Разблокировать ввод сроков";
          } else if (dateLockIcons().includes(icon)) {
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
      const hidden = hiddenSelector
        ? Array.from(row.querySelectorAll(hiddenSelector)).find(
          (element) => !element.closest(".registration-stage-project-values")
        )
        : null;
      const wrapper = toggle.closest(".proposal-stage-field-toggle-wrap");
      const contractLocked = settings.groupByContract && row?.dataset.contractTermsLocked === "1";
      toggle.checked = enabled;
      toggle.disabled = Boolean(contractLocked);
      if (hidden) hidden.value = enabled ? "true" : "false";
      wrapper?.classList.toggle("is-stage-field-disabled", !enabled);
      const keepStageDate = keepDisabledStageDatesVisible && (
        target?.classList.contains("proposal-stage-source-data-date")
        || target?.classList.contains("proposal-stage-preliminary-report-date")
        || target?.classList.contains("proposal-stage-final-report-date")
      );
      if (!enabled && options?.clear && !keepStageDate) {
        if (target?.classList.contains("js-date")) {
          setDateFieldValue(target, "");
        } else if (target) {
          target.value = "";
        }
      }
      const lockMode = toggle.dataset.lockMode || "";
      const targetIsDate = target?.classList.contains("js-date");
      const shouldLockTarget = contractLocked || !enabled || (
        lockMode === "none" ? false : (targetIsDate ? reportTermsEditMode : !reportTermsEditMode)
      );
      setReadonly(target, shouldLockTarget, {
        lockPicker: target?.classList.contains("js-date"),
      });
      if (unit) {
        const unitEditable = enabled && reportTermsEditMode && !contractLocked;
        unit.tabIndex = unitEditable ? 0 : -1;
        unit.style.pointerEvents = unitEditable ? "" : "none";
        unit.setAttribute("aria-disabled", unitEditable ? "false" : "true");
      }
      shell?.classList.toggle("readonly-field", contractLocked || !enabled || !reportTermsEditMode);
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
        if (settings.groupByContract && row.dataset.contractTermsLocked === "1") {
          setReadonly(row.querySelector(".proposal-stage-source-data-date"), true, { lockPicker: true });
          setReadonly(row.querySelector(".proposal-stage-preliminary-report-date"), true, { lockPicker: true });
          setReadonly(row.querySelector(".proposal-stage-final-report-date"), true, { lockPicker: true });
          setReadonly(sourceDataTermInput, true);
          setReadonly(preliminaryTermInput, true);
          setReadonly(finalTermInput, true);
          [sourceDataTermUnit, preliminaryTermUnit, finalTermUnit].forEach((unit) => {
            if (!unit) return;
            unit.tabIndex = -1;
            unit.style.pointerEvents = "none";
            unit.setAttribute("aria-disabled", "true");
          });
          sourceDataTermShell?.classList.add("readonly-field");
          preliminaryTermShell?.classList.add("readonly-field");
          finalTermShell?.classList.add("readonly-field");
          const delayRow = getStageDelayRowForTermRow(row);
          setReadonly(delayRow?.querySelector(".proposal-stage-next-delay-days"), true);
          const lockedDelayUnit = delayRow?.querySelector(".proposal-stage-delay-unit");
          if (lockedDelayUnit) {
            lockedDelayUnit.tabIndex = -1;
            lockedDelayUnit.style.pointerEvents = "none";
            lockedDelayUnit.setAttribute("aria-disabled", "true");
          }
          delayRow?.querySelector(".proposal-stage-delay-number-shell")?.classList.add("readonly-field");
          delayRow?.querySelector(".proposal-stage-delay-remove")?.setAttribute("disabled", "disabled");
          row.querySelector(".proposal-stage-delay-add")?.setAttribute("disabled", "disabled");
        } else if (settings.groupByContract) {
          const delayRow = getStageDelayRowForTermRow(row);
          const delayInput = delayRow?.querySelector(".proposal-stage-next-delay-days");
          if (delayInput) setReadonly(delayInput, false);
          const delayUnit = delayRow?.querySelector(".proposal-stage-delay-unit");
          if (delayUnit && delayRow?.previousElementSibling?.dataset.contractTermsLocked !== "1") {
            delayUnit.disabled = false;
            delayUnit.removeAttribute("tabindex");
            delayUnit.style.pointerEvents = "";
            delayUnit.setAttribute("aria-disabled", "false");
          }
          if (delayRow?.previousElementSibling?.dataset.contractTermsLocked !== "1") {
            delayRow?.querySelector(".proposal-stage-delay-number-shell")?.classList.remove("readonly-field");
          }
          delayRow?.querySelector(".proposal-stage-delay-remove")?.removeAttribute("disabled");
          row.querySelector(".proposal-stage-delay-add")?.removeAttribute("disabled");
        }
      });
      refreshStageFieldLockIcons();
      termLockIcons().forEach((icon) => {
        if (icon.classList.contains("is-stage-lock-disabled")) return;
        icon.classList.remove("bi-lock");
        icon.classList.toggle("bi-lock-fill", !reportTermsEditMode);
        icon.classList.toggle("bi-unlock-fill", reportTermsEditMode);
        icon.title = reportTermsEditMode ? "Заблокировать ввод сроков" : "Разблокировать ввод сроков";
      });
      dateLockIcons().forEach((icon) => {
        if (icon.classList.contains("is-stage-lock-disabled")) return;
        icon.classList.remove("bi-lock");
        icon.classList.toggle("bi-lock-fill", reportTermsEditMode);
        icon.classList.toggle("bi-unlock-fill", !reportTermsEditMode);
        icon.title = reportTermsEditMode ? "Разблокировать ввод дат" : "Заблокировать ввод дат";
      });
    }

    const projectTermFieldNames = [
      "source_data_term",
      "source_data_term_unit",
      "source_data_term_enabled",
      "source_data_date",
      "source_data_date_enabled",
      "service_term_months",
      "preliminary_report_term_unit",
      "service_term_months_enabled",
      "preliminary_report_date",
      "preliminary_report_date_enabled",
      "final_report_term_weeks",
      "final_report_term_unit",
      "final_report_date",
      "final_report_date_enabled",
      "next_stage_delay_days",
      "next_stage_delay_unit",
    ];
    const visibleTermSelectors = {
      source_data_term: ".proposal-stage-source-data-term",
      source_data_term_unit: ".proposal-stage-source-data-term-unit",
      source_data_term_enabled: ".proposal-stage-source-data-term-enabled",
      source_data_date: ".proposal-stage-source-data-date",
      source_data_date_enabled: ".proposal-stage-source-data-date-enabled",
      service_term_months: ".proposal-stage-service-term-months",
      preliminary_report_term_unit: ".proposal-stage-preliminary-term-unit",
      service_term_months_enabled: ".proposal-stage-service-term-months-enabled",
      preliminary_report_date: ".proposal-stage-preliminary-report-date",
      preliminary_report_date_enabled: ".proposal-stage-preliminary-report-date-enabled",
      final_report_term_weeks: ".proposal-stage-final-report-term-weeks",
      final_report_term_unit: ".proposal-stage-final-term-unit",
      final_report_date: ".proposal-stage-final-report-date",
      final_report_date_enabled: ".proposal-stage-final-report-date-enabled",
    };

    function readContractMeta() {
      try {
        return JSON.parse(node.querySelector("#registration-contract-meta")?.textContent || "{}");
      } catch (error) {
        return {};
      }
    }

    function getRegistrationProductRows() {
      return Array.from(node.querySelectorAll(".registration-product-row")).filter(
        (row) => row.dataset.productGroupLabel !== "1"
      );
    }

    function visibleTermControl(row, name) {
      if (name === "next_stage_delay_days") {
        return getStageDelayRowForTermRow(row)?.querySelector(".proposal-stage-next-delay-days") || null;
      }
      if (name === "next_stage_delay_unit") {
        return getStageDelayRowForTermRow(row)?.querySelector(".proposal-stage-delay-unit") || null;
      }
      const selector = visibleTermSelectors[name];
      if (!selector) return null;
      return Array.from(row.querySelectorAll(selector)).find(
        (element) => !element.closest(".registration-stage-project-values")
      ) || null;
    }

    function payloadEnabled(value, fallback) {
      if (value === undefined || value === null || value === "") return fallback;
      return !["0", "false", "off", "no", "нет"].includes(String(value).trim().toLowerCase());
    }

    function matchContractStage(stages, productId, used) {
      if (!productId) return null;
      for (let index = 0; index < stages.length; index += 1) {
        if (used.has(index)) continue;
        if (String(stages[index]?.product_id || "") === String(productId)) {
          used.add(index);
          return stages[index];
        }
      }
      return null;
    }

    function parkProjectTerms(row) {
      if (row.querySelector(".registration-stage-project-values")) return;
      const box = document.createElement("div");
      box.className = "d-none registration-stage-project-values";
      projectTermFieldNames.forEach((name) => {
        const field = visibleTermControl(row, name);
        if (!field?.name) return;
        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = field.name;
        hidden.dataset.field = name;
        hidden.value = field.value;
        field.removeAttribute("name");
        box.appendChild(hidden);
      });
      if (!box.childElementCount) return;
      row.querySelector("td")?.appendChild(box);
    }

    function restoreProjectTerms(row) {
      const box = row.querySelector(".registration-stage-project-values");
      if (box) {
        box.querySelectorAll("[data-field]").forEach((hidden) => {
          const field = visibleTermControl(row, hidden.dataset.field);
          if (!field) return;
          if (field.classList.contains("js-date")) {
            const parsed = parseDate(hidden.value);
            setDateFieldValue(field, parsed ? formatDateIso(parsed) : "");
          } else {
            field.value = hidden.value;
          }
          if (hidden.name) field.name = hidden.name;
        });
        box.remove();
      }
      delete row.dataset.contractTermsLocked;
      row.classList.remove("is-contract-terms-locked");
      row.querySelectorAll(".js-proposal-stage-field-toggle").forEach((toggle) => {
        toggle.disabled = false;
      });
    }

    function writeContractPayload(row, payload, options) {
      const lock = !options || options.lock !== false;
      const assign = (name, value) => {
        const field = visibleTermControl(row, name);
        if (!field) return;
        if (field.classList.contains("js-date")) {
          const parsed = parseDate(value);
          setDateFieldValue(field, parsed ? formatDateIso(parsed) : "");
          return;
        }
        field.value = value === undefined || value === null ? "" : String(value);
      };
      assign("source_data_term", payload.source_data_term);
      assign("source_data_term_unit", payload.source_data_term_unit || "weeks");
      assign("source_data_date", payload.source_data_date);
      assign("service_term_months", payload.service_term_months);
      assign("preliminary_report_term_unit", payload.preliminary_report_term_unit || "months");
      assign("preliminary_report_date", payload.preliminary_report_date);
      assign("final_report_term_weeks", payload.final_report_term_weeks);
      assign("final_report_term_unit", payload.final_report_term_unit || "weeks");
      assign("final_report_date", payload.final_report_date);
      assign("next_stage_delay_days", payload.next_stage_delay_days || 0);
      assign("next_stage_delay_unit", payload.next_stage_delay_unit || "days");
      const delayRow = getStageDelayRowForTermRow(row);
      if (delayRow) {
        const numeric = Number(String(delayRow.querySelector(".proposal-stage-next-delay-days")?.value || "").replace(",", "."));
        delayRow.classList.toggle("d-none", !(Number.isFinite(numeric) && numeric !== 0));
      }
      const enabledFields = [
        ["source_data_term_enabled", ".proposal-stage-source-data-term-toggle", true],
        ["source_data_date_enabled", ".proposal-stage-source-data-date-toggle", true],
        ["service_term_months_enabled", ".proposal-stage-service-term-months-toggle", true],
        ["preliminary_report_date_enabled", ".proposal-stage-preliminary-report-date-toggle", true],
        ["final_report_date_enabled", ".proposal-stage-final-report-date-toggle", true],
      ];
      enabledFields.forEach(([name, toggleSelector, fallback]) => {
        const enabled = payloadEnabled(payload[name], fallback);
        const hidden = visibleTermControl(row, name);
        if (hidden) hidden.value = enabled ? "true" : "false";
        const toggle = row.querySelector(toggleSelector);
        if (toggle) toggle.checked = enabled;
      });
      row.dataset.forceDatesFromTerms = "1";
      if (!lock) return;
      row.dataset.contractTermsLocked = "1";
      row.classList.add("is-contract-terms-locked");
    }

    function contractHeaderForRow(row) {
      let cursor = row?.previousElementSibling;
      while (
        cursor
        && !cursor.classList.contains("proposal-stage-terms-row")
        && !cursor.classList.contains("proposal-stage-terms-total-row")
      ) {
        if (cursor.classList.contains("registration-contract-terms-header")) return cursor;
        cursor = cursor.previousElementSibling;
      }
      return null;
    }

    function buildContractHeader(contractId) {
      const header = document.createElement("tr");
      header.className = "registration-contract-terms-header";
      header.dataset.contractId = contractId;
      header.innerHTML = `
        <td colspan="7">
          <div class="registration-contract-terms-labels">
            <div class="form-label">Дата договора</div>
            <div class="form-label">Договор ID</div>
            <div class="form-label">№ соглашения</div>
            <div class="form-label registration-contract-end-label">Оконч. договора</div>
            <div class="form-label">Оконч., расчет</div>
            <div class="form-label">Срок</div>
          </div>
          <div class="registration-contract-terms-fields">
            <input type="date" class="form-control readonly-field registration-contract-group-date" readonly tabindex="-1" aria-label="Дата договора">
            <input type="text" class="form-control readonly-field registration-contract-group-uid" readonly tabindex="-1" aria-label="Договор ID">
            <input type="text" class="form-control readonly-field registration-contract-group-agreement" readonly tabindex="-1" aria-label="№ соглашения">
            <div class="registration-contract-end-field">
              <input type="date" name="contract_group_end" class="form-control registration-contract-group-end" aria-label="Оконч. договора">
              <input type="hidden" name="contract_group_id" value="">
              <input type="hidden" name="contract_group_end_enabled" class="registration-contract-group-end-enabled" value="true">
              <div class="form-check form-switch proposal-stage-field-toggle">
                <input type="checkbox" class="form-check-input registration-contract-group-end-toggle" role="switch" aria-label="Включить поле Оконч. договора" checked>
              </div>
            </div>
            <input type="text" class="form-control readonly-field registration-contract-group-completion" readonly tabindex="-1" aria-label="Оконч., расчет">
            <div class="form-control readonly-field proposal-stage-final-term-shell">
              <input type="number" class="proposal-stage-final-report-term-weeks registration-contract-group-term" readonly tabindex="-1" aria-label="Срок">
              <select class="form-select proposal-stage-final-term-unit registration-contract-group-term-unit" aria-label="Единица срока">
                <option value="days">дн.</option>
                <option value="weeks" selected>нед.</option>
                <option value="months">мес.</option>
              </select>
            </div>
          </div>
        </td>`;
      return header;
    }

    function renderHeaderTerm(header) {
      if (!header) return;
      const days = Number(header.dataset.termDays || 0);
      const unitSelect = header.querySelector(".registration-contract-group-term-unit");
      const unit = ["days", "weeks", "months"].includes(unitSelect?.value) ? unitSelect.value : "weeks";
      const input = header.querySelector(".registration-contract-group-term");
      if (!input) return;
      input.value = formatPreliminaryTermValue(daysToTermValue(days, unit), unit);
    }

    function headerTermDays(states) {
      return (states || []).reduce((sum, state) => {
        const source = state.sourceDataTermEnabled
          ? termValueToDays(state.sourceDataTerm, state.sourceDataTermUnit)
          : 0;
        const preliminary = state.preliminaryTermEnabled
          ? termValueToDays(state.preliminaryTerm, state.preliminaryTermUnit)
          : 0;
        return sum + source + preliminary + termValueToDays(state.finalTerm, state.finalTermUnit);
      }, 0);
    }

    function updateSingleContractHeader(states) {
      if (settings.groupByContract) return;
      const header = termsTbody.querySelector(".registration-contract-terms-header");
      if (!header) return;
      const lastFinal = [...(states || [])].reverse().find((state) => state.calculatedFinalDate);
      const completion = header.querySelector(".registration-contract-group-completion");
      if (completion) completion.value = lastFinal ? formatDisplayDate(lastFinal.calculatedFinalDate) : "";
      header.dataset.termDays = String(headerTermDays(states));
      renderHeaderTerm(header);
    }

    function formatDisplayDate(date) {
      if (!date) return "";
      const day = String(date.getDate()).padStart(2, "0");
      const month = String(date.getMonth() + 1).padStart(2, "0");
      return `${day}.${month}.${date.getFullYear()}`;
    }

    function applyContractEndToggle(header) {
      if (!header) return;
      const toggle = header.querySelector(".registration-contract-group-end-toggle");
      const hidden = header.querySelector(".registration-contract-group-end-enabled");
      const input = header.querySelector(".registration-contract-group-end");
      const wrap = header.querySelector(".registration-contract-end-field");
      if (!toggle || !input) return;
      const enabled = hidden
        ? String(hidden.value || "true").toLowerCase() !== "false"
        : !!toggle.checked;
      toggle.checked = enabled;
      if (hidden) hidden.value = enabled ? "true" : "false";
      wrap?.classList.toggle("is-stage-field-disabled", !enabled);
      input.readOnly = !enabled;
    }

    function placeContractHeaders(groups) {
      const pool = new Map();
      termsTbody.querySelectorAll(".registration-contract-terms-header").forEach((header) => {
        const id = String(header.dataset.contractId || "");
        if (!pool.has(id)) pool.set(id, []);
        pool.get(id).push(header);
      });
      const columnTemplate = termsTbody.querySelector(".registration-stage-terms-columns")?.cloneNode(true) || null;
      const usedColumns = new Set();
      const knownEnds = new Map();
      groups.forEach((group) => {
        const list = pool.get(group.id) || [];
        let header = list.shift() || null;
        pool.set(group.id, list);
        if (!header) {
          header = buildContractHeader(group.id);
          const endInput = header.querySelector(".registration-contract-group-end");
          const fromRow = group.rows.map((item) => item.row.dataset.contractEnd || "").find(Boolean) || "";
          if (endInput) endInput.value = knownEnds.get(group.id) || fromRow;
        }
        const hidden = header.querySelector('[name="contract_group_id"]');
        if (hidden) hidden.value = group.id;
        header.dataset.contractId = group.id;
        const endInput = header.querySelector(".registration-contract-group-end");
        if (endInput && endInput.value) knownEnds.set(group.id, endInput.value);
        const first = group.rows[0]?.row;
        if (!first) return;
        let columns = first.previousElementSibling;
        if (!columns?.classList.contains("registration-stage-terms-columns")) {
          columns = columnTemplate ? columnTemplate.cloneNode(true) : null;
          if (columns) first.parentNode.insertBefore(columns, first);
        }
        if (columns) {
          usedColumns.add(columns);
          first.parentNode.insertBefore(header, columns);
        } else {
          first.parentNode.insertBefore(header, first);
        }
      });
      pool.forEach((list) => list.forEach((header) => header.remove()));
      termsTbody.querySelectorAll(".registration-stage-terms-columns").forEach((row) => {
        if (!usedColumns.has(row)) row.remove();
      });
      termsTbody.querySelectorAll(".registration-contract-terms-header").forEach(applyContractEndToggle);
    }

    function syncContractGroupOverlay() {
      const meta = readContractMeta();
      const productRows = getRegistrationProductRows();
      const groups = [];
      let current = null;
      getStageTermRows().forEach((row, index) => {
        const productRow = productRows[index];
        const select = productRow?.querySelector(".registration-product-contract-select");
        const contractId = String(
          select?.value
          || productRow?.dataset.selectedContractId
          || row.dataset.contractId
          || ""
        );
        if ((row.dataset.contractId || "") !== contractId) {
          row.dataset.forceDatesFromTerms = "1";
        }
        row.dataset.contractId = contractId;
        const productId = String(
          productRow?.querySelector(".registration-product-select")?.value
          || row.dataset.productId
          || ""
        );
        if (productId) row.dataset.productId = productId;
        if (!current || current.id !== contractId) {
          current = { id: contractId, rows: [] };
          groups.push(current);
        }
        current.rows.push({ row, productId });
      });
      placeContractHeaders(groups);
      groups.forEach((group) => {
        const contract = meta[group.id] || {};
        const signed = Boolean(contract.signed);
        const stages = Array.isArray(contract.stages) ? contract.stages : [];
        const used = new Set();
        const header = contractHeaderForRow(group.rows[0]?.row);
        if (header) {
          if (signed) header.dataset.contractSigned = "1";
          else delete header.dataset.contractSigned;
          const dateInput = header.querySelector(".registration-contract-group-date");
          if (dateInput) dateInput.value = contract.contract_date || "";
          const uidInput = header.querySelector(".registration-contract-group-uid");
          if (uidInput) uidInput.value = contract.short_uid || "";
          const agreementInput = header.querySelector(".registration-contract-group-agreement");
          if (agreementInput) agreementInput.value = contract.agreement_number || "";
        }
        group.rows.forEach((item) => {
          const payload = signed ? matchContractStage(stages, item.productId, used) : null;
          if (payload) {
            parkProjectTerms(item.row);
            writeContractPayload(item.row, payload);
          } else {
            restoreProjectTerms(item.row);
          }
        });
      });
    }

    function syncStageTerms() {
      if (settings.groupByContract) syncContractGroupOverlay();
      const termRows = getStageTermRows();
      const states = termRows.map((row) => {
        const sourceDataTermInput = row.querySelector(".proposal-stage-source-data-term");
        const sourceDataTermUnitSelect = row.querySelector(".proposal-stage-source-data-term-unit");
        const monthsInput = row.querySelector(".proposal-stage-service-term-months");
        const termUnitSelect = row.querySelector(".proposal-stage-preliminary-term-unit");
        const weeksInput = row.querySelector(".proposal-stage-final-report-term-weeks");
        const finalTermUnitSelect = row.querySelector(".proposal-stage-final-term-unit");
        const delayRow = getStageDelayRowForTermRow(row);
        const delayInput = delayRow?.querySelector(".proposal-stage-next-delay-days");
        const delayUnitSelect = delayRow?.querySelector("select.proposal-stage-delay-unit");
        const nextDelayUnit = delayUnitSelect ? getDelayUnit(delayUnitSelect) : "days";
        const nextDelayValue = delayUnitSelect && nextDelayUnit !== "days"
          ? (parseDecimal(delayInput?.value) || 0)
          : (parseInteger(delayInput?.value) || 0);
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
          nextDelayValue,
          nextDelayUnit,
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
        const write = (input, date, enabled) => {
          if (keepDisabledStageDatesVisible && !enabled) {
            if (date) setDateFieldValue(input, formatDateIso(date));
            return;
          }
          setDateFieldValue(input, enabled && date ? formatDateIso(date) : "");
        };
        write(state.sourceDataInput, state.calculatedSourceDataDate, state.sourceDataDateEnabled);
        write(state.preliminaryInput, state.calculatedPreliminaryDate, state.preliminaryDateEnabled);
        write(state.finalInput, state.calculatedFinalDate, state.finalDateEnabled);
      }

      function applyNextStageDelay(date, state) {
        if (!date || !state.nextDelayValue) return date;
        if (!state.nextDelayUnit || state.nextDelayUnit === "days") return addDays(date, state.nextDelayValue);
        return addSourceDataTerm(date, state.nextDelayValue, state.nextDelayUnit);
      }

      function subtractNextStageDelay(date, state) {
        if (!date || !state.nextDelayValue) return date;
        if (!state.nextDelayUnit || state.nextDelayUnit === "days") return addDays(date, -state.nextDelayValue);
        return subtractSourceDataTerm(date, state.nextDelayValue, state.nextDelayUnit);
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
        let cursor = startDate;
        if (state.sourceDataTerm === null) {
          state.calculatedSourceDataDate = null;
        } else {
          state.calculatedSourceDataDate = addSourceDataTerm(
            startDate,
            state.sourceDataTerm,
            state.sourceDataTermUnit
          );
          cursor = state.calculatedSourceDataDate;
        }
        if (state.preliminaryTerm === null) {
          state.calculatedPreliminaryDate = null;
          state.calculatedFinalDate = null;
          return applyNextStageDelay(cursor, state);
        }
        state.calculatedPreliminaryDate = addPreliminaryTerm(
          cursor,
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

      function clearRunDates(runStates) {
        runStates.forEach((state) => {
          state.calculatedSourceDataDate = null;
          state.calculatedPreliminaryDate = null;
          state.calculatedFinalDate = null;
          applyStateDates(state);
          delete state.row.dataset.forceDatesFromTerms;
          delete state.row.dataset.manualDateSource;
        });
      }

      function applyForwardRun(runStates, anchor) {
        if (!anchor) {
          clearRunDates(runStates);
          return;
        }
        let startDate = anchor;
        runStates.forEach((state) => {
          startDate = computeForwardDates(startDate, state);
          applyStateDates(state);
          delete state.row.dataset.forceDatesFromTerms;
          delete state.row.dataset.manualDateSource;
        });
      }

      function applyPreservedRun(runStates, anchor) {
        if (!anchor) {
          clearRunDates(runStates);
          return;
        }
        let baseStartDate = anchor;
        const manualIndex = runStates.findIndex((state) => {
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
          const manualState = runStates[manualIndex];
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
            const state = runStates[index];
            const stageEndDate = rollingStartDate && state.nextDelayValue
              ? subtractNextStageDelay(rollingStartDate, state)
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

          let forwardStartDate = applyNextStageDelay(
            manualState.calculatedFinalDate
              || manualState.calculatedPreliminaryDate
              || manualState.calculatedSourceDataDate
              || manualStageStartDate
              || baseStartDate,
            manualState
          );
          for (let index = manualIndex + 1; index < runStates.length; index += 1) {
            forwardStartDate = computeForwardDates(forwardStartDate, runStates[index]);
          }
          runStates.forEach(applyStateDates);
        } else {
          let startDate = baseStartDate;
          runStates.forEach((state) => {
            const shouldComputeFromTerms = (
              state.shouldForceDatesFromTerms
              || !state.finalDateEnabled
              || (!state.sourceDataDate && !state.preliminaryDate && !state.finalDate)
            );
            if (shouldComputeFromTerms) {
              startDate = computeForwardDates(startDate, state);
              applyStateDates(state);
            } else {
              state.calculatedSourceDataDate = state.sourceDataDate;
              state.calculatedPreliminaryDate = state.preliminaryDate;
              state.calculatedFinalDate = state.finalDate;
              startDate = applyNextStageDelay(
                state.finalDate || state.preliminaryDate || state.sourceDataDate || startDate,
                state
              );
            }
          });
        }

        runStates.forEach((state) => {
          delete state.row.dataset.forceDatesFromTerms;
          delete state.row.dataset.manualDateSource;
        });
      }

      if (settings.groupByContract) {
        const meta = readContractMeta();
        const grouped = [];
        let bucket = null;
        states.forEach((state) => {
          const id = String(state.row.dataset.contractId || "");
          if (!bucket || bucket.id !== id) {
            bucket = { id, states: [] };
            grouped.push(bucket);
          }
          bucket.states.push(state);
        });
        grouped.forEach((group) => {
          const contract = meta[group.id] || {};
          const contractDate = parseDate(contract.contract_date);
          const projectDate = parseDate(getContractStartDateValue());
          const runs = [];
          let run = null;
          group.states.forEach((state) => {
            const locked = state.row.dataset.contractTermsLocked === "1";
            if (!run || run.locked !== locked) {
              run = { locked, states: [] };
              runs.push(run);
            }
            run.states.push(state);
          });
          runs.forEach((item) => {
            if (item.locked || reportTermsEditMode) applyForwardRun(item.states, item.locked ? contractDate : projectDate);
            else applyPreservedRun(item.states, projectDate);
          });
          const header = contractHeaderForRow(group.states[0]?.row);
          if (!header) return;
          const lastFinal = [...group.states].reverse().find((state) => state.calculatedFinalDate);
          const completion = header.querySelector(".registration-contract-group-completion");
          if (completion) completion.value = lastFinal ? formatDisplayDate(lastFinal.calculatedFinalDate) : "";
          const days = group.states.reduce((sum, state) => {
            const source = state.sourceDataTermEnabled
              ? termValueToDays(state.sourceDataTerm, state.sourceDataTermUnit)
              : 0;
            const preliminary = state.preliminaryTermEnabled
              ? termValueToDays(state.preliminaryTerm, state.preliminaryTermUnit)
              : 0;
            return sum + source + preliminary + termValueToDays(state.finalTerm, state.finalTermUnit);
          }, 0);
          header.dataset.termDays = String(days);
          renderHeaderTerm(header);
        });
        updateTotals();
        applyLockState();
        return;
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
        updateSingleContractHeader(states);
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
            const stageEndDate = rollingStartDate && state.nextDelayValue
              ? subtractNextStageDelay(rollingStartDate, state)
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
              state.calculatedSourceDataDate = state.sourceDataDate;
              state.calculatedPreliminaryDate = state.preliminaryDate;
              state.calculatedFinalDate = state.finalDate;
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

      updateSingleContractHeader(states);
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
        const evaluationDate = row.querySelector(".proposal-stage-evaluation-date");
        ["input", "change"].forEach((eventName) => {
          evaluationDate?.addEventListener(eventName, () => {
            if (row !== getStageEvaluationRows()[0]) return;
            applyEvaluationCommonMode();
          });
        });
        row.querySelectorAll(".js-proposal-stage-field-toggle").forEach((toggle) => {
          toggle.addEventListener("change", () => {
            setFieldToggleValue(row, toggle, toggle.checked, { clear: true });
            syncStageEvaluationDates();
            if (row === getStageEvaluationRows()[0]) applyEvaluationCommonMode();
          });
        });
      });
      syncStageEvaluationDates();
      bindEvaluationCommonToggle();
      applyEvaluationCommonMode();
    }

    function bindStageDelayRows() {
      getStageDelayRows().forEach((row) => {
        if (row.dataset.eventsBound === "1") return;
        row.dataset.eventsBound = "1";
        const input = row.querySelector(".proposal-stage-next-delay-days");
        const unitSelect = row.querySelector("select.proposal-stage-delay-unit");
        const syncDelay = (eventName) => {
          if (eventName === "change") {
            if (unitSelect) normalizeSourceDataTermInput(input, getDelayUnit(unitSelect));
            else normalizeIntegerInput(input);
          }
          const termRows = getStageTermRows();
          const sourceIndex = termRows.indexOf(row.previousElementSibling);
          if (sourceIndex >= 0) {
            termRows.slice(sourceIndex + 1).forEach((termRow) => {
              termRow.dataset.forceDatesFromTerms = "1";
            });
          }
          syncStageTerms();
        };
        ["input", "change"].forEach((eventName) => {
          input?.addEventListener(eventName, () => syncDelay(eventName));
          unitSelect?.addEventListener(eventName, () => syncDelay(eventName));
        });
        if (unitSelect) normalizeSourceDataTermInput(input, getDelayUnit(unitSelect));
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

    if (settings.groupByContract && node.dataset.contractGroupTermsBound !== "1") {
      node.dataset.contractGroupTermsBound = "1";
      node.addEventListener("change", (event) => {
        if (event.target?.classList?.contains("registration-product-contract-select")) {
          syncStageTerms();
        }
      });
    }
    if (termsTbody.querySelector(".registration-contract-terms-header") && node.dataset.contractHeaderTermsBound !== "1") {
      node.dataset.contractHeaderTermsBound = "1";
      termsTbody.addEventListener("change", (event) => {
        const endToggle = event.target?.closest?.(".registration-contract-group-end-toggle");
        if (endToggle) {
          const header = endToggle.closest(".registration-contract-terms-header");
          const hidden = header?.querySelector(".registration-contract-group-end-enabled");
          if (hidden) hidden.value = endToggle.checked ? "true" : "false";
          applyContractEndToggle(header);
          return;
        }
        const unitSelect = event.target?.closest?.(".registration-contract-group-term-unit");
        if (unitSelect) {
          renderHeaderTerm(unitSelect.closest(".registration-contract-terms-header"));
          return;
        }
        const endInput = event.target?.closest?.(".registration-contract-group-end");
        if (!endInput) return;
        endInput.dataset.endTouched = "1";
        const contractId = endInput.closest(".registration-contract-terms-header")?.dataset.contractId || "";
        termsTbody.querySelectorAll(".registration-contract-terms-header").forEach((header) => {
          if ((header.dataset.contractId || "") !== contractId) return;
          const input = header.querySelector(".registration-contract-group-end");
          if (input && input !== endInput) input.value = endInput.value;
        });
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

    node.addEventListener("click", (event) => {
      const icon = event.target.closest(".js-proposal-report-terms-lock, .js-proposal-report-date-lock");
      if (!icon || !node.contains(icon)) return;
      if (icon.classList.contains("is-stage-lock-disabled")) return;
      reportTermsEditMode = !reportTermsEditMode;
      applyLockState();
      getStageTermRows().forEach((row) => {
        row.dataset.forceDatesFromTerms = "1";
      });
      syncStageTerms();
    });

    termsTbody.addEventListener("click", (event) => {
      const removeButton = event.target.closest(".proposal-stage-delay-remove");
      if (removeButton) {
        const delayRow = removeButton.closest(".proposal-stage-delay-row");
        if (delayRow?.previousElementSibling?.dataset.contractTermsLocked === "1") return;
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
      if (!termRow || termRow.dataset.contractTermsLocked === "1") return;
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

    function contractIdForProductRow(productRow, fallbackRow) {
      const select = productRow?.querySelector(".registration-product-contract-select");
      return String(
        select?.value
        || productRow?.dataset.selectedContractId
        || fallbackRow?.dataset.contractId
        || ""
      );
    }

    function applyUnsignedContractTerms() {
      const meta = readContractMeta();
      const productRows = getRegistrationProductRows();
      const usedByContract = new Map();
      getStageTermRows().forEach((row, index) => {
        if (row.dataset.contractTermsLocked === "1") return;
        const productRow = productRows[index];
        const contractId = contractIdForProductRow(productRow, row);
        const contract = meta[contractId] || {};
        if (contract.signed) return;
        const stages = Array.isArray(contract.stages) ? contract.stages : [];
        if (!usedByContract.has(contractId)) usedByContract.set(contractId, new Set());
        const productId = String(
          productRow?.querySelector(".registration-product-select")?.value
          || row.dataset.productId
          || ""
        );
        const payload = matchContractStage(stages, productId, usedByContract.get(contractId));
        if (!payload) return;
        writeContractPayload(row, payload, { lock: false });
      });
    }

    function applyContractEndsFromMeta() {
      const meta = readContractMeta();
      termsTbody.querySelectorAll(".registration-contract-terms-header").forEach((header) => {
        const contract = meta[header.dataset.contractId || ""] || {};
        if (!Object.prototype.hasOwnProperty.call(contract, "contract_end")
          && !Object.prototype.hasOwnProperty.call(contract, "contract_end_enabled")) {
          return;
        }
        const endInput = header.querySelector(".registration-contract-group-end");
        if (endInput) endInput.value = contract.contract_end || "";
        const hidden = header.querySelector(".registration-contract-group-end-enabled");
        const enabled = payloadEnabled(contract.contract_end_enabled, true);
        if (hidden) hidden.value = enabled ? "true" : "false";
        applyContractEndToggle(header);
      });
    }

    function applyEvaluationFromContracts() {
      const meta = readContractMeta();
      const productRows = getRegistrationProductRows();
      const usedByContract = new Map();
      const commonByContract = new Map();
      getStageEvaluationRows().forEach((row, index) => {
        const productRow = productRows[index];
        const contractId = contractIdForProductRow(productRow, row);
        const contract = meta[contractId] || {};
        const stages = Array.isArray(contract.stages) ? contract.stages : [];
        if (!usedByContract.has(contractId)) usedByContract.set(contractId, new Set());
        const productId = String(
          productRow?.querySelector(".registration-product-select")?.value
          || row.dataset.productId
          || ""
        );
        const payload = matchContractStage(stages, productId, usedByContract.get(contractId));
        if (!payload) return;
        const dateInput = row.querySelector(".proposal-stage-evaluation-date");
        if (dateInput && payload.evaluation_date !== undefined && payload.evaluation_date !== null) {
          const parsed = parseDate(payload.evaluation_date);
          setDateFieldValue(dateInput, parsed ? formatDateIso(parsed) : "");
        }
        if (payload.evaluation_date_enabled !== undefined && payload.evaluation_date_enabled !== "") {
          const enabled = payloadEnabled(payload.evaluation_date_enabled, true);
          const hidden = row.querySelector(".proposal-stage-evaluation-date-enabled");
          const toggle = row.querySelector(".proposal-stage-evaluation-date-toggle");
          if (hidden) hidden.value = enabled ? "true" : "false";
          if (toggle) toggle.checked = enabled;
        }
        if (payload.evaluation_date_common !== undefined && payload.evaluation_date_common !== "") {
          commonByContract.set(contractId, payloadEnabled(payload.evaluation_date_common, false));
        }
      });
      if (commonByContract.size) {
        const toggle = evaluationCommonToggle();
        if (toggle) toggle.checked = [...commonByContract.values()].every(Boolean);
      }
    }

    function refreshFromContracts() {
      if (!settings.groupByContract) return;
      syncContractGroupOverlay();
      applyUnsignedContractTerms();
      applyEvaluationFromContracts();
      getStageTermRows().forEach((row) => applyStageFieldToggleState(row, { clear: false }));
      getStageEvaluationRows().forEach((row) => applyStageFieldToggleState(row, { clear: false }));
      bindTermsRows();
      bindEvaluationRows();
      bindStageDelayRows();
      applyLockState();
      syncStageEvaluationDates();
      bindEvaluationCommonToggle();
      applyEvaluationCommonMode();
      syncStageTerms();
      applyContractEndsFromMeta();
    }

    termsTbody.querySelectorAll(".registration-contract-terms-header").forEach(applyContractEndToggle);
    fitReportTermsTable(node);
    bindRegistrationTermsColumnToggles(node);

    node.__contractStageTermsApi = {
      sync() {
        bindTermsRows();
        bindEvaluationRows();
        bindStageDelayRows();
        bindTotalsRow();
        applyLockState();
        syncStageEvaluationDates();
        bindEvaluationCommonToggle();
        applyEvaluationCommonMode();
        syncStageTerms();
        fitReportTermsTable(node);
      },
      refreshFromContracts,
    };

    bindTermsRows();
    bindEvaluationRows();
    bindStageDelayRows();
    bindTotalsRow();
    applyLockState();
    syncStageEvaluationDates();
    bindEvaluationCommonToggle();
    applyEvaluationCommonMode();
    syncStageTerms();
    fitReportTermsTable(node);
  }

  const registrationTermsColumnToggles = {
    "source-date": {
      collapsedClass: "is-source-date-collapsed",
      label: "Исходные данные (дата)",
    },
    "preliminary-date": {
      collapsedClass: "is-preliminary-date-collapsed",
      label: "Предварительный отчёт (дата)",
    },
    "final-date": {
      collapsedClass: "is-final-date-collapsed",
      label: "Итоговый отчёт (дата)",
    },
  };

  function registrationTermsColumnsStorageKey(editor) {
    const projectKey = (editor.dataset.termsProjectKey || "").trim();
    return projectKey ? "registration-terms-columns:" + projectKey : "";
  }

  function applyRegistrationTermsColumn(editor, column, collapsed) {
    const cfg = registrationTermsColumnToggles[column];
    if (!cfg) return;
    editor.classList.toggle(cfg.collapsedClass, !!collapsed);
    const title = collapsed
      ? "Развернуть столбец «" + cfg.label + "»"
      : "Свернуть столбец «" + cfg.label + "»";
    editor.querySelectorAll('.registration-terms-column-toggle[data-terms-column="' + column + '"]').forEach((item) => {
      item.setAttribute("aria-expanded", collapsed ? "false" : "true");
      item.title = title;
      item.setAttribute("aria-label", title);
    });
  }

  function restoreRegistrationTermsColumns(editor) {
    const storageKey = registrationTermsColumnsStorageKey(editor);
    if (!storageKey || !window.UIPref) return;
    const state = window.UIPref.get(storageKey, null);
    if (!state || typeof state !== "object") return;
    Object.keys(registrationTermsColumnToggles).forEach((column) => {
      if (typeof state[column] === "boolean") applyRegistrationTermsColumn(editor, column, state[column]);
    });
  }

  function persistRegistrationTermsColumns(editor) {
    const storageKey = registrationTermsColumnsStorageKey(editor);
    if (!storageKey || !window.UIPref) return;
    const state = {};
    Object.keys(registrationTermsColumnToggles).forEach((column) => {
      state[column] = editor.classList.contains(registrationTermsColumnToggles[column].collapsedClass);
    });
    window.UIPref.set(storageKey, state);
  }

  function bindRegistrationTermsColumnToggles(root) {
    const editor = root?.querySelector?.(".proposal-terms-editor");
    if (!editor || editor.dataset.termsColumnToggleBound === "1") return;
    editor.dataset.termsColumnToggleBound = "1";
    restoreRegistrationTermsColumns(editor);
    editor.addEventListener("click", (event) => {
      const button = event.target.closest(".registration-terms-column-toggle");
      if (!button || !editor.contains(button)) return;
      event.preventDefault();
      const column = button.dataset.termsColumn;
      if (!registrationTermsColumnToggles[column]) return;
      const collapsed = !editor.classList.contains(registrationTermsColumnToggles[column].collapsedClass);
      applyRegistrationTermsColumn(editor, column, collapsed);
      persistRegistrationTermsColumns(editor);
    });
  }

  function initRegistrationStageTerms(root) {
    const scope = root instanceof Element || root instanceof Document ? root : document;
    const forms = [];
    if (scope instanceof Element && scope.matches("form[data-registration-form]")) forms.push(scope);
    scope.querySelectorAll("form[data-registration-form]").forEach((form) => forms.push(form));
    if (!forms.length && document.querySelector("form[data-registration-form]")) {
      forms.push(document.querySelector("form[data-registration-form]"));
    }
    forms.forEach((form) => {
      if (!form.querySelector("#registration-stage-terms-tbody")) return;
      if (form.dataset.contractStageTermsBound !== "1") {
        attachContractStageTerms(form, {
          termsTbodySelector: "#registration-stage-terms-tbody",
          evaluationTbodySelector: "#registration-stage-evaluation-tbody",
          anchorSelector: '[name="project_start_date"]',
          groupByContract: true,
        });
      }
      bindRegistrationTermsColumnToggles(form);
    });
  }

  window.attachContractStageTerms = attachContractStageTerms;
  document.addEventListener("DOMContentLoaded", () => initRegistrationStageTerms(document));
  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.target;
    initRegistrationStageTerms(target instanceof Element ? target : document);
  });
})();
