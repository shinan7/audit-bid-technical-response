# 标书技术方案核验 Skill

`audit-bid-technical-response` 是一个面向 Codex 的中文标书核验 Skill，用于将采购文件中的技术要求与投标文件中的技术方案进行逐条关联和可追溯核验。

它不会修改采购文件或投标文件，而是在独立目录中生成要求清单、证据关联、模块报告和总报告。

本项目采用 [Apache License 2.0](./LICENSE)。安全问题请按照 [Security Policy](./SECURITY.md) 通过 GitHub 私密渠道报告。

## 核心能力

- 从 DOCX 采购文件中拆分原子技术要求。
- 将采购要求与投标方案中的段落、表格和图片建立多对多关联。
- 先生成关联关系和核验模块计划，待用户确认后再进行正式核验。
- 按模块判断充分响应、部分响应、未响应或无法判断。
- 检查指标、接口、部署、SLA、人员、周期、交付物和额外承诺之间的冲突。
- 实际检查架构图、流程图、产品截图和图片化表格。
- 使用 Microsoft Word 导出的 PDF 提供可追溯的 Word 物理页码。
- 输出中文 Markdown 报告和结构化 JSON 状态文件。

## 适用范围

适用于以下场景：

- 信息化、软件平台、人工智能及系统集成项目的技术标核验。
- 检查技术方案是否完整响应采购要求。
- 定位遗漏指标、内部矛盾、负偏离、过度承诺和评审定位风险。
- 在提交投标文件前形成可执行的修改清单。

当前版本的正文输入以 DOCX 为主。扫描件、XLSX 或缺少正文结构的文件不能直接作为正式核验正文；如引用了未提供的附件，报告会将其列入人工确认清单。

## 仓库结构

```text
.
├── README.md
└── audit-bid-technical-response/
    ├── SKILL.md
    ├── agents/
    │   └── openai.yaml
    ├── references/
    │   ├── audit-rules.md
    │   ├── output-contracts.md
    │   └── report-templates.md
    ├── requirements.txt
    └── scripts/
        ├── preprocess_docx.py
        └── docx_preprocessor/
```

详细工作流参见 [SKILL.md](./audit-bid-technical-response/SKILL.md)。

## 环境要求

- 支持 Skills 的 Codex 环境。
- Python 3.10 或更高版本。
- `python-docx`、`lxml`、`Pillow` 和 `pdfplumber`。
- 两份 DOCX：采购文件和投标文件。
- 如需可靠页码，应提供两份 DOCX 分别通过 Microsoft Word 导出的 PDF。

Codex Desktop 通常可以使用工作区捆绑的 Python 运行时。只有在捆绑运行时不可用或依赖缺失时，才需要安装 [requirements.txt](./audit-bid-technical-response/requirements.txt) 中的依赖。

## 安装

### 通过 Codex 安装

在 Codex 中输入：

```text
请使用 $skill-installer 从 https://github.com/shinan7/audit-bid-technical-response/tree/main/audit-bid-technical-response 安装这个 Skill。
```

安装完成后，开启新对话或重新加载 Skills 列表。

### 手动安装

```bash
git clone https://github.com/shinan7/audit-bid-technical-response.git
mkdir -p ~/.codex/skills
cp -R audit-bid-technical-response/audit-bid-technical-response ~/.codex/skills/
```

如果当前 Python 环境缺少依赖，可在获得安装许可后执行：

```bash
python3 -m pip install -r ~/.codex/skills/audit-bid-technical-response/requirements.txt
```

## 使用方法

准备采购 DOCX 和投标 DOCX 后，在 Codex 中输入：

```text
使用 $audit-bid-technical-response 核验采购文件和投标文件的技术方案。

采购文件：/path/to/procurement.docx
投标文件：/path/to/bid.docx
```

如果已经有 Microsoft Word 导出的 PDF，也可以一并提供：

```text
采购文件：/path/to/procurement.docx
采购文件 Word PDF：/path/to/procurement-word.pdf
投标文件：/path/to/bid.docx
投标文件 Word PDF：/path/to/bid-word.pdf
```

## 标准工作流

1. 检查两份 DOCX、可选 Word PDF 和核验范围。
2. 确定性提取段落、表格、图片、章节和页码。
3. 拆分采购原子要求并建立候选证据关联。
4. 生成关联关系与模块计划。
5. 等待用户明确确认关联、模块边界和执行顺序。
6. 按模块逐条核验并生成模块报告。
7. 进行全局冲突检查并生成总报告。

在用户确认模块计划前，Skill 不会提前给出“充分响应”“部分响应”或“未响应”等正式结论。

## 页码规则

- Microsoft Word 导出的 PDF 是唯一页码权威。
- 不使用 LibreOffice、DOCX XML 分页符或模型估算结果冒充 Word 物理页码。
- 标书段落归一化后仅完整等于“供应商（公章）”（可带冒号）时，允许标记“页码无法确认”。
- 其他非空正文和表格会继续执行正常页码映射或邻接页范围继承。
- `--export-with-word` 仅适用于安装了 Microsoft Word 的 macOS，并且需要用户明确授权。
- Windows、Linux 或未安装 Microsoft Word 的环境，应由用户预先提供 Word 导出的 PDF。
- 如果没有 Word PDF，用户可以选择继续核验，但报告必须明确标注页码无法确认。

## 输出内容

典型输出目录如下：

```text
audit-work/
├── project.json
├── procurement/
├── bid/
├── state/
│   ├── requirements.json
│   ├── associations.json
│   ├── modules.json
│   └── facts.jsonl
└── reports/
    ├── 01-association-and-module-plan.md
    ├── modules/
    └── 00-summary.md
```

主要交付物：

- `01-association-and-module-plan.md`：要求关联、低置信度事项和建议模块。
- `reports/modules/`：各模块的逐条核验矩阵。
- `00-summary.md`：总体结论、风险汇总、冲突、优先修改项和模块索引。

## 隐私与安全

- Skill 不会修改采购文件或投标文件。
- 原文、图片和核验报告只写入用户指定的独立输出目录。
- 不会凭空补造产品能力、人员、周期、接口、指标或服务承诺。
- 公开仓库不应包含客户文件、投标文件、Word PDF、核验报告或 `audit-work` 输出目录。
- 发布前应检查提交内容中是否存在客户名称、个人信息、内部路径、密钥或编译缓存。
- 漏洞报告不得附带真实采购文件、投标文件、核验报告、凭据、个人信息或客户数据；请使用合成样例并参照 [SECURITY.md](./SECURITY.md)。

## 常见问题

### 为什么必须先确认模块计划？

采购文件与投标文件通常章节顺序不同。确认门禁可以让用户修正关联关系、拆分或合并模块，并指定暂不核验的范围，避免在错误关联上形成正式结论。

### 没有 Microsoft Word PDF 能否使用？

可以继续完成结构提取和技术核验，但不能声称页码是可靠的 Word 物理页码。报告必须显示候选页码或“页码无法确认”。

### 能否直接核验 PDF 或 Excel？

当前版本的正式核验正文以 DOCX 为主。PDF 仅作为 Word 物理页码来源；扫描 PDF 和 XLSX 不属于当前首版正文范围。

### Skill 会自动修改投标文件吗？

不会。Skill 只生成独立核验报告和补写、改写建议，不直接修改源文档。
