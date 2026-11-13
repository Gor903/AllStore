import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModeratorStatus } from "@/components/admin/ModeratorStatus";
import type { User } from "@/lib/api";

function moderator(overrides: Partial<User> = {}): User {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    email: "moderator@example.com",
    phone: null,
    role: "moderator",
    status: "active",
    email_verified_at: null,
    created_at: "2026-10-01T10:00:00Z",
    last_login_at: null,
    must_change_password: true,
    password_handed_over_at: "2026-11-10T10:00:00Z",
    ...overrides,
  };
}

describe("состояние выданного пароля", () => {
  it("пароль выдан и ещё не потрачен", () => {
    render(<ModeratorStatus user={moderator()} />);

    expect(screen.getByText(/ждёт первого входа/)).toBeInTheDocument();
    expect(screen.getByText(/10\.11\.2026/)).toBeInTheDocument();
  });

  it("вошёл, но свой пароль ещё не задал", () => {
    render(<ModeratorStatus user={moderator({ last_login_at: "2026-11-11T10:00:00Z" })} />);

    expect(screen.getByText(/вошёл, пароль ещё не сменил/)).toBeInTheDocument();
  });

  it("дошёл до конца: пароль теперь его", () => {
    render(
      <ModeratorStatus
        user={moderator({
          must_change_password: false,
          password_handed_over_at: null,
          last_login_at: "2026-11-11T10:00:00Z",
        })}
      />,
    );

    expect(screen.getByText("пароль свой")).toBeInTheDocument();
  });
});
