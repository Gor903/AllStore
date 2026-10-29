"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

type Status = { enabled: boolean; required: boolean; recovery_codes_left: number };
type Enrolment = { secret: string; uri: string; qr: string };

/**
 * Turning the second factor on and off.
 *
 * The screen shows the secret and the recovery codes exactly once, because that is how often
 * they exist in a readable form: the secret is encrypted on our side and the codes are
 * hashed, so there is no later moment at which either can be read out again. Said in so many
 * words on the screen, because a person who closes this page expecting to come back is a
 * person who has lost their way in.
 */
export function SecondFactor({ status }: { status: Status }) {
  const router = useRouter();
  const [enrolment, setEnrolment] = useState<Enrolment | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function begin() {
    setPending(true);
    setError(null);
    const result = await apiPost<Enrolment>("/auth/totp/setup", {});
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setEnrolment(result.data);
  }

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const result = await apiPost<{ recovery_codes: string[] }>("/auth/totp/confirm", {
      code: form.get("code"),
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setEnrolment(null);
    setCodes(result.data.recovery_codes);
    router.refresh();
  }

  async function disable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const result = await apiPost("/auth/totp/disable", { code: form.get("code") });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setRemoving(false);
    router.refresh();
  }

  const complaint =
    error && Object.keys(error.fieldErrors).length === 0 ? (
      <p role="alert" className="text-sm text-danger">
        {error.message}
      </p>
    ) : null;

  if (codes !== null) {
    return (
      <section className="flex flex-col gap-3 rounded-card border border-ink-muted/20 p-4">
        <h2 className="font-medium">Резервные коды</h2>
        <p className="text-sm text-ink-muted">
          Сохраните их сейчас — показать ещё раз мы не сможем. Каждый код срабатывает один раз и
          заменяет код из приложения, если телефона нет под рукой.
        </p>
        <ul className="grid grid-cols-2 gap-1 font-mono text-sm">
          {codes.map((code) => (
            <li key={code}>{code}</li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => {
            setCodes(null);
          }}
          className="self-start rounded-lg border border-ink-muted/30 px-4 py-2 text-sm"
        >
          Я записал их
        </button>
      </section>
    );
  }

  if (enrolment !== null) {
    return (
      <section className="flex flex-col gap-3 rounded-card border border-ink-muted/20 p-4">
        <h2 className="font-medium">Привязка приложения</h2>
        <p className="text-sm text-ink-muted">
          Отсканируйте код в приложении-аутентификаторе и введите шесть цифр, которые оно покажет.
        </p>
        {/* eslint-disable-next-line @next/next/no-img-element -- a data URI has no host to optimise */}
        <img src={enrolment.qr} alt="QR-код для приложения" className="h-48 w-48" />
        <p className="text-sm text-ink-muted">
          Если камера недоступна, введите ключ вручную:{" "}
          <code className="font-mono">{enrolment.secret}</code>
        </p>
        <form onSubmit={confirm} className="flex flex-col gap-3" noValidate>
          <Field label="Код из приложения" name="code" autoComplete="one-time-code" />
          {complaint}
          <button
            type="submit"
            disabled={pending}
            className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
          >
            {pending ? "Проверяем…" : "Включить"}
          </button>
        </form>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-3 rounded-card border border-ink-muted/20 p-4">
      <h2 className="font-medium">Вход по коду</h2>
      {status.enabled ? (
        <>
          <p className="text-sm text-ink-muted">
            Включён. Осталось резервных кодов: {status.recovery_codes_left}.
          </p>
          {removing ? (
            <form onSubmit={disable} className="flex flex-col gap-3" noValidate>
              <p className="text-sm text-ink-muted">
                Введите текущий код из приложения — выключение требует подтверждения.
              </p>
              <Field label="Код из приложения" name="code" autoComplete="one-time-code" />
              {complaint}
              <button
                type="submit"
                disabled={pending}
                className="self-start rounded-lg border border-danger px-4 py-2 text-sm text-danger disabled:opacity-60"
              >
                {pending ? "Выключаем…" : "Выключить"}
              </button>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => {
                setRemoving(true);
              }}
              className="self-start rounded-lg border border-ink-muted/30 px-4 py-2 text-sm"
            >
              Выключить
            </button>
          )}
        </>
      ) : (
        <>
          <p className="text-sm text-ink-muted">
            {status.required
              ? "Для вашей роли он обязателен: пока приложение не привязано, остальные разделы закрыты."
              : "Код из приложения в дополнение к паролю. Пароль можно подсмотреть или подобрать; код живёт тридцать секунд и лежит в вашем телефоне."}
          </p>
          {complaint}
          <button
            type="button"
            onClick={() => {
              void begin();
            }}
            disabled={pending}
            className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
          >
            {pending ? "Готовим…" : "Привязать приложение"}
          </button>
        </>
      )}
    </section>
  );
}
