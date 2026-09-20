import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // standalone keeps the production image small — only the server and used deps are copied
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // product photos are served straight from the object store, whose host differs per
  // environment; optimising them here would mean pinning that host at build time
  images: { unoptimized: true },
};

export default nextConfig;
