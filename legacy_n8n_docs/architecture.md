# Legacy System Architecture: n8n Telegram Bot

> **Note:** This document describes a legacy component of the NutriSync application. The active coaching agent is now built on the FastAPI/Google ADK stack.

## 1. High-Level Architecture Description
The legacy NutriSync Telegram Bot was completely decoupled from a custom web backend. Instead, it leveraged **n8n** (a workflow automation tool) as the central orchestrator. n8n acted as both the webhook receiver for Telegram events and the execution engine for Langchain-based AI agents. The state and long-term storage were maintained in the shared Supabase PostgreSQL database.

## 2. C4 Diagrams

### 2.1 Context Level
Shows the legacy Telegram bot interacting with the user and external APIs.

```mermaid
C4Context
  title System Context diagram for Legacy n8n Telegram Bot

  Person(user, "User", "Interacts via Telegram mobile/desktop app.")
  System_Ext(telegram, "Telegram", "Messaging platform.")
  
  System(n8n, "n8n Automation Engine", "Executes AI workflows and agent logic.")
  
  System_Ext(supabase, "Supabase API", "PostgreSQL database for telemetry.")
  System_Ext(llm, "LLM Providers", "OpenRouter / Google Gemini APIs.")
  System_Ext(quickchart, "QuickChart.io", "Image generation API for charts.")

  Rel(user, telegram, "Sends text/images", "HTTPS")
  Rel(telegram, n8n, "Webhook Push", "HTTPS")
  Rel(n8n, telegram, "Sends replies/charts", "API")
  Rel(n8n, supabase, "Reads/Writes logs", "REST API")
  Rel(n8n, llm, "Requests generation/tool parsing", "API")
  Rel(n8n, quickchart, "Requests chart image", "API")
```

### 2.2 Container Level
Shows the high-level workflows inside the n8n environment.

```mermaid
C4Container
  title Container diagram for Legacy n8n Telegram Bot

  Person(user, "User", "Telegram User")
  System_Ext(telegram, "Telegram API")
  System_Ext(supabase, "Supabase Database")
  System_Ext(llm, "LLM Providers")

  Container_Boundary(n8n_bound, "n8n Environment") {
    Container(main_flow, "MyHealthBrain Workflow", "n8n", "Main entry point. Receives webhooks, compiles prompts, executes the Langchain Agent.")
    Container(reminders, "Cron Scheduler Component", "n8n Trigger", "Triggers daily at 9,12,15,18,21 to execute proactive reminder logic.")
    
    Container_Boundary(tools_bound, "Sub-Workflows (Tools)") {
        Container(tool_add, "AddRow.json", "n8n", "Generic row inserter for Supabase.")
        Container(tool_chart, "DrawChart.json", "n8n", "Connects to QuickChart.")
        Container(tool_score, "GetHealthScores.json", "n8n", "Fetches composite health queries.")
        Container(tool_deep, "DeepAnalyze.json", "n8n", "Long-form reasoning workflow.")
    }
  }

  Rel(user, telegram, "Chats")
  Rel(telegram, main_flow, "Webhook Trigger")
  Rel(main_flow, llm, "Invokes Langchain Agent")
  
  Rel(main_flow, tool_add, "Sub-Workflow Call")
  Rel(main_flow, tool_chart, "Sub-Workflow Call")
  Rel(main_flow, tool_score, "Sub-Workflow Call")
  
  Rel(tool_add, supabase, "REST POST")
  Rel(main_flow, supabase, "REST GET (Context limits)")
  
  Rel(reminders, main_flow, "Shares execution environment")
  Rel(reminders, telegram, "Sends spontaneous proactive message")
```

## 3. Key Architectural Concepts

### Agent Structure
Unlike a standard code-based agent, this implementation utilized n8n's visual Node-based Langchain integration. The **Agent Node** was provided with:
1.  **Memory**: Windowed chat history buffer.
2.  **Tools**: A mix of direct nodes (e.g., Supabase GetMany nodes mapped specifically as Tools) and Sub-Workflow components (e.g., `AddRow` acting as a generic insertion function).
3.  **Prompting**: A massive, static system prompt string compiled at runtime referencing dynamic variables like current time `{{ $now }}` and `user_profile` targets.

### Scheduled Execution (Cron)
The `MyHealthBrain` workflow contained a disconnected parallel branch specifically for triggers. A Cron trigger fired multiple times a day. Custom JavaScript executed within a Code node determined the contextual relevance of the notification (e.g., adjusting for Ramadan/Fasting logic on Mondays and Thursdays) and conditionally aborted execution before sending the Telegram API request.
