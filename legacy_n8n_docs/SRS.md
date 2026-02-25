# Legacy System Requirements Specification (SRS) for n8n Telegram Bot

> **Note:** This document describes a legacy component of the NutriSync application. The active coaching agent is now built on the FastAPI/Google ADK stack.

## 1. Introduction
### 1.1 Purpose
The purpose of this document is to define the software requirements for the legacy n8n-based NutriSync Telegram Bot. This system acted as an AI-powered fitness and nutrition coaching interface accessible exclusively via the Telegram messaging app.

### 1.2 Scope
The n8n Telegram integration provided an automated coaching layer utilizing Langchain agents within n8n workflows. It handled visual data processing (food images, health app screenshots), scheduled daily reminders, and natural language communication to log fitness telemetry into a Supabase database.

## 2. Overall Description
### 2.1 Product Perspective
The n8n automation engine sat between the Telegram Bot API and the Supabase PostgreSQL database. It utilized OpenRouter and Google Gemini APIs for its language and vision models. The system consisted of a primary orchestrator workflow (`MyHealthBrain.json`) and several distinct tool sub-workflows.

### 2.2 Product Functions
- **Telegram Chat Interface**: Real-time conversational AI coach accessible via a Telegram bot.
- **Automated Scheduled Reminders**: Time-based and logic-based push notifications sent to the user regarding meals, workouts, fasting days, and sleep logging.
- **Vision Parsing**: Ability to interpret food images for macro estimation or health app screenshots for metric extraction.
- **Tool-Assisted Database Interactions**: Agentic capability to query and mutate `nutrition_logs`, `workout_logs`, `sleep_logs`, and `body_composition_logs` using Supabase REST APIs.
- **Historical Analysis**: Deep analysis workflows triggered by user questions regarding personal trends and fatigue.

## 3. Functional Requirements

### FR-BOT-01: Conversational AI Agent
- **Description**: The core `MyHealthBrain` agent processes incoming Telegram messages.
- **Implementation**: Utilizes a Langchain Agent node in n8n. It requires a highly structured System Prompt enforcing specific persona rules (the "Sports Data Scientist"), strict data schema adherence, and specific protocols for fasting days (Mon/Thu). It uses either `OpenRouter (gpt-oss-20b)` or `Gemini` models.

### FR-BOT-02: Sub-Workflow Tools
- **Description**: The agent delegates specific actions to explicit n8n sub-workflows.
- **Tools**:
  - `AddRow`: Ingests JSON data and inserts it into the unified Supabase PostgreSQL database.
  - `DrawChart`: Sends JSON Chart.js configuration to QuickChart.io to generate timeline analysis images.
  - `GetHealthScores`: Fetches composite user health scores representing recent performance vs. baseline.
  - `DeepAnalyze`: A specialized reasoning workflow used for pattern finding and correlating lifestyle metrics.
  - Native n8n Supabase nodes: Used directly inside the main workflow to `GetMany` logs for context generation.

### FR-TIME-01: Proactive Scheduled Reminders
- **Description**: The bot proactively messages the user based on time of day and logging behavior.
- **Implementation**:
  - A Cron trigger fires at specific hours (e.g., 9:00, 12:00, 15:00, 18:00, 21:00).
  - A Code node (`Determine Reminder`) checks the day of the week (identifying fasting days Mon/Thu) and the hour to formulate contextually relevant messages (Morning Check-in, Lunch, Snack/Workout, Dinner/Iftar, Sleep).
  - A logic check ensures the reminder is relevant (e.g., skipping lunch reminders on fasting days) and introduces slight randomness (40% skip chance) to avoid notification fatigue.
  - Queries Supabase to see if previous day logs exist, modifying the message tone if the user has been inactive.

### FR-DATA-01: Functional Day Cutoff
- **Description**: The bot aligns with the user's operational schedule rather than a strict midnight calendar rollover.
- **Implementation**: Messages logged between 00:00 AM and 04:00 AM Cairo Time are forcefully attributed to the previous calendar day (e.g., setting `created_at` to `23:59:59` of the prior day) to accommodate late-night bulking habits.

## 4. Dependencies and Integrations
- **n8n Automation Platform**: The execution environment for the workflows.
- **Supabase REST API**: For database reads/writes (`nutrition_logs`, `sleep_logs`, `workout_logs`, `body_composition_logs`, `daily_goals`).
- **Telegram Bot API**: For receiving and sending messages (`n8n-nodes-base.telegram`).
- **QuickChart.io**: For generating data visualization images.
- **LLM Providers**: OpenRouter (`gpt-oss-20b`) and Google Gemini (`gemini-3-flash-preview`).
