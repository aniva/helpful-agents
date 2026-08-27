---
name: backup-chats-skills
description: >-
  Exports all Antigravity conversations to readable Markdown (.md) and plain text (.txt), creates an indexed summary,
  backs up custom skills, project configurations, and scripts to agents-backup, excluding heavy binary files and downloads.
  Includes step-by-step restoration instructions (RESTORE.md) for setting up a new PC.
  Use when the user requests to back up conversations, skills, projects, or setup restoration instructions.
---

# Backup Chats and Skills

Automated skill to convert, organize, and back up all Antigravity session histories, custom skills, project configurations, and helper scripts into `agents-backup`.

## Workflow

1. Execute the comprehensive backup tool:
   `wsl python3 /home/me/repos/home/agents-backup/scripts/backup_chats_and_skills.py`

2. The tool performs the following actions:
   - **Exports Conversations**: Converts all session histories in `.gemini/antigravity/brain/` into formatted `.md` (Markdown) and `.txt` (Plain text) inside `agents-backup/conversations/`.
   - **Generates Index**: Updates `agents-backup/conversations_index.md` listing all 60+ sessions with dates, prompt summaries, and direct markdown links.
   - **Backs Up Configurations**: Copies `projects.json`, `config.json`, `mcp_config.json`, and all `projects/*.json` files to `agents-backup/projects_config/`.
   - **Backs Up Custom Skills**: Copies all custom skills from `.gemini/antigravity/builtin/skills`, `.gemini/config/plugins`, and `.agents/skills` to `agents-backup/skills/`.
   - **Backs Up Scripts**: Backs up custom scripts and tools (e.g. `fix_wsl_folders.ps1`).
   - **Excludes Heavy Binaries**: Filters out `.mp4`, `.zip`, `.iso`, `.exe`, `.tar.gz`, and heavy download artifacts.
   - **Generates Restoration Guide**: Generates `agents-backup/RESTORE.md` with step-by-step PowerShell/Bash commands to restore everything on a new PC.

## Verification

- Check `agents-backup/conversations_index.md` for a complete list of exported sessions.
- Confirm `agents-backup/RESTORE.md` contains the latest setup and restoration manual.
