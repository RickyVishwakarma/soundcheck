import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The API base is read at runtime so the same build works against a local
  // server or the deployed one.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8077",
  },
};

export default nextConfig;
