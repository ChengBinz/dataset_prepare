# 合同文档识别测试数据集构建工具

构建用于测试多模态文档识别模型的中文商业合同数据集。每条数据包含三个属性：**文档文本（Markdown）**、**文档图片（模拟扫描件）**、**预期识别结果（JSON，18个字段）**。

## 数据集概览

| 指标 | 数值 |
|------|------|
| 合同总数 | 31 份 |
| 图片总数 | 167 张 |
| L1（简单） | 11 份，37 页，平均 3.4 页/份 |
| L2（中等） | 10 份，55 页，平均 5.5 页/份 |
| L3（复杂） | 10 份，75 页，平均 7.5 页/份 |

### 难度级别

- **L1** — 双方主体、条款清晰、篇幅较短（1-4页）
- **L2** — 行业专业术语、多阶段付款、较多条款（3-7页）
- **L3** — 多方主体、复杂验收流程、长篇幅（5-10+页）

### 识别字段（18个）

合同签订主体、合同名称、客户名称、合同含税金额、合同不含税金额、税率、开票类型、合同交付标的、履约条款（交付验收节点）、确收材料、结算回款条款、项目发生地、交付周期、质保金、质保期、是否涉及农民工代付、是否涉及垫付、合同开始时间、合同截止时间

## 项目结构

```
dataset_prepare/
├── contracts/                # Markdown 合同全文
│   ├── L1/                   #   简单级别 (11份)
│   ├── L2/                   #   中等级别 (10份)
│   └── L3/                   #   复杂级别 (10份)
├── meta/                     # 每份合同的预期识别结果 JSON
├── dataset/
│   ├── dataset.jsonl         # 最终数据集（文本+图片路径+预期结果）
│   ├── README.md             # 数据集说明
│   └── images/               # 扫描风格合同图片（需本地生成，未纳入 Git）
├── scripts/
│   ├── generate_contracts.py     # TSV → LLM → Markdown 合同全文
│   ├── generate_new_contracts.py # 批量生成新合同数据（扩充用）
│   ├── render_images.py          # Markdown → 分页扫描风格图片
│   └── build_dataset.py          # 组装 dataset.jsonl 和 README
├── 合同模型测试数据集.tsv          # 原始数据源
└── 合同模型测试数据集.xlsx         # 原始数据源（Excel）
```

## 快速开始

### 环境准备

```bash
# 安装依赖
uv sync

# 安装 Playwright 浏览器（用于图片渲染）
uv run playwright install chromium
```

### 配置 LLM API（仅生成/扩充合同文本时需要）

创建 `.env` 文件：

```env
LLM_BASE_URL=https://your-api-base-url
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-name
```

### 生成图片

图片未纳入 Git 管理（约 1GB），克隆后需本地生成：

```bash
uv run python scripts/render_images.py
```

### 重新组装数据集

```bash
uv run python scripts/build_dataset.py
```

## 使用数据集

```python
import json

with open("dataset/dataset.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        record = json.loads(line)
        print(record["id"], record["level"], record["page_count"])
        # record["document_text"]    → Markdown 合同原文
        # record["images"]           → 图片路径列表
        # record["expected_result"]  → 预期识别结果 (18个字段)
```

## 工作流程

```
原始 TSV 数据
    ↓  scripts/generate_contracts.py (LLM 扩写)
Markdown 合同全文 (contracts/)
    ↓  scripts/render_images.py (Playwright + PyMuPDF + 扫描仿真)
分页扫描风格图片 (dataset/images/)
    ↓  scripts/build_dataset.py
dataset.jsonl (最终数据集)
```

## 模型测试流程

### 1. 准备测试环境

```bash
# 克隆项目并安装依赖
git clone git@github.com:ChengBinz/dataset_prepare.git
cd dataset_prepare
uv sync
uv run playwright install chromium

# 生成扫描风格图片（约 1GB，首次需执行）
uv run python scripts/render_images.py
```

### 2. 加载数据集

```python
import json
from pathlib import Path

dataset = []
with open("dataset/dataset.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        dataset.append(json.loads(line))

print(f"共 {len(dataset)} 条测试数据")
```

### 3. 调用模型进行推理

将每条数据的扫描图片输入本地部署的多模态模型，获取结构化识别结果：

```python
from PIL import Image

for record in dataset:
    # 加载该合同的所有分页扫描图片
    images = [Image.open(f"dataset/{p}") for p in record["images"]]

    # 构造 prompt，要求模型提取 18 个合同字段
    prompt = """请从以下合同扫描件中提取结构化信息，以 JSON 格式返回，包含以下字段：
    合同签订主体、合同名称、客户名称、合同含税金额、合同不含税金额、
    税率、开票类型、合同交付标的、履约条款（交付验收节点）、确收材料、
    结算回款条款、项目发生地、交付周期、质保金、质保期、
    是否涉及农民工代付、是否涉及垫付、合同开始时间、合同截止时间"""

    # 调用本地模型（以 OpenAI 兼容接口为例）
    # model_output = call_your_model(images=images, prompt=prompt)

    # 解析模型输出
    # predicted = json.loads(model_output)
```

### 4. 评估识别准确率

将模型输出与预期结果逐字段对比，计算各字段及整体准确率：

```python
FIELDS = [
    "合同签订主体", "合同名称", "客户名称", "合同含税金额", "合同不含税金额",
    "税率", "开票类型", "合同交付标的", "履约条款（交付验收节点）", "确收材料",
    "结算回款条款", "项目发生地", "交付周期", "质保金", "质保期",
    "是否涉及农民工代付", "是否涉及垫付", "合同开始时间", "合同截止时间",
]

def evaluate(dataset, predictions):
    """
    dataset: list[dict]  — dataset.jsonl 中的记录
    predictions: dict[str, dict] — {合同ID: 模型预测JSON}
    """
    field_correct = {f: 0 for f in FIELDS}
    field_total = {f: 0 for f in FIELDS}
    level_stats = {}

    for record in dataset:
        cid = record["id"]
        level = record["level"]
        expected = record["expected_result"]
        predicted = predictions.get(cid, {})

        if level not in level_stats:
            level_stats[level] = {"correct": 0, "total": 0}

        for field in FIELDS:
            expected_val = str(expected.get(field, "")).strip()
            predicted_val = str(predicted.get(field, "")).strip()
            field_total[field] += 1
            level_stats[level]["total"] += 1

            if expected_val == predicted_val:
                field_correct[field] += 1
                level_stats[level]["correct"] += 1

    # 输出逐字段准确率
    print("=" * 50)
    print("字段级准确率")
    print("=" * 50)
    for f in FIELDS:
        acc = field_correct[f] / field_total[f] * 100 if field_total[f] else 0
        print(f"  {f}: {acc:.1f}% ({field_correct[f]}/{field_total[f]})")

    # 输出各级别准确率
    print("\n级别准确率")
    for lv in ["L1", "L2", "L3"]:
        if lv in level_stats:
            s = level_stats[lv]
            acc = s["correct"] / s["total"] * 100 if s["total"] else 0
            print(f"  {lv}: {acc:.1f}%")

    # 整体准确率
    total_correct = sum(field_correct.values())
    total_all = sum(field_total.values())
    print(f"\n整体准确率: {total_correct / total_all * 100:.1f}%")
```

### 5. 生成测试报告

```python
import csv
from datetime import datetime

def export_report(dataset, predictions, output_path="test_report.csv"):
    """导出逐条对比的详细测试报告。"""
    rows = []
    for record in dataset:
        cid = record["id"]
        expected = record["expected_result"]
        predicted = predictions.get(cid, {})
        for field in FIELDS:
            exp_val = str(expected.get(field, ""))
            pred_val = str(predicted.get(field, ""))
            rows.append({
                "合同ID": cid,
                "级别": record["level"],
                "字段": field,
                "预期值": exp_val,
                "模型输出": pred_val,
                "是否正确": "✓" if exp_val.strip() == pred_val.strip() else "✗",
            })

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"测试报告已导出: {output_path}")
```

### 测试流程总览

```
dataset.jsonl + dataset/images/
    ↓  加载数据集
逐条读取合同图片
    ↓  调用本地多模态模型
模型输出结构化 JSON
    ↓  与 expected_result 逐字段对比
生成准确率统计 + 详细测试报告 (CSV)
```

## 相关文档

- [`docs/prompts.md`](docs/prompts.md) — 项目中所有 LLM 提示词的完整汇总

## License

本项目仅用于内部模型测试，所有合同内容均为虚构合成数据。