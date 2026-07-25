# Dependency and License Register

This register is part of the MVP dependency governance. Community repositories
from `research.md` are reference material only unless a later task explicitly
adds an approved dependency and license review.

| Component | Use | License Status | Runtime Dependency | Decision |
| --- | --- | --- | --- | --- |
| Python 3.12 | Runtime | PSF License | Yes | Adopt |
| official MCP Python SDK stable 1.x | MCP stdio server support | MIT, per inspected upstream repository | Yes | Pin to `mcp>=1.0,<2`; prevent accidental v2 upgrade |
| jsonschema | Local JSON Schema validation | MIT-style project license, verify during lock review | Yes | Adopt |
| PyYAML | Local YAML config parsing | MIT, verify during lock review | Yes | Adopt |
| pytest | Test runner | MIT, verify during lock review | Test only | Adopt |
| Hypothesis | Property tests | MPL-2.0, verify during lock review | Test only | Adopt |
| Patrick-Gilles Maillot X32 Emulator | External emulator gate | GPLv3-or-later stated in research; no redistribution planned | No | Reference only |
| Community X32/M32 repositories | Research references | Varies; see `research.md` | No | Reference only |

Lock review requirements:

- The MCP Python SDK must remain on stable 1.x with an upper bound below v2.
- Third-party emulator binaries must not be redistributed until license rights
  are confirmed.
- No community repository may be copied into runtime code from this register.
- No embedded secrets or tunnel credentials may be added to dependency metadata.

