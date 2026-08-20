import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The dev server normally only trusts requests whose Origin is
  // localhost — anything else gets its HMR/dev-resource requests silently
  // blocked, which breaks the React Refresh runtime (symptom: typing into
  // any input never updates React state, no console error). Needed here
  // because this app is accessed through Docker Desktop's host-mapped port
  // and, for in-container tooling, host.docker.internal.
  allowedDevOrigins: ["host.docker.internal", "127.0.0.1", "frontend"],
};

export default nextConfig;
