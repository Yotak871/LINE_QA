

const nextConfig = {
  images: {
    remotePatterns: [{ hostname: "localhost" }, { hostname: "127.0.0.1" }],
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
