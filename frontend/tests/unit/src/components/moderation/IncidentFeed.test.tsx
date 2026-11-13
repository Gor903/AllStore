import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IncidentFeed } from "@/components/moderation/IncidentFeed";
import type { IncidentList } from "@/lib/api";

/**
 * What passed between people, as both panels show it.
 *
 * One component for a moderator's feed and an administrator's: what differs is which events the
 * backend puts in it, not how they look. So the test is about the three states a feed can be in
 * — unreadable, empty, and full — and about the one distinction that is easy to lose: an empty
 * feed means nothing happened, and a null one means we could not find out. Showing "nothing
 * happened" for a backend that is down is how an incident goes unnoticed.
 */

vi.mock("@/components/catalog/Pagination", () => ({
  Pagination: ({ total }: { total: number }) => <nav aria-label="Страницы">{total}</nav>,
}));

function feed(items: IncidentList["items"], total = items.length): IncidentList {
  return { items, total, limit: 20, offset: 0 };
}

const PARAMS = new URLSearchParams();

function show(page: IncidentList | null) {
  render(
    <IncidentFeed
      page={page}
      path="/moderation/incidents"
      params={PARAMS}
      offset={0}
      pageSize={20}
    />,
  );
}

describe("IncidentFeed", () => {
  it("says the feed could not be read, rather than that nothing happened", () => {
    show(null);

    expect(screen.getByText(/лента сейчас недоступна/i)).toBeInTheDocument();
  });

  it("says nothing happened when nothing did", () => {
    show(feed([]));

    expect(screen.getByText("Ничего не происходило.")).toBeInTheDocument();
  });

  it("says how many there are in total, not only how many are on this page", () => {
    show(feed([], 0));

    // an empty page is the empty state; the count belongs to a page with something on it
    expect(screen.queryByText(/всего/i)).not.toBeInTheDocument();
  });

  it("names both sides of an incident and what it was", () => {
    show(
      feed([
        {
          kind: "report",
          happened_at: "2026-11-13T10:00:00Z",
          initiator_email: "buyer@example.am",
          counterpart_email: "shop@example.am",
          subject: "Чашка",
          reason: "Фото чужое",
        },
      ]),
    );

    const entry = screen.getByRole("listitem");
    expect(entry).toHaveTextContent("buyer@example.am");
    expect(entry).toHaveTextContent("shop@example.am");
    expect(entry).toHaveTextContent("жалоба");
    expect(entry).toHaveTextContent("Чашка");
    expect(entry).toHaveTextContent("Фото чужое");
  });

  it("spells out the kind rather than printing its code", () => {
    show(
      feed([
        {
          kind: "customer_block",
          happened_at: "2026-11-13T10:00:00Z",
          initiator_email: "shop@example.am",
          counterpart_email: "buyer@example.am",
          subject: "",
          reason: null,
        },
      ]),
    );

    expect(screen.getByRole("listitem")).toHaveTextContent("магазин закрыт покупателю");
  });

  it("prints a kind it has no words for rather than nothing at all", () => {
    /* A new kind on the backend must not make a line disappear from a feed somebody is
       reading to find out what happened. The cast is the point of the test: the generated
       types say this cannot happen, and between a backend deploy and a regenerated
       api-types.ts it can. */
    show(
      feed([
        {
          kind: "something_new" as IncidentList["items"][number]["kind"],
          happened_at: "2026-11-13T10:00:00Z",
          initiator_email: "a@example.am",
          counterpart_email: "b@example.am",
          subject: "",
          reason: null,
        },
      ]),
    );

    expect(screen.getByRole("listitem")).toHaveTextContent("something_new");
  });

  it("says an account is gone instead of leaving a gap where a name was", () => {
    show(
      feed([
        {
          kind: "report",
          happened_at: "2026-11-13T10:00:00Z",
          initiator_email: null,
          counterpart_email: null,
          subject: "",
          reason: null,
        },
      ]),
    );

    expect(screen.getAllByText("аккаунт удалён")).toHaveLength(2);
  });

  it("counts the whole feed, so a moderator knows what they are looking at", () => {
    show(
      feed(
        [
          {
            kind: "report",
            happened_at: "2026-11-13T10:00:00Z",
            initiator_email: "a@example.am",
            counterpart_email: "b@example.am",
            subject: "",
            reason: null,
          },
        ],
        57,
      ),
    );

    expect(screen.getByText("Всего: 57")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Страницы" })).toHaveTextContent("57");
  });
});
