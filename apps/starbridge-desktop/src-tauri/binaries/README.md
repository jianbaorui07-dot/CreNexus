# Generated sidecar staging directory

`Build-Sidecar.ps1` stages the target-triple executable and its PyInstaller `_internal` directory here. Generated binaries are ignored by Git.

Expected Windows development layout:

```text
binaries/
├─ starbridge-sidecar-x86_64-pc-windows-msvc.exe
└─ _internal/
```

Do not commit generated executables, DLLs, Python bytecode, or local build paths.
