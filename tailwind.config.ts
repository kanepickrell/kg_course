import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
    "./src/**/*.{ts,tsx}",
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Cactus Theme Colors - Tactical
        cactus: {
          tan: "rgb(var(--cactus-tan))",
          green: "rgb(var(--cactus-green))",
          olive: "rgb(var(--cactus-olive))",
          sand: "rgb(var(--cactus-sand))",
          accent: "rgb(var(--cactus-accent))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        twinkle: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.6", transform: "scale(0.9)" },
        },
        "pulse-border": {
          "0%, 100%": {
            borderColor: "hsl(var(--border))",
            boxShadow: "0 0 0 0 rgba(130, 150, 70, 0.4)",
          },
          "50%": {
            borderColor: "rgb(130 150 70)",
            boxShadow: "0 0 0 4px rgba(130, 150, 70, 0.2)",
          },
        },
        "highlight-glow": {
          "0%, 100%": { filter: "drop-shadow(0 0 4px rgb(130 150 70))" },
          "50%": { filter: "drop-shadow(0 0 12px rgb(130 150 70))" },
        },
        "pulse-cactus": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-1000px 0" },
          "100%": { backgroundPosition: "1000px 0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        twinkle: "twinkle 2s ease-in-out infinite",
        "pulse-border": "pulse-border 1.5s ease-in-out infinite",
        "highlight-glow": "highlight-glow 1.5s ease-in-out infinite",
        "pulse-cactus": "pulse-cactus 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        shimmer: "shimmer 2s infinite",
      },
      boxShadow: {
        neo: "3px 3px 0px 0px rgba(0, 0, 0, 0.8)",
        "neo-sm": "2px 2px 0px 0px rgba(0, 0, 0, 0.8)",
        "neo-lg": "4px 4px 0px 0px rgba(0, 0, 0, 0.9)",
        "neo-hover": "4px 4px 0px 0px rgba(0, 0, 0, 0.9)",
        "neo-active": "1px 1px 0px 0px rgba(0, 0, 0, 1)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config;