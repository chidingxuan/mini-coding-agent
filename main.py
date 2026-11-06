import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from backend.llm import ask_agent
from backend.errors import AgentError
# 1. 读取main.py同目录下的.env
load_dotenv(Path(__file__).with_name(".env"))

api_key = os.getenv("DEEPSEEK_API_KEY")
model = os.getenv("DEEPSEEK_MODEL")

if not api_key or not model:
    raise SystemExit("缺少DEEPSEEK_API_KEY或DEEPSEEK_MODEL，请检查项目根目录的.env。")


history = []#准备历史会话
# 2. 准备客户端，用完自动关闭/exit


with OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
    timeout=30,
    max_retries=0,
) as client:
    while True:
        question = input("你：").strip()

        if question == "/exit":
            break

        if not question:
            continue
        message = [
                {"role": "system", "content": "你是编程助手，使用中文简洁回答。"},
                *history,
                {"role": "user", "content": question},
        ]
        try:
            answer = ask_agent(client= client,
                                model=model, 
                                messages= message
                        )
        except AgentError as error:
            print(f"⚠️ [{error.code}] {error}")
            continue
        except ValueError:
            print("⚠️ 返回数据未通过检查，本轮不计入历史。")
            continue

        print("助手：", answer)

        history.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ])
