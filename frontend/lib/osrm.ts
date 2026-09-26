// Real road routing via OSRM's public demo server (no key needed -- same server this repo's
// backend already defaults to, see backend/.env.example OSRM_URL). Falls back to the straight
// line the caller passes in if the request fails; the map never shows "no route" over this.
export async function roadRoute(points: [number, number][]): Promise<[number, number][] | null> {
  if (points.length < 2) return null;
  const coords = points.map(([lat, lng]) => `${lng},${lat}`).join(";");
  try {
    const r = await fetch(`https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson`);
    if (!r.ok) return null;
    const data = await r.json();
    const line = data?.routes?.[0]?.geometry?.coordinates as [number, number][] | undefined;
    if (!line || line.length < 2) return null;
    return line.map(([lng, lat]) => [lat, lng]);
  } catch {
    return null;
  }
}
