from openai import OpenAI
from backend.tool import TOOLS, execute_tool
from backend.errors import AgentError

def request_model(
        client: OpenAI,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict] | None= None,
):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            max_tokens=1000,
            extra_body={"thinking": {"type": "disabled"}},
        )
        return response

def ask_model(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    # 在这里迁移已有的请求和响应检查代码
    response = request_model(
        client=client,
        model=model,
        messages=messages,
    )
    choice = response.choices[0]
    answer = choice.message.content
    if choice.finish_reason != "stop" or not answer or not answer.strip():
        raise ValueError("本轮回答未正常完成，不计入历史")

    return answer

def ask_agent(
    client: OpenAI,
    model: str,
    messages: list[dict],
) -> str:
    # 在这里串起模型请求、工具执行和最终回答
    work_messages = [message.copy() for message in messages]
    max_model_calls = 4

    for step in range(max_model_calls):
        # 每次请求模型、判断返回、必要时执行工具

        response = request_model(
            client= client,
            model= model,
            messages= work_messages,
            tools=TOOLS
        )
        if not response.choices:
            raise ValueError("模型没有返回候选结果")

        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise AgentError(
                code="output_truncated",
                message="模型输出因长度限制被截断",
            )
        
        # 情况一：模型直接给出了文字答案，不需要工具
        if choice.finish_reason == "stop":
            answer = choice.message.content
            if not answer or not answer.strip():
                raise ValueError("模型返回了空回答")
            return answer

        # 情况二：只有完整的工具请求，才允许继续执行
        if choice.finish_reason != "tool_calls":
            raise ValueError("模型响应未正常完成")

        tool_calls = choice.message.tool_calls
        if not tool_calls:
            raise ValueError("缺少工具请求")
        
        # 第一版限制一次响应最多执行3个工具请求
        if len(tool_calls) > 3:
            raise ValueError("工具请求数量超过限制")
        
        work_messages.append(
            choice.message.model_dump(exclude_none=True)
        )

        if step == max_model_calls - 1:
            raise ValueError("已达到模型请求上限，任务尚未完成")
        
        # 逐条执行，并保存每条请求的结果
        for call in tool_calls:
            if call.type != "function":
                raise ValueError("不支持这种工具请求")

            result = execute_tool(
                name=call.function.name,
                arguments=call.function.arguments,
            )

            work_messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })


    # 工具结果已经放入消息，再请求模型生成最终答案
    raise ValueError("Agent未在规定次数内完成任务")