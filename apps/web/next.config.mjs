/** @type {import('next').NextConfig} */
const nextConfig = {
  // Keep health/index calls same-origin. Protected answer/search calls use the
  // server-side proxy in app/api so the browser never receives the API secret.
  async rewrites() {
    const apiBase = process.env.API_INTERNAL_URL || process.env.API_BASE || "http://127.0.0.1:8000";
    return [
      { source: "/api/:path*", destination: `${apiBase}/:path*` },
    ];
  },
  reactStrictMode: true,
};

export default nextConfig;
