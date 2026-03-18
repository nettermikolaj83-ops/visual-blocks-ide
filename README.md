# Visual Blocks IDE

Visual Blocks IDE is a desktop drag-and-drop block editor (built with Python + PySide6 + NodeGraphQt) that generates and runs live C# code for .NET WPF apps.

## What It Does

- Drag blocks from the palette and connect them visually.
- Live-generate C# code from the graph.
- Run generated code with one click (`Run`).
- Supports control, variables, math, logic, UI, terminal, and utility blocks.
- Save/load block layouts (JSON).

## .NET 10 SDK Handling

- The app checks for `.NET 10 SDK` on startup and before `Run`.
- If SDK is missing, it opens an installer dialog and runs:
  - `winget install --id Microsoft.DotNet.SDK.10 --exact --accept-package-agreements --accept-source-agreements`
- During install, the main editor window is hidden.
- After successful install, restart is required.
  - If user chooses **Later**, the editor does not start.
  - On next launch, restart prompt appears again until system restart happens.

## Run From Python

```powershell
python .\main.py
```

## Build EXE

```powershell
pyinstaller --onefile --noconsole --name visual_blocks_ide --icon app_icon.ico --exclude-module PyQt6 --exclude-module PyQt6.sip --hidden-import PySide6.QtSvg --hidden-import PySide6.QtSvgWidgets main.py
```

Output:

- `dist\visual_blocks_ide.exe`

## Main Files

- `main.py` - main application, block graph UI, C# generation, run/build flow.
- `app_icon.ico` - app/exe icon (diagonal line logo).
- `_run\` - temporary generated C# project used by `Run`.
