# Odoo 17, 18, and 19+ Financial Reports XML IDs and Options Catalog

This guide provides the official XML IDs for standard financial reports in Odoo 17, 18, and 19+ and details the schema of the `options` dictionary to enable direct, optimized querying.

---

## 1. Official Report XML IDs

Standard financial reports in Odoo are defined as XML records in the `account_reports` module. Using their XML IDs ensures database-independent references:

| Report Name | XML ID | Description |
|:---|:---|:---|
| **Balance Sheet** | `account_reports.balance_sheet` | Statement of assets, liabilities, and equity at a point in time. |
| **Profit and Loss** | `account_reports.profit_and_loss` | Summary of revenues, costs, and expenses over a period. |
| **General Ledger** | `account_reports.general_ledger` | Detailed list of transactions grouped by account. |
| **Partner Ledger** | `account_reports.partner_ledger` | Detailed transactions grouped by customer/vendor. |
| **Trial Balance** | `account_reports.trial_balance` | Balance of all ledger accounts at a specific date. |
| **Cash Flow Statement** | `account_reports.cash_flow_report` | Inflows and outflows of cash over a period. |
| **Executive Summary** | `account_reports.executive_summary` | High-level performance KPIs and financial health metrics. |
| **Aged Receivable** | `account_reports.aged_receivable` | Outstanding customer invoices aged by period. |
| **Aged Payable** | `account_reports.aged_payable` | Outstanding vendor bills aged by period. |
| **Bank Reconciliation** | `account_reports.bank_reconciliation_report` | Reconciliation of bank statements with ledger entries. |

### Resolving XML ID to Database ID

To resolve the XML ID to an integer database ID in a single call, query the `ir.model.data` model:

```bash
odoo-mcp search-read --model ir.model.data --domain "[('module', '=', 'account_reports'), ('name', '=', 'profit_and_loss')]" --fields res_id
```

---

## 2. Options Dictionary Schema (`previous_options`)

When calling `get_options(previous_options)`, pass a customized options dictionary directly to pre-initialize the filters. Below is the detailed schema for common filters:

### A. Date Filter (`date` key)

Used to define the reporting period.

- **mode**: `"range"` (for period-based reports like P&L) or `"single"` (for point-in-time reports like Balance Sheet).
- **filter**: `"custom"`, `"this_year"`, `"this_month"`, `"today"`, `"last_month"`, `"last_year"`.
- **date_from**: `"YYYY-MM-DD"` (required if filter is `"custom"` and mode is `"range"`).
- **date_to**: `"YYYY-MM-DD"` (required if filter is `"custom"`).

*Example:*

```json
{
  "date": {
    "mode": "range",
    "filter": "custom",
    "date_from": "2026-01-01",
    "date_to": "2026-05-31"
  }
}
```

### B. Draft Entries Filter (`all_entries` key)

Define whether to include unposted journal entries.

- **Type**: Boolean (`true` or `false`).

*Example:*

```json
{
  "all_entries": true
}
```

### C. Unreconciled Filter (`unreconciled` key)

Define whether to show only unreconciled entries (relevant for Partner Ledger).

- **Type**: Boolean.

*Example:*

```json
{
  "unreconciled": true
}
```

### D. Expand All Lines (`unfold_all` key)

Automatically expand all sub-levels in the output lines.

- **Type**: Boolean.

*Example:*

```json
{
  "unfold_all": true
}
```

---

## 3. Two-Step Execution Blueprint

Combine the resolved ID and options to calculate reports in exactly **2 calls**:

### Call 1: Resolve ID and Get Options

```python
# Call get_options with target date filters directly
opts_raw = execute_kw(
    model="account.report",
    method="get_options",
    args=[
        [resolved_db_id],
        {
            "date": {
                "mode": "range",
                "filter": "custom",
                "date_from": "2026-01-01",
                "date_to": "2026-05-31"
            }
        }
    ]
)
```

### Call 2: Calculate Report

Extract the `report_id` from `opts_raw.result.report_id` (resolving any country variants) and pass the `opts_raw.result` options dict:

```python
report_data = execute_kw(
    model="account.report",
    method="get_report_information",
    args=[[target_report_id], opts_raw.result]
)
```
