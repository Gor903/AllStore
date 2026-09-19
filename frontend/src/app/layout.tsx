import type { Metadata } from "next";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: {
    default: "AllStore.am",
    template: "%s — AllStore.am",
  },
  description: "Платформа магазинов AllStore.am",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru">
      <body className="min-h-screen bg-surface text-ink antialiased">{children}</body>
    </html>
  );
}
