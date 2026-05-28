(function () {
  if (window.__registrationCustomerMetaLoaded) return;
  window.__registrationCustomerMetaLoaded = true;

  const DEFAULT_SELECTORS = {
    customerCountry: '#reg-country-select',
    customerRegion: '#reg-region-select',
    customerIdentifier: '#reg-identifier-field',
    customerInput: 'input[name="customer"]',
    customerAcList: '#reg-ler-ac-list',
    customerSelectedIdentifier: '#reg-customer-autocomplete-identifier-record-id',
    customerSelectedFlag: '#reg-customer-autocomplete-selected',
    customerRegistrationNumber: 'input[name="registration_number"]',
    customerRegistrationDate: 'input[name="registration_date"]',
    assetOwnerCountry: '#reg-asset-owner-country-select',
    assetOwnerRegion: '#reg-asset-owner-region-select',
    assetOwnerIdentifier: '#reg-asset-owner-identifier-field',
    assetOwnerInput: 'input[name="asset_owner"]',
    assetOwnerAcList: '#reg-asset-owner-ler-ac-list',
    assetOwnerSelectedIdentifier: '#reg-asset-owner-autocomplete-identifier-record-id',
    assetOwnerSelectedFlag: '#reg-asset-owner-autocomplete-selected',
    assetOwnerRegistrationNumber: 'input[name="asset_owner_registration_number"]',
    assetOwnerRegistrationDate: 'input[name="asset_owner_registration_date"]',
    assetOwnerMatchesCustomer: '[name="asset_owner_matches_customer"]',
  };

  function query(form, selector) {
    if (!selector) return null;
    return form.querySelector(selector);
  }

  function normalizeDisplayDate(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (isoMatch) {
      return isoMatch[3] + '.' + isoMatch[2] + '.' + isoMatch[1];
    }
    return raw;
  }

  function setDateFieldValue(input, value) {
    const raw = String(value || '').trim();
    if (!input) return;
    if (!raw) {
      if (!input.value) return;
      input.value = '';
      if (input._flatpickr) input._flatpickr.clear(false);
      if (window.$ && $.fn && $.fn.datepicker) $(input).datepicker('update', '');
      return;
    }

    const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
    const isoValue = isoMatch ? (isoMatch[1] + '-' + isoMatch[2] + '-' + isoMatch[3]) : raw;
    const displayValue = normalizeDisplayDate(raw);

    if (input._flatpickr) {
      if (normalizeDisplayDate(input.value) !== displayValue) {
        input._flatpickr.setDate(isoValue, false, 'Y-m-d');
      }
      return;
    }
    if (window.$ && $.fn && $.fn.datepicker && input.dataset.hasPicker === '1') {
      if (normalizeDisplayDate(input.value) !== displayValue) {
        $(input).datepicker('update', displayValue);
      }
      return;
    }
    if (input.type === 'date') {
      if (input.value !== isoValue) input.value = isoValue;
      return;
    }
    if (input.value !== displayValue) input.value = displayValue;
  }

  function resetRegionSelect(regionSelect) {
    if (!(regionSelect instanceof HTMLSelectElement)) return;
    regionSelect.innerHTML = '<option value="">---------</option>';
  }

  function ensureRegionOption(regionSelect, regionName) {
    if (!(regionSelect instanceof HTMLSelectElement)) return;
    const value = String(regionName || '').trim();
    if (!value) return;
    for (let i = 0; i < regionSelect.options.length; i += 1) {
      if (regionSelect.options[i].value === value) return;
    }
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    regionSelect.appendChild(option);
  }

  function loadRegionOptions(regionUrl, countryId, regionSelect, options) {
    if (!(regionSelect instanceof HTMLSelectElement)) return Promise.resolve();
    const settings = options || {};
    const nextRequestSeq = String((Number(regionSelect.dataset.regionRequestSeq || '0') || 0) + 1);
    regionSelect.dataset.regionRequestSeq = nextRequestSeq;
    const hasExplicitSelectedRegion = (
      Object.prototype.hasOwnProperty.call(settings, 'selectedRegion')
      && settings.selectedRegion !== undefined
    );
    const hasPendingSelectedRegion = regionSelect.dataset.pendingSelectedRegionSet === '1';
    const pendingRegion = String(regionSelect.dataset.pendingSelectedRegion || '').trim();
    const selectedRegion = String(
      hasExplicitSelectedRegion && settings.selectedRegion !== null
        ? settings.selectedRegion
        : pendingRegion
    ).trim();
    const preserveCurrent = !!settings.preserveCurrent;
    const currentRegion = preserveCurrent ? String(regionSelect.value || '').trim() : '';
    const nextRegion = hasExplicitSelectedRegion
      ? selectedRegion
      : (hasPendingSelectedRegion ? pendingRegion : currentRegion);
    const dateValue = String(settings.dateValue || '').trim();

    if (!countryId) {
      resetRegionSelect(regionSelect);
      if (nextRegion) {
        ensureRegionOption(regionSelect, nextRegion);
        regionSelect.value = nextRegion;
      }
      return Promise.resolve();
    }

    if (!regionUrl) {
      resetRegionSelect(regionSelect);
      if (nextRegion) {
        ensureRegionOption(regionSelect, nextRegion);
        regionSelect.value = nextRegion;
      }
      return Promise.resolve();
    }

    let requestUrl = regionUrl + '?country_id=' + encodeURIComponent(countryId);
    if (dateValue) requestUrl += '&date=' + encodeURIComponent(dateValue);

    return fetch(requestUrl)
      .then((response) => response.json())
      .then((data) => {
        if (regionSelect.dataset.regionRequestSeq !== nextRequestSeq) return;
        const regions = Array.isArray(data?.regions) ? data.regions.slice() : [];
        resetRegionSelect(regionSelect);
        if (nextRegion && !regions.includes(nextRegion)) {
          regions.push(nextRegion);
        }
        regions.forEach((regionName) => {
          const option = document.createElement('option');
          option.value = regionName;
          option.textContent = regionName;
          regionSelect.appendChild(option);
        });
        regionSelect.value = nextRegion;
        if (hasPendingSelectedRegion) {
          delete regionSelect.dataset.pendingSelectedRegion;
          delete regionSelect.dataset.pendingSelectedRegionSet;
        }
      })
      .catch(() => {
        if (regionSelect.dataset.regionRequestSeq !== nextRequestSeq) return;
        resetRegionSelect(regionSelect);
        if (nextRegion) {
          ensureRegionOption(regionSelect, nextRegion);
          regionSelect.value = nextRegion;
        }
        if (hasPendingSelectedRegion) {
          delete regionSelect.dataset.pendingSelectedRegion;
          delete regionSelect.dataset.pendingSelectedRegionSet;
        }
      });
  }

  function replaceQuotes(element) {
    const value = element.value;
    if (value.indexOf('"') === -1) return;
    const pos = element.selectionStart;
    let out = '';
    for (let i = 0; i < value.length; i += 1) {
      if (value[i] === '"') {
        const prev = out.length ? out[out.length - 1] : '';
        out += (!prev || /[\s(\[{\u00AB]/.test(prev)) ? '\u00AB' : '\u00BB';
      } else {
        out += value[i];
      }
    }
    element.value = out;
    element.setSelectionRange(pos, pos);
  }

  window.initRegistrationCustomerMeta = function initRegistrationCustomerMeta(root, options) {
    if (!root) return;
    const form = root.closest('form') || root;
    if (!form || form.dataset.registrationCustomerMetaBound === '1') return;
    form.dataset.registrationCustomerMetaBound = '1';

    const selectors = Object.assign({}, DEFAULT_SELECTORS, options?.selectors || {});
    const customerChangedEvent = options?.customerChangedEvent || 'registration-customer-changed';
    const assetOwnerChangedEvent = options?.assetOwnerChangedEvent || 'registration-asset-owner-changed';
    const regionUrl = form.dataset.countryRegionUrl || '';
    const autofillUrl = form.dataset.regionAutofillUrl || '';
    const identifierUrl = form.dataset.countryIdentifierUrl || '';
    const searchUrl = form.dataset.lerSearchUrl || '';

    function dispatchCustomerChanged(detail) {
      form.dispatchEvent(new CustomEvent(customerChangedEvent, { detail: detail || {} }));
    }

    function dispatchAssetOwnerChanged(detail) {
      form.dispatchEvent(new CustomEvent(assetOwnerChangedEvent, { detail: detail || {} }));
    }

    function attachGuillemets() {
      ['customer', 'asset_owner'].forEach(function (fieldName) {
        const input = form.querySelector('input[name="' + fieldName + '"]');
        if (!input || input.dataset.guillBound === '1') return;
        input.dataset.guillBound = '1';
        input.addEventListener('input', function () {
          replaceQuotes(input);
        });
      });
    }

    function attachCountryIdentifierSync(countrySelector, identifierSelector, boundKey, onSync) {
      const countrySelect = query(form, countrySelector);
      const identifierField = query(form, identifierSelector);
      if (!countrySelect || !identifierField || !identifierUrl || countrySelect.dataset[boundKey] === '1') return;
      countrySelect.dataset[boundKey] = '1';

      countrySelect.addEventListener('change', () => {
        const countryId = countrySelect.value;
        if (!countryId) {
          identifierField.value = '';
          if (typeof onSync === 'function') onSync();
          return;
        }
        fetch(identifierUrl + '?country_id=' + encodeURIComponent(countryId))
          .then((response) => response.json())
          .then((data) => {
            identifierField.value = data.identifier || '';
            if (typeof onSync === 'function') onSync();
          });
      });
    }

    function attachCountryRegionSync(countrySelector, regionSelector, dateSelector, boundKey, onSync) {
      const countrySelect = query(form, countrySelector);
      const regionSelect = query(form, regionSelector);
      const dateInput = query(form, dateSelector);
      if (!countrySelect || !regionSelect || countrySelect.dataset[boundKey] === '1') return;
      countrySelect.dataset[boundKey] = '1';

      function syncRegions(preserveCurrent, selectedRegion) {
        const regionOptions = {
          preserveCurrent: preserveCurrent,
          dateValue: dateInput?.value || '',
        };
        if (selectedRegion !== undefined) {
          regionOptions.selectedRegion = selectedRegion;
        }
        return loadRegionOptions(regionUrl, countrySelect.value, regionSelect, regionOptions).then(() => {
          if (typeof onSync === 'function') onSync();
        });
      }

      countrySelect.addEventListener('change', () => {
        syncRegions(false);
      });
      dateInput?.addEventListener('change', () => {
        syncRegions(true);
      });
      dateInput?.addEventListener('input', () => {
        syncRegions(true);
      });

      if (!countrySelect.value) {
        resetRegionSelect(regionSelect);
      } else {
        syncRegions(true, regionSelect.value || '');
      }
    }

    function attachRegionAutofill(config) {
      const countrySelect = query(form, config.countrySelector);
      const identifierInput = query(form, config.identifierSelector);
      const registrationNumberInput = query(form, config.registrationNumberSelector);
      const regionSelect = query(form, config.regionSelector);
      if (!countrySelect || !identifierInput || !registrationNumberInput || !regionSelect || !autofillUrl) return;
      if (registrationNumberInput.dataset[config.boundKey] === '1') return;
      registrationNumberInput.dataset[config.boundKey] = '1';

      let requestSeq = 0;
      let debounce = null;

      function applyRegion(regionName) {
        const value = String(regionName || '').trim();
        regionSelect.dataset.pendingSelectedRegion = value;
        regionSelect.dataset.pendingSelectedRegionSet = '1';
        loadRegionOptions(regionUrl, countrySelect.value || '', regionSelect, {
          preserveCurrent: false,
          selectedRegion: value,
        }).then(() => {
          if (typeof config.onApplied === 'function') config.onApplied(value);
        });
      }

      function scheduleAutofill() {
        clearTimeout(debounce);
        debounce = setTimeout(() => {
          const seq = requestSeq + 1;
          requestSeq = seq;
          const countryId = String(countrySelect.value || '').trim();
          const identifier = String(identifierInput.value || '').trim();
          const registrationNumber = String(registrationNumberInput.value || '').trim();

          if (!countryId) {
            applyRegion('');
            return;
          }

          const requestUrl = autofillUrl
            + '?country_id=' + encodeURIComponent(countryId)
            + '&identifier=' + encodeURIComponent(identifier)
            + '&registration_number=' + encodeURIComponent(registrationNumber);

          fetch(requestUrl)
            .then((response) => response.json())
            .then((data) => {
              if (seq !== requestSeq) return;
              applyRegion(data?.region || '');
            })
            .catch(() => {
              if (seq !== requestSeq) return;
              applyRegion('');
            });
        }, 150);
      }

      registrationNumberInput.addEventListener('input', scheduleAutofill);
      registrationNumberInput.addEventListener('change', scheduleAutofill);
      countrySelect.addEventListener('change', scheduleAutofill);
    }

    function attachAssetOwnerMatchesCustomer() {
      const matchesCheckbox = query(form, selectors.assetOwnerMatchesCustomer);
      const customerInput = query(form, selectors.customerInput);
      const customerCountry = query(form, selectors.customerCountry);
      const customerRegion = query(form, selectors.customerRegion);
      const customerIdentifier = query(form, selectors.customerIdentifier);
      const customerRegistrationNumber = query(form, selectors.customerRegistrationNumber);
      const customerRegistrationDate = query(form, selectors.customerRegistrationDate);
      const ownerInput = query(form, selectors.assetOwnerInput);
      const ownerCountry = query(form, selectors.assetOwnerCountry);
      const ownerRegion = query(form, selectors.assetOwnerRegion);
      const ownerRegistrationNumber = query(form, selectors.assetOwnerRegistrationNumber);
      const ownerRegistrationDate = query(form, selectors.assetOwnerRegistrationDate);
      const ownerIdentifier = query(form, selectors.assetOwnerIdentifier);
      const customerSelectedIdentifier = query(form, selectors.customerSelectedIdentifier);
      const customerSelectedFlag = query(form, selectors.customerSelectedFlag);
      const ownerSelectedIdentifier = query(form, selectors.assetOwnerSelectedIdentifier);
      const ownerSelectedFlag = query(form, selectors.assetOwnerSelectedFlag);
      if (
        !matchesCheckbox
        || !ownerInput
        || !ownerCountry
        || !ownerRegion
        || !ownerIdentifier
        || !ownerRegistrationNumber
        || !ownerRegistrationDate
      ) {
        return;
      }

      function setLockedState(locked) {
        ownerInput.readOnly = locked;
        ownerInput.disabled = false;
        ownerInput.tabIndex = locked ? -1 : 0;
        ownerInput.classList.toggle('readonly-field', locked);
        ownerCountry.disabled = locked;
        ownerCountry.tabIndex = locked ? -1 : 0;
        ownerCountry.classList.toggle('readonly-field', locked);
        ownerRegion.disabled = locked;
        ownerRegion.tabIndex = locked ? -1 : 0;
        ownerRegion.classList.toggle('readonly-field', locked);
        ownerRegistrationNumber.readOnly = locked;
        ownerRegistrationNumber.disabled = false;
        ownerRegistrationNumber.tabIndex = locked ? -1 : 0;
        ownerRegistrationNumber.classList.toggle('readonly-field', locked);
        ownerRegistrationDate.readOnly = locked;
        ownerRegistrationDate.disabled = false;
        ownerRegistrationDate.tabIndex = locked ? -1 : 0;
        ownerRegistrationDate.classList.toggle('readonly-field', locked);
        if (ownerRegistrationDate._flatpickr) ownerRegistrationDate._flatpickr.set('clickOpens', !locked);
      }

      function syncFromCustomer(reason) {
        if (!matchesCheckbox.checked) {
          setLockedState(false);
          dispatchAssetOwnerChanged({ reason: reason || 'customer-sync' });
          return;
        }
        ownerInput.value = customerInput ? (customerInput.value || '') : '';
        ownerCountry.value = customerCountry ? (customerCountry.value || '') : '';
        loadRegionOptions(regionUrl, ownerCountry.value || '', ownerRegion, {
          preserveCurrent: false,
          selectedRegion: customerRegion ? (customerRegion.value || '') : '',
          dateValue: customerRegistrationDate ? (customerRegistrationDate.value || '') : '',
        });
        ownerIdentifier.value = customerIdentifier ? (customerIdentifier.value || '') : '';
        ownerRegistrationNumber.value = customerRegistrationNumber ? (customerRegistrationNumber.value || '') : '';
        setDateFieldValue(ownerRegistrationDate, customerRegistrationDate ? (customerRegistrationDate.value || '') : '');
        if (ownerSelectedIdentifier) ownerSelectedIdentifier.value = customerSelectedIdentifier ? (customerSelectedIdentifier.value || '') : '';
        if (ownerSelectedFlag) ownerSelectedFlag.value = customerSelectedFlag ? (customerSelectedFlag.value || '0') : '0';
        setLockedState(true);
        dispatchAssetOwnerChanged({ reason: reason || 'customer-sync' });
      }

      matchesCheckbox.addEventListener('change', () => syncFromCustomer('customer-sync'));
      ['customer', 'registration_number', 'registration_date'].forEach(function (fieldName) {
        form.querySelector('[name="' + fieldName + '"]')?.addEventListener('input', () => syncFromCustomer('customer-input'));
        form.querySelector('[name="' + fieldName + '"]')?.addEventListener('change', () => syncFromCustomer('customer-sync'));
      });
      customerCountry?.addEventListener('change', () => syncFromCustomer('customer-sync'));
      customerRegion?.addEventListener('change', () => syncFromCustomer('customer-sync'));
      customerIdentifier?.addEventListener('change', () => syncFromCustomer('customer-sync'));
      form.addEventListener(customerChangedEvent, () => syncFromCustomer('customer-sync'));
      syncFromCustomer('init');
    }

    function attachLerAutocomplete(config) {
      if (!searchUrl) return;
      const input = query(form, config.inputSelector);
      const list = query(form, config.listSelector);
      const selectedIdentifierInput = query(form, config.selectedIdentifierSelector);
      const selectedFlagInput = query(form, config.selectedFlagSelector);
      if (!input || !list || input.dataset[config.boundKey] === '1') return;
      input.dataset[config.boundKey] = '1';

      let debounce = null;
      let results = [];
      let picking = false;

      function clearSelection() {
        if (selectedIdentifierInput) selectedIdentifierInput.value = '';
        if (selectedFlagInput) selectedFlagInput.value = '0';
      }

      function highlight(text, queryText) {
        if (!queryText) return text;
        const escaped = queryText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return text.replace(new RegExp('(' + escaped + ')', 'gi'), '<mark>$1</mark>');
      }

      function render(data, queryText, totalCount) {
        results = data;
        if (!data.length) {
          list.classList.remove('show');
          return;
        }
        const visible = data.slice(0, 3);
        let html = visible.map(function (item, index) {
          const main = highlight(item.short_name || '', queryText);
          const parts = [item.full_name, item.identifier, item.registration_number].filter(Boolean);
          const sub = parts.length ? highlight(parts.join(' · '), queryText) : '';
          return '<div class="ler-ac-item" data-idx="' + index + '">'
            + '<div class="ler-ac-main">' + main + '</div>'
            + (sub ? '<div class="ler-ac-sub">' + sub + '</div>' : '')
            + '</div>';
        }).join('');
        const remaining = totalCount - 3;
        if (remaining > 0) {
          html += '<div class="ler-ac-item ler-ac-more">Найдено ещё ' + remaining + ' юрлиц</div>';
        }
        list.innerHTML = html;
        list.classList.add('show');
      }

      function pick(item) {
        const countrySelect = query(form, config.countrySelector);
        const regionSelect = query(form, config.regionSelector);
        const identifierField = query(form, config.identifierSelector);
        const registrationNumberField = query(form, config.registrationNumberSelector);
        const registrationDateField = query(form, config.registrationDateSelector);

        input.value = item.short_name || '';
        if (countrySelect && item.country_id) countrySelect.value = item.country_id;
        if (regionSelect) {
          regionSelect.dataset.pendingSelectedRegion = item.region || '';
          regionSelect.dataset.pendingSelectedRegionSet = '1';
        }
        setDateFieldValue(registrationDateField, item.registration_date || '');
        if (regionSelect) {
          const countryId = item.country_id || countrySelect?.value || '';
          loadRegionOptions(regionUrl, countryId, regionSelect, {
            preserveCurrent: false,
            selectedRegion: item.region || '',
            dateValue: item.registration_date || registrationDateField?.value || '',
          });
        }
        if (identifierField) identifierField.value = item.identifier || '';
        if (registrationNumberField) registrationNumberField.value = item.registration_number || '';
        if (registrationDateField) {
          registrationDateField.dispatchEvent(new Event('input', { bubbles: true }));
          registrationDateField.dispatchEvent(new Event('change', { bubbles: true }));
        }
        if (selectedIdentifierInput) selectedIdentifierInput.value = item.identifier_record_id || '';
        if (selectedFlagInput) selectedFlagInput.value = '1';

        if (config.syncAssetOwnerFromCustomer) {
          const matchesCheckbox = query(form, selectors.assetOwnerMatchesCustomer);
          const ownerInput = query(form, selectors.assetOwnerInput);
          const ownerCountry = query(form, selectors.assetOwnerCountry);
          const ownerRegion = query(form, selectors.assetOwnerRegion);
          const ownerIdentifier = query(form, selectors.assetOwnerIdentifier);
          const ownerRegistrationNumber = query(form, selectors.assetOwnerRegistrationNumber);
          const ownerRegistrationDate = query(form, selectors.assetOwnerRegistrationDate);
          const ownerSelectedIdentifier = query(form, selectors.assetOwnerSelectedIdentifier);
          const ownerSelectedFlag = query(form, selectors.assetOwnerSelectedFlag);
          if (
            matchesCheckbox?.checked
            && ownerInput
            && ownerCountry
            && ownerRegion
            && ownerIdentifier
            && ownerRegistrationNumber
            && ownerRegistrationDate
          ) {
            ownerInput.value = item.short_name || '';
            ownerCountry.value = item.country_id || '';
            ownerRegion.dataset.pendingSelectedRegion = item.region || '';
            ownerRegion.dataset.pendingSelectedRegionSet = '1';
            setDateFieldValue(ownerRegistrationDate, item.registration_date || '');
            loadRegionOptions(regionUrl, item.country_id || '', ownerRegion, {
              preserveCurrent: false,
              selectedRegion: item.region || '',
              dateValue: item.registration_date || '',
            });
            ownerIdentifier.value = item.identifier || '';
            ownerRegistrationNumber.value = item.registration_number || '';
            if (ownerSelectedIdentifier) ownerSelectedIdentifier.value = item.identifier_record_id || '';
            if (ownerSelectedFlag) ownerSelectedFlag.value = '1';
          }
        }

        list.classList.remove('show');
        if (config.changeEventName) {
          form.dispatchEvent(new CustomEvent(config.changeEventName, { detail: { reason: 'autocomplete-pick' } }));
          setTimeout(function () {
            form.dispatchEvent(new CustomEvent(config.changeEventName, { detail: { reason: 'autocomplete-pick' } }));
          }, 0);
        }
      }

      input.addEventListener('input', function () {
        const queryText = input.value.trim();
        clearSelection();
        clearTimeout(debounce);
        if (queryText.length < 1) {
          list.classList.remove('show');
          if (config.changeEventName) {
            form.dispatchEvent(new CustomEvent(config.changeEventName, { detail: { reason: 'autocomplete-clear' } }));
          }
          return;
        }
        debounce = setTimeout(function () {
          fetch(searchUrl + '?q=' + encodeURIComponent(queryText))
            .then((response) => response.json())
            .then((data) => render(data.results || [], queryText, data.total_count || 0))
            .catch(() => list.classList.remove('show'));
        }, 200);
      });

      list.addEventListener('mousedown', function (event) {
        event.preventDefault();
        picking = true;
        const itemEl = event.target.closest('.ler-ac-item');
        if (!itemEl) return;
        const idx = parseInt(itemEl.dataset.idx, 10);
        if (results[idx]) pick(results[idx]);
      });

      list.addEventListener('click', function (event) {
        const itemEl = event.target.closest('.ler-ac-item');
        if (!itemEl) return;
        const idx = parseInt(itemEl.dataset.idx, 10);
        if (results[idx]) pick(results[idx]);
        picking = false;
      });

      input.addEventListener('blur', function () {
        if (picking) {
          picking = false;
          return;
        }
        setTimeout(function () {
          list.classList.remove('show');
        }, 200);
      });

      input.addEventListener('focus', function () {
        if (results.length && input.value.trim().length >= 1) list.classList.add('show');
      });

      query(form, config.countrySelector)?.addEventListener('change', clearSelection);
      query(form, config.registrationNumberSelector)?.addEventListener('input', clearSelection);
      query(form, config.registrationNumberSelector)?.addEventListener('change', clearSelection);
      query(form, config.registrationDateSelector)?.addEventListener('input', clearSelection);
      query(form, config.registrationDateSelector)?.addEventListener('change', clearSelection);
    }

    attachGuillemets();
    attachCountryIdentifierSync(
      selectors.customerCountry,
      selectors.customerIdentifier,
      'identBoundCustomer',
      () => dispatchCustomerChanged()
    );
    attachCountryIdentifierSync(
      selectors.assetOwnerCountry,
      selectors.assetOwnerIdentifier,
      'identBoundAssetOwner'
    );
    attachCountryRegionSync(
      selectors.customerCountry,
      selectors.customerRegion,
      selectors.customerRegistrationDate,
      'regionBoundCustomer',
      () => dispatchCustomerChanged()
    );
    attachCountryRegionSync(
      selectors.assetOwnerCountry,
      selectors.assetOwnerRegion,
      selectors.assetOwnerRegistrationDate,
      'regionBoundAssetOwner',
      () => dispatchAssetOwnerChanged({ reason: 'owner-change' })
    );
    attachRegionAutofill({
      countrySelector: selectors.customerCountry,
      identifierSelector: selectors.customerIdentifier,
      registrationNumberSelector: selectors.customerRegistrationNumber,
      regionSelector: selectors.customerRegion,
      boundKey: 'regionAutofillBoundCustomer',
      onApplied: () => dispatchCustomerChanged(),
    });
    attachRegionAutofill({
      countrySelector: selectors.assetOwnerCountry,
      identifierSelector: selectors.assetOwnerIdentifier,
      registrationNumberSelector: selectors.assetOwnerRegistrationNumber,
      regionSelector: selectors.assetOwnerRegion,
      boundKey: 'regionAutofillBoundAssetOwner',
      onApplied: () => dispatchAssetOwnerChanged({ reason: 'owner-change' }),
    });
    attachAssetOwnerMatchesCustomer();
    attachLerAutocomplete({
      inputSelector: selectors.customerInput,
      listSelector: selectors.customerAcList,
      boundKey: 'lerBoundCustomer',
      countrySelector: selectors.customerCountry,
      regionSelector: selectors.customerRegion,
      identifierSelector: selectors.customerIdentifier,
      registrationNumberSelector: selectors.customerRegistrationNumber,
      registrationDateSelector: selectors.customerRegistrationDate,
      selectedIdentifierSelector: selectors.customerSelectedIdentifier,
      selectedFlagSelector: selectors.customerSelectedFlag,
      changeEventName: customerChangedEvent,
      syncAssetOwnerFromCustomer: true,
    });
    attachLerAutocomplete({
      inputSelector: selectors.assetOwnerInput,
      listSelector: selectors.assetOwnerAcList,
      boundKey: 'lerBoundAssetOwner',
      countrySelector: selectors.assetOwnerCountry,
      regionSelector: selectors.assetOwnerRegion,
      identifierSelector: selectors.assetOwnerIdentifier,
      registrationNumberSelector: selectors.assetOwnerRegistrationNumber,
      registrationDateSelector: selectors.assetOwnerRegistrationDate,
      selectedIdentifierSelector: selectors.assetOwnerSelectedIdentifier,
      selectedFlagSelector: selectors.assetOwnerSelectedFlag,
      changeEventName: assetOwnerChangedEvent,
      syncAssetOwnerFromCustomer: false,
    });
  };
})();
