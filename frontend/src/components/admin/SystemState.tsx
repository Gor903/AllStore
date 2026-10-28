"use client";

import { useEffect, useState } from "react";

import { apiGet } from "@/lib/browser-api";
import type { SystemState } from "@/lib/api";

/** Often enough to watch, rarely enough that watching costs nothing. */
const REFRESH_MS = 15_000;

function hours(seconds: number): string {
  const days = Math.floor(seconds / 86_400);
  const rest = Math.floor((seconds % 86_400) / 3_600);
  return days > 0 ? `${days} д ${rest} ч` : `${rest} ч`;
}

type Tile = { label: string; value: string; share?: number };

function tilesOf(state: SystemState): Tile[] {
  return [
    { label: "Процессор", value: `${state.cpu_percent.toFixed(0)} %`, share: state.cpu_percent },
    {
      label: "Память",
      value: `${state.memory_used_mb} из ${state.memory_total_mb} МБ`,
      share: state.memory_percent,
    },
    {
      label: "Диск",
      value: `${state.disk_free_gb} ГБ свободно из ${state.disk_total_gb}`,
      share: state.disk_percent,
    },
    { label: "Аптайм", value: hours(state.uptime_seconds) },
    { label: "База данных", value: `${state.database_size_mb} МБ` },
    { label: "Живых сессий", value: String(state.live_sessions) },
    { label: "Пользователей", value: String(state.users) },
    { label: "Продавцов", value: String(state.sellers) },
    { label: "Товаров", value: String(state.products) },
    { label: "Заявок ждут", value: String(state.businesses_pending) },
    { label: "Жалоб открыто", value: String(state.reports_open) },
  ];
}

export function SystemStateCards({ initial }: { initial: SystemState | null }) {
  const [state, setState] = useState(initial);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const result = await apiGet<SystemState>("/admin/system");
      if (!alive) {
        return;
      }
      // a failed refresh keeps the last numbers and says they are old: blanking the page
      // would turn a hiccup into an outage on the one screen meant to report outages
      setStale(!result.ok);
      if (result.ok) {
        setState(result.data);
      }
    };
    const timer = setInterval(tick, REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  if (state === null) {
    return (
      <p className="text-danger">Состояние сейчас недоступно, попробуйте обновить страницу.</p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {stale ? (
        <p role="status" className="text-sm text-ink-muted">
          Последнее обновление не прошло — цифры ниже могли устареть.
        </p>
      ) : null}
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {tilesOf(state).map((tile) => (
          <div
            key={tile.label}
            className="flex flex-col gap-1 rounded-card border border-ink-muted/20 p-4"
          >
            <dt className="text-sm text-ink-muted">{tile.label}</dt>
            <dd className="text-lg font-semibold">{tile.value}</dd>
            {tile.share === undefined ? null : (
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
                <div
                  className={tile.share > 90 ? "h-full bg-danger" : "h-full bg-brand"}
                  style={{ width: `${Math.min(100, tile.share)}%` }}
                />
              </div>
            )}
          </div>
        ))}
      </dl>
    </div>
  );
}
