# Agent Version Management

## 🔴 CRITICAL: Update Version When Making Changes

**Every time you modify agent code, you MUST update the version number.**

This is enforced by a git pre-commit hook - it will prevent you from committing agent code changes without updating the version.

### Current Version
```
v1.0.2 (Dec 11, 2025)
```

### Quick Start

**When you modify agent code:**

1. **Edit version in `agent/go/main.go`** (around line 30)
   ```go
   const AgentVersion = "1.0.2"  // ← Update this
   ```

2. **Add to changelog** (in the same file)
   ```go
   // v1.0.3: Fixed memory calculation for Windows services
   ```

3. **Commit**
   ```bash
   git add agent/go/main.go
   git commit -m "fix: agent v1.0.3 - memory calculation fix"
   ```

4. **The pre-commit hook will verify your version was updated**
   - ✅ If version was updated → commit succeeds
   - ❌ If version wasn't updated → commit fails with helpful message

### Semantic Versioning

```
AgentVersion = "MAJOR.MINOR.PATCH"

1.0.2
├─ 1 = MAJOR (breaking changes)
├─ 0 = MINOR (new features)
└─ 2 = PATCH (bug fixes, improvements)

WHEN TO INCREMENT:
• PATCH (1.0.2 → 1.0.3): Bug fixes, performance tweaks, calculation improvements
• MINOR (1.0.2 → 1.1.0): New metrics added, new features, backward compatible
• MAJOR (1.0.2 → 2.0.0): Breaking changes, incompatible changes (rare)
```

### Version History

| Version | What Changed |
|---------|-------------|
| 1.0.2 | Added uptime metrics, improved network bandwidth, enhanced tracking |
| 1.0.1 | Fixed network bandwidth calculation for per-interface metrics |
| 1.0.0 | Initial release - CPU, Memory, Disk, Network metrics |

### How the Hook Works

The pre-commit hook checks:
1. Did you modify any files in `agent/go/`?
2. Did you also modify the `AgentVersion` constant?
3. If NO → Commit fails with clear instructions
4. If YES → Commit succeeds ✅

### Examples

**❌ WILL FAIL** - Code changed, version didn't:
```bash
$ git add agent/go/main.go
$ git commit -m "fix: network calculation"
# ⚠️ WARNING: Agent code was modified but version number was NOT updated!
```

**✅ WILL SUCCEED** - Both code and version changed:
```bash
$ git add agent/go/main.go  # Has updated AgentVersion
$ git commit -m "fix: agent v1.0.3 - network calculation"
# ✓ Agent code modified and version updated to 1.0.3
```

### Bypass (Not Recommended)

If you absolutely need to skip the hook:
```bash
git commit --no-verify
```

But please don't - the hook exists to keep code organized!

### Git Hook Location

The enforcement hook is in: `.githooks/pre-commit`

If you clone the repo fresh, configure it with:
```bash
git config core.hooksPath .githooks
```

---

**TL;DR:**
- Change agent code → Update version number → Commit
- The hook ensures you never forget!
