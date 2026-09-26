// The donation demo, click for click, against the real API (fictional seed, demo clock at Friday 7 PM Miami).
// Done when it passes 3 runs in a row: npm run test:3x
import { expect, test, type Browser, type Page } from "@playwright/test";

const API = "http://localhost:8000";
// Demo accounts accept this code only while the server runs with DEMO_MODE=true (backend/app/seed.py).
const DEMO_CODE = "246810";

async function signIn(browser: Browser, email: string, next: string, viewport = { width: 1440, height: 1000 }): Promise<Page> {
  const page = await (await browser.newContext({ viewport })).newPage();
  await page.goto(`/login?email=${encodeURIComponent(email)}&next=${next}`);
  await page.getByRole("button", { name: "Email me a code" }).click();
  await page.getByLabel("6 digit code").fill(DEMO_CODE);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${next}$`));
  return page;
}

test.beforeEach(async ({ request }) => {
  await request.post(`${API}/auth/request-code`, { data: { email: "admin@foodflow-demo.example.com" } });
  const verify = await request.post(`${API}/auth/verify`, { data: { email: "admin@foodflow-demo.example.com", code: DEMO_CODE } });
  expect(verify.ok()).toBeTruthy();
  const { token } = await verify.json();
  const reset = await request.post(`${API}/demo/reset`, { headers: { Authorization: `Bearer ${token}` } });
  expect(reset.ok()).toBeTruthy();
});

test("donation: post, match, pickup with code, drop off with code, receipt", async ({ page, browser }) => {
  // Landing
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Move surplus food to local organizations with less coordination." })).toBeVisible();
  await page.getByRole("link", { name: "Try the donation demo" }).click();
  await expect(page).toHaveURL(/\/demo$/);
  await expect(page.getByRole("link", { name: "Sign in as restaurant" })).toBeVisible();

  // Restaurant posts 3 trays of hot food. Timed from the form being ready to the post being confirmed.
  const restaurant = await signIn(browser, "staff@casa-demo.example.com", "/restaurant");
  await expect(restaurant.getByRole("heading", { name: "Donate surplus food" })).toBeVisible();
  const t0 = Date.now();
  await restaurant.getByRole("group", { name: "Unit" }).getByRole("button", { name: "Trays" }).click();
  await restaurant.getByRole("group", { name: "Food type" }).getByRole("button", { name: "Hot" }).click();
  await restaurant.getByRole("checkbox").check();
  await restaurant.getByRole("button", { name: "Post donation" }).click();
  await expect(restaurant.getByRole("status").filter({ hasText: "Posted." })).toBeVisible();
  const postingMs = Date.now() - t0;
  test.info().annotations.push({ type: "restaurant posting time (ms)", description: String(postingMs) });
  console.log(`restaurant posting time: ${postingMs} ms (form ready to post confirmed, scripted clicks)`);

  const card = restaurant.locator("article").filter({ hasText: "3 trays" }).first();
  await expect(card.getByTestId("rescue-status")).toHaveText("Carrier assigned");
  await expect(card.getByText("Marcus")).toBeVisible();
  const pickupCode = (await card.getByTestId("pickup-code").textContent())!.trim();
  expect(pickupCode).toMatch(/^\d{4,8}$/);

  // Volunteer accepts and picks up with the restaurant's code
  const volunteer = await signIn(browser, "marcus@volunteer-demo.example.com", "/volunteer");
  const offer = volunteer.locator("article").filter({ hasText: "New rescue offer" }).first();
  await expect(offer).toBeVisible();
  await offer.getByRole("button", { name: "Accept" }).click();
  await expect(card.getByTestId("rescue-status")).toHaveText("On the way to pick up");

  // A wrong code is refused (and audited server-side)
  await volunteer.getByLabel("Pickup code").fill("0000");
  await volunteer.getByRole("button", { name: "Confirm pickup" }).click();
  await expect(volunteer.getByRole("alert").filter({ hasText: "pickup code does not match" })).toBeVisible();
  await volunteer.getByLabel("Pickup code").fill(pickupCode);
  await volunteer.getByRole("button", { name: "Confirm pickup" }).click();
  await expect(card.getByTestId("rescue-status")).toHaveText("On the way to drop off");

  // The shelter sees it coming with its drop-off code
  const org = await signIn(browser, "staff@shelter-demo.example.com", "/org");
  const incoming = org.locator("article").filter({ hasText: "Casa Demo Cocina" }).filter({ has: org.getByTestId("dropoff-code") }).first();
  const dropoffCode = (await incoming.getByTestId("dropoff-code").textContent())!.trim();

  await volunteer.getByLabel("Drop-off code").fill(dropoffCode);
  await volunteer.getByRole("button", { name: "Confirm drop off" }).click();
  await expect(volunteer.getByText("Delivered. The organization will confirm what it accepted.")).toBeVisible();
  await expect(card.getByTestId("rescue-status")).toHaveText("Delivered, waiting for receipt");

  // The shelter confirms receipt; its records need temperature and the receiver's name
  const toConfirm = org.locator("article").filter({ hasText: "Casa Demo Cocina" }).filter({ has: org.getByRole("button", { name: "Confirm receipt" }) }).first();
  await toConfirm.getByLabel(/Temperature at receipt/).fill("145");
  await toConfirm.getByLabel(/Received by/).fill("Tomas");
  await toConfirm.getByRole("button", { name: "Confirm receipt" }).click();
  await expect(org.getByText(/36 of 36 meals accepted/).first()).toBeVisible();

  // The restaurant sees the confirmed donation
  await restaurant.getByText(/^Recent/).click();
  await expect(restaurant.locator("article").filter({ hasText: "3 trays" }).first().getByTestId("rescue-status")).toHaveText("Received");
});

test("mobile: restaurant form fits 375px with 44px targets", async ({ browser }) => {
  const page = await signIn(browser, "staff@casa-demo.example.com", "/restaurant", { width: 375, height: 800 });
  const post = page.getByRole("button", { name: "Post donation" });
  await expect(post).toBeVisible();
  const box = await post.boundingBox();
  expect(box!.height).toBeGreaterThanOrEqual(44);
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollW).toBeLessThanOrEqual(375);
});
