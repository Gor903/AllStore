import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { BusinessOnboardingForm } from "@/components/dashboard/BusinessOnboardingForm";
import { getMyBusiness, requireUser } from "@/lib/dal";
import { homeFor } from "@/lib/home";

export const metadata: Metadata = {
  title: "Магазин",
  robots: { index: false, follow: false },
};

export default async function OnboardingPage() {
  const user = await requireUser();
  if (user.role !== "seller") {
    redirect(homeFor(user.role));
  }
  // a seller who already has one has nothing to answer here, and the form would refuse anyway
  if ((await getMyBusiness()) !== null) {
    redirect("/dashboard");
  }

  return (
    <main className="mx-auto flex max-w-sm flex-col justify-center gap-6 px-6 py-12">
      <h1 className="text-2xl font-semibold">Расскажите о магазине</h1>
      <p className="text-sm text-ink-muted">
        У вашего аккаунта ещё нет магазина. Чтобы открыть его, нужны ещё два поля — после этого
        заявка уйдёт модератору.
      </p>
      <BusinessOnboardingForm />
    </main>
  );
}
