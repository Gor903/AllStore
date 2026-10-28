import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * The one path the whole product exists for: a seller signs up, opens a shop, files a
 * product, a moderator lets both through, and a stranger finds the product in the
 * catalogue and on the shop's own address.
 *
 * The moderator is not registered here — nobody can register into that role. The account
 * is made by scripts/grant_role.py before the run, see e2e/README.md.
 */
const MODERATOR = {
  email: process.env["E2E_MODERATOR_EMAIL"] ?? "e2e-moderator@e2e.allstore.am",
  password: process.env["E2E_MODERATOR_PASSWORD"] ?? "e2e-password-1",
};

const PASSWORD = "e2e-password-1";
const PHONE = "+37410123456";

/** Every run leaves its rows behind, so nothing it creates may collide with a previous one. */
const run = Date.now().toString(36);
const subdomain = `e2e${run}`;
const seller = {
  email: `seller-${run}@e2e.allstore.am`,
  legalName: `ИП e2e ${run}`,
  displayName: `Магазин e2e ${run}`,
};
const productName = `Ваза e2e ${run}`;
const editedName = `Ваза керамическая e2e ${run}`;

/**
 * The moderator's own password, chosen in the scenario.
 *
 * The account is made by scripts/grant_role before the run, so what it starts with is a
 * password somebody typed on a command line — and the platform refuses to be used under one
 * of those. Picking a new one is therefore part of the path, not a detour around it.
 */
const moderatorPassword = `e2e-chosen-${run}`;

/** A queue page holds twenty rows and no more, so nine pages is past any stand we run on. */
const MAX_QUEUE_PAGES = 20;

async function signIn(page: Page, email: string, password: string): Promise<void> {
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Пароль", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
}

/**
 * Finds a row in a paged moderation queue, turning pages until it shows up.
 *
 * The queues are oldest-first, so a row this run has just created is on the last page — and
 * on a stand with a backlog that is not page one. Looking only at the first page passes on an
 * empty database and fails everywhere else, which is the opposite of what an end-to-end test
 * is for: it went red on a stand with 177 products in the queue while the code was fine.
 */
async function queueRow(page: Page, path: string, text: string): Promise<Locator> {
  await page.goto(path);
  for (let turned = 0; turned < MAX_QUEUE_PAGES; turned += 1) {
    const row = page.getByRole("listitem").filter({ hasText: text });
    if ((await row.count()) > 0) {
      return row;
    }
    const next = page.getByRole("link", { name: "Вперёд" });
    if ((await next.count()) === 0) {
      break;
    }
    // the pages are addresses, so the turn is done when the address has changed
    const before = page.url();
    await next.click();
    await page.waitForURL((url) => url.href !== before);
  }
  throw new Error(`«${text}» не нашлось в очереди ${path} ни на одной странице`);
}

test("продавец регистрируется, заводит магазин и товар, модератор пропускает, покупатель находит", async ({
  page,
}) => {
  await test.step("продавец регистрируется", async () => {
    await page.goto("/register");
    await page.getByRole("button", { name: "Продавец" }).click();
    await page.getByLabel("Email", { exact: true }).fill(seller.email);
    await page.getByLabel("Пароль", { exact: true }).fill(PASSWORD);
    await page.getByLabel("Юридическое название").fill(seller.legalName);
    await page.getByLabel("Название магазина").fill(seller.displayName);
    await page.getByRole("button", { name: "Зарегистрироваться" }).click();

    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole("heading", { name: "Кабинет" })).toBeVisible();
  });

  const storefrontUrl = await test.step("продавец открывает витрину", async () => {
    await page.getByLabel("Адрес магазина").fill(subdomain);
    await page.getByRole("button", { name: "Создать магазин" }).click();

    const address = page.getByRole("link", { name: new RegExp(`${subdomain}\\.`) });
    await expect(address).toBeVisible();
    // the address is taken from the page, not built here: the port belongs to the stack
    const href = await address.getAttribute("href");
    expect(href).not.toBeNull();
    return href ?? "";
  });

  await test.step("продавец оставляет способ связи", async () => {
    // without one the product does not go to review: there is no other way to order
    await page.getByRole("link", { name: /Настройки магазина/ }).click();
    await page.getByLabel("Телефон", { exact: true }).fill(PHONE);
    await page.getByRole("button", { name: "Сохранить контакты" }).click();
    await expect(page.getByText("Сохранено.")).toBeVisible();
  });

  await test.step("продавец заводит товар, и тот уходит на проверку", async () => {
    await page.goto("/dashboard/products/new");
    await page.getByLabel("Название").fill(productName);
    // the first real option: the placeholder above it is disabled
    await page.getByLabel("Категория").selectOption({ index: 1 });
    await page.getByLabel("Цена, ֏").fill("4500");
    await page.getByLabel("Остаток, шт.").fill("3");
    await page.getByRole("button", { name: "Создать товар" }).click();

    await expect(page.getByRole("heading", { name: productName })).toBeVisible();
    // a new product is already in the queue: submitting is for the ones sent back
    await expect(page.getByRole("button", { name: "Уже на проверке" })).toBeVisible();
  });

  await test.step("модератор входит и задаёт свой пароль", async () => {
    // one browser for both people: the seller is done, and the shop still has to be let in
    await page.goto("/dashboard");
    await page.getByRole("button", { name: "Выйти" }).click();
    await expect(page).toHaveURL(/\/login/);
    await signIn(page, MODERATOR.email, MODERATOR.password);

    // the account was made by scripts/grant_role, so its password came off a command line
    // and is owed a replacement; the rest of the site stays shut until it gets one
    await expect(page).toHaveURL(/\/password$/);
    await expect(page.getByRole("heading", { name: "Задайте свой пароль" })).toBeVisible();
    await page.goto("/moderation");
    await expect(page).toHaveURL(/\/password$/);

    await page.getByLabel("Текущий пароль").fill(MODERATOR.password);
    await page.getByLabel("Новый пароль", { exact: true }).fill(moderatorPassword);
    await page.getByLabel("Новый пароль ещё раз").fill(moderatorPassword);
    await page.getByRole("button", { name: "Задать пароль" }).click();

    // the change ends every session, so the way back in is through the door
    await expect(page).toHaveURL(/\/login/);
    await signIn(page, MODERATOR.email, moderatorPassword);

    // every role lands in the same cabinet; the queue is one link away from it
    await expect(page).toHaveURL(/\/dashboard$/);
    await page.getByRole("link", { name: "Очередь модерации" }).click();
    await expect(page).toHaveURL(/\/moderation$/);
  });

  await test.step("модератор допускает продавца", async () => {
    const application = await queueRow(page, "/moderation/businesses", subdomain);
    await application.getByRole("button", { name: "Допустить" }).click();
    // the queue holds applications awaiting a verdict, so a decided one leaves it
    await expect(application).toHaveCount(0);
  });

  await test.step("модератор одобряет товар", async () => {
    const queued = await queueRow(page, "/moderation", productName);
    await queued.getByRole("button", { name: "Одобрить" }).click();
    await expect(queued).toHaveCount(0);
  });

  await test.step("покупатель находит товар в каталоге", async () => {
    await page.goto(`/catalog?q=${encodeURIComponent(productName)}`);
    const card = page.getByRole("link", { name: new RegExp(productName) });
    await expect(card).toBeVisible();
    // the only address of a product is inside the shop that sells it
    await expect(card).toHaveAttribute("href", new RegExp(`^https?://${subdomain}\\.`));
  });

  await test.step("покупатель попадает на витрину и видит, как связаться", async () => {
    await page.goto(storefrontUrl);
    await expect(page.getByRole("heading", { level: 1, name: seller.displayName })).toBeVisible();
    await expect(page.getByText(productName)).toBeVisible();
    await expect(
      page.getByRole("link", { name: new RegExp(PHONE.replace("+", "\\+")) }),
    ).toHaveAttribute("href", `tel:${PHONE}`);
  });

  // Этап 18: the listing a buyer is looking at survives its own seller editing it. Before
  // revisions this half of the scenario took the product out of the catalogue on the spot.
  await test.step("продавец правит одобренный товар", async () => {
    // the moderator is still signed in, and /login sends a signed-in visitor to the cabinet
    await page.goto("/dashboard");
    await page.getByRole("button", { name: "Выйти" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel("Email", { exact: true }).fill(seller.email);
    await page.getByLabel("Пароль", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Войти" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);

    // the card of a product is also its edit form
    await page.getByRole("link", { name: new RegExp(productName) }).click();
    await page.getByLabel("Название").fill(editedName);
    await page.getByRole("button", { name: "Сохранить" }).click();

    await expect(page.getByText(/Правка на проверке/)).toBeVisible();
  });

  await test.step("покупатель всё ещё видит одобренную версию", async () => {
    await page.goto(`/catalog?q=${encodeURIComponent(productName)}`);
    await expect(page.getByRole("link", { name: new RegExp(productName) })).toBeVisible();
    await page.goto(`/catalog?q=${encodeURIComponent(editedName)}`);
    await expect(page.getByRole("link", { name: new RegExp(editedName) })).toHaveCount(0);
  });

  await test.step("модератор одобряет правку, и каталог догоняет", async () => {
    await page.goto("/dashboard");
    await page.getByRole("button", { name: "Выйти" }).click();
    await expect(page).toHaveURL(/\/login/);
    // the one they chose earlier: the handed-over password stopped working when they did
    await signIn(page, MODERATOR.email, moderatorPassword);
    // the form navigates on its own; going somewhere else before it lands races with it
    await expect(page).toHaveURL(/\/dashboard$/);

    const queued = await queueRow(page, "/moderation", editedName);
    await expect(queued.getByText(/правка уже опубликованного товара/)).toBeVisible();
    await queued.getByRole("button", { name: "Одобрить" }).click();
    await expect(queued).toHaveCount(0);

    await page.goto(`/catalog?q=${encodeURIComponent(editedName)}`);
    await expect(page.getByRole("link", { name: new RegExp(editedName) })).toBeVisible();
  });
});
