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
3. 保持部署简单，默认使用 SQLite，并提供 Docker Compose 方式在 NAS 或服务器上运行。
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

### 6.1. 使用 Docker 镜像部署

1. 创建部署目录并进入目录：

```bash
mkdir -p musicpilot
cd musicpilot
```

2. 创建 `.env` 文件：

```bash
cat > .env <<'EOF'
MP_HTTP_PORT=8000
MP_ADMIN_USERNAME=admin
MP_ADMIN_PASSWORD=change-this-password
MP_SESSION_SECRET=change-this-random-secret
MP_HOST_DATA_PATH=./data
MP_HOST_CONFIG_PATH=./config
MP_HOST_MUSIC_PATH=/volume1/music
MP_HOST_DOWNLOADS_PATH=/volume1/downloads
EOF
```

3. 创建 `docker-compose.yml` 文件：

```bash
cat > docker-compose.yml <<'EOF'
services:
  musicpilot:
    image: ghcr.io/lzcer/musicpilot:latest
    environment:
      MP_APP_NAME: MusicPilot
      MP_LOG_LEVEL: INFO
      MP_ADMIN_USERNAME: ${MP_ADMIN_USERNAME:-admin}
      MP_ADMIN_PASSWORD: ${MP_ADMIN_PASSWORD:-musicpilot}
      MP_SESSION_SECRET: ${MP_SESSION_SECRET:-musicpilot-change-me}
      MP_DATABASE_URL: ${MP_DATABASE_URL:-sqlite+aiosqlite:////data/musicpilot.db}
      MP_MUSIC_LIBRARY_PATH: /music
      MP_DOWNLOAD_STAGING_PATH: /downloads
      MP_STATIC_DIR: /app/frontend/dist
      MP_INDEXER_PARSER_CONFIG: /config/sites.parser.yaml
      MP_RUNTIME_CONFIG: /config/runtime.json
      MP_MUSICBRAINZ_USER_AGENT: ${MP_MUSICBRAINZ_USER_AGENT:-MusicPilot/1.0.0 (self-hosted)}
      MP_WRITE_AUDIO_TAGS: ${MP_WRITE_AUDIO_TAGS:-true}
      MP_SUBSCRIPTIONS_ENABLED: ${MP_SUBSCRIPTIONS_ENABLED:-true}
      MP_SUBSCRIPTION_CHECK_INTERVAL_MINUTES: ${MP_SUBSCRIPTION_CHECK_INTERVAL_MINUTES:-1440}
    restart: unless-stopped
    ports:
      - "${MP_HTTP_PORT:-8000}:8000"
    volumes:
      - ${MP_HOST_DATA_PATH:-./data}:/data
      - ${MP_HOST_CONFIG_PATH:-./config}:/config
      - ${MP_HOST_MUSIC_PATH:-./data/library}:/music
      - ${MP_HOST_DOWNLOADS_PATH:-./data/downloads}:/downloads
EOF
```

如果希望固定版本，建议把镜像改为明确的版本号，例如：

```yaml
image: ghcr.io/lzcer/musicpilot:1.0.0
```

镜像支持 `linux/amd64` 和 `linux/arm64`，Docker 会根据运行机器的架构自动拉取对应镜像。

首次启动时，如果宿主机挂载目录中没有站点解析器配置，容器会自动把内置配置初始化到：

```text
./config/sites.parser.yaml
```

后续可以直接修改该文件来自定义站点解析器，修改后重启容器生效：

```bash
docker compose up -d
```

4. 拉取镜像并启动服务：

```bash
docker compose pull
docker compose up -d
```

5. 打开 Web UI：

```text
http://<NAS_IP>:8000
```

6. 查看日志：

```bash
docker compose logs -f musicpilot
```

7. 更新到最新镜像：

```bash
docker compose pull
docker compose up -d
```

### 6.2. 从源码构建部署

以下方式适合在 NAS 或服务器上直接从源码构建并运行 MusicPilot。

1. 克隆项目并进入目录：

```bash
git clone <your-repo-url> MusicPilot
cd MusicPilot
```

2. 复制环境变量模板：

```bash
cp .env.example .env
```

3. 修改 `.env` 中的关键配置：

```text
MP_HTTP_PORT=8000
MP_ADMIN_USERNAME=admin
MP_ADMIN_PASSWORD=change-this-password
MP_SESSION_SECRET=change-this-random-secret
MP_HOST_DATA_PATH=/volume1/docker/musicpilot/data
MP_HOST_CONFIG_PATH=/volume1/docker/musicpilot/config
MP_HOST_MUSIC_PATH=/volume1/music
MP_HOST_DOWNLOADS_PATH=/volume1/downloads
```

如果 Docker 构建时容器网络无法访问 PyPI，而宿主机网络正常，可以保留：

```text
MP_DOCKER_BUILD_NETWORK=host
```

如果需要使用更稳定的 Python 包镜像源，可以调整：

```text
UV_DEFAULT_INDEX=https://pypi.org/simple
```

4. 构建并启动服务：

```bash
docker compose up -d --build
```

5. 打开 Web UI：

```text
http://<NAS_IP>:8000
```

6. 查看日志：

```bash
docker compose logs -f musicpilot
```

7. 更新项目：

```bash
git pull
docker compose up -d --build
```

### 6.3. 可选 PostgreSQL 数据库

MusicPilot 默认使用 SQLite，适合单机和 NAS 部署。需要更高并发或希望使用独立数据库时，可以把 `.env` 中的 `MP_DATABASE_URL` 改为 PostgreSQL 连接串：

```text
MP_DATABASE_URL=postgresql+asyncpg://musicpilot:change-this-password@postgres:5432/musicpilot
```

PostgreSQL 数据库和用户需要提前创建。MusicPilot 启动时会通过 Alembic 自动初始化或升级表结构。

### 6.4. 配置教程

首次启动后，还需要在 Web UI 中配置站点、下载器、音乐库、整理规则和通知渠道。

配置教程入口：[MusicPilot 配置教程](docs/configuration.md)

该文档用于集中说明各项配置步骤，当前只提供入口，具体内容后续补充。

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

同时感谢 FastAPI、SQLAlchemy、Vue、Vite、Vuetify、qBittorrent、Navidrome、MusicBrainz、NexusPHP 及相关开源生态提供的基础能力。

本项目仍在持续演进中，欢迎通过 issue、讨论和代码贡献帮助它变得更稳定、更易用。
