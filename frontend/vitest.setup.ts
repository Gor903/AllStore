import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// globals: false means Testing Library cannot auto-register its cleanup — do it explicitly.
afterEach(() => {
  cleanup();
});
