#!/usr/bin/env python3
"""Тест, прошедший со второй попытки, — это не зелёный тест.

Playwright в CI перезапускает упавший сценарий один раз. Без этого скрипта такой прогон
заканчивается зелёной галочкой: в логе есть слово flaky, но галочка зелёная, а значит никто
не посмотрит. Через месяц таких сценариев три, и падение одного из них читается как «ну это
же флака», — после чего e2e перестаёт что-либо значить.

Поэтому: прогон, в котором что-то прошло со второй попытки, красный. Чинить надо тест или то,
что он поймал, а не отношение к нему. Трассировка второй попытки лежит в отчёте, который job
выкладывает артефактом как раз потому, что этот скрипт сделал прогон красным.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def flaky(report: dict[str, Any]) -> list[str]:
    """Отчёт — дерево сьютов произвольной глубины; заголовок собирается по пути вниз."""
    found: list[str] = []
    for suite in report.get("suites", []):
        found.extend(_flaky_in(suite, prefix=""))
    return found


def _flaky_in(suite: dict[str, Any], prefix: str) -> Iterator[str]:
    title = f"{prefix}{suite.get('title', '')}".strip()
    for spec in suite.get("specs", []):
        for test in spec.get("tests", []):
            if test.get("status") == "flaky":
                attempts = len(test.get("results", []))
                yield f"{title} › {spec.get('title', '')} (попыток: {attempts})"
    for nested in suite.get("suites", []):
        yield from _flaky_in(nested, prefix=f"{title} › " if title else "")


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "frontend/playwright-report/results.json")
    if not path.exists():
        print(f"отчёт не найден: {path}", file=sys.stderr)
        return 2
    report = json.loads(path.read_text())
    unstable = flaky(report)
    if not unstable:
        print("со второй попытки не прошло ничего")
        return 0
    print("прошли только со второй попытки:", file=sys.stderr)
    for name in unstable:
        print(f"  {name}", file=sys.stderr)
    print(
        "\nТрассировка второй попытки — в артефакте playwright-report.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
