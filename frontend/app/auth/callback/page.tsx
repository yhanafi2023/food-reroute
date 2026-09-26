"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorNote, Loading } from "@/components/States";
import { HOME, useAuth, WORKSPACE_FOR_ROLE } from "@/lib/auth";

// The sign-in link from the email: /auth/callback?token=... (backend/app/auth.py).
function Callback() {
  const token = useSearchParams().get("token");
  const { verifyLink } = useAuth();
  const router = useRouter();
  const [error, setError] = useState(token ? "" : "This sign-in link is missing its token.");
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    verifyLink(token)
      .then((u) => router.replace(HOME[WORKSPACE_FOR_ROLE[u.role]]))
      .catch((e) => setError((e as Error).message));
  }, [token, verifyLink, router]);

  if (error)
    return (
      <div className="stack" style={{ maxWidth: 480 }}>
        <ErrorNote message={error} />
        <Link href="/login" className="btn btn-primary">
          Request a new code
        </Link>
      </div>
    );
  return <Loading label="Signing you in" />;
}

export default function CallbackPage() {
  return (
    <Shell>
      <Suspense>
        <Callback />
      </Suspense>
    </Shell>
  );
}
