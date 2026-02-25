# Legacy State Diagrams: n8n Telegram Bot

> **Note:** This document describes a legacy component of the NutriSync application. The active coaching agent is now built on the FastAPI/Google ADK stack.

## 1. Telegram Scheduled Reminders Flow
Describes the proactive push notification logic executed inside the `MyHealthBrain.json` n8n workflow using Cron triggers.

```mermaid
stateDiagram-v2
  [*] --> CronTrigger : Initiated at 9, 12, 15, 18, 21 hours
  
  CronTrigger --> DetermineReminder : Code Node Execution
  
  state DetermineReminder {
    [*] --> CheckTimeAndDay
    CheckTimeAndDay --> MorningLogic : Hour 6-10
    CheckTimeAndDay --> LunchLogic : Hour 10-14
    CheckTimeAndDay --> AfternoonLogic : Hour 14-17
    CheckTimeAndDay --> EveningLogic : Hour 17-20
    CheckTimeAndDay --> NightLogic : Hour 20+
    
    MorningLogic --> FastingCheck
    LunchLogic --> FastingCheck
    EveningLogic --> FastingCheck
    
    FastingCheck --> SkipNotification : Is Fasting Day & Lunch Time
    FastingCheck --> SetMessage : Adjust tone for Fasting (e.g. Iftar)
  }
  
  DetermineReminder --> RandomnessCheck : Apply 40% skip chance
  
  RandomnessCheck --> IF_Condition
  
  IF_Condition --> EndWorkflow : shouldSend == False
  IF_Condition --> CheckYesterdayLogs : shouldSend == True
  
  CheckYesterdayLogs --> PrepareFinalMessage : Supabase Query Check
  PrepareFinalMessage --> SendTelegramMessage : Execute Telegram Node (Markdown)
  
  SendTelegramMessage --> [*]
  EndWorkflow --> [*]
```

## 2. n8n `MyHealthBrain` Agent Workflow
Describes the conversational pipeline from receiving a Telegram message to invoking tools and composing a reply.

```mermaid
stateDiagram-v2
  [*] --> TelegramWebhook : Receive Telegram Message / Image
  
  TelegramWebhook --> CompileContext : Inject $now() Cairo Time & Payload
  
  CompileContext --> ExecuteAgent : Pass to Langchain Agent Node
  
  state ExecuteAgent {
    [*] --> AnalyzeInput : LLM Reasoning Phase
    
    AnalyzeInput --> ReturnText : Simple conversational intent
    AnalyzeInput --> DetermineTool : Requires action/data
    
    DetermineTool --> Tool_AddRow : Intent to save data
    DetermineTool --> Tool_GetMany : Intent to read history
    DetermineTool --> Tool_DrawChart : Intent to visualize
    DetermineTool --> Tool_GetHealthScores : Intent to verify status
    
    Tool_AddRow --> WaitSubWorkflow
    Tool_DrawChart --> WaitSubWorkflow
    Tool_GetHealthScores --> WaitSubWorkflow
    
    WaitSubWorkflow --> AnalyzeInput : Sub-workflow returns JSON
    Tool_GetMany --> AnalyzeInput : Native Supabase node returns JSON
  }
  
  ExecuteAgent --> TelegramReply : Formulate final HTML/Markdown text
  
  TelegramReply --> [*] : Message pushed to User via Telegram API
```
