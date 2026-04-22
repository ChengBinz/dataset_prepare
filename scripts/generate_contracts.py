"""
批量调用 LLM 将简略合同原文扩展为完整、真实的合同 Markdown 文档。
读取 TSV 中的合成数据部分，逐条调用 LLM 生成完整合同，保存到 contracts/ 目录。
"""

import csv
import json
import os
import re
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("LLM_BASE_URL", "https://api.ikuncode.cc")
API_KEY = os.getenv("LLM_API_KEY")
MODEL = os.getenv("LLM_MODEL", "gemini-3-pro-preview")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TSV_PATH = PROJECT_ROOT / "合同模型测试数据集.tsv"
CONTRACTS_DIR = PROJECT_ROOT / "contracts"

# 已手写的示例合同，作为 few-shot 参考
EXAMPLE_CONTRACT = (CONTRACTS_DIR / "L1" / "DS-L1-01.md").read_text(encoding="utf-8")

SYSTEM_PROMPT = """\
你是一位资深法务文书专家，擅长撰写各类中国商业合同。你的任务是将一份简略的合同摘要扩展为一份完整、真实、可直接使用的合同全文（Markdown 格式）。

## 要求

1. **完整性**：合同必须包含完整的条款结构，包括但不限于：合同主体信息（含虚构的统一社会信用代码、法定代表人、地址）、合同标的、金额与税务、交付与验收、结算回款、双方权利义务、保密条款、违约责任、争议解决、附则、签署栏等。
2. **信息一致性**：生成的合同全文必须包含"预期识别结果JSON"中的所有关键信息（合同金额、税率、日期、主体名称等），且数值和文字必须完全一致，不得篡改。
3. **真实感**：合同应具备真实商业合同的语言风格、法律术语和格式规范。根据行业特点添加合理的行业特定条款。
4. **篇幅控制**：
   - L1 级别（简单合同）：约 800-1200 字，适合渲染为 1-2 页
   - L2 级别（中等复杂度）：约 1500-2500 字，适合渲染为 2-4 页
   - L3 级别（复杂合同）：约 3000-5000 字，适合渲染为 5-10 页
5. **格式要求**：使用 Markdown 格式，用 `#` 作为标题，`**粗体**` 强调关键信息，有序/无序列表组织条款。
6. **不要**出现"[... 省略 ...]"之类的占位符，所有内容必须是完整的。

## 参考示例

以下是一份 L1 级别合同的完整示例，供你参考风格和结构：

```markdown
{example}
```
"""

USER_PROMPT_TEMPLATE = """\
请将以下合同摘要扩展为完整的合同文档。

## 合同编号
{contract_id}

## 难度级别
{level}（{level_desc}）

## 合同简略原文
```
{brief_text}
```

## 预期识别结果（合同必须包含这些信息）
```json
{expected_json}
```

请直接输出完整的合同 Markdown 文本，不要输出其他解释性内容。
"""

LEVEL_DESC = {
    "L1": "简单单页合同，约 800-1200 字",
    "L2": "中等复杂度多页合同，约 1500-2500 字，需包含更多条款细节",
    "L3": "复杂多方长合同，约 3000-5000 字，需包含完整的行业特定条款、合规要求等",
}


def parse_tsv() -> list[dict]:
    """解析 TSV 文件，提取合成数据部分的合同信息。"""
    contracts = []

    with open(TSV_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 找到合成数据集的起始位置，跳过标记行和表头行
    synth_start = content.find("下面是合成数据集")
    if synth_start == -1:
        raise ValueError("未找到合成数据集标记")

    synth_content = content[synth_start:]
    lines = synth_content.split("\n")
    # 跳过 "下面是合成数据集" 行和 "测试集编号\t..." 表头行
    data_text = "\n".join(lines[2:])

    # 使用 csv.reader 正确处理 TSV 的多行引号字段
    import io
    reader = csv.reader(io.StringIO(data_text), delimiter="\t", quotechar='"')

    for row in reader:
        if not row or not row[0].strip():
            continue

        # 第一列：测试集编号
        raw_id = row[0].strip()
        if not re.match(r"DS-L\d+-\d+", raw_id):
            continue

        # 第二列：合同原文 Markdown
        brief_text = row[1].strip() if len(row) > 1 else ""
        if not brief_text:
            continue

        # 第三列：预期识别结果 JSON
        json_str = row[2].strip() if len(row) > 2 else ""
        if not json_str:
            continue

        try:
            expected_json = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"  [WARN] {raw_id}: JSON 解析失败 ({e})，跳过")
            continue

        # 提取级别和清理 ID
        level_match = re.match(r"DS-(L\d+)-(\d+)", raw_id)
        level = level_match.group(1) if level_match else "L1"
        clean_id = re.match(r"(DS-L\d+-\d+)", raw_id).group(1)

        contracts.append(
            {
                "id": clean_id,
                "level": level,
                "brief_text": brief_text,
                "expected_json": expected_json,
            }
        )

    return contracts


def call_llm(contract: dict) -> str:
    """调用 LLM 生成完整合同文本。"""
    system_msg = SYSTEM_PROMPT.format(example=EXAMPLE_CONTRACT)
    user_msg = USER_PROMPT_TEMPLATE.format(
        contract_id=contract["id"],
        level=contract["level"],
        level_desc=LEVEL_DESC.get(contract["level"], ""),
        brief_text=contract["brief_text"],
        expected_json=json.dumps(contract["expected_json"], ensure_ascii=False, indent=2),
    )

    url = f"{BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
        "max_tokens": 8192,
    }

    resp = httpx.post(url, json=payload, headers=headers, timeout=300)
    resp.raise_for_status()
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    # 去掉可能的 markdown 代码块包裹
    content = re.sub(r"^```(?:markdown)?\s*\n", "", content)
    content = re.sub(r"\n```\s*$", "", content)
    return content.strip()


def main():
    print("=" * 60)
    print("合同文本批量生成工具")
    print("=" * 60)

    # 1. 解析 TSV
    print("\n[1/3] 解析 TSV 文件...")
    contracts = parse_tsv()
    print(f"  共解析到 {len(contracts)} 条合成数据")
    for c in contracts:
        print(f"    {c['id']} ({c['level']}): {c['expected_json'].get('合同名称', 'N/A')[:30]}")

    # 2. 检查已存在的文件，跳过已生成的
    to_generate = []
    for c in contracts:
        out_path = CONTRACTS_DIR / c["level"] / f"{c['id']}.md"
        if out_path.exists():
            existing = out_path.read_text(encoding="utf-8")
            # 如果文件内容足够长（>500字），认为已经完成
            if len(existing) > 500:
                print(f"  [SKIP] {c['id']}: 已存在完整文件")
                continue
        to_generate.append(c)

    if not to_generate:
        print("\n所有合同文件已存在，无需生成。")
        return

    print(f"\n[2/3] 需要生成 {len(to_generate)} 份合同...")

    # 3. 逐条调用 LLM
    success_count = 0
    fail_count = 0

    for idx, contract in enumerate(to_generate, 1):
        cid = contract["id"]
        level = contract["level"]
        out_path = CONTRACTS_DIR / level / f"{cid}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"\n  [{idx}/{len(to_generate)}] 生成 {cid} ({level})...")
        print(f"    合同名称: {contract['expected_json'].get('合同名称', 'N/A')}")

        try:
            result = call_llm(contract)
            out_path.write_text(result, encoding="utf-8")
            print(f"    ✓ 完成，共 {len(result)} 字 -> {out_path.relative_to(PROJECT_ROOT)}")
            success_count += 1
        except Exception as e:
            print(f"    ✗ 失败: {e}")
            fail_count += 1

        # 速率限制：间隔 2 秒
        if idx < len(to_generate):
            time.sleep(2)

    # 4. 汇总
    print("\n" + "=" * 60)
    print(f"[3/3] 生成完毕: 成功 {success_count}, 失败 {fail_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
