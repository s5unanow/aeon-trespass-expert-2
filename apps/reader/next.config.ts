import { existsSync, readdirSync } from 'fs';
import { join } from 'path';
import type { NextConfig } from 'next';

/**
 * Only enable static export when bundle data exists.
 * CI runs without generated data — a regular build still catches
 * compilation and type errors without requiring documents.
 */
const generatedDir = join(process.cwd(), 'generated');
const hasBundleData =
  existsSync(generatedDir) &&
  readdirSync(generatedDir, { withFileTypes: true }).some((d) => d.isDirectory());

const nextConfig: NextConfig = {
  ...(hasBundleData ? { output: 'export' } : {}),
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
