from contextvars import ContextVar

# Context variable to hold the current request's user_id
# This ensures that tools called deeper in the stack can access the user_id
# without it being passed as an argument by the LLM (security risk).
current_user_id: ContextVar[str] = ContextVar("user_id", default=None)
