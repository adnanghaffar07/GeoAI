# CR-006: "Ask about road risk" Assistant (Proposal)

**Status:** **Approved 2026-11-02** (owner: "ok go according to you but kept in mind we have to use free resources only"). R-D1 changed to the free local option (section 8). Agreed order: after F4 (owner, 2026-10-30).
**Builds on:** F4 (road risk, alerts, permissions), roadmap §7, F4-D2 (levels only).

## In plain words

A box in the **Road risk** tab where a person can type a question in normal words and get a short answer,
for example:

- "Which roads should we inspect first this week, and why?"
- "Why is Main Street high risk?"
- "Will the freeze-thaw this week affect our roads?"
- "Which high-risk roads have no inspection planned?"
- "What changed since last Monday?"

The assistant **only reads what the app already shows that person**, answers in plain English, and links to
the pages it used. It never changes anything: it can suggest "plan an inspection", but the person clicks the
button themselves.

## 1. Rules the assistant must follow (from the 2026-10-30 discussion)

| Rule | How it is enforced |
|---|---|
| Answers only from the app's data | The server gives it only the data for this project and question (road list, road pages, weather, alerts, inspections); it has no web access |
| Respects permissions | It is available only to people who can see road risk in that project; it gets only what that person may see (e.g. no alerts for viewers) |
| Cites its sources | Every answer ends with links: the road pages, the alert, the weather source and date |
| Says "I don't know" | If the data does not answer the question (e.g. repair cost, a road outside the project), it says so |
| No percentages | Levels only (F4-D2); it never invents a probability or shows the raw model value |
| Suggestions only | It cannot plan, change, delete or send anything |
| Labelled | Every answer shows "TRIAL FORECAST · AI answer: check the linked pages" |
| Recorded | Each question and answer is kept in the project history (who, when, which data was used) |

## 2. How it works

1. The person types a question in the Road risk tab.
2. The backend checks their permissions and collects the allowed data for the project (top roads with
   reasons, the roads named in the question, the 7-day outlook, open alerts, inspections).
3. That data and the rules above go to an AI language model, which writes the answer.
4. The backend checks the answer (no percentage, links only to this project's pages) before showing it.

## 3. Screens

- Road risk tab: an **"Ask about road risk"** box with 4 example questions to click, the answer below with
  its links, and "Was this helpful? Yes / No".
- No chat history between visits (each question stands alone), so nothing piles up.

## 4. Tests

- A fixed set of about 30 test questions with the expected behaviour: correct roads and reasons, "I don't
  know" when it should, never a percentage, no hidden data for viewers or field collectors, no actions.
- The usual backend and frontend tests; the owner tries it with the guide.

## 5. Decisions for the owner

| # | Question | Options | Suggestion |
|---|---|---|---|
| R-D1 | Which AI model writes the answers | (a) A hosted AI service (e.g. Anthropic Claude API or OpenAI): good answers; needs an account, an API key and a monthly cost; project data is sent to that service. (b) A free model running on the laptop (e.g. Ollama): no cost, data stays local; weaker answers and slow on this laptop | **(a) a hosted service with a monthly spending limit**, after checking the client is fine with sending road and inspection data to it (no photos, no personal data) |
| R-D2 | Who can use it | People who can see road risk / project managers only | **People who can see road risk** (it shows nothing they could not see already) |
| R-D3 | Keep questions and answers | Not at all / in the project history | **In the project history**, so answers can be checked later |
| R-D4 | Daily limit per person | None / e.g. 30 questions a day | **30 a day**, to keep the cost predictable |

## 6. What it needs from the owner or partner

- R-D1 decision, and for option (a): an account with the AI service, an API key in `.env`, and a monthly
  spending limit set in that service's console.
- Confirmation (PI) that sending road-risk data (road names, levels, reasons, weather, inspection dates and
  notes) to the AI service is acceptable for the client.

## 7. Time

About 1-1.5 weeks after approval, in two parts tested on the laptop: part 1 backend (data collection, rules,
answer checks, the 30-question test set); part 2 the screen and the owner check.

## 8. Owner decision: free resources only (2026-11-02)

| # | Decision |
|---|---|
| R-D1 | **Free, on the laptop:** Ollama (open-source, free) in its own Docker container with a small open model (about 2-3 GB, e.g. Llama 3.2 3B or Qwen 2.5 3B, downloaded once). No account, no API key, no cost, and no project data leaves the computer. |
| R-D1b | **Answers built from the data first:** the server works out the facts (which roads, levels, reasons, weather days, inspections) with ordinary code; the model only understands the question and writes the sentence. If the model is off or too slow, the box still answers the common questions with a plain built-in answer. This keeps answers correct even with a small model. |
| R-D2 | People who can see road risk. |
| R-D3 | Questions and answers kept in the project history. |
| R-D4 | 50 questions per person per day (no cost, but it keeps the laptop responsive). |

**What this costs instead of money:** a one-time download of about 2-3 GB; about 3-4 GB of memory for
Docker while the assistant is in use (Docker Desktop -> Settings -> Resources: at least 8 GB in total); and
answers take about 10-40 seconds on this laptop's processor (no graphics card used). On the live demo it
runs on the same laptop through the tunnel. When the app later moves to a server (P10), the same container
moves with it.

**Update 2026-11-03:** the laptop downloads at about 70 KB/s, so the model is **qwen2.5:0.5b (about 0.4 GB)** instead of a 3B model (`ASSISTANT_MODEL` in `.env`). It only rephrases facts the app has already worked out; every reply is still checked, with the built-in answer as fallback.
