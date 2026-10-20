# Statutory Contribution Timing UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let HR configure hire-month and termination-month contribution rules independently for every social-insurance and housing-fund rule.

**Architecture:** Extend the existing shared statutory-rule dialog instead of creating a second policy model. Keep conditional form behavior in focused exported helpers in `static/rule-editor.js`, leave the server-side validation and calculation engine unchanged, and remove the two frontend assignments that currently force `always`.

**Tech Stack:** Flask, vanilla HTML/CSS/JavaScript, Node.js behavior tests through `unittest`, existing policy validation/serialization and statutory calculation modules.

---

## File Structure

- `templates/workspace.html`: Add the four timing controls, required markers and conditional error targets to the shared statutory-rule dialog.
- `static/rule-editor.js`: Normalize timing fields and calculate conditional input state without inventing values.
- `static/workspace.js`: Fill timing controls, update conditional visibility, and save normalized values.
- `static/workspace.css`: Add a compact statutory timing fieldset layout only if the existing grid is insufficient.
- `static/workspace-responsive.css`: Keep timing groups usable at `390x844` only if shared responsive rules do not already cover them.
- `tests/test_workspace_ui.py`: Assert HTML contracts and execute the JavaScript timing helpers in Node.
- `docs/USER_GUIDE.md`: Replace the current limitation with the implemented behavior and exact cutoff semantics.
- `docs/hr-workbook.md`: Remove the manual-review warning for this completed configuration path.

### Task 1: Timing Field Contracts and Pure State Helpers

**Files:**
- Modify: `templates/workspace.html`
- Modify: `static/rule-editor.js`
- Modify: `tests/test_workspace_ui.py`

- [ ] **Step 1: Write failing HTML contract tests**

Add this test to `WorkspaceUiTests`:

```python
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
```

- [ ] **Step 2: Run the HTML contract test and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_workspace_ui.WorkspaceUiTests.test_statutory_dialog_exposes_contribution_timing_fields -v
```

Expected: FAIL because the four controls are absent.

- [ ] **Step 3: Add the timing controls to the shared dialog**

Inside `#insurance-form`, add two fieldsets after the employment-type field:

```html
<fieldset class="timing-group">
  <legend>入职当月缴纳</legend>
  <label>缴纳规则 <span class="required-mark" aria-hidden="true">*</span>
    <select name="hire_month_rule" required>
      <option value="">请选择</option>
      <option value="always">当月缴纳</option>
      <option value="never">当月不缴纳</option>
      <option value="cutoff_day">按截止日判断</option>
    </select>
  </label>
  <label data-timing-cutoff="hire" hidden>入职截止日 <span class="required-mark" aria-hidden="true">*</span>
    <input name="hire_cutoff_day" type="number" min="1" max="31" step="1">
  </label>
</fieldset>
<fieldset class="timing-group">
  <legend>离职当月缴纳</legend>
  <label>缴纳规则 <span class="required-mark" aria-hidden="true">*</span>
    <select name="termination_month_rule" required>
      <option value="">请选择</option>
      <option value="always">当月缴纳</option>
      <option value="never">当月不缴纳</option>
      <option value="cutoff_day">按截止日判断</option>
    </select>
  </label>
  <label data-timing-cutoff="termination" hidden>离职截止日 <span class="required-mark" aria-hidden="true">*</span>
    <input name="termination_cutoff_day" type="number" min="1" max="31" step="1">
  </label>
</fieldset>
```

Do not put a selected option in either rule field.

- [ ] **Step 4: Write failing JavaScript behavior tests**

Add a Node-backed test:

```python
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
```

- [ ] **Step 5: Run the JavaScript behavior test and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_workspace_ui.WorkspaceUiTests.test_statutory_timing_helpers_require_and_normalize_cutoffs -v
```

Expected: FAIL because the helpers are not exported.

- [ ] **Step 6: Implement pure timing helpers**

Add to the exported API in `static/rule-editor.js`:

```javascript
function statutoryTimingState(mode) {
  const active = mode === 'cutoff_day';
  return {show: active, required: active};
}

function normalizeStatutoryTiming(item) {
  const normalized = {...item};
  for (const prefix of ['hire', 'termination']) {
    const rule = normalized[`${prefix}_month_rule`] || '';
    const cutoffKey = `${prefix}_cutoff_day`;
    normalized[cutoffKey] = rule === 'cutoff_day' && normalized[cutoffKey] !== ''
      && normalized[cutoffKey] != null
      ? Number(normalized[cutoffKey])
      : null;
  }
  return normalized;
}
```

Export both functions for browser and CommonJS use following the file's existing export pattern.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_workspace_ui -v
```

Expected: all workspace UI tests pass.

- [ ] **Step 8: Commit Task 1**

```bash
git add templates/workspace.html static/rule-editor.js tests/test_workspace_ui.py
git commit -m "Add statutory timing field contracts"
```

### Task 2: Dialog State, Save and Edit Round Trip

**Files:**
- Modify: `static/workspace.js`
- Modify: `tests/test_workspace_ui.py`

- [ ] **Step 1: Write failing orchestration contract tests**

Add:

```python
def test_statutory_dialog_uses_hr_timing_values_without_defaults(self):
    script = Path("static/workspace.js").read_text(encoding="utf-8")
    self.assertIn("statutoryTimingFields", script)
    self.assertIn("normalizeStatutoryTiming", script)
    self.assertNotIn("item.hire_month_rule='always'", script)
    self.assertNotIn("item.termination_month_rule='always'", script)
    self.assertIn("hire_month_rule", script)
    self.assertIn("termination_month_rule", script)
```

- [ ] **Step 2: Run the orchestration test and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_workspace_ui.WorkspaceUiTests.test_statutory_dialog_uses_hr_timing_values_without_defaults -v
```

Expected: FAIL because `workspace.js` still writes `always`.

- [ ] **Step 3: Add conditional dialog state**

Implement:

```javascript
function statutoryTimingFields() {
  const form = $('#insurance-form');
  for (const prefix of ['hire', 'termination']) {
    const rule = form.elements[`${prefix}_month_rule`];
    const cutoff = form.elements[`${prefix}_cutoff_day`];
    const label = $(`[data-timing-cutoff="${prefix}"]`, form);
    const state = window.RuleEditor.statutoryTimingState(rule.value);
    label.hidden = !state.show;
    cutoff.disabled = !state.show;
    cutoff.required = state.required;
  }
}
```

Call it after `editInsurance()` fills an existing item and on both timing select `change` events. An old draft with missing fields must show `请选择`; do not assign a value in `editInsurance()`.

- [ ] **Step 4: Normalize saved values**

Replace the hard-coded assignments in `#save-insurance` with:

```javascript
let item = formObject(form);
item = window.RuleEditor.normalizeStatutoryTiming(item);
item.employment_types = item.employment_types
  .split(',').map(value => value.trim()).filter(Boolean);
```

Run `statutoryTimingFields()` before `reportValidity()` so hidden inputs have the correct disabled/required state. Preserve all unrelated form behavior.

- [ ] **Step 5: Run UI, validation, serialization and calculation tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  tests.test_workspace_ui \
  tests.test_policy_validation \
  tests.test_policy_serialization \
  tests.test_social_insurance_policy -v
```

Expected: all tests pass, including existing cutoff and same-month hire/termination cases.

- [ ] **Step 6: Commit Task 2**

```bash
git add static/workspace.js tests/test_workspace_ui.py
git commit -m "Persist configured statutory timing rules"
```

### Task 3: Documentation, Browser Acceptance and Full Verification

**Files:**
- Modify: `docs/USER_GUIDE.md`
- Modify: `docs/hr-workbook.md`
- Modify only if required by visual evidence: `static/workspace.css`
- Modify only if required by visual evidence: `static/workspace-responsive.css`

- [ ] **Step 1: Update the HR-facing behavior description**

In `docs/USER_GUIDE.md`, replace the warning that the interface saves `always` with:

```markdown
- 每条五险和公积金规则分别配置入职月、离职月缴纳方式。选择“按截止日判断”后必须填写 1 至 31 的截止日；系统不预设 15 日。
- 入职日期不晚于截止日时缴纳当月；离职日期不晚于截止日时当月不缴。同月入职并离职时，两项规则必须同时允许缴纳。
```

Update `docs/hr-workbook.md` to remove the manual-review limitation and direct HR to the App rule fields.

- [ ] **Step 2: Run desktop browser acceptance**

At `1440x900`, verify:

- Five-insurance and housing-fund dialogs both contain independent hire/termination rules.
- `cutoff_day` shows and requires the corresponding cutoff.
- Switching to `always` or `never` hides and disables the cutoff.
- Edit round trip preserves the rule and cutoff.
- Cancel and close do not validate or save.
- No overlapping controls, horizontal page overflow or console errors.

- [ ] **Step 3: Run mobile browser acceptance**

At `390x844`, repeat add/edit/cancel for both statutory groups. Confirm the dialog remains scrollable, labels fit, and page-level `scrollWidth <= innerWidth`.

- [ ] **Step 4: Run the complete automated suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest discover -s tests -q
```

Expected: all tests pass. If sandboxing blocks `test_desktop_server_binds_only_loopback`, require every other test to pass in the restricted run and rerun that one test with local-port permission.

- [ ] **Step 5: Verify no frontend fallback remains**

Run:

```bash
rg -n "hire_month_rule='always'|termination_month_rule='always'|hire_cutoff_day.?=.?15|termination_cutoff_day.?=.?15" templates static payroll_tool
```

Expected: no frontend hard-coded timing rule or cutoff. Legacy dataclass defaults may remain only for old direct-API compatibility and must not be used by the published-policy path.

- [ ] **Step 6: Commit Task 3**

```bash
git add docs/USER_GUIDE.md docs/hr-workbook.md
git add static/workspace.css static/workspace-responsive.css  # only when actually changed
git commit -m "Document statutory contribution timing rules"
```

## Final Gate

- [ ] Confirm the four UI fields persist in policy snapshots and calculation uses them unchanged.
- [ ] Confirm old drafts receive no invented value and published versions remain immutable.
- [ ] Confirm `git status --short` contains only the user's pre-existing unrelated files.
- [ ] Do not push GitHub until the user explicitly requests the final push.
