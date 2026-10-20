# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "desktop.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "templates"), "templates"),
        (str(root / "static"), "static"),
    ],
    hiddenimports=["webview", "webview.platforms.cocoa", "webview.platforms.edgechromium"],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GeneralPayrollTool",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="GeneralPayrollTool")
app = BUNDLE(
    coll,
    name="通用薪酬绩效工具.app",
    bundle_identifier="org.opensource.generalpayrolltool",
)
