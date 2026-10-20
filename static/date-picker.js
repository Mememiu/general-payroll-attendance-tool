/* 日期/月份选择器：用 flatpickr 接管原生控件。
 *
 * 为什么换掉手写方案：
 * 原生 date/month 控件一旦聚焦，Chromium 会全选内部子段并画出蓝色高亮，
 * 该高亮位于 UA shadow DOM，::selection 等作者样式覆盖无效。
 * flatpickr 的 altInput 模式把原生 input 降级为 type="hidden" 的值载体，
 * 页面上只呈现一个普通的 type="text" 输入框，由此彻底摆脱原生渲染与选区。
 *
 * 约束：
 * - 资源全部本地化（static/vendor/flatpickr），项目为离线应用。
 * - 原生 input 的 type / name 保留，值格式不变（month=YYYY-MM，date=YYYY-MM-DD），
 *   后端契约与既有测试均不受影响。
 */

(function (root) {
  "use strict";

  var PICKERS = new WeakMap();

  function isMonth(input) {
    return (input.getAttribute("type") || "").toLowerCase() === "month";
  }

  /* 让程序化赋值（如编辑弹窗回填、切换规则版本）也能同步到可见输入框。
     flatpickr 只监听自身交互，直接改 input.value 不会刷新 altInput。 */
  function hookValue(input, picker) {
    if (input.__fpHooked) return;
    input.__fpHooked = true;

    var descriptor = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value"
    );
    if (!descriptor || !descriptor.set) return;

    var syncing = false;

    Object.defineProperty(input, "value", {
      configurable: true,
      get: function () {
        return descriptor.get.call(this);
      },
      set: function (next) {
        descriptor.set.call(this, next);
        if (syncing) return;
        syncing = true;
        try {
          picker.setDate(next || null, false);
        } catch (error) {
          /* 非法值交给 flatpickr 自行忽略 */
        } finally {
          syncing = false;
        }
      }
    });
  }

  function resolveLocale() {
    /* l10n/zh.js 导出的是命名空间 { Mandarin: {...} }，不是 locale 本身。
       直接传命名空间会静默回落到英文（不报错），肉眼只在面板文字上暴露。 */
    var pack = root.zh;
    if (pack && pack.Mandarin) return pack.Mandarin;
    if (pack && pack.months) return pack;
    return "zh";
  }

  function buildConfig(input, monthMode) {
    var config = {
      locale: resolveLocale(),
      altInput: true,
      /* 保留 flatpickr 默认类名，再补 flatpickr-input：
         否则 workspace.css 里 input[readonly] 的灰底样式会命中可见框，
         让它看起来像禁用控件。 */
      altInputClass: "flatpickr-input form-control input",
      allowInput: false,
      disableMobile: true,
      dateFormat: monthMode ? "Y-m" : "Y-m-d",
      altFormat: monthMode ? "Y年m月" : "Y年m月d日",
      /* 月份选择器只选到月，隐藏日视图 */
      onReady: function (_, __, instance) {
        instance.calendarContainer.classList.add(
          monthMode ? "fp-scope-month" : "fp-scope-date"
        );
      },
      onChange: function () {
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
    };

    if (monthMode && typeof root.monthSelectPlugin === "function") {
      config.plugins = [
        root.monthSelectPlugin({
          shorthand: false,
          dateFormat: "Y-m",
          altFormat: "Y年m月"
        })
      ];
    }

    return config;
  }

  function enhance(input) {
    if (input.dataset.fpBound) return;
    if (typeof root.flatpickr !== "function") return;

    input.dataset.fpBound = "1";
    var monthMode = isMonth(input);
    var picker = root.flatpickr(input, buildConfig(input, monthMode));

    PICKERS.set(input, picker);
    hookValue(input, picker);
  }

  function init() {
    document.querySelectorAll('input[type="month"], input[type="date"]').forEach(enhance);
  }

  document.addEventListener("DOMContentLoaded", init);

  root.DatePickers = {
    init: init,
    /* 供动态插入节点后重新扫描 */
    rebind: init
  };
})(typeof globalThis === "object" ? globalThis : this);