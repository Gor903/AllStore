import type { Metadata } from "next";

import { SiteHeader } from "@/components/SiteHeader";
import { AssistantChat } from "@/components/assistant/AssistantChat";

export const metadata: Metadata = {
  title: "Помощник",
  description:
    "Опишите своими словами, что вы ищете, — помощник найдёт товары в каталоге AllStore.am.",
  alternates: { canonical: "/assistant" },
};

/**
 * Rendered per request, which this page does not otherwise need: the Content-Security-Policy
 * carries a fresh nonce and Next.js can only attach it while rendering. Prerendered at build
 * time there is no nonce to attach, and the page's own scripts would be the ones refused.
 */
export const dynamic = "force-dynamic";

export default function AssistantPage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-2">
          <h1 className="text-3xl font-semibold tracking-tight">Помощник</h1>
          <p className="text-ink-muted">
            Опишите словами, что нужно, — помощник поищет по каталогу и покажет, что нашёл. Он
            говорит только о товарах, которые есть на площадке.
          </p>
        </div>
        <AssistantChat />
      </main>
    </>
  );
}
