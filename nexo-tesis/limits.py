"""One place for the size limits shared by the parser, the prompt and storage.

The old values disagreed: unpack rejected drafts over 10000 characters while
update_draft accepted 20000 and the task prompt never mentioned any limit. A
long (and otherwise perfectly valid) "Marco teórico" was rejected with
"La respuesta no cumple el formato académico" every single time.
"""
MAX_RESPONSE_CHARS = 150000   # raw model reply, including JSON escaping
MAX_DRAFT_CHARS = 20000       # one section draft; matches update_draft
MAX_REPLY_CHARS = 10000       # short conversational summary
MAX_CONTEXT_CHARS = 40000     # full project context sent to a model
