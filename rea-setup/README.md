# REA installation and verification

Verified on October 24, 2026 in the Arena workspace.

## Outcome

REA **6.7.0** is installed locally and usable through this agent's terminal tools. Node.js **24.22.1** is installed locally; system Node.js was not replaced.

**Not connected as native Arena MCP tools.** Arena exposes no registration mechanism in this conversation, and REA detected no supported coding-agent installation. No unrelated client configuration was created. A standalone MCP client successfully connected for testing and then shut down.

## Setup performed

After user approval:

1. Installed a workspace-local Node 24 runtime.
2. Ran `npx --yes rea-agents@latest setup --help` and `setup --dry-run` with that runtime.
3. The setup plan had no client configuration actions. Ran `npx --yes rea-agents@latest setup --yes --format json`; result was `ready` with zero applied actions. This does not mean Arena is connected.
4. Installed the resolved release, `rea-agents@6.7.0`, locally and pinned it in the package manifest and lockfile.
5. Copied bundled workflow instructions to `/home/user/.agents/skills/reverse-engineer-anything/`. Copying these files does not automatically load them into the Arena agent.
6. Added a launcher that selects the compatible local Node runtime.

No native analysis providers were installed and no GitHub repository was changed.

## Verification

| Check | Result |
|---|---|
| CLI version | Passed: 6.7.0 |
| Compatible runtime | Passed: Node 24.22.1 |
| MCP initialization | Passed: server `rea`, version 6.7.0 |
| MCP tool listing | Passed: 207 tools advertised |
| Static JavaScript smoke test | Passed: analyzed the local fixture and returned application/semantic graph Evidence |
| Native Arena tool registration | Not available through this conversation |
| Broad `doctor` audit | Not fully healthy: optional analysis engines are missing |

Tool discovery does not prove all 207 tools can execute: many require additional providers, applications, browsers, or devices. The smoke test parsed inert fixture text and did not execute the target application.

## Usage in this workspace

```bash
/home/user/rea-setup/rea --version
/home/user/rea-setup/rea analyze-javascript-application /home/user/rea-setup/fixture --format json
/home/user/rea-setup/rea doctor --format json
python /home/user/rea-setup/verify-mcp.py
```

For a future client with manual stdio MCP support, the executable is `/home/user/rea-setup/rea` and the arguments are `["--mcp"]`. This is configuration guidance, not an active registration. These paths refer to this sandbox, not your personal computer.

## Restore after a sandbox reset

Installed dependencies and caches are excluded from saved workspace snapshots. Manifests, lockfiles, scripts, workflow files and verification results persist. Restore dependencies with:

```bash
bash /home/user/rea-setup/restore.sh
python /home/user/rea-setup/verify-mcp.py
```

Restoration requires network access to npm. It does not run client setup or install analysis providers.

## Verification artifacts

- `setup-result.json`: setup outcome and detected client states.
- `doctor-result.json`: full readiness diagnostics.
- `mcp-verification.json`: negotiated MCP server information and complete tool-name list.
- `analysis-result.json`: smoke-test analysis Evidence.
- `verify-mcp.py`: repeatable standalone protocol test.
- `fixture/`: harmless JavaScript sample used for verification.
