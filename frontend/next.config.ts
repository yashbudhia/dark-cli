import type { NextConfig } from "next";

const config: NextConfig = {
  async rewrites() {
    const backend = process.env.DARK_BACKEND_URL ?? "http://127.0.0.1:8000";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/health", destination: `${backend}/health` },
    ];
  },
};

export default config;
