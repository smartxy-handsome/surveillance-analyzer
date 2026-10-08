# Surveillance Analyzer

离线监控视频人物检测分析器:用 YOLOv8 对本地监控录像做人形检测,聚合成「人物出现时间段」,并在人物出现/离开时刻保存抓拍图(人像裁剪 + 带检测框的整帧),通过本地 Web 界面浏览结果。

## 功能

- **批量分析**:文件浏览器多选 + 拖拽,攒成待提交清单后一次提交多个视频;每个视频一个独立任务,后端并发闸(`max_concurrent_jobs`)按序执行,排队任务显示队列位置
- **时间段聚合**:按采样帧率抽帧检测,置信度过滤,合并间隙内的检测为连续时间段(可配置合并间隙与最短时长)
- **抓拍**:每个人物时间段保存出现、离开两个时刻的截图,存于 `data/captures/{job_id}/`,删除任务时一并清理
- **可视化**:时间轴、时间段表格、抓拍图画廊(裁剪图/标注图切换)、实时进度百分比
- **健壮性**:解码失败帧自动跳过并在任务上记录丢帧数(监控录像常见坏帧);长 GOP HEVC 视频采用顺序解码避免 seek 解出坏帧

## 环境要求

- Python 3.12([uv](https://docs.astral.sh/uv/) 管理依赖)
- Node.js 18+(前端构建)
- GPU 可选(CUDA 时检测走 `cuda:0`,否则改 `config/default.yaml` 的 `device` 为 `cpu`)
- 模型权重 `yolov8n.pt` 放在仓库根目录(不入库,自行下载)

## 启动

```bash
# 后端(生产模式:构建前端 + 启动 + 自动打开浏览器)
scripts/start.bat          # Windows
uv run python -m src.main  # 其他平台

# 开发模式(前后端分离)
uv run python -m src.main --dev --no-browser   # 后端 http://127.0.0.1:8000
cd frontend && npm install && npm run dev      # 前端 http://localhost:5173
```

默认只监听 `127.0.0.1`(API 无鉴权且提供任意目录浏览接口,不要默认暴露到局域网;如需共享,显式修改 `config/default.yaml` 的 `web.host`)。

CLI 参数可覆盖配置:`--host`、`--port`、`--dev`(不挂载前端构建产物)、`--no-browser`。

## 配置

`config/default.yaml`,各段含义:

| 段 | 关键项 | 说明 |
|---|---|---|
| `video` | `supported_formats` / `max_file_size_mb` | 允许的容器格式与提交时的文件大小上限 |
| `sampling` | `fps` / `strategy` | 抽帧采样率;采样策略当前仅支持 `uniform` |
| `detection` | `model_name` / `confidence_threshold` / `device` / `batch_size` | YOLOv8 模型、置信度阈值、推理设备、批大小 |
| `aggregation` | `merge_gap_seconds` / `min_segment_seconds` | 检测合并间隙与最短时间段时长 |
| `pipeline` | `frame_queue_size` / `num_decode_threads` / `max_concurrent_jobs` | 解码线程数必须为 1(乱序帧会破坏聚合的时序假设);并发任务闸 |
| `web` | `host` / `port` / `cors_origins` | 监听地址与 CORS |

环境变量可覆盖:`SURVEILLANCE_<段>__<字段>`,如 `SURVEILLANCE_SAMPLING__FPS=5`。

## 数据存储

- `data/results.db` — 任务、时间段、抓拍记录(SQLite,异步 SQLAlchemy)
- `data/captures/{job_id}/` — 抓拍图,随任务删除清理
- `data/videos/` — 预留的视频存储目录

整个 `data/` 目录不入库。

## 开发

```bash
bash scripts/check.sh   # 一键:ruff + 后端 pytest + 前端 vitest + 生产构建
```

- 后端测试:`uv run pytest tests/`(含合成视频的端到端测试,无需 GPU/真实模型)
- 前端测试:`cd frontend && npm test`
- 架构:解码线程 → 帧队列 → 推理线程(`src/pipeline/coordinator.py`);Web 层 FastAPI 路由在 `src/web/routes/`,分析任务经 `asyncio.Semaphore` 排队后作为后台任务执行
