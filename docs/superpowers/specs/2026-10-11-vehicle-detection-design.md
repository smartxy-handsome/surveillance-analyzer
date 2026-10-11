# 车辆识别功能设计(流程文档)

> 状态:**设计定稿,未开始实现**。> **状态:已实现(2026-10-12)。** 与设计的两处偏差:车辆路径复用 TrackAggregator/SegmentCaptureCollector(新增最佳帧槽)而非独立 VehicleEventTracker;vehicle_events 不持有 capture 外键,前端按 (事件序号, kind) 关联 captures。港澳牌由 HyperLPR3 类型枚举原生部分支持(BLACK_HK_MACAO / HK_SINGLE 等),识别文字依赖其模型,失败按决策 4 留空。

> 本文档是后续编程的依据;实现时按"实施阶段"小节逐任务推进,每个任务配测试。
> 决策记录(2026-10-11 用户确认):见"需求与已定决策"。

## 需求与已定决策

对视频分析增加车辆识别能力。分析前选择检测目标:人体 / 车辆 / 两者。

1. **车辆范围**:四轮及以上机动车——COCO 类 `car(2)`、`bus(5)`、`truck(7)`。**不含**摩托车/自行车(`motorcycle(3)` 排除):驾驶员不会被驾驶舱遮挡,由人体识别覆盖。
2. **车牌地域**:中国大陆(蓝/绿/黄牌)为主,另支持**香港、澳门**车牌。新能源车无独立检测类别——COCO 不区分燃油/新能源,靠**绿牌**在车牌层区分(HyperLPR 返回车牌类型)。
3. **输出形态**:选择了人体+车辆两者时,**同一个任务**内输出两组结果,详情页提供**切换选项**(人体结果 / 车辆结果),不做两个任务。
4. **车牌识别失败**:留空 + 置信度展示,不写"未知"等占位文本,截图保留供人工辨认。

每辆识别到的车辆保存三张截图:**驶入画面时一张、驶出画面时一张、车牌特写一张**;展示驶入、驶出时间与尽可能识别到的车牌号。

## 核心架构判断:车辆需要目标级跟踪

现有人体识别是**帧级布尔聚合**(画面里有没有人 → 时间段)。车辆需求是**每辆车独立**的驶入/驶出事件:两辆车时间交错时,布尔聚合会把它们糊成一段,车牌无法归属。

因此车辆路径引入 **ByteTrack 目标跟踪**(ultralytics 原生 `model.track(persist=True, tracker="bytetrack.yaml")`,离线视频可用,支持批量按序送帧):

- track 的首次出现 = **驶入**;track 的消失 = **驶出**
- track 生命周期内**车辆框面积最大**的一帧(离镜头最近、车牌像素最多)= 车牌特写候选帧
- 同一 track 框定同一辆车的全部三张截图与时间

人体路径**维持布尔聚合不变**;两者共享同一次推理(`classes=[0,2,5,7]` 一次前向,按类分派到两个消费者),推理成本不随"两者都选"翻倍。

## 数据流(车辆路径)

```
解码线程 → 帧队列 → 推理(track 模式, classes=[2,5,7])
                         │
                         ├─ per-frame 车辆框 + track_id
                         ▼
              VehicleEventTracker(新增)
                按 track_id 聚合:
                  - 首帧时间 / 末帧时间(驶入、驶出)
                  - 最大框面积帧(车牌特写候选)
                         │ 流水线结束后
                         ▼
              PlateRecognizer(新增, HyperLPR3)
                对特写候选帧:裁剪车辆 → 检测车牌区域 → 裁剪车牌 → OCR
                         ▼
              CaptureSaver(扩展)
                seg 驶入图 / 驶出图 / 车牌图 三类文件落盘
                data/captures/{job_id}/
                         ▼
              DB: vehicle_events + captures 扩展列
```

## 组件设计

### 1. 检测目标选择

- `DetectionConfig` 增加 `target` 语义或由 job 级参数传入(见数据模型);`YOLOv8Detector` 已支持 `target_classes` 列表,**无需改动**检测器本身。
- 类别映射:`person → [0]`;`vehicle → [2,5,7]`;`both → [0,2,5,7]`。
- `FrameDetection.has_person` 字段名在车辆模式下语义不符,新增别名/改名 `has_target`(保持兼容)。

### 2. VehicleEventTracker(新增,`src/pipeline/vehicle_tracker.py`)

- 输入:逐帧 (timestamp, boxes, track_ids, confidences, class_ids)
- 状态:track_id → {first_time, last_time, first_frame, last_frame, best_frame(面积最大), best_boxes}
- track 消失判定:离线批处理中,track 在其后 N 帧采样内不再出现即视为驶出(ByteTrack 的 track_id 不会复活;流水线结束时所有未闭合 track 一律闭合)
- 输出:`VehicleEvent(track_id, enter_time, exit_time, enter_frame, exit_frame, plate_frame, boxes...)` 列表

### 3. PlateRecognizer(新增,`src/detection/plate_recognizer.py`)

- 依赖:`hyperlpr3`(pip);CPU 可跑,仅对特写候选帧调用(每辆车一次,成本可忽略)
- 流程:候选帧 → 裁剪车辆区域 → HyperLPR 车牌检测(定位车牌框)→ 裁剪车牌 → OCR 文本 + 车牌类型(绿牌=新能源)
- 返回:`PlateResult(number: str | None, confidence: float, plate_type: str, plate_image: np.ndarray)`
- 识别失败(检测不到车牌/置信度过低):`number=None`,置信度照常返回(决策 4)
- **港澳车牌(风险项,见 Open Questions)**:HyperLPR3 官方主要覆盖大陆牌;港/澳牌样式不同(白底黑字 / 黑底白字)。一期方案:HyperLPR 检测器尝试定位,识别置信度低于阈值则留空;若实测不可用,二期 spike:PaddleOCR 对车牌裁剪图做通用 OCR,或收集港澳牌样本微调。接口按"可替换识别后端"设计。

### 4. 数据模型

```
jobs:            + detection_target  TEXT  ('person' | 'vehicle' | 'both', 默认 'person')
segments:        不动(人体路径不变)
vehicle_events:  新表(id, job_id, track_id, enter_time, exit_time,
                      enter_capture_id, exit_capture_id, plate_capture_id,
                      plate_number NULL, plate_confidence, plate_type NULL)
captures:        + kind TEXT ('appearance' | 'departure' | 'plate';旧数据回填
                      appearance,车辆模式写 departure/plate)
                 (crop_path/annotated_path 复用;plate 抓拍只存 crop)
```

数据库沿用轻量迁移机制(`init_db` 的 PRAGMA 检查 + ALTER,见 `src/storage/database.py`)。

### 5. API

- `POST /api/jobs`:请求体 + `detection_target`(默认 `person`,向后兼容)
- `GET /api/jobs/{id}`:响应 + `detection_target`
- `GET /api/jobs/{id}/vehicle-events`(新增):事件列表,内嵌三张截图 URL 与车牌字段
- 抓拍图片端点 `/api/captures/{id}/image` 复用

### 6. 前端

- 上传页(PendingList 一侧):检测目标选择器(人体 / 车辆 / 两者),随提交清单一起发送
- 详情页:
  - `detection_target == 'person'`:现状不变
  - `'vehicle'`:车辆事件表(驶入时间 | 驶出时间 | 车牌号 | 置信度 | 三张缩略图)
  - `'both'`:页内**切换选项**(人体结果 / 车辆结果),默认人体
- 车牌留空时展示 `—` 与置信度徽标

## 实施阶段(后续编程的任务分解)

> **进度注记(2026-10-11)**:阶段 B 的跟踪基础已提前为**人体路径**落地
> (`TrackAggregator` + ByteTrack,`aggregation.use_tracking`),车辆路径将
> 复用同一套机制并扩展 per-class 消费。

1. **阶段 A:目标选择管道**(先打通最小闭环)
   - jobs 表 `detection_target` 列 + 迁移;API 字段;config 校验;detector 按 job 传类;人体路径回归测试
2. **阶段 B:track 模式**
   - `YOLOv8Detector` 增加 track 路径(`predict` → `track`,批量按序);`FrameDetection` 携带 track_id/class_id
   - 用真实素材(D:\claude\video.mp4)验证 ByteTrack 稳定性(track 抖动/ID 切换率)
3. **阶段 C:车辆事件与三张截图**
   - VehicleEventTracker + CaptureSaver 扩展 + vehicle_events 表 + API + 车辆详情页
4. **阶段 D:车牌识别**
   - PlateRecognizer(HyperLPR3)+ plate 抓拍 + 车牌字段展示
   - 港澳牌 spike(用真实素材中的港澳车辆实测;不可用则记录为二期)
5. **阶段 E:两者都选**
   - 单次推理双消费者;详情页切换选项;混合任务的全链路测试

每阶段独立可交付、测试全绿后合并。

## Open Questions(实现时确认)

- ByteTrack 在**离线批处理 + 8 帧批量**送入时 `persist=True` 的行为需实测(官方路径是流式);若批量不支持,推理改逐帧(track 场景),或批内按序展开
- track 消失判定的 N(容忍帧数)需要用真实素材调参:取太小会把红绿灯停车误判为"驶出"
- 港澳车牌:HyperLPR3 实测通过率;决定是否引入 PaddleOCR 二级后端
- 车牌特写若车尾/车头被遮挡(进出画面瞬间),回退取 track 内次大面积帧
- 夜间/逆光下车辆检测置信度阈值(默认沿用 0.5,实测再调)

## 明确不做(一期)

- 摩托车/自行车(人体识别覆盖)
- 车辆品牌/车型识别
- 跨摄像头车辆重识别(ReID)
- 车牌超分辨率(二期视识别率再议)
