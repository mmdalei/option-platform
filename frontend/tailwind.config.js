/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Vazirmatn Variable"', '"Vazirmatn"', "system-ui", "sans-serif"],
      },
      colors: {
        paper: "#F6F7F5",
        panel: "#FFFFFF",
        ledger: "#EEF0EC",
        ink: {
          DEFAULT: "#171C19",
          soft: "#525C56",
          "on-dark-soft": "#A8B2AC",
        },
        rule: {
          DEFAULT: "#D5DAD4",
          strong: "#88928B",
        },
        focus: "#0B57D0",
        "focus-on-dark": "#93C5FD",
        up: "#0B6E43",
        "up-on-dark": "#6EDBA9",
        down: "#B42318",
        "down-on-dark": "#FF9A92",
        warn: "#9A5B00",
        itm: {
          DEFAULT: "#EBF7F1",
          strong: "#B7DFCA",
        },
        atm: {
          DEFAULT: "#FEF9E7",
          strong: "#F5DFA0",
        },
        otm: {
          DEFAULT: "#FDF0EF",
          strong: "#EBC1BE",
        },
      },
      boxShadow: {
        xs: "0 1px 2px 0 rgba(23, 28, 25, 0.04)",
        sticky: "0 1px 0 0 #D5DAD4",
      },
    },
  },
  plugins: [],
};