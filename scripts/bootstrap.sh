#!/usr/bin/env bash
# First-clone host runtimes for this checkout. Pins live in mise.toml.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v mise >/dev/null 2>&1; then
  echo "mise not on PATH — installing from https://mise.run"
  curl https://mise.run | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

if ! command -v mise >/dev/null 2>&1; then
  echo "mise still not on PATH. Add ~/.local/bin to PATH and re-run." >&2
  exit 1
fi

cd "${REPO_ROOT}"
mise trust "${REPO_ROOT}/mise.toml"
mise install

echo
echo "Pinned tools are installed under ~/.local/share/mise/."
echo "Once per shell (add to ~/.bashrc if missing):"
echo '  eval "$(mise activate bash)"'
