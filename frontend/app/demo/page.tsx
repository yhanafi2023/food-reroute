"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorNote } from "@/components/States";
import { HOME, useAuth } from "@/lib/auth";
import type { Workspace } from "@/lib/types";

const PERSONAS: { ws: Workspace; title: string; who: string; does: string }[] = [
  { ws: "restaurant", title: "Restaurant", who: "Rosa, closing cook at Casa Demo Cocina", does: "Post tonight's surplus and read the pickup code to the driver." },
  { ws: "volunteer", title: "Volunteer", who: "Marcus, volunteer driver", does: "Accept the run, enter the pickup code, then the drop-off code." },
  { ws: "org", title: "Receiving organization", who: "Tomas, staff at Demo Night Shelter", does: "Give the driver the drop-off code and confirm what you accepted." },
  { ws: "coordinator", title: "Coordinator", who: "FoodFlow coordinator", does: "Watch every rescue on the map and see why each assignment was made." },
];

export default function DemoPicker() {
  const { demoSignin } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState<Workspace | null>(null);
  const [error, setError] = useState("");

  const go = async (ws: Workspace) => {
    setBusy(ws);
    setError("");
    try {
      await demoSignin(ws);
      router.push(HOME[ws]);
    } catch (e) {
      setError(`${(e as Error).message}. Demo sign-in only works when the server runs with DEMO_MODE=true.`);
      setBusy(null);
    }
  };

  return (
    <Shell>
      <div className="stack">
        <h1>Try the donation demo</h1>
        <p style={{ maxWidth: "62ch", color: "var(--ink-2)" }}>
          Pick a role. Open another role in a second window to watch the same donation from both sides. Every business,
          organization and person here is fictional.
        </p>
      </div>
      {error ? <ErrorNote message={error} /> : null}
      <div className="grid-2">
        {PERSONAS.map((p) => (
          <div key={p.ws} className="panel stack">
            <h2>{p.title}</h2>
            <p className="muted">{p.who}</p>
            <p>{p.does}</p>
            <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => go(p.ws)}>
              {busy === p.ws ? "Signing in" : `Continue as ${p.title.toLowerCase()}`}
            </button>
          </div>
        ))}
      </div>
    </Shell>
  );
}
