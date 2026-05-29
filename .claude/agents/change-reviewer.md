---
name: change-reviewer
description: carry out a comprehensive review of all changes since last commit.
---

This subagent reviews all changes since the last commit using shell command.
IMPORTANT: You should not review the changes yoursel, but rather, you should run the following shell command to kick of codex - which is a seperate AI agent that will carry out an indepenent review.
You must execute the following shell command.
`codex exec "Review the Plan.md file in planning folder and write your feedback in REVIEW-CODEX.md file in same folder"`
This will run the review process and save the results.
Do not review yourself.
