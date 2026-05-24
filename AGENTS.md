# Codex Instructions

When the user sends `/commit`, interpret it as:

- Inspect `git status` and the relevant diffs.
- Split the working tree into coherent commit groups.
- Stage and commit one coherent group at a time with an appropriate commit message.
- Continue until there are no uncommitted changes left.
- If a change is unclear, unrelated to the recent work, destructive, too large to review safely, or otherwise risky to commit, stop and ask the user how to handle it.
- Report each commit hash and message, then confirm whether the working tree is clean.

When the user sends `/commit all`, stage all non-ignored changes before committing.
