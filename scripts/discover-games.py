#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
discover-games.py — 发现目标月份的 PC 游戏
流程：RAWG 发现 → 获取详情 → 提取 Steam App ID → Steam 补全数据 → 输出候选列表
用法：python scripts/discover-games.py --month 2026-10 [--max 50]
输出：stdout JSON 候选列表（供 update-games.py 调用），也可独立运行打印摘要。
"""
import sys
import os
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (
    load_env_file, get_rawg_api_key, HTTPClient,
    RAWG_PLATFORM_PC, STEAM_COVER_URL, STEAM_STORE_URL,
    map_genre, map_platform, field_source, today_str,
)

RAWG_BASE = "https://api.rawg.io/api"


def rawg_discover_month(client, api_key, year, month, max_results=50):
    """
    从 RAWG 发现指定月份发售的 PC 游戏。
    返回 RAWG 游戏列表（精简版）。
    """
    start = f"{year}-{month:02d}-01"
    # 计算月末
    if month == 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{month + 1:02d}-01"
    # dates 参数是 [start,end)，所以 end 用下月1号
    from datetime import timedelta
    end_date = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    results = []
    page = 1
    while len(results) < max_results and page <= 5:  # 最多5页
        params = {
            "key": api_key,
            "platforms": RAWG_PLATFORM_PC,
            "dates": f"{start},{end_date}",
            "ordering": "released",
            "page_size": min(40, max_results),
            "page": page,
        }
        data = client.get_json(f"{RAWG_BASE}/games", params=params)
        if not data or "results" not in data:
            break
        batch = data["results"]
        if not batch:
            break
        results.extend(batch)
        if not data.get("next"):
            break
        page += 1

    print(f"[RAWG] 发现 {len(results[:max_results])} 款候选游戏 ({year}-{month:02d})")
    return results[:max_results]


def rawg_game_detail(client, api_key, slug):
    """获取 RAWG 游戏详情（含 stores、developers、genres 等）。"""
    params = {"key": api_key}
    return client.get_json(f"{RAWG_BASE}/games/{slug}", params=params)


def extract_steam_appid(rawg_detail):
    """从 RAWG 详情的 stores 字段中提取 Steam App ID。"""
    stores = rawg_detail.get("stores", []) or []
    for s in stores:
        store = s.get("store", {})
        if store.get("id") == 1 or store.get("slug") == "steam" or store.get("name", "").lower() == "steam":
            url = s.get("url", "")
            # URL 格式: https://store.steampowered.com/app/12345/Game_Name/
            import re
            m = re.search(r"/app/(\d+)", url)
            if m:
                return m.group(1)
    return None


def steam_appdetails(client, appid):
    """查询 Steam appdetails，返回 data 部分或 None。"""
    url = "https://store.steampowered.com/api/appdetails"
    params = {"appids": appid, "filters": "basic,developers,publishers,genres,release_date,platforms,description"}
    data = client.get_json(url, params=params)
    if not data:
        return None
    entry = data.get(str(appid), {})
    if not entry.get("success"):
        return None
    return entry.get("data")


def build_candidate(rawg_brief, rawg_detail, steam_data, steam_appid):
    """
    合并 RAWG + Steam 数据为候选游戏对象（未归一化，供 normalize 处理）。
    数据优先级：Steam > RAWG。
    """
    today = today_str()
    cand = {
        "title": "",
        "slug": rawg_brief.get("slug", ""),
        "developer": "",
        "publisher": "",
        "releaseDate": "",
        "releaseDateTBD": False,
        "platforms": [],
        "genres": [],
        "tags": [],
        "description": "",
        "website": "",
        "cover": "",
        "externalIds": {
            "steamAppId": steam_appid,
            "rawgId": rawg_brief.get("id"),
        },
        "storeLinks": {},
        "fieldSources": {},
        "rawgData": rawg_brief,
        "steamData": steam_data,
    }

    # ---- 标题：Steam 优先 ----
    if steam_data and steam_data.get("name"):
        cand["title"] = steam_data["name"]
        cand["fieldSources"]["title"] = field_source("steam", today)
    elif rawg_brief.get("name"):
        cand["title"] = rawg_brief["name"]
        cand["fieldSources"]["title"] = field_source("rawg", today)

    # ---- 开发商：Steam 优先 ----
    if steam_data and steam_data.get("developers"):
        cand["developer"] = ", ".join(steam_data["developers"])
        cand["fieldSources"]["developer"] = field_source("steam", today)
    elif rawg_detail and rawg_detail.get("developers"):
        devs = [d.get("name", "") for d in rawg_detail["developers"] if d.get("name")]
        if devs:
            cand["developer"] = ", ".join(devs)
            cand["fieldSources"]["developer"] = field_source("rawg", today)

    # ---- 发行商：Steam 优先 ----
    if steam_data and steam_data.get("publishers"):
        cand["publisher"] = ", ".join(steam_data["publishers"])
        cand["fieldSources"]["publisher"] = field_source("steam", today)
    elif rawg_detail and rawg_detail.get("publishers"):
        pubs = [p.get("name", "") for p in rawg_detail["publishers"] if p.get("name")]
        if pubs:
            cand["publisher"] = ", ".join(pubs)
            cand["fieldSources"]["publisher"] = field_source("rawg", today)

    # ---- 发售日期：Steam 优先 ----
    if steam_data and steam_data.get("release_date"):
        rd = steam_data["release_date"]
        if rd.get("date") and not rd.get("coming_soon"):
            # Steam 日期格式如 "20 Oct, 2026"，尝试解析
            try:
                from datetime import datetime as dt
                parsed = dt.strptime(rd["date"], "%d %b, %Y")
                cand["releaseDate"] = parsed.strftime("%Y-%m-%d")
                cand["fieldSources"]["releaseDate"] = field_source("steam", today)
            except (ValueError, TypeError):
                pass
        if rd.get("coming_soon") and not cand["releaseDate"]:
            cand["releaseDateTBD"] = True
    if not cand["releaseDate"] and rawg_brief.get("released"):
        cand["releaseDate"] = rawg_brief["released"]
        cand["fieldSources"]["releaseDate"] = field_source("rawg", today)
    if not cand["releaseDate"] and rawg_detail and rawg_detail.get("released"):
        cand["releaseDate"] = rawg_detail["released"]
        cand["fieldSources"]["releaseDate"] = field_source("rawg", today)

    # ---- 平台：合并 Steam + RAWG ----
    plats = set()
    if steam_data and steam_data.get("platforms"):
        sp = steam_data["platforms"]
        if sp.get("windows"):
            plats.add("PC")
        # Steam 不直接区分 PS5/Xbox，用 RAWG 补充
    if rawg_detail and rawg_detail.get("platforms"):
        for p in rawg_detail["platforms"]:
            pname = p.get("platform", {}).get("name", "")
            mapped = map_platform(pname)
            if mapped:
                plats.add(mapped)
    elif rawg_brief.get("platforms"):
        for p in rawg_brief["platforms"]:
            pname = p.get("platform", {}).get("name", "")
            mapped = map_platform(pname)
            if mapped:
                plats.add(mapped)
    if not plats:
        plats.add("PC")  # 默认 PC（因为我们按 PC 筛选）
    cand["platforms"] = sorted(plats)

    # ---- 类型：Steam 优先，RAWG 补充 ----
    genres = []
    if steam_data and steam_data.get("genres"):
        for g in steam_data["genres"]:
            mapped = map_genre(g.get("description", ""))
            if mapped and mapped not in genres:
                genres.append(mapped)
        if genres:
            cand["fieldSources"]["genres"] = field_source("steam", today)
    if not genres and rawg_detail and rawg_detail.get("genres"):
        for g in rawg_detail["genres"]:
            mapped = map_genre(g.get("name", ""))
            if mapped and mapped not in genres:
                genres.append(mapped)
        if genres:
            cand["fieldSources"]["genres"] = field_source("rawg", today)
    if not genres and rawg_brief.get("genres"):
        for g in rawg_brief["genres"]:
            mapped = map_genre(g.get("name", ""))
            if mapped and mapped not in genres:
                genres.append(mapped)
    cand["genres"] = genres

    # ---- 标签：RAWG tags ----
    tags = []
    if rawg_detail and rawg_detail.get("tags"):
        for t in rawg_detail["tags"][:10]:
            tname = t.get("name", "").strip()
            if tname and tname not in tags:
                tags.append(tname)
    cand["tags"] = tags

    # ---- 描述：Steam 优先（去除 HTML）----
    import re
    if steam_data and steam_data.get("short_description"):
        desc = re.sub(r"<[^>]+>", "", steam_data["short_description"]).strip()
        if desc:
            cand["description"] = desc[:500]
            cand["fieldSources"]["description"] = field_source("steam", today)
    if not cand["description"] and rawg_detail and rawg_detail.get("description_raw"):
        desc = re.sub(r"<[^>]+>", "", rawg_detail["description_raw"]).strip()
        if desc:
            cand["description"] = desc[:500]
            cand["fieldSources"]["description"] = field_source("rawg", today)

    # ---- 官网 ----
    if steam_data and steam_data.get("website"):
        cand["website"] = steam_data["website"]
    elif rawg_detail and rawg_detail.get("website"):
        cand["website"] = rawg_detail["website"]

    # ---- 封面：Steam CDN 优先，RAWG 补充 ----
    if steam_appid:
        cand["cover"] = STEAM_COVER_URL.format(appid=steam_appid)
        cand["fieldSources"]["cover"] = field_source("steam", today)
        cand["storeLinks"]["steam"] = STEAM_STORE_URL.format(appid=steam_appid)
    elif rawg_brief.get("background_image"):
        cand["cover"] = rawg_brief["background_image"]
        cand["fieldSources"]["cover"] = field_source("rawg", today)
    elif rawg_detail and rawg_detail.get("background_image"):
        cand["cover"] = rawg_detail["background_image"]
        cand["fieldSources"]["cover"] = field_source("rawg", today)

    return cand


def discover(month_str, max_results=50):
    """
    主发现流程。返回候选游戏列表。
    """
    load_env_file()
    api_key = get_rawg_api_key()
    if not api_key:
        print("=" * 60)
        print("错误：未配置 RAWG_API_KEY 环境变量。")
        print("请设置环境变量或在项目根目录创建 .env 文件：")
        print("  RAWG_API_KEY=你的key")
        print("申请免费 Key：https://rawg.io/apidocs")
        print("=" * 60)
        sys.exit(2)

    try:
        year, month = map(int, month_str.split("-"))
    except ValueError:
        print(f"错误：月份格式无效 '{month_str}'，应为 YYYY-MM 格式，如 2026-10")
        sys.exit(1)

    client = HTTPClient(min_interval=0.3)

    # 1. RAWG 发现
    rawg_briefs = rawg_discover_month(client, api_key, year, month, max_results)
    if not rawg_briefs:
        print("[RAWG] 未发现任何游戏，可能是 API 限制或无数据。")
        return []

    # 2. 逐个获取详情 + Steam 补全
    candidates = []
    for i, brief in enumerate(rawg_briefs):
        slug = brief.get("slug", "")
        name = brief.get("name", slug)
        print(f"  [{i + 1}/{len(rawg_briefs)}] {name}")

        # RAWG 详情
        detail = rawg_game_detail(client, api_key, slug) if slug else None

        # 提取 Steam App ID
        steam_appid = None
        steam_data = None
        if detail:
            steam_appid = extract_steam_appid(detail)

        # Steam 补全
        if steam_appid:
            print(f"      → Steam AppID: {steam_appid}")
            steam_data = steam_appdetails(client, steam_appid)
            if steam_data:
                stype = (steam_data.get("type") or "").lower()
                print(f"      → Steam type: {stype}")
            else:
                print(f"      → Steam 无数据或查询失败")
        else:
            print(f"      → 无 Steam AppID（仅 RAWG 数据）")

        cand = build_candidate(brief, detail, steam_data, steam_appid)
        candidates.append(cand)

    print(f"[完成] 共生成 {len(candidates)} 个候选游戏")
    return candidates


def main():
    parser = argparse.ArgumentParser(description="GameVault 游戏发现脚本")
    parser.add_argument("--month", required=True, help="目标月份，格式 YYYY-MM，如 2026-10")
    parser.add_argument("--max", type=int, default=50, help="最多发现数量（默认 50）")
    parser.add_argument("--output", help="输出 JSON 文件路径（默认仅打印摘要）")
    args = parser.parse_args()

    candidates = discover(args.month, args.max)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=2)
        print(f"已写入 {args.output}")
    else:
        # 打印摘要
        print("\n=== 候选游戏摘要 ===")
        for c in candidates:
            steam = c["externalIds"].get("steamAppId") or "-"
            print(f"  {c['title'][:40]:40s} | {c['releaseDate'] or 'TBD':10s} | Steam:{steam}")


if __name__ == "__main__":
    main()
