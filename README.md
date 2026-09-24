# Watch 2.0

一个供个人使用的 13 路视频墙：4×4 网格中，中央画面占 2×2，外围同时播放 12 路视频。双击任意小画面即可与主画面无缝交换。

## 启动

1. 安装 Docker Desktop。
2. 复制 `.env.example` 为 `.env`，按需修改视频目录和数据目录。
3. 将视频放入配置的 `MEDIA_DIR`，支持浏览器原生可播放的 MP4、WebM、OGG、MOV、M4V 文件。
4. 运行：

   ```bash
   docker compose up --build -d
   ```

5. 浏览器打开 <http://127.0.0.1:8080>。

配置、标签、合集、观看进度和布局保存在 `DATA_DIR` 下的 SQLite 数据库，缩略图保存在 `DATA_DIR/thumbnails`。迁移到其他电脑时，复制项目、媒体文件和数据目录即可。

顶部的“管理媒体库”进入独立管理页面，可搜索、分页、筛选、收藏、编辑详情、管理标签和合集。目录扫描在后台运行，使用容器内的 ffprobe 读取时长、分辨率和编码，并通过 FFmpeg 生成缩略图。左侧“视频移入”可调用系统文件选择器，将一个或多个视频复制到 `MEDIA_DIR`；为支持该功能，默认媒体目录会以可写方式挂载。同名文件会自动追加序号，不会覆盖已有视频。

本地视频详情中可修改真实文件名或永久删除文件。改名不会改变媒体 ID、标签、合集和观看进度；删除会经过两次确认并清理相关媒体记录。qBittorrent 下载的视频不能单独改名，删除时会删除整个下载任务及其全部文件。

如需多个媒体库，可在 Compose 中增加只读目录挂载，并通过 `MEDIA_LIBRARIES` 提供 JSON 配置。配置中的路径必须是容器内路径，不要填写宿主机绝对路径。

项目默认使用国内资源镜像：Docker 基础镜像来自华为云 SWR，npm 使用 npmmirror，pip 使用阿里云 PyPI 镜像。

## 磁力下载

“磁力下载”页面通过独立的 qBittorrent-nox 容器管理任务。Web UI 默认不向宿主机开放；BT 流量端口由 `QBT_TORRENT_PORT` 配置。完成文件保存在 `DOWNLOAD_DIR/complete`，Watch 以只读方式扫描该目录，视频会出现在“下载的视频”媒体库中。

首次使用时需要初始化认证：

1. 临时开放仅限本机访问的管理端口：`docker compose -f compose.yaml -f compose.qbt-admin.yaml up -d`。
2. 用 `docker compose logs qbittorrent` 查看 qBittorrent 生成的临时密码，在浏览器打开 `http://127.0.0.1:8081`，用户名为 `admin`。
3. 修改密码，并在 Web UI 的“选项 → Web UI → API Key”生成 API Key。
4. 把 Key 单独写入 `data/secrets/qbittorrent-api-key`，或写入 `.env` 的 `QBT_API_KEY`，然后只用基础配置重建：`docker compose up -d --force-recreate`。此时 8081 不再开放。

也可以在 `.env` 中配置 `QBT_USERNAME` 和 `QBT_PASSWORD` 使用会话登录。Watch 不保存种子任务本身，qBittorrent 是任务状态的唯一来源；SQLite 仅保存下载文件与媒体记录的导入映射。“移除任务”保留文件，“删除任务和文件”会永久删除下载目录中的对应内容。

## 本地开发

后端：

```bash
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements-dev.txt
uvicorn backend.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

Vite 开发服务器会把 `/api` 请求代理到 `http://127.0.0.1:8000`。
