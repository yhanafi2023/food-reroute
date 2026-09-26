// Screenshots for docs/screenshots: coordinator, restaurant and volunteer pages at 1440px and 375px,
// dark (default) and light. Run on its own: npx playwright test screenshots.spec.ts
import { expect, test, type Browser, type Page } from "@playwright/test";

const API = "http://localhost:8000";
const DEMO_CODE = "246810";
const OUT = "../docs/screenshots";

async function signIn(browser: Browser, email: string, next: string, viewport: { width: number; height: number }, theme: "dark" | "light"): Promise<Page> {
  const context = await browser.newContext({ viewport });
  if (theme === "light") await context.addInitScript(() => localStorage.setItem("foodflow_theme", "light"));
  const page = await context.newPage();
  await page.goto(`/login?email=${encodeURIComponent(email)}&next=${next}`);
  await page.getByRole("button", { name: "Email me a code" }).click();
  await page.getByLabel("6 digit code").fill(DEMO_CODE);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${next}$`));
  return page;
}

async function settle(page: Page) {
  await page.locator(".leaflet-tile-loaded").first().waitFor({ timeout: 20_000 }).catch(() => {});
  await page.waitForTimeout(1500);
}

test("screenshots", async ({ browser, request }) => {
  test.setTimeout(300_000);
  await request.post(`${API}/auth/request-code`, { data: { email: "admin@foodflow-demo.example.com" } });
  const { token } = await (await request.post(`${API}/auth/verify`, { data: { email: "admin@foodflow-demo.example.com", code: DEMO_CODE } })).json();
  expect((await request.post(`${API}/demo/reset`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();

  // One live donation, accepted by the volunteer, so every page has a route on its map.
  const setup = await signIn(browser, "staff@casa-demo.example.com", "/restaurant", { width: 1440, height: 1000 }, "dark");
  await setup.getByRole("checkbox").check();
  await setup.getByRole("button", { name: "Post donation" }).click();
  await expect(setup.getByText(/Match found/)).toBeVisible();
  const vol = await signIn(browser, "marcus@volunteer-demo.example.com", "/volunteer", { width: 1440, height: 1000 }, "dark");
  await vol.getByRole("button", { name: "Accept" }).click();
  await expect(vol.getByLabel("Pickup code")).toBeVisible();

  for (const theme of ["dark", "light"] as const) {
    for (const [w, h, tag] of [[1440, 1000, "desktop"], [375, 812, "375"]] as const) {
      for (const [email, path, name] of [
        ["admin@foodflow-demo.example.com", "/coordinator", "coordinator"],
        ["staff@casa-demo.example.com", "/restaurant", "restaurant"],
        ["marcus@volunteer-demo.example.com", "/volunteer", "volunteer"],
      ] as const) {
        const page = await signIn(browser, email, path, { width: w, height: h }, theme);
        await settle(page);
        await page.screenshot({ path: `${OUT}/${name}-${tag}-${theme}.png`, fullPage: true });
        await page.context().close();
      }
    }
  }
});
