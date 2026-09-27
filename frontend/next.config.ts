import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Drivers used to be called volunteers: keep old links and bookmarks working.
  redirects() {
    return [{ source: "/volunteer/:path*", destination: "/driver/:path*", permanent: true }];
  },
};

export default nextConfig;
