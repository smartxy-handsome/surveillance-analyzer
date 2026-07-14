# 一次添加多个视频文件 - 设计文档

- 日期：2026-07-15
- 状态：已确认，待编写实现计划
- 范围：将"一次提交一个视频"扩展为"一次提交多个视频"，每个视频仍是独立 job

## 1. 背景与目标

当前系统一次只能添加一个视频文件：用户在 `VideoUploader` 中输入或浏览选择单个路径，点击"开始分析"后立即创建一个 job 并跳转到该 job 的详情页。数据模型上每个 job 与一个视频文件 1:1 对应，job 之间无关联。

本次目标：支持一次添加多个视频文件并提交，每个视频仍是独立的 job，各自独立分析。

### 关键决策（已与用户逐项确认）

| 决策点 | 选择 |
|---|---|
| 多视频之间的关系 | 互相独立的多任务，job 之间无关联，数据模型不变 |
| 提交后界面去向 | 留在上传页，新任务进入下方 `JobList`，不跳转 |
| 添加入口 | `FileBrowser` 多选 + 手动框追加；不动拖拽 |
| 后端 API | 不改，前端循环调用现有单条 `POST /api/jobs` |
| GPU 并发 | 用 `asyncio.Semaphore` 限制并发分析任务数，默认 1，config 可调 |
| 部分失败 | 尽力提交，成功项移除、失败项保留标红 |

## 2. 架构与范围

核心判断：job 与视频本就是 1:1 且互不关联，因此**数据模型完全不变**，后端 API 接口也完全不变。本次改动是两层：

1. **前端提交层**：从"单路径即提交"改为"先攒成清单、再批量提交"。
2. **后端并发闸**：新增信号量，防止 N 个分析任务同时抢占 GPU 导致 OOM。

### 改动边界

| 文件 | 改动 |
|---|---|
| `frontend/src/components/PendingList.vue` | 新增：待提交清单组件 |
| `frontend/src/components/VideoUploader.vue` | 改造：手动框改追加、管理清单、循环提交 |
| `frontend/src/components/FileBrowser.vue` | 改造：单选改多选，emit 路径数组 |
| `frontend/src/App.vue` | 改造：`onJobCreated` 不再设置 `currentJobId`（不跳转），改为刷新 `JobList` |
| `frontend/src/api/client.ts` | 不变，复用现有 `createJob` |
| `src/web/app.py` | 改造：lifespan 中初始化 `analysis_semaphore` 挂到 `app.state` |
| `src/web/routes/jobs.py` | 改造：`_run_analysis` 用信号量包住，`processing` 前获取 |
| `src/core/models.py` | 改造：`PipelineConfig` 增加 `max_concurrent_jobs` |
| `config/default.yaml` | 改造：`pipeline` 段增加 `max_concurrent_jobs` |

### 明确不做

- 不引入批次/分组概念，不新增 batch 表。
- 不实现拖拽多文件（现有 `DropZone` 受浏览器安全限制拿不到磁盘路径，本就未真正可用，维持现状不扩展）。
- 不做前端预校验（文件存在性/格式由后端权威判断）。
- 不改 `JobList` / `JobDetail` / 数据模型 / 存储层。
- 不引入轮询或 SSE 进度推送。

## 3. 前端组件与数据流

### 3.1 新增 `PendingList.vue`

纯粹的受控展示+操作组件，职责单一：管理"待提交路径"数组。

- **Props**：`items: PendingItem[]`，其中 `PendingItem = { id: string, path: string, filename: string, status: 'pending' | 'submitting' | 'error', error?: string }`
- **Emits**：`remove(id)`（点 ✕ 移除单条）、`submit()`（点"开始分析"）
- **渲染**：
  - 列表展示每项文件名 + 目录。
  - `submitting` 项显示加载态。
  - `error` 项整行标红，显示后端返回的错误信息。
  - 底部"开始分析 (N)"按钮，清单为空时禁用。
- **无自身状态**：清单数据由父组件 `VideoUploader` 持有，`PendingList` 只做受控展示，便于独立测试与复用。

### 3.2 改造 `VideoUploader.vue`

从"单路径提交器"变为"清单管理 + 批量提交器"。

数据流：

1. 手动框输入路径 + 回车/点"＋追加" -> 校验非空、按路径去重后 `push` 到 `items`（状态 `pending`）。
2. `FileBrowser` 多选关闭时 `emit('select', paths: string[])` -> 全部追加到 `items`（去重）。
3. 点"开始分析" -> 遍历 `items`，对每个 `pending` 项：
   - 置为 `submitting` -> 调 `createJob(path)` -> 成功则从清单移除、`emit('job-created', id)`；失败则置为 `error` 并写入后端返回的 `detail`。
4. 提交期间按钮禁用显示"⏳ 提交中..."，全部处理完恢复。

"遍历清单 + 逐条调用 + 成功移除/失败标红"这块逻辑抽成可独立调用的函数（如 `submitItems`），便于单测时注入 mock 的 `createJob`。

### 3.3 改造 `FileBrowser.vue`

单选改多选：

- 文件项点击改为**切换选中**（目录项仍是点击即进入）。
- 底部加"确认选择 (N)"按钮，点击时 `emit('select', selectedPaths)` 并关闭；另设"取消"。
- `defineEmits` 由 `select: [path: string]` 改为 `select: [paths: string[]]`。

### 3.4 `App.vue` 与 `api/client.ts`

- **`App.vue` 不变**其结构：仍监听 `job-created`，但现在每成功一个就触发一次。关键改动是 `onJobCreated` **不再设置 `currentJobId`**（不跳转），改为触发 `JobList` 刷新，让新任务出现在列表里。
- **`api/client.ts` 不变**：复用现有 `createJob`。

## 4. 后端并发闸

### 问题

`_run_analysis` 通过 `BackgroundTasks` 挂起，FastAPI 并发执行多个后台任务。多个任务同时指向 `cuda:0` 会抢显存，可能 OOM。

### 方案

用 `asyncio.Semaphore` 限流，超出并发数的 job 停在 `pending` 状态等待。

### 实现

- `src/core/models.py` 的 `PipelineConfig` 增加 `max_concurrent_jobs: int = 1`。
- `config/default.yaml` 的 `pipeline` 段增加 `max_concurrent_jobs: 1`。
- `src/web/app.py` 的 `lifespan` 中：`app.state.analysis_semaphore = asyncio.Semaphore(config.pipeline.max_concurrent_jobs)`。
- `src/web/routes/jobs.py` 的 `_run_analysis`：

```python
async def _run_analysis(job_id, app):
    config = app.state.config
    job_repo = app.state.job_repo
    async with app.state.analysis_semaphore:      # 未获许可则阻塞，job 停在 pending
        await job_repo.update_status(job_id, "processing")
        ...  # 现有逻辑不变
```

### 关键点

- 信号量在 `update_status("processing")` **之前**获取。排队中的 job 状态仍是创建时写入的 `pending`，界面能区分"排队中(pending)"与"处理中(processing)"。
- 信号量在 lifespan 启动时按配置初始化并挂到 `app.state`，避免全局变量，也便于测试时注入不同并发数。
- 默认 1 = 串行分析，最稳妥；有富余显存可调高。

## 5. 错误处理

三层各管一段：

1. **后端创建时校验（已有，不变）**：`create_job` 中 `file_path.exists()` 与 `supported_formats` 校验仍返回 400 + `detail`，是文件不存在/格式不支持的唯一权威来源。
2. **后端分析失败（已有，不变）**：`_run_analysis` 的 `try/except` 写入 `job.status=failed` + `error_message`。并发闸不改变该行为。
3. **前端循环提交**：`createJob` 失败时捕获 `err.response?.data?.detail`，把该清单项置 `error` 并显示；不中断其余项。

### 边界情况

- **重复路径**：追加时按路径去重，避免同一文件建多个 job。
- **提交中再次点提交**：按钮禁用，靠 `submitting` 标志位拦截。
- **并发闸导致排队**：前端无需感知，`pending` job 已在列表，`JobList` 刷新即可见；本次不引入轮询/SSE 进度。

## 6. 测试策略

按单元边界，纯逻辑优先单测：

- **`PendingList.vue`**：受控组件，测 props 渲染 + emit。空清单禁用按钮、`error` 项标红、`remove`/`submit` emit 正确。
- **`VideoUploader` 提交逻辑（`submitItems`）**：注入 mock 的 `createJob`，验证：N 个路径产生 N 次调用、成功项移除、失败项保留且带错误、提交期间禁用。本次最值得测的核心逻辑。
- **`FileBrowser` 多选**：测点击切换选中、目录项仍导航、"确认选择"emit 的路径数组正确、去重。
- **后端并发闸**：集成测，构造 `max_concurrent_jobs=2`，连续创建 3 个 job，断言前 2 个进入 `processing`、第 3 个保持 `pending`；某任务完成后第 3 个转为 `processing`。可用 mock 慢的 `_run_analysis` 验证排队语义。
- **现有测试**：`tests/test_api.py` 覆盖 `create_job`/`list`/`get`/`delete`，后端 API 不变，应继续通过，无需改动。

### 刻意不测

- GPU 实际推理（依赖硬件，靠现有 `test_pipeline.py` 覆盖）。
- 真实文件系统（用 `tmp_path` 造文件即可）。
