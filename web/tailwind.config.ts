import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        peach: {
          50: "#FFF8F0",
          100: "#FFF1E4",
          200: "#FFE0C8",
          300: "#F5C9A8",
          400: "#E8A87C",
          500: "#E08A4F",
          800: "#6B3F2A",
          900: "#3F2A22",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
