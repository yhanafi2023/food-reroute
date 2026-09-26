// Real road routing via OSRM's public demo server (no key; the same server the backend defaults to).
// The demo server is shared infrastructure, so each route is fetched at most once per page session
// (in-flight and finished requests are cached by waypoints). Returns null on failure; callers keep
// their straight-line fallback and label it as such. From a073982, with the cache added.
const cache = new Map<string, Promise<[number, number][] | null>>();

export function roadRoute(points: [number, number][]): Promise<[number, number][] | null> {
  if (points.length < 2) return Promise.resolve(null);
  const coords = points.map(([lat, lng]) => `${lng.toFixed(5)},${lat.toFixed(5)}`).join(";");
  const hit = cache.get(coords);
  if (hit) return hit;
  const request = fetch(`https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson`)
    .then(async (r) => {
      if (!r.ok) return null;
      const data = await r.json();
      const line = data?.routes?.[0]?.geometry?.coordinates as [number, number][] | undefined;
      if (!line || line.length < 2) return null;
      return line.map(([lng, lat]) => [lat, lng] as [number, number]);
    })
    .catch(() => null);
  cache.set(coords, request);
  return request;
}
