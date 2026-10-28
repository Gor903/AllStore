import type { Metadata } from "next";

import { AdminNav } from "@/components/admin/AdminNav";
import { SystemStateCards } from "@/components/admin/SystemState";
import { getActivity, getSystemState, requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Состояние сайта",
  robots: { index: false, follow: false },
};

const SERIES = [
  { key: "registrations", label: "Регистрации" },
  { key: "logins", label: "Входы" },
  { key: "products", label: "Товары" },
  { key: "reports", label: "Жалобы" },
] as const;

export default async function SystemPage() {
  await requireRole("admin");
  const [state, activity] = await Promise.all([getSystemState(), getActivity(14)]);
  const days = activity?.days ?? [];
  // one scale for the whole table, or a quiet column would look as busy as a loud one
  const peak = Math.max(1, ...days.flatMap((day) => SERIES.map((series) => day[series.key])));

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-10">
      <AdminNav current="system" />
      <p className="text-sm text-ink-muted">
        Текущее состояние, прочитанное в момент запроса. История не хранится: ни таблицы замеров, ни
        фонового сборщика. В контейнере процессор и память — машины, а не контейнера, так что под
        квотой цифры разойдутся с настоящими.
      </p>

      <SystemStateCards initial={state} />

      <section className="flex flex-col gap-2">
        <h2 className="font-medium">Активность за две недели</h2>
        {days.length === 0 ? (
          <p className="text-ink-muted">Данных пока нет.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-xl text-sm">
              <thead>
                <tr className="text-left text-ink-muted">
                  <th className="py-1 font-normal">День</th>
                  {SERIES.map((series) => (
                    <th key={series.key} className="py-1 font-normal">
                      {series.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {days.map((day) => (
                  <tr key={day.day} className="border-t border-ink-muted/15">
                    <td className="py-1 whitespace-nowrap">
                      {new Date(day.day).toLocaleDateString("ru-RU")}
                    </td>
                    {SERIES.map((series) => (
                      <td key={series.key} className="py-1">
                        <span className="inline-flex items-center gap-2">
                          <span className="inline-block h-1.5 w-24 overflow-hidden rounded-full bg-surface-muted align-middle">
                            <span
                              className="block h-full bg-brand"
                              style={{ width: `${(day[series.key] / peak) * 100}%` }}
                            />
                          </span>
                          {day[series.key]}
                        </span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
