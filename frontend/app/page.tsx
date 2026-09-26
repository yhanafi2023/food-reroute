import Link from "next/link";
import { TopNav } from "@/components/AppShell";
import FlowLine from "@/components/FlowLine";
import Icon, { IconTile, type IconName } from "@/components/Icon";
import LandingMap from "@/components/LandingMap";

const STEPS: { icon: IconName; title: string; text: string }[] = [
  { icon: "food-box", title: "A restaurant posts surplus food", text: "Meals, weight, pickup deadline and a food safety check. It takes under a minute." },
  { icon: "route", title: "FoodFlow finds the best match", text: "It scores the nearest available drivers against open needs by distance, ETA, urgency, demand fit and priority, and shows why." },
  { icon: "van", title: "One pickup, several drop offs", text: "A 50 meal donation can go 30 to a food bank and 20 to a shelter, so no food is left over and no need is overfilled." },
  { icon: "food-safe", title: "Organizations confirm receipt", text: "Each drop off is confirmed by the organization that received it, and only then counts toward impact." },
];

const USERS: { icon: IconName; who: string; what: string }[] = [
  { icon: "restaurant", who: "Restaurants", what: "post surplus in under a minute." },
  { icon: "driver", who: "Volunteer drivers", what: "get one clear offer and one next step at a time." },
  { icon: "community-org", who: "Organizations", what: "post needs and confirm what arrives." },
  { icon: "stats", who: "Coordinators", what: "watch the whole network live." },
];

export default function Landing() {
  return (
    <div className="min-h-screen">
      <TopNav />

      <main>
        <section className="mx-auto flex max-w-7xl flex-col gap-8 px-4 pb-12 pt-10">
          <div className="mx-auto flex max-w-3xl flex-col items-center gap-5 text-center">
            <span className="eyebrow">Real time food rescue · Miami</span>
            <h1>Food shouldn&apos;t go to waste when people need it.</h1>
            <p className="max-w-[62ch] text-lg text-ink-2">
              Restaurants have safe surplus food tonight. Food banks, shelters and school pantries need it tonight.
              FoodFlow matches the two, splits each donation across the organizations that need it, and routes a
              volunteer driver before the food expires.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <Link href="/signup" className="btn btn-primary btn-lg">Get Started</Link>
              <a href="#how" className="btn btn-ghost btn-lg">See How It Works</a>
            </div>
          </div>

          <div className="relative" aria-label="Example map of food moving toward high need areas in Miami" role="figure">
            <LandingMap />
            <aside className="panel landing-match mt-4 flex flex-col gap-4 lg:absolute lg:right-4 lg:top-4 lg:z-[1000] lg:mt-0 lg:w-[340px] lg:bg-panel/95 lg:backdrop-blur"
              aria-label="Example match">
              <div className="flex items-center justify-between">
                <span className="eyebrow">Example match</span>
                <span className="chip">demo data</span>
              </div>
              <ol className="transit">
                <li className="done"><span className="dot">P</span><span className="label flex items-center gap-2"><Icon name="restaurant" size={22} />ABC Restaurant posts 50 meals</span></li>
                <li className="done"><span className="dot">D</span><span className="label flex items-center gap-2"><Icon name="car" size={22} />Marcus, 0.6 mi away, is matched</span></li>
                <li className="now"><span className="dot">1</span><span className="label flex items-center justify-between gap-2">Hope Shelter <span className="chip">20 meals</span></span></li>
                <li className="now"><span className="dot">2</span><span className="label flex items-center justify-between gap-2">Community Food Bank <span className="chip">30 meals</span></span></li>
              </ol>
              <p className="text-sm text-ink-3">Routes lean toward the areas with the highest need. Every match shows its reasons and the options it beat.</p>
            </aside>
          </div>
        </section>

        <section className="border-y border-line bg-panel" aria-label="How food moves">
          <div className="mx-auto max-w-7xl px-4 py-10">
            <FlowLine />
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
                <IconTile name={s.icon} size={48} />
                <div className="flex flex-col gap-1">
                  <span className="mono text-sm font-bold text-accent">{String(i + 1).padStart(2, "0")}</span>
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
              <IconTile name="community" size={56} />
              <span className="eyebrow">Who it serves</span>
              <h2>Low income families, students, workers and seniors.</h2>
              <p className="max-w-[58ch] text-ink-2">
                People receiving food never need this app or a smartphone. Community organizations are the bridge:
                they post what they need and receive the food.
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <span className="eyebrow">Who uses it</span>
              <ul className="flex flex-col gap-3 text-lg">
                {USERS.map((u) => (
                  <li key={u.who} className="flex items-center gap-3">
                    <IconTile name={u.icon} size={40} />
                    <span><strong>{u.who}</strong> {u.what}</span>
                  </li>
                ))}
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
