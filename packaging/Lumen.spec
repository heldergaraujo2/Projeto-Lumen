from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("app")
app = Analysis(["Lumen.pyw"], pathex=["."], binaries=[], datas=[("app", "app"), (".env.example", ".")], hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(app.pure)
exe = EXE(pyz, app.scripts, app.binaries, app.datas, [], name="Lumen", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
