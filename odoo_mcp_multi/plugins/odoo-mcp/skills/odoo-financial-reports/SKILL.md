---
name: "odoo-financial-reports"
description: "Use this skill when you need to fetch, calculate, analyze, or format Odoo financial reports (Balance Sheet, Profit & Loss, Trial Balance, Partner Ledger, General Ledger, Cash Flow, DIOT) via Odoo MCP. Triggers on: 'financial report', 'balance sheet', 'profit and loss', 'trial balance', 'partner ledger', 'general ledger', 'accounting report', 'financial statement', 'p&l', 'diot'."
last_validated: 2026-06-12
---

# Odoo Financial Reports Skill

This skill guides you on how to query Odoo financial reports (`account.report`) via the Odoo MCP server, delegate their calculations to Odoo, and parse and format their JSON structures into clean, readable Markdown reports.

## Prerequisites

- Active connection profile in `odoo-mcp-multi`.
- Direct execution access to the `execute_kw` and `search_read` tools.

## Odoo Version Context Awareness

This skill is designed and validated specifically for **Odoo 17.0, 18.0, and 19.0+**.
Before executing report queries on a connection profile, you should verify the target Odoo version using the `get_version` tool:

- **Odoo 17.0, 18.0, and 19.0+**: Uses the `get_financial_report` tool or CLI command which invokes `get_options` and `get_report_information` (singular for 19.0+, plural `get_report_informations` for 17.0/18.0) on the `account.report` model.
- **Odoo < 17.0**: Financial reports are handled differently (community/enterprise use distinct engines, and the database does not store report configurations in `account.report` records in the same way).

Ensure you inspect the target server version before executing financial report commands.

## Reference Catalog

Refer to the [financial_reports_options.md](financial_reports_options.md) catalog for:

- Mapping of all standard report names to their official Odoo XML IDs.
- Schema definitions for common report options (dates, journals, draft entries, etc.).

## Execution Workflow

Calculating a financial report in Odoo 17, 18, or 19+ must be done using the native `get_financial_report` tool or CLI command. This encapsulates the 2-step resolution chain (country redirects, active variants, and dates merging) into a single optimized operation.

### MCP Tool Usage

Call the `get_financial_report` tool with your target report name or ID:

```json
{
  "report_id_or_name": "Profit and Loss",
  "date_from": "2026-01-01",
  "date_to": "2026-05-31",
  "format": "html",
  "profile": "edyendigital"
}
```

### CLI Command Usage

Invoke the command directly from the shell:

```bash
odoo-mcp get-financial-report -r "Profit and Loss" --df 2026-01-01 --dt 2026-05-31 -f html -p edyendigital
```

## Presentation Formats

The tool handles formatting and represents Odoo's native OWL report layout styles:

### 1. HTML Format (`-f html`)

Generates a complete HTML page matching Odoo's native OWL report templates (`line.xml`, `header.xml`, `account_report.scss`) conceptually:

- **Spacing**: Inserts an empty `<tr>` row before `level=0` lines to group sections cleanly.
- **Header Structure**: Generates multi-row headers based on `column_headers` (dates) and subheaders (`columns` labels).
- **Indentation**: Indents hierarchical row concepts using left padding: `style="padding-left: {((level + 1) * 8) - 20}px;"` for `level >= 2`.
- **Level 0 Styling**: Styles root lines with bold text and a solid light grey (`#dee2e6`) background.
- **Totals**: Styles total lines (`id` containing `|total~~`) with bold text and double underlines (`border-bottom: 2px double #212529`).

### 2. Table / Markdown Format (`-f table`)

Renders a clean Markdown table with concept lines prepended with spaces (`  ` * `level`) to preserve hierarchy in chat interfaces.

### 3. CSV Format (`-f csv`)

Renders a RFC 4180 CSV representing the hierarchical concepts with spaces prefixing the concept labels.

### 4. JSON Format (`-f json`)

Returns the raw calculated report payload and options dictionaries for programmatic parsing.

## Known Discrepancies

- **Report 418 (STAFF)**: Misconfigured on Odoo 19. It references the deprecated field `analytic_account_id` on `account.move.line`, which is removed in Odoo 19. Calculating this report will fail with a 422 error.
