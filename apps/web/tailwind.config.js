/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "-apple-system", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
      },
      colors: {
        // Clinical blue used for primary actions, links, and the active navigation state.
        brand: {
          50: "#eef5fc",
          100: "#d9e9f8",
          200: "#b5d2f0",
          300: "#86b4e4",
          400: "#4f8fd3",
          500: "#2470c2",
          600: "#005eb8",
          700: "#004f9e",
          800: "#003f7d",
          900: "#002f5e",
          950: "#001d3b",
        },
        canvas: "#f3f6f9",
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.05), 0 1px 3px rgba(15, 23, 42, 0.06)",
      },
    },
  },
  plugins: [],
};
