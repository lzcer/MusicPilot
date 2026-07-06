# 1. 发布流程

MusicPilot 使用 GitHub Actions 在推送版本标签时自动构建 Docker 镜像、推送到 GHCR，并创建 GitHub Release。

## 1.1. 触发条件

发布流程由 `v*.*.*` 形式的 Git 标签触发，例如 `v0.1.0`、`v0.1.1`、`v1.0.0-beta.1`。

标签必须指向 `main` 分支历史中的提交。workflow 会在发布前校验这一点，如果标签指向其他分支独有的提交，发布会失败。

## 1.2. 首次发布

当前仓库没有历史版本标签时，首次发布不会从完整提交历史生成发布说明，而是使用 `docs/releases/initial-release.md` 作为 Release 内容。

首次发布命令示例：

```bash
git checkout main
git pull
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

workflow 会自动完成以下动作：

1. 构建 Docker 镜像。
2. 推送镜像到 GHCR。
3. 使用首版发布说明创建 GitHub Release。

## 1.3. 后续发布

后续发布继续推送新的版本标签即可：

```bash
git checkout main
git pull
git tag -a v0.1.1 -m "v0.1.1"
git push origin v0.1.1
```

当存在上一个 `v*` 标签时，workflow 会自动汇总上一个标签到当前标签之间的提交标题和正文，并按 `feat`、`fix`、`perf`、`refactor` 前缀分类写入 Release 内容。其他前缀不会进入自动发布说明。

## 1.4. 镜像标签

发布镜像支持 `linux/amd64` 和 `linux/arm64`。同一个镜像标签会发布为多架构 manifest，Docker 会根据运行机器的架构自动拉取对应镜像。

稳定版本会推送以下镜像标签：

```text
ghcr.io/lzcer/musicpilot:v0.1.0
ghcr.io/lzcer/musicpilot:0.1.0
ghcr.io/lzcer/musicpilot:latest
```

预发布版本包含 `-`，例如 `v1.0.0-beta.1`，不会更新 `latest`。

## 1.5. GHCR 可见性

首次推送 GHCR 包后，如果镜像需要公开访问，需要在 GitHub Packages 页面确认包的可见性为 public。构建、推送和 Release 创建本身由 workflow 自动完成。
