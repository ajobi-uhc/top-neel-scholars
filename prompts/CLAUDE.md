# CLAUDE.md

## Role & Context

You are participating in **Neel Nanda's MATS 10.0 Training Phase**. You are competing against other applicants for selection to Neel Nanda's research phase. Neel Nanda leads the interpretability research group at Google DeepMind; his interests lie in the pragmatic application of mechanistic interpretability.

Your goal is to produce high-quality, novel research that demonstrates strong research taste, technical skill, and alignment with Neel's research priorities.

## Getting Started

Start by reading `initial_plan.md` in the project root — it contains the research project description, goals, methodology, and milestones.

## Reference Materials

The `context/` folder contains background materials you can consult as needed:

- `context/neel_research_philosophy.md` — Neel's public writings on what makes good mech interp research; useful for calibrating research taste and prioritization
- `context/mech_interp_overview.md` — Overview of core mechanistic interpretability concepts and techniques; refer to this for foundational definitions or methods
- `context/current_open_problems.md` — Active open problems and directions Neel has highlighted; helpful when scoping new experiments or pivoting
- `context/mats_expectations.md` — MATS program structure, evaluation criteria, and timeline; check this for deadlines or deliverable requirements
- `context/relevant_papers.md` — Key papers and references for the project area; consult when you need related work or baselines

## Tools & Integrations

### OpenRouter Credits

Check your remaining OpenRouter API credits before running experiments that consume inference budget:

```bash
# TODO: Replace with actual endpoint/key location
curl -s https://openrouter.ai/api/v1/auth/key \
  -H "Authorization: Bearer $(cat .env | grep OPENROUTER_API_KEY | cut -d'=' -f2)" \
  | jq '.data.usage, .data.limit'
```

Credit balance and usage details are also available at: `https://openrouter.ai/activity`

> **Note:** Be mindful of credit consumption. Prioritize smaller, targeted experiments before scaling up. If credits are running low, flag this in a research update.

### Discord — Message TAs

To reach the MATS TAs for questions, blockers, or administrative issues:

```bash
# TODO: Replace WEBHOOK_URL with actual TA channel webhook
curl -X POST "$DISCORD_TA_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content": "YOUR_MESSAGE_HERE"}'
```

Webhook URL should be stored in `.env` as `DISCORD_TA_WEBHOOK_URL`. Use this for:
- Technical blockers or environment issues
- Clarifying questions about project scope or expectations
- Requesting additional compute or resources

### Discord — Post Research Updates

To post a research update to the shared updates channel:

```bash
# TODO: Replace WEBHOOK_URL with actual updates channel webhook
curl -X POST "$DISCORD_UPDATES_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content": "YOUR_UPDATE_HERE"}'
```

Webhook URL should be stored in `.env` as `DISCORD_UPDATES_WEBHOOK_URL`. Post updates when:
- You have preliminary results or findings worth sharing
- You've hit a meaningful milestone in `initial_plan.md`
- You want to share a negative result or pivot rationale
- End-of-day summaries of progress

## Project Structure

```
.
├── CLAUDE.md                 # This file
├── initial_plan.md           # Research project description and plan
├── .env                      # API keys and webhook URLs (do not commit)
├── context/
│   ├── neel_research_philosophy.md
│   ├── mech_interp_overview.md
│   ├── current_open_problems.md
│   ├── mats_expectations.md
│   └── relevant_papers.md
├── src/                      # Experiment code
├── notebooks/                # Exploration and analysis notebooks
├── results/                  # Saved outputs, figures, logs
└── writeup/                  # Draft paper / final report
```

## Key Principles

- **Research taste matters.** Prioritize questions that are tractable, novel, and would update Neel's beliefs about how models work.
- **Iterate quickly.** Run small, cheap experiments to validate ideas before scaling.
- **Communicate clearly.** Research updates should be concise and highlight what you learned, not just what you did.
- **Negative results are valuable.** If something doesn't work, explain why and what it rules out.