#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
npm ci --prefix "$ROOT/runtime" --no-audit --no-fund
mkdir -p "$ROOT/runtime/node_modules/node/lib"
export PATH="$ROOT/runtime/node_modules/node/bin:$PATH"
npm ci --prefix "$ROOT" --no-audit --no-fund
chmod +x "$ROOT/rea"
"$ROOT/rea" --version
# Does not register a client or install native analysis providers.
