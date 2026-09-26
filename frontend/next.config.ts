import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Old dashboard paths (before the current API) keep working for existing links and bookmarks.
  redirects() {
    return [
      { source: "/admin/dashboard", destination: "/coordinator", permanent: false },
      { source: "/restaurant/dashboard", destination: "/restaurant", permanent: false },
      { source: "/driver/dashboard", destination: "/volunteer", permanent: false },
      { source: "/organization/dashboard", destination: "/org", permanent: false },
    ];
  },
};

export default nextConfig;
