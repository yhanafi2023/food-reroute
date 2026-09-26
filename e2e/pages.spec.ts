// Pages carried over from main (a073982 and earlier) onto the new shell, plus old-path redirects.
import { expect, test, type Browser, type Page } from "@playwright/test";

const DEMO_CODE = "246810"; // demo accounts only, DEMO_MODE only (backend/app/seed.py)

async function signIn(browser: Browser, email: string, next: string): Promise<Page> {
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
  await page.goto(`/login?email=${encodeURIComponent(email)}&next=${next}`);
  await page.getByRole("button", { name: "Email me a code" }).click();
  await page.getByLabel("6 digit code").fill(DEMO_CODE);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${next}$`));
  return page;
}

test("old dashboard paths redirect to the new workspaces", async ({ page }) => {
  for (const [from, to] of [
    ["/admin/dashboard", "/coordinator"],
    ["/restaurant/dashboard", "/restaurant"],
    ["/organization/dashboard", "/org"],
    ["/volunteer/dashboard", "/volunteer"],
    ["/driver/dashboard", "/volunteer"],
  ]) {
    await page.goto(from);
    await expect(page).toHaveURL(new RegExp(`${to}`));
  }
});

test("sign-up page renders with the three account types", async ({ page }) => {
  await page.goto("/signup");
  await expect(page.getByRole("heading", { name: "Create an account" })).toBeVisible();
  for (const t of ["Restaurant", "Organization", "Volunteer"]) await expect(page.getByRole("radio", { name: t })).toBeVisible();
});

test("organization onboarding loads its three questions", async ({ browser }) => {
  const org = await signIn(browser, "manager@shelter-demo.example.com", "/org");
  await org.getByRole("navigation", { name: "Workspace" }).getByRole("link", { name: "Onboarding" }).click();
  await expect(org.getByRole("heading", { name: /Q1/ })).toBeVisible();
  await expect(org.getByRole("heading", { name: /Q3/ })).toBeVisible();
});

test("restaurant surplus log and coordinator prospects load", async ({ browser }) => {
  const restaurant = await signIn(browser, "manager@casa-demo.example.com", "/restaurant");
  await restaurant.getByRole("navigation", { name: "Workspace" }).getByRole("link", { name: "Surplus log" }).click();
  await expect(restaurant.getByRole("heading", { name: "Seven-day surplus log" })).toBeVisible();
  const admin = await signIn(browser, "admin@foodflow-demo.example.com", "/coordinator");
  await admin.getByRole("navigation", { name: "Workspace" }).getByRole("link", { name: "Prospects" }).click();
  await expect(admin.getByRole("heading", { name: "Miami surplus prospects" })).toBeVisible();
  await expect(admin.getByText("Macchialina").first()).toBeVisible();
});
