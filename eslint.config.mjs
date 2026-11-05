// ESLint para web/: garantiza compatibilidad con Chrome 60 (Xiaomi Redmi 5 Plus, Android 7/8).
// - ecmaVersion 2017: rechaza ?. ?? spread de objetos, etc.
// - eslint-plugin-compat: avisa de APIs que no existen en Chrome 60 (según browserslist).
import js from "@eslint/js";
import compat from "eslint-plugin-compat";
import globals from "globals";

export default [
  { ignores: ["node_modules/**", "dist/**", "build/**", ".venv/**"] },
  js.configs.recommended,
  compat.configs["flat/recommended"],
  {
    files: ["web/**/*.js"],
    languageOptions: {
      ecmaVersion: 2017,
      sourceType: "script",
      globals: Object.assign({}, globals.browser, { PD: "writable" }),
    },
    rules: {
      eqeqeq: ["error", "always"],
      // catch sin variable (catch {}) es ES2019: en Chrome 60 hay que declararla aunque no se use.
      "no-unused-vars": ["error", { caughtErrors: "none" }],
      "no-var": "error",
      "prefer-const": "error",
      "no-implicit-globals": "error",
      "no-restricted-properties": [
        "error",
        { property: "finally", message: "Promise.prototype.finally no existe en Chrome 60." },
        { property: "flat", message: "Array.prototype.flat no existe en Chrome 60." },
        { property: "flatMap", message: "Array.prototype.flatMap no existe en Chrome 60." },
        { property: "fromEntries", message: "Object.fromEntries no existe en Chrome 60." },
        { property: "replaceAll", message: "String.prototype.replaceAll no existe en Chrome 60." },
      ],
      "no-restricted-globals": [
        "error",
        { name: "AbortController", message: "No existe en Chrome 60: usa Promise.race con un temporizador." },
        { name: "ResizeObserver", message: "No existe en Chrome 60." },
        { name: "globalThis", message: "No existe en Chrome 60: usa window." },
      ],
    },
  },
  {
    files: ["web/sw.js"],
    languageOptions: { globals: globals.serviceworker },
  },
];
