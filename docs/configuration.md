# 1. MusicPilot 配置教程

本文档说明首次启动 MusicPilot 后需要完成的配置。推荐按本文顺序配置：先准备目录和环境变量，再在 Web UI 中配置站点、下载器、音乐库、系统设置和通知。

## 1.1. 配置边界

MusicPilot 的配置分为两类：

1. 启动配置：通过环境变量或 `.env` 设置，决定服务如何启动、数据库放在哪里、容器内目录挂载到哪里。
2. 运行配置：通过 Web UI 写入数据库，包含站点、下载器、音乐库用户、通知渠道、代理、刮削和搜索设置。

通常只有部署路径、管理员账号、数据库地址、容器挂载目录和站点解析器文件需要放在环境变量中。站点账号、下载器、音乐库、通知和刮削规则应优先在 Web UI 中维护。

## 1.2. 首次启动前准备

部署前建议先确认以下目录：

| 目录 | 用途 | Docker 示例 |
| --- | --- | --- |
| 数据目录 | 保存导入导出文件等运行数据；使用 SQLite 时也保存 SQLite 数据库文件 | `./data:/data` |
| PostgreSQL 数据目录 | 持久化默认 PostgreSQL 数据库 | `./postgres:/var/lib/postgresql/data` |
| 配置目录 | 保存自定义站点解析器等配置文件 | `./config:/config` |
| 音乐库目录 | MusicPilot 整理后的音乐库目录，也是 Navidrome 应扫描的目录 | `/volume1/music:/music` |
| 下载目录 | qBittorrent 保存音乐资源的目录 | `/volume1/downloads:/downloads` |

如果 qBittorrent 和 MusicPilot 不在同一个容器或看到的路径不同，需要在下载器配置中同时填写“下载目录”和“本机对应目录”。例如 qBittorrent 保存路径是 `/downloads/music`，MusicPilot 容器中对应挂载路径是 `/downloads/music`，两项可以相同；如果 qBittorrent 返回的是 NAS 路径 `/volume1/downloads/music`，而 MusicPilot 容器内看到的是 `/downloads/music`，则需要分别填写这两个路径。

## 1.3. 启动环境变量

常用环境变量如下：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MP_APP_NAME` | `MusicPilot` | 应用名称。 |
| `MP_LOG_LEVEL` | `INFO` | 日志级别。 |
| `MP_ADMIN_USERNAME` | `admin` | 管理员登录账号。 |
| `MP_ADMIN_PASSWORD` | `musicpilot` | 管理员登录密码，生产环境必须修改。 |
| `MP_SESSION_SECRET` | `musicpilot-dev-session-secret` | 会话密钥，生产环境必须改成随机长字符串。 |
| `MP_DATABASE_URL` | `postgresql+asyncpg://musicpilot:musicpilot-change-me@postgres:5432/musicpilot` | 数据库连接串。默认使用 PostgreSQL；SQLite 仅适合测试和快速试用。 |
| `MP_MUSIC_LIBRARY_PATH` | `./data/library` | 音乐库目录。Docker 部署通常设置为 `/music`。 |
| `MP_DOWNLOAD_STAGING_PATH` | `./data/downloads` | 下载暂存目录。Docker 部署通常设置为 `/downloads`。 |
| `MP_STATIC_DIR` | `frontend/dist` | 前端静态文件目录，镜像内通常是 `/app/frontend/dist`。 |
| `MP_SYSTEM_INDEXER_PARSER_CONFIG` | `config/sites.parser.yaml` | 系统内置站点解析器文件，一般不需要修改。 |
| `MP_INDEXER_PARSER_CONFIG` | `config/sites.parser.yaml` | 用户自定义站点解析器文件。Docker 部署通常设置为 `/config/sites.parser.yaml`。 |
| `MP_RUNTIME_CONFIG` | `config/runtime.json` | 旧版运行配置迁移入口。新配置保存到数据库中，通常不需要手工编辑该文件。 |
| `MP_MUSICBRAINZ_USER_AGENT` | `MusicPilot/0.1.0 (...)` | 访问 MusicBrainz 时使用的 User-Agent。 |
| `MP_WRITE_AUDIO_TAGS` | `true` | 是否写入音频标签。 |
| `MP_SUBSCRIPTIONS_ENABLED` | `true` | 是否启用订阅检查。 |
| `MP_SUBSCRIPTION_CHECK_INTERVAL_MINUTES` | `1440` | 订阅检查间隔，单位分钟。 |

Docker Compose 中至少应修改管理员密码、会话密钥和 PostgreSQL 密码：

```yaml
environment:
  MP_ADMIN_USERNAME: admin
  MP_ADMIN_PASSWORD: change-this-password
  MP_SESSION_SECRET: change-this-random-secret
  MP_DATABASE_URL: postgresql+asyncpg://musicpilot:musicpilot-change-me@postgres:5432/musicpilot
  MP_MUSIC_LIBRARY_PATH: /music
  MP_DOWNLOAD_STAGING_PATH: /downloads
  MP_INDEXER_PARSER_CONFIG: /config/sites.parser.yaml
```

## 1.4. 数据库选择

MusicPilot 支持 SQLite 和 PostgreSQL，默认使用 PostgreSQL。SQLite 部署简单，可作为备用方案用于本地开发、测试或快速试用；在任务较多、并发较高或长期运行时可能出现性能下降和数据库锁竞争问题。

推荐 PostgreSQL 的原因：

1. 下载轮询、任务队列、歌单同步、媒体库刷新和日志/状态更新会持续写入运行数据。
2. 多个后台任务同时推进时，PostgreSQL 的并发和锁处理比 SQLite 更稳妥。
3. 备份、恢复、迁移和观测能力更适合长期维护。
4. 后续如果扩展到更多站点、歌单和订阅，PostgreSQL 更容易承载增长后的数据量。

如果使用外部 PostgreSQL，把 `MP_DATABASE_URL` 改成对应的连接串：

```yaml
MP_DATABASE_URL: postgresql+asyncpg://musicpilot:change-this-password@postgres:5432/musicpilot
```

默认的 `docker-compose.yml` 已经包含 PostgreSQL 服务。核心配置如下：

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: musicpilot
      POSTGRES_USER: musicpilot
      POSTGRES_PASSWORD: change-this-password
    volumes:
      - ./postgres:/var/lib/postgresql/data
    restart: unless-stopped

  musicpilot:
    environment:
      MP_DATABASE_URL: postgresql+asyncpg://musicpilot:change-this-password@postgres:5432/musicpilot
    depends_on:
      postgres:
        condition: service_healthy
```

生产环境不要复用示例密码。首次启动前应确认 PostgreSQL 数据目录已经持久化，并把数据库备份纳入日常备份策略。若确实需要使用 SQLite，将 `MP_DATABASE_URL` 改为 `sqlite+aiosqlite:////data/musicpilot.db`，并保留 `/data` 挂载；SQLite 可能不适合高并发或长期运行场景。

## 2. Web UI 配置顺序

首次登录后进入“系统管理 / 设置”，建议按以下顺序配置：

1. 系统设置：先保存代理、刮削和搜索参数。
2. 站点：添加资源站点，并确认站点解析器可用。
3. 下载器：添加 qBittorrent，并测试连接。
4. 音乐库：添加 Navidrome，并测试连接。
5. 通知：按需添加 Telegram 通知渠道。
6. 歌单和订阅：基础配置可用后再导入歌单或启用订阅。

## 2.1. 系统设置

系统设置包含网络设置、刮削设置、搜索设置和数据库管理。

### 2.1.1. 网络设置

网络设置提供系统代理，供明确启用代理的站点和通知渠道使用。

| 字段 | 说明 |
| --- | --- |
| 代理地址 | 可以填 `127.0.0.1`、`http://127.0.0.1:7890`、`socks5://127.0.0.1:7890` 等。 |
| 端口 | 当代理地址没有包含端口时，在这里填写端口。 |
| 用户名 / 密码 | 代理需要认证时填写。 |

如果站点或通知渠道未开启“使用系统代理”，保存代理后也不会影响它们。

### 2.1.2. 刮削设置

刮削用于在下载完成或手动整理文件时补齐元数据、歌词、标签和目标路径。

| 字段 | 可选值 | 说明 |
| --- | --- | --- |
| 开启刮削 | 开 / 关 | 关闭后不会自动执行刮削流程。 |
| 刮削类型 | 源文件、映射文件、复制文件 | 控制处理后的文件来源和落点。 |
| 源文件目录 | 路径 | 手动整理时的源目录。 |
| 映射目录 / 复制目录 | 路径 | 选择“映射文件”或“复制文件”时填写。 |
| 缺失时尝试刮削 | 专辑、艺术家、歌词 | 当这些字段缺失时尝试在线补齐。 |
| 缺失则判定失败 | 专辑、艺术家、歌词 | 这些字段仍缺失时，本次整理视为失败。 |
| 自动重命名 | 开 / 关 | 根据元数据重命名文件。 |
| 自动分类 | 开 / 关 | 根据艺术家或专辑建立分类目录。 |
| 分类方式 | 艺术家、专辑 | 开启自动分类后生效。 |
| 重复文件处理 | 不处理、总是覆盖、保留最大文件 | 决定目标位置已有文件时如何处理。 |

重复文件处理的行为：

1. `ignore`：目标文件已存在时跳过。
2. `overwrite`：目标文件已存在时覆盖。
3. `keep_largest`：只保留体积更大的文件。

### 2.1.3. 搜索设置

| 字段 | 说明 |
| --- | --- |
| 排除关键词 | 用 `|` 分隔多个关键词。站点搜索结果标题命中任一关键词时会被过滤。 |
| 最少做种人数 | 仅显示做种人数不小于该值的种子。默认 `1`，可避免下载死种；设为 `0` 可关闭筛选。 |
| 元数据搜索并发数 | 控制同时访问元数据源的搜索任务数量。默认 `3`；遇到频率限制时可降到 `1` 或 `2`。 |

## 2.2. 站点配置

站点配置用于保存资源站点账号信息。当前支持 NexusPHP 类站点，站点必须能在解析器配置中匹配到对应 `base_url`。

| 字段 | 说明 |
| --- | --- |
| 站点名称 | 显示名称。 |
| 站点地址 | 站点根地址，例如 `https://open.cd`。 |
| Cookie | 登录后的站点 Cookie。 |
| User-Agent | 访问站点时使用的 User-Agent；站点有风控要求时建议填写浏览器中的值。 |
| 最大并发 | 单站点并发请求数，范围 `1` 到 `10`。 |
| 启用站点 | 关闭后搜索不会使用该站点。 |
| 使用系统代理 | 开启后该站点请求会使用系统代理。 |

保存站点时，如果提示“当前站点暂不支持，请先在 sites.parser.yaml 中配置解析器”，说明该站点地址没有匹配到内置或自定义解析器。

## 2.3. 站点解析器配置

站点解析器文件用于描述如何从站点搜索结果页提取标题、详情页、下载链接、大小、发布时间和促销信息。Docker 部署时默认读取：

```text
/config/sites.parser.yaml
```

镜像内还包含一份系统解析器配置。启动时会先读取系统解析器，再读取 `MP_INDEXER_PARSER_CONFIG` 指向的用户解析器；如果两个文件里配置了相同站点主机，以用户解析器为准。

本地开发时默认读取：

```text
config/sites.parser.yaml
```

一个解析规则可以绑定多个站点：

```yaml
sites:
  - targets:
      - name: OpenCD
        base_url: https://open.cd
      - name: HDFans
        base_url: https://hdfans.org/
    parser:
      list_selector: "table.torrents tr:has(a[href*='details.php']):has(a[href*='download.php'])"
      fields:
        title:
          selector: "a[href*='details.php']"
          filters: ["collapse_space"]
        details:
          selector: "a[href*='details.php']"
          attribute: "href"
        download:
          selector: "a[href*='download.php']"
          attribute: "href"
```

常用字段：

| 字段 | 说明 |
| --- | --- |
| `targets` | 使用同一解析规则的站点列表。 |
| `parser.list_selector` | 搜索结果列表中每个种子条目的 CSS 选择器。 |
| `parser.search_query_param` | 搜索关键词参数名，默认 `search`。 |
| `parser.search_params` | 搜索时固定附加的查询参数。 |
| `parser.fields.title` | 种子标题。 |
| `parser.fields.subtitle` | 副标题或描述。 |
| `parser.fields.details` | 详情页地址。 |
| `parser.fields.download` | 下载链接，必填。 |
| `parser.fields.size` | 文件大小。 |
| `parser.fields.published_at` | 发布时间。 |
| `parser.fields.promotion` | 免费、优惠等促销信息。 |
| `parser.fields.seeders` | 做种数。 |
| `parser.fields.leechers` | 下载数。 |
| `parser.filter` | 对解析结果进行包含或排除过滤。 |

字段规则支持：

| 配置 | 说明 |
| --- | --- |
| `selector` | CSS 选择器。 |
| `attribute` | 读取属性，常用 `text`、`href`、`text+attrs`、`titles`。 |
| `regex` | 从读取结果中提取指定片段。 |
| `index` | 当选择器匹配多个节点时取第几个。 |
| `remove` | 提取前移除指定内容。 |
| `filters` | 预置过滤器，例如 `collapse_space`、`category`、`date`、`promotion`。 |

修改解析器文件后，需要重启服务或容器，使解析器重新加载。

## 2.4. 下载器配置

当前下载器类型为 qBittorrent。

| 字段 | 说明 |
| --- | --- |
| 类型 | 固定为 `qbittorrent`。 |
| 名称 | 显示名称。 |
| 地址 | qBittorrent Web UI 地址，例如 `http://192.168.1.10:8080`。 |
| 用户名 / 密码 | qBittorrent Web UI 登录账号。 |
| 下载目录 | 提交给 qBittorrent 的保存路径。 |
| 本机对应目录 | MusicPilot 读取已下载文件时使用的本机或容器内路径。 |
| 监听模式 | 目前使用“轮询”；“qB 回调”为预留选项。 |
| 设为默认 | 搜索结果和歌单下载默认提交到该下载器。 |
| 启用 | 关闭后不会使用该下载器。 |

路径配置示例：

| 场景 | 下载目录 | 本机对应目录 |
| --- | --- | --- |
| qBittorrent 与 MusicPilot 同容器路径一致 | `/downloads/music` | `/downloads/music` |
| qBittorrent 在 NAS 上返回宿主路径，MusicPilot 在容器内读取 | `/volume1/downloads/music` | `/downloads/music` |
| Windows 本地开发 | `D:\Downloads\music` | `D:\Downloads\music` |

下载完成后的整理流程依赖“本机对应目录”能被 MusicPilot 访问。如果测试连接成功但下载完成后找不到文件，优先检查这两个目录是否正确映射。

## 2.5. 音乐库配置

当前音乐库类型为 Navidrome。MusicPilot 会使用 Navidrome 查询曲库、刷新曲库，并把本地歌单同步到 Navidrome。

| 字段 | 说明 |
| --- | --- |
| 类型 | 固定为 `navidrome`。 |
| 名称 | 显示名称。 |
| 地址 | Navidrome 地址，例如 `http://192.168.1.10:4533`。 |
| API Token | 预留字段，可留空。 |
| 默认用户名 / 默认用户密码 | 用于连接 Navidrome 的默认账号。 |
| 启用 | 关闭后不会使用该音乐库。 |

保存音乐库配置后，页面会生成默认用户账号。需要用不同 Navidrome 用户同步歌单时，可以在“用户账号”中新增用户。默认账号请在上方音乐库配置中编辑。

Navidrome 自身也需要能扫描到 MusicPilot 整理后的音乐库目录。Docker 部署时，建议让 Navidrome 和 MusicPilot 指向同一个宿主机音乐目录。

## 2.6. 通知配置

当前通知类型为 Telegram。

| 字段 | 说明 |
| --- | --- |
| 类型 | 固定为 `telegram`。 |
| 名称 | 显示名称。 |
| Bot Token | Telegram Bot Token。 |
| Webhook URL | 预留或扩展用地址，可按实际部署填写。 |
| Chat IDs | 接收通知的 Chat ID，多个目标按当前 Bot 使用习惯填写。 |
| 使用系统代理 | 开启后发送通知时使用系统代理。 |
| 下载通知 | 下载相关事件是否通知。 |
| 媒体库刷新通知 | 媒体库刷新相关事件是否通知。 |
| 启用 | 关闭后不发送该渠道通知。 |

如果 Telegram 在部署环境无法直连，先在系统设置中保存代理，再在该通知渠道开启“使用系统代理”。

## 2.7. 数据库导入导出

“系统设置 / 数据库管理”提供数据库导出和导入。

1. 导出数据库会生成一个 ZIP 文件，可用于备份或迁移。
2. 导入数据库会用目标数据替换当前本地数据，导入前应先导出现有数据库作为备份。
3. 导入完成后，系统会重新加载站点、下载器和通知配置。

## 3. 歌单同步配置

歌单功能依赖基础配置：

1. 已配置可用的站点，用于搜索资源。
2. 已配置默认下载器，用于提交下载。
3. 已配置可用的 Navidrome，用于刷新曲库和同步歌单。
4. 已完成音乐库扫描，使本地曲库中存在可匹配的歌曲。

同步到 Navidrome 时，可以选择音乐库用户和公开状态。MusicPilot 会优先使用已持久化的本地曲库歌曲 ID 构建歌单，不会仅靠标题重新匹配。

## 4. 常见问题

### 4.1. 站点保存时提示不支持

检查 `sites.parser.yaml` 中是否存在相同主机名的 `base_url`。匹配时会忽略 `www.`，但协议、主机和实际站点仍应保持一致。修改解析器后重启服务再保存站点。

### 4.2. 下载器测试成功但下载完成后无法整理

检查下载器的“下载目录”和“本机对应目录”。前者是 qBittorrent 保存文件时看到的路径，后者是 MusicPilot 读取文件时看到的路径。容器部署时尤其容易出现 NAS 路径和容器挂载路径不一致。

### 4.3. 站点或通知没有走代理

保存系统代理后，还需要分别在站点或通知渠道开启“使用系统代理”。未开启的配置不会使用系统代理。

### 4.4. Navidrome 测试失败

确认 Navidrome 地址可以从 MusicPilot 所在环境访问，并确认用户名、密码正确。容器部署时还要确认 MusicPilot 容器和 Navidrome 容器或宿主机网络可互通。

### 4.5. 刮削结果缺少专辑、艺术家或歌词

检查“缺失时尝试刮削”和“缺失则判定失败”。如果某个字段被设置为“缺失则判定失败”，在线源也没有补齐该字段时，本次整理会失败并记录原因。

### 4.6. 数据库迁移或换机后配置丢失

确认迁移的是“数据库导出”生成的 ZIP，或者完整保留了 `MP_DATABASE_URL` 指向的数据库文件。仅复制 `config/sites.parser.yaml` 只会迁移站点解析器，不会迁移 Web UI 中保存的站点、下载器、音乐库和通知配置。
