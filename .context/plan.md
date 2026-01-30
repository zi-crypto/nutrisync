### NutriSync 2.0: ADK Migration Strategy Report

**Objective:**
Refactor NutriSync from a visual n8n workflow into a code-first **Python Application** using the **Google Agent Development Kit (ADK)** to achieve <1s latency, strict logical reliability, and robust state management.

#### 1. Core Architecture

* **Framework:** Google ADK (Python SDK) for agent orchestration.
* **Model:** `Gemini 3 Flash` (Vertex AI) for speed and superior tool adherence.
* **Hosting:** Google Cloud Run (Serverless) for auto-scaling and zero-maintenance.
* **Database:** Supabase (Existing) accessed via strictly typed Python functions.


#### 3. Development Roadmap

1. **Skeleton Setup:** Initialize `agent.py` and `requirements.txt` with ADK boilerplate.
2. **Tool Migration:** Port Supabase queries from n8n nodes to `tools/*.py` functions with strict typing.
3. **Prompt Refinement:** Rewrite the System Prompt to separate Persona ("Gym Bro") from Protocol ("Receipts").
4. **Local Testing:** Run the agent locally against the exported chat logs to verify fixes.
5. **Deploy:** Push to Google Cloud Run as a webhook listener for Telegram.