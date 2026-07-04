# 1. MusicPilot 任务队列与资源互斥设计

日期：2026-07-04

## 1.1 目标

建立一个数据库持久化的任务队列机制，用于统一处理搜索、站点检索、刮削、通知、下载提交等会占用外部服务或本地重资源的流程。核心目标是：

1. 同类互斥资源按顺序执行，避免媒体搜索、站点搜索、刮削同时拥挤导致服务卡顿。
2. 任务落库，系统重启后可以恢复 `WAIT` 和过期 `RUNNING` 任务。
3. 支持任务链，前一个任务完成后创建后续任务，并传递执行结果。
4. 支持同一任务同时占用多个资源 key。
5. 支持 chain 级可继承资源 key，用于同歌手连续处理，直到该业务链路结束后才释放。

## 1.2 当前实现基础

当前系统已有几类局部机制：

1. `torrent_records` 是下载生命周期任务，服务下载、刷新音乐库和歌单状态同步。
2. `ArtistDownloadQueue` 是内存队列，按 artist key 做系统级互斥，但不可落库恢复。
3. 站点爬虫里有 `asyncio.Semaphore(max_concurrency)`，只能限制单 crawler 内部并发。
4. `MetadataSiteSearchTask` 和 `EventBus` 是内存状态，不适合承担系统级可恢复队列。

这些机制可以保留业务语义，但不能继续扩展成多个互相独立的排队实现。

## 1.3 核心概念

### 1.3.1 任务类型

`task_type` 表示任务做什么，例如：

1. `SEARCH_MEDIA`
2. `SEARCH_SITE`
3. `SEARCH_SITE_CANDIDATES`
4. `SCRAPE`
5. `NOTIFY`
6. `DOWNLOAD_SUBMIT`
7. `PLAYLIST_TRACK_DOWNLOAD`
8. `DOWNLOAD_ITEM_SCRAPE`
9. `DOWNLOAD_REFRESH_LIBRARY`
10. `MANUAL_SCRAPE`

任务类型决定由哪个 executor 执行业务逻辑。

### 1.3.2 资源 key

`resource_keys` 表示任务执行时需要占用的互斥资源，例如：

1. `media-search`
2. `site:<site_id>`
3. `scraper`
4. `notifier:<notifier_id>`
5. `downloader:<downloader_id>`
6. `artist:<artist_id>`

一个任务可以需要多个 key。只有所有 key 都可用，任务才能进入执行。

### 1.3.3 可继承 key

可继承 key 表示需要跨任务连续持有的资源，第一阶段只允许每条 chain 持有一个可继承 key。典型例子是 `artist:<artist_id>`。

可继承 key 的持有者是 `chain_id`，不是单个 task。chain 内后续任务如果需要同一个 key，视为已经持有。chain 完成、失败终止、取消或 lease 超时后释放。

### 1.3.4 任务链

`chain_id` 表示一条业务链路。例如歌单下载某首歌：

1. `SEARCH_MEDIA`
2. `SEARCH_SITE_CANDIDATES`
3. `PLAYLIST_TRACK_DOWNLOAD`
4. `DOWNLOAD_SUBMIT`
5. `SCRAPE`

前一个任务成功后由 executor 创建后续任务，并把必要结果写入后续任务 payload。

## 1.4 数据模型

新增 `system_tasks` 表：

1. `id`
2. `task_type`
3. `status`: `WAIT`、`RUNNING`、`SUCCEEDED`、`FAILED`
4. `chain_id`
5. `parent_task_id`
6. `priority`
7. `resource_keys`
8. `inheritable_key`
9. `payload`
10. `result`
11. `error_message`
12. `attempts`
13. `max_attempts`
14. `available_at`
15. `started_at`
16. `finished_at`
17. `heartbeat_at`
18. `lease_until`
19. `idempotency_key`
20. `created_at`
21. `updated_at`

新增 `system_task_resource_leases` 表：

1. `resource_key`
2. `holder_kind`: `task` 或 `chain`
3. `holder_id`
4. `task_id`
5. `chain_id`
6. `lease_until`
7. `created_at`
8. `updated_at`

`resource_key` 是主键，用于保证同一资源同一时间只有一个持有者。

## 1.5 执行流程

### 1.5.1 入队

业务入口调用 `TaskManager.enqueue(...)` 创建任务。创建时写入：

1. 任务类型。
2. 普通资源 key。
3. 可继承 key。
4. 任务 payload。
5. chain 信息。
6. 幂等 key。

### 1.5.2 调度

调度器周期性读取 `WAIT` 且 `available_at <= now` 的任务，按 `priority desc, created_at asc` 取候选。调度器可以同时运行多个任务；是否真正并发由 `max_concurrent_tasks` 和资源 lease 共同决定。

任务开始前，调度器统一尝试占用资源：

1. 对普通 key，必须全部可用。
2. 对可继承 key，如果当前 chain 已持有则直接通过。
3. 对可继承 key，如果无人持有，则由 chain 占用。
4. 任意 key 被其他 task 或 chain 持有，则本任务保持 `WAIT`。

资源占用成功后，任务状态更新为 `RUNNING`，并设置 `lease_until` 和 `started_at`。

### 1.5.3 执行

`TaskExecutorRegistry` 根据 `task_type` 找到 executor。executor 只负责业务逻辑：

1. 读取 payload。
2. 调用搜索、站点、刮削或通知逻辑。
3. 返回 result。
4. 生成后续任务定义。

资源抢占、状态更新、失败重试、释放和恢复都由 `TaskManager` 统一处理。

### 1.5.4 完成

任务成功后：

1. 写入 `result`。
2. 创建后续任务。
3. 普通 key 释放。
4. 如果 chain 没有后续 `WAIT/RUNNING` 任务，则释放 chain 持有的可继承 key。
5. 任务状态改为 `SUCCEEDED`。

任务失败后：

1. 如果 `attempts < max_attempts`，设置回 `WAIT` 并按退避规则更新 `available_at`。
2. 如果重试耗尽，状态改为 `FAILED`。
3. 释放普通 key。
4. 如果失败终止 chain，则释放 chain 可继承 key。

## 1.6 原子任务粒度

一个任务应该代表一个需要独立排队、可重试、可记录结果的业务步骤。

搜索一个单曲得到多个专辑候选后，同一站点对这批候选连续搜索并整合结果，应该是一个 `SEARCH_SITE_CANDIDATES` 原子任务，而不是拆成多个专辑任务。原因是选种需要合并候选结果，拆开会让结果聚合和失败恢复变复杂。

多个站点仍然可以生成多个 `SEARCH_SITE_CANDIDATES` 任务。它们通过 `site:<site_id>` 和 `artist:<artist_id>` 共同决定是否并发。

## 1.7 第一阶段实现范围

第一阶段实现任务系统基础设施，并先接入高风险互斥资源：

1. 新增数据库模型和 Alembic 迁移。
2. 新增任务状态、任务定义、执行结果等基础类型。
3. 新增 `TaskManager`，支持入队、资源占用、释放、chain lease、lease 续租和过期恢复。
4. 新增 `TaskExecutorRegistry`，后续按 `task_type` 注册异步 executor。
5. App 启动时恢复所有 `RUNNING` 任务到 `WAIT`，并启动调度后台任务。
6. 保留 `run_exclusive(...)` 作为兼容同步调用的资源队列辅助能力。
7. 手动整理接入 `MANUAL_SCRAPE` / `scraper` 资源。
8. 下载明细预刮削接入 `DOWNLOAD_ITEM_SCRAPE` / `scraper` 资源。
9. 下载完成后的刮削和媒体库刷新接入 `DOWNLOAD_REFRESH_LIBRARY` / `scraper` 资源。
10. 站点搜索接入 `SEARCH_SITE` / `site:<site_id>` 资源。
11. 站点候选搜索接入 `SEARCH_SITE_CANDIDATES` / `site:<site_id>` + `artist:<key>` 资源。
12. 媒体元数据搜索接入 `SEARCH_MEDIA` / `media-search` 资源。
13. 歌单单曲下载接入 `PLAYLIST_TRACK_DOWNLOAD`，使用 `artist:<key>` 资源替代内存 `ArtistDownloadQueue`。

第一阶段不把全部业务流改成异步链式任务。后续分批接入：

1. 将 `PLAYLIST_TRACK_DOWNLOAD` 内部的下载提交继续拆成更细的持久化任务链。
2. 增加任务列表和失败重试管理入口。

## 1.8 稳定性要求

1. 单进程内使用 `asyncio.Condition` 唤醒调度器。
2. 数据库 lease 是恢复依据，内存状态只是当前进程加速结构。
3. 启动时恢复所有 `RUNNING` 任务，运行中恢复 lease 过期的 `RUNNING` 任务。
4. 资源 lease 过期后可被回收。
5. 每个 chain 第一阶段最多持有一个可继承 key。
6. Executor 不直接管理资源锁，避免 key 泄漏。
7. 日志需要记录入队、开始、成功、失败、重试和释放资源。

## 1.9 验证

第一阶段验证：

1. `python -m py_compile` 覆盖新增任务模块、数据库模型、仓储和 API 启动文件。
2. `ruff check` 覆盖新增任务模块和迁移。
3. 前端不涉及 UI 时不要求构建；若 App 类型或 API schema 变化影响前端，再运行 `npm run build`。
4. 不新增单元测试，除非后续明确要求。
