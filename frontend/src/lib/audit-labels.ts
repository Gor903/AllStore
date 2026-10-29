/**
 * The journal in the words an administrator reads it in.
 *
 * Separate from the screen because the mapping is the part that goes stale: an action renamed
 * on the backend leaves a dead key here and a line that reads like a database row, and nothing
 * fails — the screen renders either way. Here it can be tested against the actions the backend
 * actually writes.
 */

/** Every action the backend writes down. */
const ACTION: Record<string, string> = {
  "user.role_changed": "сменил роль",
  "user.admin_transferred": "передал администрирование",
  "user.admin_bootstrapped": "создало первого администратора",
  "user.admin_promoted": "сделало аккаунт администратором",
  "user.admin_password_reset": "заменило пароль администратора",
  "user.role_granted": "выдало роль с серверной оболочки",
  "user.password_granted": "выдало временный пароль с серверной оболочки",
  "user.password_changed": "сменил себе пароль",
  "user.email_change_requested": "запросил смену логина",
  "user.email_verified": "подтвердил адрес",
  "user.google_registered": "зарегистрировался через Google",
  "user.google_signed_in": "вошёл через Google",
  "user.google_linked": "привязал Google",
  "user.google_unlinked": "отвязал Google",
  "user.totp_enabled": "включил вход по коду",
  "user.totp_disabled": "выключил вход по коду",
  "user.totp_recovery_used": "вошёл по резервному коду",
  "user.totp_revoked": "сняло вход по коду с аккаунта",
  "user.blocked": "заблокировал",
  "user.unblocked": "разблокировал",
  "session.replayed": "предъявил отозванный токен — сессии устройства завершены",
  "moderator.created": "завёл модератора",
  "moderator.password_reset": "выдал модератору новый пароль",
  "business.approved": "допустил продавца",
  "business.rejected": "отклонил заявку продавца",
  "business.resubmitted": "подал заявку снова",
  "business.suspended": "приостановил магазин",
  "business.blocked": "заблокировал магазин",
  "business.restored": "восстановил магазин",
  "product.approved": "одобрил товар",
  "product.rejected": "отклонил товар",
  "product.hidden": "снял товар с публикации",
  "product.published": "вернул товар в каталог",
  "store.customer_blocked": "закрыл магазин покупателю",
  "store.customer_unblocked": "вернул покупателю доступ в магазин",
  "report.upheld": "признал жалобу обоснованной",
  "report.dismissed": "отклонил жалобу",
  "category.created": "завёл категорию",
  "category.renamed": "переименовал категорию",
  "category.hidden": "скрыл категорию",
  "category.shown": "вернул категорию",
};

/**
 * Entries nobody can be named for, and what stands in the actor's place for each.
 *
 * Without this they read "аккаунт удалён", which is what an empty actor means everywhere else
 * and is a lie here: these never had one. A replayed token was presented by somebody the
 * platform cannot identify; a bootstrap or a `grant_role` answers to whoever holds the server.
 */
const NOBODY: Record<string, string> = {
  "session.replayed": "неизвестный",
  "user.admin_bootstrapped": "развёртывание",
  "user.admin_promoted": "развёртывание",
  "user.admin_password_reset": "развёртывание",
  "user.role_granted": "серверная оболочка",
  "user.totp_revoked": "серверная оболочка",
  "user.password_granted": "серверная оболочка",
};

const DETAIL: Record<string, string> = {
  from: "было",
  to: "стало",
  reason: "причина",
  name: "название",
  slug: "адрес",
  email: "адрес",
  buyer: "покупатель",
  device: "устройство",
  subject: "предмет",
  closed: "закрыто жалоб",
};

/** Prefix matching, so a subject keeps working as new actions about it are added. */
export const SUBJECTS = [
  { value: "", label: "Любое действие" },
  { value: "user.", label: "Аккаунты" },
  { value: "session.", label: "Сессии" },
  { value: "moderator.", label: "Модераторы" },
  { value: "business.", label: "Продавцы" },
  { value: "product.", label: "Товары" },
  { value: "store.", label: "Магазины" },
  { value: "report.", label: "Жалобы" },
  { value: "category.", label: "Категории" },
];

/** The raw action is the fallback: an unlabelled entry is better than a hidden one. */
export function actionLabel(action: string): string {
  return ACTION[action] ?? action;
}

export function actorLabel(action: string, actorEmail: string | null): string {
  return actorEmail ?? NOBODY[action] ?? "аккаунт удалён";
}

export function described(details: Record<string, unknown>): string {
  return Object.entries(details)
    .map(([key, value]) => `${DETAIL[key] ?? key}: ${String(value)}`)
    .join(", ");
}
