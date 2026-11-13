import { expect, test } from "@playwright/test";

/**
 * The one thing that only shows up over https, in a browser, in production mode.
 *
 * Outside local the backend prefixes its cookies with `__Host-`, and the browser half of the
 * frontend learns those names from `NEXT_PUBLIC_*` — baked into the bundle at build time. Get
 * that wrong and nothing looks broken: signing in works, pages render, and then every single
 * mutating request answers 403, because `browser-api.ts` looked for a cookie by a name nobody
 * set and sent no CSRF header.
 *
 * curl cannot catch this — it carries whatever cookies it is handed and sets headers by hand.
 * It takes a browser running the real bundle.
 *
 * Skipped on the plain http stand, where there is no prefix and nothing to check.
 */
const STAFF = {
  email: process.env["E2E_MODERATOR_EMAIL"] ?? "e2e-moderator@e2e.allstore.am",
  password: process.env["E2E_MODERATOR_PASSWORD"] ?? "e2e-password-1",
};
const CHOSEN = "a-password-of-their-own-1";

test.describe("https, production mode", () => {
  test.skip(
    ({ baseURL }) => baseURL?.startsWith("https://") !== true,
    "только на https-стенде: без него префикса нет и проверять нечего",
  );

  test("браузер доносит CSRF и меняет пароль, а не получает 403", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(STAFF.email);
    await page.getByLabel("Пароль", { exact: true }).fill(STAFF.password);
    await page.getByRole("button", { name: "Войти" }).click();

    // выданный пароль пускает ровно до экрана смены
    await page.waitForURL("**/password");

    // половина сервера: кука с префиксом действительно выставлена и читается из JS
    const cookies = await page.evaluate(() => document.cookie);
    expect(cookies, "CSRF-кука приходит с префиксом и доступна скрипту").toContain(
      "__Host-allstore_csrf",
    );

    await page.getByLabel("Текущий пароль").fill(STAFF.password);
    await page.getByLabel("Новый пароль", { exact: true }).fill(CHOSEN);
    await page.getByLabel("Новый пароль ещё раз").fill(CHOSEN);
    await page.getByRole("button", { name: "Задать пароль" }).click();

    // Вторая половина, клиентская: имя куки должно совпасть с тем, что ищет `browser-api.ts`,
    // иначе заголовок не уйдёт и сервер ответит 403. Проверено от обратного — сборка без
    // `NEXT_PUBLIC_CSRF_COOKIE` досюда не доходит. Успех уводит на /login: смена пароля
    // завершает все сессии, включая эту.
    await page.waitForURL("**/login", { timeout: 30_000 });
  });
});
