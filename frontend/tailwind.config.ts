import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        line: {
          50:  "#e6f9ed",
          100: "#c0f0d1",
          200: "#8de4ae",
          300: "#4dd980",
          400: "#1ecf60",
          500: "#06c755",   // LINE Primary Green
          600: "#05b34a",
          700: "#049a3f",
          800: "#037a32",
          900: "#025a25",
        },
        surface: {
          50:  "#f7f8f9",
          100: "#efefef",
          200: "#e5e5e5",
        },
      },
      fontFamily: {
        seed: [
          '"LINE Seed"',
          '"Noto Sans KR"',
          "system-ui",
          "sans-serif",
        ],
        sans: [
          '"Noto Sans KR"',
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Roboto",
          "Helvetica Neue",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
