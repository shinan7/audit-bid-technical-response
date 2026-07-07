# 输出与状态契约

## 目录

1. 目录结构
2. 通用规则
3. 状态文件
4. 引用规则
5. 完成校验

## 1. 目录结构

```text
audit-work/
├── project.json
├── procurement/{document.json,outline.md,chunks/,images/,pagination/}
├── bid/{document.json,outline.md,chunks/,images/,pagination/}
├── state/{requirements.json,associations.json,modules.json,facts.jsonl}
└── reports/{01-association-and-module-plan.md,modules/,00-summary.md}
```

预处理器只创建 `project.json`、`procurement/` 和 `bid/`。模型在确认工作流中创建 `state/` 与 `reports/`。

## 2. 通用规则

- 所有 JSON 根对象包含 `schema_version: "1.0"`。
- 使用 UTF-8、两空格缩进、稳定键顺序。
- 源 ID：段落 `P-000001`、表格 `T-000001`、图片 `IMG-000001`、块 `CHUNK-0001`。
- 模型状态 ID：要求 `REQ-0001`、关联 `ASSOC-0001`、模块 `MOD-001`、事实 `FACT-0001`。
- 状态文件引用源 ID，不复制整份源内容。

每个段落、表格和图片来源记录包含：

```json
{
  "page_start": 18,
  "page_end": 19,
  "page_source": "microsoft_word_pdf",
  "page_confidence": "high",
  "page_match_method": "ordered_exact_text",
  "page_candidates": []
}
```

`page_start`/`page_end` 是 Word PDF 的物理页码；跨页时必须保留完整页码范围。无法唯一消歧时两者为 `null`，并在 `page_candidates` 列出候选范围；无法映射时显示“页码无法确认”，不得猜测。

`document.json.pagination` 必须记录 `status`、`source`、`acquisition`、`pdf_file`、`pdf_sha256`、`page_count`、`mapped_text_blocks`、`total_text_blocks`、`coverage`、`confidence_counts` 和 `warnings`。报告必须有“分页质量”摘要；`unreliable`、`unavailable`、`mismatch` 不得包装成可靠页码。

## 3. 状态文件

### requirements.json

```json
{
  "schema_version": "1.0",
  "requirements": [{
    "id": "REQ-0001",
    "source_ids": ["P-000120"],
    "section_path": ["第三章", "平台能力"],
    "page_start": 18,
    "page_end": 19,
    "excerpt": "应支持……",
    "summary": "支持统一认证",
    "type": "功能",
    "mandatory_terms": ["应"],
    "key_metrics": [],
    "sensitivity": "medium"
  }]
}
```

### associations.json

```json
{
  "schema_version": "1.0",
  "associations": [{
    "id": "ASSOC-0001",
    "requirement_id": "REQ-0001",
    "bid_evidence_ids": ["P-000310", "IMG-000018"],
    "confidence": "high",
    "reason": "正文说明与架构图共同覆盖统一认证"
  }]
}
```

一个要求允许多条关联；一个证据允许出现在多条关联。置信度只用 `high|medium|low`，并必须说明理由。

### modules.json

```json
{
  "schema_version": "1.0",
  "confirmed": false,
  "modules": [{
    "id": "MOD-001",
    "title": "平台与统一认证",
    "parent_id": null,
    "order": 1,
    "requirement_ids": ["REQ-0001"],
    "bid_evidence_ids": ["P-000310", "IMG-000018"],
    "status": "pending"
  }]
}
```

状态只能按 `pending -> in_progress -> complete` 转移。`confirmed` 只有在用户明确确认后才能为 `true`。

### facts.jsonl

每行一个 JSON 对象：

```json
{"schema_version":"1.0","id":"FACT-0001","module_id":"MOD-001","type":"performance","subject":"并发用户","normalized_value":"100","unit":"users","source_ids":["P-000310"],"uncertainty":null}
```

事实类型至少覆盖产品、架构、部署、指标、接口、周期、SLA、人员、交付物、依赖和额外承诺。

## 4. 引用规则

每条正式结论包含采购要求 ID，以及采购和标书两侧的完整页码范围、章节路径、来源 ID、原文摘录/图片摘要、判断理由、风险和建议。

文字摘录必须来自连续原文，不得在引号内改写；不超过 100 字，超过时保留前 98 字并追加 `……`。图片的模型观察摘要放在引号外。

若一项要求对应多处关键响应，必须列出所有实质性支撑结论的出处，而不是只列最佳匹配。全局冲突至少列出两个相互冲突的来源 ID。

## 5. 完成校验

生成总报告前检查：

- 每条要求恰有一个主结论；
- 每个非干净结论都有风险、理由、证据和建议；
- 每个证据 ID 存在于对应 `document.json`；
- 页码与来源记录一致，跨页引用显示完整页码范围；
- 页码歧义显示候选页码，未映射显示“页码无法确认”；
- 摘录均为原文且不超过 100 字；
- 每项结论包含所有实质性支撑位置；
- 每个 `complete` 模块都有报告和至少一条事实或“无关键事实”记录；
- 所有无法读取图片进入“无法判断/需人工确认”；
- 总报告中的统计与逐条结论数量一致。
