import { describe, expect, it } from "vitest";

import { accountApiParams, accountSearchParams, parseAccountQuery } from "@/lib/account-query";

function parse(search: string) {
  return parseAccountQuery(new URLSearchParams(search));
}

describe("разбор адреса списка аккаунтов", () => {
  it("читает вкладку, поиск, статус, баны и порядок", () => {
    const query = parse("tab=sellers&q=ваза&status=blocked&has_bans=true&sort=email&offset=40");

    expect(query).toEqual({
      tab: "sellers",
      q: "ваза",
      status: "blocked",
      hasBans: true,
      sort: "email",
      offset: 40,
    });
  });

  it("выдуманные значения читает как «не спрашивали»", () => {
    // a typed address should narrow the list or leave it alone, never fail
    const query = parse("tab=wizards&status=sleepy&sort=by-vibes&offset=-5");

    expect(query.tab).toBeNull();
    expect(query.status).toBeNull();
    expect(query.sort).toBe("registered");
    expect(query.offset).toBe(0);
  });

  it("различает «банов не было» и «не спрашивали»", () => {
    expect(parse("has_bans=false").hasBans).toBe(false);
    expect(parse("").hasBans).toBeNull();
  });
});

describe("перевод в параметры бэкенда", () => {
  it("вкладка становится ролью", () => {
    const params = accountApiParams(parse("tab=moderators"), 20);

    expect(params.getAll("role")).toEqual(["moderator"]);
    expect(params.get("limit")).toBe("20");
  });

  it("вкладка «все» роль не навязывает", () => {
    const params = accountApiParams(parse(""), 20);

    expect(params.getAll("role")).toEqual([]);
  });

  it("не спрашивали про баны — параметра нет", () => {
    expect(accountApiParams(parse(""), 20).has("has_bans")).toBe(false);
    expect(accountApiParams(parse("has_bans=false"), 20).get("has_bans")).toBe("false");
  });
});

describe("обратный перевод в адрес", () => {
  it("порядок по умолчанию в адрес не пишется", () => {
    expect(accountSearchParams(parse("sort=registered")).toString()).toBe("");
  });

  it("фильтры переживают переход на другую страницу", () => {
    const params = accountSearchParams(parse("tab=buyers&status=blocked&q=ова"));

    expect(params.get("tab")).toBe("buyers");
    expect(params.get("status")).toBe("blocked");
    expect(params.get("q")).toBe("ова");
  });
});
