"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorNote } from "@/components/States";
import { HOME, useAuth, WORKSPACE_FOR_ROLE } from "@/lib/auth";

function LoginForm() {
  const { requestCode, verifyCode } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (!sent) {
        await requestCode(email);
        setSent(true);
      } else {
        const user = await verifyCode(email, code);
        const home = HOME[WORKSPACE_FOR_ROLE[user.role]];
        router.push(next && next.startsWith(home) ? next : home);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel stack" onSubmit={submit} style={{ maxWidth: 480 }}>
      <h1>Sign in</h1>
      <p className="muted">No password. We email you a 6 digit code and a sign-in link.</p>
      {error ? <ErrorNote message={error} /> : null}
      <label className="field">
        <span>Email</span>
        <input className="input" type="email" autoComplete="email" required value={email} disabled={sent} onChange={(e) => setEmail(e.target.value)} />
      </label>
      {sent ? (
        <label className="field">
          <span>6 digit code</span>
          <input
            className="input"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            required
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          />
        </label>
      ) : null}
      <button type="submit" className="btn btn-primary" disabled={busy}>
        {sent ? "Sign in" : "Email me a code"}
      </button>
      {sent ? (
        <button type="button" className="btn btn-ghost" onClick={() => setSent(false)}>
          Use a different email
        </button>
      ) : null}
      <p className="small">
        Just looking? <Link href="/demo">Try the donation demo</Link> with fictional accounts.
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <Shell>
      <Suspense>
        <LoginForm />
      </Suspense>
    </Shell>
  );
}
