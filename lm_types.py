from typing import List, Optional, TypedDict, NotRequired
# https://docs.python.org/3/library/typing.html
# https://docs-python.ru/standart-library/modul-typing-python/

class UsageResponse(TypedDict):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class MessageResponse(TypedDict):
    role: str
    content: str

class ChoiceResponse(TypedDict):
    index: int
    message: MessageResponse
    logprobs: Optional[str]
    finish_reason: str

class ModelResponse(TypedDict):
    id: str
    object: str
    created: int
    model: str
    choices: List[ChoiceResponse]
    usage: UsageResponse
    system_fingerprint: str

class UserData(TypedDict):
    user_id: int
    registration_date: str
    last_active_date: str
    context: NotRequired[str]
