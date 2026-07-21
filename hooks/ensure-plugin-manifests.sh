#!/bin/bash
# Synthesize .claude-plugin/plugin.json for cached marketplace plugins that
# ship without one. Without a manifest, the inline plugin loader (desktop app)
# falls back to the version-directory basename as the plugin name, so e.g.
# complete@policyengine-claude also loads as "3.23.0:*" and every manifest-less
# v0.1.0 plugin merges into a shared "0.1.0:*" namespace. Plugin updates
# regenerate cache dirs, so this must re-run each session (SessionStart hook).
# Cache layout: ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/

CACHE="$HOME/.claude/plugins/cache"
[ -d "$CACHE" ] || exit 0

for version_dir in "$CACHE"/*/*/*/; do
  [ -d "$version_dir" ] || continue
  [ -f "$version_dir/.claude-plugin/plugin.json" ] && continue
  plugin=$(basename "$(dirname "$version_dir")")
  version=$(basename "$version_dir")
  mkdir -p "$version_dir/.claude-plugin"
  if [ -f "$version_dir/plugin.json" ]; then
    # Older layout: manifest at plugin root — copy it where the loader looks.
    cp "$version_dir/plugin.json" "$version_dir/.claude-plugin/plugin.json"
  else
    python3 - "$version_dir/.claude-plugin/plugin.json" "$plugin" "$version" <<'EOF'
import json, sys
path, name, version = sys.argv[1:4]
json.dump({
    "name": name,
    "version": version,
    "description": f"Manifest synthesized by ensure-plugin-manifests.sh (upstream ships none; prevents version-string plugin names in inline loading)",
}, open(path, "w"), indent=2)
EOF
  fi
  echo "ensure-plugin-manifests: synthesized manifest for ${plugin}@${version}"
done
exit 0
