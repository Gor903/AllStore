import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// globals: false means Testing Library cannot auto-register its cleanup — do it explicitly.
afterEach(() => {
  cleanup();
  // A stubbed global outlives the test that stubbed it, so the next test silently inherits
  // somebody else's `fetch`. That is a dependency on the order tests happen to run in, and
  // shuffling the order is exactly what found it: a test that never stubbed anything passed
  // for months because a neighbour had.
  vi.unstubAllGlobals();
});
