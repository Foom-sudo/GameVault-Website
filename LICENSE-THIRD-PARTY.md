# 依赖与第三方组件 License 声明

GameVault 自动更新管道遵循"零额外成本、最小依赖"原则，仅使用以下成熟开源组件：

## Python 依赖

| 组件 | 版本 | License | 用途 |
|------|------|---------|------|
| [requests](https://github.com/psf/requests) | >=2.28.0 | Apache 2.0 | HTTP 请求（RAWG / Steam API） |

> 所有其他功能（JSON 处理、日期计算、去重、规范化、验证）均使用 Python 标准库实现，无额外依赖。

## GitHub Actions

| Action | 版本 | License | 用途 |
|--------|------|---------|------|
| [actions/checkout](https://github.com/actions/checkout) | v4 | MIT | 检出仓库代码 |
| [actions/setup-python](https://github.com/actions/setup-python) | v5 | MIT | 配置 Python 环境 |
| [peter-evans/create-pull-request](https://github.com/peter-evans/create-pull-request) | v6 | MIT | 自动创建 Pull Request（不直接 push 到 main） |

## 数据源

| 数据源 | 类型 | 认证方式 | 用途 |
|--------|------|----------|------|
| [RAWG.io API](https://rawg.io/apidocs) | 免费 REST API | API Key（环境变量） | 游戏发现、元数据 |
| [Steam Store API](https://store.steampowered.com/api/appdetails) | 公开 REST API | 无需认证 | 数据补全、验证、Steam App ID |

> 封面图片直接引用 Steam CDN / RAWG URL，不下载到仓库，避免仓库膨胀。

## 选型说明

实施前调研了以下方向，确认无需引入更重的依赖：
- **Steam API 封装库**（如 steam, steamapi）：功能可用但增加依赖，Steam 公开接口仅需简单 GET 请求，`requests` 足够。
- **RAWG SDK**：非官方且维护状态不明，直接 REST 调用更稳定。
- **数据验证库**（如 jsonschema）：Schema 简单，手写验证逻辑更可控且零依赖。
- **IGDB / Twitch API**：第一阶段明确不接入，避免 OAuth 复杂度。

所有第三方组件的最新 License 文本请访问其各自仓库获取。
