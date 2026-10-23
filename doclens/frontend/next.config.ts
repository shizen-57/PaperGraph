import type { NextConfig } from "next";

const API = process.env.API_URL ?? "http://localhost:8000";

const config: NextConfig = {
  // Same origin in the browser, so the FastAPI backend needs no CORS setup.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/:path*` }];
  },
  // pdf.js has an optional Node-only canvas import; the viewer only runs in the browser.
  webpack: (config) => {
    config.resolve.alias.canvas = false;
    return config;
  },
};

export default config;
