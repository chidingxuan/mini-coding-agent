# Mini Code Agent

一个由学习者逐步实现的真实DeepSeek项目。终端对话和模型模块已接通；当前整理后端目录，准备亲手实现HTTP接口。

## 开发约定

- 所有模型业务使用真实DeepSeek；不提供假模型、离线业务或预设回答。
- 不预写教师函数、SDK封装、业务答案或一大套接线代码。学习者先写最小实现，教师解释、检查，再一起重构。
- 前端由教师负责，但等第一条后端链路打通后再接入，不抢跑。
- 每一步明确输入、输出、执行时刻与真实验收效果。密钥仅本地.env或环境变量，不放聊天、网页或Git。
- 不自动重试；失败保留原样分析。允许真实API成本，不意味着允许读取私人文件、任意执行命令或公开部署。

## 当前结构与进度

```text
Mini Code Agent/
├── main.py                 # 终端入口，仍可点三角运行
├── backend/
│   ├── __init__.py          # Python包标记
│   ├── llm.py               # 你实现的ask_model，迁移时逻辑不改
│   └── api.py               # HTTP入口预留，尚未实现
├── .env                    # 本地配置，不上传
├── .env.example
├── requirements.txt
└── README.md
```

main.py从backend.llm导入ask_model。后续HTTP接口也复用它；不要导入带终端输入循环的main.py。

已用两次真实DeepSeek请求验证终端历史追问，随后/exit正常退出；这是当前正常链路证据，不代表所有失败路径或独立复现均已验收。

下一步只编写backend/api.py。它要从项目根目录定位.env，而不是查找backend目录里的.env；未来服务启动入口是backend.api:app。目前只有说明文字，还没有app，不要提前执行该启动命令。frontend和docs在实际需要时再创建；当前没有数据库、流式或文件工具。

准备：在本目录新建`.env`，按`.env.example`填写你已有的DeepSeek密钥。不要把真实密钥粘贴给教师。

本机已创建独立`.venv`，无需重复安装。换设备时在项目根目录执行：

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Windows把解释器路径换成`.venv/Scripts/python.exe`。写好后运行`.venv/bin/python main.py`；创建.env和导入库不会发送聊天请求，调用生成接口才会。

## 后续方向，仅作规划

真实调用 → 自己组织多轮上下文 → HTTP接口和前端 → SQLite → 文档检索与引用 → 有边界的代码工具 → 授权补丁与隔离测试 → 长任务恢复。

现有知识在这个项目中逐项复习，新知识按实际缺口补。旧课程及作答保留，不以教师演示或自述理解代替独立实现证据。

参考：[DeepSeek请求协议](https://api-docs.deepseek.com/api/create-chat-completion/) · [开源架构对照](https://github.com/shareAI-lab/learn-claude-code)。当前没有复制开源代码，也没有克隆或接入完整Agent框架。
