"""
组装最终数据集：生成 dataset/dataset.jsonl 和 dataset/README.md。

每条 JSONL 记录包含：
  - id: 合同编号
  - level: 难度级别 (L1/L2/L3)
  - document_text: Markdown 合同全文
  - images: 该合同对应的分页扫描图片路径列表
  - expected_result: 预期识别结果 JSON (18个字段)
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = PROJECT_ROOT / "contracts"
IMAGES_DIR = PROJECT_ROOT / "dataset" / "images"
META_DIR = PROJECT_ROOT / "meta"
DATASET_DIR = PROJECT_ROOT / "dataset"


def build_jsonl():
    """扫描所有合同，组装 dataset.jsonl。"""
    records = []

    for level in ["L1", "L2", "L3"]:
        level_dir = CONTRACTS_DIR / level
        if not level_dir.exists():
            continue

        for md_path in sorted(level_dir.glob("*.md")):
            cid = md_path.stem  # e.g., DS-L1-01

            # 读取 Markdown 全文
            md_text = md_path.read_text(encoding="utf-8")

            # 读取 meta JSON
            json_path = META_DIR / f"{cid}.json"
            if not json_path.exists():
                print(f"  [WARN] {cid}: meta JSON 不存在，跳过")
                continue
            expected_result = json.loads(json_path.read_text(encoding="utf-8"))

            # 收集图片路径（相对于 dataset/ 目录）
            image_files = sorted(IMAGES_DIR.glob(f"{cid}_p*.png"))
            if not image_files:
                print(f"  [WARN] {cid}: 无图片文件，跳过")
                continue
            image_paths = [f"images/{p.name}" for p in image_files]

            record = {
                "id": cid,
                "level": level,
                "document_text": md_text,
                "images": image_paths,
                "page_count": len(image_paths),
                "expected_result": expected_result,
            }
            records.append(record)

    return records


def write_jsonl(records: list[dict]):
    """写入 dataset.jsonl。"""
    out_path = DATASET_DIR / "dataset.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out_path


def write_readme(records: list[dict]):
    """生成 dataset/README.md。"""
    total = len(records)
    total_pages = sum(r["page_count"] for r in records)

    level_stats = {}
    for r in records:
        lv = r["level"]
        if lv not in level_stats:
            level_stats[lv] = {"count": 0, "pages": 0}
        level_stats[lv]["count"] += 1
        level_stats[lv]["pages"] += r["page_count"]

    fields = [
        "合同签订主体", "合同名称", "客户名称", "合同含税金额", "合同不含税金额",
        "税率", "开票类型", "合同交付标的", "履约条款（交付验收节点）", "确收材料",
        "结算回款条款", "项目发生地", "交付周期", "质保金", "质保期",
        "是否涉及农民工代付", "是否涉及垫付", "合同开始时间", "合同截止时间",
    ]

    readme = f"""# 合同文档识别测试数据集

## 概述

本数据集用于测试多模态文档识别模型对中文商业合同的结构化信息提取能力。每条数据包含：

- **文档文本**：完整的 Markdown 格式合同原文
- **文档图片**：模拟扫描件效果的分页 PNG 图片
- **识别结果**：标准化的 JSON 格式预期识别结果（18个字段）

## 数据规模

| 指标 | 数值 |
|------|------|
| 合同总数 | {total} |
| 图片总数 | {total_pages} |
"""

    for lv in ["L1", "L2", "L3"]:
        if lv in level_stats:
            s = level_stats[lv]
            avg = s["pages"] / s["count"] if s["count"] else 0
            readme += f"| {lv} 级别 | {s['count']} 份, {s['pages']} 页 (平均 {avg:.1f} 页/份) |\n"

    readme += f"""
## 难度级别说明

| 级别 | 说明 |
|------|------|
| L1 | 简单合同：双方主体、条款清晰、篇幅较短（1-4页） |
| L2 | 中等合同：行业专业术语、多阶段付款、较多条款（3-7页） |
| L3 | 复杂合同：多方主体、复杂验收流程、长篇幅（5-10+页） |

## 识别字段（18个）

| 序号 | 字段名 |
|------|--------|
"""
    for i, f in enumerate(fields, 1):
        readme += f"| {i} | {f} |\n"

    readme += """
## 文件结构

```
dataset/
├── dataset.jsonl          # 数据集主文件
├── README.md              # 本说明文件
└── images/                # 扫描风格合同图片
    ├── DS-L1-01_p1.png    # 合同编号_页码.png
    ├── DS-L1-01_p2.png
    └── ...
```

## JSONL 格式

每行一条 JSON 记录，字段如下：

```json
{
  "id": "DS-L1-01",
  "level": "L1",
  "document_text": "# 软件系统技术服务合同\\n\\n合同编号：...",
  "images": ["images/DS-L1-01_p1.png", "images/DS-L1-01_p2.png", ...],
  "page_count": 3,
  "expected_result": {
    "合同签订主体": "甲方：xxx；乙方：xxx",
    "合同名称": "...",
    ...
  }
}
```

## 使用方式

```python
import json

with open("dataset/dataset.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        record = json.loads(line)
        print(record["id"], record["level"], record["page_count"])
        # record["images"] -> 图片路径列表
        # record["expected_result"] -> 预期识别结果
        # record["document_text"] -> Markdown 合同原文
```
"""

    out_path = DATASET_DIR / "README.md"
    out_path.write_text(readme.strip() + "\n", encoding="utf-8")
    return out_path


def main():
    print("=" * 60)
    print("数据集组装工具")
    print("=" * 60)

    records = build_jsonl()
    print(f"\n共组装 {len(records)} 条记录")

    for lv in ["L1", "L2", "L3"]:
        lv_records = [r for r in records if r["level"] == lv]
        pages = sum(r["page_count"] for r in lv_records)
        print(f"  {lv}: {len(lv_records)} 份, {pages} 页")

    jsonl_path = write_jsonl(records)
    print(f"\n✓ 已生成 {jsonl_path}")

    readme_path = write_readme(records)
    print(f"✓ 已生成 {readme_path}")

    # 验证 JSONL 可读性
    print("\n验证 JSONL...")
    with open(jsonl_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    print(f"  共 {len(lines)} 行")
    for i, line in enumerate(lines):
        r = json.loads(line)
        assert "id" in r and "images" in r and "expected_result" in r
    print("  ✓ 所有记录格式正确")

    print(f"\n{'=' * 60}")
    print("数据集组装完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
