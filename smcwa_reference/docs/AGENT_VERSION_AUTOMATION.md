# Agent Version and Changelog Automation

## Overview
The SMC-LAMA agent onboarding dashboard now automatically displays version information and changelog from dynamic sources instead of hardcoded values.

## Automated Components

### 1. Agent Version (`/api/v1/agents/version`)
- **Source**: Reads version directly from `agent/go/main.go` source code
- **Method**: Parses `const AgentVersion = "x.x.x"` from the Go source
- **Update**: Automatically reflects the current built agent version

### 2. Changelog (`/api/v1/agents/changelog`)
- **Source**: Reads from `CHANGELOG.json` file
- **Format**: JSON structure with version entries
- **Update**: Requires manual editing of `CHANGELOG.json` when releasing new versions

## File Structure

```
CHANGELOG.json
├── versions
│   ├── "1.0.4"
│   │   ├── release_date: "2025-12-11"
│   │   ├── changes: ["Feature 1", "Feature 2"]
│   │   └── type: "feature|bugfix|initial"
│   └── "1.0.3"
│       └── ...
```

## Release Process

When releasing a new agent version:

1. **Update Go source version**:
   ```go
   const AgentVersion = "1.0.5"
   ```

2. **Run changelog update script**:
   ```bash
   ./update_changelog.sh
   ```

3. **Edit CHANGELOG.json** to add actual release notes for the new version

4. **Rebuild and deploy**:
   ```bash
   docker compose build --no-cache api
   docker compose up -d api
   npm run build  # For UI
   ```

## Benefits

- ✅ **Version info always current** - No manual updates needed
- ✅ **Changelog centralized** - Single source of truth for release notes
- ✅ **Automated detection** - Version read from source code
- ✅ **Dynamic UI updates** - Frontend fetches latest data
- ✅ **Historical tracking** - Complete version history maintained

## API Endpoints

- `GET /api/v1/agents/version` - Returns current agent version
- `GET /api/v1/agents/changelog` - Returns full changelog data

## Maintenance

- Keep `CHANGELOG.json` updated with meaningful release notes
- Run `./update_changelog.sh` after version bumps
- Rebuild API container when changelog changes
- Frontend automatically reflects all changes