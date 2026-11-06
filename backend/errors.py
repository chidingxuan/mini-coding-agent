"""可安全展示的业务错误；不携带密钥、请求正文或SDK异常全文。"""

from openai import (
    APIConnectionError, APIStatusError, APITimeoutError,
    AuthenticationError, OpenAIError, PermissionDeniedError, RateLimitError,
)


class AgentError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def model_request_error(error: OpenAIError) -> AgentError:
    """将已知SDK失败转换成固定错误码，不回显error的原始内容。"""
    if isinstance(error, APITimeoutError):
        return AgentError("model_timeout", "模型请求超时，请稍后手动重试", 504)
    if isinstance(error, APIConnectionError):
        return AgentError("model_connection_failed", "无法连接模型服务，请检查后端网络", 503)
    if isinstance(error, AuthenticationError):
        return AgentError("model_auth_failed", "模型密钥认证失败，请检查后端.env配置", 503)
    if isinstance(error, PermissionDeniedError):
        return AgentError("model_permission_denied", "当前密钥没有访问模型的权限", 503)
    if isinstance(error, RateLimitError):
        return AgentError("model_rate_limited", "模型服务限流，请稍后手动发送", 429)
    if isinstance(error, APIStatusError):
        if error.status_code == 402:
            return AgentError("model_balance_exhausted", "模型账户余额不足，请检查账户额度", 503)
        if error.status_code >= 500:
            return AgentError("model_service_error", "模型服务暂时不可用，请稍后手动发送")
        return AgentError("model_request_rejected", "模型服务拒绝了请求，请检查模型名称和请求参数")
    return AgentError("model_request_failed", "模型请求未完成，请检查后端配置和服务状态")
