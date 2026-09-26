// The 2 minute demo from DEMO.md, click for click. The demo is "done" when this passes 3 times in a row:
//   npm run test:3x
import { expect, test, type Browser, type Page } from "@playwright/test";

const API = "http://localhost:8000";

async function asRole(browser: Browser, button: string): Promise<Page> {
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
  await page.goto("/login");
  await page.getByRole("button", { name: `Demo login as ${button}` }).click();
  return page;
}

async function loginWithForm(browser: Browser, email: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("demo1234");
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  return page;
}

test.beforeEach(async ({ request }) => {
  const login = await request.post(`${API}/auth/login`, { data: { email: "admin@demo.com", password: "demo1234" } });
  const { token } = await login.json();
  const reset = await request.post(`${API}/demo/reset`, { headers: { Authorization: `Bearer ${token}` } });
  expect(reset.ok()).toBeTruthy();
});

test("FoodFlow demo click path", async ({ page, browser }) => {
  // 1. Landing page
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Food shouldn't go to waste when people need it." })).toBeVisible();

  // 2. Restaurant posts 50 meals
  const restaurant = await asRole(browser, "Restaurant");
  await expect(restaurant).toHaveURL(/\/restaurant\/dashboard/);
  await restaurant.getByRole("checkbox").check();
  await restaurant.getByRole("button", { name: "Find a match" }).click();
  await expect(restaurant.getByText("Finding the most efficient rescue match...")).toBeVisible();

  // 3. Match found: Marcus, 30 to the food bank and 20 to the shelter, with "Why this match?"
  const match = restaurant.getByRole("region", { name: "Match found" });
  await expect(match.getByText("Marcus").first()).toBeVisible();
  await expect(match.getByRole("list", { name: "Stops" })).toContainText("Community Food Bank");
  await expect(match.getByRole("list", { name: "Stops" })).toContainText("Hope Shelter");
  await expect(restaurant.getByRole("heading", { name: "Why this match?" })).toBeVisible();
  await expect(restaurant.getByText("CHOSEN")).toBeVisible();

  // 4. Driver accepts and steps through every status; the restaurant sees a live ML ETA to its door
  const driver = await asRole(browser, "Driver");
  await expect(driver.getByText("New food rescue")).toBeVisible();
  await expect(driver.getByText("50 meals from ABC Restaurant")).toBeVisible();
  await driver.getByRole("button", { name: "Accept" }).click();
  await expect(restaurant.getByText("Driver to pickup")).toBeVisible();
  await expect(restaurant.getByText(/About \d+ min/)).toBeVisible();
  for (const step of ["I arrived at the restaurant", "I picked up the food", "Start delivering", "Mark delivered"]) {
    await driver.getByRole("button", { name: step }).click();
    await expect(driver.getByRole("button", { name: step })).toHaveCount(0);
  }
  await expect(driver.getByText("awaiting confirmation")).toBeVisible();

  // 5. The restaurant's card updated live (polling, no refresh)
  await expect(restaurant.getByRole("list", { name: "Delivery status" })).toBeVisible();

  // 6. Both organizations confirm their drop off
  const org = await asRole(browser, "Organization");
  await expect(org.getByText("30 meals incoming")).toBeVisible();
  await org.getByRole("button", { name: "Confirm Receipt of 30 meals" }).click();
  await expect(org.getByText("Confirmed 30 meals. Thank you!")).toBeVisible();
  const shelter = await loginWithForm(browser, "shelter@demo.com");
  await shelter.getByRole("button", { name: "Confirm Receipt of 20 meals" }).click();
  await expect(shelter.getByText("Confirmed 20 meals. Thank you!")).toBeVisible();

  // 7. The public impact page counts only real deliveries: the demo accounts are fictional, so it stays at 0
  await page.goto("/impact");
  await expect(page.getByText(/Only real deliveries confirmed by a receiving organization count here/)).toBeVisible();
  await expect(page.getByText("Meals rescued (real, confirmed)")).toBeVisible();

  // 8. Admin runs Simulate Tonight
  const admin = await asRole(browser, "Admin");
  await expect(admin.getByRole("heading", { name: "Network" })).toBeVisible();
  await expect(admin.getByText("Driver ETA model")).toBeVisible();
  await expect(admin.getByText("Needs real data")).toBeVisible(); // no synthetic surplus forecast is shown
  await admin.getByRole("button", { name: "Simulate Tonight" }).click();
  await expect(admin.getByText(/ABC Restaurant posts 50 meals/)).toBeVisible();
  await expect(admin.getByText(/Marcus matched: 30 to Community Food Bank, 20 to Hope Shelter|Marcus matched: 20 to Hope Shelter, 30 to Community Food Bank/)).toBeVisible();
  await expect(admin.getByText(/Delivered 50 meals/)).toBeVisible({ timeout: 20_000 });
  await expect(admin.getByRole("button", { name: "Back to live network" })).toBeVisible({ timeout: 70_000 });
});
