# DXBMARK Interactive Terminal CLI Style Reference

Source read for this reference: `/Users/sunmarke/Downloads/dxbmark_cli_debug.py`.

This reference captures the first-run wizard style contract for later installer setup work. It is documentation only for T022-T029. The raw interactive UI is not implemented inside `scripts/install.sh` or `scripts/install.ps1`.

## Visual Style

- Use a dark terminal canvas based on `#243947`.
- Use DXBMARK Flame Orange `#F97E1A` for the primary accent, borders, selected rows, and brand emphasis.
- Use a readable ASCII DXBMARK banner style as the first TTY visual signal.
- Keep `/help` and `/contact` as stable slash commands in the interactive wizard vocabulary.
- Use a fixed status bar concept for TTY sessions so status remains visible while prompts update.
- Use green status dots for detected/online/available states.
- Use grey status dots for not detected, unknown, or unavailable states.

## Terminal Behavior

- Enable Windows ANSI support for enhanced TTY rendering when possible.
- Enhanced rendering is TTY-only.
- Non-TTY output must fall back to plain text or structured JSON.
- Do not put the raw interactive TUI engine into `install.sh` or `install.ps1`.
- Install scripts may mention that the later first-run wizard uses DXBMARK style, but the complete wizard belongs to T030-T040 or a later approved task.

## IDE And MCP Client Discovery Note

The later wizard may show a best-effort local client list by OS, including Claude Desktop, Codex, Gemini, Antigravity, ChatGPT Desktop, VS Code, Cursor, or other supported local hosts.

- Detected clients use a green status dot.
- Not detected clients use a grey status dot.
- Discovery must not open applications.
- Discovery must not write Claude, ChatGPT, IDE, or MCP host configuration.
- Discovery must not request elevated permissions.
- Non-TTY and JSON output must return a structured client list.
- Full discovery implementation is deferred to T030-T040 or a later appropriate task.
