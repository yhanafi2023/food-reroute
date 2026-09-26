# Why every participant benefits

**Not legal or tax advice.** Everything below is general information with sources, and FoodFlow's numbers are
estimates and records for a donor's own professionals to review.

## Restaurants

### Enhanced tax deduction for donated food

US federal law gives businesses an enhanced deduction for donating food inventory to qualified charities that use
it for the ill, the needy or infants (Internal Revenue Code section 170(e)(3), with the food-specific rules in
170(e)(3)(C)). The PATH Act of 2015 made the enhanced deduction permanent and available to any business, not only
C corporations.

In plain English, per donation:

- The deduction is the **smaller** of (a) the food's cost basis plus half of its "appreciation" (fair market value
  minus basis) and (b) twice the basis.
- A business that is not required to keep inventories may elect to treat the basis as **25% of fair market value**.
- The total enhanced deduction for the year is limited to 15% of taxable income (for non-C corporations, 15% of
  aggregate net income from the businesses that donated); anything above carries forward up to 5 years.

What FoodFlow does: each received drop off becomes a line with FMV and basis (from the post, defaulting to the
restaurant's settings), the estimate `min(basis + 0.5 x (FMV - basis), 2 x basis)`, and the 25% election when the
restaurant chose it. Only donations received by organizations whose 501(c)(3) status and EIN an admin has verified
count toward the estimate. `GET /reports/donor-tax-summary?year=` returns JSON, CSV or PDF, labeled
"Estimate for your tax preparer. Not tax advice." Math tests: `backend/tests/test_records.py::test_deduction_math`.

Source for the rules summarized above: House Report 114-18 (Fighting Hunger Incentive Act of 2015),
https://www.congress.gov/committee-report/114th-congress/house-report/18 . Verify current rules with a tax
professional.

### Acknowledgment documents

On receipt, FoodFlow generates an acknowledgment for the receiving org to e-sign: donor, date, food description and
quantity, the org's legal name and EIN, and statements that the org will use the food for the care of the ill,
needy or infants, will not sell or transfer it for money, and that the food meets Federal Food, Drug, and Cosmetic
Act requirements. The template is marked "have a tax professional review before real use". The org issues any
official acknowledgment; FoodFlow only prepares the record.

### Liability protection

The Bill Emerson Good Samaritan Food Donation Act (1996) protects good-faith donors of apparently wholesome food
and the nonprofits that distribute it from civil and criminal liability, except for gross negligence or intentional
misconduct. The Food Donation Improvement Act of 2022 (signed January 5, 2023) extended that protection to
donations made directly to people in need and to food sold at a "Good Samaritan reduced price" covering costs.
Sources: https://www.congress.gov/bill/117th-congress/senate-bill/5329/text ,
https://www.usda.gov/sites/default/files/documents/usda-good-samaritan-faqs.pdf .

### Compliance records (first template: California SB 1383)

California's SB 1383 requires commercial edible food generators to keep records of their food recovery: written
agreements with recovery organizations, donation schedules, pounds donated per month per organization, and the types
of food each receives (CalRecycle: https://calrecycle.ca.gov/organics/slcp/foodrecovery/donors). FoodFlow builds
that monthly report from its own records (`GET /reports/sb1383?month=`) with uploaded agreements, labeled
"Verify requirements with your local jurisdiction." FoodFlow's demo city is Miami, where SB 1383 does not apply;
the template shows how a jurisdiction-specific report plugs in.

### Dashboard

Meals donated, pounds diverted (meals x 1.2, Feeding America's standard,
https://www.feedingamerica.org/ways-to-give/faq/about-our-claims), the estimated deduction (managers only),
acknowledgment status, and avoided disposal cost **only** if the restaurant enters its own hauling cost (FoodFlow
never assumes one). An opt-in public "Food Rescue Partner" page is off by default.

## Receiving organizations

Reliable deliveries that respect their own answers (hours, cutoff, hot food, storage, dietary and allergen rules,
curbside), and the records they said they need: reports built from exactly their chosen fields at their chosen
frequency, missing fields flagged, and a prompt at the next receipt.

## Volunteers

Offers only when their equipment fits the food, one step at a time, and an exportable service-hours log.

## People served

Food reaches organizations that can take it safely, when they are open, and within the hot-food time they set.
They never need the app.
