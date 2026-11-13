import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import * as codes from "@/lib/api-codes";

/**
 * The few backend error codes a screen reacts to rather than merely prints.
 *
 * Asserting their values against themselves would prove nothing — they are string constants.
 * What can actually break is agreement: the backend renames a code, nothing here fails to
 * compile, and a screen silently stops recognising the thing it exists to handle. A buyer
 * blocked by a shop would see a generic refusal instead of the page explaining it.
 *
 * So the test reads the backend. It is the one place in this tree that does, and the reason is
 * that the contract genuinely lives on the other side.
 */

function backendSources(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      return entry.name === "__pycache__" ? [] : backendSources(path);
    }
    return entry.name.endsWith(".py") ? [readFileSync(path, "utf8")] : [];
  });
}

const sources = backendSources(join(import.meta.dirname, "../../../../../backend/app"));

describe("every code a screen reacts to", () => {
  it("has backend sources to be checked against at all", () => {
    expect(sources.length).toBeGreaterThan(50);
  });

  it.each(Object.entries(codes))("%s is still the backend's own code", (_name, value) => {
    expect(sources.some((source) => source.includes(`code = "${value}"`))).toBe(true);
  });

  it("stays short, because the backend's message is the wording everywhere else", () => {
    // A long list here is a second place for the wording to live and drift. Raising this
    // number is a decision; reaching it by accident is not.
    expect(Object.keys(codes).length).toBeLessThanOrEqual(8);
  });
});
