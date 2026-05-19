# Demo session

A worked transcript of an agent using `subconscious-mcp` across two turns.
The first turn misses, the agent computes the answer and writes it back. The
second turn, days later, asks the same thing in different words and hits.

---

## Turn 1 — cache miss, agent computes and remembers

**User:**
> Quick reminder — what's the command to deploy a Next.js app to Vercel in production?

**Agent thinks:** I should check my subconscious before doing the work.

```json
// tool call
{
  "tool": "recall",
  "args": {
    "task": "How do I deploy a Next.js app to Vercel in production?",
    "threshold": 0.85
  }
}
```

```json
// tool result
{
  "hit": false,
  "similarity": 0.0,
  "answer": null,
  "task_text": null,
  "entry_id": null,
  "stored_at": null,
  "tags": []
}
```

The agent now has to work it out the slow way: opens docs, confirms commands,
composes the answer. Once it has the answer, it writes it back to memory:

```json
// tool call
{
  "tool": "remember",
  "args": {
    "task": "How do I deploy a Next.js app to Vercel in production?",
    "answer": "After `vercel login`, run `vercel --prod` from the project root. To configure env vars set them in Project Settings -> Environment Variables before deploying.",
    "tags": ["vercel", "next.js", "deploy"]
  }
}
```

```json
// tool result
{
  "stored": true,
  "entry_id": "f5c4f0c9-2c33-4d56-9b07-2a3e7b4bcae3",
  "embedding_dim": 384
}
```

**Agent (to user):**
> Once you've logged in with `vercel login`, run `vercel --prod` from the project root. Set env vars in Project Settings -> Environment Variables first if your build needs them.

---

## Turn 2 — three days later, paraphrased query, cache hit

**User (a new session, days later):**
> What's the process for shipping a Next.js project on Vercel?

**Agent thinks:** Different wording, same intent. Let me check subconscious.

```json
// tool call
{
  "tool": "recall",
  "args": {
    "task": "What's the process for shipping a Next.js project on Vercel?",
    "threshold": 0.7
  }
}
```

```json
// tool result
{
  "hit": true,
  "similarity": 0.83,
  "answer": "After `vercel login`, run `vercel --prod` from the project root. To configure env vars set them in Project Settings -> Environment Variables before deploying.",
  "task_text": "How do I deploy a Next.js app to Vercel in production?",
  "entry_id": "f5c4f0c9-2c33-4d56-9b07-2a3e7b4bcae3",
  "stored_at": 1731000000.12,
  "tags": ["vercel", "next.js", "deploy"]
}
```

**Agent (to user):**
> Same as before — `vercel login`, then `vercel --prod` from the project root, with env vars configured in Project Settings first.

The agent skipped a full docs lookup. The 0.83 similarity reflects that the
words are different but the meaning matches the stored task.

---

## Turn 3 — checking how well the cache is working

```json
// tool call
{ "tool": "stats", "args": {} }
```

```json
// tool result
{
  "total_entries": 47,
  "last_hit_at": 1731259200.55,
  "hit_rate_last_100": 0.34
}
```

A 34% hit rate over the last 100 recalls — about a third of tasks are repeats.

---

## Takeaway

`recall` is cheap (a single embedding + nearest-neighbour lookup). The
threshold is the dial: tighten it (e.g. 0.9) for safety, loosen it (0.65–0.75)
to catch more paraphrases at the cost of occasional false positives.
