# 安装说明

## macOS

1. 从 GitHub Releases 下载 `GeneralPayrollTool-darwin.zip` 并解压。
2. 将“通用薪酬绩效工具.app”拖入“应用程序”。
3. 首次打开如果 Gatekeeper 提示无法验证开发者，进入“系统设置 → 隐私与安全性”，在对应拦截提示处选择“仍要打开”；也可以在 Finder 中右键 App，选择“打开”。
4. App 窗口出现后即可配置规则。不要同时启动多个实例。

当前 macOS 包为 Apple Silicon 构建。Intel Mac 需要 GitHub 使用 Intel runner 单独构建，不能把 Apple Silicon 包当作通用包。

## Windows

1. 从 GitHub Releases 下载 `GeneralPayrollTool-windows.zip` 并完整解压。
2. 双击目录内 `GeneralPayrollTool.exe`，不要只把 exe 单独移出目录。
3. SmartScreen 提示时选择“更多信息 → 仍要运行”。公司管控电脑若禁止未签名软件，需要联系本单位 IT 放行。

安装包已包含 Python 和运行依赖。App 只监听 `127.0.0.1`，其他电脑不能通过你的地址访问；上传的考勤和薪酬文件不会发送给开发者。

## 数据位置

- macOS：`~/Library/Application Support/GeneralPayrollTool/`
- Windows：`%LOCALAPPDATA%\GeneralPayrollTool\`

规则、计算记录、上传文件和结果都保存在这里。卸载程序不会自动删除该目录。
