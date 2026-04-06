window.UIPref = (function () {
  var PREFIX = 'app:';
  var LEGACY_PREFIX = 'app:';

  function scope() {
    var raw = window.__uiPrefScope;
    return raw ? String(raw) : 'anon';
  }

  function scopedKey(key) {
    return PREFIX + scope() + ':' + key;
  }

  function legacyKey(key) {
    return LEGACY_PREFIX + key;
  }

  function get(key, fallback) {
    try {
      var raw = localStorage.getItem(scopedKey(key));
      if (raw === null) raw = localStorage.getItem(legacyKey(key));
      return raw === null ? fallback : JSON.parse(raw);
    } catch (e) { return fallback; }
  }

  function set(key, value) {
    try { localStorage.setItem(scopedKey(key), JSON.stringify(value)); } catch (e) {}
  }

  function remove(key) {
    try {
      localStorage.removeItem(scopedKey(key));
      localStorage.removeItem(legacyKey(key));
    } catch (e) {}
  }

  return { get: get, set: set, remove: remove };
})();
