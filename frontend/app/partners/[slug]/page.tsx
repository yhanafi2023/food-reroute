"use client";
import { useParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { ErrorNote, Loading } from "@/components/States";
import { number } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

interface PartnerPage {
  name: string;
  badge: string;
  meals_donated_to_date: number;
  pounds_diverted_to_date: number;
  pounds_method: string;
  partner_organizations: string[];
  other_partner_organizations: number;
  is_fictional: boolean;
}

// Public, opt-in partner page (GET /public/partners/{slug}); the window decal QR code links here.
export default function Partner() {
  const { slug } = useParams<{ slug: string }>();
  const { data, error, refresh } = usePoll<PartnerPage>(`/public/partners/${encodeURIComponent(slug)}`, 60000);
  return (
    <Shell>
      {error && !data ? <ErrorNote message={error} onRetry={refresh} /> : null}
      {!data && !error ? <Loading /> : null}
      {data ? (
        <article className="stack" style={{ maxWidth: 720 }}>
          <span className="eyebrow">{data.badge}</span>
          <h1>{data.name}</h1>
          {data.is_fictional ? <p className="chip chip-warn">Fictional demo business</p> : null}
          <div className="grid-2">
            <div className="stat">
              <span className="stat-value">{number(data.meals_donated_to_date)}</span>
              <span className="muted">meals donated and confirmed by the receiving organizations</span>
            </div>
            <div className="stat">
              <span className="stat-value">{number(data.pounds_diverted_to_date)} lbs</span>
              <span className="muted">food kept out of the trash ({data.pounds_method})</span>
            </div>
          </div>
          {data.partner_organizations.length ? <p>Donates to {data.partner_organizations.join(", ")}.</p> : null}
          {data.other_partner_organizations ? (
            <p className="muted">
              And {data.other_partner_organizations} other organization{data.other_partner_organizations === 1 ? "" : "s"} that chose not to be named.
            </p>
          ) : null}
        </article>
      ) : null}
    </Shell>
  );
}
