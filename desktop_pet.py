# -*- coding: utf-8 -*-
"""
希尔菲像素桌宠 (Windows)
素材: assets/spritesheet.webp  (8列 x 9行, 单元 192x208)

动画行分配:
  R1 待机  R2 被拖动向右  R3 被拖动向左  R4 打招呼
  R5 转圈跳舞  R6 打瞌睡  R7 说话  R8 看书  R9 开心大笑

交互:
  - 左键拖拽: 向右/向左自动切换对应拖拽动画
  - 单击: 互动(大笑/打招呼)
  - 长时间无互动: 自动打瞌睡, 点击唤醒
  - 右键菜单: 打招呼 / 跳个舞 / 看会儿书 / 喂苹果 / 大小 / 退出

依赖: Pillow    运行: python desktop_pet.py
"""
import json
import os
import random
import sys
import webbrowser
import tkinter as tk

from tkinter import filedialog

from PIL import Image, ImageTk

try:
    import pystray
    from pystray import Menu as TrayMenu, MenuItem as TrayItem
except Exception:      # 没装 pystray 也能跑，只是没有托盘图标
    pystray = None

APP_NAME = "ElfPet"        # 内部配置目录名（保持不变以免丢失位置记忆）
DISPLAY_NAME = "桌宠Demo"   # 对外显示的应用名（托盘提示等）

# 打包成 exe 后：优先用 exe 同目录的 assets（方便换素材），没有再用打包进程序的
if getattr(sys, "frozen", False):
    EXE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", EXE_DIR)
else:
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = EXE_DIR

ROOT = EXE_DIR
ASSET_DIR = os.path.join(EXE_DIR, "assets")
if not os.path.isdir(ASSET_DIR):
    ASSET_DIR = os.path.join(BUNDLE_DIR, "assets")
SHEET_PATH = os.path.join(ASSET_DIR, "spritesheet.webp")
ICON_PATH = os.path.join(ASSET_DIR, "icon.png")
ICO_PATH = os.path.join(ASSET_DIR, "icon.ico")
CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME, "config.json"
)
# 自定义跳转单独放一个文件：和 config.json（位置/大小）解耦，
# 免得 _save() 保存位置时把它一起覆盖掉
CUSTOM_CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME,
    "desktop_pet_config.json"
)

CELL_W, CELL_H, COLS, ROWS = 192, 208, 8, 9
BASE_HEIGHT = 240
SIZES = {"小": 0.6, "中": 1.0, "大": 1.4}
SM_CXSMICON = 49           # Win32: 托盘等「小图标」的边长（96 DPI 下为 16）

# 自动行为节奏（秒）：每 40~90 秒检查一次，其中 55% 概率真的做一个动作
AUTO_CHECK_MIN = 40
AUTO_CHECK_MAX = 90
AUTO_ACTION_CHANCE = 0.55
SLEEP_AFTER = 180      # 连续无互动多少秒后自动打瞌睡

# name: (row, frame_count, fps)
ANIMS = {
    "idle": (0, 6, 6),
    "drag_right": (1, 8, 16),
    "drag_left": (2, 8, 16),
    "wave": (3, 4, 6),
    "dance": (4, 5, 6),
    "sleep": (5, 8, 4),
    "talk": (6, 6, 6),
    "read": (7, 6, 4),
    "laugh": (8, 6, 6),
}

TALK_LINES = [
    "今天也要元气满满哦~",
    "要一起去采蘑菇吗？",
    "魔法使的一天开始了♪",
    "唔…卢迪乌斯在哪里呀…",
]
PET_LINES = ["嘿嘿，被摸头了~", "好痒好痒♪", "再摸一下也可以哦"]
FEED_LINES = ["哇！苹果！最喜欢了！", "谢谢款待~ 开动了！", "唔姆，很甜很好吃！"]
GREET_LINES = ["你回来啦！", "嘿嘿，我一直在等你哦"]
SLEEP_LINES = ["Zzz…", "呼…呼…"]


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_pet_config():
    """读自定义配置：返回 (网页跳转列表, 本地文件列表)。

    优先读独立的 desktop_pet_config.json；读不到就从旧版 config.json 里的
    custom_items 迁移一次，避免升级后用户配的东西凭空消失。
    """
    def sane(items):
        return [i for i in items if isinstance(i, dict)] \
            if isinstance(items, list) else []

    custom, files = [], []
    try:
        with open(CUSTOM_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            custom = sane(data.get("custom_items"))
            files = sane(data.get("file_items"))
    except Exception:
        pass

    if not custom:
        old = sane(load_json(CONFIG_PATH).get("custom_items"))
        if old:
            custom = old
            save_pet_config(custom, files)   # 顺手落盘，下次就走新文件
    return custom, files


def save_pet_config(custom_items, file_items):
    """写自定义配置（URL 跳转 + 本地文件），返回是否成功。"""
    try:
        os.makedirs(os.path.dirname(CUSTOM_CONFIG_PATH), exist_ok=True)
        with open(CUSTOM_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"version": 1,
                       "custom_items": custom_items,
                       "file_items": file_items}, f,
                      ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def normalize_url(url):
    """补上协议前缀：输 bilibili.com 也当成 https://bilibili.com。"""
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    return url


class Pet(tk.Tk):
    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        key = "magenta"
        self.configure(bg=key)
        self.attributes("-transparentcolor", key)

        cfg = load_json(CONFIG_PATH)
        self.scale = SIZES.get(cfg.get("size", "中"), 1.0)
        # 右键菜单里平铺的两类自定义项：
        #   网页跳转 custom_items: [{"name":..., "url":...}]
        #   本地文件 file_items   : [{"name":..., "path":...}]
        self.custom_items, self.file_items = load_pet_config()
        self._x, self._y = 100, 100
        self._drag_start = None
        self._drag_dir = 0          # -1 左 / 1 右 / 0 无
        self._drag_prev_x = 0       # 上一次拖动事件的屏幕 x，用来判即时方向
        self._last_interact = self._now()
        self._anim_job = None
        self._frame_idx = 0         # 当前动画播到第几帧
        self._move_job = None       # 合并窗口移动的 idle 任务
        self._sleep_job = None
        self._bubble = None
        self.tray = None            # pystray 托盘图标，隐藏后靠它把桌宠召回来
        self._hidden = False        # 是否已隐藏到托盘
        self._config_win = None     # 配置弹窗，只允许开一个
        self.current_anim = ""

        self.label = tk.Label(self, bg=key, bd=0)
        self.label.pack()

        self._load_sheet()
        self._restore_position()
        self._build_menu()

        self.label.bind("<Button-1>", self._on_press)
        self.label.bind("<B1-Motion>", self._on_drag)
        self.label.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Button-3>", self._show_menu)

        self.play("idle")
        self._behavior_loop()
        self._setup_tray()

    @staticmethod
    def _now():
        import time
        return time.time()

    # ---------- 素材加载 ----------
    @staticmethod
    def _hard_alpha(img, threshold=140):
        """alpha 二值化：消除半透明边缘与抠色底色混出的紫色描边。"""
        r, g, b, a = img.split()
        a = a.point(lambda v: 255 if v >= threshold else 0)
        return Image.merge("RGBA", (r, g, b, a))

    def _load_sheet(self):
        sheet = Image.open(SHEET_PATH).convert("RGBA")
        h = int(BASE_HEIGHT * self.scale)
        w = int(CELL_W * h / CELL_H)
        size = (w, h)
        self.frames = {}
        for name, (row, count, _fps) in ANIMS.items():
            imgs = []
            for c in range(count):
                fr = sheet.crop((c * CELL_W, row * CELL_H,
                                 (c + 1) * CELL_W, (row + 1) * CELL_H))
                fr = self._hard_alpha(fr).resize(size, Image.NEAREST)
                imgs.append(ImageTk.PhotoImage(fr))
            self.frames[name] = imgs
        self._img_w, self._img_h = size

    # ---------- 动画状态机 ----------
    def play(self, name, loop=True, on_end=None, keep_phase=False):
        if self._anim_job:
            self.after_cancel(self._anim_job)
            self._anim_job = None
        self.current_anim = name
        frames = self.frames[name]
        _, _, fps = ANIMS[name]
        interval = int(1000 / fps)

        def show(idx):
            self._frame_idx = idx
            self.label.configure(image=frames[idx])
            nxt = idx + 1
            if nxt < len(frames):
                self._anim_job = self.after(interval, lambda: show(nxt))
            elif loop:
                self._anim_job = self.after(interval, lambda: show(0))
            else:
                self._anim_job = None
                if on_end:
                    on_end()

        # keep_phase：接着当前的帧序号播。切换左右方向时用它，动画才不会
        # 每次都跳回第 0 帧，看着像「卡住重来」。
        show(self._frame_idx % len(frames) if keep_phase else 0)

    def back_to_idle(self):
        self.play("idle")

    # ---------- 位置 ----------
    def _move(self, x, y):
        """记下目标位置，把 geometry() 合并到一个 idle 任务里。

        拖动时鼠标事件可达几百 Hz，每个事件都 geometry() 会让带
        -transparentcolor 的分层窗口反复重新合成，挤占事件循环，
        把动画帧的 after 回调往后推，看上去就是「动作变慢」。
        """
        self._x, self._y = x, y
        if self._move_job is None:
            self._move_job = self.after_idle(self._apply_move)

    def _apply_move(self):
        self._move_job = None
        self.geometry("+%d+%d" % (self._x, self._y))

    def _restore_position(self):
        pos = load_json(CONFIG_PATH).get("pos")
        if pos:
            self._move(pos[0], pos[1])
        else:
            self.update_idletasks()
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self._move(sw - self._img_w - 60, sh - self._img_h - 40)

    def _save(self):
        # 自定义跳转现在写在独立的 desktop_pet_config.json 里，
        # 这里只负责位置和大小，不再需要（也不能）带上它
        save_json(CONFIG_PATH, {
            "pos": [self._x, self._y],
            "size": next(k for k, v in SIZES.items()
                         if abs(v - self.scale) < 1e-6),
        })

    # ---------- 行为循环 ----------
    def _behavior_loop(self):
        delay = random.randint(AUTO_CHECK_MIN, AUTO_CHECK_MAX) * 1000
        self.after(delay, self._behavior_tick)

    def _behavior_tick(self):
        idle_secs = self._now() - self._last_interact
        # 隐藏到托盘时不做任何动作：看不见还演，纯浪费 CPU
        if self._current_anim() == "idle" and not self._hidden:
            if idle_secs > SLEEP_AFTER:
                self._do_sleep()
            elif random.random() < AUTO_ACTION_CHANCE:
                r = random.random()
                if r < 0.35:
                    self._do_talk()
                elif r < 0.55:
                    self._do_anim("read")
                elif r < 0.72:
                    self._do_anim("laugh")
                elif r < 0.88:
                    self._do_anim("dance")
                else:
                    self._do_anim("wave")
        self._behavior_loop()

    def _current_anim(self):
        return self.current_anim

    def _do_anim(self, name, say=None):
        if say:
            self._say(say)
        self.play(name, loop=False, on_end=self.back_to_idle)

    def _do_talk(self):
        self._do_anim("talk", random.choice(TALK_LINES))

    def _do_sleep(self):
        self._say(random.choice(SLEEP_LINES), duration=4000)
        self.play("sleep", loop=True)
        # 睡 20 秒后自动醒来
        if self._sleep_job:
            self.after_cancel(self._sleep_job)
        self._sleep_job = self.after(20000, self._wake)

    def _wake(self):
        self._sleep_job = None
        if self._current_anim() == "sleep":
            self._last_interact = self._now()
            self._do_anim("wave", "啊…睡得真好~")

    # ---------- 气泡 ----------
    def _say(self, text, duration=2800):
        if self._bubble is not None and self._bubble.winfo_exists():
            self._bubble.destroy()
        bubble = tk.Toplevel(self)
        bubble.overrideredirect(True)
        bubble.attributes("-topmost", True)
        frame = tk.Frame(bubble, bg="#fffef2",
                         highlightbackground="#8a9a5b", highlightthickness=2)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=text, bg="#fffef2", fg="#4a4a3a",
                 font=("Microsoft YaHei UI", 10), padx=10, pady=6).pack()
        bubble.update_idletasks()
        x = self._x + (self._img_w - bubble.winfo_width()) // 2
        y = self._y - bubble.winfo_height() - 8
        bubble.geometry("+%d+%d" % (max(0, x), max(0, y)))
        self._bubble = bubble
        self.after(duration,
                   lambda: bubble.winfo_exists() and bubble.destroy())

    # ---------- 鼠标交互 ----------
    def _on_press(self, event):
        self._drag_start = (event.x_root, event.y_root,
                            self._x, self._y)
        self._drag_dir = 0
        self._drag_prev_x = event.x_root
        self._last_interact = self._now()
        if self._sleep_job:          # 睡觉时被碰醒
            self.after_cancel(self._sleep_job)
            self._sleep_job = None

    def _on_drag(self, event):
        if not self._drag_start:
            return
        dx = event.x_root - self._drag_start[0]
        dy = event.y_root - self._drag_start[1]
        self._last_interact = self._now()
        if self._sleep_job:
            self.after_cancel(self._sleep_job)
            self._sleep_job = None

        # 方向按「本次事件相对上一次事件的位移」判断，一动就切。
        # 以前用的是相对按下点的累计位移，还带 3px 死区：向右拖到一半往回拖，
        # 只要累计位移仍为正就一直保持向右，方向跟不上手；死区又让刚按下时
        # 必须先拖一小段才换动作。
        step = event.x_root - self._drag_prev_x
        self._drag_prev_x = event.x_root
        if step:
            direction = 1 if step > 0 else -1
        elif self._drag_dir == 0:
            # 首次事件几乎没有横向位移（比如纯竖直拖），按总位移定方向，
            # 不再固定成向右
            direction = 1 if dx >= 0 else -1
        else:
            direction = self._drag_dir
        if direction != self._drag_dir:
            self._drag_dir = direction
            # keep_phase：左右切换时接着当前帧播，避免动作从头跳一遍
            self.play("drag_right" if direction > 0 else "drag_left",
                      keep_phase=True)

        self._move(self._drag_start[2] + dx, self._drag_start[3] + dy)

    def _on_release(self, event):
        was_drag = self._drag_start is not None and self._drag_dir != 0 and \
            (abs(event.x_root - self._drag_start[0]) > 4 or
             abs(event.y_root - self._drag_start[1]) > 4)
        self._drag_start = None
        self._drag_dir = 0
        self._last_interact = self._now()
        if was_drag:
            self.back_to_idle()
        else:
            self._react("pet")

    # ---------- 互动 ----------
    def _react(self, kind):
        if kind == "pet":
            self._do_anim(random.choice(["laugh", "wave"]),
                          random.choice(PET_LINES))
        elif kind == "feed":
            self._do_anim("laugh", random.choice(FEED_LINES))
        elif kind == "greet":
            self._do_anim("wave", random.choice(GREET_LINES))

    # ---------- 系统托盘 ----------
    def _tk(self, func, *args):
        """托盘线程回调 -> 转发到 tkinter 主线程执行。"""
        self.after(0, lambda: func(*args))

    @staticmethod
    def _tray_icon_size():
        """系统托盘图标实际的边长：96 DPI 下 16，125% 缩放 20，150% 缩放 24。"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            size = user32.GetSystemMetrics(SM_CXSMICON) or 16
            # 进程没声明 DPI 感知时 GetSystemMetrics 恒返回 96 DPI 下的 16，
            # 而托盘由 explorer 按真实 DPI 渲染成 20/24，这里折算回去。
            get_dpi = getattr(user32, "GetDpiForSystem", None)
            if get_dpi and size <= 16:
                size = int(round(16 * (get_dpi() or 96) / 96.0))
            return min(max(size, 8), 64)
        except Exception:
            return 32

    def _tray_image(self):
        """按系统托盘的实际尺寸，从 ICO 里取恰好同尺寸的一帧。

        之前固定缩到 64x64 交给 Windows，Windows 再压到 16/20/24 显示，
        等于二次降采样，细节被糊掉两次。给同尺寸的帧才能 1:1 呈现。
        """
        want = self._tray_icon_size()
        try:
            from PIL import IcoImagePlugin
            with open(ICO_PATH, "rb") as fp:
                ico = IcoImagePlugin.IcoFile(fp)
                sizes = sorted(s[0] for s in ico.sizes())
                pick = min((s for s in sizes if s >= want), default=max(sizes))
                return ico.getimage((pick, pick)).convert("RGBA")
        except Exception:
            # ICO 缺失或读不出时退回 png，用 BOX 面积平均降采样保留细节
            try:
                img = Image.open(ICON_PATH).convert("RGBA")
            except Exception:
                sheet = Image.open(SHEET_PATH).convert("RGBA")
                img = self._hard_alpha(sheet.crop((0, 0, CELL_W, CELL_H)))
            return self._hard_alpha(img.resize((want, want),
                                               Image.Resampling.BOX))

    def _tray_cmd(self, fn, *args):
        """生成 pystray 要求的 (icon, item) 两参数回调。"""
        def handler(icon, item):
            self._tk(fn, *args)
        return handler

    def _tray_menu(self):
        """托盘菜单。

        左键单击触发的是 default 项，它必须跟着显隐状态变：窗口隐藏后如果
        default 还挂在「打招呼」上，点了会毫无反应，用户会以为桌宠丢了。

        这里用 self._hidden 而不是 winfo_viewable()：后者在 __init__ 里
        _setup_tray() 那一刻窗口还没映射、会返回 0，把初始菜单建成隐藏态。
        """
        size_menu = TrayMenu(*[
            TrayItem(n, self._tray_cmd(self._set_scale, s))
            for n, s in SIZES.items()
        ])
        if self._hidden:
            # 隐藏时只留「显示」和「退出」：动画类操作在看不见时没有意义
            return TrayMenu(
                TrayItem("显示", self._tray_cmd(self._show), default=True),
                TrayItem("退出", self._tray_cmd(self._quit)),
            )
        return TrayMenu(
            # default=True：左键单击托盘图标时触发，放在无害项上，避免误退出
            TrayItem("打招呼", self._tray_cmd(self._react, "greet"), default=True),
            TrayItem("隐藏", self._tray_cmd(self._hide)),
            TrayItem("看会儿书", self._tray_cmd(self._do_anim, "read", "让我看看书…")),
            TrayItem("跳个舞", self._tray_cmd(self._do_anim, "dance", "来跳舞吧♪")),
            TrayItem("喂苹果", self._tray_cmd(self._react, "feed")),
            TrayItem("打盹", self._tray_cmd(self._do_sleep)),
            TrayItem("大小", size_menu),
            TrayItem("配置自定义项", self._tray_cmd(self._open_config_dialog)),
            TrayItem("退出", self._tray_cmd(self._quit)),
        )

    def _setup_tray(self):
        if pystray is None:
            return
        self.tray = pystray.Icon(APP_NAME, self._tray_image(),
                                 DISPLAY_NAME, self._tray_menu())
        try:
            self.tray.run_detached()
        except Exception:
            pass

    def _pause_anim(self):
        """窗口看不见了就停掉帧切换，别再白烧 CPU。"""
        if self._anim_job:
            self.after_cancel(self._anim_job)
            self._anim_job = None

    def _resume_anim(self):
        """恢复显示后接着播；拖拽类动画不该被恢复，退回待机。"""
        name = self.current_anim
        if not name or name.startswith("drag"):
            name = "idle"
        self.play(name)

    def _refresh_tray(self):
        """显隐状态变了，重建托盘菜单（左键单击的 default 项跟着变）。"""
        if self.tray is None:
            return
        try:
            # Icon.menu 的 setter 内部会调用 update_menu()
            self.tray.menu = self._tray_menu()
        except Exception:
            pass

    def _show(self):
        if not self._hidden:
            return
        self._hidden = False
        self.deiconify()
        self._resume_anim()
        self._refresh_tray()

    def _hide(self):
        if self._hidden:
            return
        self._hidden = True
        self.withdraw()
        self._pause_anim()
        self._refresh_tray()

    def _toggle_visible(self):
        if self._hidden:
            self._show()
        else:
            self._hide()

    # ---------- 右键菜单 ----------
    def _rebuild_menu(self):
        """配置改过之后重建右键菜单。

        菜单是 __init__ 时一次性建好的，不重建的话新加的自定义项不生效。
        """
        if getattr(self, "menu", None) is not None:
            try:
                self.menu.destroy()
            except Exception:
                pass
        self._build_menu()

    def _build_menu(self):
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="打招呼",
                              command=lambda: self._react("greet"))
        self.menu.add_command(label="跳个舞",
                              command=lambda: self._do_anim("dance", "来跳舞吧♪"))
        self.menu.add_command(label="看会儿书",
                              command=lambda: self._do_anim("read", "让我看看书…"))
        self.menu.add_command(label="喂苹果",
                              command=lambda: self._react("feed"))
        size_menu = tk.Menu(self.menu, tearoff=0)
        for name in SIZES:
            size_menu.add_command(
                label=name, command=lambda n=name: self._set_scale(SIZES[n]))
        self.menu.add_cascade(label="大小", menu=size_menu)
        # 自定义项分两组，各自用横杠与内置功能、以及彼此隔开；
        # 一组都没配就整段不出现。空 URL/空路径的死项也要挡掉。
        url_idx = [i for i, it in enumerate(self.custom_items)
                   if (it.get("url") or "").strip()]
        if url_idx:
            self.menu.add_separator()
            for i in url_idx:
                item = self.custom_items[i]
                self.menu.add_command(
                    label=item.get("name") or item.get("url") or "未命名",
                    command=lambda i=i: self._open_custom(i))

        file_idx = [i for i, it in enumerate(self.file_items)
                    if (it.get("path") or "").strip()]
        if file_idx:
            self.menu.add_separator()
            for i in file_idx:
                item = self.file_items[i]
                self.menu.add_command(
                    label=item.get("name") or item.get("path") or "未命名",
                    command=lambda i=i: self._open_file(i))
        self.menu.add_separator()
        self.menu.add_command(label="打盹", command=self._do_sleep)
        self.menu.add_command(label="隐藏", command=self._hide)
        self.menu.add_command(label="退出", command=self._quit)

    def _open_custom(self, idx):
        """用系统默认浏览器打开第 idx 条网页跳转。"""
        if not 0 <= idx < len(self.custom_items):
            return
        url = (self.custom_items[idx].get("url") or "").strip()
        if not url:
            return
        self._last_interact = self._now()
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _open_file(self, idx):
        """用系统默认程序打开第 idx 条本地文件/文件夹。"""
        if not 0 <= idx < len(self.file_items):
            return
        path = (self.file_items[idx].get("path") or "").strip()
        if not path:
            return
        self._last_interact = self._now()
        try:
            os.startfile(path)
        except Exception:
            # 路径不存在、文件被删、没有关联程序都会走到这儿。
            # 用桌宠自己的气泡提示，不弹窗、不嵌套模态。
            self._say("打不开：%s" % path, duration=3500)

    def _open_config_dialog(self):
        """自定义项配置弹窗：网页跳转 + 本地文件，两个区都是内联编辑行。

        刻意不用「列表 + 输入框」那套：它要靠 Listbox 的选中事件在草稿和
        输入框之间来回同步，事件会重入、索引会错位。这里数据即 UI，
        直接遍历行读 Entry，中间没有任何需要同步的状态。

        所有改动都即时落盘（删除、输入框失焦、点完成），不设「保存/取消」，
        用户不会遇到「删了却没生效」这种事。
        """
        # 单例：已经开着就只是拉到前面，不再叠第二个窗（两个 grab 会打架）
        if self._config_win is not None and self._config_win.winfo_exists():
            self._config_win.lift()
            self._config_win.focus_force()
            return

        win = tk.Toplevel(self)
        win.title("配置自定义项")
        # 桌宠本身置顶，弹窗不加 topmost 会被它盖住
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.configure(bg="#fffef2")
        self._config_win = win

        outer = tk.Frame(win, bg="#fffef2", padx=12, pady=12)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="改完即生效：删除、修改都会立刻保存并更新右键菜单",
                 bg="#fffef2", fg="#4a4a3a").pack(anchor="w")

        def make_section(title, headers, height):
            """造一个区：标题 + 表头 + 可滚动行容器。

            整个区自包含在一个 Frame 里，canvas 和滚动条只在本区的子 Frame
            内左右排。早先把它们直接 pack 到外层 outer，按钮就被挤到行的
            右边去了，整页错位。
            """
            section = tk.Frame(outer, bg="#fffef2")
            section.pack(fill="x", pady=(12, 0))

            tk.Label(section, text=title, bg="#fffef2", fg="#4a4a3a",
                     font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")

            head = tk.Frame(section, bg="#fffef2")
            head.pack(fill="x", pady=(4, 2))
            for text, width in headers:
                tk.Label(head, text=text, width=width, anchor="w",
                         bg="#fffef2", fg="#4a4a3a").pack(side=tk.LEFT)

            scroll = tk.Frame(section, bg="#fffef2")
            scroll.pack(fill="x")
            # 宽度给死：窗口不可缩放，宽度由内容定，不固定 canvas 会被压扁
            canvas = tk.Canvas(scroll, bg="#fffef2", highlightthickness=0,
                               height=height, width=460)
            bar = tk.Scrollbar(scroll, command=canvas.yview, width=12)
            canvas.configure(yscrollcommand=bar.set)
            canvas.pack(side=tk.LEFT, fill="y")
            bar.pack(side=tk.RIGHT, fill="y")

            frame = tk.Frame(canvas, bg="#fffef2")
            canvas.create_window((0, 0), window=frame, anchor="nw")

            def refresh():
                canvas.configure(scrollregion=canvas.bbox("all"))

            frame.bind("<Configure>", lambda _e: refresh())

            def on_wheel(event):
                canvas.yview_scroll(int(-event.delta / 120), "units")

            def bind_wheel(w):
                w.bind("<MouseWheel>", on_wheel)
                for c in w.winfo_children():
                    bind_wheel(c)

            bind_wheel(frame)
            return frame, refresh, bind_wheel

        # ---------- 网页跳转区 ----------
        url_frame, url_refresh, url_wheel = make_section(
            "网页跳转", [("选项名称", 16), ("跳转 URL", 32)], 80)
        url_rows = []          # [(name_entry, url_entry), ...]

        def add_url_row(name="", url=""):
            row = tk.Frame(url_frame, bg="#fffef2", pady=2)
            ne = tk.Entry(row, width=16)
            ue = tk.Entry(row, width=32)
            ne.insert(0, name)
            ue.insert(0, url)

            def on_delete():
                url_rows.remove((ne, ue))
                row.destroy()
                url_refresh()
                commit()

            def on_blur(_event):
                commit()

            btn = tk.Button(row, text="删", width=4, command=on_delete)
            for e in (ne, ue):
                e.bind("<FocusOut>", on_blur)
            ne.pack(side=tk.LEFT, padx=(0, 6))
            ue.pack(side=tk.LEFT, padx=(0, 6))
            btn.pack(side=tk.LEFT)
            row.pack(fill="x")
            url_rows.append((ne, ue))
            url_wheel(row)
            url_refresh()

        tk.Button(outer, text="+ 新增网页",
                  command=lambda: add_url_row()).pack(anchor="w", pady=(4, 0))

        # ---------- 本地文件区 ----------
        file_frame, file_refresh, file_wheel = make_section(
            "本地文件", [("文件名称", 16), ("文件路径", 32)], 80)
        file_rows = []         # [(name_entry, path_entry), ...]

        def add_file_row(name="", path=""):
            row = tk.Frame(file_frame, bg="#fffef2", pady=2)
            ne = tk.Entry(row, width=16)
            pe = tk.Entry(row, width=32)
            ne.insert(0, name)
            pe.insert(0, path)

            def on_delete():
                file_rows.remove((ne, pe))
                row.destroy()
                file_refresh()
                commit()

            def on_blur(_event):
                commit()

            def on_browse():
                # 文件对话框自己会 grab，先把弹窗的 grab 放掉再开，
                # 两个 grab 叠在一起会出怪事
                try:
                    win.grab_release()
                except Exception:
                    pass
                picked = filedialog.askopenfilename(parent=win,
                                                    title="选择要打开的文件")
                try:
                    win.grab_set()
                except Exception:
                    pass
                if not picked:
                    return
                pe.delete(0, tk.END)
                pe.insert(0, picked)
                # 名称为空就用文件名（去掉扩展名）兜底
                if not ne.get().strip():
                    ne.delete(0, tk.END)
                    ne.insert(0, os.path.splitext(os.path.basename(picked))[0])
                commit()

            btn = tk.Button(row, text="删", width=4, command=on_delete)
            browse = tk.Button(row, text="浏览…", width=6, command=on_browse)
            for e in (ne, pe):
                e.bind("<FocusOut>", on_blur)
            ne.pack(side=tk.LEFT, padx=(0, 6))
            pe.pack(side=tk.LEFT, padx=(0, 6))
            browse.pack(side=tk.LEFT, padx=(0, 6))
            btn.pack(side=tk.LEFT)
            row.pack(fill="x")
            file_rows.append((ne, pe))
            file_wheel(row)
            file_refresh()

        tk.Button(outer, text="+ 新增文件",
                  command=lambda: add_file_row()).pack(anchor="w", pady=(4, 0))

        def commit():
            """把当前各行写进配置并刷新菜单（即时生效）。"""
            customs, files = [], []
            for ne, ue in list(url_rows):
                url = normalize_url(ue.get())
                if url:      # 空 URL 直接丢掉，不留点了没反应的死项
                    customs.append({"name": ne.get().strip() or url, "url": url})
            for ne, pe in list(file_rows):
                path = (pe.get() or "").strip()
                if path:     # 空路径同理
                    files.append({"name": ne.get().strip() or path,
                                  "path": path})
            save_pet_config(customs, files)
            self.custom_items = customs
            self.file_items = files
            self._rebuild_menu()
            self._refresh_tray()

        def close():
            commit()          # 关窗前把当前内容落盘，不丢没保存的修改
            self._config_win = None
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        tk.Button(outer, text="完成", width=8,
                  command=close).pack(anchor="e", pady=(14, 0))

        for it in self.custom_items:
            add_url_row(it.get("name", ""), it.get("url", ""))
        if not self.custom_items:
            add_url_row()     # 至少给一行，打开就能直接填

        for it in self.file_items:
            add_file_row(it.get("name", ""), it.get("path", ""))
        if not self.file_items:
            add_file_row()

        win.protocol("WM_DELETE_WINDOW", close)

        # 定位到桌宠附近，别飘到屏幕另一端
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x = max(0, min(self._x + (self._img_w - w) // 2, sw - w))
        y = max(0, min(self._y + (self._img_h - h) // 2, sh - h))
        win.geometry("+%d+%d" % (x, y))
        try:
            win.grab_set()
        except Exception:
            pass

    def _show_menu(self, event):
        self._last_interact = self._now()
        self.menu.tk_popup(event.x_root, event.y_root)

    def _set_scale(self, scale):
        self.scale = scale
        self._load_sheet()
        self._save()
        self.back_to_idle()

    def _quit(self):
        self._save()
        try:
            if getattr(self, "tray", None):
                self.tray.stop()
        except Exception:
            pass
        self.destroy()
        os._exit(0)     # 结束托盘后台线程，确保进程完全退出


if __name__ == "__main__":
    Pet().mainloop()
