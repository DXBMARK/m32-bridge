# MCP Guidance Contract

This contract defines installer-adjacent MCP guidance. It is manual-copy documentation only and does not authorize automatic edits to Claude Desktop or other host configuration.

## Default Snippet Shape

Default MCP guidance must use:

```json
{
  "command": "m32-bridge",
  "args": ["mcp-server"]
}
```

## Required Properties

- Guidance is manual-copy only.
- The default command is `m32-bridge mcp-server`.
- Default snippets do not embed host or port.
- The bridge reads saved user-local configuration by default.
- Host/port environment overrides, if shown, are clearly labeled advanced/manual examples.
- Guidance must not claim it has modified Claude Desktop configuration.

## Forbidden Behavior

MCP guidance and installer flows must not:

- automatically write Claude Desktop configuration;
- expose raw OSC through MCP;
- expose arbitrary OSC paths through MCP;
- expose shell execution through MCP tools;
- expose firmware, shutdown, phantom, sample-rate, clock, or approval-token bypass surfaces;
- open a remote/cloud MCP transport;
- start a ChatGPT tunnel.

## Validation Expectations

Tests should validate that standard snippets:

- contain `m32-bridge`;
- contain `mcp-server`;
- omit configured host and port;
- state manual-copy behavior;
- keep logs/stdout expectations consistent with local stdio MCP behavior.
