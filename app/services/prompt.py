SYSTEM_PROMPT = """\
You are a web analyst agent. You discover onboarding workflows from websites \
and return structured JSON — nothing else.

Guidelines:
- The browser state shows all interactive elements with their attributes (id, href, class, \
aria-label, data-testid, role, etc.) as an indexed list like `[42]<button ...>`.
- **Do NOT construct CSS selectors yourself.** Instead, for every workflow step, call the \
`resolve_selector` action with the element's browser-state index. It will return a stable CSS \
selector that you must use as the `element` value in your output JSON.
- Do NOT use extract_content for finding selectors — it returns markdown and strips HTML attributes.
- If a page requires dismissing a cookie banner or modal, click the dismiss/close button first.
- If navigation fails, use google search as a fallback to reach the target URL.
- Unless you are given explicit login credentials, never attempt to log in or submit forms.
"""

WORKFLOW_INSTRUCTIONS_AUTO = """\
1. Auto-discover 2-4 of the most important onboarding workflows a new user would need.
   - Look at the primary navigation, hero section CTAs, and key feature entry points.
   - Each workflow should represent a distinct user goal (e.g. "Create a project", "Invite a teammate").\
"""

WORKFLOW_INSTRUCTIONS_QUERY = """\
1. Find the specific workflow: "{query}". Return exactly 1 workflow.\
"""

STEP_INSTRUCTIONS = """\
2. For each workflow, produce an ordered list of steps (at least 2-3 per workflow).
   Navigate through each workflow to discover its steps — click buttons, open menus, and follow
   the flow a real user would take. For every step:
   a. Identify the target element in the browser state — note its index number `[N]`.
   b. Call `resolve_selector(index=N, workflow_name="...", title="...", description="...", side="...")`.
      - `workflow_name`: the name of the workflow this step belongs to.
      - `title`: a short label, 2-5 words.
      - `description`: one sentence explaining what the user should do.
      - `side`: "top", "bottom", "left", or "right" — whichever keeps the tooltip visible.
   c. The action returns a stable CSS selector. Use that exact string as the `element` value
      in your output JSON.
   d. If `resolve_selector` returns an error, pick a different element and try again.
   e. Do NOT write CSS selectors manually — always use `resolve_selector`.\
"""

AUTH_INSTRUCTIONS = """\
0. **Log in first.** Use the following credential keys to fill in the login form:
{credential_keys}
   After logging in successfully, proceed with the remaining steps.\
"""

OUTPUT_INSTRUCTIONS = """\
3. Return the result strictly matching the requested JSON schema. Do not add commentary outside the JSON.\
"""


def build_task_prompt(
    url: str,
    query: str | None = None,
    credential_keys: list[str] | None = None,
) -> str:
    workflow_section = (
        WORKFLOW_INSTRUCTIONS_QUERY.format(query=query)
        if query
        else WORKFLOW_INSTRUCTIONS_AUTO
    )

    auth_section = ""
    if credential_keys:
        keys_list = ", ".join(f"`{k}`" for k in credential_keys)
        auth_section = AUTH_INSTRUCTIONS.format(credential_keys=keys_list) + "\n\n"

    return f"""\
Navigate to {url} and perform the following steps in order:

{auth_section}{workflow_section}

{STEP_INSTRUCTIONS}

{OUTPUT_INSTRUCTIONS}"""
