# GameVault — 个人游戏数据库

> 你的下一款游戏，藏在这座 Vault 里。

收录即将发售与已发售的精选游戏，搜索、筛选、收藏，打造属于你自己的游戏资料库。
纯静态网站（HTML + CSS + Vanilla JS），Netlify 免费部署，零服务器成本。

## 项目结构

```
GameVault/
├── index.html              # 前端页面（不修改）
├── style.css               # 样式（不修改）
├── app.js                  # 前端逻辑（不修改，fetch games.json）
├── games.json              # 正式游戏库（人工审核后合并）
├── images/                 # 本地封面图
├── discovered-games.json   # 自动发现的候选游戏（待审核，不直接使用）
├── scripts/                # Python 数据管道
│   ├── _common.py          # 共享工具（Schema/HTTP/去重/映射）
│   ├── discover-games.py   # RAWG 发现 + Steam 补全
│   ├── normalize-games.py  # 过滤/去重/Schema 转换
│   ├── validate-games.py   # Schema 验证（失败则 CI 失败）
│   └── update-games.py     # 统一入口（编排全流程）
├── logs/                   # 每次运行的变更日志
├── .github/workflows/
│   └── update-games.yml    # GitHub Actions 自动更新 + 自动 PR
├── requirements.txt        # Python 依赖（仅 requests）
├── .env.example            # 环境变量示例（不含真实 Key）
├── .gitignore              # 防止 .env 等敏感文件提交
├── LICENSE-THIRD-PARTY.md  # 第三方组件 License 声明
└── README.md
```

## 自动化架构（零额外成本）

```
RAWG (发现游戏)
    ↓
Steam (补全/验证，Steam 数据优先)
    ↓
Python 管道 (过滤 DLC/Demo → 去重 → Schema 归一化 → 验证)
    ↓
discovered-games.json (候选数据，绝不直接覆盖正式库)
    ↓
GitHub Actions (每天自动运行 + 手动指定月份)
    ↓
自动创建 Pull Request (peter-evans/create-pull-request)
    ↓
人工审核 → Merge → games.json → Netlify 自动部署
```

### 关键设计原则

1. **前端零修改**：`index.html` / `style.css` / `app.js` 完全不变。新增字段对前端透明。
2. **向后兼容 Schema**：保留原有 14 个字段，新增 `slug` / `externalIds` / `storeLinks` / `fieldSources` / `lastUpdated`。
3. **状态兼容**：前端使用 `coming-soon`（非 `upcoming`），管道输出保持一致。
4. **Steam 优先**：每个重要字段记录来源（`fieldSources`），Steam > RAWG。
5. **去重四层**：steamAppId → rawgId → slug → 标题规范化（+开发商校验，避免误杀）。
6. **过滤非游戏**：优先用 Steam `type` 字段排除 DLC/Demo/Soundtrack 等。
7. **封面不入库**：直接引用 Steam CDN URL，避免仓库膨胀；前端有 onerror fallback。
8. **API Key 安全**：`RAWG_API_KEY` 仅通过环境变量/GitHub Secrets 读取，`.env` 已 gitignore。

## 快速开始

### 1. 配置 RAWG API Key

免费申请：https://rawg.io/apidocs

**本地运行**：复制 `.env.example` 为 `.env`，填入 Key。
**GitHub Actions**：在仓库 Settings → Secrets and variables → Actions 中添加 `RAWG_API_KEY`。

### 2. 本地运行

```bash
pip install -r requirements.txt

# 更新指定月份的 PC 游戏（生成 discovered-games.json + 日志）
python scripts/update-games.py --month 2026-10

# 仅发现游戏
python scripts/discover-games.py --month 2026-10 --output candidates.json

# 验证正式游戏库
python scripts/validate-games.py --file games.json

# 干跑（不写文件）
python scripts/update-games.py --month 2026-10 --dry-run
```

### 3. GitHub Actions

- **自动运行**：每天 UTC 02:17（北京时间 10:17），默认发现下月新游戏。
- **手动运行**：Actions → Update Games Data → Run workflow → 输入月份（如 `2026-10`）。
- **自动 PR**：发现新游戏后自动创建分支和 Pull Request，标题 `[auto] Update games for YYYY-MM`，审核后合并。

## 数据 Schema（向后兼容）

```json
{
  "id": "game-053",
  "title": "Example Game",
  "slug": "example-game",
  "developer": "Example Studio",
  "publisher": "Example Publisher",
  "releaseDate": "2026-10-15",
  "releaseDateTBD": false,
  "platforms": ["PC", "PS5"],
  "genres": ["动作角色扮演"],
  "tags": ["开放世界", "单人"],
  "status": "coming-soon",
  "cover": "https://cdn.cloudflare.steamstatic.com/steam/apps/123456/library_600x900.jpg",
  "coverColors": ["#1a1f2b", "#2a3040"],
  "description": "游戏简介...",
  "website": "https://example.com",
  "externalIds": { "steamAppId": "123456", "rawgId": 98765 },
  "storeLinks": { "steam": "https://store.steampowered.com/app/123456/" },
  "fieldSources": {
    "title": { "source": "steam", "checkedAt": "2026-09-30" },
    "releaseDate": { "source": "steam", "checkedAt": "2026-09-30" }
  },
  "lastUpdated": "2026-09-30"
}
```

> 加粗字段为新增，原有字段完全保留。前端仅读取原有字段，新增字段不影响渲染。

## 变更日志

每次自动运行生成 `logs/YYYY-MM-DD.json`，记录：
- 新增游戏 / 过滤移除 / 去重移除
- 发售日期变化 / 状态变化
- 潜在冲突（需人工确认）

## 第一阶段明确不做

PostgreSQL / MongoDB / Redis / Docker / VPS / 微服务 / GraphQL / Kubernetes / 付费 SaaS / AI API / IGDB / 本地封面镜像 / 复杂后台管理系统。

当前：Python + GitHub Actions + RAWG + Steam + JSON + Netlify 即可。
