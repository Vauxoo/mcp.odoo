# Odoo 19 Financial Reports Catalog

Complete catalog of all active financial reports configured in the Odoo 19.0+e instance. This directory serves as a reference for agents performing accounting analysis to identify report IDs and their structures.

## Overview Table

| ID | Report Name | Localization | Root Report | Status |
|----|-------------|--------------|-------------|--------|
| 1 | DIOT | MX | account.report(1,) | ✅ Success |
| 10 | General Ledger | MX | account.report() | ✅ Success |
| 12 | Trial Balance | MX | account.report() | ✅ Success |
| 13 | EC Sales List | MX | account.report() | ✅ Success |
| 14 | Partner Ledger | MX | account.report() | ✅ Success |
| 15 | Unrealized Currency Gains/Losses | MX | account.report() | ✅ Success |
| 16 | Journal Report | MX | account.report() | ✅ Success |
| 17 | Depreciation Schedule | MX | account.report() | ✅ Success |
| 2 | Group by: Account > Tax  | MX | account.report(1,) | ✅ Success |
| 20 | VAT Report (RCE Purchase 8.4) | MX | account.report(1,) | ✅ Success |
| 21 | VAT Report (RCE Purchase 8.5) | MX | account.report(1,) | ✅ Success |
| 22 | VAT Report (RVIE Sales 14.4) | MX | account.report(1,) | ✅ Success |
| 23 | INS | MX | account.report() | ✅ Success |
| 24 | IDSE (Reingreso) | MX | account.report() | ✅ Success |
| 25 | IDSE (Baja) | MX | account.report() | ✅ Success |
| 26 | IDSE (Wage Update) | MX | account.report() | ✅ Success |
| 27 | SUA (Aseg) | MX | account.report() | ✅ Success |
| 28 | SUA (Affil) | MX | account.report() | ✅ Success |
| 29 | SUA (Mov) | MX | account.report() | ✅ Success |
| 3 | Group by: Tax > Account  | MX | account.report(1,) | ✅ Success |
| 30 | Alimony | MX | account.report() | ✅ Success |
| 4 | Balance sheet | MX | account.report(4,) | ✅ Success |
| 418 | Report 418 | Global | None | ❌ Error |
| 419 | Balance Sheet (tipo 4) | MX | account.report() | ✅ Success |
| 420 | DIOT | MX | account.report(1,) | ✅ Success |
| 421 | Bank Reconciliation Report | MX | account.report() | ✅ Success |
| 422 | Deferred Expense Report | MX | account.report() | ✅ Success |
| 423 | Deferred Revenue Report | MX | account.report() | ✅ Success |
| 424 | Balance sheet | MX | account.report(4,) | ✅ Success |
| 425 | Profit and Loss | MX | account.report(7,) | ✅ Success |
| 426 | Customer Statement | MX | account.report(14,) | ✅ Success |
| 427 | Follow-Up Report | MX | account.report(14,) | ✅ Success |
| 429 | Tax Report | MX | account.report(1,) | ✅ Success |
| 430 | Balance Sheet | MX | account.report(4,) | ✅ Success |
| 431 | Balance Sheet | MX | account.report(4,) | ✅ Success |
| 432 | Balance Sheet | MX | account.report(4,) | ✅ Success |
| 433 | Profit and Loss | MX | account.report(7,) | ✅ Success |
| 434 | Balance sheet | MX | account.report(4,) | ✅ Success |
| 435 | Effective VAT Statement (Mexico) | MX | account.report(1,) | ✅ Success |
| 5 | Cash Flow Statement | MX | account.report() | ✅ Success |
| 6 | Executive Summary | MX | account.report() | ✅ Success |
| 7 | Profit and Loss | MX | account.report(7,) | ✅ Success |
| 8 | Aged Receivable | MX | account.report() | ✅ Success |
| 9 | Aged Payable | MX | account.report() | ✅ Success |

---

## Detailed Report Structure

Below are details of the main financial reports, outlining what they contain and how their sections/lines are structured.

### DIOT (ID: 1)

- **Localization**: MX
- **Parent / Root Report**: account.report(1,)

**Primary Sections / Account Groups:**

- `DIOT`

---

### Journal Report (ID: 16)

- **Localization**: MX
- **Parent / Root Report**: account.report()

**Primary Sections / Account Groups:**

- `Name`
- `Global Tax Summary`

---

### Group by: Account > Tax  (ID: 2)

- **Localization**: MX
- **Parent / Root Report**: account.report(1,)

**Primary Sections / Account Groups:**

- `Purchases`

---

### VAT Report (RCE Purchase 8.4) (ID: 20)

- **Localization**: MX
- **Parent / Root Report**: account.report(1,)

**Primary Sections / Account Groups:**

- `RCE 8.4`

---

### VAT Report (RCE Purchase 8.5) (ID: 21)

- **Localization**: MX
- **Parent / Root Report**: account.report(1,)

**Primary Sections / Account Groups:**

- `RCE 8.5`

---

### Group by: Tax > Account  (ID: 3)

- **Localization**: MX
- **Parent / Root Report**: account.report(1,)

**Primary Sections / Account Groups:**

- `Purchases`

---

### Alimony (ID: 30)

- **Localization**: MX
- **Parent / Root Report**: account.report()

**Primary Sections / Account Groups:**

- `Total`

---

### Balance sheet (ID: 4)

- **Localization**: MX
- **Parent / Root Report**: account.report(4,)

**Primary Sections / Account Groups:**

- `Assets`
- `Liabilities`
- `Equity`
- `Equity and Liabilities`

---

### DIOT (ID: 420)

- **Localization**: MX
- **Parent / Root Report**: account.report(1,)

**Primary Sections / Account Groups:**

- `DIOT`

---

### Bank Reconciliation Report (ID: 421)

- **Localization**: MX
- **Parent / Root Report**: account.report()

**Primary Sections / Account Groups:**

- `Balance of 'CBC-BAC 928-753-490 CRC'`
- `Outstanding Receipts/Payments`

---

### Balance sheet (ID: 424)

- **Localization**: MX
- **Parent / Root Report**: account.report(4,)

**Primary Sections / Account Groups:**

- `Assets`
- `Liabilities`
- `Equity`
- `Equity and Liabilities`

---

### Profit and Loss (ID: 425)

- **Localization**: MX
- **Parent / Root Report**: account.report(7,)

**Primary Sections / Account Groups:**

- `Gross profit`
- `Operating Expenses`
- `Operating profit`
- `Other revenues and expenses`
- `Financial income`
- `Financial expenses`
- `Result before taxes`
- `Income tax expense`
- `Net Profit`

---

### Balance Sheet (ID: 430)

- **Localization**: MX
- **Parent / Root Report**: account.report(4,)

**Primary Sections / Account Groups:**

- `Assets`
- `Liabilities & Equity`
- `Equity (& Earnings)`

---

### Balance Sheet (ID: 431)

- **Localization**: MX
- **Parent / Root Report**: account.report(4,)

**Primary Sections / Account Groups:**

- `Assets`
- `Liabilities & Equity`
- `Equity (& Earnings)`

---

### Balance Sheet (ID: 432)

- **Localization**: MX
- **Parent / Root Report**: account.report(4,)

**Primary Sections / Account Groups:**

- `Assets`
- `Liabilities & Equity`
- `Equity (& Earnings)`

---

### Profit and Loss (ID: 433)

- **Localization**: MX
- **Parent / Root Report**: account.report(7,)

**Primary Sections / Account Groups:**

- `Gross Profit`
- `Net Operating Income`
- `Net Other Income`
- `Net Income`

---

### Balance sheet (ID: 434)

- **Localization**: MX
- **Parent / Root Report**: account.report(4,)

**Primary Sections / Account Groups:**

- `Assets`
- `Liabilities`
- `Equity`
- `Equity and Liabilities`

---

### Cash Flow Statement (ID: 5)

- **Localization**: MX
- **Parent / Root Report**: account.report()

**Primary Sections / Account Groups:**

- `Cash and cash equivalents, beginning of period`
- `Net increase in cash and cash equivalents`
- `Cash and cash equivalents, closing balance`

---

### Executive Summary (ID: 6)

- **Localization**: MX
- **Parent / Root Report**: account.report()

**Primary Sections / Account Groups:**

- `Cash`
- `Profitability`
- `Balance Sheet`
- `Performance`
- `Position`

---

### Profit and Loss (ID: 7)

- **Localization**: MX
- **Parent / Root Report**: account.report(7,)

**Primary Sections / Account Groups:**

- `Gross Profit`
- `Net Operating Income`
- `Net Other Income`
- `Net Income`

---

## Known Discrepancies

- **Report 418 (STAFF)**: Misconfigured on Odoo 19. It references `analytic_account_id` on the `account.move.line` model, which has been deprecated and removed in Odoo 19 in favor of analytic distribution plans. Attempting to calculate this report will result in a 422 validation error.
