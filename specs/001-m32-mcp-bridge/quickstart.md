# Developer Quickstart: M32 MCP Bridge MVP

**Date**: 2026-07-19  
**Audience**: Developers validating the MVP locally. These steps are not production or Live instructions.

This document is a validation outline until implementation creates concrete commands and package entry points. `/speckit.tasks` should turn these steps into executable developer tasks without adding production or Live instructions before Hardware Acceptance.

## 1. Prepare Python and Dependencies

Use Python 3.12. Install the project dependencies once implementation exists, including the official MCP Python SDK stable 1.x. The exact dependency lock is an implementation-phase output and is not defined in this planning document.

Expected result: local development commands can run on Windows and macOS without starting a WebUI or AI backend.

## 2. Run Project Fake M32

Start the project-owned deterministic Fake M32 once implemented. Use it as the default CI and developer validation target.

Expected result: the bridge can connect, identify the fake target, read deterministic state, and report `hardware_verified: false`.

## 3. Run Basic Tests

Run the core test suite once implemented:

- Unit/property tests.
- Policy and risk-class tests.
- Proposal digest and conflict tests.
- OSC value/blob parsing tests.
- Failure injection tests for lost, delayed, duplicate, malformed, and out-of-order packets.
- Disconnect/restart tests.

Expected result: tests pass locally and in CI against Fake M32.

## 4. Run External X32 Emulator

Install and run the Patrick-Gilles Maillot X32 Emulator as an external developer tool only, subject to local licensing review. Do not add emulator binaries to the project and do not redistribute them. This suite is optional for daily development, but it is a required release gate before declaring MCP readiness.

Expected result: the bridge can connect to the emulator, perform read-only validation, create safe proposals, execute allowed emulator writes, and still report `hardware_verified: false`.

## 5. Run MCP Inspector

Use MCP Inspector to verify tool discovery, schemas, structured outputs, and denial behavior.

Expected result:

- No raw OSC or arbitrary path tools are exposed.
- Write-capable tools require proposal and confirmation.
- EMERGENCY tools do not send OSC writes.
- Denied operations return structured error codes.

## 6. Connect Claude Desktop

Configure Claude Desktop to launch the local MCP stdio server once implemented. stdout must contain only valid MCP messages; logs go to stderr.

Expected result: Claude Desktop can call read-only tools and proposal tools through the MCP server.

## 7. Run Read-Only Validation Conversation

In Claude Desktop, validate that the bridge can answer questions about:

- Connection state and source of truth.
- Console identity and hardware verification flag.
- Channel, bus, routing, clock, meters, and RTA state.
- Manual changes such as a gain changing from 10 dB to 6 dB.
- Stale or partial state warnings.

Expected result: Claude identifies the console or emulator as the state source and does not claim emulator output as hardware verification.

## 8. Test Safe Proposal on Emulator

Use Claude Desktop to request a bounded safe change on Fake M32 or the external emulator:

1. Ask for a proposal.
2. Review the proposal summary, risk, affected paths, base revisions, and rollback candidates.
3. Approve through the host confirmation flow.
4. Execute the proposal.
5. Verify readback and audit output.
6. Create a manual conflict and confirm execution is rejected.

Expected result: the full Read -> Proposal -> Human Approval -> Policy Check -> Write -> Readback -> Audit flow is enforced.

## 9. Hardware Acceptance Still Required

Fake M32 and external emulator validation do not authorize production or Live use. Before production or Live operation, run the final real-M32 Hardware Acceptance suite with a physical console, verified network isolation, clock/AES50/expansion-card sync checks, manual conflict tests, readback/rollback tests outside EMERGENCY, and Claude Desktop E2E.

Expected result: only successful real-M32 Hardware Acceptance can set `hardware_verified: true` for the approved hardware profile.
