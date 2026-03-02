const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const nextConfig = {
  images: {
    remotePatterns: [
      { hostname: "localhost" },
      { hostname: "127.0.0.1" },
      { hostname: "line-qa.onrender.com" },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
