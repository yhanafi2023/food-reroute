// New features: mobile navigation, simulation stop/restart, the prospect directory and seven-day log.
import { expect, test, type Browser } from "@playwright/test";

const API = "http://localhost:8000";

async function adminPage(browser: Browser, viewport = { width: 1440, height: 1000 }) {
  const page = await (await browser.newContext({ viewport })).newPage();
  await page.goto("/login");
  await page.getByRole("button", { name: "Demo login as Admin" }).click();
  await expect(page).toHaveURL(/\/admin\/dashboard/);
  return page;
}

test.beforeEach(async ({ request }) => {
  const { token } = await (await request.post(`${API}/auth/login`, { data: { email: "admin@demo.com", password: "demo1234" } })).json();
  expect((await request.post(`${API}/demo/reset`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
});

test("mobile navigation opens, navigates and closes", async ({ browser }) => {
  const page = await adminPage(browser, { width: 375, height: 800 });
  const openMenu = page.getByRole("button", { name: "Open menu" });
  await expect(openMenu).toBeVisible();
  await openMenu.click();
  const menu = page.getByRole("dialog", { name: "Menu" });
  await expect(menu).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await openMenu.click();
  await menu.getByRole("link", { name: "Prospects" }).click();
  await expect(page).toHaveURL(/\/admin\/prospects/);
  await expect(page.getByRole("dialog", { name: "Menu" })).toHaveCount(0);
  const scroll = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(scroll).toBeLessThanOrEqual(0);
});

test("simulation can be stopped and restarted", async ({ browser }) => {
  const page = await adminPage(browser);
  await page.getByRole("button", { name: "Simulate Tonight" }).click();
  await expect(page.getByText(/ABC Restaurant posts 50 meals/)).toBeVisible();
  await page.getByRole("button", { name: "Stop simulation" }).click();
  await expect(page.getByText(/Stopped at/)).toBeVisible();
  const clockAtStop = await page.getByText(/^\d{1,2}:\d{2} PM$/).first().textContent();
  await page.waitForTimeout(1500);
  expect(await page.getByText(/^\d{1,2}:\d{2} PM$/).first().textContent()).toBe(clockAtStop); // really stopped
  await page.getByRole("button", { name: "Restart simulation" }).click();
  await expect(page.getByRole("button", { name: "Stop simulation" })).toBeVisible();
  await expect(page.getByText(/ABC Restaurant posts 50 meals/)).toBeVisible();
  await page.getByRole("button", { name: "Stop simulation" }).click();
  await page.getByRole("button", { name: "Back to live network" }).click();
  await expect(page.getByRole("button", { name: "Simulate Tonight" })).toBeVisible();
  await expect(page.getByText("Driver ETA model")).toBeVisible();
  await expect(page.getByText("Real road-network data")).toBeVisible();
});

test("prospect directory: filter, sources, seven-day log, ranking", async ({ browser }) => {
  const page = await adminPage(browser);
  await page.goto("/admin/prospects");
  await expect(page.getByText(/None yet\. No researched business has published a measured surplus quantity/)).toBeVisible();

  await page.getByLabel("Neighborhood").selectOption("Doral");
  await expect(page.getByRole("button", { name: /MIA Bakery Gourmet/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Macchialina/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await page.getByRole("searchbox").fill("macchia");
  await page.getByRole("button", { name: /Macchialina/ }).click();
  const detail = page.getByRole("article", { name: "Macchialina" });
  await expect(detail.getByText("Researched prospect · not enrolled")).toBeVisible();
  await expect(detail.getByRole("link", { name: /Give Miami Day/ })).toHaveAttribute("href", /givemiamiday\.org/);
  await expect(detail.getByText(/no quantity published/)).toBeVisible();

  await page.getByRole("button", { name: "Clear filters" }).click();
  await page.getByRole("button", { name: /Sergio's \(FIU location\)/ }).click();
  const log = page.getByRole("article", { name: "Sergio's (FIU location)" });
  for (let i = 7; i >= 1; i--) {
    const d = new Date(Date.now() - i * 86400000);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    await log.getByLabel("Date").fill(iso);
    await log.getByLabel("Surplus meals").fill("10");
    await log.getByRole("button", { name: "Save this day" }).click();
    await expect(log.getByText(`Saved ${iso}.`)).toBeVisible();
  }
  await expect(log.getByText("7 of 7 days logged")).toBeVisible();
  const ranking = page.getByRole("region", { name: "Ranked rescue opportunities" });
  await expect(ranking.getByRole("cell", { name: /Sergio's \(FIU location\)/ })).toBeVisible();
  await expect(ranking.getByText(/Self-reported seven-day kitchen surplus log/)).toBeVisible();
});
