import Link from "next/link";
import { Brand } from "@/components/AppShell";

const FLOW = [
  { n: "R", title: "Restaurant", text: "Posts safe surplus food" },
  { n: "FF", title: "FoodFlow", text: "Matches, splits, routes", hub: true },
  { n: "D", title: "Driver", text: "Volunteer picks it up" },
  { n: "O", title: "Organization", text: "Food bank, shelter, pantry" },
  { n: "C", title: "Community", text: "Families, students, seniors" },
];

const STEPS = [
  { title: "A restaurant posts surplus food", text: "Meals, weight, pickup deadline and a food safety check. It takes under a minute." },
  { title: "FoodFlow finds the best match", text: "It scores the nearest available drivers against open needs by distance, ETA, urgency, demand fit and priority, and shows why." },
  { title: "One pickup, several drop offs", text: "A 50 meal donation can go 30 to a food bank and 20 to a shelter, so no food is left over and no need is overfilled." },
  { title: "Organizations confirm receipt", text: "Each drop off is confirmed by the organization that received it, and only then counts toward impact." },
];

export default function Landing() {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4">
        <Brand />
        <nav className="flex items-center gap-2" aria-label="Main">
          <Link href="/impact" className="btn btn-ghost">Impact</Link>
          <Link href="/login" className="btn btn-primary">Log in</Link>
        </nav>
      </header>

      <main>
        <section className="mx-auto grid max-w-7xl items-center gap-8 px-4 pb-12 pt-8 lg:grid-cols-[1.2fr_1fr]">
          <div className="flex flex-col gap-6">
            <span className="eyebrow">Real time food rescue · Miami</span>
            <h1>Food shouldn&apos;t go to waste when people need it.</h1>
            <p className="max-w-[58ch] text-lg text-ink-2">
              Restaurants have safe surplus food tonight. Food banks, shelters and school pantries need it tonight.
              FoodFlow matches the two, splits each donation across the organizations that need it, and routes a
              volunteer driver before the food expires.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link href="/signup" className="btn btn-primary btn-lg">Get Started</Link>
              <a href="#how" className="btn btn-ghost btn-lg">See How It Works</a>
            </div>
          </div>

          <aside className="panel flex flex-col gap-4" aria-label="Example match">
            <div className="flex items-center justify-between">
              <span className="eyebrow">Example match</span>
              <span className="chip">demo data</span>
            </div>
            <ol className="transit">
              <li className="done"><span className="dot">P</span><span className="label">ABC Restaurant posts 50 meals, pickup before 10 PM</span></li>
              <li className="done"><span className="dot">D</span><span className="label">Marcus, 0.6 mi away, is matched</span></li>
              <li className="now"><span className="dot">1</span><span className="label flex justify-between gap-2">Community Food Bank <span className="chip">30 meals</span></span></li>
              <li className="now"><span className="dot">2</span><span className="label flex justify-between gap-2">Hope Shelter <span className="chip">20 meals</span></span></li>
            </ol>
            <p className="text-sm text-ink-3">Every match shows its reasons and the options it beat.</p>
          </aside>
        </section>

        <section className="border-y border-line bg-panel" aria-label="How food moves">
          <div className="mx-auto max-w-7xl px-4 py-8">
            <div className="flow">
              {FLOW.map((f) => (
                <div key={f.title}>
                  <span className={`stop ${f.hub ? "hub" : ""}`} aria-hidden>{f.n}</span>
                  <div className="flex flex-col">
                    <strong>{f.title}</strong>
                    <span className="text-sm text-ink-2">{f.text}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="how" className="mx-auto grid max-w-7xl gap-8 px-4 py-12 lg:grid-cols-[1fr_1.5fr]">
          <div className="flex flex-col gap-3">
            <span className="eyebrow">How it works</span>
            <h2>There is food available right now. Who needs it, and how does it get there in time?</h2>
          </div>
          <ol className="flex flex-col gap-6">
            {STEPS.map((s, i) => (
              <li key={s.title} className="grid grid-cols-[48px_1fr] gap-4">
                <span className="mono text-2xl font-bold text-accent">{String(i + 1).padStart(2, "0")}</span>
                <div className="flex flex-col gap-1">
                  <h3>{s.title}</h3>
                  <p className="max-w-[62ch] text-ink-2">{s.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="bg-wash">
          <div className="mx-auto grid max-w-7xl gap-8 px-4 py-12 md:grid-cols-2">
            <div className="flex flex-col gap-3">
              <span className="eyebrow">Who it serves</span>
              <h2>Low income families, students, workers and seniors.</h2>
              <p className="max-w-[58ch] text-ink-2">
                People receiving food never need this app or a smartphone. Community organizations are the bridge:
                they post what they need and receive the food.
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <span className="eyebrow">Who uses it</span>
              <ul className="flex flex-col gap-2 text-lg">
                <li><strong>Restaurants</strong> post surplus in under a minute.</li>
                <li><strong>Volunteer drivers</strong> get one clear offer and one next step at a time.</li>
                <li><strong>Organizations</strong> post needs and confirm what arrives.</li>
                <li><strong>Coordinators</strong> watch the whole network live.</li>
              </ul>
              <div className="pt-2"><Link href="/login" className="btn btn-primary">Try the demo</Link></div>
            </div>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-6 text-sm text-ink-3">
        <span>FoodFlow · Good Food. Greater Impact. · ShellHacks 2026</span>
        <Link href="/qr" className="underline">QR code</Link>
      </footer>
    </div>
  );
}
