# Research: M32 MCP Bridge MVP

**Date**: 2026-07-19  
**Scope**: Technical planning research only. No code copied, no repositories added as dependencies, no submodules created.

## Method

Sources were inspected through public read-only web access and temporary clones outside the project directory. Community repositories are not adopted as runtime dependencies. Protocol knowledge is separated from copyrighted implementation. Hardware compatibility claims remain unverified unless a source reports real hardware testing; emulator results do not satisfy Hardware Acceptance.

## Official and Protocol Sources

| Source | Findings | Decision |
| --- | --- | --- |
| Midas M32 Live product page, https://www.midasconsoles.com/en/products/0603-AEO | Official product page identifies M32 LIVE as a 40-input, 32 Midas PRO preamp, 25-bus console with 32x32 USB, Ethernet control, and dual AES50. | Adopt as product capability context only; do not infer OSC behavior from marketing specs. |
| Unofficial X32/M32 OSC Protocol PDF, https://x32ram.com/wp-content/uploads/download-files/X32-OSC.pdf | Primary public protocol reference for OSC path/value behavior. It is unofficial and must be validated against emulator and hardware. | Reference protocol knowledge; verify behavior with Fake M32, external emulator, and real M32. |
| Model Context Protocol docs, https://modelcontextprotocol.io/docs and transport spec | MCP uses JSON-RPC; standard transports include stdio and Streamable HTTP. stdio servers communicate over stdin/stdout and must keep stdout valid MCP only. Streamable HTTP requires security controls such as Origin validation and localhost binding when local. | Adopt stdio first; defer Streamable HTTP to optional ChatGPT transport with security gates. |
| MCP Python SDK, https://github.com/modelcontextprotocol/python-sdk | Official Python SDK. Current main documents v2 prerelease; stable production work should use v1.x with an upper bound below v2. | Adopt official MCP Python SDK stable 1.x. Exact pin deferred to dependency lock step. |
| MCP Inspector, https://github.com/modelcontextprotocol/inspector | Official visual testing/debugging tool for MCP servers; supports stdio and HTTP-style transports. | Adopt as developer validation tool, not runtime dependency. |
| ChatGPT MCP documentation, https://developers.openai.com/api/docs/mcp | OpenAI docs describe building remote MCP servers for ChatGPT/API use, connecting from ChatGPT, and risks of write actions. | Reference for optional ChatGPT path only. |
| ChatGPT Developer Mode, https://developers.openai.com/api/docs/guides/developer-mode | Developer Mode provides full MCP client support for read/write tools and is intended for developers who understand the risks. | Optional later path; write tools still require bridge policy and human confirmation. |
| Secure MCP Tunnel, https://developers.openai.com/api/docs/guides/secure-mcp-tunnels | Official OpenAI guide for connecting a local/private MCP server to ChatGPT without broad public exposure. | Only approved optional connectivity exception for ChatGPT. |

## Mandatory Community Repository Review

### modelcontextprotocol/python-sdk

- Repository URL: https://github.com/modelcontextprotocol/python-sdk
- Purpose: Official Python SDK for MCP clients and servers.
- Language/technology: Python.
- Last commit inspected: `3a6f2996cdd8358957479791e8b26198c07d6a75`, 2026-07-16, `docs: load media examples from disk instead of inline base64 (#3108)`.
- License: MIT, root LICENSE present.
- Maturity/tests: Active official SDK with tests and packaging metadata.
- Supported systems: Cross-platform Python.
- X32/M32 evidence: Not console-specific.
- Useful parts: MCP server primitives, stdio transport, schema/tool exposure.
- Parts not to use: v2 prerelease APIs for MVP stability.
- Risks/limits: Exact stable 1.x pin must be selected during dependency lock work.
- Decision: Adopt.

### modelcontextprotocol/inspector

- Repository URL: https://github.com/modelcontextprotocol/inspector
- Purpose: Developer inspection and debugging tool for MCP servers.
- Language/technology: TypeScript, Node, web UI for development inspection.
- Last commit inspected: `ac3c1a122a5e072a200c99869fc0cd8bfa660ece`, 2026-07-17, `Bump to version 1.0.0 (#1720)`.
- License: Mixed transition in repository license text; MIT/Apache-2.0 with docs under CC-BY-4.0 as documented by the project.
- Maturity/tests: Active project with client and CLI tests.
- Supported systems: Developer workstation with Node runtime.
- X32/M32 evidence: Not console-specific.
- Useful parts: MCP tool discovery, schema inspection, smoke validation.
- Parts not to use: Not a production runtime component.
- Risks/limits: Inspector proxy must remain local and not exposed.
- Decision: Adopt as developer tool only.

### elisha-rudenkov/x32-mcp-server

- Repository URL: https://github.com/elisha-rudenkov/x32-mcp-server
- Purpose: MCP server for Behringer X32/Midas M32 control and schema reference.
- Language/technology: TypeScript/Node.
- Last commit inspected: `ec469e16ac06cd1992b913c6bcf3071c55726b64`, 2026-05-26, `feat: runtime mixer discovery + reconnect`.
- License: package metadata says MIT; no root LICENSE file found in the inspected clone.
- Maturity/tests: Build/start/test scripts present; active schema/tool surface.
- Supported systems: Node-supported systems.
- X32/M32 evidence: README reports X32 full-size firmware 4.13 hardware testing and states M32 family should work due similar OSC surface; README alone is not M32 hardware proof.
- Useful parts: Tool coverage, naming, runtime discovery patterns, schema ideas.
- Parts not to use: Raw/custom OSC command surfaces, runtime dependency, copied implementation.
- Risks/limits: M32 compatibility unverified by hardware evidence; missing root license file increases reuse caution.
- Decision: Reference only.

### pmaillot/X32-Behringer

- Repository URL: https://github.com/pmaillot/X32-Behringer
- Purpose: X32 OSC tools and emulator.
- Language/technology: C and related build assets.
- Last commit inspected: `5194fdaf26f141649b80d5bc477772c5f20fd97e`, 2024-02-15, `Merge pull request #38 from schattenmann80/fix-high-cpu-usage`.
- License: README/copyright text states GPLv3-or-later; no root LICENSE file found in the inspected clone.
- Maturity/tests: Mature community protocol toolset; no conventional automated test suite found.
- Supported systems: Desktop platforms depending on build/runtime artifacts; Windows emulator references exist through community packaging.
- X32/M32 evidence: X32-focused emulator and tools; M32 behavior must be treated as unverified.
- Useful parts: External emulator for integration checks, OSC behavior reference, `/xremote`, meters, node exploration.
- Parts not to use: Do not redistribute emulator binary until license/rights are confirmed; do not copy code into MVP.
- Risks/limits: Emulator does not produce audio and does not fully represent hardware.
- Decision: Reference only; external emulator gate.

### JoueBien/X32-OSC-Workbench

- Repository URL: https://github.com/JoueBien/X32-OSC-Workbench
- Purpose: OSC workbench and Windows-friendly emulator/reference environment.
- Language/technology: JavaScript/Electron/Node.
- Last commit inspected: `9f7a0459a1a37e411aa06bd99536783014b37709`, 2022-10-12, `Create LICENSE`.
- License: Root LICENSE is Apache-2.0; package metadata says ISC, so licensing should be treated as conflicting until resolved.
- Maturity/tests: Test script is placeholder; development utility maturity.
- Supported systems: Electron-supported desktops; Windows reference value.
- X32/M32 evidence: X32/M32 OSC sandbox claims; no independent M32 hardware proof found.
- Useful parts: OSC buffer/value handling reference and Windows emulator workflow ideas.
- Parts not to use: Do not depend on or redistribute emulator assets.
- Risks/limits: License metadata conflict and limited test evidence.
- Decision: Reference only.

### CristianMoresi/M32LiveConsoleTool

- Repository URL: https://github.com/CristianMoresi/M32LiveConsoleTool
- Purpose: M32/X32 automation, meters, simulator, manual override, and control-loop reference.
- Language/technology: C#/.NET.
- Last commit inspected: `804299018b09a32d3ecaed40e0d2c2a9012f9463`, 2026-06-11, `v1.1.0: harden the live control loop and polish the operator UX`.
- License: MIT, root LICENSE present.
- Maturity/tests: xUnit tests found for OSC encoding/decoding, malformed blobs, fader math, simulator and control loop behavior.
- Supported systems: README/build assets indicate Windows, macOS, and Linux release targets.
- X32/M32 evidence: Project is explicitly M32/X32-oriented; any unverified hardware claims remain subject to our Hardware Acceptance.
- Useful parts: Manual override precedence, simulator ideas, control-loop hardening, malformed packet tests.
- Parts not to use: No runtime dependency and no code copy.
- Risks/limits: Different stack and UX assumptions.
- Decision: Adapt with attribution for ideas only.

### infrafast/LiveStageAssistant

- Repository URL: https://github.com/infrafast/LiveStageAssistant
- Purpose: Voice assistant, MCP client/server, and assistant-layer reference for live stage workflows.
- Language/technology: Python, assistant/voice/web monitor components.
- Last commit inspected: `f6989390add02ffcc79ee7ac5f733eb0cf34fc26`, 2026-07-06, `tailscale config adjustement : STDIO or HTTP`.
- License: Project metadata indicates MIT.
- Maturity/tests: Tests directory present; broader assistant system scope.
- Supported systems: Python-supported systems.
- X32/M32 evidence: Assistant-layer reference, not direct M32 hardware proof for this MVP.
- Useful parts: Conversation UX and MCP client/server operational lessons.
- Parts not to use: Voice pipeline, web monitor, AI backend, and assistant orchestration are out of MVP scope.
- Risks/limits: Scope expansion risk.
- Decision: Defer to post-MVP.

### infrafast/XMSeries-MCP

- Repository URL: https://github.com/infrafast/XMSeries-MCP
- Purpose: MCP implementation for Behringer/Midas mixers over OSC.
- Language/technology: TypeScript/Node.
- Last commit inspected: `cbc730fd9ceb9b05c54efc4572743cc95dc70299`, 2026-07-02, `enforce fade rules`.
- License: package metadata indicates MIT; no root LICENSE file found in inspected clone.
- Maturity/tests: Active comparative implementation; details require implementation-phase review before reuse.
- Supported systems: Node-supported systems.
- X32/M32 evidence: Reports X32 Producer testing; M32 support remains compatibility inference, not hardware proof.
- Useful parts: Comparative MCP tool design, HTTP/stdio transport lessons, no-raw-tool intent.
- Parts not to use: Runtime dependency, admin UI, HTTP-first assumptions, copied code.
- Risks/limits: M32 hardware unverified; missing root license file.
- Decision: Reference only.

### bitfocus/companion-module-behringer-x32

- Repository URL: https://github.com/bitfocus/companion-module-behringer-x32
- Purpose: Bitfocus Companion module action coverage for X32/M32-style control.
- Language/technology: TypeScript.
- Last commit inspected: `9ec797feb1d577e828d30a2e03ed1315a3abc6c9`, 2026-06-24, `chore: update yarn config`.
- License: MIT, root LICENSE present.
- Maturity/tests: Mature Companion ecosystem module; no conventional tests found in inspected clone.
- Supported systems: Companion-supported systems.
- X32/M32 evidence: X32 module with M32-adjacent usage; not sufficient as M32 hardware verification.
- Useful parts: Action coverage inventory and operational vocabulary.
- Parts not to use: Companion runtime, copied action code, broad write coverage.
- Risks/limits: Companion workflow differs from proposal/approval model.
- Decision: Reference only.

### HealGaren/feedguard

- Repository URL: https://github.com/HealGaren/feedguard
- Purpose: Future USB/ASIO/DSP analyzer concept.
- Language/technology: TypeScript/Node concept with browser UI direction.
- Last commit inspected: `ac0ce6a8cfed2ef716ed64b324f034086aa4fb84`, 2026-03-22, `Update README with finalized architecture and roadmap`.
- License: MIT, root LICENSE present.
- Maturity/tests: Concept/roadmap stage; package test placeholder.
- Supported systems: Desktop/audio stack dependent.
- X32/M32 evidence: Analyzer concept, not console control verification.
- Useful parts: Post-MVP analyzer ideas only.
- Parts not to use: USB/ASIO capture, FFT analyzer, browser UI, DSP automation.
- Risks/limits: Directly expands MVP beyond PLAN.md.
- Decision: Defer to post-MVP.

## Decision Records

### Python 3.12 vs TypeScript

- Decision: Python 3.12.
- Rationale: Mandated by the current plan, aligns with a small local modular monolith, supports official MCP Python SDK stable 1.x, and keeps runtime dependencies minimal.
- Rejected alternative: TypeScript because community MCP examples are useful but would add a Node runtime path and does not improve MVP safety.

### Official MCP Python SDK Stable 1.x

- Decision: Use official MCP Python SDK stable 1.x, with exact pin selected during dependency lock work.
- Rationale: Official project, stable branch available, stdio support, and lower protocol implementation risk.
- Rejected alternative: Current main/v2 prerelease for MVP.

### stdio vs Streamable HTTP

- Decision: stdio first for Claude Desktop; Streamable HTTP later for optional ChatGPT transport.
- Rationale: stdio is the simplest local boundary and avoids exposing local control over HTTP. Streamable HTTP is required for ChatGPT-style remote MCP access and has additional security requirements.
- Rejected alternative: HTTP-first local server because it adds exposure and security work before MVP needs it.

### Project-Owned Fake M32 vs External Emulator

- Decision: Use both for different purposes.
- Rationale: Fake M32 gives deterministic CI coverage and failure injection. External emulator provides independent protocol integration confidence.
- Constraint: Neither provides hardware verification.

### Patrick-Gilles Maillot X32 Emulator

- Decision: Use as an external, optional developer tool and pre-MCP-readiness gate.
- Rationale: It is a widely referenced OSC emulator/toolset.
- Constraint: Do not redistribute binary until license and rights are confirmed.

### x32-mcp-server as Reference

- Decision: Reference only.
- Rationale: Useful MCP schema and tool coverage ideas, but includes custom/raw OSC-like surfaces and lacks M32 hardware proof.
- Constraint: No runtime dependency and no copied code.

### State Cache and `/xremote`

- Decision: Use in-memory state cache with revisions, freshness, and recurring synchronization, including `/xremote` renewal where supported.
- Rationale: Writes need conflict detection and readback; cached state is useful but never authoritative over the console.
- Rejected alternative: Blind write-through without baseline reconciliation.

### OSC Packet, Value, and Blob Handling

- Decision: Implement strict typed OSC encoding/decoding with property and failure-injection tests.
- Rationale: UDP can lose, delay, duplicate, and reorder messages; malformed values must fail closed.
- Constraint: Unsupported or malformed replies disable writes.

### Windows and macOS Support

- Decision: Treat both as required MVP platforms.
- Rationale: Constitution requires cross-platform gates before release.
- Constraint: Avoid OS-specific bridge assumptions and validate startup/packaging/smoke tests on both.

### No WebUI, Database, or Microservices

- Decision: Reject for MVP.
- Rationale: Claude/ChatGPT are the UX, state is in-memory plus JSON/JSONL, and local modular monolith minimizes safety and operational complexity.
- Deferred: Any UI, database, service split, or analyzer belongs to post-MVP only after new approval.

## Risks and Rejected Alternatives

- **Raw OSC tool exposure**: Rejected because it bypasses policy and violates constitution.
- **Always Allow write tools**: Rejected because write actions require explicit human approval and host confirmation.
- **M32-Edit control**: Rejected because console control is direct OSC/UDP only.
- **Internet-exposed OSC**: Rejected because OSC remains local/LAN-only and network bridging/ICS/packet forwarding are disabled.
- **Hardware readiness from emulator**: Rejected; real M32 Hardware Acceptance remains required.
- **Community repo as dependency**: Rejected until license and fit are formally reviewed during implementation.
- **Post-MVP analyzer**: Rejected for MVP; RTA-assisted guidance is limited to console-provided RTA/meter capabilities.

