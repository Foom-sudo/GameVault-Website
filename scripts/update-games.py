#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update-games.py — GameVault 自动更新统一入口
流程：discover → normalize → validate → 追加到 games.json + discovered-games.json + 变更日志
所有变更通过 Pull Request 审核，人工合并后网站自动更新。
用法：python scripts/update-games.py --month 2026-10 [--max 50] [--dry-run]
"""
import sys
import os
import json
import argparse
import importlib.util
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (
    load_env_file, get_rawg_api_key, today_str,
    games_json_path, discovered_json_path, logs_dir,
    load_json, save_json, is_probable_duplicate,
)

# 脚本文件名含连字符（符合项目规范），需用 importlib 动态加载
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_SCRIPTS_DIR, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

discover_games = _load_module("discover_games", "discover-games.py")
normalize_games = _load_module("normalize_games", "normalize-games.py")
validate_games = _load_module("validate_games", "validate-games.py")


def detect_changes(new_games, existing_games):
    """
    检测变更：新增、发售日期变化、状态变化、平台变化等。
    由于新游戏不会直接合并，这里主要记录新增游戏和与现有库的潜在冲突。
    """
    changes = {
        "added": [],
        "releaseDateChanges": [],
        "statusChanges": [],
        "potentialConflicts": [],
    }

    existing_by_steam = {}
    existing_by_rawg = {}
    for g in existing_games:
        ext = g.get("externalIds", {})
        if ext.get("steamAppId"):
            existing_by_steam[str(ext["steamAppId"])] = g
        if ext.get("rawgId"):
            existing_by_rawg[str(ext["rawgId"])] = g

    for ng in new_games:
        changes["added"].append({
            "id": ng["id"],
            "title": ng["title"],
            "releaseDate": ng.get("releaseDate", ""),
            "steamAppId": (ng.get("externalIds") or {}).get("steamAppId"),
        })

        # 检查与现有游戏的潜在冲突（可能是同一游戏的更新）
        for eg in existing_games:
            dup, reason = is_probable_duplicate(eg, ng)
            if dup:
                conflict = {
                    "newTitle": ng["title"],
                    "existingId": eg["id"],
                    "existingTitle": eg["title"],
                    "reason": reason,
                }
                # 发售日期变化
                if eg.get("releaseDate") and ng.get("releaseDate") and \
                   eg["releaseDate"] != ng["releaseDate"]:
                    changes["releaseDateChanges"].append({
                        "id": eg["id"],
                        "title": eg["title"],
                        "old": eg["releaseDate"],
                        "new": ng["releaseDate"],
                    })
                    conflict["releaseDateChanged"] = True
                # 状态变化
                if eg.get("status") and ng.get("status") and eg["status"] != ng["status"]:
                    changes["statusChanges"].append({
                        "id": eg["id"],
                        "title": eg["title"],
                        "old": eg["status"],
                        "new": ng["status"],
                    })
                changes["potentialConflicts"].append(conflict)
                break

    return changes


def write_changelog(month, result, changes):
    """写入变更日志 logs/YYYY-MM-DD.json。"""
    log = {
        "date": today_str(),
        "month": month,
        "stats": result.get("stats", {}),
        "added": changes["added"],
        "removed": result.get("removed", []),
        "duplicates": result.get("duplicates", []),
        "releaseDateChanges": changes["releaseDateChanges"],
        "statusChanges": changes["statusChanges"],
        "potentialConflicts": changes["potentialConflicts"],
    }
    log_path = os.path.join(logs_dir(), f"{today_str()}.json")
    save_json(log_path, log)
    print(f"[日志] 变更日志已写入: logs/{today_str()}.json")
    return log_path


def write_discovered(new_games, month):
    """写入 discovered-games.json（候选数据记录，保留用于审计）。"""
    output = {
        "generatedAt": today_str(),
        "month": month,
        "source": "auto-pipeline (RAWG + Steam)",
        "reviewStatus": "pending-review",
        "games": new_games,
    }
    save_json(discovered_json_path(), output)
    print(f"[候选] discovered-games.json 已写入（{len(new_games)} 款，保留作审计记录）")


def merge_to_games_json(new_games, existing_games):
    """
    将新游戏追加到正式 games.json（重新分配连续 ID）。
    PR 审核合并后网站即更新，无需手动合并。
    返回更新后的完整游戏列表。
    """
    import re
    merged = list(existing_games)
    max_num = 0
    for g in existing_games:
        m = re.match(r"game-(\d+)", g.get("id", ""))
        if m:
            max_num = max(max_num, int(m.group(1)))
    for i, g in enumerate(new_games):
        g["id"] = f"game-{max_num + 1 + i:03d}"
        merged.append(g)
    save_json(games_json_path(), merged)
    print(f"[正式库] games.json 已更新：{len(existing_games)} → {len(merged)} 款（新增 {len(new_games)}）")
    return merged


def generate_pr_summary(month, result, changes):
    """生成 PR 摘要文本（供 GitHub Actions 使用）。"""
    stats = result.get("stats", {})
    lines = [
        f"## 自动更新摘要 — {month}",
        f"",
        f"- **新增游戏**: {len(changes['added'])} 款",
        f"- **过滤非游戏**: {stats.get('filtered_out', 0)} 款 (DLC/Demo/OST 等)",
        f"- **去重移除**: {stats.get('duplicates', 0)} 款",
        f"- **发售日期变化**: {len(changes['releaseDateChanges'])} 项",
        f"- **状态变化**: {len(changes['statusChanges'])} 项",
        f"- **潜在冲突需人工确认**: {len(changes['potentialConflicts'])} 项",
        f"",
        f"### 新增游戏列表",
    ]
    for g in changes["added"][:30]:
        rd = g.get("releaseDate") or "TBD"
        steam = g.get("steamAppId") or "-"
        lines.append(f"- {g['title']} ({rd}, Steam:{steam})")
    if len(changes["added"]) > 30:
        lines.append(f"- ... 共 {len(changes['added'])} 款，详见 discovered-games.json")

    if changes["potentialConflicts"]:
        lines.append("")
        lines.append("### ⚠️ 需人工确认的潜在冲突")
        for c in changes["potentialConflicts"][:10]:
            lines.append(f"- 新游戏「{c['newTitle']}」可能与现有 {c['existingId']}「{c['existingTitle']}」重复（{c['reason']}）")

    lines.append("")
    lines.append("---")
    lines.append("**合并此 PR 后，games.json 即更新，Netlify 自动部署，网站直接生效。**")
    lines.append("*此 PR 由 GameVault 自动更新管道生成。请审核新增游戏后合并。*")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="GameVault 自动更新统一入口")
    parser.add_argument("--month", required=True, help="目标月份 YYYY-MM，如 2026-10")
    parser.add_argument("--max", type=int, default=50, help="最多发现数量（默认 50）")
    parser.add_argument("--dry-run", action="store_true", help="仅运行流程，不写文件")
    parser.add_argument("--pr-summary", help="输出 PR 摘要到指定文件")
    args = parser.parse_args()

    print("=" * 60)
    print(f"GameVault 自动更新 — 目标月份: {args.month}")
    print("=" * 60)

    load_env_file()

    # 0. 检查 API Key（给出清晰错误而非崩溃）
    if not get_rawg_api_key():
        print("\n❌ 错误：未配置 RAWG_API_KEY 环境变量。")
        print("   请在 GitHub Secrets 中配置 RAWG_API_KEY，或本地创建 .env 文件。")
        print("   申请免费 Key: https://rawg.io/apidocs")
        sys.exit(2)

    # 1. 加载现有游戏库（只读，不修改）
    existing = load_json(games_json_path()) if os.path.exists(games_json_path()) else []
    print(f"[现有库] {len(existing)} 款游戏（只读，不会被修改）")

    # 2. Discover: RAWG → Steam
    print("\n--- 阶段 1/4: 发现游戏 (RAWG + Steam) ---")
    candidates = discover_games.discover(args.month, args.max)
    if not candidates:
        print("\n⚠️ 未发现任何候选游戏，流程结束。")
        # 仍然写一个空日志
        if not args.dry_run:
            log = {
                "date": today_str(), "month": args.month,
                "stats": {"candidates_total": 0},
                "added": [], "note": "未发现候选游戏",
            }
            save_json(os.path.join(logs_dir(), f"{today_str()}.json"), log)
        sys.exit(0)

    # 3. Normalize: 过滤 + 去重 + Schema
    print("\n--- 阶段 2/4: 归一化 (过滤/去重/Schema) ---")
    result = normalize_games.normalize(candidates, existing)
    new_games = result["games"]

    # 4. Validate: 验证新游戏数据
    print("\n--- 阶段 3/4: 验证 Schema ---")
    if new_games:
        # 临时写入验证
        tmp_path = os.path.join(logs_dir(), "_validate_tmp.json")
        save_json(tmp_path, new_games)
        errors = validate_games.validate_file(tmp_path)
        os.remove(tmp_path)
        if errors:
            print(f"\n❌ 验证失败，共 {len(errors)} 个错误：")
            for e in errors[:10]:
                print(f"  - {e}")
            print("\n候选数据未写入 discovered-games.json。")
            sys.exit(1)
        print("✅ 新游戏数据验证通过")

    # 5. 变更检测
    print("\n--- 阶段 4/4: 变更检测与输出 ---")
    changes = detect_changes(new_games, existing)

    # 6. 输出：候选记录 + 正式库更新 + 变更日志
    if not args.dry_run:
        write_discovered(new_games, args.month)
        if new_games:
            merge_to_games_json(new_games, existing)
        write_changelog(args.month, result, changes)
    else:
        print("[dry-run] 跳过文件写入")

    # PR 摘要
    pr_summary = generate_pr_summary(args.month, result, changes)
    if args.pr_summary:
        with open(args.pr_summary, "w", encoding="utf-8") as f:
            f.write(pr_summary)
        print(f"[PR摘要] 已写入 {args.pr_summary}")
    else:
        print("\n" + pr_summary)

    print("\n" + "=" * 60)
    print(f"✅ 流程完成：新增 {len(new_games)} 款游戏已写入 games.json")
    print("   所有变更通过 Pull Request 提交，人工审核合并后网站自动更新。")
    print("=" * 60)


if __name__ == "__main__":
    main()
