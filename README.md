# MusicPilot

<p align="center">
  <img src="docs/assets/musicpilot-logo.png" alt="MusicPilot" width="420">
</p>

语言：[简体中文](README.md) | [English](README_EN.md)

## 1. 项目简介

MusicPilot 是一个面向自托管用户的音乐库自动化工具，用来把“发现音乐、搜索资源、提交下载、整理文件、补全元数据、刷新音乐库、同步歌单”串成一个可管理的工作流。

它适合已经在使用 PT 站点、qBittorrent、Navidrome 等服务的用户：MusicPilot 不替代这些系统，而是负责把它们连接起来，减少重复搜索、手动下载、手动整理和手动刷新音乐库的操作。

项目的核心目标：

1. 用一个 Web 界面管理音乐搜索、下载、整理、歌单和音乐库状态。
2. 通过任务队列处理耗时操作，尽量让下载、刮削、整理和同步可以自动推进。
3. 保持部署简单，默认使用 SQLite，并提供 Docker Compose 方式在 NAS 或服务器上运行。
4. 保留清晰的适配层，方便后续接入更多站点、下载器、音乐平台、元数据源和媒体服务器。

## 2. 项目功能

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

## 3. 项目工作流程图

![MusicPilot 工作流程](docs/assets/musicpilot-workflow.png)

## 4. 快速开始

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

### 4.1. 可选 PostgreSQL 数据库

MusicPilot 默认使用 SQLite，适合单机和 NAS 部署。需要更高并发或希望使用独立数据库时，可以把 `.env` 中的 `MP_DATABASE_URL` 改为 PostgreSQL 连接串：

```text
MP_DATABASE_URL=postgresql+asyncpg://musicpilot:change-this-password@postgres:5432/musicpilot
```

PostgreSQL 数据库和用户需要提前创建。MusicPilot 启动时会通过 Alembic 自动初始化或升级表结构。

### 4.2. 配置教程

首次启动后，还需要在 Web UI 中配置站点、下载器、音乐库、整理规则和通知渠道。

配置教程入口：[MusicPilot 配置教程](docs/configuration.md)

该文档用于集中说明各项配置步骤，当前只提供入口，具体内容后续补充。

## 5. 鸣谢

MusicPilot 的设计和实现过程中参考了许多优秀开源项目。特别感谢：

1. [MoviePilot](https://github.com/jxxghp/MoviePilot)
   - MusicPilot 在自托管自动化、任务编排、站点与下载器联动、管理后台体验等方向上，受到了 MoviePilot 项目的启发。

2. [musicdl](https://github.com/CharlesPikachu/musicdl)
   - MusicPilot 的多源音乐元数据检索和音乐信息补全能力，参考了 musicdl 项目中对音乐平台数据获取的实践。

同时感谢 FastAPI、SQLAlchemy、Vue、Vite、Vuetify、qBittorrent、Navidrome、MusicBrainz、NexusPHP 及相关开源生态提供的基础能力。

本项目仍在持续演进中，欢迎通过 issue、讨论和代码贡献帮助它变得更稳定、更易用。
