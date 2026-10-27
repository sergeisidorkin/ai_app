(function () {
  function memberRows(container, groupId, productRowClass) {
    return Array.from(container.querySelectorAll("." + productRowClass)).filter(function (row) {
      return row.dataset.productGroupLabel !== "1" && row.dataset.productGroupParent === String(groupId || "");
    });
  }

  function assignSelect(select, value) {
    if (!select) return;
    const next = String(value || "");
    if (!next) return;
    const match = Array.from(select.options).some(function (option) {
      return option.value === next;
    });
    if (match) select.value = next;
  }

  function ensureGroupInput(row, groupId) {
    let input = row.querySelector('input[name="row_group_id"]');
    if (!input) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = "row_group_id";
      row.appendChild(input);
    }
    input.value = groupId ? String(groupId) : "";
    return input;
  }

  const ProductGroupPicker = {
    isGroup(product) {
      return Boolean(product && product.is_group && Array.isArray(product.member_ids) && product.member_ids.length >= 2);
    },

    allow(container) {
      return Boolean(container && container.dataset.allowProductGroups === "1");
    },

    becomeLabel(row, groupProduct, options) {
      row.classList.add(options.labelClass);
      row.dataset.productGroupLabel = "1";
      row.dataset.groupProductId = String(groupProduct.id);
      delete row.dataset.productGroupParent;
      row.dataset.selectedProductId = String(groupProduct.id);
      row.dataset.selectedConsultingType = groupProduct.consulting_type || "";
      row.dataset.selectedServiceCategory = groupProduct.service_category || "";
      row.dataset.selectedServiceSubtype = groupProduct.service_subtype || "";
      assignSelect(row.querySelector(".proposal-consulting-select, .registration-consulting-select"), groupProduct.consulting_type);
      assignSelect(row.querySelector(".proposal-service-category-select, .registration-service-category-select"), groupProduct.service_category);
      assignSelect(row.querySelector(".proposal-service-subtype-select, .registration-service-subtype-select"), groupProduct.service_subtype);
      assignSelect(row.querySelector(".proposal-product-select, .registration-product-select"), groupProduct.id);
      row.querySelectorAll("select").forEach(function (select) {
        select.removeAttribute("name");
      });
      const groupInput = row.querySelector('input[name="row_group_id"]');
      if (groupInput) groupInput.remove();
      const badge = row.querySelector(options.badgeSelector);
      if (badge) badge.textContent = "0";
      const display = row.querySelector(options.displaySelector);
      if (display) {
        display.textContent = groupProduct.short_label || "";
        display.classList.remove("is-placeholder");
      }
    },

    reifyLabel(row, options) {
      const groupId = row.dataset.groupProductId || "";
      row.classList.remove(options.labelClass);
      delete row.dataset.productGroupLabel;
      delete row.dataset.groupProductId;
      if (options.restoreNames) options.restoreNames(row);
      ensureGroupInput(row, "");
      if (groupId && options.container) {
        memberRows(options.container, groupId, options.productRowClass).forEach(function (member) {
          delete member.dataset.productGroupParent;
          const input = member.querySelector('input[name="row_group_id"]');
          if (input) input.value = "";
        });
      }
    },

    prepareMember(row, groupProduct, options) {
      row.classList.remove(options.labelClass);
      delete row.dataset.productGroupLabel;
      delete row.dataset.groupProductId;
      delete row.dataset.eventsBound;
      row.dataset.productGroupParent = String(groupProduct.id);
      if (options.restoreNames) options.restoreNames(row);
      ensureGroupInput(row, groupProduct.id);
    },

    expand(row, groupProduct, options) {
      if (!this.isGroup(groupProduct) || !options.container) return false;
      if (row.dataset.productGroupLabel === "1" && row.dataset.groupProductId === String(groupProduct.id)) {
        return false;
      }
      const previousParent = row.dataset.productGroupParent || "";
      const template = row.cloneNode(true);
      this.becomeLabel(row, groupProduct, options);
      let anchor = row;
      groupProduct.member_ids.forEach(function (memberId) {
        const member = template.cloneNode(true);
        ProductGroupPicker.prepareMember(member, groupProduct, options);
        const memberProduct = options.productById.get(String(memberId));
        member.dataset.selectedProductId = String(memberId);
        member.dataset.selectedConsultingType = memberProduct?.consulting_type || "";
        member.dataset.selectedServiceCategory = memberProduct?.service_category || "";
        member.dataset.selectedServiceSubtype = memberProduct?.service_subtype || "";
        if (options.assignStageUid) options.assignStageUid(member);
        anchor.insertAdjacentElement("afterend", member);
        anchor = member;
        if (options.bindRow) options.bindRow(member);
        if (options.syncRow) options.syncRow(member, { productId: String(memberId) });
      });
      if (previousParent) this.prune(options.container, options);
      if (options.after) options.after();
      return true;
    },

    restore(container, options) {
      const rows = Array.from(container.querySelectorAll("." + options.productRowClass)).filter(function (row) {
        return row.dataset.productGroupLabel !== "1";
      });
      const groups = new Map();
      rows.forEach(function (row) {
        const groupId = String(
          row.dataset.productGroupId
          || row.querySelector('input[name="row_group_id"]')?.value
          || ""
        ).trim();
        if (!groupId) return;
        if (!groups.has(groupId)) groups.set(groupId, []);
        groups.get(groupId).push(row);
      });
      groups.forEach(function (members, groupId) {
        if (members.length < 2) {
          members.forEach(function (row) {
            delete row.dataset.productGroupParent;
            const input = row.querySelector('input[name="row_group_id"]');
            if (input) input.value = "";
          });
          return;
        }
        const group = options.productById.get(String(groupId));
        if (!ProductGroupPicker.isGroup(group)) return;
        members.forEach(function (row) {
          row.dataset.productGroupParent = String(groupId);
          ensureGroupInput(row, groupId);
        });
        const first = members[0];
        const previous = first.previousElementSibling;
        if (
          previous
          && previous.dataset.productGroupLabel === "1"
          && previous.dataset.groupProductId === String(groupId)
        ) {
          return;
        }
        const label = first.cloneNode(true);
        delete label.dataset.eventsBound;
        first.insertAdjacentElement("beforebegin", label);
        ProductGroupPicker.becomeLabel(label, group, options);
      });
    },

    prune(container, options) {
      container.querySelectorAll("." + options.labelClass).forEach(function (label) {
        const members = memberRows(container, label.dataset.groupProductId, options.productRowClass);
        if (members.length >= 2) {
          const badge = label.querySelector(options.badgeSelector);
          if (badge) badge.textContent = "0";
          return;
        }
        members.forEach(function (row) {
          delete row.dataset.productGroupParent;
          const input = row.querySelector('input[name="row_group_id"]');
          if (input) input.value = "";
        });
        label.remove();
      });
    },

    releaseLabel(container, label, options) {
      memberRows(container, label.dataset.groupProductId, options.productRowClass).forEach(function (row) {
        delete row.dataset.productGroupParent;
        const input = row.querySelector('input[name="row_group_id"]');
        if (input) input.value = "";
      });
      label.remove();
    },

    clearMemberMarker(row) {
      delete row.dataset.productGroupParent;
      delete row.dataset.productGroupLabel;
      const input = row.querySelector('input[name="row_group_id"]');
      if (input) input.value = "";
    },
  };

  window.ProductGroupPicker = ProductGroupPicker;
})();
