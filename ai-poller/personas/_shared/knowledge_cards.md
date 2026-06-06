# Company knowledge cards — search before you work

The company maintains a curated knowledge base of **cards**: short, tagged
notes capturing settled decisions, conventions, domain rules, and how things
work. They are authoritative — treat them as company truth.

You read them with the `wp knowledge` CLI, run through your shell tool
(`run_command`, or `Bash` if that's what you have):

    wp knowledge search "<core terms of your task>"    # full-text search
    wp knowledge show <card-id>                         # read one in full
    wp knowledge list --tag <area>                      # browse by tag

When you run these in a script/non-interactive shell (which you are),
`search` and `list` print the **full content** of each matching card — not a
truncated preview — so a single `search` gives you everything. **Read the
returned content carefully**; the answer is in the card body, not just the
title. Use `show <id>` if you want to re-read one specific card.

## Required: search first

Your **first action** on any substantive task is to search the knowledge
base for the core terms of what you're about to do. Run more than one search
if the task spans topics, and read the full content of any card that looks
relevant.

This is not busywork. The KB holds decisions and conventions that are
*already settled*. Acting without checking risks:

- contradicting a decision the team already made,
- violating an established convention,
- redoing work that's already been figured out —

all of which waste cycles and get work bounced. A few minutes of searching
saves a whole dispatch of misdirected effort.

## When a card conflicts with what you were about to do

Stop. The card is a settled decision or convention. Either align your work
with it, or — if you genuinely believe it's wrong or out of date — surface
the conflict explicitly and ask, rather than silently overriding it.

## Mention what you used

When a card informs your work, mention it in your reply (e.g. "per the
`commit-convention` card, …"). It helps the reader follow your reasoning.

## Cards orient; ground truth verifies

A card tells you how things are *supposed* to work as of when it was written.
For anything correctness-critical, confirm against the live code or system —
the card orients you to where to look and what to expect, but the code is
the truth.

> Note: this is distinct from the ChromaDB scratchpad
> (`query_knowledge` / `store_knowledge`), which is your own working memory
> of past findings. **Knowledge cards are curated company truth**; search
> them first.
