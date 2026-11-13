import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    tsconfigPaths: true,
    alias: {
      "server-only": new URL("./tests/server-only.stub.ts", import.meta.url).pathname,
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./vitest.setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}", "src/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      // только исходники: покрытие самих тестов — это число ни о чём
      include: ["src/**"],
      reporter: ["text-summary", "json-summary"],
      // Исключается только то, что не может содержать логики. Каждое новое исключение видно
      // в диффе PR — список намеренно короткий, чтобы в него нельзя было спрятать непокрытое.
      exclude: [
        // сгенерирован из схемы бэкенда, см. ADR 4
        "src/lib/api-types.ts",
        // объявления типов без исполняемого кода
        "src/**/*.d.ts",
      ],
      // Храповик: цифры — то, чего набор достигает сейчас, и они растут по мере закрытия
      // пробелов. Порог выше правды — это порог, который выключают в первую красную пятницу.
      thresholds: {
        statements: 58,
        branches: 54,
        functions: 55,
        lines: 58,
      },
    },
  },
});
