---
name: fix-wsl-folders
description: >-
  Scans, validates, and fixes malformed WSL folder URIs (such as file:///%5C%5Cwsl.localhost... or file:///Ubuntu/...)
  in Antigravity project and workspace configuration files. Use when adding WSL folders to Antigravity encounters path errors
  or when asked to clean up Antigravity project folder URIs.
---

# Fix WSL Folders Skill

Automated skill for inspecting, validating, and fixing malformed WSL folder URIs in Antigravity project configuration files.

## Workflow

1. Execute the sanitization PowerShell script:
   `powershell -ExecutionPolicy Bypass -File "C:\Users\me\.gemini\antigravity\builtin\skills\fix-wsl-folders\scripts\fix_wsl_folders.ps1"`

2. Verify project JSON files in `C:\Users\me\.gemini\config\projects\*.json` to confirm that all WSL resources use standard `file://wsl.localhost/Ubuntu/...` URIs.
