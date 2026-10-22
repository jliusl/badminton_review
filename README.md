# 羽球飞扬

面向羽毛球单打视频的本地复盘网页。上传比赛视频后，系统自动识别回合、生成比分时间线、在视频左上角同步显示双方姓名与比分，并支持人工校正、重发球标记、换边事件以及完整视频/精彩集锦导出。

## 已实现

- 导入 MP4、MOV、MKV、AVI、M4V、WebM 视频
- 本机路径导入或浏览器上传
- 自动生成 H.264 浏览器预览与缩略图
- 基于高频击球瞬态和静音间隔识别回合
- 基于画面运动与球员半场推断得分方，并标记置信度
- 轻量级羽毛球轨迹跟踪与落点判断，清晰落点优先用于得分建议
- 比分由事件序列推导，修改历史回合后自动级联重算
- 发球方与发球区自动计算：偶数分右区、奇数分左区
- 同一发球方连续两次、同一发球区、比分未变化时自动标记重发候选
- 重发球不计分，可人工确认或改判
- 时间线编辑：调整起止点、拆分、合并、删除、补录、改判得分方
- 有效/无效回合确认：无效回合保留在时间线中，但不计分、不改变发球权与发球区
- 左上方实时比分覆盖层
- 场地四角标定与换边事件
- 导出完整比赛视频或所选回合集锦，烧录中文比分覆盖层
- SQLite 自动保存项目，源视频默认引用原文件

## 启动

首次运行：

```powershell
.\scripts\setup.ps1
```

之后启动：

```powershell
.\scripts\start.ps1
```

浏览器会打开 `http://127.0.0.1:8787/`。

开发模式：

```powershell
.\scripts\dev.ps1
```

## 技术栈

- 前端：React + Vite + TypeScript
- 后端：FastAPI + Python 3.12
- 数据：SQLite
- 视频：FFmpeg、OpenCV
- AI 预处理：NumPy 音频瞬态分析 + OpenCV 羽毛球轨迹跟踪 + 画面运动启发式

## 数据位置

- 数据库：`library/badminton.db`
- 预览与分析文件：`library/projects/`
- 导出视频：`library/outputs/`

视频和比分数据默认只保存在本机。

## 识别边界

当前版本是**可校对的 AI 辅助分析**，不是自动裁判：

- 回合切分依赖现场音频，背景噪音较重时可能需要补录或删除误识别回合。
- 得分方推断优先使用清晰的下坠轨迹与落点，无法可靠判断时回退到画面运动启发式；低置信度回合会进入待确认队列。
- 出界、触网、遮挡和争议球必须人工校对。
- 首版只支持单打和连续累计比分，不套用固定 11/15/21 分制。
- 不支持直播、双打、账号系统和云同步。

导出前必须处理全部待确认回合，避免错误比分被静默写入成片。

## 测试

后端：

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

前端单元测试与构建：

```powershell
cd frontend
npm test
npm run build
```

前端 Playwright E2E 测试会分别运行 Edge 和 Chrome，并使用隔离的 API Mock，不会修改本地项目数据：

```powershell
npm run test:e2e
npm run test:e2e:edge
npm run test:e2e:chrome
npm run test:all
```

在 Windows 下如果 pytest 自动加载插件导致输出卡住，可设置：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
```