"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { TopNav } from "@/components/AppShell";
import { HOME_FOR_ROLE, useAuth } from "@/lib/auth";

function Callback() {
  const params = useSearchParams();
  const router = useRouter();
  const { verifyToken } = useAuth();
  const token = params.get("token");
  const [error, setError] = useState<string | null>(token ? null : "This sign-in link is missing its token.");

  useEffect(() => {
    if (!token) return;
    verifyToken(token)
      .then((u) => router.replace(HOME_FOR_ROLE[u.role]))
      .catch((e) => setError((e as Error).message));
  }, [token, router, verifyToken]);

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-16 text-center">
      {error ? (
        <>
          <div className="alert alert-bad" role="alert">{error}</div>
          <a className="btn btn-primary" href="/login">Back to log in</a>
        </>
      ) : (
        <p className="text-ink-2" role="status">Signing you in...</p>
      )}
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <>
      <TopNav />
      <Suspense fallback={<p className="mx-auto max-w-md px-4 py-16 text-center text-ink-2">Signing you in...</p>}>
        <Callback />
      </Suspense>
    </>
  );
}
