# Git Hooks for SMC-LAMA

This directory contains git hooks that enforce development standards.

## Hooks Installed

### `pre-commit`
**Purpose:** Ensure agent version number is updated whenever agent code changes.

**What it does:**
- Checks if any files in `agent/go/` have been modified
- Verifies that the `AgentVersion` constant in `agent/go/main.go` has also been updated
- Prevents commits where code changed but version didn't

**How it works:**
```bash
# If you try to commit with modified agent code but unchanged version:
$ git commit -m "fix: improved network calculation"

⚠️  WARNING: Agent code was modified but version number was NOT updated!

Modified agent files:
   agent/go/main.go

Current version: 1.0.2

📝 You must update the version in: agent/go/main.go

Steps to fix:
1. Edit agent/go/main.go
2. Find: const AgentVersion = "1.0.2"
3. Update version number (e.g., to 1.0.3 for a patch)
4. Add changelog comment explaining what changed
5. Stage changes: git add agent/go/main.go
6. Try commit again
```

**To bypass (not recommended):**
```bash
git commit --no-verify
```

## Installing Hooks

Hooks are automatically used when you have this config set:
```bash
git config core.hooksPath .githooks
```

This is already configured in the repo. If you cloned the repo fresh, run:
```bash
cd /opt/smc-lama
git config core.hooksPath .githooks
```

## Verifying Hooks Work

Test the pre-commit hook:
```bash
# Modify an agent file without updating version
echo "// test" >> agent/go/main.go
git add agent/go/main.go
git commit -m "test: check hook"  # Should fail

# Now update version and try again
# Edit agent/go/main.go, update AgentVersion to 1.0.3
git add agent/go/main.go
git commit -m "test: check hook"  # Should succeed
```

## Modifying Hooks

If you need to update the pre-commit hook logic:
1. Edit `.githooks/pre-commit`
2. Test it works: `git commit --no-verify` to skip, then `git commit` normally to test
3. Commit the updated hook: `git add .githooks/pre-commit && git commit -m "improve: pre-commit hook"`

---

**These hooks help maintain code quality and version consistency across the team.**
