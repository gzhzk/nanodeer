# OpenClaw Prompts & Skills

All available prompts and skills for OpenClaw development, maintenance, and releases.

---

## `.pi/prompts/` — Codex Local Prompts

Located at `.pi/prompts/`, these are lightweight task-specific prompts for Codex (local AI coding assistant).

---

### `is.md` — Issue Analyzer

**Description:** Analyze GitHub issues (bugs or feature requests)

**Trigger:** `/is [issue-url|number]`

**Purpose:** Analyze GitHub issue(s) — bugs or feature requests — and propose implementation approaches without implementing.

**Process:**
1. Read the issue in full, including all comments and linked issues/PRs
2. **For bugs:**
   - Ignore any root cause analysis in the issue (likely wrong)
   - Read all related code files in full (no truncation)
   - Trace the code path and identify the actual root cause
   - Propose a fix
3. **For feature requests:**
   - Read all related code files in full (no truncation)
   - Propose the most concise implementation approach
   - List affected files and changes needed

**Rule:** Do NOT implement unless explicitly asked. Analyze and propose only.

---

### `cl.md` — Changelog Auditor

**Description:** Audit changelog entries before release

**Purpose:** Verify all commits since the last release have proper changelog entries.

**Process:**
1. Find the last release tag: `git tag --sort=-version:refname | head -1`
2. List all commits since that tag: `git log <tag>..HEAD --oneline`
3. Read each package's `[Unreleased]` section:
   - `packages/ai/CHANGELOG.md`
   - `packages/tui/CHANGELOG.md`
   - `packages/coding-agent/CHANGELOG.md`
4. For each commit, check:
   - Skip: changelog updates, doc-only changes, release housekeeping
   - Determine which package(s) the commit affects
   - Verify a changelog entry exists in the affected package(s)
   - For external contributions: verify format: `Description ([#N](url) by [@user](url))`
5. **Cross-package duplication rule:** Changes in `ai`, `agent` or `tui` that affect end users should be duplicated to `coding-agent` changelog
6. **Add New Features section** after changelog fixes:
   - Insert `### New Features` at the start of `## [Unreleased]` in `packages/coding-agent/CHANGELOG.md`
   - Propose top new features for confirmation before writing

**Changelog Format (sections in order):**
- `### Breaking Changes` - API changes requiring migration
- `### Added` - New features
- `### Changed` - Changes to existing functionality
- `### Fixed` - Bug fixes
- `### Removed` - Removed features

**Attribution:**
- Internal: `Fixed foo ([#123](https://github.com/badlogic/pi-mono/issues/123))`
- External: `Added bar ([#456](https://github.com/badlogic/pi-mono/pull/456) by [@user](https://github.com/user))`

---

### `reviewpr.md` — PR Reviewer

**Description:** Review a PR thoroughly without merging

**Trigger:** `/reviewpr [pr-number|url]`

**Goal:** Produce a thorough review and a clear recommendation. Do NOT merge, push, or make changes.

**Required Gate (for bug-fix claims):**
- Do not trust issue text or PR summary by default
- Verify bug exists now (repro steps, logs, failing test, or clear code-path proof)
- Prove root cause with exact location (`path/file.ts:line` + explanation)
- Verify fix targets the same code path as the root cause
- Require regression test when feasible; if not, require explicit justification + manual verification

**Hallucination/BS red flags (treat as BLOCKER):**
- Claimed behavior not present in repo
- Issue/PR says "fixes #..." but changed files do not touch implicated path
- Only docs/comments changed for a runtime bug claim
- Vague AI-generated rationale without concrete evidence

**Review Steps:**
1. Identify PR meta + context via `gh pr view`
2. Read the PR description carefully
3. Read the full diff
4. Validate the change is needed / valuable
5. Evaluate implementation quality + optimality (correctness, design, performance, security, backwards compatibility, style)
6. Assess tests & verification coverage
7. Note follow-up refactors / cleanup suggestions

**Output Structure:**
- **A) TL;DR recommendation:** READY FOR /landpr | NEEDS WORK | INVALID CLAIM | NEEDS DISCUSSION
- **B) Claim verification matrix:**
  | Field | Evidence |
  |-------|----------|
  | Claimed problem | ... |
  | Evidence observed | ... |
  | Root cause location | ... |
  | Why this fix addresses that | ... |
  | Regression coverage | ... |
- **C) What changed** — brief bullet summary
- **D) What's good** — correctness, simplicity, tests, docs, ergonomics
- **E) Concerns / questions** — numbered, marked as BLOCKER / IMPORTANT / NIT
- **F) Tests** — what exists, what's missing, regression test status
- **G) Follow-ups** — non-blocking refactors/tickets
- **H) Suggested PR comment** — optional ready-to-paste summary

---

### `landpr.md` — PR Lander

**Description:** Land a PR (merge with proper workflow)

**Trigger:** `/landpr [pr-number|url]`

**Goal:** PR must end in GitHub state = MERGED (never CLOSED)

**Merge Strategy:**
- Squash (preferred): `gh pr merge <PR> --squash`
- Rebase (only when preserving commit history required): `gh pr merge <PR> --rebase`

**Workflow Steps:**
1. Assign PR to self: `gh pr edit <PR> --add-assignee @me`
2. Ensure repo clean: `git status`
3. Identify PR meta (author + head branch)
4. Fast-forward base: `git checkout main && git pull --ff-only`
5. Create temp base branch: `git checkout -b temp/landpr-<ts>`
6. Check out PR branch: `gh pr checkout <PR>`
7. Rebase onto temp base: `git rebase temp/landpr-<ts>`
8. Fix conflicts; keep history tidy
9. Implement fixes + adjust tests
10. Update `CHANGELOG.md` with `#<PR>` + `@$contrib`
11. Run gate: `pnpm lint && pnpm build && pnpm test`
12. Commit via committer: `committer "fix: <summary> (#<PR>) (thanks @$contrib)" CHANGELOG.md <files>`
13. Push updated PR branch (usually needs force)
14. Merge PR via squash or rebase
15. Sync main: `git checkout main && git pull --ff-only`
16. Comment on PR with what was done + SHAs + thanks
17. Verify PR state == MERGED
18. Delete temp branch

**Key Rules:**
- Never `gh pr close` (closing is wrong)
- Final merge commit only includes PR # + thanks
- Intermediate fix commits omit PR number/thanks

---

## `.agents/skills/` — Agent Skills

Located at `.agents/skills/`, these are detailed skill definitions for OpenClaw maintainer workflows.

---

### `openclaw-release-maintainer/SKILL.md`

**Name:** `openclaw-release-maintainer`

**Description:** Maintainer workflow for OpenClaw releases, prereleases, changelog release notes, and publish validation.

**Guardrails:**
- Do not change version numbers without explicit operator approval
- Ask permission before any npm publish or release step
- Use the private maintainer release docs for credentials/recovery/mac specifics
- Use `docs/reference/RELEASING.md` for public policy
- Core `openclaw` publish is manual `workflow_dispatch`; creating/pushing a tag does not publish by itself

**Release Channel Naming:**
- `stable`: tagged releases only, published to npm `latest` then mirrored to `beta`
- `beta`: prerelease tags like `vYYYY.M.D-beta.N` with npm dist-tag `beta`
- Prefer `-beta.N`; do not mint new `-1` or `-2` beta suffixes
- `dev`: moving head on `main`

**Version Locations (must all match before tagging):**
- `package.json`
- `apps/android/app/build.gradle.kts`
- `apps/ios/Sources/Info.plist`
- `apps/ios/Tests/Info.plist`
- `apps/macos/Sources/OpenClaw/Resources/Info.plist`
- `docs/install/updating.md`
- Peekaboo Xcode project and plist version fields

**Note:** "Bump version everywhere" excludes `appcast.xml`.

**Publish-time Validation (run before tagging/publishing):**
```bash
pnpm build
pnpm ui:build
pnpm release:check
pnpm test:install:smoke
# or for non-root:
OPENCLAW_INSTALL_SMOKE_SKIP_NONROOT=1 pnpm test:install:smoke
```

**After npm publish:**
```bash
node --import tsx scripts/openclaw-npm-postpublish-verify.ts <published-version>
```

**Release Sequence:**
1. Confirm operator explicitly wants to cut a release
2. Choose exact target version and git tag
3. Make every repo version location match that tag before creating it
4. Update `CHANGELOG.md` and assemble GitHub release notes
5. Run full preflight for all relevant release builds
6. Confirm target npm version is not already published
7. Create and push the git tag
8. Create or refresh matching GitHub release
9-18. Run preflight workflows, await approvals, publish npm and mac
19. Verify artifacts and update `appcast.xml` (stable only)

**Related:** Use `openclaw-ghsa-maintainer` for GHSA advisory workflow.

---

### `openclaw-ghsa-maintainer/SKILL.md`

**Name:** `openclaw-ghsa-maintainer`

**Description:** Maintainer workflow for GitHub Security Advisories (GHSA) — inspect, patch, validate, or publish repo advisories.

**Guardrails:**
- Before reviewing or publishing, read `SECURITY.md`
- Ask permission before any publish action
- GHSA-only; do not use for stable or beta release work

**Workflow:**
1. Fetch advisory state + latest npm version
2. Verify private fork PRs are closed before publishing
3. Prepare advisory Markdown and JSON safely (use heredoc + `jq`, not escaped strings)
4. Apply PATCH calls in correct sequence (do not set `severity` and `cvss_vector_string` in same call)
5. Publish by PATCHing with `"state":"published"` (no separate `/publish` endpoint)
6. Verify success: re-fetch and confirm `state=published`, `published_at` set, no literal `\\n`

**Common GHSA Footguns:**
- Publishing fails HTTP 422 if required fields missing or private fork still has open PRs
- Markdown assembled with escaped newlines looks correct in shell but is wrong
- Advisory PATCH sequencing matters; separate field updates when API constraints require it

---

### `openclaw-pr-maintainer/SKILL.md`

**Name:** `openclaw-pr-maintainer`

**Description:** Maintainer workflow for reviewing, triaging, preparing, closing, or landing OpenClaw pull requests.

**Bug-Fix Evidence Bar (enforced before merge):**
1. Symptom evidence (repro, logs, failing test)
2. Verified root cause in code with file/line
3. Fix that touches the implicated code path
4. Regression test when feasible, or explicit manual verification + reason no test added

**Close Labels:**
- `r: skill`, `r: support`, `r: no-ci-pr`, `r: too-many-prs`, `r: testflight`, `r: third-party-extension`, `r: moltbook`, `r: spam`
- `invalid`, `dirty` (PRs only)

**Rule:** If issue or PR matches an auto-close reason, apply the label and let `.github/workflows/auto-response.yml` handle the comment/close/lock flow. Do not manually close + manually comment.

**GitHub Text Safety:**
- Use literal multiline strings or `-F - <<'EOF'` for real newlines
- Never embed `\n` in `-b "..."`
- Do not wrap issue/PR refs like `#24643` in backticks (breaks auto-linking)

**Search Examples:**
```bash
gh search prs --repo openclaw/openclaw --match title,body --limit 50 -- "auto-update"
gh search issues --repo openclaw/openclaw --match title,body --limit 50 -- "auto update"
```

**Safety:** If close/reopen would affect >5 PRs, ask for explicit confirmation first.

---

### `openclaw-parallels-smoke/SKILL.md`

**Name:** `openclaw-parallels-smoke`

**Description:** End-to-end Parallels smoke, upgrade, and rerun workflow for OpenClaw across macOS, Windows, and Linux guests.

**Entry Points:**
- `pnpm test:parallels:macos` — macOS flow
- `pnpm test:parallels:windows` — Windows flow
- `pnpm test:parallels:linux` — Linux flow
- `pnpm test:parallels:npm-update` — npm install then update

**Global Rules:**
- Use snapshot most closely matching requested fresh baseline
- Gateway verification: `openclaw gateway status --deep --require-rpc`
- Pass `--json` for machine-readable summaries
- Per-phase logs: `/tmp/openclaw-parallels-*`
- Do not run local and gateway agent turns in parallel on same fresh workspace
- Use `prlctl exec "$VM" --current-user ...` (VM name before `--current-user`)

**macOS Notes:**
- Snapshot: closest to `macOS 26.3.1 latest`
- Use `/opt/homebrew/bin/node` when needed on fresh snapshots
- Fresh host-served tgz installs: install as guest root with `HOME=/var/root`, onboard as desktop user via `prlctl exec --current-user`

**Windows Notes:**
- Always use `prlctl exec --current-user`
- Prefer explicit `npm.cmd` and `openclaw.cmd`
- Use PowerShell only as transport with `-ExecutionPolicy Bypass`
- Global npm installs can stay quiet for minute+ even when healthy

**Linux Notes:**
- Snapshot: closest to fresh `Ubuntu 24.04.3 ARM64` or `Ubuntu 25.10`
- Use plain `prlctl exec` (no `--current-user`)
- Bootstrap with `apt-get -o Acquire::Check-Date=false update` if clock skew

**Discord Roundtrip:** Optional, enabled with `--discord-token-env`, `--discord-guild-id`, `--discord-channel-id`. See `parallels-discord-roundtrip` skill for deep-dive.

---

### `parallels-discord-roundtrip/SKILL.md`

**Name:** `parallels-discord-roundtrip`

**Description:** macOS Parallels smoke with Discord end-to-end roundtrip verification.

**Goal:** Prove Discord two-way delivery:
1. Install on fresh macOS snapshot
2. Onboard + gateway health
3. Guest `message send` to Discord
4. Host sees that message on Discord
5. Host posts a new Discord message
6. Guest `message read` sees that new message

**Inputs:**
- Discord bot token (host env var)
- Discord guild ID
- Discord channel ID
- `OPENAI_API_KEY`

**Preferred Run:**
```bash
pnpm test:parallels:macos \
  --discord-token-env OPENCLAW_PARALLELS_DISCORD_TOKEN \
  --discord-guild-id 1456350064065904867 \
  --discord-channel-id 1456744319972282449 \
  --json
```

**Pass Criteria:**
- Fresh lane or upgrade lane passes
- Summary reports `discord=pass`
- Guest outbound nonce appears in channel history
- Host inbound nonce appears in `openclaw message read` output

---

### `openclaw-test-heap-leaks/SKILL.md`

**Name:** `openclaw-test-heap-leaks`

**Description:** Investigate `pnpm test` memory growth, Vitest worker OOMs, and suspicious RSS increases.

**Workflow:**
1. Reproduce the failing shape with heap snapshots enabled:
   ```bash
   pnpm canvas:a2ui:bundle && \
   OPENCLAW_TEST_MEMORY_TRACE=1 \
   OPENCLAW_TEST_HEAPSNAPSHOT_INTERVAL_MS=60000 \
   OPENCLAW_TEST_HEAPSNAPSHOT_DIR=.tmp/heapsnap \
   OPENCLAW_TEST_WORKERS=2 \
   OPENCLAW_TEST_MAX_OLD_SPACE_SIZE_MB=6144 \
   pnpm test
   ```
2. Wait for repeated snapshots before concluding (at least two intervals from same lane)
3. Compare snapshots from same PID: `node .agents/skills/openclaw-test-heap-leaks/scripts/heapsnapshot-delta.mjs --lane-dir .tmp/heapsnap/<lane>`
4. Classify the growth:
   - Dominated by Vite/Vitest transformed source strings, `Module`, `system / Context`, bytecode → likely retained module graph growth
   - Dominated by app objects, caches, buffers, server handles, timers, mock state → likely cleanup/lifecycle leak
5. Fix the right layer:
   - Module retention: prefer timing/hotspot fixes; check `test/fixtures/test-timings.unit.json`; use `singletonIsolated` for hotspot files
   - Real leaks: patch cleanup path; look for missing `afterEach`/`afterAll`, unreleased handles, listeners/timers

**Snapshot Comparison:**
```bash
# Direct comparison:
node .agents/skills/openclaw-test-heap-leaks/scripts/heapsnapshot-delta.mjs before.heapsnapshot after.heapsnapshot

# Auto-select earliest/latest per PID:
node .agents/skills/openclaw-test-heap-leaks/scripts/heapsnapshot-delta.mjs --lane-dir .tmp/heapsnap/<lane>

# Flags: --top 40 --min-kb 32 --pid 16133
```

**Rule:** Do not call everything a leak. Large `unit-fast` growth can be worker-lifetime problem, not application leak.

---

### `security-triage/SKILL.md`

**Name:** `security-triage`

**Description:** Triage GitHub security advisories with high-confidence close/keep decisions.

**Close Bar (close only if one of true):**
- duplicate of existing advisory or fixed issue
- invalid against shipped behavior
- out of scope under `SECURITY.md`
- fixed before any affected release/tag

**Rule:** Do not close only because `main` is fixed. If latest shipped tag or npm release is affected, keep open until released with right status.

**Required Reads:**
1. `SECURITY.md`
2. GHSA body: `gh api /repos/openclaw/openclaw/security-advisories/<GHSA>`
3. Inspect exact implicated code paths
4. Verify shipped state:
   - `git tag --sort=-creatordate | head`
   - `npm view openclaw version`
   - `git tag --contains <fix-commit>`
   - `git show <tag>:path/to/file` if needed
5. Search for canonical overlap (existing GHSAs, older fixed bugs, same trust-model class in `SECURITY.md`)

**Review Method (check in order):**
1. **Trust model:** Is prerequisite already inside trusted host/local/plugin/operator state? Is it explicitly out of scope in `SECURITY.md`?
2. **Shipped behavior:** Is bug in latest shipped tag or npm release? Was it fixed before release?
3. **Exploit path:** Real boundary bypass, not just prompt injection, local same-user control, or helper-level semantics?
4. **Functional tradeoff:** If hardening would reduce intended functionality, call that out; prefer fixes that preserve user workflows

**Decision Labels:** `close` | `keep open` | `keep open but narrow`

**Decision Notes:**
- "fixed on main, unreleased" is usually not a close
- "needs attacker-controlled trusted local state first" is usually out of scope
- "same-host same-user process can already read/write local state" is usually out of scope
- "helper function behaves differently than documented config semantics" is usually invalid
- If only severity is wrong but bug is real, keep open and narrow impact

**Output:** Draft detailed response with GHSA URL, exact reason, code refs, shipped tag facts, fix commit/duplicate GHSA, optional hardening note. Copy to clipboard via `pbcopy`.

---

### `security-triage/SKILL.md`

**Name:** `security-triage`

**Description:** Triage GitHub security advisories for OpenClaw with high-confidence close/keep decisions.

**Close Bar:**
- duplicate of existing advisory or fixed issue
- invalid against shipped behavior
- out of scope under `SECURITY.md`
- fixed before any affected release/tag

**Do NOT close only because `main` is fixed.** If latest shipped tag or npm release is affected, keep open until released.

**Required Reads:**
1. `SECURITY.md`
2. GHSA body
3. Exact implicated code paths
4. Shipped state verification

**Response Format:**
1. Print GHSA URL first
2. Draft detailed response with exact reason, code refs, shipped tag facts, fix commit
3. Include optional hardening note only if worthwhile and functionality-preserving

---

### `openclaw-test-heap-leaks/SKILL.md`

**Name:** `openclaw-test-heap-leaks`

**Description:** Investigate test memory growth, Vitest worker OOMs, and suspicious RSS increases using heap snapshot tooling.

**Workflow:**
1. Reproduce failing shape with memory trace + heap snapshots
2. Compare snapshots from same PID
3. Classify: module graph retention vs. real leak
4. Fix right layer (timing/hotspot scheduling or cleanup patches)
5. Verify with targeted lane re-run

---

## Summary Table

| File | Name | Purpose |
|------|------|---------|
| `.pi/prompts/is.md` | Issue Analyzer | Analyze bugs/feature requests, propose fixes |
| `.pi/prompts/cl.md` | Changelog Auditor | Verify changelog entries before release |
| `.pi/prompts/reviewpr.md` | PR Reviewer | Thorough PR review with evidence gate |
| `.pi/prompts/landpr.md` | PR Lander | End-to-end PR merge workflow |
| `.agents/skills/openclaw-release-maintainer/SKILL.md` | Release Maintainer | Release/publish workflow |
| `.agents/skills/openclaw-ghsa-maintainer/SKILL.md` | GHSA Maintainer | Security advisory workflow |
| `.agents/skills/openclaw-pr-maintainer/SKILL.md` | PR Maintainer | PR triage, close, landing decisions |
| `.agents/skills/openclaw-parallels-smoke/SKILL.md` | Parallels Smoke | VM smoke tests (macOS/Windows/Linux) |
| `.agents/skills/parallels-discord-roundtrip/SKILL.md` | Discord Roundtrip | Discord two-way delivery smoke |
| `.agents/skills/openclaw-test-heap-leaks/SKILL.md` | Test Heap Leaks | Memory leak investigation |
| `.agents/skills/security-triage/SKILL.md` | Security Triage | GHSA close/keep decisions |

---

## External Reference

- Maintainer skills now live in [`openclaw/maintainers`](https://github.com/openclaw/maintainers/)
- Global `/landpr` process: `~/.codex/prompts/landpr.md`
