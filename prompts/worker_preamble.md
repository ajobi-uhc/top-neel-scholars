IMPORTANT: Never ask for user input or clarification. Make your best judgment on any decision and proceed.

When you believe you are done with the current iteration, write a timestamped progress file at `checkpoints/progress_<timestamp>.md` (create the `checkpoints/` directory if it doesn't exist). Use the format `YYYY-MM-DD_HH-MM-SS` for the timestamp.

**CRITICAL: Your progress file is the ONLY memory the next worker has.** Each worker starts completely fresh — there is no conversation history carried over. The progress report must be fully self-contained: anyone reading it with no prior context should be able to pick up exactly where you left off.

This file should contain three sections:

## Context Compaction
A complete summary of everything needed to continue this project — key facts, architecture decisions, constraints discovered, file locations, environment details, and any context that would be lost without this section. Be thorough: if it's not here, the next worker won't know it.

## Work Overview
What you accomplished this iteration:
- What files you changed and why
- Key decisions or trade-offs made
- Any issues encountered
- Current state of tests, builds, or experiments

## Planned Next Steps
What should be done next, in priority order. Be specific — include file paths, function names, and concrete actions.

Then output DONE on its own line.
