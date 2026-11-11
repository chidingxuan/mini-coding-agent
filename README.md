# Mini Code Agent

一个由学习者逐步实现的真实 DeepSeek 项目。现已接通命令行、HTTP多轮会话、SQLite聊天历史、受限代码搜索与读取工具，以及可恢复旧会话的本地聊天网页。

## 开发约定

- 所有模型业务使用真实DeepSeek；不提供假模型、离线业务或预设回答。
- 不预写教师函数、SDK封装、业务答案或一大套接线代码。学习者先写最小实现，教师解释、检查，再一起重构。
- 前端由教师负责，但等第一条后端链路打通后再接入，不抢跑。
- 每一步明确输入、输出、执行时刻与真实验收效果。密钥仅本地.env或环境变量，不放聊天、网页或Git。
- 新增改动必须先说明单步范围，得到用户明确要求后只执行该步，不顺带完成后续步骤。
- 不自动重试；失败保留原样分析。允许真实API成本，不意味着允许读取私人文件、任意执行命令或公开部署。

## 当前结构与进度

```text
Mini Code Agent/
├── main.py                 # 终端入口，仍可点三角运行
├── backend/
│   ├── __init__.py          # Python包标记
│   ├── llm.py               # request_model、ask_model、ask_agent
│   ├── tool.py              # 模型工具参数检查与分发
│   ├── tool_schemas.py      # 给模型看的工具说明
│   ├── file_access.py       # 访问范围、路径检查、读取与搜索
│   ├── proposal_files.py    # 差异、提案、版本检查、备份与文件替换
│   ├── edits.py             # 应用提案的协调流程和单进程锁
│   ├── errors.py            # 带错误码的AgentError
│   ├── storage.py           # SQLite建表、保存、读取和列出会话
│   └── api.py               # 聊天、会话查询、网页和静态资源入口
├── frontend/dist/
│   ├── index.html           # 网页结构
│   └── assets/
│       ├── app.css          # 网页样式
│       └── app.js           # 输入、请求、展示与会话切换
├── tests/
│   ├── test_web.py          # 网页接线测试，不调用模型
│   ├── test_errors.py       # SDK错误映射与真实本地工具测试
│   └── test_preview_edit.py # 临时真实文件的预览与只读权限测试
├── workspace/demo.py        # 唯一允许手动确认修改的演练文件
├── runtime/agent.sqlite3    # 本机聊天数据库，不上传
├── .env                    # 本地配置，不上传
├── .env.example
├── requirements.txt
└── README.md
```

main.py 和 HTTP 接口均复用 backend.llm.ask_agent，不导入带终端输入循环的 main.py。

Agent 支持有限多轮工具调用：一次用户提问最多请求模型4次，每次响应最多接受3个工具请求。第4次若仍要求工具，则停止而不执行新的工具；若返回完整文字答案则成功。请求异常不自动重试，不是无限自主循环。

list_files 只列出白名单中实际存在的文件名；read_file 只允许读取 main.py、backend/api.py、backend/llm.py、workspace/demo.py，并检查实际路径和20000字节大小限制。search_code 复用同一白名单，进行区分大小写的字面关键词匹配，返回路径、行号及最多300字符的命中行，最多20条；不是向量检索，不执行代码。read_lines 返回指定行区间及原始行号，包含结束行，一次最多80行；内部仍先读文件再截取，减少的是发给模型的内容。.env和个人研究文件backend/ceshi.ipynb不在工具白名单内，也不上传GitHub。模型只能读取、搜索和提出修改，不提供应用提案、Shell或执行代码的模型工具。

preview_edit(path, old_text, new_text) 生成单处精确替换的 unified diff 预览。old_text 必须非空、在当前文件中唯一出现，且不带read_lines添加的行号；缩进和换行不会被strip。原文找不到、重复（含重叠匹配）、没有实际变化、类型错误时拒绝。new_text 可为空来预览删除；单个替换文本不能超过20000字符，拟修改后的UTF-8文件不能超过20000字节。工具说明要求模型先读取原文，在最终回答中用diff代码块完整展示工具返回的差异，并说明仅预览。现有网页支持代码块，无需专门的前端改动。

preview_edit只在内存中计算字符串，不写文件、不运行代码、不验证修改后的Python语法或业务正确性，也不保存可应用提案。2026-11-10曾按用户要求撤回整段确认实现；随后按单步教学重新接入下述功能，旧恢复存档不参与当前执行。

create_proposal返回id、path、old_text、new_text、diff；演练文件额外保存与差异来自同一次快照的before_sha256。编号和提案不代表写入批准。/chat收集实际工具生成的提案，与问答在同一SQLite事务中保存，并返回answer和proposals。历史接口返回消息编号及提案，用assistant_message_id恢复对应卡片。默认None的旧命令行调用不提供create_proposal工具。旧提案没有指纹时不能补算成当前版本，也不能应用。

网页仅为workspace/demo.py且带有效指纹的待应用提案提供按钮；二次确认后调用POST /proposals/{proposal_id}/apply，只提交conversation_id和严格布尔值confirmed=true。后端检查固定本地Origin、会话范围、pending状态、路径及符号链接、文件指纹和差异；保存原内容备份，使用同目录临时文件替换目标，再记录applied状态及备份路径。其他源码继续只读，修改后的代码不自动执行。取消不发送应用请求，已应用提案不再提供按钮；失败或断连不自动重试，特别是“文件已改但状态记录失败”必须先人工核查。备份位于runtime/edit_backups，不上传Git。

安全边界：仅限127.0.0.1上的本机单进程开发演练；Origin和会话编号不是用户鉴权，进程锁不是跨进程锁，文件与SQLite不具备联合事务，也未实现中断后的自动恢复或恶意文件系统并发防护。应用时不要同时手动编辑演练文件，不要公开部署或放宽写入范围。

每次模型请求的 max_tokens 当前为1000。AgentError 为输出截断、模型请求次数耗尽、工具拒绝、参数错误、文件读取失败，以及常见模型服务异常提供稳定错误码；/chat 用 detail.code 和固定安全说明返回给网页。网页按错误码显示提示，不回显SDK异常全文、不自动重发。模型失败时不会保存本轮成功问答。

HTTP会话历史完整保存在SQLite中，一轮问题和回答在同一事务中写入；工具调用的临时消息不入库。/chat 每次只发送最近10轮历史，加上系统规则和当前问题；这是轮数限制，不是严格token预算。GET /conversations 列出会话，按最新消息编号降序排列；GET /conversations/{conversation_id}/messages 返回指定会话的完整历史。当前命令行入口仍使用临时内存历史，尚未接入SQLite和HTTP历史轮数限制。

准备：在本目录新建`.env`，按`.env.example`填写你已有的DeepSeek密钥。不要把真实密钥粘贴给教师。

本机已创建独立`.venv`，无需重复安装。换设备时在项目根目录执行：

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Windows把解释器路径换成`.venv/Scripts/python.exe`。终端聊天运行`.venv/bin/python main.py`；创建.env和导入库不会发送聊天请求，调用生成接口才会。

## 打开本地聊天网页

在项目根目录启动（只监听本机）：

```sh
.venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8010 --reload
```

浏览器打开 <http://127.0.0.1:8010/>，接口文档仍在 <http://127.0.0.1:8010/docs>。终端保持运行，Ctrl+C停止。不需要 Node、前端安装或构建；不要双击 index.html 以 file:// 打开。

- 示例问题只填入输入框；点击发送或按 Enter 才发真实请求，Shift+Enter换行。中文输入法选字的 Enter 不会提交。
- 等待回答时禁用重复提交和新建对话；不虚构工具进度，不自动重试。断网时后台可能仍在处理原请求，应先检查终端。
- 新建对话使用新的 conversation_id，不删除旧记录；侧栏及手机上的“历史会话”可恢复旧对话。已保存或已打开的会话编号放在URL片段中，刷新后重新读取数据库；未保存的新对话刷新后重新开始。消息正文不写入浏览器持久存储。
- 后端重启后SQLite记录仍保留。有草稿时切换旧会话需确认；读取失败保留当前会话和草稿。网页恢复完整记录，不代表模型每次能看到全部旧内容，最近10轮之前的细节可能无法回忆。
- 当前没有鉴权、同会话并发保护或生产部署支持，只能在本机开发使用。勿公开暴露会话查询接口或把conversation_id当作访问凭证。
- 网页只接触同源聊天和会话查询接口，密钥留在后端；只公开 frontend/dist/assets，不公开项目根目录或数据库文件。回答以文本及代码块展示，不执行其中的HTML。
- 页面不显示工具名、耗时或token等后端没有提供的实时事件。需要观察这些信息时继续使用调试方式，而不是把推测当进度。

不产生模型费用的网页接线、错误映射和预览测试（预览测试使用临时真实文件，不替换模型）：

```sh
.venv/bin/python -m unittest discover -s tests -v
```

真实提问会调用 DeepSeek；普通回答可能一次模型请求，多轮工具任务可能需要多次（当前最多4次）。提高 max_tokens 是提高每次输出上限，不代表每次固定消耗该数量。回答仍需对照代码核实。

只读预览演练可在网页发送：先读取main.py中初始化history的代码，再调用preview_edit，把该行注释改成“保存当前会话历史”，完整展示diff，明确仅预览、不写入、不执行。此预览验收曾用真实DeepSeek完成read_lines→preview_edit→最终diff展示，共3次模型请求，逐字节核对原三个目标文件未变，历史只存入临时数据库。

## 后续方向，仅作规划

真实调用 → 自己组织多轮上下文 → HTTP接口和前端 → SQLite → 文档检索与引用 → 有边界的代码工具 → 授权补丁与隔离测试 → 长任务恢复。

现有知识在这个项目中逐项复习，新知识按实际缺口补。旧课程及作答保留，不以教师演示或自述理解代替独立实现证据。

参考：[DeepSeek请求协议](https://api-docs.deepseek.com/api/create-chat-completion/) · [开源架构对照](https://github.com/shareAI-lab/learn-claude-code)。当前没有复制开源代码，也没有克隆或接入完整Agent框架。
