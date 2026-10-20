import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from app import create_app


NODE = shutil.which("node") or os.environ.get("CODEX_NODE")
if NODE is None:
    bundled = list(Path.home().glob(".cache/codex-runtimes/*/dependencies/node/bin/node"))
    NODE = str(bundled[0]) if bundled else None


class WorkspaceUiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions["task_store"].close()

    def test_workspace_exposes_product_navigation_and_rule_tabs(self):
        html = self.client.get("/").get_data(as_text=True)
        for label in ("薪酬计算", "规则配置", "计算记录", "使用说明", "高级设置"):
            self.assertIn(label, html)
        for label in ("公司制度", "法定政策", "商业保险", "员工例外"):
            self.assertIn(label, html)
        self.assertNotIn('data-tab="tasks"', html)
        self.assertNotIn('id="tab-tasks"', html)

    def test_mobile_rule_tabs_use_two_columns_without_clipping(self):
        css = Path("static/workspace-responsive.css").read_text(encoding="utf-8")

        self.assertRegex(
            css,
            r"@media \(max-width: 560px\)[\s\S]*?\.tabs\s*\{[^}]*"
            r"display:\s*grid;[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)",
        )
        self.assertRegex(
            css,
            r"@media \(max-width: 560px\)[\s\S]*?\.tabs button\s*\{[^}]*"
            r"min-width:\s*0;[^}]*white-space:\s*normal",
        )

    def test_calculation_records_page_is_read_only_and_loads_real_api(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('data-page="calculation-records"', html)
        self.assertIn('id="calculation-records"', html)
        self.assertIn('id="calculation-records-table"', html)
        records_page = html.split('<section id="calculation-records"', 1)[1].split(
            "</section>", 1
        )[0]
        self.assertNotIn("<form", records_page)
        self.assertNotIn("编辑", records_page)
        self.assertIn("操作", records_page)
        script = Path("static/workspace.js").read_text(encoding="utf-8")
        self.assertIn("/api/calculation-records", script)
        self.assertIn("renderCalculationRecords", script)
        self.assertIn("downloadTokens", script)
        self.assertIn("重新计算", script)

    def test_monthly_form_has_two_xlsx_uploads_and_published_policy_selection(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('name="attendance"', html)
        self.assertIn('name="employee_payroll"', html)
        self.assertIn('href="/templates/employee-payroll.xlsx"', html)
        self.assertIn("下载员工薪酬模板", html)
        self.assertIn('name="policy_version_id"', html)
        self.assertNotIn('name="payroll_rules"', html)

    def test_rule_editor_has_version_actions_and_dynamic_rule_tables(self):
        html = self.client.get("/").get_data(as_text=True)
        for action in ("保存草稿", "检查规则", "发布版本", "复制新版本"):
            self.assertIn(action, html)
        self.assertIn('id="leave-table"', html)
        self.assertIn('id="insurance-table"', html)
        self.assertIn('id="housing-fund-table"', html)
        self.assertIn("住房公积金", html)
        self.assertIn('id="leave-dialog"', html)
        self.assertIn('id="insurance-dialog"', html)

    def test_rule_editor_marks_required_and_conditional_fields(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="policy-completion"', html)
        self.assertIn('class="required-mark"', html)
        self.assertIn('data-required-path="company.worktime.mode"', html)
        self.assertIn(
            'data-required-when="company.worktime.lunch.enabled:true"', html
        )
        self.assertIn('data-error-for="company.worktime.mode"', html)
        script = Path("static/workspace.js").read_text(encoding="utf-8")
        self.assertRegex(script, r"refreshRequiredState\(\);\s*loadPolicies")

    def test_required_rules_are_parseable_and_cover_compound_conditions(self):
        source = Path("static/rule-editor.js").read_text(encoding="utf-8")
        payload = re.search(
            r"/\* REQUIRED_RULES_START \*/\n(.*?)\n/\* REQUIRED_RULES_END \*/",
            source,
            re.DOTALL,
        ).group(1)
        rules = json.loads(payload)
        by_path = {rule["path"]: rule for rule in rules}
        self.assertEqual(
            by_path["company.overtime.cash_rate"]["when"],
            {"company.overtime.enabled": True, "company.overtime.cash_enabled": True},
        )
        self.assertEqual(
            by_path["company.overtime.comp_time_ratio"]["when"],
            {"company.overtime.enabled": True, "company.overtime.comp_time_enabled": True},
        )
        self.assertNotIn("commercial_insurance", by_path)
        self.assertRegex(source, r"return \{required, completed, percent\}")

    def test_rule_editor_executes_and_applies_compound_conditions(self):
        if NODE is None:
            self.skipTest("Node.js is required for JavaScript behavior tests")
        program = r"""
const assert = require('node:assert/strict');
const editor = require('./static/rule-editor.js');
const base = {
  company: {overtime: {enabled: true, cash_enabled: false, comp_time_enabled: false}},
};
const disabled = editor.requiredState(base, []);
base.company.overtime.cash_enabled = true;
const enabled = editor.requiredState(base, []);
assert.equal(enabled.required - disabled.required, 5);
assert.equal(editor.requiredConditionMatches(
  'company.overtime.enabled:true;company.overtime.cash_enabled:true', base
), true);
base.company.overtime.enabled = false;
assert.equal(editor.requiredConditionMatches(
  'company.overtime.enabled:true;company.overtime.cash_enabled:true', base
), false);
"""
        subprocess.run(
            [NODE, "-e", program], cwd=Path.cwd(), check=True, capture_output=True, text=True
        )

    def test_rule_editor_parses_boolean_and_json_field_values(self):
        if NODE is None:
            self.skipTest("Node.js is required for JavaScript behavior tests")
        program = r"""
const assert = require('node:assert/strict');
const editor = require('./static/rule-editor.js');
assert.equal(editor.fieldValue({dataset: {boolean: ''}, value: ''}), null);
assert.equal(editor.fieldValue({dataset: {boolean: ''}, value: 'false'}), false);
assert.deepEqual(editor.fieldValue({dataset: {jsonList: ''}, value: '[{"rate":0.03}]'}), [{rate: 0.03}]);
assert.throws(() => editor.fieldValue({dataset: {jsonList: ''}, value: '{bad'}));
assert.equal(
  editor.fieldDisplayValue({dataset: {jsonList: ''}}, [{rate: 0.03}]),
  '[\n  {\n    "rate": 0.03\n  }\n]'
);
"""
        subprocess.run(
            [NODE, "-e", program], cwd=Path.cwd(), check=True, capture_output=True, text=True
        )

    def test_completion_rejects_empty_required_lists_and_ignores_unknown_paths(self):
        if NODE is None:
            self.skipTest("Node.js is required for JavaScript behavior tests")
        program = r"""
const assert = require('node:assert/strict');
const editor = require('./static/rule-editor.js');
const snapshot = {statutory: {tax: {enabled: true, brackets: []}}};
const empty = editor.requiredState(snapshot, []);
snapshot.statutory.tax.brackets = [{upper: null, rate: 0.03, quick_deduction: 0}];
const populated = editor.requiredState(snapshot, []);
assert.equal(populated.completed - empty.completed, 1);
const unknown = editor.requiredState(snapshot, [{code:'required', field:'commercial_insurance[0].rate'}]);
assert.equal(unknown.required, populated.required);
assert.equal(unknown.completed, populated.completed);
"""
        subprocess.run(
            [NODE, "-e", program], cwd=Path.cwd(), check=True, capture_output=True, text=True
        )

    def test_save_validation_and_publish_stop_after_failed_previous_step(self):
        script = Path("static/workspace.js").read_text(encoding="utf-8")
        self.assertIn("if(!saved)return false", script)
        self.assertIn("if(!valid||!state.current", script)
        self.assertGreaterEqual(script.count("return false"), 4)

    def test_rule_changes_clear_stale_errors_and_errors_are_accessible(self):
        script = Path("static/workspace.js").read_text(encoding="utf-8")
        self.assertIn("clearValidationErrors", script)
        self.assertIn("aria-invalid", script)
        self.assertIn("aria-describedby", script)

    def test_visible_boolean_decisions_are_three_state_and_keep_boolean_snapshots(self):
        html = self.client.get("/").get_data(as_text=True)
        for path in (
            "company.worktime.lunch.enabled",
            "company.overtime.enabled",
            "company.overtime.cash_enabled",
            "company.income_items.allowance.taxable",
            "statutory.tax.enabled",
        ):
            self.assertRegex(
                html,
                rf'<select data-field="{re.escape(path)}" data-boolean>.*?value="true".*?value="false"',
            )
        script = Path("static/workspace.js").read_text(encoding="utf-8")
        self.assertIn("RuleEditor.fieldValue", script)
        self.assertIn("RuleEditor.fieldDisplayValue", script)

    def test_dialog_business_decisions_are_three_state(self):
        html = self.client.get("/").get_data(as_text=True)
        for name in (
            "counts_as_attendance",
            "counts_as_absence",
            "affects_perfect_attendance",
            "skip_punch_requirement",
            "proof_required",
            "cross_day_allowed",
            "enabled",
        ):
            self.assertRegex(
                html,
                rf'<select name="{name}" data-boolean required>.*?value="true".*?value="false"',
            )

    def test_conditional_fields_and_list_errors_are_reachable(self):
        html = self.client.get("/").get_data(as_text=True)
        for path in (
            "company.overtime.cash_formula",
            "company.overtime.cash_rate",
            "company.overtime.day_rates.workday",
            "company.overtime.comp_time_ratio",
            "statutory.tax.negative_tax_mode",
            "statutory.tax.brackets",
        ):
            self.assertIn(f'data-field="{path}"', html)
            self.assertIn(f'data-error-for="{path}"', html)
        self.assertIn('data-list-path="company.leaves"', html)
        self.assertIn('data-error-for="company.leaves"', html)
        self.assertIn('data-list-path="commercial_insurance"', html)
        self.assertIn('data-error-for="commercial_insurance"', html)

    def test_failed_requests_do_not_refill_or_clear_the_editor(self):
        script = Path("static/workspace.js").read_text(encoding="utf-8")
        self.assertIn("catch(error)", script)
        self.assertNotRegex(script, r"catch\(error\)\{[^\n]*fillSnapshot")

    def test_dialog_cancel_controls_do_not_submit_required_fields(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('data-close-dialog="leave-dialog"', html)
        self.assertIn('data-close-dialog="insurance-dialog"', html)
        self.assertGreaterEqual(html.count('type="button" data-close-dialog='), 4)

    def test_statutory_dialog_exposes_contribution_timing_fields(self):
        html = self.client.get("/").get_data(as_text=True)
        for name in (
            "hire_month_rule", "hire_cutoff_day",
            "termination_month_rule", "termination_cutoff_day",
        ):
            self.assertIn(f'name="{name}"', html)
        self.assertRegex(
            html,
            r'<select name="hire_month_rule" required>.*?value="always".*?value="never".*?value="cutoff_day"',
        )
        self.assertRegex(
            html,
            r'<select name="termination_month_rule" required>.*?value="always".*?value="never".*?value="cutoff_day"',
        )
        self.assertIn('data-timing-cutoff="hire"', html)
        self.assertIn('data-timing-cutoff="termination"', html)

    def test_statutory_timing_helpers_require_and_normalize_cutoffs(self):
        if NODE is None:
            self.skipTest("Node.js is required for JavaScript behavior tests")
        program = r"""
const assert = require('node:assert/strict');
const editor = require('./static/rule-editor.js');
assert.deepEqual(editor.statutoryTimingState('cutoff_day'), {show: true, required: true});
assert.deepEqual(editor.statutoryTimingState('always'), {show: false, required: false});
assert.deepEqual(editor.normalizeStatutoryTiming({
  hire_month_rule: 'always', hire_cutoff_day: '15',
  termination_month_rule: 'cutoff_day', termination_cutoff_day: '16',
}), {
  hire_month_rule: 'always', hire_cutoff_day: null,
  termination_month_rule: 'cutoff_day', termination_cutoff_day: 16,
});
assert.equal(editor.normalizeStatutoryTiming({
  hire_month_rule: '', hire_cutoff_day: '',
  termination_month_rule: '', termination_cutoff_day: '',
}).hire_month_rule, '');
"""
        subprocess.run(
            [NODE, "-e", program], cwd=Path.cwd(), check=True,
            capture_output=True, text=True,
        )

    def test_statutory_dialog_uses_hr_timing_values_without_defaults(self):
        script = Path("static/workspace.js").read_text(encoding="utf-8")
        styles = Path("static/workspace.css").read_text(encoding="utf-8")
        self.assertIn("statutoryTimingFields", script)
        self.assertIn("normalizeStatutoryTiming", script)
        self.assertNotIn("item.hire_month_rule='always'", script)
        self.assertNotIn("item.termination_month_rule='always'", script)
        self.assertIn("hire_month_rule", script)
        self.assertIn("termination_month_rule", script)
        self.assertIn("[data-timing-cutoff][hidden]{display:none}", styles)

    def test_structured_employment_type_editor(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="employment-type-table"', html)
        self.assertIn('id="add-employment-type"', html)
        self.assertIn('id="employment-type-dialog"', html)
        self.assertIn('data-close-dialog="employment-type-dialog"', html)
        self.assertNotIn('id="employment-types"', html)
        for name in ("code", "name", "payroll_scheme"):
            self.assertRegex(html, rf'<(?:input|select) name="{name}"[^>]*required')
        for name in (
            "social_insurance_applicable",
            "housing_fund_applicable",
            "tax_applicable",
            "enabled",
        ):
            self.assertRegex(
                html,
                rf'<select name="{name}" data-boolean required>.*?value="true".*?value="false"',
            )
        self.assertGreaterEqual(
            html.count('type="button" data-close-dialog="employment-type-dialog"'),
            2,
        )

    def test_employment_type_draft_validation_rejects_format_and_duplicates(self):
        if NODE is None:
            self.skipTest("Node.js is required for JavaScript behavior tests")
        program = r"""
const assert = require('node:assert/strict');
const editor = require('./static/rule-editor.js');
const existing = [
  {code: 'full_time', name: '全职'},
  {code: 'intern', name: '实习生'},
];
assert.deepEqual(
  editor.validateEmploymentTypeDraft({code: 'Full-Time', name: '外包'}, existing, null),
  {code: '代码只能使用小写字母、数字和下划线，且必须以小写字母开头'}
);
assert.deepEqual(
  editor.validateEmploymentTypeDraft({code: ' full_time ', name: '外包'}, existing, null),
  {code: '用工类型代码已存在'}
);
assert.deepEqual(
  editor.validateEmploymentTypeDraft({code: 'outsourced', name: ' 实习生 '}, existing, null),
  {name: '用工类型名称已存在'}
);
assert.deepEqual(
  editor.validateEmploymentTypeDraft({code: 'full_time', name: '全职'}, existing, 0),
  {}
);
assert.deepEqual(
  editor.validateEmploymentTypeDraft({code: 'outsourced', name: '   '}, existing, null),
  {name: '请填写用工类型名称'}
);
"""
        subprocess.run(
            [NODE, "-e", program], cwd=Path.cwd(), check=True, capture_output=True, text=True
        )

    def test_employment_type_codes_lock_only_after_save_or_reference(self):
        script = Path("static/workspace.js").read_text(encoding="utf-8")
        self.assertIn("persistedEmploymentTypeCodes", script)
        self.assertIn("employmentTypeReferenced", script)
        self.assertIn("employmentTypeCodeLocked", script)
        self.assertIn("state.commercialInsurance.some", script)
        self.assertIn("state.current?.status==='published'", script)
        self.assertRegex(script, r"add-employment-type'\)\.disabled=locked")

    def test_legacy_employment_type_ui_fallback_does_not_invent_business_values(self):
        script = Path("static/workspace.js").read_text(encoding="utf-8")
        self.assertIn("code:item,name:'',payroll_scheme:''", script)
        self.assertNotIn("code:item,name:item", script)

    def test_commercial_insurance_editor(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="commercial-insurance-table"', html)
        self.assertIn('id="commercial-insurance-dialog"', html)
        self.assertIn('id="add-commercial"', html)
        for name in (
            "code", "name", "region", "effective_from", "calculation",
            "employee_share", "employer_share", "deduction_mode",
            "employment_types",
        ):
            self.assertRegex(html, rf'<(?:input|select) name="{name}"[^>]*required')
        for name in ("taxable", "included_in_gross", "enabled"):
            self.assertRegex(
                html,
                rf'<select name="{name}" data-boolean required>.*?value="true".*?value="false"',
            )
        self.assertGreaterEqual(
            html.count('type="button" data-close-dialog="commercial-insurance-dialog"'),
            2,
        )
        script = Path("static/workspace.js").read_text(encoding="utf-8")
        self.assertIn("renderCommercialInsurance", script)
        self.assertIn("editCommercialInsurance", script)
        self.assertIn("commercialCalculationState", script)
        self.assertIn("commercialEnabledState", script)
        self.assertRegex(script, r"add-commercial'\)\.disabled=locked")
        self.assertIn("setPath(result,'commercial_insurance',state.commercialInsurance)", script)

    def test_employee_exception_editor(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="employee-exception-table"', html)
        self.assertIn('id="add-employee-exception"', html)
        self.assertIn('id="employee-exception-dialog"', html)
        for name in (
            "employee_id", "override_type", "target_code", "effective_from",
            "reason", "enabled",
        ):
            self.assertRegex(html, rf'<(?:input|select) name="{name}"[^>]*required')
        self.assertGreaterEqual(
            html.count('type="button" data-close-dialog="employee-exception-dialog"'), 2
        )
        script = Path("static/workspace.js").read_text(encoding="utf-8")
        for symbol in ("renderEmployeeExceptions", "editEmployeeException", "exceptionFieldState"):
            self.assertIn(symbol, script)
        for empty_hint in (
            "请先选择覆盖类型",
            "请先在法定政策中新增五险规则",
            "请先在法定政策中新增公积金规则",
            "请先新增商业保险",
            "请选择覆盖项目",
        ):
            self.assertIn(empty_hint, script)
        self.assertIn("target.disabled=!targets.length", script)
        self.assertIn("setPath(result,'employee_exceptions',state.employeeExceptions)", script)
        self.assertIn("state.employeeExceptions.some", script)
        self.assertIn("setCustomValidity('')", script)
        css = Path("static/workspace.css").read_text(encoding="utf-8")
        self.assertIn("[data-commercial-mode][hidden]{display:none}", css)

    def test_static_assets_are_local_and_accessible(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('/static/workspace.css', html)
        self.assertIn('/static/workspace.js', html)
        self.assertNotIn("cdn.", html)
        self.assertIn('aria-label="主导航"', html)


if __name__ == "__main__":
    unittest.main()
