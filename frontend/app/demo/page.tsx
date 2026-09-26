import Link from "next/link";
import { Shell } from "@/components/Shell";

// Fictional demo accounts (backend/app/seed.py). They sign in with the normal email code, like everyone else.
const PERSONAS = [
  { title: "Restaurant", email: "staff@casa-demo.example.com", who: "Rosa, closing cook at Casa Demo Cocina", does: "Post tonight's surplus and read the pickup code to the driver.", next: "/restaurant" },
  { title: "Volunteer", email: "marcus@volunteer-demo.example.com", who: "Marcus, volunteer driver", does: "Accept the run, enter the pickup code, then the drop-off code.", next: "/volunteer" },
  { title: "Receiving organization", email: "staff@shelter-demo.example.com", who: "Tomas, staff at Demo Night Shelter", does: "Give the driver the drop-off code and confirm what you accepted.", next: "/org" },
  { title: "Coordinator", email: "admin@foodflow-demo.example.com", who: "FoodFlow coordinator", does: "Watch every rescue and see why each assignment was made.", next: "/coordinator" },
];

export default function DemoPicker() {
  return (
    <Shell>
      <div className="stack">
        <h1>Try the donation demo</h1>
        <p style={{ maxWidth: "62ch", color: "var(--ink-2)" }}>
          Pick a role and sign in with the emailed code. Open another role in a second window to watch the same donation
          from both sides. Every business, organization and person here is fictional.
        </p>
      </div>
      <div className="grid-2">
        {PERSONAS.map((p) => (
          <div key={p.email} className="panel stack">
            <h2>{p.title}</h2>
            <p className="muted">{p.who}</p>
            <p>{p.does}</p>
            <Link className="btn btn-primary" href={`/login?email=${encodeURIComponent(p.email)}&next=${p.next}`}>
              Sign in as {p.title.toLowerCase()}
            </Link>
          </div>
        ))}
      </div>
    </Shell>
  );
}
