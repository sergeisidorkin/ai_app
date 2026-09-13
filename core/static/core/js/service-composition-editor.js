(function (global) {
  var QUILL_JS = '/static/letters_app/vendor/quill/quill.min.js';
  var QUILL_CSS = '/static/letters_app/vendor/quill/quill.snow.css';

  function loadCss(href) {
    if (document.querySelector('link[data-policy-quill-css="' + href + '"]')) return;
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset.policyQuillCss = href;
    document.head.appendChild(link);
  }

  function loadQuill(callback) {
    if (window.Quill) {
      callback();
      return;
    }
    window.__policyQuillReadyCallbacks = window.__policyQuillReadyCallbacks || [];
    window.__policyQuillReadyCallbacks.push(callback);
    if (window.__policyQuillLoading) return;
    window.__policyQuillLoading = true;
    loadCss(QUILL_CSS);
    var script = document.createElement('script');
    script.src = QUILL_JS;
    script.async = true;
    script.onload = function () {
      window.__policyQuillLoading = false;
      var callbacks = window.__policyQuillReadyCallbacks || [];
      window.__policyQuillReadyCallbacks = [];
      callbacks.forEach(function (cb) { cb(); });
    };
    script.onerror = function () {
      window.__policyQuillLoading = false;
      window.__policyQuillReadyCallbacks = [];
    };
    document.head.appendChild(script);
  }

  function registerFonts() {
    if (!window.Quill || window.__policyTypicalServiceCompositionFontsRegistered) return;
    var Font = window.Quill.import('formats/font');
    Font.whitelist = ['calibri', 'cambria', 'sans', 'serif', 'monospace', 'georgia', 'times-new-roman'];
    window.Quill.register(Font, true);
    window.__policyTypicalServiceCompositionFontsRegistered = true;
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function normalizeTextToHtml(text) {
    var value = String(text || '').trim();
    if (!value) return '';
    return value.split(/\n{2,}/).map(function (chunk) {
      return '<p>' + escapeHtml(chunk).replace(/\n/g, '<br>') + '</p>';
    }).join('');
  }

  function countEmptyParagraphs(markup) {
    var matches = String(markup || '').match(/<p>(?:\s|&nbsp;|<br\s*\/?>)*<\/p>/gi);
    return matches ? matches.length : 0;
  }

  function restoreEmptyParagraphs(quill, sourceHtml) {
    if (!quill) return;
    var wanted = countEmptyParagraphs(sourceHtml);
    var guard = 0;
    while (countEmptyParagraphs(quill.root.innerHTML) < wanted && guard < 20) {
      var index = Math.max(quill.getLength() - 1, 0);
      quill.insertText(index, '\n', 'silent');
      quill.formatLine(index, 1, 'list', false, 'silent');
      guard += 1;
    }
  }


  function mount(options) {
    options = options || {};
    var toolbar = options.toolbar;
    var editorEl = options.editorEl;
    var onChange = typeof options.onChange === 'function' ? options.onChange : function () {};
    var initialHtml = String(options.html || '').trim();
    var initialPlain = String(options.plainText || '').trim();
    var activeQuill = null;
    var lastRange = null;
    var destroyed = false;
    var colorDragKind = null;
    var unsubscribers = [];

    if (!toolbar || !editorEl) {
      return {
        getState: function () { return { html: initialHtml, plain_text: initialPlain }; },
        destroy: function () {},
        focus: function () {},
        closePopovers: function () { return false; },
        contains: function () { return false; }
      };
    }

    function on(target, type, handler, capture) {
      var opts = !!capture;
      target.addEventListener(type, handler, opts);
      unsubscribers.push(function () {
        target.removeEventListener(type, handler, opts);
      });
    }

    var colorPopovers = Array.prototype.slice.call(toolbar.querySelectorAll('[data-color-popover]'));
    var colorPopoverPlaceholders = {};

    function getColorPopover(kind) {
      var i;
      for (i = 0; i < colorPopovers.length; i += 1) {
        if (colorPopovers[i].dataset.colorPopover === kind) return colorPopovers[i];
      }
      return null;
    }

    function queryColorControl(kind, selector) {
      var popover = getColorPopover(kind);
      return popover ? popover.querySelector(selector) : null;
    }

    function queryColorControls(kind, selector) {
      var popover = getColorPopover(kind);
      return popover ? popover.querySelectorAll(selector) : [];
    }

    function isColorPopoverTarget(node) {
      var i;
      if (!node) return false;
      for (i = 0; i < colorPopovers.length; i += 1) {
        if (colorPopovers[i].contains(node)) return true;
      }
      return false;
    }

  function updateColorPreviews() {
    toolbar.querySelectorAll('[data-color-preview]').forEach(function (preview) {
      var kind = preview.dataset.colorPreview;
      preview.style.backgroundColor = getAppliedToolbarColor(kind);
    });
  }

  function normalizeToolbarColor(value, fallback) {
    var source = String(value || '').trim();
    if (!source) return fallback;
    if (/^#([0-9a-f]{3}){1,2}$/i.test(source)) {
      if (source.length === 4) {
        return '#' + source.slice(1).split('').map(function (part) { return part + part; }).join('');
      }
      return source;
    }
    var rgbMatch = source.match(/^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/i);
    if (!rgbMatch) return fallback;
    return '#' + rgbMatch.slice(1, 4).map(function (part) {
      return Math.max(0, Math.min(255, Number(part) || 0)).toString(16).padStart(2, '0');
    }).join('');
  }

  var COLOR_DEFAULTS = {
    color: '#000000',
    background: '#ffffff'
  };

  function getColorDefault(kind) {
    return COLOR_DEFAULTS[kind] || '#000000';
  }

  function getColorDatasetKey(kind, state) {
    return state + (kind === 'background' ? 'BackgroundColor' : 'TextColor');
  }

  function clampColorChannel(value) {
    return Math.max(0, Math.min(255, Math.round(Number(value) || 0)));
  }

  function clampUnit(value) {
    return Math.max(0, Math.min(1, Number(value) || 0));
  }

  function hexToRgb(value) {
    var hex = normalizeToolbarColor(value, '#000000').slice(1);
    return {
      r: parseInt(hex.slice(0, 2), 16) || 0,
      g: parseInt(hex.slice(2, 4), 16) || 0,
      b: parseInt(hex.slice(4, 6), 16) || 0
    };
  }

  function rgbToHex(rgb) {
    return '#' + ['r', 'g', 'b'].map(function (channel) {
      return clampColorChannel(rgb[channel]).toString(16).padStart(2, '0');
    }).join('');
  }

  function rgbToHsv(rgb) {
    var r = clampColorChannel(rgb.r) / 255;
    var g = clampColorChannel(rgb.g) / 255;
    var b = clampColorChannel(rgb.b) / 255;
    var max = Math.max(r, g, b);
    var min = Math.min(r, g, b);
    var delta = max - min;
    var hue = 0;
    if (delta) {
      if (max === r) hue = ((g - b) / delta) % 6;
      else if (max === g) hue = (b - r) / delta + 2;
      else hue = (r - g) / delta + 4;
      hue = Math.round(hue * 60);
      if (hue < 0) hue += 360;
    }
    return {
      h: hue,
      s: max === 0 ? 0 : delta / max,
      v: max
    };
  }

  function hsvToRgb(hsv) {
    var h = ((Number(hsv.h) || 0) % 360 + 360) % 360;
    var s = clampUnit(hsv.s);
    var v = clampUnit(hsv.v);
    var c = v * s;
    var x = c * (1 - Math.abs((h / 60) % 2 - 1));
    var m = v - c;
    var r1 = 0;
    var g1 = 0;
    var b1 = 0;
    if (h < 60) {
      r1 = c;
      g1 = x;
    } else if (h < 120) {
      r1 = x;
      g1 = c;
    } else if (h < 180) {
      g1 = c;
      b1 = x;
    } else if (h < 240) {
      g1 = x;
      b1 = c;
    } else if (h < 300) {
      r1 = x;
      b1 = c;
    } else {
      r1 = c;
      b1 = x;
    }
    return {
      r: (r1 + m) * 255,
      g: (g1 + m) * 255,
      b: (b1 + m) * 255
    };
  }

  function getPendingToolbarColor(kind) {
    var pendingKey = getColorDatasetKey(kind, 'pending');
    return normalizeToolbarColor(toolbar.dataset[pendingKey], getAppliedToolbarColor(kind));
  }

  function updateColorPickerControls(kind, value) {
    var rgb = hexToRgb(value);
    var hsv = rgbToHsv(rgb);
    var previousHue = Number(toolbar.dataset[getColorDatasetKey(kind, 'hue')]);
    var hue = hsv.s === 0 && Number.isFinite(previousHue) ? previousHue : hsv.h;
    toolbar.dataset[getColorDatasetKey(kind, 'hue')] = String(hue);

    var hueInput = queryColorControl(kind, '[data-color-hue="' + kind + '"]');
    if (hueInput) {
      hueInput.dataset.colorHueValue = String(Math.round(hue));
      hueInput.setAttribute('aria-valuenow', String(Math.round(hue)));
    }

    var hueHandle = queryColorControl(kind, '[data-color-hue-handle="' + kind + '"]');
    if (hueHandle) hueHandle.style.left = (hue / 360 * 100) + '%';

    Array.prototype.forEach.call(queryColorControls(kind, '[data-color-rgb="' + kind + '"]'), function (input) {
      input.value = String(clampColorChannel(rgb[input.dataset.colorChannel]));
    });

    var sv = queryColorControl(kind, '[data-color-sv="' + kind + '"]');
    if (sv) sv.style.setProperty('--proposal-color-picker-hue', String(Math.round(hue)));

    var handle = queryColorControl(kind, '[data-color-sv-handle="' + kind + '"]');
    if (handle) {
      handle.style.left = (hsv.s * 100) + '%';
      handle.style.top = ((1 - hsv.v) * 100) + '%';
    }
  }

  function setToolbarColor(kind, value, commit) {
    var normalized = normalizeToolbarColor(value, getColorDefault(kind));
    toolbar.dataset[getColorDatasetKey(kind, 'pending')] = normalized;
    if (commit) {
      toolbar.dataset[getColorDatasetKey(kind, 'applied')] = normalized;
    }
    updateColorPickerControls(kind, normalized);
    updateColorPreviews();
    return normalized;
  }

  function getAppliedToolbarColor(kind) {
    var key = getColorDatasetKey(kind, 'applied');
    return normalizeToolbarColor(toolbar.dataset[key], getColorDefault(kind));
  }

  function restoreColorPopover(popover) {
    var kind = popover.dataset.colorPopover;
    var placeholder = colorPopoverPlaceholders[kind];
    popover.style.position = '';
    popover.style.left = '';
    popover.style.top = '';
    popover.style.right = '';
    popover.style.zIndex = '';
    if (placeholder && placeholder.parentNode) {
      placeholder.parentNode.insertBefore(popover, placeholder);
      placeholder.parentNode.removeChild(placeholder);
      colorPopoverPlaceholders[kind] = null;
    }
  }

  function closeColorPopovers(exceptKind) {
    colorPopovers.forEach(function (popover) {
      var kind = popover.dataset.colorPopover;
      var keepOpen = exceptKind && kind === exceptKind;
      popover.hidden = !keepOpen;
      var toggle = toolbar.querySelector('[data-color-toggle="' + kind + '"]');
      if (toggle) toggle.setAttribute('aria-expanded', keepOpen ? 'true' : 'false');
      if (!keepOpen) restoreColorPopover(popover);
    });
  }

  function openColorPopover(kind) {
    var popover = getColorPopover(kind);
    var toggle = toolbar.querySelector('[data-color-toggle="' + kind + '"]');
    if (!popover || !toggle) return;
    var shouldOpen = popover.hidden;
    closeListMenu();
    closeColorPopovers(shouldOpen ? kind : null);
    if (!shouldOpen) return;
    setToolbarColor(kind, getAppliedToolbarColor(kind), false);
    var rect = toggle.getBoundingClientRect();
    if (popover.parentNode !== document.body) {
      colorPopoverPlaceholders[kind] = document.createComment('composition-color-popover-' + kind);
      popover.parentNode.insertBefore(colorPopoverPlaceholders[kind], popover);
      document.body.appendChild(popover);
    }
    popover.hidden = false;
    popover.style.position = 'fixed';
    popover.style.zIndex = '1080';
    var width = popover.offsetWidth || 208;
    var left = Math.round(rect.right - width);
    if (left < 8) left = 8;
    if (left + width > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - width - 8);
    }
    popover.style.left = left + 'px';
    popover.style.top = Math.round(rect.bottom + 6) + 'px';
    popover.style.right = 'auto';
  }

  function commitToolbarColor(kind) {
    setToolbarColor(kind, getPendingToolbarColor(kind), true);
    closeColorPopovers();
  }

  function resetToolbarColor(kind) {
    setToolbarColor(kind, getColorDefault(kind), false);
  }

  function initializeToolbarColors() {
    ['color', 'background'].forEach(function (kind) {
      setToolbarColor(kind, getColorDefault(kind), true);
    });
  }

  function updateColorFromSv(kind, event) {
    var sv = queryColorControl(kind, '[data-color-sv="' + kind + '"]');
    if (!sv) return;
    var rect = sv.getBoundingClientRect();
    var saturation = clampUnit((event.clientX - rect.left) / Math.max(1, rect.width));
    var value = clampUnit(1 - ((event.clientY - rect.top) / Math.max(1, rect.height)));
    var currentHsv = rgbToHsv(hexToRgb(getPendingToolbarColor(kind)));
    var hue = Number(toolbar.dataset[getColorDatasetKey(kind, 'hue')]);
    if (!Number.isFinite(hue)) hue = currentHsv.h;
    setToolbarColor(kind, rgbToHex(hsvToRgb({ h: hue, s: saturation, v: value })), false);
  }

  function updateColorFromHue(kind, hue) {
    var currentHsv = rgbToHsv(hexToRgb(getPendingToolbarColor(kind)));
    var saturation = currentHsv.s > 0.01 ? currentHsv.s : 1;
    var value = currentHsv.v > 0.01 ? currentHsv.v : 1;
    setToolbarColor(kind, rgbToHex(hsvToRgb({
      h: Number(hue) || 0,
      s: saturation,
      v: value
    })), false);
  }

  function updateColorFromHueStrip(kind, event) {
    var strip = queryColorControl(kind, '[data-color-hue="' + kind + '"]');
    if (!strip) return;
    var rect = strip.getBoundingClientRect();
    var ratio = clampUnit((event.clientX - rect.left) / Math.max(1, rect.width));
    updateColorFromHue(kind, ratio * 360);
  }

  function updateColorFromRgb(kind) {
    var rgb = { r: 0, g: 0, b: 0 };
    Array.prototype.forEach.call(queryColorControls(kind, '[data-color-rgb="' + kind + '"]'), function (input) {
      rgb[input.dataset.colorChannel] = clampColorChannel(input.value);
    });
    setToolbarColor(kind, rgbToHex(rgb), false);
  }

  function setToolbarButtonActive(button, isActive) {
    if (!button) return;
    button.classList.toggle('is-active', !!isActive);
    button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  }

  var LIST_MARKER_TYPES = ['bullet', 'circle', 'square', 'dash', 'ndash', 'check'];
  var LIST_MARKER_LABELS = {
    bullet: 'Точка',
    circle: 'Круг',
    square: 'Квадрат',
    dash: 'Дефис',
    ndash: 'Тире',
    check: 'Галочка'
  };
  var LIST_MARKER_ICON_URLS = {
    bullet: '/static/core/icons/list-ul2.svg',
    circle: '/static/core/icons/list-circle.svg',
    square: '/static/core/icons/list-square.svg',
    dash: '/static/core/icons/list-dash.svg',
    ndash: '/static/core/icons/list-ndash.svg',
    check: '/static/core/icons/list-check.svg'
  };

  function isListMarkerType(value) {
    return LIST_MARKER_TYPES.indexOf(String(value || '').trim()) !== -1;
  }

  function renderListMarkerPrimaryIcon(primary, activeMarker) {
    var iconSrc = LIST_MARKER_ICON_URLS[activeMarker] || LIST_MARKER_ICON_URLS.bullet;
    var icon = primary.querySelector('[data-list-marker-icon]');
    if (!icon || icon.tagName !== 'IMG') {
      primary.innerHTML = '<img src="' + iconSrc + '" alt="" class="proposal-service-text-toolbar__icon" data-list-marker-icon>';
    } else {
      icon.src = iconSrc;
      icon.className = 'proposal-service-text-toolbar__icon';
    }
  }

  function updateListMarkerControl(listType) {
    var activeMarker = isListMarkerType(listType)
      ? String(listType)
      : (isListMarkerType(toolbar.dataset.listMarker) ? toolbar.dataset.listMarker : 'bullet');
    toolbar.dataset.listMarker = activeMarker;
    var primary = toolbar.querySelector('[data-list-marker-primary]');
    if (primary) {
      primary.dataset.list = activeMarker;
      primary.setAttribute('aria-label', LIST_MARKER_LABELS[activeMarker] || 'Маркированный список');
      primary.setAttribute('title', LIST_MARKER_LABELS[activeMarker] || 'Маркированный список');
      renderListMarkerPrimaryIcon(primary, activeMarker);
    }
    toolbar.querySelectorAll('[data-list-marker-option]').forEach(function (option) {
      var isSelected = option.dataset.list === activeMarker;
      option.classList.toggle('active', isSelected);
      option.setAttribute('aria-current', isSelected ? 'true' : 'false');
    });
  }

  function syncToolbarState() {
    var format = activeQuill ? activeQuill.getFormat(lastRange || activeQuill.getSelection() || undefined) : {};
    var fontSelect = toolbar.querySelector('select[data-format="font"]');
    var currentFont = String(format.font || 'calibri').trim() || 'calibri';
    if (fontSelect) {
      var hasOption = Array.from(fontSelect.options).some(function (option) {
        return option.value === currentFont;
      });
      fontSelect.value = hasOption ? currentFont : 'calibri';
    }

    toolbar.querySelectorAll('button[data-format]').forEach(function (button) {
      setToolbarButtonActive(button, !!format[button.dataset.format]);
    });
    var currentList = String(format.list || '');
    updateListMarkerControl(currentList);
    toolbar.querySelectorAll('button[data-list]:not([data-list-marker-option])').forEach(function (button) {
      setToolbarButtonActive(button, currentList === button.dataset.list);
    });
    toolbar.querySelectorAll('button[data-align]').forEach(function (button) {
      var align = format.align || 'left';
      setToolbarButtonActive(button, align === button.dataset.align);
    });

    updateColorPreviews();
  }

  function restoreSelection() {
    if (!activeQuill) return;
    activeQuill.focus();
    if (lastRange) {
      activeQuill.setSelection(lastRange.index, lastRange.length, 'silent');
    } else {
      activeQuill.getSelection(true);
    }
  }

  function applyFontToDocument(value) {
    if (!activeQuill) return;
    var font = value || false;
    var range = lastRange || activeQuill.getSelection();
    if (range && range.length > 0) {
      activeQuill.formatText(range.index, range.length, 'font', font, 'user');
      return;
    }
    var len = activeQuill.getLength();
    if (len > 1) {
      activeQuill.formatText(0, len - 1, 'font', font, 'user');
    } else {
      activeQuill.format('font', font);
    }
  }


    function getState() {
      if (!activeQuill) {
        return {
          html: initialHtml,
          plain_text: initialPlain
        };
      }
      var html = activeQuill.root.innerHTML === '<p><br></p>' ? '' : activeQuill.root.innerHTML;
      var plainText = activeQuill.getText().replace(/\s+$/, '').trim();
      return {
        html: html,
        plain_text: plainText
      };
    }

    function syncState(source) {
      var payload = getState();
      if (payload.html) initialHtml = payload.html;
      if (payload.plain_text || payload.html) initialPlain = payload.plain_text;
      onChange(payload, source);
      return payload;
    }

    function queueSyncState() {
      window.requestAnimationFrame(function () {
        if (!destroyed) syncState('user');
      });
    }

    function closePopovers() {
      var anyOpen = false;
      colorPopovers.forEach(function (popover) {
        if (!popover.hidden) anyOpen = true;
      });
      if (listMenu && listMenu.classList.contains('show')) anyOpen = true;
      closeColorPopovers();
      closeListMenu();
      return anyOpen;
    }

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      closeListMenu();
      closeColorPopovers();
      unsubscribers.forEach(function (fn) { fn(); });
      unsubscribers = [];
      colorDragKind = null;
      if (activeQuill) {
        try { activeQuill.off('selection-change'); } catch (err) {}
        try { activeQuill.off('text-change'); } catch (err) {}
        activeQuill = null;
      }
      lastRange = null;
    }

    function focus() {
      if (activeQuill) activeQuill.focus();
      else if (editorEl && typeof editorEl.focus === 'function') editorEl.focus();
    }

    function contains(node) {
      if (!node) return false;
      if (toolbar.contains(node) || editorEl.contains(node)) return true;
      if (listMenu && listMenu.contains(node)) return true;
      if (isColorPopoverTarget(node)) return true;
      return false;
    }

    var listMenu = toolbar.querySelector('.proposal-service-text-toolbar__list-menu');
    var listToggle = toolbar.querySelector('[data-bs-toggle="dropdown"]');
    var listMenuPlaceholder = null;

    function closeListMenu() {
      if (listToggle) listToggle.setAttribute('aria-expanded', 'false');
      if (!listMenu) return;
      listMenu.classList.remove('show');
      listMenu.style.display = '';
      listMenu.style.position = '';
      listMenu.style.left = '';
      listMenu.style.top = '';
      listMenu.style.right = '';
      listMenu.style.bottom = '';
      listMenu.style.margin = '';
      listMenu.style.transform = '';
      listMenu.style.zIndex = '';
      if (listMenuPlaceholder && listMenuPlaceholder.parentNode) {
        listMenuPlaceholder.parentNode.insertBefore(listMenu, listMenuPlaceholder);
        listMenuPlaceholder.parentNode.removeChild(listMenuPlaceholder);
        listMenuPlaceholder = null;
      }
    }

    function openListMenu() {
      if (!listMenu || !listToggle) return;
      closeColorPopovers();
      var rect = listToggle.getBoundingClientRect();
      if (listMenu.parentNode !== document.body) {
        listMenuPlaceholder = document.createComment('composition-list-menu');
        listMenu.parentNode.insertBefore(listMenuPlaceholder, listMenu);
        document.body.appendChild(listMenu);
      }
      listMenu.classList.add('show');
      listMenu.style.position = 'fixed';
      listMenu.style.display = 'block';
      listMenu.style.left = Math.round(rect.left) + 'px';
      listMenu.style.top = Math.round(rect.bottom + 2) + 'px';
      listMenu.style.right = 'auto';
      listMenu.style.bottom = 'auto';
      listMenu.style.margin = '0';
      listMenu.style.transform = 'none';
      listMenu.style.zIndex = '1080';
      listToggle.setAttribute('aria-expanded', 'true');
    }

    function applyListFormat(listType, isMarkerOption) {
      if (!activeQuill) return;
      restoreSelection();
      var currentList = activeQuill.getFormat().list || false;
      var toggleCurrent = !isMarkerOption && currentList === listType;
      if (isListMarkerType(listType)) updateListMarkerControl(listType);
      activeQuill.format('list', toggleCurrent ? false : listType);
      queueSyncState();
      syncToolbarState();
      closeListMenu();
    }

    if (listToggle && listMenu) {
      on(listToggle, 'pointerdown', function (event) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        var willOpen = !listMenu.classList.contains('show');
        closeListMenu();
        if (willOpen) openListMenu();
      }, true);
      on(listToggle, 'click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
      }, true);
      on(listMenu, 'click', function (event) {
        var option = event.target.closest('button[data-list]');
        if (!option) return;
        event.preventDefault();
        applyListFormat(option.dataset.list, !!option.dataset.listMarkerOption);
      });
      on(document, 'click', function (event) {
        if (!listMenu.classList.contains('show')) return;
        if (listToggle.contains(event.target) || listMenu.contains(event.target)) return;
        closeListMenu();
      }, true);
    }

  on(toolbar, 'click', function (event) {
    if (event.target.closest('[data-bs-toggle="dropdown"]')) return;
    var colorToggle = event.target.closest('button[data-color-toggle]');
    if (colorToggle && toolbar.contains(colorToggle)) {
      event.preventDefault();
      openColorPopover(colorToggle.dataset.colorToggle);
      return;
    }
    var button = event.target.closest('button[data-format], button[data-list], button[data-action], button[data-align], button[data-apply-color]');
    if (!button || !activeQuill) return;
    event.preventDefault();
    restoreSelection();
    if (button.dataset.format) {
      var formatName = button.dataset.format;
      var currentFormat = activeQuill.getFormat();
      var current = Object.prototype.hasOwnProperty.call(currentFormat, formatName) ? currentFormat[formatName] : false;
      activeQuill.format(formatName, current ? false : true);
      queueSyncState();
      syncToolbarState();
      return;
    }
    if (button.dataset.list) {
      applyListFormat(button.dataset.list, !!button.dataset.listMarkerOption);
      return;
    }
    if (button.dataset.align) {
      var align = button.dataset.align;
      activeQuill.format('align', align === 'left' ? false : align);
      queueSyncState();
      syncToolbarState();
      return;
    }
    if (button.dataset.applyColor) {
      activeQuill.format(button.dataset.applyColor, getAppliedToolbarColor(button.dataset.applyColor));
      queueSyncState();
      syncToolbarState();
      return;
    }
    if (button.dataset.action === 'clean') {
      var safeRange = activeQuill.getSelection(true);
      if (safeRange && safeRange.length) {
        activeQuill.removeFormat(safeRange.index, safeRange.length);
      } else {
        activeQuill.format('bold', false);
        activeQuill.format('italic', false);
        activeQuill.format('underline', false);
        activeQuill.format('color', false);
        activeQuill.format('background', false);
        activeQuill.format('list', false);
        activeQuill.format('align', false);
      }
      queueSyncState();
      syncToolbarState();
    }
  });

  on(toolbar, 'change', function (event) {
    var select = event.target.closest('select[data-format]');
    if (select && activeQuill) {
      restoreSelection();
      if (select.dataset.format === 'font') {
        applyFontToDocument(select.value);
      } else {
        activeQuill.format(select.dataset.format, select.value || false);
      }
      queueSyncState();
      syncToolbarState();
      return;
    }
  });

  on(toolbar, 'input', function (event) {
    var rgbInput = event.target.closest('[data-color-rgb]');
    if (rgbInput && (toolbar.contains(rgbInput) || isColorPopoverTarget(rgbInput))) {
      updateColorFromRgb(rgbInput.dataset.colorRgb);
    }
  });

  on(toolbar, 'pointerdown', function (event) {
    var hue = event.target.closest('[data-color-hue]');
    if (hue && (toolbar.contains(hue) || isColorPopoverTarget(hue))) {
      event.preventDefault();
      colorDragKind = 'hue:' + hue.dataset.colorHue;
      updateColorFromHueStrip(hue.dataset.colorHue, event);
      return;
    }
    var sv = event.target.closest('[data-color-sv]');
    if (!sv || !(toolbar.contains(sv) || isColorPopoverTarget(sv))) return;
    event.preventDefault();
    colorDragKind = sv.dataset.colorSv;
    updateColorFromSv(colorDragKind, event);
  });

  on(document, 'pointermove', function (event) {
    if (!colorDragKind) return;
    event.preventDefault();
    if (colorDragKind.indexOf('hue:') === 0) {
      updateColorFromHueStrip(colorDragKind.slice(4), event);
      return;
    }
    updateColorFromSv(colorDragKind, event);
  });

  on(document, 'pointerup', function () {
    colorDragKind = null;
  });

  colorPopovers.forEach(function (popover) {
    on(popover, 'click', function (event) {
      var colorCommit = event.target.closest('button[data-color-commit]');
      if (colorCommit && popover.contains(colorCommit)) {
        event.preventDefault();
        commitToolbarColor(colorCommit.dataset.colorCommit);
        return;
      }
      var colorReset = event.target.closest('button[data-color-reset]');
      if (colorReset && popover.contains(colorReset)) {
        event.preventDefault();
        resetToolbarColor(colorReset.dataset.colorReset);
      }
    });
    on(popover, 'input', function (event) {
      var rgbInput = event.target.closest('[data-color-rgb]');
      if (rgbInput && popover.contains(rgbInput)) {
        updateColorFromRgb(rgbInput.dataset.colorRgb);
      }
    });
    on(popover, 'pointerdown', function (event) {
      var hue = event.target.closest('[data-color-hue]');
      if (hue && popover.contains(hue)) {
        event.preventDefault();
        colorDragKind = 'hue:' + hue.dataset.colorHue;
        updateColorFromHueStrip(hue.dataset.colorHue, event);
        return;
      }
      var sv = event.target.closest('[data-color-sv]');
      if (!sv || !popover.contains(sv)) return;
      event.preventDefault();
      colorDragKind = sv.dataset.colorSv;
      updateColorFromSv(colorDragKind, event);
    });
  });

  on(document, 'click', function (event) {
    if (
      toolbar.contains(event.target)
      || (editorEl && editorEl.contains(event.target))
      || isColorPopoverTarget(event.target)
    ) {
      return;
    }
    closeColorPopovers();
  });

  on(document, 'keydown', function (event) {
    if (event.key === 'Escape') {
      closeColorPopovers();
      return;
    }
    var hue = event.target.closest && event.target.closest('[data-color-hue]');
    if (!hue || !(toolbar.contains(hue) || isColorPopoverTarget(hue))) return;
    var delta = event.key === 'ArrowRight' || event.key === 'ArrowUp'
      ? 5
      : (event.key === 'ArrowLeft' || event.key === 'ArrowDown' ? -5 : 0);
    if (!delta) return;
    event.preventDefault();
    var current = Number(hue.dataset.colorHueValue) || 0;
    updateColorFromHue(hue.dataset.colorHue, current + delta);
  });


    loadQuill(function () {
      if (destroyed) return;
      registerFonts();
      activeQuill = new window.Quill(editorEl, {
        theme: 'snow',
        modules: {
          toolbar: false
        }
      });
      var html = initialHtml || normalizeTextToHtml(initialPlain);
      if (html) {
        var delta = activeQuill.clipboard.convert({ html: html });
        activeQuill.setContents(delta, 'silent');
        restoreEmptyParagraphs(activeQuill, html);
      } else {
        activeQuill.format('font', 'calibri', 'silent');
        activeQuill.format('align', 'justify', 'silent');
      }
      activeQuill.on('selection-change', function (range) {
        if (range) {
          lastRange = range;
        }
        syncToolbarState();
      });
      activeQuill.on('text-change', function (delta, oldDelta, source) {
        if (source === 'user') syncState(source);
        syncToolbarState();
      });
      on(editorEl, 'click', function () {
        if (activeQuill) activeQuill.focus();
      });
      initializeToolbarColors();
      syncToolbarState();
      if (typeof options.onReady === 'function') options.onReady();
    });

    return {
      getState: getState,
      destroy: destroy,
      focus: focus,
      closePopovers: closePopovers,
      contains: contains
    };
  }

  global.ServiceCompositionEditor = {
    mount: mount,
    loadQuill: loadQuill,
    normalizeTextToHtml: normalizeTextToHtml
  };
})(window);
