import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogStore } from "@/lib/api";

/**
 * The listing of shops.
 *
 * Three states, and the test is about telling two of them apart: "the list could not be read"
 * and "no shop has opened yet" look the same to anybody who only checks for an empty page, and
 * they mean opposite things — one is our problem and the other is a stage of the project.
 */

vi.mock("@/lib/api", () => ({
  PAGE_SIZE: 24,
  fetchCatalogStores: vi.fn(),
}));

const { fetchCatalogStores } = await import("@/lib/api");
const { default: StoresPage } = await import("@/app/(public)/stores/page");

function store(subdomain: string, displayName: string): CatalogStore {
  return {
    subdomain,
    display_name: displayName,
    description: null,
    logo_url: null,
    banner_url: null,
    contacts: [],
  };
}

const props = (offset?: string) => ({
  params: Promise.resolve({}),
  searchParams: Promise.resolve(offset === undefined ? {} : { offset }),
});

beforeEach(() => {
  vi.mocked(fetchCatalogStores).mockReset();
});

describe("stores page", () => {
  it("shows the shops there are", async () => {
    vi.mocked(fetchCatalogStores).mockResolvedValue({
      items: [store("cups", "Лавка кружек"), store("wool", "Шерсть")],
      total: 2,
      limit: 24,
      offset: 0,
    });

    render(await StoresPage(props()));

    expect(screen.getByRole("heading", { name: "Магазины", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Лавка кружек")).toBeInTheDocument();
    expect(screen.getByText("Шерсть")).toBeInTheDocument();
  });

  it("says the list could not be read when it could not", async () => {
    vi.mocked(fetchCatalogStores).mockResolvedValue(null);

    render(await StoresPage(props()));

    expect(screen.getByText(/список сейчас недоступен/i)).toBeInTheDocument();
  });

  it("says no shop has opened yet when none has", async () => {
    vi.mocked(fetchCatalogStores).mockResolvedValue({
      items: [],
      total: 0,
      limit: 24,
      offset: 0,
    });

    render(await StoresPage(props()));

    expect(screen.getByText(/пока ни один магазин не открыт/i)).toBeInTheDocument();
    expect(screen.queryByText(/недоступен/i)).not.toBeInTheDocument();
  });

  it("asks for the page the address bar names", async () => {
    vi.mocked(fetchCatalogStores).mockResolvedValue({
      items: [store("cups", "Лавка кружек")],
      total: 48,
      limit: 24,
      offset: 24,
    });

    render(await StoresPage(props("24")));

    expect(fetchCatalogStores).toHaveBeenCalledWith(24);
  });

  it("asks for the first page when the address bar says something impossible", async () => {
    /* `?offset=-5` is a typed address, not an attack, and it should narrow the list or leave
       it alone rather than fail. */
    vi.mocked(fetchCatalogStores).mockResolvedValue({
      items: [],
      total: 0,
      limit: 24,
      offset: 0,
    });

    render(await StoresPage(props("-5")));

    expect(fetchCatalogStores).toHaveBeenCalledWith(0);
  });
});
