/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"}/:path*`,
      },
    ]
  },
}

export default nextConfig
