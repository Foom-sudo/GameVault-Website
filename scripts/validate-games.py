#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate-games.py — 游戏数据 Schema 验证
检查：JSON 合法、Schema 正确、ID 不重复、steamAppId 不重复、日期格式、状态合法、必要字段存在。
验证失败时以非零退出码退出（GitHub Actions 会失败）。
用法：python scripts/validate-games.py --file games.json [--strict]
"""
import sys
import os
import json
import re
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ALLOWED_STATUSES, FRONTEND_STATUSES, load_json


REQUIRED_FIELDS = ["id", "title", "releaseDate", "platforms", "genres", "status", "cover"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_game(g, index, errors, strict=False):
    """验证单个游戏对象。"""
    prefix = f"[{index}] id={g.get('id', '?')} title={g.get('title', '?')[:30]}"

    # 必要字段存在
    for field in REQUIRED_FIELDS:
        if field not in g or g[field] in (None, "", []):
            # cover 允许为空（前端有 fallback），但 strict 模式下警告
            if field == "cover" and not strict:
                continue
            if field in ("platforms", "genres") and not strict:
                continue
            errors.append(f"{prefix}: 缺少必要字段 '{field}'")

    # ID 格式
    gid = g.get("id", "")
    if not re.match(r"^game-\d{3,}$", gid):
        errors.append(f"{prefix}: ID 格式无效 '{gid}'（应为 game-XXX）")

    # status 合法
    status = g.get("status", "")
    if status not in ALLOWED_STATUSES:
        errors.append(f"{prefix}: status 非法 '{status}'（允许: {sorted(ALLOWED_STATUSES)}）")
    elif status not in FRONTEND_STATUSES:
        # delayed/canceled 合法但前端不直接支持，给出警告
        print(f"  [警告] {prefix}: status='{status}' 前端将按 coming-soon 展示")

    # releaseDate 格式
    rd = g.get("releaseDate", "")
    if rd and not DATE_RE.match(rd):
        errors.append(f"{prefix}: releaseDate 格式无效 '{rd}'（应为 YYYY-MM-DD）")
        try:
            datetime.strptime(rd, "%Y-%m-%d")
        except ValueError:
            errors.append(f"{prefix}: releaseDate 不是真实日期 '{rd}'")

    # platforms 是数组
    if not isinstance(g.get("platforms", []), list):
        errors.append(f"{prefix}: platforms 应为数组")

    # genres 是数组
    if not isinstance(g.get("genres", []), list):
        errors.append(f"{prefix}: genres 应为数组")

    # externalIds 结构
    ext = g.get("externalIds")
    if ext is not None and not isinstance(ext, dict):
        errors.append(f"{prefix}: externalIds 应为对象")

    # fieldSources 结构
    fs = g.get("fieldSources")
    if fs is not None and not isinstance(fs, dict):
        errors.append(f"{prefix}: fieldSources 应为对象")


def validate_file(filepath, strict=False):
    """验证整个 JSON 文件。返回错误列表。"""
    errors = []

    # 1. JSON 合法
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"JSON 解析失败: {e}"]
    except FileNotFoundError:
        return [f"文件不存在: {filepath}"]

    # 2. 顶层是数组
    if not isinstance(data, list):
        return ["顶层结构应为数组（游戏列表）"]

    print(f"[验证] 共 {len(data)} 个游戏对象")

    # 3. 逐个验证
    for i, g in enumerate(data):
        if not isinstance(g, dict):
            errors.append(f"[{i}] 不是对象")
            continue
        validate_game(g, i, errors, strict)

    # 4. ID 不重复
    ids = [g.get("id", "") for g in data if isinstance(g, dict)]
    dup_ids = [x for x in set(ids) if ids.count(x) > 1 and x]
    if dup_ids:
        errors.append(f"ID 重复: {dup_ids}")

    # 5. steamAppId 不重复（非空值）
    steam_ids = []
    for g in data:
        if isinstance(g, dict):
            sid = (g.get("externalIds") or {}).get("steamAppId")
            if sid:
                steam_ids.append(str(sid))
    dup_steam = [x for x in set(steam_ids) if steam_ids.count(x) > 1]
    if dup_steam:
        errors.append(f"steamAppId 重复: {dup_steam}")

    # 6. slug 不重复（非空值）
    slugs = [g.get("slug", "").lower() for g in data if isinstance(g, dict) and g.get("slug")]
    dup_slugs = [x for x in set(slugs) if slugs.count(x) > 1]
    if dup_slugs:
        errors.append(f"slug 重复: {dup_slugs}")

    return errors


def main():
    parser = argparse.ArgumentParser(description="GameVault 数据验证")
    parser.add_argument("--file", required=True, help="要验证的 JSON 文件")
    parser.add_argument("--strict", action="store_true", help="严格模式（cover/genres/platforms 也必须非空）")
    args = parser.parse_args()

    errors = validate_file(args.file, args.strict)

    if errors:
        print(f"\n❌ 验证失败，共 {len(errors)} 个错误：")
        for e in errors[:20]:
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  ... 还有 {len(errors) - 20} 个错误")
        sys.exit(1)
    else:
        print(f"\n✅ 验证通过：{args.file}")
        sys.exit(0)


if __name__ == "__main__":
    main()
