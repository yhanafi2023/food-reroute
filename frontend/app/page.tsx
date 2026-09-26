import Link from "next/link";
import { Brand } from "@/components/Shell";

const STEPS = [
  {
    title: "Post what is available",
    text: "Quantity, unit, food type and a pickup deadline. FoodFlow estimates meals from the unit and the restaurant confirms the food was held safely.",
  },
  {
    title: "FoodFlow assigns a carrier and a recipient",
    text: "It checks each organization's receiving hours, food rules and capacity, then picks a volunteer or a simulated vehicle and records why.",
  },
  {
    title: "Track pickup and drop off with codes",
    text: "The carrier enters the restaurant's pickup code and the organization's drop-off code. Every handoff goes into an append-only record.",
  },
  {
    title: "Keep a record of every confirmed donation",
    text: "The organization confirms what it accepted. Only confirmed meals count, and the restaurant gets records for its tax preparer.",
  },
];

export default function Landing() {
  return (
    <>
      <a href="#main" className="skip">
        Skip to content
      </a>
      <header className="topbar">
        <Brand />
        <span style={{ flex: 1 }} />
        <Link href="/login" className="btn btn-ghost">
          Sign in
        </Link>
      </header>
      <main id="main" className="page">
        <section className="grid-2" style={{ alignItems: "center", paddingTop: "var(--s-6)" }}>
          <div className="stack">
            <span className="eyebrow">Food rescue near FIU, Miami-Dade</span>
            <h1>Move surplus food to local organizations with less coordination.</h1>
            <p className="text-lg" style={{ maxWidth: "58ch", color: "var(--ink-2)" }}>
              Post what is available, track pickup, and keep a record of every confirmed donation.
            </p>
            <div className="row">
              <Link href="/demo" className="btn btn-primary btn-lg">
                Try the donation demo
              </Link>
            </div>
            <p className="small muted">
              The demo uses fictional restaurants, organizations and volunteers. Autonomous vehicles and robots in it
              are simulated; FoodFlow does not control real vehicles.
            </p>
          </div>
          <ol className="panel transit" aria-label="How a donation moves">
            {["Restaurant posts", "Carrier assigned", "Pickup with code", "Drop off with code", "Organization confirms"].map((s, i) => (
              <li key={s} className="done">
                <span className="dot" aria-hidden="true">
                  {i + 1}
                </span>
                <span className="label">{s}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="stack" aria-labelledby="how">
          <h2 id="how">How it works</h2>
          <div className="grid-2">
            {STEPS.map((s) => (
              <div key={s.title} className="stack" style={{ gap: "var(--s-2)" }}>
                <h3>{s.title}</h3>
                <p style={{ color: "var(--ink-2)", maxWidth: "62ch" }}>{s.text}</p>
              </div>
            ))}
          </div>
        </section>
      </main>
    </>
  );
}
