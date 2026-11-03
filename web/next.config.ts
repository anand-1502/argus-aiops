import type { NextConfig } from "next";

// NEXT_PUBLIC_STATIC=1 builds the public GitHub Pages site (scripts/build_static.sh): plain files, data read from snapshots.
const isStatic = process.env.NEXT_PUBLIC_STATIC === "1";

const nextConfig: NextConfig = {
  output: isStatic ? "export" : "standalone", // standalone: a small self-contained server for the container image
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || undefined,
  trailingSlash: isStatic,
  images: { unoptimized: isStatic },
  /* config options here */
  cacheComponents: !isStatic, // partial prerendering cannot be enabled in export mode
  partialPrefetching: !isStatic,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
