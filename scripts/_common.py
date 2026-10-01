# -*- coding: utf-8 -*-
"""
GameVault 数据管道 — 共享工具模块
仅依赖标准库 + requests。所有敏感信息通过环境变量读取。
"""
import os
import re
import json
import time
import hashlib
from datetime import datetime, date

try:
    import requests
except ImportError:
    requests = None

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 前端兼容：status 只能是 "released" 或 "coming-soon"（app.js 硬编码）
STATUS_RELEASED = "released"
STATUS_COMING_SOON = "coming-soon"
STATUS_DELAYED = "delayed"
STATUS_CANCELED = "canceled"
ALLOWED_STATUSES = {STATUS_RELEASED, STATUS_COMING_SOON, STATUS_DELAYED, STATUS_CANCELED}

# 前端筛选中实际使用的状态（delayed/canceled 归为 coming-soon 展示）
FRONTEND_STATUSES = {STATUS_RELEASED, STATUS_COMING_SOON}

# RAWG PC 平台 ID
RAWG_PLATFORM_PC = 4

# Steam 封面 CDN 模板
STEAM_COVER_URL = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg"
STEAM_HEADER_URL = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
STEAM_STORE_URL = "https://store.steampowered.com/app/{appid}/"

# Steam 非游戏类型（排除）
STEAM_NON_GAME_TYPES = {"dlc", "demo", "soundtrack", "music", "hardware", "video",
                        "mod", "episode", "advertising", "other"}

# RAWG 英文类型 → GameVault 中文类型映射（保持与现有库一致）
GENRE_MAP = {
    "action": "动作",
    "action rpg": "动作角色扮演",
    "action-adventure": "动作冒险",
    "adventure": "冒险",
    "rpg": "角色扮演",
    "role-playing": "角色扮演",
    "shooter": "射击",
    "strategy": "策略",
    "puzzle": "益智",
    "simulation": "模拟",
    "sports": "体育",
    "racing": "竞速",
    "fighting": "格斗",
    "platformer": "平台跳跃",
    "horror": "恐怖",
    "indie": "独立",
    "casual": "休闲",
    "card": "卡牌",
    "board": "桌游",
    "educational": "教育",
    "family": "家庭",
    "massively multiplayer": "大型多人在线",
    "mmo": "大型多人在线",
}

# 平台映射 RAWG → GameVault
PLATFORM_MAP = {
    "pc": "PC",
    "playstation 5": "PS5",
    "playstation 4": "PS4",
    "xbox series x/s": "Xbox",
    "xbox one": "Xbox",
    "nintendo switch": "Switch",
}

# 标题规范化：常见 Edition/版本后缀
EDITION_SUFFIXES = [
    r"definitive edition", r"complete edition", r"goty edition",
    r"game of the year", r"deluxe edition", r"ultimate edition",
    r"collector's edition", r"special edition", r"gold edition",
    r"enhanced edition", r"director's cut", r"remastered", r"remake",
    r"hd", r"vr", r"ii", r"iii", r"iv", r"v",
]

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

def load_env_file(path=".env"):
    """从 .env 文件加载环境变量（不覆盖已存在的环境变量）。"""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def get_rawg_api_key():
    """获取 RAWG API Key，不存在时返回 None（调用方负责给出清晰错误）。"""
    return os.environ.get("RAWG_API_KEY", "").strip() or None


def get_project_root():
    """项目根目录（scripts/ 的上一级）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def games_json_path():
    return os.path.join(get_project_root(), "games.json")


def discovered_json_path():
    return os.path.join(get_project_root(), "discovered-games.json")


def logs_dir():
    d = os.path.join(get_project_root(), "logs")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# HTTP 请求（带重试与速率限制）
# ---------------------------------------------------------------------------

class HTTPClient:
    """简单的 HTTP 客户端，带重试、超时、速率限制。"""

    def __init__(self, min_interval=0.3, max_retries=3, timeout=20):
        if requests is None:
            raise RuntimeError("缺少 requests 库，请运行: pip install requests")
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_request = 0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "GameVault-AutoUpdater/1.0 (+https://github.com/gamevault)",
            "Accept": "application/json",
        })

    def _wait(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request = time.time()

    def get_json(self, url, params=None):
        """GET 请求返回 JSON，失败返回 None。"""
        for attempt in range(self.max_retries):
            try:
                self._wait()
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    # 速率限制，退避重试
                    wait = 2 ** (attempt + 1)
                    print(f"  [429] 速率限制，等待 {wait}s 后重试...")
                    time.sleep(wait)
                    continue
                if resp.status_code == 403 or resp.status_code == 401:
                    print(f"  [{resp.status_code}] 认证失败: {url}")
                    return None
                if resp.status_code >= 400:
                    print(f"  [{resp.status_code}] 请求失败: {url}")
                    return None
                return resp.json()
            except Exception as e:
                if attempt == self.max_retries - 1:
                    print(f"  [错误] 请求失败 ({type(e).__name__}): {url} — {e}")
                    return None
                time.sleep(1)
        return None


# ---------------------------------------------------------------------------
# 标题规范化与去重
# ---------------------------------------------------------------------------

def normalize_title(title):
    """
    标题规范化：小写、去标点、压缩空格、去除常见版本后缀。
    用于模糊去重匹配。注意：仅用于匹配判断，不修改原始标题。
    """
    if not title:
        return ""
    t = title.lower()
    # 去除常见版本后缀（仅用于匹配）
    for suffix in EDITION_SUFFIXES:
        t = re.sub(r"\b" + suffix + r"\b", "", t)
    # 去除标点和特殊字符
    t = re.sub(r"[^\w\s]", "", t)
    # 压缩空格
    t = re.sub(r"\s+", " ", t).strip()
    return t


def title_fingerprint(title):
    """生成标题指纹（MD5）用于快速比较。"""
    return hashlib.md5(normalize_title(title).encode("utf-8")).hexdigest()[:12]


def is_probable_duplicate(existing, candidate):
    """
    判断候选游戏是否与已有游戏重复。
    优先级：steamAppId > rawgId > slug > 标题规范化。
    返回 (is_dup, reason)。
    """
    # 1. Steam App ID 精确匹配
    ext_e = existing.get("externalIds", {})
    ext_c = candidate.get("externalIds", {})
    e_steam = ext_e.get("steamAppId")
    c_steam = ext_c.get("steamAppId")
    if e_steam and c_steam and str(e_steam) == str(c_steam):
        return True, f"steamAppId={e_steam}"

    # 2. RAWG ID 精确匹配
    e_rawg = ext_e.get("rawgId")
    c_rawg = ext_c.get("rawgId")
    if e_rawg and c_rawg and str(e_rawg) == str(c_rawg):
        return True, f"rawgId={e_rawg}"

    # 3. slug 精确匹配
    if existing.get("slug") and candidate.get("slug") and \
       existing["slug"].lower() == candidate["slug"].lower():
        return True, f"slug={candidate['slug']}"

    # 4. 标题规范化匹配（需同时开发商相似才判定，避免误杀）
    e_fp = title_fingerprint(existing.get("title", ""))
    c_fp = title_fingerprint(candidate.get("title", ""))
    if e_fp == c_fp and e_fp != "d41d8cd98f00":  # 空字符串的md5前12位
        e_dev = (existing.get("developer") or "").lower()
        c_dev = (candidate.get("developer") or "").lower()
        # 开发商相同或其中一方缺失，才判定重复
        if not e_dev or not c_dev or e_dev == c_dev or \
           e_dev in c_dev or c_dev in e_dev:
            return True, f"title_fingerprint={e_fp}"

    return False, None


# ---------------------------------------------------------------------------
# 类型/平台映射
# ---------------------------------------------------------------------------

def map_genre(raw_genre):
    """RAWG/Steam 英文类型 → GameVault 中文类型。无法映射保留原文。"""
    if not raw_genre:
        return ""
    key = raw_genre.strip().lower()
    return GENRE_MAP.get(key, raw_genre.strip())


def map_platform(raw_platform):
    """RAWG/Steam 平台名 → GameVault 平台名。"""
    if not raw_platform:
        return ""
    key = raw_platform.strip().lower()
    return PLATFORM_MAP.get(key, raw_platform.strip())


# ---------------------------------------------------------------------------
# Schema 构建
# ---------------------------------------------------------------------------

def empty_game_schema():
    """返回一个空的、向后兼容的 GameVault 游戏对象。"""
    return {
        "id": "",
        "title": "",
        "slug": "",
        "developer": "",
        "publisher": "",
        "releaseDate": "",
        "releaseDateTBD": False,
        "platforms": [],
        "genres": [],
        "tags": [],
        "status": STATUS_COMING_SOON,
        "cover": "",
        "coverColors": ["#1a1f2b", "#2a3040"],
        "description": "",
        "website": "",
        "externalIds": {
            "steamAppId": None,
            "rawgId": None,
        },
        "storeLinks": {
            "steam": "",
        },
        "fieldSources": {},
        "lastUpdated": "",
    }


def field_source(source, checked_at=None):
    """生成字段来源记录。"""
    return {
        "source": source,
        "checkedAt": checked_at or date.today().isoformat(),
    }


def determine_status(release_date_str, today=None):
    """根据发售日期确定状态。"""
    if not release_date_str:
        return STATUS_COMING_SOON
    try:
        rd = datetime.strptime(release_date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return STATUS_COMING_SOON
    today = today or date.today()
    return STATUS_RELEASED if rd <= today else STATUS_COMING_SOON


def next_game_id(existing_games):
    """生成下一个游戏 ID（game-XXX 格式，保持与现有一致）。"""
    max_num = 0
    for g in existing_games:
        gid = g.get("id", "")
        m = re.match(r"game-(\d+)", gid)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"game-{max_num + 1:03d}"


# ---------------------------------------------------------------------------
# JSON 读写
# ---------------------------------------------------------------------------

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def today_str():
    return date.today().isoformat()
