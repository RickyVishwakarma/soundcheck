"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect } from "react";
import { setTokenGetter } from "@/lib/api";

/**
 * Registers Clerk's async getToken with the framework-agnostic api client, so
 * every request to the Python backend carries the current Clerk session token
 * (or none, when signed out — the backend then serves the public demo tenant).
 */
export function ClerkTokenBridge() {
  const { getToken, isSignedIn } = useAuth();
  useEffect(() => {
    setTokenGetter(isSignedIn ? () => getToken() : null);
    return () => setTokenGetter(null);
  }, [getToken, isSignedIn]);
  return null;
}
