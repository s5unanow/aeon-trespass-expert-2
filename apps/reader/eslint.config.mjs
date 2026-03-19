import { FlatCompat } from "@eslint/eslintrc";
import { dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory: __dirname });

/** @type {import("eslint").Linter.Config[]} */
const config = [
  ...compat.extends("next/core-web-vitals"),
  {
    rules: {
      // Static export uses unoptimized <img> — next/image not needed
      "@next/next/no-img-element": "off",
    },
  },
  {
    ignores: [".next/", "out/", "generated/", "coverage/"],
  },
];

export default config;
