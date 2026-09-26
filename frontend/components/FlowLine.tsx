"use client";
import { useEffect, useRef, useState } from "react";
import Icon, { type IconName } from "./Icon";
import { BrandMark } from "./AppShell";

const FLOW: { icon: IconName | "brand"; title: string; text: string; hub?: boolean }[] = [
  { icon: "restaurant", title: "Restaurant", text: "Posts safe surplus food" },
  { icon: "brand", title: "FoodFlow", text: "Matches, splits, routes", hub: true },
  { icon: "driver", title: "Driver", text: "Volunteer picks it up" },
  { icon: "community-org", title: "Organization", text: "Food bank, shelter, pantry" },
  { icon: "community", title: "Community", text: "Families, students, seniors" },
];

// The landing page's five stop route line. Once it scrolls into view the line draws itself,
// the stops rise in one by one, then a food parcel rides the line on a loop and each stop
// lights up as the parcel passes it. Timing lives in globals.css (.flow-*).
export default function FlowLine() {
  const ref = useRef<HTMLDivElement>(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setLive(true);
        io.disconnect();
      }
    }, { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={ref} className={`flow ${live ? "is-live" : ""}`}>
      <div className="flow-track" aria-hidden>
        <i className="flow-fill" />
        <span className="flow-packet"><Icon name="food-box" size={22} /></span>
      </div>
      {FLOW.map((f, i) => (
        <div key={f.title} className="flow-step" style={{ "--i": i } as React.CSSProperties}>
          <span className={`stop ${f.hub ? "hub" : ""}`} aria-hidden>
            {f.icon === "brand" ? <BrandMark size={30} /> : <Icon name={f.icon} size={34} />}
          </span>
          <div className="flex flex-col">
            <strong>{f.title}</strong>
            <span className="text-sm text-ink-2">{f.text}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
