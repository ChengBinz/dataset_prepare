"""
批量调用 LLM 生成新的合成合同数据（Markdown 原文 + 预期识别结果 JSON）。
扩充数据集从30条到约50条。
"""

import json
import os
import re
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("LLM_BASE_URL")
API_KEY = os.getenv("LLM_API_KEY")
MODEL = os.getenv("LLM_MODEL")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = PROJECT_ROOT / "contracts"
META_DIR = PROJECT_ROOT / "meta"  # 存放预期识别结果 JSON

# 18个识别字段
JSON_FIELDS = [
    "合同签订主体", "合同名称", "客户名称", "合同含税金额", "合同不含税金额",
    "税率", "开票类型", "合同交付标的", "履约条款（交付验收节点）", "确收材料",
    "结算回款条款", "项目发生地", "交付周期", "质保金", "质保期",
    "是否涉及农民工代付", "是否涉及垫付", "合同开始时间", "合同截止时间",
]

# 新合同的场景清单，按级别分组
NEW_CONTRACTS = {
    "L1": [
        {"id": "DS-L1-11", "hint": "SaaS 云平台年度订阅服务合同，互联网行业"},
        {"id": "DS-L1-12", "hint": "企业内训课程采购合同，教育培训行业"},
        {"id": "DS-L1-13", "hint": "UI/UX 设计外包服务合同，移动端 App 设计"},
        {"id": "DS-L1-14", "hint": "商标注册代理服务合同，知识产权服务"},
        {"id": "DS-L1-15", "hint": "办公设备租赁合同，打印机与复印机"},
        {"id": "DS-L1-16", "hint": "网络安全渗透测试服务合同，信息安全行业"},
        {"id": "DS-L1-17", "hint": "短视频拍摄制作服务合同，新媒体营销"},
    ],
    "L2": [
        {"id": "DS-L2-11", "hint": "智慧园区安防监控系统集成合同，含摄像头和AI分析平台"},
        {"id": "DS-L2-12", "hint": "ERP系统实施与数据迁移服务合同，制造业企业"},
        {"id": "DS-L2-13", "hint": "光伏发电设备采购与安装合同，新能源行业"},
        {"id": "DS-L2-14", "hint": "医院信息化HIS系统运维合同，医疗行业"},
        {"id": "DS-L2-15", "hint": "冷链物流温控系统维保合同，食品冷链行业"},
        {"id": "DS-L2-16", "hint": "无人机航拍测绘服务合同，国土规划行业"},
        {"id": "DS-L2-17", "hint": "工业机器人安装调试与培训合同，汽车制造业"},
    ],
    "L3": [
        {"id": "DS-L3-11", "hint": "智慧矿山综合监控与自动化改造EPC总承包合同，矿业，三方"},
        {"id": "DS-L3-12", "hint": "跨境电商平台技术开发与运营服务合同，涉及多币种结算与海外仓"},
        {"id": "DS-L3-13", "hint": "城市轨道交通信号系统升级改造合同，涉及夜间施工与安全认证"},
        {"id": "DS-L3-14", "hint": "大型数据中心新建工程设计施工一体化合同，含土建与机电"},
        {"id": "DS-L3-15", "hint": "省级政务云平台建设与运营服务合同，含数据安全与等保三级"},
        {"id": "DS-L3-16", "hint": "海上风电场运维与船舶租赁综合服务合同，涉及农民工代付"},
    ],
}

EXAMPLE_CONTRACT_PATH = CONTRACTS_DIR / "L1" / "DS-L1-01.md"
EXAMPLE_JSON_PATH = PROJECT_ROOT / "meta" / "DS-L1-01.json"

SYSTEM_PROMPT = """\
你是一位资深法务文书专家。你需要同时生成两样东西：
1. 一份完整、真实的中文商业合同（Markdown 格式）
2. 该合同的结构化识别结果（JSON 格式，包含18个固定字段）

## 合同文本要求
- 包含完整条款：主体信息（含虚构社会信用代码、法定代表人、地址）、合同标的、金额税务、交付验收、结算回款、权利义务、保密、违约责任、争议解决、附则、签署栏
- 具备真实商业合同的语言风格和法律术语
- 篇幅要求：
  - L1: 约 800-1500 字（1-2页）
  - L2: 约 2000-3500 字（3-5页）
  - L3: 约 4000-7000 字（6-10页）

## JSON 识别结果要求
18个字段如下，每个字段必须从合同文本中可以找到对应内容：
- 合同签订主体: 格式 "甲方：xxx；乙方：xxx"（如有丙方也列出）
- 合同名称: 合同标题
- 客户名称: 甲方/发包方名称
- 合同含税金额: 数字字符串如 "106000.00"
- 合同不含税金额: 数字字符串
- 税率: 如 "6%"、"13%"、"9%"
- 开票类型: "增值税专用发票" 或 "增值税普通发票"
- 合同交付标的: 简要描述交付内容
- 履约条款（交付验收节点）: 关键验收节点描述
- 确收材料: 验收确认所需文件名
- 结算回款条款: 付款方式与节点描述
- 项目发生地: 具体地点
- 交付周期: 格式 "YYYY-MM-DD 至 YYYY-MM-DD"
- 质保金: 百分比如 "5%" 或 null
- 质保期: 如 "12个月"、"2年" 或 null
- 是否涉及农民工代付: true/false
- 是否涉及垫付: true/false
- 合同开始时间: "YYYY-MM-DD"
- 合同截止时间: "YYYY-MM-DD" 或描述性文字如 "质保期届满之日"

## 输出格式要求
严格按以下格式输出，不要加额外解释：

===CONTRACT_START===
（合同 Markdown 全文）
===CONTRACT_END===
===JSON_START===
（JSON 对象）
===JSON_END===
"""

USER_PROMPT_TEMPLATE = """\
请为以下场景生成完整合同和对应的识别结果 JSON。

- **合同编号**: {contract_id}
- **难度级别**: {level}
- **场景描述**: {hint}

确保合同金额、日期等关键数值在合同文本和 JSON 中完全一致。
"""


def call_llm(contract_id: str, level: str, hint: str) -> tuple[str, dict]:
    """调用 LLM 生成合同文本和对应 JSON。"""
    user_msg = USER_PROMPT_TEMPLATE.format(
        contract_id=contract_id, level=level, hint=hint
    )

    url = f"{BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
        "max_tokens": 16384,
    }

    resp = httpx.post(url, json=payload, headers=headers, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]

    # 解析合同文本
    contract_match = re.search(
        r"===CONTRACT_START===\s*\n(.*?)\n\s*===CONTRACT_END===", content, re.DOTALL
    )
    if not contract_match:
        raise ValueError("未找到 CONTRACT 标记")
    contract_text = contract_match.group(1).strip()
    # 去掉可能的 markdown 代码块
    contract_text = re.sub(r"^```(?:markdown)?\s*\n", "", contract_text)
    contract_text = re.sub(r"\n```\s*$", "", contract_text)

    # 解析 JSON
    json_match = re.search(
        r"===JSON_START===\s*\n(.*?)\n\s*===JSON_END===", content, re.DOTALL
    )
    if not json_match:
        raise ValueError("未找到 JSON 标记")
    json_str = json_match.group(1).strip()
    json_str = re.sub(r"^```(?:json)?\s*\n", "", json_str)
    json_str = re.sub(r"\n```\s*$", "", json_str)
    expected_json = json.loads(json_str)

    return contract_text, expected_json


def main():
    print("=" * 60)
    print("新合同数据批量生成工具")
    print("=" * 60)

    META_DIR.mkdir(parents=True, exist_ok=True)

    total = sum(len(v) for v in NEW_CONTRACTS.values())
    print(f"\n计划生成 {total} 份新合同")

    # 收集所有待生成的
    to_generate = []
    for level, items in NEW_CONTRACTS.items():
        for item in items:
            md_path = CONTRACTS_DIR / level / f"{item['id']}.md"
            json_path = META_DIR / f"{item['id']}.json"
            if md_path.exists() and json_path.exists():
                print(f"  [SKIP] {item['id']}: 已存在")
                continue
            to_generate.append((level, item, md_path, json_path))

    if not to_generate:
        print("\n所有新合同已存在，无需生成。")
        return

    print(f"\n需要生成 {len(to_generate)} 份...")

    success = 0
    fail = 0

    for idx, (level, item, md_path, json_path) in enumerate(to_generate, 1):
        cid = item["id"]
        hint = item["hint"]
        print(f"\n  [{idx}/{len(to_generate)}] {cid} ({level}): {hint}")

        try:
            contract_text, expected_json = call_llm(cid, level, hint)

            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(contract_text, encoding="utf-8")
            json_path.write_text(
                json.dumps(expected_json, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"    ✓ 合同 {len(contract_text)} 字, JSON {len(expected_json)} 字段")
            success += 1
        except Exception as e:
            print(f"    ✗ 失败: {e}")
            fail += 1

        if idx < len(to_generate):
            time.sleep(2)

    print(f"\n{'=' * 60}")
    print(f"完成: 成功 {success}, 失败 {fail}")
    print("=" * 60)

    # 同时为已有30条生成 meta JSON（从 TSV 中提取）
    print("\n补充已有30条数据的 meta JSON...")
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from generate_contracts import parse_tsv
    existing = parse_tsv()
    created = 0
    for c in existing:
        json_path = META_DIR / f"{c['id']}.json"
        if not json_path.exists():
            json_path.write_text(
                json.dumps(c["expected_json"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            created += 1
    print(f"  补充了 {created} 个 meta JSON 文件")


if __name__ == "__main__":
    main()
