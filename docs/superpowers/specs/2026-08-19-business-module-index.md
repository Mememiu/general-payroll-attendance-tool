# 通用薪酬绩效工具业务设计索引

## 实施顺序

1. 产品边界、角色权限、规则包版本和输入质量。
2. 员工主数据、班次工时、假勤外出出差、加班调休。
3. 薪资收入项目、法定缴纳、商业保险、累计个税。
4. 月度算薪、异常复核、报表审计、本地 App 交付。

## 独立设计文档

- 总需求：`2026-08-19-general-payroll-product-requirements.md`
- 产品边界与角色：`2026-08-19-product-boundary-and-roles-design.md`
- HR 规则包与政策：`2026-08-19-hr-configurable-rules-design.md`
- 员工主数据：`2026-08-19-employee-master-and-employment-cycle-design.md`
- 输入与数据质量：`2026-08-19-input-template-and-data-quality-design.md`
- 考勤与工时：`2026-08-19-attendance-and-worktime-design.md`
- 假勤、外出与出差：`2026-08-19-leave-offsite-and-travel-design.md`
- 加班与调休：`2026-08-19-overtime-and-comp-time-design.md`
- 薪资与收入项目：`2026-08-19-payroll-and-income-items-design.md`
- 五险、公积金与商业保险：`2026-08-19-statutory-and-commercial-insurance-design.md`
- 个税：`2026-08-19-cumulative-tax-design.md`
- 月度算薪与异常复核：`2026-08-19-monthly-payroll-and-review-design.md`
- 结果、报表与审计：`2026-08-19-results-reporting-and-audit-design.md`
- 本地 App 与数据安全：`2026-08-19-local-app-and-data-security-design.md`

## 当前实现差距

现有代码具备 Flask 本地服务、XLSX 上传、规则包骨架、考勤解析、基础薪资、五险一金和累计个税骨架。尚未完成的关键项包括：所有 HR 字段真正接入计算、无限新增假期、外出返岗接入每日流水线、商业保险、入离职缴纳截止规则、全勤影响配置、异常复核闭环和跨平台安装包。
