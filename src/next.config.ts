import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://xps:8766/:path*",
      },
    ];
  },
};

export default nextConfig;
