"""
将 contracts/ 中的 Markdown 合同文件渲染为分页扫描风格图片。
流程: Markdown → HTML → PDF(Playwright/Chromium) → 逐页PNG(PyMuPDF) → 扫描仿真(Pillow+numpy)
"""

import os
import random
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import markdown
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = PROJECT_ROOT / "contracts"
IMAGES_DIR = PROJECT_ROOT / "dataset" / "images"

DPI = 200  # 渲染分辨率

# HTML 模板：模拟 A4 打印合同样式
HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{
    size: A4;
    margin: 2.5cm 2cm 2.5cm 2cm;
}}
body {{
    font-family: "Songti SC", "STSong", "SimSun", "Noto Serif CJK SC", serif;
    font-size: 10.5pt;
    line-height: 1.8;
    color: #1a1a1a;
}}
h1 {{
    font-family: "Heiti SC", "STHeiti", "SimHei", "Noto Sans CJK SC", sans-serif;
    font-size: 18pt;
    text-align: center;
    margin-top: 0.5cm;
    margin-bottom: 0.8cm;
    font-weight: bold;
}}
h2, h3 {{
    font-family: "Heiti SC", "STHeiti", "SimHei", "Noto Sans CJK SC", sans-serif;
    font-size: 12pt;
    margin-top: 0.6cm;
    margin-bottom: 0.3cm;
}}
h2 {{
    font-size: 13pt;
}}
p {{
    text-indent: 0em;
    margin: 0.2cm 0;
    text-align: justify;
}}
ol, ul {{
    margin: 0.2cm 0;
    padding-left: 1.5em;
}}
li {{
    margin: 0.15cm 0;
}}
hr {{
    border: none;
    border-top: 1px solid #666;
    margin: 0.5cm 0;
}}
strong {{
    font-weight: bold;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 0.3cm 0;
}}
th, td {{
    border: 1px solid #333;
    padding: 4px 8px;
    font-size: 9.5pt;
}}
th {{
    background-color: #f0f0f0;
    font-family: "Heiti SC", "STHeiti", sans-serif;
}}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def md_to_html(md_text: str) -> str:
    """将 Markdown 转为完整的 HTML。"""
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br"],
    )
    return HTML_TEMPLATE.format(body=body)


# Playwright 浏览器实例（延迟初始化，全局复用）
_browser = None
_playwright = None


def _get_browser():
    """获取或创建全局 Playwright 浏览器实例。"""
    global _browser, _playwright
    if _browser is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=True)
    return _browser


def cleanup_browser():
    """关闭浏览器实例。"""
    global _browser, _playwright
    if _browser:
        _browser.close()
        _browser = None
    if _playwright:
        _playwright.stop()
        _playwright = None


def html_to_pdf_bytes(html_str: str) -> bytes:
    """使用 Playwright (Chromium) 将 HTML 渲染为 PDF bytes。"""
    browser = _get_browser()
    page = browser.new_page()
    page.set_content(html_str, wait_until="networkidle")
    pdf_bytes = page.pdf(
        format="A4",
        margin={"top": "2.5cm", "right": "2cm", "bottom": "2.5cm", "left": "2cm"},
        print_background=True,
    )
    page.close()
    return pdf_bytes


def pdf_to_pages(pdf_bytes: bytes, dpi: int = DPI) -> list[Image.Image]:
    """将 PDF 转为逐页 PIL Image 列表。"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        pages.append(img)
    doc.close()
    return pages


def apply_scan_effect(img: Image.Image, seed: int = None) -> Image.Image:
    """给图片添加扫描仿真效果：纸张底色、噪点、轻微旋转、边缘阴影。"""
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    arr = np.array(img, dtype=np.float32)

    # 1. 纸张底色偏暖：轻微偏黄
    paper_r = random.uniform(245, 252)
    paper_g = random.uniform(242, 248)
    paper_b = random.uniform(230, 240)
    paper = np.array([paper_r, paper_g, paper_b], dtype=np.float32)

    # 将白色背景替换为纸张色
    white_mask = (arr > 240).all(axis=2)
    arr[white_mask] = paper

    # 非白色区域也稍微偏暖
    arr[~white_mask] = arr[~white_mask] * 0.95 + paper * 0.05

    # 2. 高斯噪声
    noise = np.random.normal(0, random.uniform(2, 4), arr.shape).astype(np.float32)
    arr = np.clip(arr + noise, 0, 255)

    # 3. 轻微亮度/对比度变化
    img_out = Image.fromarray(arr.astype(np.uint8))
    brightness = ImageEnhance.Brightness(img_out)
    img_out = brightness.enhance(random.uniform(0.96, 1.0))
    contrast = ImageEnhance.Contrast(img_out)
    img_out = contrast.enhance(random.uniform(0.95, 1.02))

    # 4. 轻微模糊（模拟扫描不够锐利）
    img_out = img_out.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.3, 0.6)))

    # 5. 轻微旋转（-0.8° ~ 0.8°）
    angle = random.uniform(-0.8, 0.8)
    img_out = img_out.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(int(paper_r), int(paper_g), int(paper_b)))

    # 6. 边缘渐暗（模拟扫描仪边缘阴影）
    w, h = img_out.size
    shadow = Image.new("L", (w, h), 255)
    shadow_arr = np.array(shadow, dtype=np.float32)
    # 四边渐暗
    margin = int(min(w, h) * 0.03)
    for i in range(margin):
        factor = (i / margin) ** 0.5
        val = int(235 + 20 * factor)
        shadow_arr[i, :] = np.minimum(shadow_arr[i, :], val)
        shadow_arr[h - 1 - i, :] = np.minimum(shadow_arr[h - 1 - i, :], val)
        shadow_arr[:, i] = np.minimum(shadow_arr[:, i], val)
        shadow_arr[:, w - 1 - i] = np.minimum(shadow_arr[:, w - 1 - i], val)

    shadow = Image.fromarray(shadow_arr.astype(np.uint8))
    result_arr = np.array(img_out, dtype=np.float32)
    shadow_factor = np.array(shadow, dtype=np.float32)[:, :, np.newaxis] / 255.0
    result_arr = result_arr * shadow_factor
    img_out = Image.fromarray(np.clip(result_arr, 0, 255).astype(np.uint8))

    return img_out


def process_contract(md_path: Path, force: bool = False) -> list[str]:
    """处理单份合同：Markdown → 分页扫描图片。返回生成的图片相对路径列表。"""
    contract_id = md_path.stem  # e.g., "DS-L1-01"
    level = md_path.parent.name  # e.g., "L1"

    # 检查是否已生成
    existing = sorted(IMAGES_DIR.glob(f"{contract_id}_p*.png"))
    if existing and not force:
        return [str(p.relative_to(PROJECT_ROOT / "dataset")) for p in existing]

    md_text = md_path.read_text(encoding="utf-8")

    # Markdown → HTML → PDF → Pages
    html_str = md_to_html(md_text)
    pdf_bytes = html_to_pdf_bytes(html_str)
    pages = pdf_to_pages(pdf_bytes)

    # 每页添加扫描效果并保存
    image_paths = []
    for i, page_img in enumerate(pages, 1):
        scanned = apply_scan_effect(page_img, seed=hash(f"{contract_id}_p{i}") % (2**31))
        filename = f"{contract_id}_p{i}.png"
        out_path = IMAGES_DIR / filename
        scanned.save(out_path, "PNG", optimize=True)
        image_paths.append(f"images/{filename}")

    return image_paths


def main():
    print("=" * 60)
    print("合同图片渲染工具")
    print("=" * 60)

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # 收集所有合同文件
    md_files = sorted(CONTRACTS_DIR.glob("L*/*.md"))
    print(f"\n找到 {len(md_files)} 份合同文件")

    total_images = 0
    results = {}

    for idx, md_path in enumerate(md_files, 1):
        cid = md_path.stem
        print(f"\n  [{idx}/{len(md_files)}] {cid}...", end=" ", flush=True)

        try:
            paths = process_contract(md_path)
            results[cid] = paths
            total_images += len(paths)
            print(f"✓ {len(paths)} 页")
        except Exception as e:
            print(f"✗ {e}")
            results[cid] = []

    print(f"\n{'=' * 60}")
    print(f"完成: 共生成 {total_images} 张图片")
    print(f"{'=' * 60}")

    # 统计
    for level in ["L1", "L2", "L3"]:
        level_ids = [k for k in results if k.startswith(f"DS-{level}")]
        pages = sum(len(results[k]) for k in level_ids)
        avg = pages / len(level_ids) if level_ids else 0
        print(f"  {level}: {len(level_ids)} 份合同, 共 {pages} 页, 平均 {avg:.1f} 页/份")

    cleanup_browser()


if __name__ == "__main__":
    main()
