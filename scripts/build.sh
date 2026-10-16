#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
dist_root="$project_root/dist"

mkdir -p "$dist_root/server" "$dist_root/.openai"
cp "$project_root/worker/index.js" "$dist_root/server/index.js"
cp "$project_root/.openai/hosting.json" "$dist_root/.openai/hosting.json"

# Stamp the page footer with the commit being deployed.
source_commit=$(git -C "$project_root" rev-parse HEAD)
git -C "$project_root" diff --quiet HEAD || source_commit="$source_commit-dirty"
sed -i.bak "s/__MONEYMAP_SOURCE_COMMIT__/$source_commit/" "$dist_root/server/index.js"
rm "$dist_root/server/index.js.bak"

echo "Built $dist_root"
