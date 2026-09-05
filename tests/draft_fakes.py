"""In-memory draft repository for controller tests without application data."""

from chat.drafts import ChatDraft


class MemoryDraftRepository:
    def __init__(self) -> None:
        self.items: dict[str, ChatDraft] = {}

    def get_draft(self, chat_id: str) -> ChatDraft:
        return self.items.get(chat_id, ChatDraft(chat_id))

    def save_draft(self, draft: ChatDraft) -> ChatDraft:
        current = self.get_draft(draft.chat_id)
        if draft.revision > current.revision:
            self.items[draft.chat_id] = draft
        return self.get_draft(draft.chat_id)
