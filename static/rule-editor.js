(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.RuleEditor = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  const rules =
/* REQUIRED_RULES_START */
[
  {"path":"company.worktime.mode"},
  {"path":"company.worktime.daily_minutes"},
  {"path":"company.worktime.standard_start"},
  {"path":"company.worktime.standard_end"},
  {"path":"company.worktime.lunch.enabled"},
  {"path":"company.worktime.lunch.start","when":{"company.worktime.lunch.enabled":true}},
  {"path":"company.worktime.lunch.end","when":{"company.worktime.lunch.enabled":true}},
  {"path":"company.worktime.strategy","when":{"company.worktime.mode":"flexible"}},
  {"path":"company.worktime.latest_start","when":{"company.worktime.strategy":"latest_start"}},
  {"path":"company.worktime.core_start","when":{"company.worktime.strategy":"core_hours"}},
  {"path":"company.worktime.core_end","when":{"company.worktime.strategy":"core_hours"}},
  {"path":"company.overtime.enabled"},
  {"path":"company.overtime.cash_enabled"},
  {"path":"company.overtime.comp_time_enabled"},
  {"path":"company.overtime.approval_required","when":{"company.overtime.enabled":true}},
  {"path":"company.overtime.cross_midnight_allowed","when":{"company.overtime.enabled":true}},
  {"path":"company.overtime.minimum_minutes","when":{"company.overtime.enabled":true}},
  {"path":"company.overtime.rounding_mode","when":{"company.overtime.enabled":true}},
  {"path":"company.overtime.start_mode","when":{"company.overtime.enabled":true}},
  {"path":"company.overtime.cash_formula","when":{"company.overtime.enabled":true,"company.overtime.cash_enabled":true}},
  {"path":"company.overtime.cash_rate","when":{"company.overtime.enabled":true,"company.overtime.cash_enabled":true}},
  {"path":"company.overtime.day_rates.workday","when":{"company.overtime.enabled":true,"company.overtime.cash_enabled":true}},
  {"path":"company.overtime.day_rates.rest_day","when":{"company.overtime.enabled":true,"company.overtime.cash_enabled":true}},
  {"path":"company.overtime.day_rates.holiday","when":{"company.overtime.enabled":true,"company.overtime.cash_enabled":true}},
  {"path":"company.overtime.comp_time_ratio","when":{"company.overtime.enabled":true,"company.overtime.comp_time_enabled":true}},
  {"path":"company.payroll.monthly_pay_days"},
  {"path":"company.payroll.perfect_attendance_award"},
  {"path":"company.payroll.rounding_places"},
  {"path":"company.payroll.rounding_mode"},
  {"path":"company.income_items.allowance.taxable"},
  {"path":"company.income_items.allowance.included_in_social_base"},
  {"path":"company.income_items.allowance.included_in_fund_base"},
  {"path":"company.income_items.bonus.taxable"},
  {"path":"company.income_items.bonus.included_in_social_base"},
  {"path":"company.income_items.bonus.included_in_fund_base"},
  {"path":"statutory.tax.enabled"},
  {"path":"statutory.tax.system","when":{"statutory.tax.enabled":true}},
  {"path":"statutory.tax.monthly_exemption","when":{"statutory.tax.enabled":true}},
  {"path":"statutory.tax.negative_tax_mode","when":{"statutory.tax.enabled":true}},
  {"path":"statutory.tax.effective_from","when":{"statutory.tax.enabled":true}},
  {"path":"statutory.tax.brackets","when":{"statutory.tax.enabled":true}},
  {"path":"employment_types"}
]
/* REQUIRED_RULES_END */;

  function pathValue(source, path) {
    return path.replace(/\[(\d+)\]/g, ".$1").split(".")
      .reduce((value, key) => value == null ? undefined : value[key], source);
  }

  function supplied(value, path) {
    if (typeof value === "boolean" || typeof value === "number") return true;
    if (typeof value === "string") return value.trim() !== "";
    if (Array.isArray(value)) return value.length > 0;
    return value !== null && value !== undefined;
  }

  function active(rule, source) {
    return !rule.when || Object.entries(rule.when).every(([path, expected]) => pathValue(source, path) === expected);
  }

  function conditionValue(value) {
    if (value === "true") return true;
    if (value === "false") return false;
    return value;
  }

  function requiredConditionMatches(condition, source) {
    if (!condition) return true;
    return condition.split(";").every(part => {
      const split = part.lastIndexOf(":");
      if (split < 1) return false;
      return pathValue(source, part.slice(0, split)) === conditionValue(part.slice(split + 1));
    });
  }

  function fieldValue(input) {
    if (input.dataset.boolean !== undefined) {
      if (input.value === "") return null;
      return input.value === "true";
    }
    if (input.dataset.jsonList !== undefined) {
      if (input.value.trim() === "") return [];
      const value = JSON.parse(input.value);
      if (!Array.isArray(value)) throw new TypeError("必须填写 JSON 数组");
      return value;
    }
    if (input.type === "checkbox") return input.checked;
    if (input.type === "number") {
      return input.value === "" ? null : (input.step === "1" || input.step === "" ? Number(input.value) : input.value);
    }
    return input.value || null;
  }

  function fieldDisplayValue(input, value) {
    if (input.dataset.jsonList !== undefined) {
      return value == null ? "" : JSON.stringify(value, null, 2);
    }
    if (input.dataset.boolean !== undefined) {
      return value === null || value === undefined ? "" : String(value);
    }
    return value ?? "";
  }

  function requiredState(snapshot, validationErrors) {
    const source = snapshot && typeof snapshot === "object" ? snapshot : {};
    const errors = Array.isArray(validationErrors) ? validationErrors : [];
    const paths = new Set(rules.filter(rule => active(rule, source)).map(rule => rule.path));
    const ownerPath = field => [...paths]
      .filter(path => field === path || field.startsWith(`${path}.`) || field.startsWith(`${path}[`))
      .sort((left, right) => right.length - left.length)[0];
    const invalid = new Set(errors
      .map(error => error && typeof error === "object" && error.field ? ownerPath(error.field) : null)
      .filter(Boolean));
    const required = paths.size;
    const completed = [...paths].filter(path => supplied(pathValue(source, path), path) && !invalid.has(path)).length;
    const percent = required ? Math.round(completed * 100 / required) : 100;
    return {required, completed, percent};
  }

  function validateEmploymentTypeDraft(item, items, editingIndex) {
    const code = String(item?.code ?? "").trim();
    const name = String(item?.name ?? "").trim();
    if (!/^[a-z][a-z0-9_]*$/.test(code)) {
      return {code: "代码只能使用小写字母、数字和下划线，且必须以小写字母开头"};
    }
    if (!name) return {name: "请填写用工类型名称"};
    const others = (Array.isArray(items) ? items : []).filter((_, index) => index !== editingIndex);
    if (others.some(existing => String(existing?.code ?? "").trim() === code)) {
      return {code: "用工类型代码已存在"};
    }
    if (others.some(existing => String(existing?.name ?? "").trim() === name)) {
      return {name: "用工类型名称已存在"};
    }
    return {};
  }

  function statutoryTimingState(mode) {
    const active = mode === "cutoff_day";
    return {show: active, required: active};
  }

  function normalizeStatutoryTiming(item) {
    const normalized = {...item};
    for (const prefix of ["hire", "termination"]) {
      const rule = normalized[`${prefix}_month_rule`] || "";
      const cutoffKey = `${prefix}_cutoff_day`;
      normalized[cutoffKey] = rule === "cutoff_day"
        && normalized[cutoffKey] !== ""
        && normalized[cutoffKey] != null
        ? Number(normalized[cutoffKey])
        : null;
    }
    return normalized;
  }

  return {fieldDisplayValue, fieldValue, normalizeStatutoryTiming, requiredConditionMatches, requiredState, rules, statutoryTimingState, validateEmploymentTypeDraft};
});
