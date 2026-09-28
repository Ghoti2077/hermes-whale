# DeepSeek Whale 🐋

一只趴在桌面上的 DeepSeek 余额鲸鱼娘 —— 透明无边框、可拖拽甩抛、点击有 Q 弹反馈和音效，**跟随 Hermes 开关**（开 Hermes 她出现，关 Hermes 她退出）。

![whale](art/whale.png)

---

## 特性

| | |
|---|---|
| 🐋 **余额显示** | 气泡里显示 DeepSeek 账户余额，60 秒自动刷新，点她一下立刻刷新 |
| 🖱️ **拖拽 / 甩抛** | 跟手拖动；快速甩出去会抛物线飞出、撞屏幕边缘反弹、摩擦停下 |
| 🧲 **四边吸附** | 松手自动吸到最近的屏幕边；贴左/贴右时**整体水平镜像**（连文字一起翻）|
| 🧸 **按压 Q 弹** | 点击时挤压 560ms 再弹回，伴随两声小黄鸭音效 |
| 🔗 **跟随 Hermes** | Hermes 开着 → 她在；Hermes 关掉 → 她自己退出，不留后台 |
| 🪟 **真透明** | 用 PyQt6 的 `WA_TranslucentBackground`（per-pixel alpha），不是色键 |
| 🔊 **无延迟音效** | 启动时预热全部音频，快速连点也不卡 |

## 环境要求

- **Windows 10/11**
- **Python 3.11+**（安装时勾选 *Add python.exe to PATH*）
- **PyQt6**

```bash
pip install PyQt6
```

## 两种用法

### ① 独立运行（最快，不需要 Hermes）

1. 把整个文件夹放到任意位置（路径**不要**含空格）
2. **双击 `start.vbs`** —— 没有窗口、没有黑框，鲸鱼直接出现

> `start.vbs` 会自动在 PATH 和常见 Python 安装位置里找 `pythonw.exe`。
> 用的是 `pythonw`（无控制台）+ `WScript.Shell.Run(..., 0, ...)`（隐藏窗口），
> 所以**不会**出现黑色终端，也**不会**因为关掉某个终端而连带退出。

### ② 当 Hermes 插件用（跟随 Hermes 开关）

1. 把整个文件夹拷到 Hermes 插件目录：
   ```
   %LOCALAPPDATA%\hermes\plugins\deepseek-whale\
   ```
2. 启用它：
   ```bash
   hermes plugins enable deepseek-whale
   ```
3. **重启 Hermes** → 鲸鱼自动出现；关掉 Hermes → 鲸鱼自动退出

> 插件版还有额外的状态栏 chip（余额直接显示在 Hermes 状态栏右侧）。

## API Key 配置

余额从 DeepSeek 官方接口读：`GET https://api.deepseek.com/user/balance`

按以下顺序查找 key：

1. 环境变量 `DEEPSEEK_API_KEY`
2. Hermes 的 `.env` 文件（`%LOCALAPPDATA%\hermes\.env`）

**key 只在本机使用，不会上传到任何地方。** 没配 key 时气泡显示 `未配置`。

## 配置

打开 `whale-qt.pyw`，文件开头是配置区：

```python
IMG_W = 220             # 鲸鱼宽度（像素），也是窗口宽度
ART_TOP = 0.42          # 角色从窗口 42% 高度处开始，上方留给气泡
BALANCE_FONT_PX = 21    # 余额字号
REFRESH_S = 60          # 自动刷新间隔（秒）
FOLLOW_HERMES = True    # False = 不跟随 Hermes，常驻显示
SNAP_GAP = 0            # 吸附后距离屏幕边的像素
BUBBLE_BOX = (0.10, 0.055, 0.80, 0.30)   # 气泡位置（x, y, 宽, 高，按窗口比例）
BUBBLE_DOTS = (...)     # 气泡和头顶之间那 3 个小圈（贝塞尔弧）
```

改完直接重启鲸鱼（右键 → 退出 → 双击 `start.vbs`）。

## 操作

| 操作 | 效果 |
|---|---|
| **左键点击她** | Q 弹挤压 + 两声小黄鸭，同时刷新余额 |
| **拖拽** | 跟手移动 |
| **快速甩** | 抛物线飞出 + 撞边反弹 + 摩擦停下 |
| **右键** | 菜单：刷新余额 / 手动翻转 / 吸附开关 / 尺寸 / 退出 |

## 排障

| 现象 | 原因 / 解法 |
|---|---|
| 双击 `start.vbs` 没反应 | 没装 Python 或没勾 PATH。命令行跑 `python --version` 确认，再 `pip install PyQt6` |
| 气泡显示 `未配置` | 没找到 `DEEPSEEK_API_KEY`（见上面「API Key 配置」）|
| 出现一个黑色终端窗口 | **那不是鲸鱼**。Hermes 桌面版的后端（`python.exe -m hermes_cli.main`）自带控制台，鲸鱼已经通过 `wscript` 完全脱离它了 |
| 关掉某个终端后鲸鱼没了 | 如果你是用命令行 / `.bat` 启动的，它就成了那个 shell 的子进程。**用 `start.vbs` 双击启动**才完全独立 |
| 日志在哪 | 程序同目录的 `whale-error.log`（超过 1MB 自动清空）|

## 致谢 / 素材来源

**角色图和音效不是原创**，来自这个 MIT 项目：

- [MeteorNOX/DeepSeek-Balance-Whale-Widget](https://github.com/MeteorNOX/DeepSeek-Balance-Whale-Widget) —— DSH（DeepSeek Harness）的小鲸鱼挂件

其中：
- `art/whale.png` ← 由该项目的 `assets/DSniang1.png` 缩放而来
- `sfx/Ya1.wav` `Ya2.wav` `D1.wav` `D2.wav` ← 由该项目的同名 mp3 转换（`tools/mp3-to-wav.py`）
- `sfx/minecraft-exp-orb.wav` ← 该项目原样

本项目同样以 **MIT** 发布，原作者许可已一并保留（见 `LICENSE`）。

## License

MIT —— 见 [LICENSE](LICENSE)
