import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // standalone keeps the production image small — only the server and used deps are copied
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;
