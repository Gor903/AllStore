import type { Metadata } from "next";
import "@/styles/globals.css";

import { SessionKeeper } from "@/components/auth/SessionKeeper";
import { env } from "@/lib/env";

const DESCRIPTION =
  "Магазины Армении в одном каталоге: товары, витрины и прямой контакт с продавцом.";

export const metadata: Metadata = {
  // every relative address in metadata is resolved against this, so canonical links and
  // Open Graph images come out absolute
  metadataBase: new URL(env.siteUrl),
  title: {
    default: "AllStore.am",
    template: "%s — AllStore.am",
  },
  description: DESCRIPTION,
  openGraph: {
    siteName: "AllStore.am",
    locale: "ru_RU",
    type: "website",
    title: "AllStore.am",
    description: DESCRIPTION,
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru">
      <body className="min-h-screen bg-surface text-ink antialiased">
        {children}
        {/* renders nothing; binds this browser's key to the session and keeps it renewed */}
        <SessionKeeper />
      </body>
    </html>
  );
}
