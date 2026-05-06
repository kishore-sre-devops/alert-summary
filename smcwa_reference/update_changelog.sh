#!/bin/bash
# update_changelog.sh - Automatically update CHANGELOG.json when agent version changes
# Run this script after building a new agent version

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Get the current agent version from the Go source
get_agent_version() {
    local version_file="agent/go/main.go"
    if [ ! -f "$version_file" ]; then
        echo "Error: $version_file not found" >&2
        return 1
    fi

    # Extract version from: const AgentVersion = "1.0.x"
    local version=$(grep -o 'const AgentVersion = "[^"]*"' "$version_file" | sed 's/const AgentVersion = "\(.*\)"/\1/')
    if [ -z "$version" ]; then
        echo "Error: Could not extract version from $version_file" >&2
        return 1
    fi

    echo "$version"
}

# Update CHANGELOG.json with new version entry
update_changelog() {
    local version="$1"
    local changelog_file="CHANGELOG.json"

    if [ ! -f "$changelog_file" ]; then
        echo "Creating new $changelog_file"
        cat > "$changelog_file" << EOF
{
  "versions": {
    "$version": {
      "release_date": "$(date +%Y-%m-%d)",
      "changes": [
        "Version $version released"
      ],
      "type": "feature"
    }
  }
}
EOF
        return 0
    fi

    # Check if version already exists
    if jq -e ".versions.\"$version\"" "$changelog_file" > /dev/null 2>&1; then
        echo "Version $version already exists in changelog"
        return 0
    fi

    echo "Adding version $version to changelog"

    # Add new version entry (you'll need to edit the changes manually)
    jq ".versions.\"$version\" = {
        \"release_date\": \"$(date +%Y-%m-%d)\",
        \"changes\": [
            \"Version $version released - update changes manually\"
        ],
        \"type\": \"feature\"
    }" "$changelog_file" > "${changelog_file}.tmp" && mv "${changelog_file}.tmp" "$changelog_file"

    echo "✅ Updated $changelog_file with version $version"
    echo "📝 Remember to edit the changes array in $changelog_file with actual release notes"
}

# Main execution
main() {
    echo "🔍 Detecting current agent version..."
    local version=$(get_agent_version)
    echo "📦 Current version: $version"

    echo "📝 Updating changelog..."
    update_changelog "$version"

    echo "✅ Changelog update complete!"
    echo ""
    echo "Next steps:"
    echo "1. Edit CHANGELOG.json to update the changes for version $version"
    echo "2. Rebuild the API container: docker compose build --no-cache api"
    echo "3. Restart the API: docker compose up -d api"
}

main "$@"