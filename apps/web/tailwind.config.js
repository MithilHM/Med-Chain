/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef8ff",
          100: "#d8eeff",
          200: "#b9e2ff",
          300: "#89d1ff",
          400: "#52b5ff",
          500: "#2a94ff",
          600: "#1374f6",
          700: "#0d5ce2",
          800: "#124ab7",
          900: "#14408f",
          950: "#102857",
        },
      },
    },
  },
  plugins: [],
};
