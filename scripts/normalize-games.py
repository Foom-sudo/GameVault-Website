#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normalize-games.py — 候选游戏归一化
流程：过滤非游戏(DLC/Demo/OST) → 去重 → 转换为 GameVault Schema → 分配 ID
用法：python scripts/normalize-games.py --candidates candidates.json --existing games.json
输出：归一化后的游戏列表（JSON）
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (
    load_env_file, empty_game_schema, next_game_id, is_probable_duplicate,
    determine_status, STEAM_NON_GAME_TYPES, STATUS_COMING_SOON,
    today_str, load_json, save_json,
)


def filter_non_games(candidates):
    """
    过滤明显不是正式游戏的项目（DLC/Demo/Soundtrack/Music/Hardware/Tool）。
    优先使用 Steam type 判断。
    返回 (kept, removed) 列表。
    """
    kept = []
    removed = []
    for cand in candidates:
        steam_data = cand.get("steamData") or {}
        steam_type = (steam_data.get("type") or "").lower()

        reason = None
        if steam_type and steam_type in STEAM_NON_GAME_TYPES:
            reason = f"steam_type={steam_type}"

        # 名称启发式（仅在无 Steam type 时作为辅助）
        if not reason:
            title_lower = (cand.get("title") or "").lower()
            if any(kw in title_lower for kw in ["soundtrack", "ost", "original soundtrack"]):
                reason = "title_contains_soundtrack"
            elif "demo" in title_lower.split() or title_lower.endswith(" demo"):
                reason = "title_contains_demo"

        if reason:
            removed.append({"title": cand.get("title"), "reason": reason})
            print(f"  [过滤] {cand.get('title')[:40]:40s} — {reason}")
        else:
            kept.append(cand)
    return kept, removed


def deduplicate(candidates, existing_games):
    """
    去重：候选之间去重 + 与现有库去重。
    优先级：steamAppId > rawgId > slug > 标题规范化。
    返回 (unique, duplicates)。
    """
    unique = []
    duplicates = []

    # 先在候选内部去重
    seen = []  # 已保留的候选
    for cand in candidates:
        is_dup = False
        dup_reason = None
        for s in seen:
            dup, reason = is_probable_duplicate(s, cand)
            if dup:
                is_dup = True
                dup_reason = reason
                break
        if is_dup:
            duplicates.append({"title": cand.get("title"), "reason": f"候选内重复: {dup_reason}"})
            print(f"  [去重] {cand.get('title')[:40]:40s} — 候选内重复 ({dup_reason})")
            continue

        # 与现有库去重
        for existing in existing_games:
            dup, reason = is_probable_duplicate(existing, cand)
            if dup:
                is_dup = True
                dup_reason = reason
                break
        if is_dup:
            duplicates.append({"title": cand.get("title"), "reason": f"与现有库重复: {dup_reason}"})
            print(f"  [去重] {cand.get('title')[:40]:40s} — 与现有库重复 ({dup_reason})")
            continue

        seen.append(cand)
        unique.append(cand)

    return unique, duplicates


def to_gamevault_schema(cand, existing_games):
    """将候选游戏转换为 GameVault Schema（向后兼容）。"""
    g = empty_game_schema()

    g["id"] = next_game_id(existing_games)
    # 分配后立即加入 existing 列表以避免重复 ID
    existing_games.append({"id": g["id"]})

    g["title"] = cand.get("title", "")
    g["slug"] = cand.get("slug", "")
    g["developer"] = cand.get("developer", "")
    g["publisher"] = cand.get("publisher", "")
    g["releaseDate"] = cand.get("releaseDate", "")
    g["releaseDateTBD"] = cand.get("releaseDateTBD", False)
    g["platforms"] = cand.get("platforms", [])
    g["genres"] = cand.get("genres", [])
    g["tags"] = cand.get("tags", [])
    g["cover"] = cand.get("cover", "")
    g["coverColors"] = ["#1a1f2b", "#2a3040"]  # 默认渐变，前端有 fallback
    g["description"] = cand.get("description", "")
    g["website"] = cand.get("website", "")
    g["externalIds"] = cand.get("externalIds", {"steamAppId": None, "rawgId": None})
    g["storeLinks"] = cand.get("storeLinks", {})
    g["fieldSources"] = cand.get("fieldSources", {})
    g["lastUpdated"] = today_str()

    # 状态判定（前端兼容：仅 released / coming-soon）
    g["status"] = determine_status(g["releaseDate"])

    return g


def normalize(candidates, existing_games):
    """
    主归一化流程。
    返回 dict: {games: [...], removed: [...], duplicates: [...], stats: {...}}
    """
    print(f"\n=== 归一化开始：{len(candidates)} 个候选 ===")

    # 1. 过滤非游戏
    kept, removed = filter_non_games(candidates)
    print(f"[过滤] 保留 {len(kept)}，移除 {len(removed)} 个非游戏")

    # 2. 去重
    unique, duplicates = deduplicate(kept, existing_games)
    print(f"[去重] 保留 {len(unique)}，重复 {len(duplicates)} 个")

    # 3. 转换 Schema
    games = []
    # 复制一份 existing 用于 ID 分配（不修改原列表）
    existing_for_ids = [{"id": g["id"]} for g in existing_games]
    for cand in unique:
        g = to_gamevault_schema(cand, existing_for_ids)
        games.append(g)

    stats = {
        "candidates_total": len(candidates),
        "filtered_out": len(removed),
        "duplicates": len(duplicates),
        "final_new_games": len(games),
    }

    print(f"\n[完成] 新增游戏 {len(games)} 款")
    return {
        "games": games,
        "removed": removed,
        "duplicates": duplicates,
        "stats": stats,
    }


def main():
    parser = argparse.ArgumentParser(description="GameVault 候选游戏归一化")
    parser.add_argument("--candidates", required=True, help="候选游戏 JSON 文件")
    parser.add_argument("--existing", default="games.json", help="现有游戏库 JSON（用于去重）")
    parser.add_argument("--output", help="输出归一化后的 JSON 文件")
    args = parser.parse_args()

    candidates = load_json(args.candidates)
    existing = load_json(args.existing) if os.path.exists(args.existing) else []

    result = normalize(candidates, existing)

    if args.output:
        save_json(args.output, result)
        print(f"已写入 {args.output}")
    else:
        print(json.dumps(result["stats"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
