import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // output: 'export', // Enabled once generateStaticParams returns real data (EP-009)
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
