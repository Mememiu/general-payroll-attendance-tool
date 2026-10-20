# 真实数据验收

验收脚本调用与桌面 App 相同的 `/tasks` 计算接口。输入文件和结果保留在本机数据目录；提交到仓库的代码不会包含真实文件。报告仅记录文件哈希、员工工号集合哈希、人数、待复核数和 sheet 名称。

```bash
python scripts/acceptance_real_data.py --attendance attendance.xlsx --payroll employees.xlsx --policy-version VERSION_ID --month 2026-08 --start 2026-08-01 --end 2026-08-31 --output instance/acceptance/2026-08.json
```

验收前必须在 App 内完成并发布 HR 规则。不得把真实 XLSX 或 `instance/acceptance/` 报告提交到 Git。
