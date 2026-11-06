import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI,HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

from backend.llm import ask_model

# api.py在backend中，因此向上两级找到项目根目录
PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")

api_key = os.getenv("DEEPSEEK_API_KEY")
model = os.getenv("DEEPSEEK_MODEL")

app = FastAPI()

conversations: dict[str, list[dict[str, str]]] = {}

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str = Field(min_length=1, max_length=100)


@app.post("/chat")
def chat(body: ChatRequest):
    history = conversations.get(body.conversation_id, [])
    with OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=30,
        max_retries=0,
    ) as client:
        message = [
                {"role": "system", "content": "你是编程助手，使用中文简洁回答。"},
                *history,
                {"role": "user", "content": body.question},
        ]
        try:
            answer = ask_model(client= client, model=model, messages= message)
        except ValueError:
            raise HTTPException(
                status_code=502,
                detail="模型回答未正常完成",
            ) from None

    conversations[body.conversation_id]=[
        *history,
        {'role': 'user', 'content': body.question},
        {'role': 'assistant', "content": answer},
    ]
    return {"answer": answer}
        