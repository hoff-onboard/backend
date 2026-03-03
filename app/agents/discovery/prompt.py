SYSTEM_PROMPT = """\
You are a web analyst. Browse the given website and identify the most important onboarding \
workflows a new user should know about. Return only structured JSON — nothing else.

Guidelines:
- Explore the primary navigation, hero CTAs, and key feature entry points.
- Each workflow should represent a distinct user goal (e.g. "Create a project", "Invite a teammate").
- Do NOT extract workflow steps — only identify workflow names and one-sentence descriptions.
- If a cookie banner or modal appears, dismiss it first.
- If navigation fails, use a Google search as a fallback to reach the target URL.
"""


def build_task_prompt(url: str, query: str | None = None) -> str:
    query_line = (
        f'\n- The workflow "{query}" MUST be included in your list.' if query else ""
    )
    return f"""\
Navigate to {url} and identify up to 5 onboarding workflows worth teaching a new user.{query_line}

Return a JSON object with a list of workflow names and one-sentence descriptions.
Do not extract steps — only identify the workflows at a high level."""
