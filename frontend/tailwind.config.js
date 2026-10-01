/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: "#EDEBE4",
        surface: "#FFFFFF",
        ink: "#1B2430",
        stone: "#6B6560",
        "stone-light": "#A9A39C",
        line: "#D8D4C9",
        oxblood: "#8A2E22",
        "oxblood-light": "#F4E4E0",
        verified: "#3F6659",
        "verified-light": "#E3ECE8",
      },
      fontFamily: {
        serif: ["var(--font-source-serif)", "Georgia", "serif"],
        sans: ["var(--font-plex-sans)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        sm: "2px",
      },
      maxWidth: {
        prose: "70ch",
      },
    },
  },
  plugins: [],
};
