from openai import OpenAI

def ask_model(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    # 在这里迁移已有的请求和响应检查代码
    response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=300,
                extra_body={"thinking": {"type": "disabled"}},
    )
    choice = response.choices[0]
    answer = choice.message.content
    if choice.finish_reason != "stop" or not answer or not answer.strip():
        raise ValueError("本轮回答未正常完成，不计入历史")

    return answer
