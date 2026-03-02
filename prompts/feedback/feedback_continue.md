# Continuation Prompt (Feedback Agent)

The progress file to evaluate is: `memories/finished_{timestamp}.md`

## Your Task

1. Carefully read the entire contents of `memories/finished_{timestamp}.md`. Visit all the files referenced and read them; do not simply rely on the single `finished.md` file.
2. **Critically evaluate:**
   - Clarity of research questions
   - Soundness of experimental design
   - Correctness of implementation decisions
   - Interpretation of results, rigor and falsifiability
   - Whether conclusions are supported by sufficient evidence
3. **Identify:**
   - Conceptual mistakes in experimental design
   - Missing baselines
   - Confounders
   - Overclaims
   - Gaps in methodology
   - Opportunities for stronger experiments
4. **Generate strong new ideas:**
   - Propose novel experiments the worker has not considered
   - Suggest alternative framings of the core question
   - Recommend sharper metrics, stress tests, or adversarial setups
   - Identify new hypotheses

Focus heavily on expanding the project's ambition and insight, not just fixing small issues.

## Output

You must produce a file named `memories/feedback_{timestamp}.md`, which contains all of the above. The timestamp must exactly match the timestamp of the input file.

Structure your feedback as:

1. **High-Level Assessment**
2. **Specific Issues** (both conceptual and implementation-focused)
3. **Possible New Ideas** (at least 5 concrete proposals)
4. **Priority Next Steps**

Your feedback should be constructive but rigorous. Do not rewrite the worker's work. Do not perform the experiments yourself. Focus on improving the worker's reasoning, rigor, and creativity.
