# Why donating beats throwing food away

**FoodFlow provides records and estimates for your tax preparer. It is not tax advice.** FoodFlow never says a
donation is deductible and never computes a final allowable deduction; the business and its preparer decide. Every
page of every tax report carries: "Estimates and records for your tax preparer. Not tax advice."

All businesses, organizations and dollar amounts in the examples are **fictional** demo data, computed by the
code in `backend/app/tax/`.

## The enhanced deduction, in plain English

US federal law gives businesses an enhanced deduction for donating food inventory to qualified charities that use
it for the care of the ill, the needy or infants: Internal Revenue Code section 170(e)(3), with the food rules in
170(e)(3)(C). The Protecting Americans from Tax Hikes (PATH) Act of 2015 made it permanent and available to every
kind of business, not only C corporations (House Report 114-18:
https://www.congress.gov/committee-report/114th-congress/house-report/18).

For each item an organization accepted (rejected, expired or undelivered food counts as zero):

- If the fair market value (FMV) is at or below the cost basis, the deduction is the FMV. There is no enhancement.
- Otherwise the deduction is the smaller of: basis + half of (FMV - basis), or 2 x basis.
- A business that does not keep inventories may elect a basis of 25% of FMV.

### Why it beats the trash: the extra benefit

A business that keeps inventory already deducts what the food cost through cost of goods sold (COGS), whether the
food is sold, thrown away or donated. When it donates and takes the enhanced deduction, the donated food's basis
comes out of COGS. So the gain compared with throwing it away is the **extra benefit = enhanced deduction - basis**.
FoodFlow shows this only when it applies (inventory kept, no 25% election, FMV above basis); otherwise it says
"Ask your tax preparer how this interacts with your expensed costs."

Worked examples (the numbers the tests check, `backend/tests/test_tax.py`):

| Case | FMV | Basis | Enhanced deduction | Extra vs throwing away |
|---|---|---|---|---|
| Normal | $15 | $5 | min(5 + 5, 10) = **$10** | $10 - $5 = **$5** |
| 2 x basis cap | $20 | $2 | min(2 + 9, 4) = **$4** | $2 |
| FMV at or below basis | $4 | $5 | **$4** (the FMV) | not computed |
| 25% election | $20 | 25% of 20 = $5 | min(5 + 7.50, 10) = **$10** | not computed (ask your preparer) |

With a tax rate the business entered itself, estimated tax saved = extra benefit x rate. FoodFlow never assumes a
rate, a taxable income, or a hauling cost.

### Seed example (fictional, from a real run of the demo seed)

Casa Demo Cocina (fictional C corporation that keeps inventory and entered a 21% rate) donated 2 trays of rice and
black beans, valued from its own menu at $60 a tray with a 30% food cost, and a fictional shelter accepted all of it:
FMV $120, basis $36, enhanced deduction **$72**, extra benefit vs throwing it away **$36**, estimated tax saved
**$8** (from $7.56, displayed in whole dollars).

Demo Grill Norte's donations went to a fictional community fridge that is not a 501(c)(3), so its report lists them
as "not included in tax estimate: recipient not verified", and its headline says "No estimate yet" and why
instead of showing $0.

## The 15% cap and carryforward

Contributions under 170(e)(3) are limited to 15% of taxable income for C corporations, or 15% of aggregate net
income from the trades or businesses making the contributions for other entities. Any excess can generally be
carried forward up to 5 years. If a business enters an estimated taxable income, FoodFlow shows the cap, the
amount over it, and a carryforward note. It is a warning, never a computed allowable deduction.

## Who counts as a qualified donee

Only donations to organizations an admin verified count toward estimates: a 501(c)(3) that is not a private
non-operating foundation. The admin tool imports the IRS Exempt Organizations Business Master File extract
(https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf; the Florida
file is https://www.irs.gov/pub/irs-soi/eo_fl.csv, and the code meanings are in
https://www.irs.gov/pub/foia/ig/tege/eo-info.pdf), matches by EIN, and checks SUBSECTION 03 (501(c)(3)) and that
FOUNDATION is not 04 (private non-operating foundation). The admin sees the match and confirms. Manual checks use
the IRS Tax Exempt Organization Search: https://apps.irs.gov/app/eos/. Unverified organizations still receive food;
their donations are listed but left out of estimates.

The demo organizations are fictional and have made-up EINs with no IRS record; their verification is labeled
"FICTIONAL demo verification".

## Why the written acknowledgment matters

After receipt, FoodFlow prepares an acknowledgment for the receiving organization to sign, per delivery or as a
monthly statement (the organization's choice). It contains the organization's legal name, address and EIN; the
donor's name and address; the dates received; a description and quantity of the food accepted; and statements that
the organization is a 501(c)(3), that the food will be used solely for the care of the ill, the needy or infants and
not transferred for money, other property or services, and that to its knowledge the food meets Federal Food, Drug,
and Cosmetic Act requirements. The signer types a name and title; the signed PDF is stored unchanged and its SHA-256
hash is written to the audit log. Organizations get reminders after 3 and 7 days. The template says: "Have a tax
professional review this template before real use."

## Records the preparer will want

`GET /reports/donor-tax-summary?year=` (restaurant managers; JSON, CSV or PDF): one line per accepted item with
recipient and EIN, quantity, weight, FMV and how it was set, basis and how it was set, enhanced deduction, extra
benefit, and acknowledgment status; subtotals per recipient; the total basis of donated inventory ("cost to remove
from COGS; confirm with your preparer"); counts of items needing valuation and unsigned acknowledgments; and a note
that noncash contributions may require IRS Form 8283 (https://www.irs.gov/pub/irs-pdf/i8283.pdf), with the fields
that form typically asks for filled from FoodFlow's records.

## Try the numbers before joining

`POST /tools/donation-roi` needs no account. Example from the test run: average menu price $15, food cost one third,
20 meals a week for 50 weeks gives an enhanced deduction of **$10,000** and an extra deduction vs throwing it away of
**$5,000** a year. Tax saved (for example **$1,050** at a 21% rate the user entered) and avoided hauling (for example
**$120** at a $0.10 per lb hauling cost the user entered, 1.2 lbs per meal from Feeding America) appear only when the
user enters those numbers. Every input and formula is shown.

## State credits

Some states offer additional food donation credits, often limited to farmers. `backend/data/state_incentives.json`
is empty on purpose; an entry is shown only with a source URL and after a human verified it.

## Liability protection

The Bill Emerson Good Samaritan Food Donation Act (1996) protects good-faith donors of apparently wholesome food and
the nonprofits that distribute it from civil and criminal liability, except for gross negligence or intentional
misconduct. The Food Donation Improvement Act of 2022 (signed January 5, 2023) extended protection to donations made
directly to people in need and to food sold at a "Good Samaritan reduced price" that covers costs.
Sources: https://www.congress.gov/bill/117th-congress/senate-bill/5329/text ,
https://www.usda.gov/sites/default/files/documents/usda-good-samaritan-faqs.pdf .

## Compliance records (California SB 1383 template)

`GET /reports/sb1383?month=` builds the records CalRecycle lists for food donors (agreements, schedules, pounds per
month per organization, food types; https://calrecycle.ca.gov/organics/slcp/foodrecovery/donors), labeled "Verify
requirements with your local jurisdiction." The demo city is Miami, where SB 1383 does not apply.
