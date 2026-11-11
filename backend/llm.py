from openai import OpenAI, OpenAIError
from backend.tool import execute_tool
from backend.tool_schemas import TOOLS
from backend.errors import AgentError, model_request_error

def request_model(
    client: OpenAI,
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
):
    if not isinstance(model, str) or not model.strip():
        raise AgentError("configuration_error", "未配置模型名称，请检查后端.env", 503)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            max_tokens=1000,
            extra_body={"thinking": {"type": "disabled"}},
        )
    except OpenAIError as error:
        raise model_request_error(error) from None
    return response

def ask_model(
    client: OpenAI,
    model: str,
    messages: list[dict],
) -> str:
    # 在这里迁移已有的请求和响应检查代码
    response = request_model(
        client=client,
        model=model,
        messages=messages,
    )
    if not response.choices:
        raise AgentError("invalid_model_response", "模型没有返回候选结果")
    choice = response.choices[0]
    answer = choice.message.content
    if choice.finish_reason == "length":
        raise AgentError("output_truncated", "模型输出因长度限制被截断")
    if choice.finish_reason == "content_filter" or choice.message.refusal:
        raise AgentError("model_refused", "模型未提供可用回答，请调整问题")
    if choice.finish_reason != "stop":
        raise AgentError("incomplete_model_response", "模型响应未正常完成")
    if not answer or not answer.strip():
        raise AgentError("empty_model_response", "模型返回了空回答")

    return answer

def ask_agent(
    client: OpenAI,
    model: str,
    messages: list[dict],
    edit_proposals: list[dict] | None = None,
) -> str:
    # 在这里串起模型请求、工具执行和最终回答
    work_messages = [message.copy() for message in messages]
    max_model_calls = 4

    available_tools = TOOLS

    if edit_proposals is None:
        available_tools = [
            entry
            for entry in TOOLS
            if entry["function"]["name"] != "create_proposal"
        ]

    for step in range(max_model_calls):
        # 每次请求模型、判断返回、必要时执行工具

        response = request_model(
            client= client,
            model= model,
            messages= work_messages,
            tools=available_tools
        )
        if not response.choices:
            raise AgentError("invalid_model_response", "模型没有返回候选结果")

        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise AgentError(
                code="output_truncated",
                message="模型输出因长度限制被截断",
            )

        if choice.finish_reason == "content_filter" or choice.message.refusal:
            raise AgentError("model_refused", "模型未提供可用回答，请调整问题")

        # 情况一：模型直接给出了文字答案，不需要工具
        if choice.finish_reason == "stop":
            answer = choice.message.content
            if not answer or not answer.strip():
                raise AgentError("empty_model_response", "模型返回了空回答")
            return answer

        # 情况二：只有完整的工具请求，才允许继续执行
        if choice.finish_reason != "tool_calls":
            raise AgentError("incomplete_model_response", "模型响应未正常完成")

        tool_calls = choice.message.tool_calls
        if not tool_calls:
            raise AgentError("invalid_tool_call", "模型未提供有效的工具请求")

        # 第一版限制一次响应最多执行3个工具请求
        if len(tool_calls) > 3:
            raise AgentError("tool_rejected", "单次模型响应的工具请求超过3个")

        if step == max_model_calls - 1:
            raise AgentError("model_call_limit", "已达到模型请求上限，任务尚未完成")

        call_ids = [call.id for call in tool_calls]
        if any(not call_id for call_id in call_ids) or len(set(call_ids)) != len(call_ids):
            raise AgentError("invalid_tool_call", "工具请求编号缺失或重复")

        work_messages.append(
            choice.message.model_dump(exclude_none=True)
        )

        # 逐条执行，并保存每条请求的结果
        for call in tool_calls:
            if call.type != "function":
                raise AgentError("tool_rejected", "不支持这种工具请求")

            result = execute_tool(
                name=call.function.name,
                arguments=call.function.arguments,
                edit_proposals=edit_proposals,
            )

            work_messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })


    raise AgentError("model_call_limit", "Agent未在规定次数内完成任务")
