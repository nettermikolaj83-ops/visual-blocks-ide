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

## Main Files

- `main.py` - main application, block graph UI, C# generation, run/build flow.
