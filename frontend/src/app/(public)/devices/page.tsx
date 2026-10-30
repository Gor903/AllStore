import type { Metadata } from "next";

import { DeviceList } from "@/components/auth/DeviceList";
import { SecondFactor } from "@/components/auth/SecondFactor";
import { getMyDevices, getSecondFactor, requireUser } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Устройства",
  robots: { index: false, follow: false },
};

/**
 * Outside the role groups on purpose: a buyer, a seller, a moderator and the administrator
 * all have devices, and none of them should have to go through somebody else's cabinet to
 * find the list — the same reasoning that put `/password` here.
 */
export default async function DevicesPage() {
  // the one page a staff account still owing a second factor has to reach
  await requireUser({ owingASecondFactor: true });
  const [devices, secondFactor] = await Promise.all([getMyDevices(), getSecondFactor()]);

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 px-6 py-10">
      <h1 className="text-2xl font-semibold">Устройства</h1>
      <p className="text-sm text-ink-muted">
        Здесь видно, откуда выполнен вход. Если какая-то строка вам незнакома — выйдите на всех
        остальных устройствах и смените пароль: смена пароля тоже завершает все сессии.
      </p>
      {secondFactor === null ? null : <SecondFactor status={secondFactor} />}
      {devices === null ? (
        <p className="text-sm text-danger">Список устройств сейчас недоступен.</p>
      ) : (
        <DeviceList devices={devices.items} />
      )}
    </main>
  );
}
