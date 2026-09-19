import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/StatusBadge";

describe("StatusBadge", () => {
  it("reports a healthy dependency", () => {
    render(<StatusBadge label="Backend" healthy={true} />);

    expect(screen.getByTestId("status-badge")).toHaveTextContent("Backend: доступен");
  });

  it("reports an unhealthy dependency", () => {
    render(<StatusBadge label="Backend" healthy={false} />);

    expect(screen.getByTestId("status-badge")).toHaveTextContent("Backend: недоступен");
  });
});
