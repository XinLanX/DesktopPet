# -*- coding: utf-8 -*-
"""从 spritesheet.webp 的人物像素形象生成两套应用图标。

两套的用途不同，取材目前一致（都是头部特写），将来想区分只改 crop 即可：
  - 托盘 icon.ico：格子只有 16~24px。
  - 桌面 app.ico：主要显示 48~256px。

为什么不取半身/全身：这个角色的最宽处（92px）在裙摆 y160+，上半身只有 83px 宽，
取半身补成方块要左右留白（占 90%），全身更是只占 45%；头部特写能到 94~100%，
是这个角色塞进方块图标的理论上限。

要点：
1. 裁剪后按 alpha 包围盒裁紧，再 NEAREST 放大「填满」128x128 画布。
   不留白的原因：画布留白会让角色在格子里（托盘）/ 方框里（桌面）显得更小。
2. 放大用 NEAREST，保住像素画的硬边色块。
3. 缩小用 BOX 面积平均。NEAREST 从 128 直接降到 16 是 8:1 抽样，每 8 行取 1 行，
   眼睛/发饰这类细窄像素很可能整行被跳过而直接消失。
4. BOX 前要按 alpha 预乘 RGB：透明区的 RGB 是纯黑，直接面积平均会在边缘糊出一圈
   暗边；预乘后透明像素的颜色权重为 0，降完再除回来即可。
5. 保存 ICO 时基准图取最大尺寸帧，否则 Pillow 会丢弃比基准大的尺寸
   （Pillow 只会保留 <= 基准图宽度的尺寸，基准图给小了就只剩一张 16x16）
"""
import os

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET_PATH = os.path.join(ROOT, "assets", "spritesheet.webp")
ASSET_DIR = os.path.join(ROOT, "assets")

CELL_W, CELL_H = 192, 208
CANVAS = 128                       # 画布边长（2 的倍数，方便整数倍缩放）
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
ALPHA_THRESHOLD = 140

# crop 取自精灵单元 (192x208) 的第一帧；png 为 None 表示不额外导出
ICONS = [
    {
        "name": "托盘 icon.ico",
        "crop": (48, 2, 134, 88),      # 头部 x48~134, y2~88
        "ico": "icon.ico",
        "png": "icon.png",             # 运行时托盘取不到 ICO 时的兜底
    },
    {
        "name": "桌面 app.ico",
        "crop": (48, 2, 134, 88),      # 与托盘同源
        "ico": "app.ico",
        "png": None,
    },
]

try:
    BOX = Image.Resampling.BOX
except AttributeError:      # Pillow < 9.1
    BOX = Image.BOX


def hard_alpha(img, threshold=ALPHA_THRESHOLD):
    """alpha 二值化：消除半透明边缘与抠色底色混出的杂色描边。"""
    r, g, b, a = img.split()
    a = a.point(lambda v: 255 if v >= threshold else 0)
    return Image.merge("RGBA", (r, g, b, a))


def _premul(img):
    """RGB 预乘 alpha，让透明像素在面积平均里的权重为 0。"""
    a = img.getchannel("A")
    ch = [ImageChops.multiply(c, a) for c in img.convert("RGB").split()]
    return Image.merge("RGBA", (*ch, a))


def _unmul(img):
    """_premul 的逆运算：把颜色除回原来的强度。

    逐像素算很够用——进来的都是 64px 以内的小图，最多几千个像素。
    """
    # Pillow 14 起 getdata 换成 get_flattened_data，两种都兼容
    pixels = (img.get_flattened_data() if hasattr(img, "get_flattened_data")
              else img.getdata())
    out = []
    for r, g, b, a in pixels:
        if a > 0:
            r, g, b = (min(255, r * 255 // a), min(255, g * 255 // a),
                       min(255, b * 255 // a))
        out.append((r, g, b, a))
    res = Image.new("RGBA", img.size)
    res.putdata(out)
    return res


def tight_square(img):
    """按 alpha 包围盒裁掉四周透明边，再补成正方形（居中），方便填满画布。"""
    bb = img.split()[3].getbbox()
    if bb:
        img = img.crop(bb)
    w, h = img.size
    if w == h:
        return img
    side = max(w, h)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
    return canvas


def make_frame(art, canvas, size):
    """生成 ICO 的单个尺寸帧。art 是裁紧的原图，canvas 是填满后的画布。"""
    if size >= canvas.width:
        # 放大：128 -> 256 是整数倍，NEAREST 保住像素画的硬边色块
        return canvas.resize((size, size), Image.NEAREST)
    # 缩小：直接从裁紧的原图 BOX 降采样，避免「非整数放大到 128 再缩小」的二次劣化
    return hard_alpha(_unmul(_premul(art).resize((size, size), BOX)))


def build(sheet, spec):
    """按一套取材参数生成 ICO（可选再导出一张 png）。"""
    art = tight_square(hard_alpha(sheet.crop(spec["crop"])))

    # 填满整张画布：任何留白都会让角色在显示格里显得更小
    canvas = art.resize((CANVAS, CANVAS), Image.NEAREST)

    if spec["png"]:
        canvas.save(os.path.join(ASSET_DIR, spec["png"]))

    frames = {s: make_frame(art, canvas, s) for s in ICO_SIZES}
    path = os.path.join(ASSET_DIR, spec["ico"])
    biggest = frames[max(ICO_SIZES)]
    others = [frames[s] for s in ICO_SIZES if s != max(ICO_SIZES)]
    biggest.save(path, sizes=[(s, s) for s in ICO_SIZES],
                 append_images=others)

    print("%s  裁紧 %dx%d" % (spec["name"], art.width, art.height))
    print("  ico sizes:", sorted(Image.open(path).info["sizes"]))
    for s in ICO_SIZES:
        bb = frames[s].split()[3].getbbox()
        print("   %3dpx  bbox %-18s 占方框 %.0f%%"
              % (s, str(bb), (bb[2] - bb[0]) / s * 100))


def main():
    sheet = Image.open(SHEET_PATH).convert("RGBA")
    for spec in ICONS:
        build(sheet, spec)


if __name__ == "__main__":
    main()
