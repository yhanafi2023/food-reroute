"use client";
import { QRCodeSVG } from "qrcode.react";
import { useSyncExternalStore } from "react";
import { Brand } from "@/components/AppShell";

const noop = () => () => {};

export default function QrPage() {
  const origin = useSyncExternalStore(noop, () => window.location.origin, () => "");
  const url = process.env.NEXT_PUBLIC_SITE_URL || origin;
  return (
    <div className="mx-auto flex min-h-screen max-w-4xl flex-col items-start gap-8 px-4 py-6">
      <Brand />
      <div className="grid w-full items-center gap-8 md:grid-cols-[auto_1fr]">
        <div className="panel inline-flex" aria-label="QR code">
          {url && <QRCodeSVG value={url} size={320} fgColor="#0e1a2b" level="M" marginSize={1} />}
        </div>
        <div className="flex flex-col gap-4">
          <span className="eyebrow">Try FoodFlow</span>
          <h1>Scan to open the live demo.</h1>
          <p className="mono break-all text-lg text-ink-2">{url}</p>
          <p className="text-ink-2">Demo logins use password demo1234.</p>
        </div>
      </div>
    </div>
  );
}
