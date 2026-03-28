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
