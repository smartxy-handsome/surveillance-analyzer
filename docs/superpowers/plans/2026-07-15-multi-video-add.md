# 一次添加多个视频文件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将"一次提交一个视频"扩展为"一次提交多个视频"，每个视频仍是独立 job，并加后端并发闸防止多任务抢爆 GPU。

**Architecture:** 数据模型与 API 接口完全不变（job 与视频 1:1）。前端新增一个待提交清单组件 `PendingList`，把多个路径先攒成清单再循环调用现有 `POST /api/jobs`；后端用 `asyncio.Semaphore`（挂到 `app.state`）包住 `_run_analysis`，超出并发数的 job 停在 `pending` 排队。提交后留在上传页、刷新 `JobList`，不跳转。

**Tech Stack:** 后端 Python 3.12 / FastAPI / pytest-asyncio / httpx。前端 Vue 3 / Vite / TypeScript / Pinia / axios。新增前端测试：vitest + @vue/test-utils + jsdom。

**Spec:** `docs/superpowers/specs/2026-07-15-multi-video-add-design.md`

---

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `src/core/models.py` | `PipelineConfig` 增加 `max_concurrent_jobs` 字段 | Modify |
| `config/default.yaml` | `pipeline` 段增加 `max_concurrent_jobs: 1` | Modify |
| `tests/test_config.py` | 断言新配置项默认值 | Modify |
| `src/web/app.py` | `lifespan` 中初始化 `app.state.analysis_semaphore` | Modify |
| `src/web/routes/jobs.py` | `_run_analysis` 用信号量包住 | Modify |
| `tests/test_api.py` | `client` fixture 同步设置 `analysis_semaphore` | Modify |
| `tests/test_concurrency.py` | 并发闸集成测试 | Create |
| `frontend/package.json` | 加 vitest/@vue/test-utils/jsdom + test 脚本 | Modify |
| `frontend/vitest.config.ts` | vitest 配置（jsdom） | Create |
| `frontend/src/utils/submitItems.ts` | 批量提交纯逻辑函数 + `PendingItem` 类型 | Create |
| `frontend/src/utils/submitItems.spec.ts` | submitItems 单测 | Create |
| `frontend/src/components/PendingList.vue` | 待提交清单受控组件 | Create |
| `frontend/src/components/PendingList.spec.ts` | PendingList 单测 | Create |
| `frontend/src/components/FileBrowser.vue` | 单选改多选 | Modify |
| `frontend/src/components/FileBrowser.spec.ts` | 多选单测 | Create |
| `frontend/src/components/VideoUploader.vue` | 清单管理 + 批量提交 + open-history | Modify |
| `frontend/src/App.vue` | 新建刷新列表不跳转 / 历史打开跳转 | Modify |

**单元边界：**
- `submitItems.ts` 是纯函数（输入路径数组 + createJob 注入，输出结果数组），零 UI 依赖，最易测。
- `PendingList.vue` 受控组件，无自身状态，只 props 渲染 + emit。
- `FileBrowser.vue` 多选逻辑内聚在组件内。
- 后端并发闸是 `app.state` 上一把信号量，独立于业务逻辑。

---

## Task 1: 后端配置项 `max_concurrent_jobs`

**Files:**
- Modify: `src/core/models.py`
- Modify: `config/default.yaml`
- Modify: `tests/test_config.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_config.py` (append a new test function at the end of the file):

```python
def test_pipeline_max_concurrent_jobs_default():
    config = load_config(Path("config/default.yaml"))
    assert config.pipeline.max_concurrent_jobs == 1


def test_pipeline_max_concurrent_jobs_from_yaml(tmp_path):
    cfg = {"pipeline": {"max_concurrent_jobs": 3}}
    p = tmp_path / "custom.yaml"
    p.write_text(yaml.dump(cfg))
    config = load_config(p)
    assert config.pipeline.max_concurrent_jobs == 3
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_pipeline_max_concurrent_jobs_default tests/test_config.py::test_pipeline_max_concurrent_jobs_from_yaml -v`
Expected: FAIL with `AttributeError: 'PipelineConfig' object has no attribute 'max_concurrent_jobs'`

- [x] **Step 3: Add the field to `PipelineConfig`**

In `src/core/models.py`, find the `PipelineConfig` dataclass and add the new field:

```python
@dataclass
class PipelineConfig:
    frame_queue_size: int = 64
    num_decode_threads: int = 2
    num_inference_threads: int = 1
    max_concurrent_jobs: int = 1
```

- [x] **Step 4: Add the value to the YAML config**

In `config/default.yaml`, update the `pipeline` section:

```yaml
pipeline:
  frame_queue_size: 64
  num_decode_threads: 2
  num_inference_threads: 1
  max_concurrent_jobs: 1
```

- [x] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (all config tests, including the two new ones)

- [x] **Step 6: Commit**

```bash
git add src/core/models.py config/default.yaml tests/test_config.py
git commit -m "feat(config): add max_concurrent_jobs to PipelineConfig

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: 后端并发闸（asyncio.Semaphore）

**Files:**
- Modify: `src/web/app.py`
- Modify: `src/web/routes/jobs.py`
- Modify: `tests/test_api.py`
- Create: `tests/test_concurrency.py`

- [x] **Step 1: Write the failing concurrency test**

Create `tests/test_concurrency.py`:

```python
import asyncio
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.config import load_config
from src.storage.database import Base
from src.storage.repository import CaptureRepository, JobRepository, SegmentRepository
from src.web.app import create_app
from src.web.routes import jobs as jobs_module


@pytest_asyncio.fixture
async def app_with_semaphore():
    """An app instance configured with a 2-permit analysis semaphore."""
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    config = load_config("config/default.yaml")

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app = create_app(lifespan_fn=noop_lifespan)
    app.state.config = config
    app.state.job_repo = JobRepository(session_factory)
    app.state.segment_repo = SegmentRepository(session_factory)
    app.state.capture_repo = CaptureRepository(session_factory)
    app.state.session_factory = session_factory
    app.state.analysis_semaphore = asyncio.Semaphore(2)
    return app


@pytest.mark.asyncio
async def test_concurrency_gate_limits_parallel_jobs(app_with_semaphore, tmp_path, monkeypatch):
    """At most `max_concurrent_jobs` analysis tasks hold the semaphore at once."""
    app = app_with_semaphore
    active = 0
    peak = 0
    lock = asyncio.Lock()
    gate = asyncio.Event()

    async def fake_run(job_id, app):
        nonlocal active, peak
        async with app.state.analysis_semaphore:
            async with lock:
                active += 1
                peak = max(peak, active)
            await gate.wait()
            async with lock:
                active -= 1

    monkeypatch.setattr(jobs_module, "_run_analysis", fake_run)

    # Create 4 video files
    paths = []
    for i in range(4):
        v = tmp_path / f"v{i}.mp4"
        v.write_bytes(b"x")
        paths.append(str(v))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Fire all 4 requests concurrently so their background tasks overlap
        await asyncio.gather(*[ac.post("/api/jobs", json={"file_path": p}) for p in paths])
        # Let the background tasks reach the semaphore acquire
        await asyncio.sleep(0.2)

    # Only 2 may hold the semaphore; the other 2 wait
    assert peak == 2

    # Release all, let them finish cleanly
    gate.set()
    await asyncio.sleep(0.2)
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_concurrency.py -v`
Expected: FAIL — either `AttributeError: 'state' object has no attribute 'analysis_semaphore'` (because `_run_analysis` references `app.state.analysis_semaphore` which we have not added yet, and the real `_run_analysis` would run before monkeypatching takes effect on the first call) or the real `_run_analysis` runs (it will try to load the YOLO model / read the file and fail). The test must not pass yet.

- [x] **Step 3: Initialize the semaphore in `lifespan`**

In `src/web/app.py`, add the `import asyncio` at the top (with the other imports) and initialize the semaphore inside the `lifespan` function. The full updated `lifespan`:

```python
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from src.core.config import load_config
from src.storage.database import init_db
from src.storage.repository import CaptureRepository, JobRepository, SegmentRepository
from src.web.routes.jobs import create_jobs_router
from src.web.routes.results import create_results_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config(Path("config/default.yaml"))
    session_factory = await init_db(config.storage.database_url)
    job_repo = JobRepository(session_factory)
    segment_repo = SegmentRepository(session_factory)
    capture_repo = CaptureRepository(session_factory)

    app.state.config = config
    app.state.job_repo = job_repo
    app.state.segment_repo = segment_repo
    app.state.capture_repo = capture_repo
    app.state.session_factory = session_factory
    app.state.analysis_semaphore = asyncio.Semaphore(config.pipeline.max_concurrent_jobs)

    yield
```

(Rest of `app.py` — `create_app`, `app = create_app()` — stays unchanged.)

- [x] **Step 4: Wrap `_run_analysis` with the semaphore**

In `src/web/routes/jobs.py`, modify `_run_analysis` so its entire body is wrapped in `async with app.state.analysis_semaphore:`. The function currently starts like this:

```python
async def _run_analysis(job_id: str, app):
    import time as time_mod

    from src.core.config import load_config
    from src.detection.yolo_detector import YOLOv8Detector
    ...
    try:
        await job_repo.update_status(job_id, "processing")
        ...
```

Change it to acquire the semaphore **before** setting `processing`, so queued jobs stay `pending`:

```python
async def _run_analysis(job_id: str, app):
    async with app.state.analysis_semaphore:
        import time as time_mod

        from src.core.config import load_config
        from src.detection.yolo_detector import YOLOv8Detector
        from src.pipeline.capture_saver import CaptureSaver, get_capture_output_dir
        from src.pipeline.coordinator import PipelineCoordinator
        from src.storage.repository import CaptureCreate, SegmentCreate
        from src.video.reader import OpenCVFrameReader
        from src.video.sampler import compute_frame_indices

        config = app.state.config
        job_repo = app.state.job_repo
        segment_repo = app.state.segment_repo
        capture_repo = app.state.capture_repo

        try:
            await job_repo.update_status(job_id, "processing")
            job = await job_repo.get(job_id)

            # Read metadata with a temporary reader
            meta_reader = OpenCVFrameReader()
            meta = meta_reader.open(job.file_path)
            meta_reader.close()

            await job_repo.update_video_metadata(
                job_id, meta.duration_seconds, meta.fps, meta.width, meta.height, meta.total_frames
            )

            frame_indices = compute_frame_indices(meta.fps, config.sampling.fps, meta.total_frames)

            detector = YOLOv8Detector(
                model_name=config.detection.model_name,
                device=config.detection.device,
                target_classes=config.detection.target_classes,
                confidence_threshold=config.detection.confidence_threshold,
                batch_size=config.detection.batch_size,
            )

            coordinator = PipelineCoordinator(
                reader_factory=OpenCVFrameReader,
                video_path=job.file_path,
                detector=detector,
                sampling_config=config.sampling,
                detection_config=config.detection,
                aggregation_config=config.aggregation,
                pipeline_config=config.pipeline,
            )

            t0 = time_mod.monotonic()
            result = coordinator.run(frame_indices, meta.fps)
            elapsed = time_mod.monotonic() - t0

            segments = result.segments
            captures = result.captures

            if segments:
                await segment_repo.bulk_create(
                    job_id,
                    [
                        SegmentCreate(
                            start_time=s.start_time,
                            end_time=s.end_time,
                            detection_count=s.detection_count,
                            avg_confidence=s.avg_confidence,
                            max_confidence=s.max_confidence,
                        )
                        for s in segments
                    ],
                )

            # Save capture images
            if captures:
                output_dir = get_capture_output_dir(job.file_path)
                saver = CaptureSaver(output_dir)
                all_capture_results = []
                for capture_data in captures:
                    results = saver.save_segment_captures(capture_data)
                    all_capture_results.extend(results)

                # Store capture paths in database
                if all_capture_results:
                    await capture_repo.bulk_create(
                        job_id,
                        [
                            CaptureCreate(
                                segment_index=r.segment_index,
                                timestamp=r.timestamp,
                                confidence=r.confidence,
                                crop_path=r.crop_path,
                                annotated_path=r.annotated_path,
                            )
                            for r in all_capture_results
                        ],
                    )

            total_person_time = sum(s.duration for s in segments)
            await job_repo.update_summary(job_id, len(segments), total_person_time, elapsed)
            await job_repo.update_status(job_id, "completed")
        except Exception as e:
            await job_repo.update_status(job_id, "failed", str(e))
```

(Only the `async with app.state.analysis_semaphore:` wrapper and one level of indentation are added; the inner logic is identical to the original.)

- [x] **Step 5: Update the shared `client` fixture to set the semaphore**

In `tests/test_api.py`, the `client` fixture uses `noop_lifespan` and sets `app.state` manually, so it bypasses the real `lifespan` that now creates `analysis_semaphore`. Add the semaphore to the fixture so existing tests (which trigger `_run_analysis` via `BackgroundTasks`) don't hit `AttributeError`.

Add `import asyncio` near the top of `tests/test_api.py` (after the existing imports), then update the `client` fixture's `app.state` setup block:

```python
@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    config = load_config("config/default.yaml")

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app = create_app(lifespan_fn=noop_lifespan)
    app.state.config = config
    app.state.job_repo = JobRepository(session_factory)
    app.state.segment_repo = SegmentRepository(session_factory)
    app.state.capture_repo = CaptureRepository(session_factory)
    app.state.session_factory = session_factory
    app.state.analysis_semaphore = asyncio.Semaphore(config.pipeline.max_concurrent_jobs)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

- [x] **Step 6: Run the concurrency test to verify it passes**

Run: `uv run pytest tests/test_concurrency.py -v`
Expected: PASS

- [x] **Step 7: Run the full backend test suite to verify no regressions**

Run: `uv run pytest -v`
Expected: PASS (all tests, including `test_api.py` and `test_concurrency.py`). Note: tests that trigger the real `_run_analysis` (e.g. `test_create_job`) may leave the job in `failed` status if no GPU is present — that is pre-existing behavior and the assertions in those tests only check the `201`/`pending` creation response, which still holds.

- [x] **Step 8: Commit**

```bash
git add src/web/app.py src/web/routes/jobs.py tests/test_api.py tests/test_concurrency.py
git commit -m "feat(web): add asyncio.Semaphore concurrency gate for analysis jobs

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: 前端 vitest 测试基础设施

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`

- [x] **Step 1: Install test dependencies**

Run from the `frontend/` directory:

```bash
cd frontend
npm install -D vitest @vue/test-utils jsdom
```

(Do not pin versions — let npm resolve the latest versions compatible with the installed Vite. If the install fails due to a Vite major-version mismatch, install the `vitest` major that matches the installed `vite` — check with `npm ls vite` first.)

- [x] **Step 2: Add the vitest config**

Create `frontend/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
  },
})
```

- [x] **Step 3: Add test scripts to `package.json`**

In `frontend/package.json`, add `test` and `test:watch` scripts alongside the existing `dev`/`build`/`preview` scripts in the `"scripts"` block:

```json
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
```

- [x] **Step 4: Verify vitest runs (no tests yet)**

Run from `frontend/`:

```bash
cd frontend
npm test
```

Expected: vitest runs and reports "No test files found" (exit code may be non-zero due to no tests — that's fine for this step; the goal is to confirm vitest is installed and the config is valid).

- [x] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts
git commit -m "chore(frontend): add vitest + @vue/test-utils + jsdom test setup

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: 前端 `submitItems` 纯逻辑函数（TDD）

**Files:**
- Create: `frontend/src/utils/submitItems.ts`
- Create: `frontend/src/utils/submitItems.spec.ts`

- [x] **Step 1: Write the failing tests**

Create `frontend/src/utils/submitItems.spec.ts`:

```ts
import { describe, it, expect, vi } from 'vitest'
import { submitItems, extractError, basename } from './submitItems'
import type { PendingItem } from './submitItems'

function makeItem(path: string): PendingItem {
  return { id: path, path, filename: basename(path), status: 'pending' }
}

const job = (id: string, filename: string) => ({
  id,
  filename,
  status: 'pending',
  created_at: '',
  total_segments: 0,
  total_person_time: 0,
})

describe('submitItems', () => {
  it('returns ok outcomes for all successful creations, in order', async () => {
    const createJob = vi
      .fn<((path: string) => Promise<typeof job>)>()
      .mockResolvedValueOnce(job('job-1', 'a.mp4'))
      .mockResolvedValueOnce(job('job-2', 'b.mp4'))

    const outcomes = await submitItems(
      [makeItem('D:\\a.mp4'), makeItem('D:\\b.mp4')],
      createJob
    )

    expect(outcomes).toEqual([
      { id: 'D:\\a.mp4', ok: true, jobId: 'job-1' },
      { id: 'D:\\b.mp4', ok: true, jobId: 'job-2' },
    ])
    expect(createJob).toHaveBeenCalledTimes(2)
    expect(createJob).toHaveBeenNthCalledWith(1, 'D:\\a.mp4')
    expect(createJob).toHaveBeenNthCalledWith(2, 'D:\\b.mp4')
  })

  it('marks a failed item with the backend detail without stopping the rest', async () => {
    const createJob = vi
      .fn<((path: string) => Promise<typeof job>)>()
      .mockResolvedValueOnce(job('job-1', 'a.mp4'))
      .mockRejectedValueOnce({ response: { data: { detail: 'Unsupported format: .wmv' } } })

    const outcomes = await submitItems(
      [makeItem('D:\\a.mp4'), makeItem('D:\\bad.wmv')],
      createJob
    )

    expect(outcomes[0].ok).toBe(true)
    expect(outcomes[0].jobId).toBe('job-1')
    expect(outcomes[1].ok).toBe(false)
    expect(outcomes[1].error).toBe('Unsupported format: .wmv')
  })
})

describe('extractError', () => {
  it('extracts detail from an axios-like error', () => {
    expect(extractError({ response: { data: { detail: 'File not found' } } })).toBe('File not found')
  })
  it('falls back to Error.message', () => {
    expect(extractError(new Error('boom'))).toBe('boom')
  })
  it('falls back to a default message for unknown shapes', () => {
    expect(extractError('weird')).toBe('创建任务失败')
  })
})

describe('basename', () => {
  it('handles Windows backslash paths', () => {
    expect(basename('D:\\videos\\cam.mp4')).toBe('cam.mp4')
  })
  it('handles POSIX slash paths', () => {
    expect(basename('/home/u/v.mp4')).toBe('v.mp4')
  })
})
```

- [x] **Step 2: Run test to verify it fails**

Run from `frontend/`:

```bash
cd frontend
npm test -- src/utils/submitItems.spec.ts
```

Expected: FAIL — `Cannot find module './submitItems'`

- [x] **Step 3: Implement `submitItems.ts`**

Create `frontend/src/utils/submitItems.ts`:

```ts
import type { Job } from '../api/client'

export type PendingItemStatus = 'pending' | 'submitting' | 'error'

export interface PendingItem {
  id: string
  path: string
  filename: string
  status: PendingItemStatus
  error?: string
}

export interface SubmitOutcome {
  id: string
  ok: boolean
  jobId?: string
  error?: string
}

/** Extract a human-readable message from a thrown value (axios errors carry `response.data.detail`). */
export function extractError(err: unknown): string {
  if (err && typeof err === 'object') {
    const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  if (err instanceof Error) return err.message
  return '创建任务失败'
}

/** Return the file name portion of a path, handling both `\` and `/` separators. */
export function basename(path: string): string {
  const parts = path.split(/[\\/]/)
  return parts[parts.length - 1] || path
}

/**
 * Submit every pending item by calling `createJob` for each, in order.
 * A failure on one item does not stop the rest. Returns one outcome per input item
 * (same length, same order). The caller is responsible for removing successful items
 * from the UI list and emitting `job-created` for each.
 */
export async function submitItems(
  items: PendingItem[],
  createJob: (path: string) => Promise<Job>
): Promise<SubmitOutcome[]> {
  const outcomes: SubmitOutcome[] = []
  for (const item of items) {
    try {
      const job = await createJob(item.path)
      outcomes.push({ id: item.id, ok: true, jobId: job.id })
    } catch (err) {
      outcomes.push({ id: item.id, ok: false, error: extractError(err) })
    }
  }
  return outcomes
}
```

- [x] **Step 4: Run test to verify it passes**

Run from `frontend/`:

```bash
cd frontend
npm test -- src/utils/submitItems.spec.ts
```

Expected: PASS (all `submitItems` / `extractError` / `basename` tests)

- [x] **Step 5: Commit**

```bash
git add frontend/src/utils/submitItems.ts frontend/src/utils/submitItems.spec.ts
git commit -m "feat(frontend): add submitItems batch-submit logic + tests

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: 前端 `PendingList` 组件（TDD）

**Files:**
- Create: `frontend/src/components/PendingList.vue`
- Create: `frontend/src/components/PendingList.spec.ts`

- [x] **Step 1: Write the failing tests**

Create `frontend/src/components/PendingList.spec.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PendingList from './PendingList.vue'
import type { PendingItem } from '../utils/submitItems'

function item(overrides: Partial<PendingItem> = {}): PendingItem {
  return {
    id: '1',
    path: 'D:\\vids\\a.mp4',
    filename: 'a.mp4',
    status: 'pending',
    ...overrides,
  }
}

describe('PendingList', () => {
  it('renders nothing when the list is empty', () => {
    const wrapper = mount(PendingList, { props: { items: [] } })
    expect(wrapper.find('.pending-list').exists()).toBe(false)
  })

  it('lists items with their filename and path, and shows the count', () => {
    const wrapper = mount(PendingList, {
      props: {
        items: [
          item({ id: '1', filename: 'a.mp4', path: 'D:\\vids\\a.mp4' }),
          item({ id: '2', filename: 'b.mp4', path: 'D:\\vids\\b.mp4' }),
        ],
      },
    })
    const names = wrapper.findAll('.item .filename').map((n) => n.text())
    expect(names).toEqual(['a.mp4', 'b.mp4'])
    expect(wrapper.find('.title').text()).toContain('2')
    expect(wrapper.find('.submit-btn').text()).toContain('2')
  })

  it('emits remove with the item id when the remove button is clicked', async () => {
    const wrapper = mount(PendingList, {
      props: { items: [item({ id: 'abc', filename: 'a.mp4' })] },
    })
    await wrapper.find('.item .remove').trigger('click')
    expect(wrapper.emitted('remove')).toBeTruthy()
    expect(wrapper.emitted('remove')![0]).toEqual(['abc'])
  })

  it('emits submit when the submit button is clicked', async () => {
    const wrapper = mount(PendingList, {
      props: { items: [item()] },
    })
    await wrapper.find('.submit-btn').trigger('click')
    expect(wrapper.emitted('submit')).toBeTruthy()
  })

  it('shows the error message and marks the row as error for failed items', () => {
    const wrapper = mount(PendingList, {
      props: {
        items: [
          item({
            id: '1',
            filename: 'bad.wmv',
            path: 'D:\\bad.wmv',
            status: 'error',
            error: 'Unsupported format: .wmv',
          }),
        ],
      },
    })
    const row = wrapper.find('.item')
    expect(row.classes()).toContain('error')
    expect(wrapper.find('.error-msg').text()).toBe('Unsupported format: .wmv')
  })

  it('shows a spinner indicator for submitting items', () => {
    const wrapper = mount(PendingList, {
      props: { items: [item({ status: 'submitting' })] },
    })
    const row = wrapper.find('.item')
    expect(row.classes()).toContain('submitting')
    expect(wrapper.find('.status').exists()).toBe(true)
  })
})
```

- [x] **Step 2: Run test to verify it fails**

Run from `frontend/`:

```bash
cd frontend
npm test -- src/components/PendingList.spec.ts
```

Expected: FAIL — `Cannot find module './PendingList.vue'`

- [x] **Step 3: Implement `PendingList.vue`**

Create `frontend/src/components/PendingList.vue`:

```vue
<script setup lang="ts">
import type { PendingItem } from '../utils/submitItems'

defineProps<{ items: PendingItem[] }>()
const emit = defineEmits<{
  remove: [id: string]
  submit: []
}>()
</script>

<template>
  <div v-if="items.length > 0" class="pending-list">
    <div class="header">
      <span class="title">📋 待提交清单 ({{ items.length }})</span>
      <span class="hint">逐条提交，失败的会标红</span>
    </div>

    <div
      v-for="item in items"
      :key="item.id"
      class="item"
      :class="{ error: item.status === 'error', submitting: item.status === 'submitting' }"
    >
      <span class="icon">🎬</span>
      <span class="filename">{{ item.filename }}</span>
      <span class="path">{{ item.path }}</span>
      <span v-if="item.status === 'submitting'" class="status">⏳</span>
      <span v-else-if="item.status === 'error'" class="error-msg">{{ item.error }}</span>
      <button class="remove" title="移除" @click="emit('remove', item.id)">✕</button>
    </div>

    <button class="submit-btn" @click="emit('submit')">
      ▶ 开始分析 ({{ items.length }})
    </button>
  </div>
</template>

<style scoped>
.pending-list {
  margin-top: var(--space-4);
  background: var(--bg-primary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}

.title {
  font-weight: 600;
  font-size: var(--text-sm);
}

.hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-secondary);
  font-size: var(--text-sm);
}

.item.error {
  background: rgba(248, 81, 73, 0.08);
}

.icon {
  flex-shrink: 0;
}

.filename {
  font-weight: 500;
  color: var(--text-primary);
}

.path {
  flex: 1;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status {
  color: var(--accent-blue);
}

.error-msg {
  color: var(--accent-red);
  font-size: var(--text-xs);
  flex: 1;
}

.remove {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: var(--text-sm);
  padding: 0 var(--space-1);
}

.remove:hover {
  color: var(--accent-red);
}

.submit-btn {
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-5);
  background: var(--gradient-blue);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.submit-btn:hover {
  box-shadow: var(--shadow-glow-blue);
}
</style>
```

- [x] **Step 4: Run test to verify it passes**

Run from `frontend/`:

```bash
cd frontend
npm test -- src/components/PendingList.spec.ts
```

Expected: PASS (all 6 PendingList tests)

- [x] **Step 5: Commit**

```bash
git add frontend/src/components/PendingList.vue frontend/src/components/PendingList.spec.ts
git commit -m "feat(frontend): add PendingList component + tests

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: 前端 `FileBrowser` 单选改多选（TDD）

**Files:**
- Modify: `frontend/src/components/FileBrowser.vue`
- Create: `frontend/src/components/FileBrowser.spec.ts`

- [x] **Step 1: Write the failing tests**

Create `frontend/src/components/FileBrowser.spec.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FileBrowser from './FileBrowser.vue'
import * as api from '../api/client'

vi.mock('../api/client', () => ({
  browse: vi.fn(),
  getSystemPaths: vi.fn().mockResolvedValue({ paths: [], home: '' }),
}))

function fileItems(): Awaited<ReturnType<typeof api.browse>> {
  return {
    current: 'D:\\vids',
    parent: '',
    items: [
      { name: 'a.mp4', path: 'D:\\vids\\a.mp4', is_dir: false, size_mb: 1 },
      { name: 'b.mp4', path: 'D:\\vids\\b.mp4', is_dir: false, size_mb: 2 },
    ],
  }
}

describe('FileBrowser multi-select', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.body.innerHTML = ''
  })

  it('toggles file selection and emits the selected paths on confirm', async () => {
    vi.mocked(api.browse).mockResolvedValue(fileItems())
    const wrapper = mount(FileBrowser)
    ;(wrapper.vm as any).open()
    await flushPromises()

    const files = document.querySelectorAll('.file-item:not(.dir)')
    expect(files.length).toBe(2)

    await (files[0] as HTMLElement).click()
    await (files[1] as HTMLElement).click()

    const confirm = document.querySelector('.confirm-btn') as HTMLButtonElement
    await confirm.click()

    const emitted = wrapper.emitted('select')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual(['D:\\vids\\a.mp4', 'D:\\vids\\b.mp4'])
  })

  it('deselects a file when clicked again', async () => {
    vi.mocked(api.browse).mockResolvedValue(fileItems())
    const wrapper = mount(FileBrowser)
    ;(wrapper.vm as any).open()
    await flushPromises()

    const file = document.querySelector('.file-item') as HTMLElement
    await file.click() // select
    await file.click() // deselect

    const confirm = document.querySelector('.confirm-btn') as HTMLButtonElement
    await confirm.click()

    const emitted = wrapper.emitted('select')
    expect(emitted![0][0]).toEqual([])
  })

  it('navigates into a directory instead of selecting it', async () => {
    vi.mocked(api.browse)
      .mockResolvedValueOnce({
        current: 'D:\\vids',
        parent: '',
        items: [{ name: 'sub', path: 'D:\\vids\\sub', is_dir: true }],
      })
      .mockResolvedValueOnce({ current: 'D:\\vids\\sub', parent: 'D:\\vids', items: [] })

    const wrapper = mount(FileBrowser)
    ;(wrapper.vm as any).open()
    await flushPromises()

    const dir = document.querySelector('.file-item.dir') as HTMLElement
    await dir.click()
    await flushPromises()

    // Two browse calls: initial open + navigating into the dir
    expect(api.browse).toHaveBeenCalledTimes(2)
    expect(vi.mocked(api.browse).mock.calls[1][0]).toBe('D:\\vids\\sub')
    // Nothing selected yet
    const confirm = document.querySelector('.confirm-btn') as HTMLButtonElement
    await confirm.click()
    expect(wrapper.emitted('select')![0][0]).toEqual([])
  })
})
```

- [x] **Step 2: Run test to verify it fails**

Run from `frontend/`:

```bash
cd frontend
npm test -- src/components/FileBrowser.spec.ts
```

Expected: FAIL — the old `FileBrowser` emits a single string and has no `.confirm-btn`, so `wrapper.emitted('select')` will be `undefined` or have the wrong shape.

- [x] **Step 3: Rework `FileBrowser.vue` for multi-select**

Replace the `<script setup>` block of `frontend/src/components/FileBrowser.vue` with the multi-select version. Keep the `<template>` and `<style>` mostly as-is, but add a confirm bar and selected styling (shown in the next step). New `<script setup>`:

```ts
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { browse } from '../api/client'
import type { BrowseItem } from '../api/client'
import QuickPathBar from './QuickPathBar.vue'

const emit = defineEmits<{ select: [paths: string[]] }>()

const currentPath = ref('')
const parentPath = ref<string | null>(null)
const items = ref<BrowseItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const visible = ref(false)
const selected = ref<Set<string>>(new Set())

const selectedPaths = computed(() => Array.from(selected.value))

async function navigate(path: string) {
  loading.value = true
  error.value = null
  try {
    const result = await browse(path)
    currentPath.value = result.current
    parentPath.value = result.parent
    items.value = result.items
  } catch (err: any) {
    error.value = err.response?.data?.detail || '浏览失败'
  } finally {
    loading.value = false
  }
}

function open() {
  visible.value = true
  selected.value = new Set()
  navigate(currentPath.value)
}

function goUp() {
  if (parentPath.value !== null) {
    navigate(parentPath.value)
  }
}

function handleClick(item: BrowseItem) {
  if (item.is_dir) {
    navigate(item.path)
    return
  }
  // Toggle file selection
  if (selected.value.has(item.path)) {
    selected.value.delete(item.path)
  } else {
    selected.value.add(item.path)
  }
  // Trigger reactivity for the Set
  selected.value = new Set(selected.value)
}

function isSelected(item: BrowseItem) {
  return selected.value.has(item.path)
}

function confirmSelection() {
  emit('select', selectedPaths.value)
  visible.value = false
  selected.value = new Set()
}

function onQuickPath(path: string) {
  navigate(path)
}

defineExpose({ open })
</script>
```

- [x] **Step 4: Update the `FileBrowser.vue` template to reflect selection and add a confirm bar**

In the `<template>` of `frontend/src/components/FileBrowser.vue`, make two changes:

1. On the `file-item` element, bind a `selected` class based on `isSelected(item)` and remove the old single-select close-on-click (now handled by `handleClick`). Replace the existing `<div v-for="item in items" ...>` with:

```html
            <div
              v-for="item in items"
              :key="item.path"
              class="file-item"
              :class="{ dir: item.is_dir, selected: !item.is_dir && isSelected(item) }"
              @click="handleClick(item)"
            >
              <span class="icon">{{ item.is_dir ? '📁' : '🎬' }}</span>
              <span class="name">{{ item.name }}</span>
              <span v-if="!item.is_dir && item.size_mb" class="size">{{ item.size_mb }} MB</span>
              <span v-if="!item.is_dir && isSelected(item)" class="check">✓</span>
            </div>
```

2. Add a confirm bar at the bottom of the `.dialog` (just before the closing `</div>` of `.dialog`, after the `.file-list` block):

```html
          <div class="confirm-bar">
            <span class="selected-count">
              已选 {{ selectedPaths.length }} 个
            </span>
            <button class="confirm-btn" @click="confirmSelection">
              确认选择
            </button>
          </div>
```

3. Add styles for the new elements inside the existing `<style scoped>` block (append at the end, before `</style>`):

```css
.file-item.selected {
  background: rgba(88, 166, 255, 0.12);
}

.file-item.selected .name {
  color: var(--accent-blue);
}

.check {
  color: var(--accent-blue);
  margin-left: auto;
}

.confirm-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--border-primary);
  background: var(--bg-primary);
}

.selected-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.confirm-btn {
  padding: var(--space-2) var(--space-4);
  background: var(--gradient-blue);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
}
```

- [x] **Step 5: Run tests to verify they pass**

Run from `frontend/`:

```bash
cd frontend
npm test -- src/components/FileBrowser.spec.ts
```

Expected: PASS (all 3 FileBrowser tests)

- [x] **Step 6: Commit**

```bash
git add frontend/src/components/FileBrowser.vue frontend/src/components/FileBrowser.spec.ts
git commit -m "feat(frontend): multi-select in FileBrowser + tests

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: `VideoUploader` 改造 + `App.vue` 集成 + 构建验证

**Files:**
- Modify: `frontend/src/components/VideoUploader.vue`
- Modify: `frontend/src/App.vue`

- [x] **Step 1: Rewrite `VideoUploader.vue` to manage a pending list and batch-submit**

Replace the entire contents of `frontend/src/components/VideoUploader.vue` with:

```vue
<script setup lang="ts">
import { ref, computed } from 'vue'
import { createJob } from '../api/client'
import FileBrowser from './FileBrowser.vue'
import PendingList from './PendingList.vue'
import RecentHistory from './RecentHistory.vue'
import { useRecentHistory } from '../composables/useRecentHistory'
import { submitItems, basename, type PendingItem } from '../utils/submitItems'

const emit = defineEmits<{
  'job-created': []
  'open-history': [id: string]
}>()

const draftPath = ref('')
const submitting = ref(false)
const error = ref<string | null>(null)
const browser = ref<InstanceType<typeof FileBrowser> | null>(null)
const items = ref<PendingItem[]>([])
const { addEntry } = useRecentHistory()

const canSubmit = computed(() => items.value.length > 0 && !submitting.value)

function addPath(path: string) {
  const trimmed = path.trim()
  if (!trimmed) return
  if (items.value.some((it) => it.path === trimmed)) return // dedupe
  items.value.push({
    id: crypto.randomUUID(),
    path: trimmed,
    filename: basename(trimmed),
    status: 'pending',
  })
}

function onAddDraft() {
  addPath(draftPath.value)
  draftPath.value = ''
}

function onFilesSelected(paths: string[]) {
  for (const p of paths) {
    addPath(p)
  }
}

function onRemove(id: string) {
  items.value = items.value.filter((it) => it.id !== id)
}

async function onSubmit() {
  if (!canSubmit.value) return
  submitting.value = true
  error.value = null
  try {
    const outcomes = await submitItems(items.value, createJob)
    const remaining: PendingItem[] = []
    for (let i = 0; i < items.value.length; i++) {
      const item = items.value[i]
      const outcome = outcomes[i]
      if (outcome.ok) {
        addEntry({
          id: outcome.jobId!,
          filename: item.filename,
          filePath: item.path,
          status: 'pending',
          createdAt: new Date().toISOString(),
        })
        emit('job-created')
      } else {
        remaining.push({ ...item, status: 'error', error: outcome.error })
      }
    }
    items.value = remaining
    if (remaining.some((it) => it.status === 'error')) {
      error.value = '部分视频提交失败，请查看标红项'
    }
  } catch (err) {
    error.value = '提交失败'
  } finally {
    submitting.value = false
  }
}

function onHistorySelect(id: string) {
  emit('open-history', id)
}
</script>

<template>
  <div class="uploader">
    <h2>
      <span class="icon">🔍</span>
      分析视频
    </h2>
    <form @submit.prevent="onAddDraft">
      <input
        v-model="draftPath"
        type="text"
        placeholder="视频文件路径，可逐条追加，例如 D:\videos\camera1.mp4"
        :disabled="submitting"
        class="path-input"
      />
      <button type="submit" class="add-btn" :disabled="submitting || !draftPath.trim()">
        ＋ 追加
      </button>
      <button
        type="button"
        class="browse-btn"
        @click="browser?.open()"
        :disabled="submitting"
      >
        📁 浏览...
      </button>
    </form>
    <p v-if="error" class="error">{{ error }}</p>

    <PendingList
      :items="items"
      :submitting="submitting"
      @remove="onRemove"
      @submit="onSubmit"
    />

    <FileBrowser ref="browser" @select="onFilesSelected" />
  </div>

  <RecentHistory @select="onHistorySelect" />
</template>

<style scoped>
.uploader {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  transition: all var(--transition-normal);
}

.uploader:hover {
  border-color: rgba(88, 166, 255, 0.3);
}

h2 {
  margin-bottom: var(--space-4);
  font-size: var(--text-lg);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

h2 .icon {
  font-size: 1.2em;
}

form {
  display: flex;
  gap: var(--space-2);
}

.path-input {
  flex: 1;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  transition: all var(--transition-fast);
}

.path-input:focus {
  outline: none;
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15);
}

.path-input::placeholder {
  color: var(--text-muted);
}

.add-btn,
.browse-btn {
  padding: var(--space-2) var(--space-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.add-btn:hover:not(:disabled),
.browse-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--text-secondary);
}

.add-btn:disabled,
.browse-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error {
  color: var(--accent-red);
  font-size: var(--text-sm);
  margin-top: var(--space-2);
}

@media (max-width: 640px) {
  form {
    flex-direction: column;
  }

  .add-btn,
  .browse-btn {
    width: 100%;
  }
}
</style>
```

Note: `PendingList` now receives a `submitting` prop so it can disable its button while submitting. Update `PendingList.vue`'s props and submit button accordingly in Step 2.

- [x] **Step 2: Add the `submitting` prop to `PendingList.vue`**

In `frontend/src/components/PendingList.vue`, update the props definition and the submit button:

Change:
```ts
defineProps<{ items: PendingItem[] }>()
```
to:
```ts
defineProps<{ items: PendingItem[]; submitting?: boolean }>()
```

And change the submit button:
```html
    <button class="submit-btn" @click="emit('submit')">
      ▶ 开始分析 ({{ items.length }})
    </button>
```
to:
```html
    <button class="submit-btn" :disabled="submitting" @click="emit('submit')">
      {{ submitting ? '⏳ 提交中...' : `▶ 开始分析 (${items.length})` }}
    </button>
```

Add a disabled style inside `<style scoped>`:
```css
.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

- [x] **Step 3: Update `App.vue` — new jobs refresh the list (no navigation); history opens a job**

In `frontend/src/App.vue`, replace the `<script setup>` block and wire two events. New `<script setup>`:

```ts
<script setup lang="ts">
import { ref } from 'vue'
import VideoUploader from './components/VideoUploader.vue'
import JobList from './components/JobList.vue'
import JobDetail from './components/JobDetail.vue'
import { useJobsStore } from './stores/jobs'

const currentJobId = ref<string | null>(null)
const store = useJobsStore()

function onJobCreated() {
  // New jobs were submitted: refresh the list and stay on the upload page.
  store.fetchJobs()
}

function onOpenJob(id: string) {
  // Open an existing job (e.g. from recent history): navigate to its detail.
  currentJobId.value = id
}

function onBack() {
  currentJobId.value = null
}
</script>
```

In the `<template>`, update the `<VideoUploader>` usage (inside the `v-if="!currentJobId"` block):

```html
      <template v-if="!currentJobId">
        <VideoUploader @job-created="onJobCreated" @open-history="onOpenJob" />
        <JobList @select="(id: string) => (currentJobId = id)" />
      </template>
```

- [x] **Step 4: Run the full frontend test suite**

Run from `frontend/`:

```bash
cd frontend
npm test
```

Expected: PASS (all submitItems, PendingList, and FileBrowser tests). The `submitting` prop added to `PendingList` is optional, so the existing PendingList tests still pass.

- [x] **Step 5: Verify the frontend type-checks and builds**

Run from `frontend/`:

```bash
cd frontend
npm run build
```

Expected: `vue-tsc` type-check passes and `vite build` completes with no errors. If `vue-tsc` reports a type error in the FileBrowser test's `vi.fn<...>()` generic, simplify the mock to `vi.fn()` (drop the explicit generic) — the assertions do not depend on it.

- [x] **Step 6: Run the backend test suite once more**

Run from the project root:

```bash
uv run pytest -v
```

Expected: PASS (no backend changes in this task; sanity check that nothing regressed).

- [x] **Step 7: Manual end-to-end verification**

1. Start the backend: `uv run uvicorn src.web.app:app --reload` (from project root).
2. Start the frontend: `cd frontend && npm run dev`.
3. Open `http://localhost:5173`.
4. Click 📁 浏览, multi-select 2–3 video files, click 确认选择 — they appear in the 待提交清单.
5. Type a path in the input and click ＋ 追加 — it appends (and a duplicate path is ignored).
6. Click ▶ 开始分析 — successful items disappear from the list and appear in 分析任务 below; any invalid file stays in the list marked red with the backend's error.
7. Confirm the page does **not** navigate away on submit.
8. Click 查看 on a job to open its detail; click 返回列表 to return.

- [x] **Step 8: Commit**

```bash
git add frontend/src/components/VideoUploader.vue frontend/src/components/PendingList.vue frontend/src/App.vue
git commit -m "feat(frontend): batch video upload via pending list + stay-on-page submit

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- §1 各关键决策 → Task 1 (config), Task 2 (semaphore), Task 4–7 (frontend), all covered.
- §2 改动边界表 → every file in that table maps to a task. ✓ (App.vue was added to the table during spec review → Task 7.)
- §3 PendingList (Task 5), VideoUploader (Task 7), FileBrowser multi-select (Task 6), App.vue no-jump (Task 7), api/client.ts unchanged (no task needed — explicitly skipped). ✓
- §3.2 "submitItems 抽成可独立调用函数" → Task 4. ✓
- §4 后端并发闸（lifespan init, `_run_analysis` wrap, pending semantics, config） → Task 1 + Task 2. ✓
- §5 错误处理三层 → Task 4 extractError (frontend) + existing 400 (backend, unchanged) + Task 7 onSubmit retry-on-error. 重复路径去重 → Task 7 `addPath` dedupe. 提交中禁用 → Task 7 `canSubmit`/`submitting` prop. ✓
- §6 测试策略 → Task 2 (concurrency), Task 4 (submitItems), Task 5 (PendingList), Task 6 (FileBrowser). 现有 test_api.py 不变性 → Task 2 Step 7 verifies. ✓

**2. Placeholder scan:** No TBD/TODO/"implement later". All code blocks are complete. ✓

**3. Type consistency:**
- `PendingItem` (id, path, filename, status, error?) — defined in `submitItems.ts` (Task 4), used in `PendingList.vue` (Task 5) and `VideoUploader.vue` (Task 7). ✓
- `submitItems(items, createJob)` signature — Task 4 defines, Task 7 calls with `(items.value, createJob)`. ✓
- `SubmitOutcome { id, ok, jobId?, error? }` — Task 4 defines, Task 7 reads `outcome.ok` / `outcome.jobId` / `outcome.error`. ✓
- FileBrowser emits `select: [paths: string[]]` — Task 6 defines, Task 7 `@select="onFilesSelected"` with `(paths: string[])`. ✓
- `job-created` now emits `[]` (no payload) — Task 7 VideoUploader emits `job-created` with no arg, App.vue `onJobCreated()` takes no arg. ✓ (was `job-created: [id]` before; the spec said App no longer needs the id — consistent.)
- `PendingList` `submitting` prop — added in Task 7 Step 2; VideoUploader passes `:submitting="submitting"`. ✓
- `basename` — defined Task 4, used in Task 7 `addPath`. ✓
- `extractError` — defined Task 4, used inside `submitItems` Task 4. ✓

**4. Ambiguity / risk notes (made explicit in-plan):**
- vitest version resolution left to npm (Task 3 Step 1) with a documented fallback.
- BackgroundTasks per-request ordering handled by `asyncio.gather` in the concurrency test (Task 2 Step 1) so the semaphore is actually contended.
- `App.vue` two-event split (`job-created` vs `open-history`) preserves the existing recent-history "open job" behavior that would otherwise break — documented in Task 7 Step 3.

No gaps found. Plan is ready.
