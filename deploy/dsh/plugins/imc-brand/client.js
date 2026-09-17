window.__ModuleLoader__.load({
  id: "imc-dsh-brand",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    var jsx = require("react/jsx-runtime");

    var BRAND_GLOBAL = "__IMC_DSH_BRAND__";
    var inject = ["slots"];

    function readBrand() {
      var raw = window[BRAND_GLOBAL] || {};
      var productName = String(raw.productName || "IMC Montan AI").trim() || "IMC Montan AI";
      return {
        productName: productName,
        logoAlt: String(raw.logoAlt || productName).trim() || productName,
        logoHref: raw.logoHref ? String(raw.logoHref) : "",
      };
    }

    function BrandMark(props) {
      var brand = readBrand();
      var size = props && props.size ? props.size : 24;
      if (!brand.logoHref) {
        return jsx.jsx("span", {
          style: { display: "inline-block", height: size, width: size },
        });
      }
      return jsx.jsx("img", {
        alt: brand.logoAlt,
        src: brand.logoHref,
        height: size,
        width: size,
        style: { display: "block", height: size, objectFit: "contain", width: size },
      });
    }

    function BrandName() {
      var brand = readBrand();
      return jsx.jsx("span", {
        style: {
          display: "block",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        },
        children: brand.productName,
      });
    }

    function installDocumentTitle(productName) {
      var updating = false;
      var applyTitle = function () {
        if (updating) return;
        var separator = " \u2014 ";
        var title = document.title;
        var at = title.lastIndexOf(separator);
        var next = at === -1 ? productName : title.slice(0, at) + separator + productName;
        if (title === next) return;
        updating = true;
        document.title = next;
        updating = false;
      };
      var observer = new MutationObserver(applyTitle);
      observer.observe(document.head, { childList: true, characterData: true, subtree: true });
      applyTitle();
      return function () {
        observer.disconnect();
      };
    }

    function installTestingNoticeDismissal() {
      var scheduled = false;
      var dismiss = function () {
        scheduled = false;
        var dialogs = document.querySelectorAll('[role="dialog"]');
        for (var i = 0; i < dialogs.length; i += 1) {
          var dialog = dialogs[i];
          var heading = dialog.querySelector("h1, h2, h3, [role=heading]");
          if (!heading || heading.textContent.trim() !== "Internal Testing Notice") continue;
          var buttons = dialog.querySelectorAll("button");
          for (var j = 0; j < buttons.length; j += 1) {
            var button = buttons[j];
            if (button.disabled) continue;
            var label = button.textContent.trim();
            if (label === "Continue" || label === "Продолжить") {
              button.click();
              return;
            }
          }
        }
      };
      var schedule = function () {
        if (scheduled) return;
        scheduled = true;
        window.requestAnimationFrame(dismiss);
      };
      var observer = new MutationObserver(schedule);
      observer.observe(document.body, { childList: true, subtree: true });
      schedule();
      return function () {
        observer.disconnect();
      };
    }

    function apply(ctx) {
      var brand = readBrand();
      ctx.slots.inject("sidebar.brand.mark", function () {
        return ctx.slots.inject("sidebar.brand.name", function () {
          return ctx.slots.inject("conversation.hero.brand.mark", function* () {
            yield ctx.slots.register({ name: "sidebar.brand.mark" }, BrandMark);
            yield ctx.slots.register({ name: "sidebar.brand.name" }, BrandName);
            yield ctx.slots.register({ name: "conversation.hero.brand.mark" }, BrandMark);
          });
        });
      });
      ctx.effect(function () {
        return installDocumentTitle(brand.productName);
      }, "imc-dsh-brand: document title");
      ctx.effect(function () {
        return installTestingNoticeDismissal();
      }, "imc-dsh-brand: dismiss internal testing notice");
    }

    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  },
});
