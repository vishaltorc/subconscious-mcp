# Demo session

A worked transcript of an agent using `subconscious-mcp` across two turns.
The first turn misses, the agent computes the answer and writes it back. The
second turn, days later, asks the same thing in different words and hits.

---

## Turn 1. Cache miss: agent computes and remembers

**User:**
> Quick reminder. What's the command to deploy a Next.js app to Vercel in production?

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

## Turn 2. Three days later: paraphrased query, cache hit

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
> Same as before: `vercel login`, then `vercel --prod` from the project root, with env vars configured in Project Settings first.

The agent skipped a full docs lookup. The 0.83 similarity reflects that the
words are different but the meaning matches the stored task.

---

## Turn 3. Checking how well the cache is working

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

A 34% hit rate over the last 100 recalls. About a third of tasks are repeats.

---

## Turn 4. Sonar before committing: `echo`

The agent has a borderline task and wants to sense the territory before
risking a low-threshold recall:

```json
// tool call
{
  "tool": "echo",
  "args": { "task": "Ship a Nuxt app on Vercel", "top_k": 3 }
}
```

```json
// tool result
{
  "count": 47,
  "echoes": [
    {
      "entry_id": "f5c4f0c9-2c33-4d56-9b07-2a3e7b4bcae3",
      "similarity": 0.74,
      "task_text": "How do I deploy a Next.js app to Vercel in production?",
      "stored_at": 1731000000.12,
      "tags": ["vercel", "next.js", "deploy"]
    },
    {
      "entry_id": "0a1b2c3d-...",
      "similarity": 0.41,
      "task_text": "How do I configure a custom domain on Vercel?",
      "stored_at": 1730820000.0,
      "tags": ["vercel", "dns"]
    }
  ]
}
```

No answers came back, only geometry. The agent sees the nearest memory is a
*Next.js* deployment at 0.74 — close, but this task is about *Nuxt*. A
lowered-threshold recall would have absorbed the Next.js answer. The agent
does the work fresh and remembers it as a new entry instead.

---

## Turn 5. Reviewing the cache for drift

```json
// tool call
{ "tool": "drift_report", "args": { "min_hits": 3, "min_spread": 0.08 } }
```

```json
// tool result
{
  "analyzed_recalls": 412,
  "entries_with_hits": 38,
  "candidates": [
    {
      "entry_id": "77aa9b21-...",
      "task_text": "Pull out all digits from the sentence about milk and eggs",
      "still_stored": true,
      "hits": 5,
      "distinct_queries": 4,
      "similarity_min": 0.82,
      "similarity_max": 0.94,
      "similarity_spread": 0.12
    }
  ]
}
```

One entry is serving five hits across four differently-phrased queries
spanning a 0.12 similarity band — the signature of first-fill semantic
drift ("digits" vs "numbers" interpretations colliding). The agent
`forget`s it and lets the family re-fill with more specific entries.

---

## Takeaway

`recall` is cheap (a single embedding + nearest-neighbour lookup). The
threshold is the dial: tighten it (e.g. 0.9) for safety, loosen it (0.65–0.75)
to catch more paraphrases at the cost of occasional false positives. `echo`
lets you sense before you commit, and `drift_report` turns the echo log into
an early-warning system for cached answers that absorbed too much.
