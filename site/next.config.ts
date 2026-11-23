import type { NextConfig } from "next";

// GitHub Pages serves a project site from a sub-path (https://<org>.github.io/<repo>/).
// The deploy workflow sets NEXT_PUBLIC_BASE_PATH to that sub-path; locally it is empty.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || undefined;

const nextConfig: NextConfig = {
  output: "export", // fully static: the map is client-side, so it can be hosted on any static host
  basePath,
  trailingSlash: true, // static hosts serve /path/ as /path/index.html
};

export default nextConfig;
