(function () {
  function qa(selector, root) {
    return Array.from((root || document).querySelectorAll(selector));
  }

  function parsePercentValue(input) {
    const raw = String(input?.value || "").trim().replace(",", ".");
    if (!raw) return 0;
    const value = Number.parseFloat(raw);
    return Number.isFinite(value) ? value : 0;
  }

  function formatPercentValue(value) {
    return value.toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
  }

  function syncFinalReportPercent(group) {
    const scope = group || document;
    const advanceInput = scope.querySelector('[name="advance_percent"]');
    const preliminaryInput = scope.querySelector('[name="preliminary_report_percent"]');
    const finalInput = scope.querySelector('[name="final_report_percent"]');
    if (!advanceInput || !preliminaryInput || !finalInput) return;
    const result = 100 - parsePercentValue(advanceInput) - parsePercentValue(preliminaryInput);
    finalInput.value = formatPercentValue(result);
  }

  function syncAllFinalReportPercents(form) {
    const groups = qa(".js-proposal-payment-group", form);
    if (groups.length) {
      groups.forEach(function (group) {
        syncFinalReportPercent(group);
      });
      return;
    }
    syncFinalReportPercent(form);
  }

  function copyPaymentDefaultsFromFirstStage(form) {
    const stageBlocks = qa(".proposal-payment-stage-block", form);
    const firstBlock = stageBlocks[0];
    if (!firstBlock) return;
    const fieldNames = [
      "advance_percent",
      "advance_term_days",
      "preliminary_report_percent",
      "preliminary_report_term_days",
      "final_report_percent",
      "final_report_term_days",
    ];
    stageBlocks.slice(1).forEach(function (block) {
      fieldNames.forEach(function (fieldName) {
        const target = block.querySelector('[name="' + fieldName + '"]');
        const source = firstBlock.querySelector('[name="' + fieldName + '"]');
        if (!target || !source || String(target.value || "").trim()) return;
        target.value = source.value || "";
      });
    });
  }

  function isPreliminaryReportStageEnabled(row) {
    const hidden = row?.querySelector(".proposal-stage-service-term-months-enabled");
    return String(hidden?.value || "true").toLowerCase() !== "false";
  }

  function setPreliminaryPaymentFieldsLocked(scope, locked) {
    if (!scope) return;
    ["preliminary_report_percent", "preliminary_report_term_days"].forEach(function (fieldName) {
      const input = scope.querySelector('[name="' + fieldName + '"]');
      if (!input) return;
      if (locked) {
        input.value = "0";
        input.readOnly = true;
        input.setAttribute("readonly", "");
        input.tabIndex = -1;
        input.classList.add("readonly-field");
      } else {
        input.readOnly = false;
        input.removeAttribute("readonly");
        input.removeAttribute("tabindex");
        input.classList.remove("readonly-field");
      }
    });
  }

  function syncPreliminaryReportPaymentState(form) {
    const toggle = form.querySelector('input[type="checkbox"][name="payment_schedule_common"]');
    const termRows = qa(".proposal-stage-terms-row", form);
    const paymentBlocks = qa(".proposal-payment-stage-block", form);
    const preliminaryStates = termRows.map(isPreliminaryReportStageEnabled);
    const hasMixedPreliminaryStages = preliminaryStates.length > 1 && preliminaryStates.some(function (state) {
      return state !== preliminaryStates[0];
    });
    if (toggle) {
      if (hasMixedPreliminaryStages) {
        toggle.checked = false;
      }
      toggle.disabled = hasMixedPreliminaryStages;
      toggle.classList.toggle("is-contract-payment-common-blocked", hasMixedPreliminaryStages);
    }

    const isCommon = !toggle || toggle.checked;
    setPreliminaryPaymentFieldsLocked(
      form.querySelector(".js-proposal-payment-common-fields"),
      isCommon && termRows.length > 0 && !isPreliminaryReportStageEnabled(termRows[0])
    );
    paymentBlocks.forEach(function (block, index) {
      const termRow = termRows[index];
      setPreliminaryPaymentFieldsLocked(
        block,
        !isCommon && !!termRow && !isPreliminaryReportStageEnabled(termRow)
      );
    });
  }

  function syncPaymentScheduleMode(form) {
    const toggle = form.querySelector('input[type="checkbox"][name="payment_schedule_common"]');
    syncPreliminaryReportPaymentState(form);
    const commonFields = form.querySelector(".js-proposal-payment-common-fields");
    const stageFields = form.querySelector(".js-proposal-payment-stage-fields");
    const isCommon = !toggle || toggle.checked;
    commonFields?.classList.toggle("d-none", !isCommon);
    stageFields?.classList.toggle("d-none", isCommon);
    if (commonFields) {
      commonFields.querySelectorAll("input, select, textarea").forEach(function (input) {
        input.disabled = !isCommon;
      });
    }
    if (stageFields) {
      stageFields.querySelectorAll("input, select, textarea").forEach(function (input) {
        if (input.name === "final_report_percent") {
          input.disabled = true;
          return;
        }
        input.disabled = isCommon;
      });
    }
    if (!isCommon) {
      copyPaymentDefaultsFromFirstStage(form);
    }
    syncPreliminaryReportPaymentState(form);
    syncAllFinalReportPercents(form);
  }

  function clonePaymentStageBlock(block) {
    const clone = block.cloneNode(true);
    clone.querySelectorAll("input").forEach(function (input) {
      if (input.name === "final_report_percent") {
        input.readOnly = true;
        input.tabIndex = -1;
        input.classList.add("readonly-field");
        input.disabled = true;
        return;
      }
      input.value = "";
      input.disabled = false;
    });
    return clone;
  }

  function syncContractPaymentStageBlocks(node) {
    if (!node) return;
    const container = node.querySelector("#contract-payment-stages-container");
    const productsContainer = node.querySelector("#registration-products-container");
    const metaEl = node.querySelector("#registration-type-meta");
    if (!container || !productsContainer || !metaEl) return;

    let meta = {};
    try {
      meta = JSON.parse(metaEl.textContent || "{}");
    } catch (error) {
      meta = {};
    }
    const products = Array.isArray(meta.products) ? meta.products : [];
    const productById = new Map(products.map(function (product) {
      return [String(product.id), product];
    }));

    const productRows = Array.from(productsContainer.querySelectorAll(".registration-product-row"));
    let paymentBlocks = Array.from(container.querySelectorAll(".proposal-payment-stage-block"));
    while (paymentBlocks.length < productRows.length && paymentBlocks.length) {
      container.appendChild(clonePaymentStageBlock(paymentBlocks[paymentBlocks.length - 1]));
      paymentBlocks = Array.from(container.querySelectorAll(".proposal-payment-stage-block"));
    }
    while (paymentBlocks.length > productRows.length && paymentBlocks.length > 1) {
      paymentBlocks[paymentBlocks.length - 1].remove();
      paymentBlocks = Array.from(container.querySelectorAll(".proposal-payment-stage-block"));
    }

    productRows.forEach(function (productRow, index) {
      const paymentBlock = paymentBlocks[index];
      if (!paymentBlock) return;
      const productId = String(productRow.querySelector(".registration-product-select")?.value || "").trim();
      const product = productById.get(productId);
      const shortLabel = String(product?.short_label || "").trim();
      paymentBlock.dataset.proposalStageKey = String(index + 1);
      paymentBlock.querySelectorAll(".proposal-payment-stage-title").forEach(function (title) {
        title.textContent = shortLabel
          ? "Этап " + (index + 1) + " " + shortLabel
          : "Этап " + (index + 1);
      });
      paymentBlock.classList.toggle("mt-4", index > 0);
    });

    syncPaymentScheduleMode(node);
  }

  function attachContractPaymentSchedule(node) {
    if (!node || node.dataset.contractPaymentScheduleBound === "1") return;
    const toggle = node.querySelector('input[type="checkbox"][name="payment_schedule_common"]');
    if (!toggle) return;
    node.dataset.contractPaymentScheduleBound = "1";

    toggle.addEventListener("change", function () {
      syncPaymentScheduleMode(node);
    });

    node.addEventListener("htmx:beforeRequest", function () {
      syncPaymentScheduleMode(node);
    });

    node.addEventListener("input", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) return;
      if (target.name !== "advance_percent" && target.name !== "preliminary_report_percent") return;
      const group = target.closest(".js-proposal-payment-group");
      syncFinalReportPercent(group || node);
    });

    node.addEventListener("change", function (event) {
      if (!event.target?.classList?.contains("proposal-stage-service-term-months-toggle")) return;
      syncPaymentScheduleMode(node);
    });

    syncPaymentScheduleMode(node);
  }

  window.attachContractPaymentSchedule = attachContractPaymentSchedule;
  window.syncContractPaymentStageBlocks = syncContractPaymentStageBlocks;
})();
