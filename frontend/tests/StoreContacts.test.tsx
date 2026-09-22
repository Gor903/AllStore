import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StoreContacts } from "@/components/StoreContacts";
import type { Contact } from "@/lib/api";

const contact = (platform: Contact["platform"], value: string, href: string): Contact => ({
  platform,
  value,
  href,
});

describe("store contacts", () => {
  it("renders nothing at all when the seller left none", () => {
    const { container } = render(<StoreContacts contacts={[]} heading="Связаться" />);

    expect(container).toBeEmptyDOMElement();
  });

  it("uses the address the backend built, not one of its own", () => {
    render(
      <StoreContacts
        contacts={[
          contact("phone", "+37410123456", "tel:+37410123456"),
          contact("whatsapp", "+37410123456", "https://wa.me/37410123456"),
          contact("viber", "+37410123456", "viber://chat?number=%2B37410123456"),
        ]}
      />,
    );

    expect(screen.getByRole("link", { name: /Телефон/u })).toHaveAttribute(
      "href",
      "tel:+37410123456",
    );
    expect(screen.getByRole("link", { name: /WhatsApp/u })).toHaveAttribute(
      "href",
      "https://wa.me/37410123456",
    );
    expect(screen.getByRole("link", { name: /Viber/u })).toHaveAttribute(
      "href",
      "viber://chat?number=%2B37410123456",
    );
  });

  it("shows a handle as a handle and a number as a number", () => {
    render(
      <StoreContacts
        contacts={[
          contact("telegram", "mystore", "https://t.me/mystore"),
          contact("instagram", "my.store", "https://instagram.com/my.store"),
          contact("facebook", "my.store", "https://facebook.com/my.store"),
          contact("phone", "+37410123456", "tel:+37410123456"),
        ]}
      />,
    );

    expect(screen.getByText("@mystore")).toBeInTheDocument();
    expect(screen.getByText("@my.store")).toBeInTheDocument();
    // facebook pages are not addressed by @handle, so the name stands as written
    expect(screen.getByText("my.store")).toBeInTheDocument();
    expect(screen.getByText("+37410123456")).toBeInTheDocument();
  });

  it("opens a profile in a new tab and dials in place", () => {
    render(
      <StoreContacts
        contacts={[
          contact("telegram", "mystore", "https://t.me/mystore"),
          contact("phone", "+37410123456", "tel:+37410123456"),
          contact("viber", "+37410123456", "viber://chat?number=%2B37410123456"),
        ]}
      />,
    );

    const profile = screen.getByRole("link", { name: /Telegram/u });
    expect(profile).toHaveAttribute("target", "_blank");
    // without this an opened tab could reach back into the shop through window.opener
    expect(profile).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", { name: /Телефон/u })).not.toHaveAttribute("target");
    expect(screen.getByRole("link", { name: /Viber/u })).not.toHaveAttribute("target");
  });

  it("shows the heading only when it is given", () => {
    const phone = [contact("phone", "+37410123456", "tel:+37410123456")];
    const { rerender } = render(<StoreContacts contacts={phone} heading="Связаться" />);
    expect(screen.getByText("Связаться")).toBeInTheDocument();

    rerender(<StoreContacts contacts={phone} />);

    expect(screen.queryByText("Связаться")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Телефон/u })).toBeInTheDocument();
  });
});
