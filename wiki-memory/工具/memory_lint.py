#!/usr/bin/env python3
"""检查 ChatWechat 工程记忆，并重建单一工作日志索引。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


REQUIRED = {"type", "status", "kind", "importance", "updated", "topic"}
MANAGED = {"当前状态", "决策", "知识", "日志"}
ALLOWED_TYPES = {"state", "decision", "knowledge", "log", "moc"}
ALLOWED_STATUSES = {"active", "proposed", "deprecated", "superseded", "archived"}


def parse(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, text
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip().strip('"')
    return fields, "\n".join(lines[end + 1 :])


def pages(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.md") if path.relative_to(root).parts[0] in MANAGED)


def title(body: str, fallback: str) -> str:
    return next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), fallback)


def links(body: str) -> list[str]:
    return [match.split("|", 1)[0].strip() for match in re.findall(r"\[\[([^\]]+)\]\]", body)]


def check(root: Path) -> int:
    errors: list[str] = []
    found = pages(root)
    known = {path.relative_to(root).with_suffix("").as_posix() for path in root.rglob("*.md")}
    topics: dict[tuple[str, str], list[str]] = {}
    all_bodies: list[str] = []
    for path in found:
        fields, body = parse(path)
        all_bodies.append(body)
        rel = path.relative_to(root).as_posix()
        missing = REQUIRED - fields.keys()
        if missing:
            errors.append(f"{rel}: 缺少字段 {', '.join(sorted(missing))}")
        if fields.get("type") and fields["type"] not in ALLOWED_TYPES:
            errors.append(f"{rel}: type 无效")
        if fields.get("status") and fields["status"] not in ALLOWED_STATUSES:
            errors.append(f"{rel}: status 无效")
        if fields.get("status") == "active" and fields.get("type") in {"state", "decision"}:
            topics.setdefault((fields["type"], fields.get("topic", "")), []).append(rel)
        for target in links(body):
            if target not in known:
                errors.append(f"{rel}: 断链 {target}")
    for key, paths in topics.items():
        if key[1] and len(paths) > 1:
            errors.append(f"重复 active 主题 {key}: {', '.join(paths)}")
    combined = "\n".join(all_bodies)
    for path in found:
        fields, _ = parse(path)
        if fields.get("type") == "log" and path.name != "README.md":
            marker = f"日志/{path.stem}"
            if marker not in combined:
                errors.append(f"{path.relative_to(root).as_posix()}: 未进入日志索引")
    if errors:
        print(f"记忆体检失败：{len(errors)} 个问题")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"记忆体检通过：检查 {len(found)} 个受管页面。")
    return 0


def index(root: Path) -> int:
    rows: list[tuple[str, str, str, str, str, str]] = []
    for path in (root / "日志").glob("*.md"):
        fields, body = parse(path)
        if fields.get("type") != "log":
            continue
        goal = next((line.split("：", 1)[1].strip() for line in body.splitlines() if line.startswith("- 目标：")), "-")
        rows.append((fields.get("updated", "-"), fields.get("kind", "-"), goal, fields.get("status", "-"), fields.get("topic", "-"), title(body, path.stem)))
    rows.sort(reverse=True)
    output = root / "日志" / "MOC_工作日志.md"
    lines = [
        "---", "type: moc", "status: active", "kind: process", "importance: high",
        f"updated: {rows[0][0] if rows else '2026-08-23'}", "topic: work-log-index",
        "source_logs: []", "supersedes: null", "---", "", "# 工作日志 MOC", "",
        "| 时间 | 类型 | 目标 | 状态 | 主题 | 日志 |", "| --- | --- | --- | --- | --- | --- |",
    ]
    for date, kind, goal, status, topic, page_title in rows:
        stem = next(path.stem for path in (root / "日志").glob("*.md") if title(parse(path)[1], path.stem) == page_title)
        lines.append(f"| {date} | {kind} | {goal.replace('|', '｜')} | {status} | {topic} | [[日志/{stem}|{page_title.replace('|', '｜')}]] |")
    lines.extend(["", "## 入口", "", "- [[README|工程记忆]]", "- [[AGENTS|记忆维护协议]]", "- [[当前状态/项目概览|项目概览]]", "- [[当前状态/系统架构|系统架构]]", ""])
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成日志索引：{output.relative_to(root).as_posix()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check", "index"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    return check(root) if args.command == "check" else index(root)


if __name__ == "__main__":
    raise SystemExit(main())
