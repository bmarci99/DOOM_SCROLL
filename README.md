
# 🛰️ Doomscrolling 2.0

> Daily high-signal intelligence for RL, AI agents, and ML systems.
> Fully automated. Zero LLMs. Pure signal.

---

![Python](https://img.shields.io/badge/Python-3.10-blue)
![automation](https://img.shields.io/badge/GitHub%20Actions-Enabled-brightgreen)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
![no-LLM](https://img.shields.io/badge/LLM-Free-purple)

---

## ⚡ What It Does

AI Research Radar runs daily and:

* 📡 Pulls new arXiv papers (cs.LG, cs.AI, cs.MA, stat.ML…)
* 🔥 Tracks high-activity Hacker News posts
* 📰 Ingests curated RSS feeds
* ⏱ Applies per-source time windows
* 📊 Ranks by recency + activity
* 📧 Sends a clean daily email digest
* 🗂 Exports structured JSON for dashboards

No summarization models. No hallucinations. Just structured intelligence.

---

## 🧠 Why

Instead of doom-scrolling:

* Know what matters in RL
* Track multi-agent systems
* Monitor ML systems advances
* Spot infrastructure shifts early

Delivered every morning.

---

## 🏗 Architecture

```text
arXiv      Hacker News      RSS
   │             │            │
   └────── Ingestion Layer ───┘
               │
         Time Windows
               │
         HN Enrichment
               │
            Scoring
               │
        Topic Tagging
               │
        Markdown Render
               │
           Email Push
```

Cloud scheduled via GitHub Actions.

---

## ☁️ Automation

Runs daily via GitHub cron:

```yaml
schedule:
  - cron: "0 7 * * *"
```

Add secrets:

* `GMAIL_ADDRESS`
* `GMAIL_APP_PASSWORD`
* `DIGEST_TO_EMAIL`

---

