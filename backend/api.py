import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field, StrictBool, field_validator

from backend.llm import ask_agent
from backend.errors import AgentError
from backend.edits import apply_proposal
from backend.storage import (
    init_db, load_history, save_turn, list_conversations,
    load_messages, load_proposals,
)
# api.py在backend中，因此向上两级找到项目根目录
PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")

MAX_HISTORY_TURNS = 10
api_key = os.getenv("DEEPSEEK_API_KEY")
model = os.getenv("DEEPSEEK_MODEL")

init_db()
app = FastAPI()

# 只公开前端资源目录，不挂载项目根目录，避免暴露.env和源文件。
FRONTEND_DIR = PROJECT_DIR / "frontend" / "dist"
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def index():
    # 输入：无函数参数；由浏览器GET /调用。
    # 返回：指向前端index.html的FileResponse响应对象；不调用模型、不返回源代码或密钥。
    return FileResponse(FRONTEND_DIR / "index.html")



class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str = Field(min_length=1, max_length=100)


@app.post("/chat")
def chat(body: ChatRequest):
    # 输入：body为已校验的ChatRequest，含question:str和conversation_id:str。
    # 返回：dict，含answer:str及proposals:list；FastAPI将其编码为JSON响应。
    # 副作用：真实调用模型/获准工具并在成功后保存问答和提案；不自动应用提案，业务失败转换为HTTP错误。
    if not body.question.strip():
        raise HTTPException(422, detail={"code": "invalid_input", "message": "问题不能为空"})
    if not api_key or not model:
        raise HTTPException(503, detail={
            "code": "configuration_error",
            "message": "缺少模型密钥或模型名称，请检查后端.env配置",
        })
    history = load_history(body.conversation_id)
    model_history = history[-2 * MAX_HISTORY_TURNS:]
    proposals = []

    with OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=30,
        max_retries=0,
    ) as client:
        message = [
                {"role": "system", "content": "你是编程助手，使用中文简洁回答。"},
                *model_history,
                {"role": "user", "content": body.question},
        ]
        try:
            answer = ask_agent(client= client,
                               model=model,
                               messages= message,
                               edit_proposals= proposals
                               )
            
        except AgentError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={
                    "code": error.code,
                    "message": str(error),
                },
            ) from None

        except ValueError:
            raise HTTPException(
                status_code=502,
                detail={"code": "invalid_model_response", "message": "返回数据未通过检查"},
            ) from None

    save_turn(body.conversation_id, body.question, answer, proposals=proposals)

    return {
        "answer": answer,
        "proposals": proposals,
    }
        
@app.get("/conversations")
def get_conversations():
    # 输入：无函数参数；由GET /conversations调用。
    # 返回：{'conversations': 会话编号列表}，按最近消息排序；只查询数据库，不调用模型。
    return {"conversations": list_conversations()}

@app.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str):
    # 输入：conversation_id为URL路径中的会话编号str。
    # 返回：dict，含conversation_id、messages（带id的消息列表）、proposals（该会话提案列表）。
    # 说明：无记录时两个列表为空；只读数据库，不调用模型或应用提案。
    return {
        "conversation_id": conversation_id,
        "messages": load_messages(conversation_id),
        "proposals": load_proposals(conversation_id),
    }

class ApplyProposalRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=100)
    confirmed: StrictBool

    @field_validator("confirmed")
    @classmethod
    def require_confirmation(cls, value: bool) -> bool:
        # 输入：cls为ApplyProposalRequest类；value为已通过StrictBool类型检查的bool，由Pydantic自动传入。
        # 返回：仅True可返回；False抛ValueError，被Pydantic纳入校验错误，不代表身份认证或执行写入。
        if not value:
            raise ValueError("必须明确确认应用提案")
        return value

def require_local_origin(request: Request) -> None:
    # 输入：request为FastAPI Request，从headers读取Origin请求头。
    # 返回：来源完整匹配两个获准本地地址时返回None，否则抛403 HTTPException；不执行文件操作。
    allowed_origins = {
        "http://127.0.0.1:8010",
        "http://localhost:8010",
    }

    origin = request.headers.get("origin")

    if origin not in allowed_origins:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "untrusted_origin",
                "message": "只允许从本项目的本地网页确认修改",
            },
        )

@app.post("/proposals/{proposal_id}/apply")
def confirm_proposal(
    proposal_id: str,
    body: ApplyProposalRequest,
    request: Request,
):
    # 输入：proposal_id为URL中的str，body为已校验的ApplyProposalRequest（会话编号及confirmed=True），request为请求对象。
    # 返回：应用成功的dict，含proposal_id和status='applied'；来源不合格或业务失败转为HTTP错误。
    # 副作用：通过来源检查后调用apply_proposal，可能实际备份和修改演练文件、更新数据库；不调用模型。
    require_local_origin(request)

    try:
        return apply_proposal(
            conversation_id=body.conversation_id,
            proposal_id=proposal_id,
        )
    except AgentError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={
                "code": error.code,
                "message": str(error),
            },
        ) from None
