# MusicPilot

<p align="center">
  <img src="docs/assets/musicpilot-logo.png" alt="MusicPilot" width="420">
</p>

语言：[简体中文](README.md) | [English](README_EN.md)

## 1. 项目简介

MusicPilot 是一个面向自托管用户的音乐库自动化工具，用来把“发现音乐、搜索资源、提交下载、整理文件、补全元数据、刷新音乐库、同步歌单”串成一个可管理的工作流。

它适合已经搭建好音乐库、下载器和资源站点的用户：MusicPilot 不替代这些系统，也不提供下载渠道，而是负责把已有服务连接起来，减少重复搜索、手动下载、手动整理和手动刷新音乐库的操作。

项目的核心目标：

1. 用一个 Web 界面管理音乐搜索、下载、整理、歌单和音乐库状态。
2. 通过任务队列处理耗时操作，尽量让下载、刮削、整理和同步可以自动推进。
3. 保持部署简单，默认使用 PostgreSQL，并提供 Docker Compose 方式在 NAS 或服务器上运行；SQLite 作为备用数据库用于测试和快速试用。
4. 保留清晰的适配层，方便后续接入更多站点、下载器、音乐平台、元数据源和媒体服务器。

## 2. 支持范围

媒体库支持：

- [x] Navidrome

下载器支持：

- [x] qBittorrent

站点支持：

- [x] OpenCD
- [x] HDFans

## 3. 项目功能

MusicPilot 当前提供以下能力：

1. 音乐搜索与站点搜索
   - 支持先搜索音乐元数据，再基于元数据到站点搜索候选资源。
   - 支持站点并发控制、排除关键词和搜索结果去重。
   - 支持按艺术家、标题、专辑等信息辅助过滤候选结果。

2. 下载任务管理
   - 支持把选中的资源提交到 qBittorrent。
   - 支持下载任务状态跟踪、下载明细查看和任务删除。
   - 支持下载完成后触发后续整理和音乐库刷新流程。

3. 文件整理与元数据处理
   - 支持源目录、映射目录、复制整理等模式。
   - 支持自动刮削、手动整理、歌词和标签写入。
   - 支持记录每个文件的整理状态、失败原因和实际整理类型。

4. 歌单管理
   - 支持导入外部歌单并在本地管理歌单条目。
   - 支持根据歌单条目搜索、下载和匹配本地音乐库。
   - 支持把本地歌单同步到 Navidrome 音乐库，并可选择同步账号和公开状态。

5. 音乐库与歌手库
   - 支持扫描和展示音乐库歌曲。
   - 支持维护歌手库、别名和合并关系，用于提升中文名、英文名、别名之间的匹配准确性。
   - 支持刷新歌单与音乐库之间的匹配状态。

6. 系统管理
   - 支持站点、下载器、音乐库、通知和系统参数配置。
   - 支持日志查看、仪表盘统计和文件管理。
   - 支持 Docker 环境变量控制基础部署参数。

## 4. 项目工作流程图

![MusicPilot 工作流程](docs/assets/musicpilot-workflow.png)

## 5. 图片介绍

### 5.1. 仪表盘

仪表盘集中展示歌曲库规模、近 7 天新增、歌单数量、活跃下载、整理记录和任务队列健康状态。最近下载和最近整理区域用于快速确认自动化流程是否正常推进，以及失败任务是否需要人工处理。

![MusicPilot 仪表盘](docs/assets/screenshots/dashboard.png)

### 5.2. 搜索与站点选择

搜索页面先展示音乐元数据候选，再由用户确认要搜索的站点。确认弹窗会保留媒体信息和专辑列表，方便在提交站点搜索前检查标题、歌手和专辑线索。

![MusicPilot 搜索页面](docs/assets/screenshots/search.png)

### 5.3. 下载任务

下载任务页面用于查看已提交任务的状态、进度、保存路径和操作入口。用户可以刷新任务状态、筛选活跃任务、查看任务明细，也可以删除不再需要的记录。

![MusicPilot 下载任务](docs/assets/screenshots/downloads.png)

### 5.4. 文件管理

文件管理页面用于浏览源文件或目标音乐库目录，支持按目录切换、搜索文件、刷新列表、批量整理和删除。每个文件或目录都保留类型、大小、修改时间和整理操作入口，方便手动介入自动整理流程。

![MusicPilot 文件整理](docs/assets/screenshots/media-files.png)

### 5.5. 歌单管理

歌单页面展示外部歌单导入后的本地管理状态，包括来源平台、歌曲数量、已存在数量、等待处理、已提交、失败和同步状态。操作区可进入详情、刷新匹配、提交下载、同步或删除歌单。

![MusicPilot 歌单管理](docs/assets/screenshots/playlists.png)

### 5.6. 系统设置

设置页面按下载器、音乐库、通知和系统设置分组管理运行参数。系统设置中可以配置代理、刮削开关、源目录、映射目录和缺失字段处理策略，用于控制资源整理和元数据补全行为。

![MusicPilot 系统配置](docs/assets/screenshots/settings.png)

## 6. 快速开始

推荐在 NAS 或服务器上直接使用已发布的 Docker 镜像部署 MusicPilot。需要本地修改源码或调试构建时，再使用源码构建方式。

### 6.1. 配置教程

开始部署前，建议先阅读[详细配置教程](docs/configuration.md)，了解数据库、目录映射、环境变量以及 Web UI 配置顺序。

默认部署使用 Compose 中的 PostgreSQL 容器。SQLite 仅作为备用方案，适合测试或快速试用；在任务较多、并发较高或长期运行时可能出现性能和锁竞争问题。

### 6.2. 使用 Docker 镜像部署

1. 创建部署目录并进入目录：

```bash
mkdir -p musicpilot
cd musicpilot
```

2. 创建 `docker-compose.yml` 文件：

```bash
cat > docker-compose.yml <<'EOF'
services:
  musicpilot:
    image: ghcr.io/lzcer/musicpilot:latest
    environment:
      MP_APP_NAME: MusicPilot
      MP_LOG_LEVEL: INFO
      MP_ADMIN_USERNAME: admin
      MP_ADMIN_PASSWORD: change-this-password
      MP_SESSION_SECRET: change-this-random-secret
      MP_DATABASE_URL: postgresql+asyncpg://musicpilot:musicpilot-change-me@postgres:5432/musicpilot
      MP_MUSIC_LIBRARY_PATH: /music
      MP_DOWNLOAD_STAGING_PATH: /downloads
      MP_STATIC_DIR: /app/frontend/dist
      MP_INDEXER_PARSER_CONFIG: /config/sites.parser.yaml
      MP_RUNTIME_CONFIG: /config/runtime.json
      MP_MUSICBRAINZ_USER_AGENT: MusicPilot/1.0.0 (self-hosted)
      MP_WRITE_AUDIO_TAGS: "true"
      MP_SUBSCRIPTIONS_ENABLED: "true"
      MP_SUBSCRIPTION_CHECK_INTERVAL_MINUTES: "1440"
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
      - ./config:/config
      - /volume1/music:/music
      - /volume1/downloads:/downloads
    depends_on:
      postgres:
        condition: service_healthy
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: musicpilot
      POSTGRES_USER: musicpilot
      POSTGRES_PASSWORD: musicpilot-change-me
    volumes:
      - ./postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
EOF
```

需要调整端口、账号密码、密钥或目录时，直接修改 `docker-compose.yml` 里的对应值。

如果希望固定版本，建议把镜像改为明确的版本号，例如：

```yaml
image: ghcr.io/lzcer/musicpilot:1.0.0
```

镜像支持 `linux/amd64` 和 `linux/arm64`，Docker 会根据运行机器的架构自动拉取对应镜像。

MusicPilot 会同时读取镜像内置的站点解析器配置和用户自定义配置。内置配置随镜像更新，用户自定义配置用于新增或覆盖规则。

如果需要自定义站点解析器，把配置文件放到：

```text
./config/sites.parser.yaml
```

多个站点共用同一套解析规则时，可以把站点写在同一个 `targets` 列表中：

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
        download:
          selector: "a[href*='download.php']"
          attribute: href
```

只有解析规则不同时，才需要新增一个 `sites` 条目。当用户配置中的 `base_url` 与内置配置重复时，以用户配置为准。后续修改该文件后，重新启动容器生效。

3. 拉取镜像并启动服务：

```bash
docker compose pull
docker compose up -d
```

4. 打开 Web UI：

```text
http://<NAS_IP>:8000
```

5. 查看日志：

```bash
docker compose logs -f musicpilot
```

6. 更新到最新镜像：

```bash
docker compose pull
docker compose up -d
```

### 6.3. 从源码构建部署

以下方式适合在 NAS 或服务器上直接从源码构建并运行 MusicPilot。

1. 克隆项目并进入目录：

```bash
git clone <your-repo-url> MusicPilot
cd MusicPilot
```

2. 修改 `docker-compose.yml` 中的关键配置：

```yaml
ports:
  - "8000:8000"
volumes:
  - /volume1/docker/musicpilot/data:/data
  - /volume1/docker/musicpilot/config:/config
  - /volume1/music:/music
  - /volume1/downloads:/downloads
environment:
  MP_ADMIN_USERNAME: admin
  MP_ADMIN_PASSWORD: change-this-password
  MP_SESSION_SECRET: change-this-random-secret
```

如果 Docker 构建时容器网络无法访问 PyPI，而宿主机网络正常，可以保留：

```yaml
build:
  network: host
```

如果需要使用更稳定的 Python 包镜像源，可以调整：

```yaml
build:
  args:
    UV_DEFAULT_INDEX: https://pypi.org/simple
```

3. 构建并启动服务：

```bash
docker compose up -d --build
```

4. 打开 Web UI：

```text
http://<NAS_IP>:8000
```

5. 查看日志：

```bash
docker compose logs -f musicpilot
```

6. 更新项目：

```bash
git pull
docker compose up -d --build
```

### 6.4. 本地开发启动

以下方式适合在本机修改源码、调试接口和开发前端页面。需要提前安装 Python、`uv`、Node.js 和 npm。

1. 第一次拉代码时，安装后端依赖并启动 API：

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
uvicorn musicpilot.infra.api.app:create_app --factory --reload
```

后端默认监听：

```text
http://127.0.0.1:8000
```

以后后端依赖没有变化时，只需要：

```bash
source .venv/bin/activate
uvicorn musicpilot.infra.api.app:create_app --factory --reload
```

2. 第一次启动前端时，另开一个终端安装依赖并启动：

```bash
cd frontend
npm ci
npm run dev
```

前端开发服务器默认监听：

```text
http://127.0.0.1:5173
```

Vite 已配置把 `/api` 代理到 `http://127.0.0.1:8000`，所以本地开发时通常打开：

```text
http://127.0.0.1:5173
```

默认登录账号：

```text
admin / musicpilot
```

本地开发不强制需要 `.env`。如果要改账号、数据库或目录，可以在项目根目录创建 `.env` 覆盖默认值。

3. 可以用健康检查确认后端已启动：

```bash
curl --noproxy '*' http://127.0.0.1:8000/api/health
```

4. 常用检查命令：

```bash
make test
make lint
make smoke
cd frontend
npm run build
```

5. 如果只想用后端直接托管前端静态文件，先执行：

```bash
cd frontend
npm ci
npm run build
cd ..
source .venv/bin/activate
uvicorn musicpilot.infra.api.app:create_app --factory --reload
```

然后打开：

```text
http://127.0.0.1:8000
```

## 7. 免责声明

- 本项目仅作为自托管音乐库整理和管理工具使用，不直接提供、存储、发布或分发任何音乐资源，也不提供任何下载渠道。
- 本项目只负责连接用户自行配置的媒体库、下载器、站点和元数据来源；用户应自行确认相关账号、站点、资源和文件的合法性，并自行承担使用过程中的全部责任。
- 本项目仅供学习交流和个人自托管场景使用，不得用于商业用途，不得用于任何违法违规活动。
- 本项目代码开源。任何基于本项目进行修改、分发、传播或去除限制后产生的风险和责任，均由对应修改者、分发者或使用者自行承担。
- 本项目不接受捐赠，不提供收费服务，也不会在任何地方发布收费或捐赠入口，请注意辨别，避免误导。

## 8. 鸣谢

MusicPilot 的设计和实现过程中参考了许多优秀开源项目。特别感谢：

1. [MoviePilot](https://github.com/jxxghp/MoviePilot)
   - MusicPilot 在自托管自动化、任务编排、站点与下载器联动、管理后台体验等方向上，受到了 MoviePilot 项目的启发。

2. [musicdl](https://github.com/CharlesPikachu/musicdl)
   - MusicPilot 的多源音乐元数据检索和音乐信息补全能力，参考了 musicdl 项目中对音乐平台数据获取的实践。

3. [Jackett/Jackett](https://github.com/Jackett/Jackett)
   - MusicPilot 的站点搜索适配参考了 Jackett 对私有站点请求参数和结果解析规则的实践。

同时感谢 FastAPI、SQLAlchemy、Vue、Vite、Vuetify、qBittorrent、Navidrome、MusicBrainz、NexusPHP 及相关开源生态提供的基础能力。

本项目仍在持续演进中，欢迎通过 issue、讨论和代码贡献帮助它变得更稳定、更易用。
