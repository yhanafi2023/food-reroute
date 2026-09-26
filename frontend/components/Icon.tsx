import type { CSSProperties } from "react";

// FoodFlow's full-color icon set: one SVG sprite in public/icons, each icon a <symbol> on a
// 48x48 grid. Referencing the sprite (rather than inlining each icon) keeps pages small and
// lets the browser cache it once for every page and every map marker.
export const ICON_SPRITE = "/icons/foodflow-icons.svg";

export type IconName =
  | "restaurant" | "driver" | "community-org" | "person" | "avatar" | "community"
  | "car" | "car-top" | "van" | "route" | "pickup-pin" | "dropoff" | "navigate" | "eta" | "locate"
  | "food-box" | "hot-meal" | "produce" | "bread" | "temp-check" | "food-safe" | "scale"
  | "schedule" | "alert" | "message" | "stats";

export default function Icon({ name, size = 24, label, className, style }: {
  name: IconName; size?: number; label?: string; className?: string; style?: CSSProperties;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" className={className} style={{ flex: "none", ...style }}
      role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <use href={`${ICON_SPRITE}#ff-${name}`} />
    </svg>
  );
}

// The same icon as an HTML string, for Leaflet divIcons (which take markup, not React nodes).
export function iconMarkup(name: IconName, size: number) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 48 48" aria-hidden="true"><use href="${ICON_SPRITE}#ff-${name}"/></svg>`;
}

// A tile behind an icon so the dark-outlined artwork reads on the dark console panels.
export function IconTile({ name, size = 40, tone = "light", className = "" }: {
  name: IconName; size?: number; tone?: "light" | "accent" | "good" | "warn"; className?: string;
}) {
  return (
    <span className={`icon-tile icon-tile-${tone} ${className}`} style={{ width: size, height: size }} aria-hidden>
      <Icon name={name} size={Math.round(size * 0.72)} />
    </span>
  );
}
