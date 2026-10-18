# GitHub 私有仓库 + CI 接入（一次性设置）

CI workflow 已就位（`.github/workflows/ci.yml`）：推送到 master 或开 PR 时，
在 windows-latest 上跑与 `scripts/check.sh` 相同的四步（ruff / pytest /
vitest / vite build）。Windows runner 按 2 倍计费，私有仓库免费额度
2000 分钟/月足够（单次约 20–30 计费分钟，torch 大包走 uv 缓存，首跑后变快）。

## 你需要做的（约 5 分钟）

1. 在 GitHub 上创建**私有**空仓库，例如 `<你的用户名>/surveillance-analyzer`
   （不要勾选任何初始化文件：README/.gitignore/license 都不要）。

2. 本地关联并推送（在仓库根目录执行）：

   ```bash
   git remote add origin https://github.com/<你的用户名>/surveillance-analyzer.git
   git push -u origin master
   ```

   推送时按提示登录（浏览器授权或 PAT）。如果装了 GitHub Desktop 也可以用它发布。

3. 打开仓库的 **Actions** 标签页确认首跑变绿。

## 说明

- `.pt` 权重与 `data/` 均在 .gitignore 中，不会上传。
- 需要真实视频的端到端测试在 CI 上自动跳过（`D:\claude\video.mp4` 不存在时
  skipif 生效），其余 138+ 用例全部执行。
- 以后每次推送/PR，CI 绿了再合并，形成回归保护。
