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
    // Два дерева, и это не беспорядок, а разные вещи. `tests/unit` зеркалит `src` — по
    // модулю на файл, чтобы на вопрос «какой тест покрывает это?» был один ответ.
    // `tests/screens` — сценарии по нескольким модулям сразу; у них нет одного модуля, и
    // притворяться, что есть, значило бы врать зеркалу.
    include: ["tests/unit/**/*.test.{ts,tsx}", "tests/screens/**/*.test.{ts,tsx}"],
    // Порядок перемешивается, потому что порядок, на который тесты опираются, — это
    // зависимость, о которой никто не знает, пока она не сломается в чужом PR. Сид печатается
    // и воспроизводится через --sequence.seed=<n>.
    sequence: { shuffle: true },
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
        statements: 95,
        branches: 91,
        functions: 91,
        lines: 95,
      },
    },
  },
});
