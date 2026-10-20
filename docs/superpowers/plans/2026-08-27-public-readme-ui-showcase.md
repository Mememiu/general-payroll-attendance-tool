# Public README UI Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two privacy-safe App screenshots to the public repository README as a clear, full-width UI preview.

**Architecture:** Store optimized PNG screenshots under `docs/images/` and reference them with relative Markdown paths from `README.md`. Keep the screenshots independent of runtime assets so desktop packaging remains unchanged.

**Tech Stack:** Markdown, PNG, macOS `sips`, Git, repository safety checks

---

### Task 1: Prepare UI screenshot assets

**Files:**
- Create: `docs/images/rule-configuration-overview.png`
- Create: `docs/images/company-policy-configuration.png`

- [ ] **Step 1: Inspect source image dimensions and metadata**

Run:

```bash
sips -g pixelWidth -g pixelHeight -g format source-1.png source-2.png
```

Expected: both inputs are PNG screenshots and contain no employee, payroll, attendance, or local path data.

- [ ] **Step 2: Create GitHub-sized PNG assets**

Run:

```bash
mkdir -p docs/images
sips -Z 1800 source-1.png --out docs/images/rule-configuration-overview.png
sips -Z 1800 source-2.png --out docs/images/company-policy-configuration.png
```

Expected: each image has a maximum dimension of 1800 pixels and remains legible.

- [ ] **Step 3: Verify generated images**

Run:

```bash
file docs/images/*.png
sips -g pixelWidth -g pixelHeight docs/images/*.png
```

Expected: both files are valid PNG images with nonzero dimensions.

### Task 2: Add the README interface preview

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the preview section after the project introduction**

Insert:

```markdown
## 界面预览

### 规则配置总览

![规则配置总览](docs/images/rule-configuration-overview.png)

### 公司制度配置

![公司制度配置](docs/images/company-policy-configuration.png)
```

Expected: screenshots appear before detailed documentation links and remain full width in GitHub Markdown.

- [ ] **Step 2: Verify README image references**

Run:

```bash
rg -n '界面预览|docs/images/.*\.png' README.md
test -f docs/images/rule-configuration-overview.png
test -f docs/images/company-policy-configuration.png
```

Expected: one preview heading, two image references, and both referenced files exist.

### Task 3: Audit and publish

**Files:**
- Modify: `README.md`
- Create: `docs/images/rule-configuration-overview.png`
- Create: `docs/images/company-policy-configuration.png`

- [ ] **Step 1: Run repository and privacy checks**

Run:

```bash
python scripts/check_repository_safety.py
git diff --check
rg -n 'S26040112|26040106|shellyzouou@gmail.com|skyris' README.md docs/images || true
```

Expected: repository safety and diff checks pass; privacy scan returns no matches.

- [ ] **Step 2: Review the final README diff and asset sizes**

Run:

```bash
git diff -- README.md
du -h docs/images/*.png
```

Expected: only the approved preview section is added and both images are reasonably sized for GitHub.

- [ ] **Step 3: Commit and push only to the public repository**

Run:

```bash
git add README.md docs/images/rule-configuration-overview.png docs/images/company-policy-configuration.png
git commit -m "Add UI preview to public README"
git push public main
```

Expected: the public repository main branch displays both screenshots; the private `origin` remote is not pushed.
