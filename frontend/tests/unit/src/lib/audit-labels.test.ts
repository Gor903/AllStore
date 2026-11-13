/**
 * The journal's captions, checked against the actions the backend actually writes.
 *
 * This file exists because of a bug it would have caught: the screen still knew three actions
 * about moderator invitations that a migration had removed, and did not know the two that
 * replaced them — so an administrator read `moderator.created` as a raw database string. A
 * caption map fails silently in both directions, which is exactly the kind of thing that needs
 * a test rather than a careful reader.
 *
 * It reads the Python source, which is unusual and deliberate: the backend is the authority on
 * what it writes, and any other source of truth here would be a second list to keep in step.
 */

import { execSync } from "node:child_process";

import { describe, expect, it } from "vitest";

import { actionLabel, actorLabel, described, SUBJECTS } from "@/lib/audit-labels";

/** What the backend passes to `audit.record` as the action, wherever it does. */
function actionsTheBackendWrites(): string[] {
  const source = execSync(
    "grep -rhoE '\"[a-z_]+\\.[a-z_]+\"' ../backend/app ../backend/scripts --include='*.py'",
    { encoding: "utf8" },
  );
  const candidates = new Set(source.split("\n").map((line) => line.replaceAll('"', "").trim()));
  // The filter is the subject list the screen already offers. It keeps module paths and the
  // like out, and it has a second use: an action under a prefix nobody can filter by is one
  // an administrator cannot find, so the two lists are worth holding to each other.
  return [...candidates].filter((value) => KNOWN_PREFIXES.some((p) => value.startsWith(p)));
}

const KNOWN_PREFIXES = SUBJECTS.map((subject) => subject.value).filter((value) => value !== "");

/** Written with an f-string, so the grep above cannot see them. */
const BUILT_AT_RUNTIME = ["report.upheld", "report.dismissed"];

describe("the journal's captions", () => {
  it("has one for every action the backend writes", () => {
    const unlabelled = actionsTheBackendWrites().filter((action) => actionLabel(action) === action);

    expect(unlabelled).toEqual([]);
  });

  it("knows the ones the backend builds at runtime", () => {
    for (const action of BUILT_AT_RUNTIME) {
      expect(actionLabel(action)).not.toEqual(action);
    }
  });

  it("reads an action it has never seen as itself rather than as nothing", () => {
    expect(actionLabel("user.something_new")).toEqual("user.something_new");
  });
});

describe("who an entry is attributed to", () => {
  it("names the actor when there is one", () => {
    expect(actorLabel("user.blocked", "admin@example.com")).toEqual("admin@example.com");
  });

  it("does not call a replayed token a deleted account", () => {
    // an empty actor means "deleted" everywhere else, and here it means nobody ever knew
    expect(actorLabel("session.replayed", null)).toEqual("неизвестный");
  });

  it("says where authority granted outside the interface came from", () => {
    expect(actorLabel("user.admin_bootstrapped", null)).toEqual("развёртывание");
    expect(actorLabel("user.role_granted", null)).toEqual("серверная оболочка");
  });

  it("still says deleted for an ordinary action with no actor left", () => {
    expect(actorLabel("user.blocked", null)).toEqual("аккаунт удалён");
  });
});

describe("the details of an entry", () => {
  it("translates the keys it knows and passes through the ones it does not", () => {
    expect(described({ from: "buyer", to: "seller", whatever: 1 })).toEqual(
      "было: buyer, стало: seller, whatever: 1",
    );
  });
});
