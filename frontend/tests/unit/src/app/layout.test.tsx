import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { env } from "@/lib/env";

/**
 * The shell every page is rendered inside.
 *
 * Two things in it are load-bearing. `metadataBase` is what every relative address in metadata is
 * resolved against, so without it canonical links and Open Graph images come out relative and a
 * crawler reads them against whatever host it happened to fetch from. And the language is declared
 * on `<html>`, which is what a screen reader reads the page with.
 *
 * `SessionKeeper` renders nothing: it binds this browser's key to the session and keeps it
 * renewed, so it has to be inside the shell rather than on any one page.
 */

vi.mock("@/components/auth/SessionKeeper", () => ({
  SessionKeeper: () => <div data-testid="session-keeper" />,
}));

const layout = await import("@/app/layout");
const RootLayout = layout.default;

describe("the root layout", () => {
  it("resolves metadata addresses against the public site", () => {
    expect(layout.metadata.metadataBase?.toString()).toBe(`${env.siteUrl}/`);
  });

  it("names the site, and lets a page prefix its own title", () => {
    expect(layout.metadata.title).toEqual({
      default: "AllStore.am",
      template: "%s — AllStore.am",
    });
  });

  it("says what the site is, in the language it is in", () => {
    expect(layout.metadata.openGraph?.locale).toBe("ru_RU");
    expect(layout.metadata.description).toMatch(/Магазины Армении/);
  });

  it("renders whatever page it was given", () => {
    render(
      <RootLayout params={Promise.resolve({})}>
        <main data-testid="page" />
      </RootLayout>,
    );

    expect(screen.getByTestId("page")).toBeInTheDocument();
  });

  it("keeps the session alive from inside the shell, not from a page", () => {
    render(
      <RootLayout params={Promise.resolve({})}>
        <main />
      </RootLayout>,
    );

    expect(screen.getByTestId("session-keeper")).toBeInTheDocument();
  });
});
