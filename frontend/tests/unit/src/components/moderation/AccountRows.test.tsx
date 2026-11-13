import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountRows } from "@/components/moderation/AccountRows";
import type { User } from "@/lib/api";

/**
 * One list of accounts, shared by the administrator's screen and the moderator's.
 *
 * The rows are identical because the action is: barring somebody is one decision in the access
 * matrix, and who may take it against whom is settled by the backend's ranks. The panels differ
 * in what else they may do — roles and appointments are the administrator's — which is what the
 * `extra` slot is for.
 *
 * The viewer's own row is marked and carries no verdicts. A moderator who can bar themselves
 * has a way to lock the platform's own staff out of it by mis-clicking.
 */

vi.mock("@/components/moderation/VerdictButtons", () => ({
  VerdictButtons: ({ basePath, verdicts }: { basePath: string; verdicts: { label: string }[] }) => (
    <div data-testid="verdicts" data-base={basePath}>
      {verdicts.map((verdict) => (
        <span key={verdict.label}>{verdict.label}</span>
      ))}
    </div>
  ),
}));

vi.mock("@/components/moderation/BlockHistory", () => ({
  BlockHistory: ({ email }: { email: string }) => <div data-testid="history">{email}</div>,
}));

const VIEWER = "11111111-1111-1111-1111-111111111111";
const OTHER = "22222222-2222-2222-2222-222222222222";

function account(overrides: Partial<User> = {}): User {
  return {
    id: OTHER,
    email: "person@example.am",
    role: "buyer",
    status: "active",
    ...overrides,
  } as User;
}

describe("AccountRows", () => {
  it("names the account and says what it is", () => {
    render(<AccountRows items={[account()]} viewerId={VIEWER} />);

    const row = screen.getByRole("listitem");
    expect(row).toHaveTextContent("person@example.am");
    expect(row).toHaveTextContent("покупатель");
    expect(row).toHaveTextContent("активен");
  });

  it("spells out a role and a status rather than printing their codes", () => {
    render(
      <AccountRows items={[account({ role: "moderator", status: "blocked" })]} viewerId={VIEWER} />,
    );

    const row = screen.getByRole("listitem");
    expect(row).toHaveTextContent("модератор");
    expect(row).toHaveTextContent("заблокирован");
  });

  it("prints a role it has no words for rather than nothing at all", () => {
    /* The cast is the point: the generated types say this cannot happen, and between a
       backend deploy and a regenerated api-types.ts it can — and a row that silently lost
       its role would be a row a moderator reads without noticing anything is missing. */
    const unknownRole = { role: "auditor" } as unknown as Partial<User>;

    render(<AccountRows items={[account(unknownRole)]} viewerId={VIEWER} />);

    expect(screen.getByRole("listitem")).toHaveTextContent("auditor");
  });

  it("offers a ban for an account that has none", () => {
    render(<AccountRows items={[account()]} viewerId={VIEWER} />);

    expect(screen.getByTestId("verdicts")).toHaveTextContent("Заблокировать");
    expect(screen.getByTestId("verdicts")).toHaveAttribute("data-base", `/accounts/${OTHER}`);
  });

  it("offers to lift one for an account that has", () => {
    render(<AccountRows items={[account({ status: "blocked" })]} viewerId={VIEWER} />);

    expect(screen.getByTestId("verdicts")).toHaveTextContent("Разблокировать");
  });

  it("marks the viewer's own row", () => {
    render(<AccountRows items={[account({ id: VIEWER })]} viewerId={VIEWER} />);

    expect(screen.getByRole("listitem")).toHaveTextContent("это вы");
  });

  it("offers nobody a verdict against themselves", () => {
    render(<AccountRows items={[account({ id: VIEWER })]} viewerId={VIEWER} />);

    expect(screen.queryByTestId("verdicts")).not.toBeInTheDocument();
  });

  it("still shows their own history, which is a fact and not an action", () => {
    render(<AccountRows items={[account({ id: VIEWER })]} viewerId={VIEWER} />);

    expect(screen.getByTestId("history")).toBeInTheDocument();
  });

  it("renders whatever the panel adds between the name and the verdicts", () => {
    render(
      <AccountRows
        items={[account()]}
        viewerId={VIEWER}
        extra={(item) => <span data-testid="extra">{item.email}</span>}
      />,
    );

    expect(screen.getByTestId("extra")).toHaveTextContent("person@example.am");
  });

  it("adds nothing where the panel has nothing to add", () => {
    render(<AccountRows items={[account()]} viewerId={VIEWER} />);

    expect(screen.queryByTestId("extra")).not.toBeInTheDocument();
  });

  it("is one list rather than a row of loose blocks", () => {
    render(
      <AccountRows
        items={[account(), account({ id: "33333333-3333-3333-3333-333333333333" })]}
        viewerId={VIEWER}
      />,
    );

    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});
