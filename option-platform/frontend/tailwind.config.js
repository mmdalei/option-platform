/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Cool ledger paper, white panels, one ink colour.
        paper: "#EEF1F3",
        panel: "#FFFFFF",
        ink: { DEFAULT: "#14202B", soft: "#4A5A68" },
        rule: "#D3DBE1",
        // Moneyness: in profit / at the money / in loss (the only decorative colour in the UI).
        itm: { DEFAULT: "#DCF2E6", strong: "#B9E3CC" },
        atm: { DEFAULT: "#FFF0C2", strong: "#F7D977" },
        otm: { DEFAULT: "#FBE3E1", strong: "#F2C1BC" },
        // Direction of a price change (Tehran convention: green = up, red = down).
        up: "#0C7A4D",
        down: "#B3261E",
        focus: "#1D5FA8",
      },
      fontFamily: {
        sans: ['"Vazirmatn Variable"', "Vazirmatn", "Tahoma", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
