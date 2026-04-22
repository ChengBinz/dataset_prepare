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

## License

本项目仅用于内部模型测试，所有合同内容均为虚构合成数据。