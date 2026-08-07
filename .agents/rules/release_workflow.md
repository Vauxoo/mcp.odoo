# Release Workflow — odoo-mcp-multi

## Rule for C3PO

After completing ANY task in this repository, ALWAYS ask Gerónimo:

> "¿Hacemos merge? Si sí: ¿`[patch]` / `[minor]` / `[major]` o sin release?"

If he says "con release", add the marker to the commit message of the MR before pushing.
If he says "sin release", push normally — no marker needed.

## Convention

| Marker in commit | Result |
|-----------------|--------|
| *(none)* | Merge freely, no release |
| `[patch]` | `0.4.x → 0.4.x+1` |
| `[minor]` | `0.4.x → 0.5.0` |
| `[major]` | `0.4.x → 1.0.0` |

## Notes

- The marker can appear anywhere in any commit of the push.
- It also works inside the MR title if GitLab squashes commits.
- `[skip release]` no longer exists — omitting the marker IS the skip.

## Changelog & announcement (automated since 0.16.0)

- Keep notes under `## [Unreleased]` in `CHANGELOG.md` as you merge. At
  release time `bump-my-version` renames that section to
  `## [X.Y.Z] - <date>` and leaves a fresh empty `[Unreleased]` on top —
  never stamp versions by hand.
- The `release-notes` CI job publishes the stamped section as the GitLab
  Release description; the `ai/marketplace` announcer broadcasts its first
  plain paragraph to Telegram (bullets are skipped). So when cutting a
  release, open the Unreleased section with 1–3 human lines — the tweet-style
  "why this matters" — before the `###` subsections. An optional `Try:` line
  becomes the suggested prompt in the announcement.
- Do not delete the `## [Unreleased]` header: the bump fails without it
  (guarded by `test_changelog_release_contract`).
