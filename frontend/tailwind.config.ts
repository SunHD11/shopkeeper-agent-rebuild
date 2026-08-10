import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          '"Noto Sans SC"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          "sans-serif",
        ],
        display: [
          '"LXGW WenKai Screen"',
          '"Noto Sans SC"',
          '"Microsoft YaHei"',
          "sans-serif",
        ],
        mono: ['"JetBrains Mono"', '"SFMono-Regular"', "Consolas", "monospace"],
      },
      colors: {
        canvas: "rgb(var(--color-canvas) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        "surface-strong": "rgb(var(--color-surface-strong) / <alpha-value>)",
        ink: "rgb(var(--color-ink) / <alpha-value>)",
        muted: "rgb(var(--color-muted) / <alpha-value>)",
        moss: "rgb(var(--color-moss) / <alpha-value>)",
        brass: "rgb(var(--color-brass) / <alpha-value>)",
        tomato: "rgb(var(--color-tomato) / <alpha-value>)",
        info: "rgb(var(--color-info) / <alpha-value>)",
      },
      boxShadow: {
        line: "0 1px 0 rgba(30, 32, 28, 0.08)",
        panel: "0 18px 48px rgba(45, 41, 37, 0.12)",
        floating: "0 10px 30px rgba(45, 41, 37, 0.16)",
      },
      borderRadius: {
        panel: "8px",
      },
    },
  },
  plugins: [],
} satisfies Config;
