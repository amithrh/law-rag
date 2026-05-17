/** @type {import('next').NextConfig} */
const nextConfig = {
  // SSE works best when the dev proxy forwards directly to the FastAPI on :8000
  // so the browser sees a single origin. Override API_BASE for prod (nginx, etc).
  async rewrites() {
    const apiBase = process.env.API_BASE || "http://127.0.0.1:8000";
    return [
      { source: "/api/:path*", destination: `${apiBase}/:path*` },
    ];
  },
  reactStrictMode: true,
};

export default nextConfig;
