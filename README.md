# Autonomous Knowledge Execution Agent — Internal Helpdesk Agent

An agent that perceives (retrieves internal knowledge), reasons about what an
employee needs, decides which action to take, asks for human approval when
the action is critical, executes the action, and explains why it did what it
did. Built entirely with **free, open-source tools and a free-tier LLM API**
— no paid service is required to run this project.

## Why this scenario

The assignment asked for an agent that can retrieve from internal knowledge
sources, reason, decide an action, execute it, and explain itself. I built a
concrete, demonstrable version of that: an **internal IT/HR helpdesk agent**
that answers employee queries using a company knowledge base and can take
real follow-up actions (file a ticket, check leave balance, escalate to HR,
reset a password, etc.) instead of just answering questions.

## Architecture

```
User query
   │
   ▼
[retrieve_node]   Hybrid search (FAISS semantic + BM25 keyword) over the
                   internal knowledge base -> top 3 relevant policy snippets
   │
   ▼
[reason_node]     Gemini LLM reads the query + retrieved knowledge + recent
                   history, decides: intent, which action to take, its
                   parameters, why, and whether it's a critical action
   │
   ▼
 is_critical? ──yes──▶ [approval_node]  Agent pauses and asks a human (CLI
   │no                                   prompt) to approve/reject
   ▼                        │
[execute_node] ◀────────────┘
   Actually calls the chosen Python action function (create_ticket,
   check_leave_balance, reset_password, etc.)
   │
   ▼
[explain_node]    Builds the final explanation for the user AND writes a
                   full audit log row to SQLite (query, decision, reasoning,
                   critical?, approved?, result)
```

This is implemented as a **LangGraph** state graph (`agent/graph.py`) — each
box above is a node, with a conditional edge that routes critical actions
through human approval first.

## Why no step is "hardcoded"

- The knowledge base is just data (`data/knowledge_base.json`) — nothing in
  it is a canned response.
- `reason_node` is the only place that decides *what to do*, and it's a live
  call to an LLM (Gemini) with the retrieved context — the LLM chooses the
  action and writes the reasoning, in JSON, based on the specific query.
- Python code never picks the action itself; it only (a) retrieves data,
  (b) executes whatever action the LLM decided, and (c) enforces the
  approval gate for critical actions.

## Free resources used (no paid API/service anywhere)

| Component | Tool | Why free |
|---|---|---|
| LLM reasoning | **Google Gemini API** (`gemini-3.1-flash-lite`) | Free tier, no credit card — get a key at https://aistudio.google.com/app/apikey |
| Embeddings | **sentence-transformers** (`all-MiniLM-L6-v2`) | Open-source, runs 100% locally, downloads once from HuggingFace, zero cost |
| Vector search | **FAISS** (`faiss-cpu`) | Open-source, local, no server needed |
| Keyword search | **rank_bm25** | Pure Python, open-source |
| Orchestration | **LangGraph** | Open-source |
| Audit log / memory | **SQLite** (Python's built-in `sqlite3`) | No install, no server |

> If you'd rather not use Gemini, this can be swapped for **Groq's free API**
> (also free, no card, very fast Llama models) by changing the LLM client in
> `agent/graph.py` — the rest of the pipeline stays identical.

## Project structure

```
agentic-helpdesk/
├── data/knowledge_base.json   # internal knowledge source (the "database")
├── knowledge/retriever.py     # hybrid FAISS + BM25 retrieval
├── actions/actions.py         # the real actions the agent can execute
├── agent/graph.py             # LangGraph: retrieve -> reason -> approve -> execute -> explain
├── memory/audit_log.py        # SQLite audit log + short-term memory
├── main.py                    # CLI entry point
├── requirements.txt
├── .env.example
└── README.md
```

## Setup (from scratch)

1. **Clone/unzip the project**, then create a virtual environment:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Get a free Gemini API key**: go to
   https://aistudio.google.com/app/apikey → "Create API key" (no credit card
   required).

4. **Configure your key**:
   ```bash
   cp .env.example .env
   # then open .env and paste your key into GEMINI_API_KEY=
   ```

5. **Run it**:
   ```bash
   python main.py
   ```

First run will download the small embedding model (~80MB) automatically —
this needs an internet connection once; after that it's cached locally.

## Example session

```
Enter your employee ID (or press Enter for 'EMP001'): EMP001

You: my laptop is extremely slow, can someone look at it?

--- Agent ---
Intent understood: report a hardware performance issue
Reasoning: The knowledge base classifies slow hardware as an IT support
issue that should be filed as a ticket; this is not critical and does not
need human approval.
Action taken: create_ticket
Result: Support ticket TCK-4821 created for: laptop extremely slow (severity: medium).

You: please reset my password, I'm locked out

[HUMAN APPROVAL REQUIRED]
  Action proposed : reset_password
  Parameters      : {'employee_id': 'EMP001'}
  Agent reasoning : Password resets are marked critical in policy and
  require identity verification and human approval before execution.
Approve this action? (y/n): y

--- Agent ---
Intent understood: reset a forgotten/locked account password
Reasoning: ...
Action taken: reset_password
Result: Password for EMP001 has been reset and a temporary password sent.
```

## Bonus features implemented

- **Human-in-the-loop approval** for critical actions (`reset_password`,
  `deactivate_account`) — the agent explicitly pauses and will not execute
  without a "y".
- **Full audit logging** — every query, decision, reasoning, and result is
  written to `agent_memory.db` (SQLite) with a timestamp.
- **Short-term/long-term memory** — the last 3 interactions are pulled back
  into the reasoning prompt so the agent has continuity across a session.
- **Hybrid retrieval** (semantic + keyword) instead of a single-method
  search, so it's more robust to how the query is phrased.
- **Multiple internal knowledge entries** with different policy domains
  (leave, IT, security, HR escalation, reimbursement, WFH).

## Notes / limitations

- Actions (`actions/actions.py`) are simulated (they return structured
  results and don't call a real ticketing/HRMS system) — the assignment
  is evaluating the agent's autonomous reasoning and action-selection
  loop, not a real backend integration. Swapping in real API calls there
  would take the exact same interface.
- If Google renames or retires `gemini-3.1-flash-lite` by the time you run
  this, check https://ai.google.dev/gemini-api/docs/models for the current
  stable free-tier model and update `GEMINI_MODEL` in `.env`.
