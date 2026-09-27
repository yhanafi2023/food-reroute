"use client";
import { useState } from "react";
import FlowMap from "./FlowMap";
import Icon from "./Icon";
import { api } from "@/lib/api";

export interface PickedAddress { address: string; lat: number; lng: number }

// Street address -> the point every route starts or ends at (backend /geo/search). The person picks
// the right match from the list and sees the pin, so drivers are never sent to a guessed spot.
export default function AddressPicker({ label, value, onChange }: {
  label: string; value: PickedAddress | null; onChange: (picked: PickedAddress | null) => void;
}) {
  const [query, setQuery] = useState(value?.address ?? "");
  const [results, setResults] = useState<PickedAddress[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function search() {
    if (query.trim().length < 5) {
      setNote("Type the street address, including the city.");
      return;
    }
    setBusy(true);
    setNote(null);
    onChange(null);
    try {
      const { results } = await api<{ results: { label: string; lat: number; lng: number }[] }>(
        `/geo/search?q=${encodeURIComponent(query.trim())}`);
      const found = results.map((r) => ({ address: r.label, lat: r.lat, lng: r.lng }));
      setResults(found);
      if (!found.length) setNote("No match. Check the street number and add the city and ZIP code.");
      if (found.length === 1) pick(found[0]);
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function pick(p: PickedAddress) {
    onChange(p);
    setQuery(p.address);
    setResults(null);
    setNote(null);
  }

  return (
    <div className="flex flex-col gap-2">
      <label className="field"><span>{label}</span>
        <div className="flex gap-2">
          <input className="input flex-1" required value={query} autoComplete="street-address"
            placeholder="e.g. 11200 SW 8th St, Miami, FL 33199"
            onChange={(e) => { setQuery(e.target.value); if (value) onChange(null); }}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); search(); } }} />
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={search}>
            <Icon name="locate" size={20} />{busy ? "Searching..." : "Find"}
          </button>
        </div>
      </label>
      {note && <p className="text-sm text-ink-2" role="status">{note}</p>}
      {results && results.length > 1 && (
        <ul className="panel panel-tight flex flex-col divide-y divide-line" aria-label="Matching addresses">
          {results.map((r) => (
            <li key={`${r.lat},${r.lng}`}>
              <button type="button" className="w-full py-2 text-left hover:text-accent" onClick={() => pick(r)}>{r.address}</button>
            </li>
          ))}
        </ul>
      )}
      {value && (
        <>
          <p className="text-sm text-ink-2" role="status">Pinned: drivers will be routed here. Wrong spot? Edit the address and search again.</p>
          <FlowMap height={220} fitKey={`${value.lat},${value.lng}`}
            restaurants={[{ id: "picked", lat: value.lat, lng: value.lng, label: value.address }]} />
        </>
      )}
    </div>
  );
}
