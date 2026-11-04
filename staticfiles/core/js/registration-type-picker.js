(function () {
function attachRegistrationProducts(node) {
  if (!node) return;
  const container = node.querySelector("#registration-products-container");
  const addBtn = node.querySelector("#registration-add-product");
  const metaEl = node.querySelector("#registration-type-meta");
  if (!container || !metaEl || container.dataset.bound === "1") return;
  container.dataset.bound = "1";

  const isContractProposalTermsMode = Boolean(
    node.querySelector("#contract-stage-terms-tbody, #registration-stage-terms-tbody")
  );
  const isProjectRegistrationTerms = Boolean(node.querySelector("#registration-stage-terms-tbody"));
  const usesRegistryStageTerms = isProjectRegistrationTerms || Boolean(node.querySelector("#contract-stage-terms-tbody"));
  const isRegistrationGroupEdit = node.dataset.groupEdit === "1";
  const hasRegistrationContracts = Boolean(node.querySelector("#registration-contracts-container"));
  const termsConfig = isContractProposalTermsMode ? {
    termRowSelector: ".proposal-stage-terms-row",
    delayRowSelector: ".proposal-stage-delay-row",
    totalRowSelector: ".proposal-stage-terms-total-row",
    stageLabelSelector: ".proposal-stage-label-input",
    sourceDataTermSelector: ".proposal-stage-source-data-term",
    sourceDataTermUnitSelector: ".proposal-stage-source-data-term-unit",
    sourceDataDateSelector: ".proposal-stage-source-data-date",
    monthsSelector: ".proposal-stage-service-term-months",
    preliminaryTermUnitSelector: ".proposal-stage-preliminary-term-unit",
    weeksSelector: ".proposal-stage-final-report-term-weeks",
    finalTermUnitSelector: ".proposal-stage-final-term-unit",
    preliminarySelector: ".proposal-stage-preliminary-report-date",
    finalSelector: ".proposal-stage-final-report-date",
    delayInputSelector: ".proposal-stage-next-delay-days",
    delayActionSlotSelector: ".proposal-stage-delay-action-slot",
    delayAddClass: "proposal-stage-delay-add",
    delayRemoveClass: "proposal-stage-delay-remove",
    finalReportWrapClass: "proposal-stage-final-report-wrap",
    delayRowClass: "proposal-stage-delay-row",
    delayColspan: 5,
    evaluationRowSelector: ".proposal-stage-evaluation-row",
    getEvaluationTbody: () => node.querySelector("#contract-stage-evaluation-tbody, #registration-stage-evaluation-tbody"),
    getTbody: () => node.querySelector("#contract-stage-terms-tbody, #registration-stage-terms-tbody"),
  } : {
    termRowSelector: ".registration-contract-terms-row",
    delayRowSelector: ".registration-stage-delay-row",
    totalRowSelector: ".registration-contract-terms-total-row",
    stageLabelSelector: ".registration-contract-stage-label-input",
    sourceDataTermSelector: "",
    sourceDataTermUnitSelector: "",
    sourceDataDateSelector: "",
    monthsSelector: "[name='stage1_weeks']",
    preliminaryTermUnitSelector: "",
    weeksSelector: "[name='stage2_weeks']",
    finalTermUnitSelector: "",
    preliminarySelector: ".js-stage1-date",
    finalSelector: ".js-stage2-end",
    delayInputSelector: ".registration-stage-next-delay-days",
    delayActionSlotSelector: ".registration-stage-delay-action-slot",
    delayAddClass: "registration-stage-delay-add",
    delayRemoveClass: "registration-stage-delay-remove",
    finalReportWrapClass: "registration-stage-final-report-wrap",
    delayRowClass: "registration-stage-delay-row",
    delayColspan: 3,
    evaluationRowSelector: "",
    getEvaluationTbody: () => null,
    getTbody: () => node.querySelector(".registration-contract-terms-table tbody"),
  };

  let meta = {};
  try {
    meta = JSON.parse(metaEl.textContent || "{}");
  } catch (error) {
    meta = {};
  }
  const products = Array.isArray(meta.products) ? meta.products : [];
  const consultingTypes = Array.isArray(meta.consulting_types) ? meta.consulting_types : [];
  const serviceCategories = Array.isArray(meta.service_categories) ? meta.service_categories : [];
  const productById = new Map(products.map((product) => [String(product.id), product]));

  const getProductRows = () => Array.from(container.querySelectorAll(".registration-product-row")).filter(
    (row) => row.dataset.productGroupLabel !== "1"
  );
  const getTermsTbody = () => termsConfig.getTbody();
  const getEvaluationTbody = () => termsConfig.getEvaluationTbody();
  const getTermsRows = () => Array.from(node.querySelectorAll(termsConfig.termRowSelector));
  const getEvaluationRows = () => termsConfig.evaluationRowSelector
    ? Array.from(node.querySelectorAll(termsConfig.evaluationRowSelector))
    : [];
  const getStageDelayRows = () => Array.from(node.querySelectorAll(termsConfig.delayRowSelector));
  const getTermsTotalRow = () => node.querySelector(termsConfig.totalRowSelector);

  const parseTermDecimal = (value) => {
    const raw = String(value || "").trim().replace(/\s+/g, "").replace(",", ".");
    if (!raw) return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const formatTermDecimal = (value) => (
    Number.isFinite(value) ? (Math.round(value * 10) / 10).toFixed(1) : ""
  );

  const termValueToDays = (value, unit) => {
    const safeValue = Number.isFinite(value) ? Math.max(value, 0) : 0;
    if (unit === "days") return Math.round(safeValue);
    if (unit === "months") return safeValue * 30;
    return safeValue * 7;
  };

  const daysToTermValue = (days, unit) => {
    const safeDays = Number.isFinite(days) ? Math.max(days, 0) : 0;
    if (unit === "days") return Math.round(safeDays);
    if (unit === "months") return safeDays / 30;
    return safeDays / 7;
  };

  const termValueForUnit = (value, sourceUnit, targetUnit) => {
    const parsed = parseTermDecimal(value);
    if (parsed === null) return "";
    const normalizedSourceUnit = ["days", "weeks", "months"].includes(sourceUnit) ? sourceUnit : targetUnit;
    return formatTermDecimal(daysToTermValue(termValueToDays(parsed, normalizedSourceUnit), targetUnit));
  };

  const createStageDelayRow = () => {
    const row = document.createElement("tr");
    row.className = `${termsConfig.delayRowClass} d-none`;
    const fieldHtml = usesRegistryStageTerms
      ? [
          `<div class="proposal-stage-field-toggle-wrap proposal-stage-delay-input-wrap">`,
          `<div class="form-control proposal-stage-delay-number-shell">`,
          `<input type="number" name="next_stage_delay_days" min="0" step="0.1" inputmode="decimal" class="${termsConfig.delayInputSelector.slice(1)}" value="">`,
          `<select name="next_stage_delay_unit" class="form-select proposal-stage-delay-unit" aria-label="Единица лага">`,
          `<option value="days" selected>дн.</option>`,
          `<option value="weeks">нед.</option>`,
          `<option value="months">мес.</option>`,
          `</select>`,
          `</div>`,
          `<button type="button" class="btn btn-sm ${termsConfig.delayRemoveClass}" title="Удалить лаг" aria-label="Удалить лаг">&times;</button>`,
          `</div>`,
        ].join("")
      : [
          `<div class="${isContractProposalTermsMode ? "proposal-stage-delay-input-wrap" : "registration-stage-delay-input-wrap"}">`,
          `<div class="${isContractProposalTermsMode ? "proposal-stage-delay-number-shell" : "registration-stage-delay-number-shell"}">`,
          `<input type="number" name="next_stage_delay_days" step="1" inputmode="numeric" class="form-control ${termsConfig.delayInputSelector.slice(1)}" value="">`,
          `<span class="${isContractProposalTermsMode ? "proposal-stage-delay-unit" : "registration-stage-delay-unit"}" aria-hidden="true">дн.</span>`,
          `</div>`,
          `<button type="button" class="btn btn-sm ${termsConfig.delayRemoveClass}" title="Удалить лаг" aria-label="Удалить лаг">&times;</button>`,
          `</div>`,
        ].join("");
    row.innerHTML = [
      `<td class="${isContractProposalTermsMode ? "proposal-terms-stage-col" : "registration-contract-terms-stage-col"}">`,
      `<input type="text" class="form-control readonly-field ${termsConfig.stageLabelSelector.slice(1)}" value="Лаг" readonly tabindex="-1">`,
      "</td>",
      "<td>",
      fieldHtml,
      "</td>",
      `<td colspan="${termsConfig.delayColspan}"></td>`,
    ].join("");
    return row;
  };

  const getStageDelayRowForTermRow = (row) => {
    const nextRow = row?.nextElementSibling;
    return nextRow?.classList?.contains(termsConfig.delayRowClass) ? nextRow : null;
  };

  const getStageDelayActionSlot = (row) => {
    let slot = row.querySelector(termsConfig.delayActionSlotSelector);
    if (slot) return slot;
    const finalInput = row.querySelector(termsConfig.finalSelector);
    const finalCell = finalInput?.closest("td");
    if (!finalCell) return null;
    let wrap = finalCell.querySelector(`.${termsConfig.finalReportWrapClass}`);
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = termsConfig.finalReportWrapClass;
      finalCell.appendChild(wrap);
      wrap.appendChild(finalInput);
    }
    slot = document.createElement("span");
    slot.className = termsConfig.delayActionSlotSelector.slice(1);
    wrap.appendChild(slot);
    return slot;
  };

  const cloneTermsRow = (row) => {
    const clone = row.cloneNode(true);
    delete clone.dataset.eventsBound;
    delete clone.dataset.productId;
    delete clone.dataset.forceDatesFromTerms;
    delete clone.dataset.manualDateSource;
    delete clone.dataset.contractTermsLocked;
    delete clone.dataset.contractId;
    delete clone.dataset.contractEnd;
    clone.classList.remove("is-contract-terms-locked");
    clone.querySelector(".registration-stage-project-values")?.remove();
    const registrationToggleStartsOff = (input) => usesRegistryStageTerms && (
      input.classList.contains("proposal-stage-source-data-term-toggle")
      || input.classList.contains("proposal-stage-source-data-date-toggle")
      || input.classList.contains("proposal-stage-preliminary-report-date-toggle")
      || input.classList.contains("proposal-stage-final-report-date-toggle")
      || input.classList.contains("proposal-stage-source-data-term-enabled")
      || input.classList.contains("proposal-stage-source-data-date-enabled")
      || input.classList.contains("proposal-stage-preliminary-report-date-enabled")
      || input.classList.contains("proposal-stage-final-report-date-enabled")
    );
    clone.querySelectorAll("input").forEach((input) => {
      delete input.dataset.hasPicker;
      if (input.type === "checkbox") {
        input.checked = !registrationToggleStartsOff(input);
        return;
      }
      if (input.type === "hidden" && input.name && input.name.endsWith("_enabled")) {
        input.value = registrationToggleStartsOff(input) ? "false" : "true";
        return;
      }
      if (!input.classList.contains(termsConfig.stageLabelSelector.slice(1))) {
        input.value = "";
      }
    });
    if (termsConfig.preliminaryTermUnitSelector) {
      const unitSelect = clone.querySelector(termsConfig.preliminaryTermUnitSelector);
      if (unitSelect) unitSelect.value = "months";
    }
    if (termsConfig.sourceDataTermUnitSelector) {
      const unitSelect = clone.querySelector(termsConfig.sourceDataTermUnitSelector);
      if (unitSelect) unitSelect.value = "weeks";
    }
    if (termsConfig.finalTermUnitSelector) {
      const unitSelect = clone.querySelector(termsConfig.finalTermUnitSelector);
      if (unitSelect) unitSelect.value = "weeks";
    }
    clone.querySelector(termsConfig.delayActionSlotSelector)?.replaceChildren();
    return clone;
  };

  const cloneEvaluationRow = (row) => {
    const clone = row.cloneNode(true);
    delete clone.dataset.eventsBound;
    delete clone.dataset.productId;
    clone.classList.remove("d-none");
    const common = clone.querySelector(".registration-evaluation-common");
    if (common) {
      common.closest("td")?.classList.remove("registration-evaluation-common-cell");
      common.remove();
    }
    clone.querySelectorAll("input").forEach((input) => {
      delete input.dataset.hasPicker;
      if (input.type === "checkbox") {
        input.checked = true;
        return;
      }
      if (input.type === "hidden" && input.name && input.name.endsWith("_enabled")) {
        input.value = "true";
        return;
      }
      if (!input.classList.contains(termsConfig.stageLabelSelector.slice(1))) {
        input.value = "";
      }
    });
    return clone;
  };

  const syncRegistrationStageTerms = () => {
    if (node.__contractStageTermsApi) {
      node.__contractStageTermsApi.sync();
      return;
    }
    if (node.__registrationStageCalculatorApi) {
      node.__registrationStageCalculatorApi.sync();
    }
  };

  const isStageFieldEnabled = (row, selector) => {
    if (!selector) return true;
    const hidden = row.querySelector(selector);
    return String(hidden?.value || "true").toLowerCase() !== "false";
  };

  const ensureEvaluationRows = () => {
    const tbody = getEvaluationTbody();
    if (!tbody) return;
    let evaluationRows = getEvaluationRows();
    const productRows = getProductRows();
    while (evaluationRows.length < productRows.length && evaluationRows.length) {
      tbody.appendChild(cloneEvaluationRow(evaluationRows[evaluationRows.length - 1]));
      evaluationRows = getEvaluationRows();
    }
    while (evaluationRows.length > productRows.length && evaluationRows.length > 1) {
      evaluationRows[evaluationRows.length - 1].remove();
      evaluationRows = getEvaluationRows();
    }
  };

  const ensureTermsRows = () => {
    const tbody = getTermsTbody();
    const totalRow = getTermsTotalRow();
    if (!tbody || !totalRow) return;
    let termRows = getTermsRows();
    const productRows = getProductRows();
    while (termRows.length < productRows.length && termRows.length) {
      tbody.insertBefore(cloneTermsRow(termRows[termRows.length - 1]), totalRow);
      termRows = getTermsRows();
    }
    while (termRows.length > productRows.length && termRows.length > 1) {
      const removedRow = termRows[termRows.length - 1];
      const prevRow = termRows[termRows.length - 2];
      getStageDelayRowForTermRow(prevRow)?.remove();
      removedRow.remove();
      termRows = getTermsRows();
    }
    if (totalRow) {
      totalRow.classList.toggle("d-none", getProductRows().length <= 1);
    }
  };

  const ensureStageDelayRows = () => {
    const tbody = getTermsTbody();
    if (!tbody) return;
    const termRows = getTermsRows();
    const expectedDelayRows = new Set();
    termRows.forEach((row, index) => {
      const isEligible = termRows.length > 1 && index < termRows.length - 1;
      const actionSlot = getStageDelayActionSlot(row);
      let delayRow = getStageDelayRowForTermRow(row);
      if (isEligible) {
        if (!delayRow) {
          delayRow = createStageDelayRow();
          tbody.insertBefore(delayRow, row.nextSibling);
        }
        expectedDelayRows.add(delayRow);
        const button = actionSlot?.querySelector(`.${termsConfig.delayAddClass}`) || document.createElement("button");
        if (!button.classList.contains(termsConfig.delayAddClass)) {
          button.type = "button";
          button.className = `btn btn-sm rounded-circle ${termsConfig.delayAddClass}`;
          button.innerHTML = '<i class="bi bi-plus" aria-hidden="true"></i>';
          actionSlot?.appendChild(button);
        }
        button.title = "Добавить задержку/наложение";
        button.setAttribute("aria-label", "Добавить задержку или наложение после этапа " + (index + 1));
        button.classList.remove("d-none");
      } else {
        if (actionSlot) actionSlot.innerHTML = "";
        if (delayRow) delayRow.remove();
      }
    });
    getStageDelayRows().forEach((row) => {
      if (!expectedDelayRows.has(row)) row.remove();
    });
  };

  const syncTermsRowsWithProducts = () => {
    ensureTermsRows();
    ensureEvaluationRows();
    const termRows = getTermsRows();
    const evaluationRows = getEvaluationRows();
    getProductRows().forEach((productRow, index) => {
      const termRow = termRows[index];
      if (!termRow) return;
      const evaluationRow = evaluationRows[index];
      const productId = String(productRow.querySelector(".registration-product-select")?.value || "").trim();
      const product = productById.get(productId);
      const previousProductId = String(termRow.dataset.productId || "");
      const stageInput = termRow.querySelector(termsConfig.stageLabelSelector);
      const evaluationStageInput = evaluationRow?.querySelector(termsConfig.stageLabelSelector);
      const sourceDataTermInput = termsConfig.sourceDataTermSelector
        ? termRow.querySelector(termsConfig.sourceDataTermSelector)
        : null;
      const sourceDataTermUnitSelect = termsConfig.sourceDataTermUnitSelector
        ? termRow.querySelector(termsConfig.sourceDataTermUnitSelector)
        : null;
      const monthsInput = termRow.querySelector(termsConfig.monthsSelector);
      const preliminaryTermUnitSelect = termsConfig.preliminaryTermUnitSelector
        ? termRow.querySelector(termsConfig.preliminaryTermUnitSelector)
        : null;
      const weeksInput = termRow.querySelector(termsConfig.weeksSelector);
      const finalTermUnitSelect = termsConfig.finalTermUnitSelector
        ? termRow.querySelector(termsConfig.finalTermUnitSelector)
        : null;
      const writeStageLabel = (input, value) => {
        if (!input) return;
        input.value = value;
        const compact = input.parentElement?.querySelector(".proposal-stage-label-compact");
        if (!compact) return;
        const match = String(value).match(/^Этап\s+(\d+)$/);
        compact.textContent = match ? match[1] : value;
      };
      writeStageLabel(stageInput, "Этап " + (index + 1));
      writeStageLabel(evaluationStageInput, "Этап " + (index + 1));
      const terms = product?.typical_service_terms || {};
      if (!productId && previousProductId) {
        if (sourceDataTermInput) sourceDataTermInput.value = "";
        if (sourceDataTermUnitSelect) sourceDataTermUnitSelect.value = "weeks";
        if (monthsInput) monthsInput.value = "";
        if (preliminaryTermUnitSelect) preliminaryTermUnitSelect.value = "months";
        if (weeksInput) weeksInput.value = "";
        if (finalTermUnitSelect) finalTermUnitSelect.value = "weeks";
        const sourceDataDateInput = termsConfig.sourceDataDateSelector
          ? termRow.querySelector(termsConfig.sourceDataDateSelector)
          : null;
        const preliminaryInput = termRow.querySelector(termsConfig.preliminarySelector);
        const finalInput = termRow.querySelector(termsConfig.finalSelector);
        if (sourceDataDateInput) sourceDataDateInput.value = "";
        if (preliminaryInput) preliminaryInput.value = "";
        if (finalInput) finalInput.value = "";
        termRow.dataset.forceDatesFromTerms = "1";
      }
      if (productId && productId !== previousProductId) {
        if (
          sourceDataTermInput
          && terms.source_data_weeks !== undefined
          && isStageFieldEnabled(termRow, ".proposal-stage-source-data-term-enabled")
        ) {
          sourceDataTermInput.value = terms.source_data_weeks || "";
        }
        if (sourceDataTermUnitSelect) sourceDataTermUnitSelect.value = terms.source_data_term_unit || "weeks";
        if (
          monthsInput
          && terms.preliminary_report_months !== undefined
          && isStageFieldEnabled(termRow, ".proposal-stage-service-term-months-enabled")
        ) {
          monthsInput.value = isContractProposalTermsMode
            ? (terms.preliminary_report_months || "")
            : termValueForUnit(
                terms.preliminary_report_months,
                terms.preliminary_report_term_unit || "months",
                "months"
              );
        }
        if (preliminaryTermUnitSelect) preliminaryTermUnitSelect.value = terms.preliminary_report_term_unit || "months";
        if (weeksInput && terms.final_report_weeks !== undefined) {
          weeksInput.value = isContractProposalTermsMode
            ? (terms.final_report_weeks || "")
            : termValueForUnit(terms.final_report_weeks, terms.final_report_term_unit || "weeks", "weeks");
        }
        if (finalTermUnitSelect) finalTermUnitSelect.value = terms.final_report_term_unit || "weeks";
        termRow.dataset.forceDatesFromTerms = "1";
      }
      termRow.dataset.productId = productId;
      if (evaluationRow) evaluationRow.dataset.productId = productId;
    });
    ensureStageDelayRows();
    syncRegistrationStageTerms();
    if (typeof window.syncContractPaymentStageBlocks === "function") {
      window.syncContractPaymentStageBlocks(node);
    }
    if (typeof window.syncContractServiceStageBlocks === "function") {
      window.syncContractServiceStageBlocks(node);
    }
  };

  const uniqueValues = (items) => {
    const seen = new Set();
    return items.filter((item) => {
      const value = String(item || "").trim();
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    });
  };

  const buildOptions = (select, items, placeholder, selectedValue, mapper) => {
    if (!select) return;
    const normalizedSelected = String(selectedValue || "");
    select.innerHTML = "";
    if (placeholder) {
      const placeholderOption = document.createElement("option");
      placeholderOption.value = "";
      placeholderOption.textContent = placeholder;
      select.appendChild(placeholderOption);
    }
    items.forEach((item) => {
      const option = document.createElement("option");
      const mapped = mapper ? mapper(item) : { value: item, label: item };
      option.value = String(mapped.value || "");
      option.textContent = mapped.label || "";
      select.appendChild(option);
    });
    select.value = normalizedSelected;
    if (select.value !== normalizedSelected) {
      select.value = "";
    }
  };

  const filteredProducts = (consultingType, serviceCategory, serviceSubtype) => (
    products.filter((product) => {
      if (product.is_group && !(window.ProductGroupPicker && ProductGroupPicker.allow(container))) return false;
      if (consultingType && product.consulting_type !== consultingType) return false;
      if (serviceCategory && product.service_category !== serviceCategory) return false;
      if (serviceSubtype && product.service_subtype !== serviceSubtype) return false;
      return true;
    })
  );

  function registrationGroupOptions() {
    return {
      container,
      productRowClass: "registration-product-row",
      labelClass: "registration-product-group-label",
      badgeSelector: ".registration-product-badge",
      displaySelector: ".registration-product-display",
      productById,
      bindRow,
      syncRow,
      restoreNames(row) {
        [
          [".registration-consulting-select", "type_consulting"],
          [".registration-service-category-select", "type_service_category"],
          [".registration-service-subtype-select", "type_service_subtype"],
          [".registration-product-select", "type_id"],
        ].forEach(function (pair) {
          const field = row.querySelector(pair[0]);
          if (field) field.setAttribute("name", pair[1]);
        });
      },
      after() {
        renumberRows();
      },
    };
  }

  const syncRow = (row, state = {}) => {
    const consultingSelect = row.querySelector(".registration-consulting-select");
    const categorySelect = row.querySelector(".registration-service-category-select");
    const subtypeSelect = row.querySelector(".registration-service-subtype-select");
    const productSelect = row.querySelector(".registration-product-select");
    const productDisplay = row.querySelector(".registration-product-display");
    const hasOwn = (key) => Object.prototype.hasOwnProperty.call(state, key);
    const incomingProductId = hasOwn("productId") ? state.productId : (productSelect?.value ?? "");
    const selectedProduct = productById.get(String(incomingProductId || ""));

    let consultingValue = hasOwn("consultingType") ? state.consultingType : (consultingSelect?.value ?? "");
    let categoryValue = hasOwn("serviceCategory") ? state.serviceCategory : (categorySelect?.value ?? "");
    let subtypeValue = hasOwn("serviceSubtype") ? state.serviceSubtype : (subtypeSelect?.value ?? "");
    let productValue = String(incomingProductId ?? "");

    if (selectedProduct) {
      consultingValue = selectedProduct.consulting_type || consultingValue;
      categoryValue = selectedProduct.service_category || categoryValue;
      subtypeValue = selectedProduct.service_subtype || subtypeValue;
      productValue = String(selectedProduct.id);
    }

    buildOptions(
      consultingSelect,
      consultingTypes,
      "— выберите вид консалтинга —",
      consultingValue
    );
    consultingValue = consultingSelect?.value || "";

    const categoryOptions = uniqueValues(
      filteredProducts(consultingValue, "", "").map((product) => product.service_category)
    );
    const orderedCategories = serviceCategories.filter((value) => categoryOptions.includes(value));
    const extraCategories = categoryOptions.filter((value) => !orderedCategories.includes(value));
    buildOptions(
      categorySelect,
      orderedCategories.concat(extraCategories),
      consultingValue ? "— выберите тип услуги —" : "— выберите вид консалтинга —",
      categoryValue
    );
    categoryValue = categorySelect?.value || "";

    const subtypeOptions = uniqueValues(
      filteredProducts(consultingValue, categoryValue, "").map((product) => product.service_subtype)
    );
    buildOptions(
      subtypeSelect,
      subtypeOptions,
      categoryValue ? "— выберите подтип услуги —" : "— выберите тип услуги —",
      subtypeValue
    );
    subtypeValue = subtypeSelect?.value || "";

    buildOptions(
      productSelect,
      filteredProducts(consultingValue, categoryValue, subtypeValue),
      "— выберите продукт —",
      productValue,
      (product) => ({ value: product.id, label: product.label })
    );
    const displayProduct = productById.get(String(productSelect?.value || ""));
    if (productDisplay) {
      const displayText = displayProduct?.short_label || "— выберите продукт —";
      productDisplay.textContent = displayText;
      productDisplay.classList.toggle("is-placeholder", !displayProduct);
    }

    row.dataset.selectedConsultingType = consultingValue;
    row.dataset.selectedServiceCategory = categoryValue;
    row.dataset.selectedServiceSubtype = subtypeValue;
    row.dataset.selectedProductId = productSelect?.value || "";
  };

  const renumberRows = () => {
    getProductRows().forEach((row, idx) => {
      const badge = row.querySelector(".registration-product-badge");
      if (badge) badge.textContent = idx + 1;
    });
    syncTermsRowsWithProducts();
  };

  const bindRow = (row) => {
    if (!row || row.dataset.eventsBound === "1") return;
    row.dataset.eventsBound = "1";
    const consultingSelect = row.querySelector(".registration-consulting-select");
    const categorySelect = row.querySelector(".registration-service-category-select");
    const subtypeSelect = row.querySelector(".registration-service-subtype-select");
    const productSelect = row.querySelector(".registration-product-select");

    consultingSelect?.addEventListener("change", () => {
      syncRow(row, {
        consultingType: consultingSelect.value,
        serviceCategory: "",
        serviceSubtype: "",
        productId: "",
      });
      syncTermsRowsWithProducts();
    });
    categorySelect?.addEventListener("change", () => {
      syncRow(row, {
        consultingType: consultingSelect?.value || "",
        serviceCategory: categorySelect.value,
        serviceSubtype: "",
        productId: "",
      });
      syncTermsRowsWithProducts();
    });
    subtypeSelect?.addEventListener("change", () => {
      syncRow(row, {
        consultingType: consultingSelect?.value || "",
        serviceCategory: categorySelect?.value || "",
        serviceSubtype: subtypeSelect.value,
        productId: "",
      });
      syncTermsRowsWithProducts();
    });
    productSelect?.addEventListener("change", () => {
      const selected = productById.get(String(productSelect.value || ""));
      if (window.ProductGroupPicker && ProductGroupPicker.allow(container)) {
        if (ProductGroupPicker.isGroup(selected)) {
          if (row.dataset.productGroupLabel === "1" && row.dataset.groupProductId !== String(selected.id)) {
            ProductGroupPicker.reifyLabel(row, registrationGroupOptions());
          }
          if (ProductGroupPicker.expand(row, selected, registrationGroupOptions())) return;
          return;
        }
        if (row.dataset.productGroupLabel === "1") {
          ProductGroupPicker.reifyLabel(row, registrationGroupOptions());
        } else if (row.dataset.productGroupParent) {
          const parent = productById.get(String(row.dataset.productGroupParent));
          const stillMember = parent && (parent.member_ids || []).map(String).includes(String(productSelect.value || ""));
          if (!stillMember) ProductGroupPicker.clearMemberMarker(row);
          ProductGroupPicker.prune(container, registrationGroupOptions());
        }
      }
      syncRow(row, { productId: productSelect.value });
      syncTermsRowsWithProducts();
    });
  };

  const refreshProductContractOptions = (extraSelects = []) => {
    if (!hasRegistrationContracts) return;
    const contractSelects = [...node.querySelectorAll("#registration-contracts-container .registration-contract-select")];
    const source = contractSelects[0] || node.querySelector(".registration-contract-select");
    if (!source) return;
    const allowed = [];
    const seen = new Set();
    contractSelects.forEach((select) => {
      const value = String(select.value || "").trim();
      if (!value || seen.has(value)) return;
      seen.add(value);
      allowed.push(value);
    });
    const sourceByValue = new Map([...source.options].map((option) => [option.value, option.textContent]));
    const productSelects = [...node.querySelectorAll(".registration-product-contract-select")];
    extraSelects.forEach((select) => {
      if (select && !productSelects.includes(select)) productSelects.push(select);
    });
    productSelects.forEach((select) => {
      if (select.dataset.contractChangeBound !== "1") {
        select.dataset.contractChangeBound = "1";
        select.addEventListener("change", () => {
          select.dataset.contractTouched = "1";
        });
      }
      const preferred = select.dataset.contractTouched === "1"
        ? String(select.value || "")
        : String(select.value || select.closest(".registration-product-row")?.dataset.selectedContractId || "");
      select.replaceChildren();
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = sourceByValue.has("") ? sourceByValue.get("") : "— Не выбрано —";
      select.appendChild(blank);
      allowed.forEach((value) => {
        if (!sourceByValue.has(value)) return;
        const option = document.createElement("option");
        option.value = value;
        option.textContent = sourceByValue.get(value);
        select.appendChild(option);
      });
      select.value = allowed.includes(preferred) ? preferred : "";
    });
    if (node.dataset.registrationContractGroups === "1") node.__contractStageTermsApi?.sync();
  };

  const fillProductContractSelect = (select) => {
    if (!select || !hasRegistrationContracts) return;
    refreshProductContractOptions([select]);
  };

  if (hasRegistrationContracts && node.dataset.productContractLinkBound !== "1") {
    node.dataset.productContractLinkBound = "1";
    node.addEventListener("change", (event) => {
      if (event.target?.classList?.contains("registration-contract-select")) {
        refreshProductContractOptions();
      }
    });
    node.addEventListener("click", (event) => {
      if (event.target?.closest?.("#registration-add-contract, .registration-contract-remove")) {
        refreshProductContractOptions();
      }
    });
  }

  const buildRow = (initialState = {}) => {
    const row = document.createElement("div");
    row.className = "registration-product-row";
    row.dataset.selectedConsultingType = initialState.consultingType || "";
    row.dataset.selectedServiceCategory = initialState.serviceCategory || "";
    row.dataset.selectedServiceSubtype = initialState.serviceSubtype || "";
    row.dataset.selectedProductId = initialState.productId || "";
    const contractField = hasRegistrationContracts
      ? '<div class="col-12"><select name="stage_contract_id" class="form-select registration-product-contract-select" aria-label="Договор ID"></select></div>'
      : "";
    let html = '<div class="registration-product-row-inner">'
      + '<span class="badge rounded-circle d-flex align-items-center justify-content-center registration-product-badge"></span>'
      + '<div class="row g-2 flex-grow-1 registration-product-fields">'
      + contractField
      + '<div class="col-12 col-xl-3"><select name="type_consulting" class="form-select registration-consulting-select"></select></div>'
      + '<div class="col-12 col-xl-3"><select name="type_service_category" class="form-select registration-service-category-select"></select></div>'
      + '<div class="col-12 col-xl-3"><select name="type_service_subtype" class="form-select registration-service-subtype-select"></select></div>'
      + '<div class="col-12 col-xl-3"><div class="registration-product-select-shell"><select name="type_id" class="form-select registration-product-select"></select><div class="registration-product-display" aria-hidden="true"></div></div></div>'
      + '</div>'
      + '<button type="button" class="btn btn-sm registration-product-remove" title="Удалить" aria-label="Удалить строку типа">&times;</button>'
      + '</div>'
      + '<input type="hidden" name="row_group_id" value="">'
      + '<input type="hidden" name="registration_row_id" value="">';
    row.innerHTML = html;
    fillProductContractSelect(row.querySelector(".registration-product-contract-select"));
    bindRow(row);
    syncRow(row, initialState);
    return row;
  };

  addBtn?.addEventListener("click", () => {
    container.appendChild(buildRow({}));
    renumberRows();
  });

  container.addEventListener("click", (event) => {
    const removeBtn = event.target.closest(".registration-product-remove");
    if (!removeBtn) return;
    const row = removeBtn.closest(".registration-product-row");
    if (row && row.dataset.productGroupLabel === "1" && window.ProductGroupPicker) {
      ProductGroupPicker.releaseLabel(container, row, registrationGroupOptions());
      renumberRows();
      return;
    }
    const rows = getProductRows();
    if (isRegistrationGroupEdit) {
      if (rows.length <= 1) {
        alert("В группе должна остаться хотя бы одна строка.");
        return;
      }
      if (!window.confirm("Удалить строку проекта из группы? Строка исчезнет из реестра после сохранения.")) {
        return;
      }
      row?.remove();
      if (window.ProductGroupPicker) ProductGroupPicker.prune(container, registrationGroupOptions());
      renumberRows();
      return;
    }
    const isFirstRow = row && rows[0] === row;
    if (isFirstRow) {
      if (window.ProductGroupPicker) ProductGroupPicker.clearMemberMarker(row);
      row.dataset.selectedConsultingType = "";
      row.dataset.selectedServiceCategory = "";
      row.dataset.selectedServiceSubtype = "";
      row.dataset.selectedProductId = "";
      syncRow(row, {
        consultingType: "",
        serviceCategory: "",
        serviceSubtype: "",
        productId: "",
      });
      if (window.ProductGroupPicker) ProductGroupPicker.prune(container, registrationGroupOptions());
      syncTermsRowsWithProducts();
      return;
    }
    row?.remove();
    if (window.ProductGroupPicker) ProductGroupPicker.prune(container, registrationGroupOptions());
    renumberRows();
  });

  if (window.ProductGroupPicker && ProductGroupPicker.allow(container)) {
    ProductGroupPicker.restore(container, registrationGroupOptions());
  }
  container.querySelectorAll(".registration-product-row").forEach((row) => {
    fillProductContractSelect(row.querySelector(".registration-product-contract-select"));
    bindRow(row);
    syncRow(row, {
      consultingType: row.dataset.selectedConsultingType || "",
      serviceCategory: row.dataset.selectedServiceCategory || "",
      serviceSubtype: row.dataset.selectedServiceSubtype || "",
      productId: row.dataset.selectedProductId || "",
    });
  });
  renumberRows();
}
  window.attachRegistrationProducts = attachRegistrationProducts;
})();
