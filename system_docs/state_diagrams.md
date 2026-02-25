# NutriSync State Diagrams

This document contains text-based state diagrams (Mermaid) representing the actual runtime states and workflows within the NutriSync application.

## 1. User Onboarding Flow
Describes the multi-step wizard shown during initial account creation to capture physiological data and goals to formulate the user's macronutrients profile and save 1RM records.

```mermaid
stateDiagram-v2
  [*] --> AuthOverlay

  AuthOverlay --> Signup : User creates account (Email/Password)
  AuthOverlay --> ChatInterface : User logs in (Existing Profile)
  
  Signup --> Step1_Basics : Account created successfully (Session initialized)
  
  state OnboardingWizard {
    Step1_Basics --> Step2_BodyStats : Next (Name entered)
    Step2_BodyStats --> Step3_Goals : Next (Gender/DOB/Height/Weight entered)
    Step3_Goals --> Step4_Logistics : Next (Goal/Experience, Target Weight entered)
    Step4_Logistics --> Step5_Sport : Next (Workout Days/Equipment entered)
    Step5_Sport --> Step6_Nutrition : Next (Activity/Split/1RM Records entered)
    Step6_Nutrition --> ProfileSaving : Finish (Typical Diet/Allergies entered)
    
    %% Users can go back
    Step6_Nutrition --> Step5_Sport : Back
    Step5_Sport --> Step4_Logistics : Back
    Step4_Logistics --> Step3_Goals : Back
    Step3_Goals --> Step2_BodyStats : Back
    Step2_BodyStats --> Step1_Basics : Back
  }

  ProfileSaving --> ChatInterface : API Success (/api/profile upsert)
  ProfileSaving --> OnboardingWizard : API Failure (Validation/Network Error)

  ChatInterface --> [*]
```

## 2. Live Coach Repetition Tracking (MediaPipe)
Describes the tracking logic inside the `ExerciseEngine` and associated Profiles (`SquatProfile`, `PushupProfile`, `PullProfile`) inside `workout_coach.js`. Contains dynamic range calibration and cross-contamination filtering.

```mermaid
stateDiagram-v2
  [*] --> CameraInitialization
  
  CameraInitialization --> AnalyzingStream : Camera stream explicitly started & MediaPipe loaded
  CameraInitialization --> Stopped : Camera denied or unsupported
  
  state AnalyzingStream {
    [*] --> DetectPoseVisibility

    DetectPoseVisibility --> CheckCrossContamination_Pushup : High visibility confidence
    DetectPoseVisibility --> FalsePositiveError : Low confidence (e.g. Tripod object)

    state CrossContaminationFilter {
      CheckCrossContamination_Pushup --> ErrorFeedback : Pullup chosen but wrists dropped massively below shoulders
      CheckCrossContamination_Pushup --> ErrorFeedback : Pushup chosen but vertical distance > 50% screen
      CheckCrossContamination_Pushup --> ErrorFeedback : Squat chosen but horizontal stretch > 35% screen
      CheckCrossContamination_Pushup --> CalibrationPhase : Valid Form for Pushup/Pullup
      CheckCrossContamination_Pushup --> FormTrackingPhase : Valid Form for Squat
    }

    state CalibrationPhase {
        SETUP --> SETUP : Angle/Position held for 3 seconds (Plank or Hang)
        SETUP --> UP : Calibration completed (Dynamic Range max calculated)
    }
    
    state FormTrackingPhase {
        UP --> DESCENDING : Angle dropping past threshold (Pixel distance shrinks)
        DESCENDING --> DOWN : Angle/Distance indicates full contraction or target depth (e.g. Squat Hip Y >= Knee Y)
        DOWN --> ASCENDING : Angle opening
        ASCENDING --> UP : Return to neutral (Rep++ & Voice Feedback)
    }

    CalibrationPhase --> FormTrackingPhase : Switch automatically after setup
    ErrorFeedback --> DetectPoseVisibility : User corrects posture
    FalsePositiveError --> DetectPoseVisibility : Person enters frame
  }

  AnalyzingStream --> Stopped : User clicks "Stop"
  Stopped --> [*]
```

## 3. AI Agent Request State Machine
Describes the backend state machine running within Google's Agent Development Kit (ADK) Runner (`runners.py`) for processing a single user message. Includes parallel context fetching and async locks.

```mermaid
stateDiagram-v2
  [*] --> RequestReceived : POST /api/chat

  RequestReceived --> AcquireLock : Request user-specific Asyncio Lock
  AcquireLock --> ContextLoading : Fetch dynamic context (local_context.py)
  
  state ContextLoading {
     [*] --> FetchProfile
     [*] --> FetchDailyGoals
     [*] --> FetchPersistentContext
     FetchProfile --> MergeContext
     FetchDailyGoals --> MergeContext
     FetchPersistentContext --> MergeContext
  }
  
  MergeContext --> SessionUpdate : Setup/Update ADK session.state with Context
  SessionUpdate --> UserMessageLogged : Dual-write User Message to `chat_history`
  
  UserMessageLogged --> AgentExecution : Dispatch streaming async event generator
  
  state AgentExecution {
    [*] --> GeneratingContent
    GeneratingContent --> ToolCallRequested : LLM decides it needs data
    ToolCallRequested --> ExecutingTool : Runner calls Python Tool (e.g., workouts.py logs entry)
    ExecutingTool --> GeneratingContent : Return tool json result back to LLM context
    GeneratingContent --> FinalResponseReady : event.is_final_response() == True
  }

  AgentExecution --> HistorySaving : Dual-write Model Response to `chat_history`
  
  HistorySaving --> ReturnToFrontend : Release Lock, Return text/chart and message_id
  ReturnToFrontend --> [*] : HTTP 200 OK
```

## 4. Message Feedback Flow
Describes the state of recording user sentiment and feedback on AI messages.

```mermaid
stateDiagram-v2
  [*] --> MessageDisplayed
  MessageDisplayed --> FeedbackModalOpened : User hovers and clicks Trigger Icon
  
  FeedbackModalOpened --> Validation : User selects Like/Dislike, types comment and clicks Submit
  
  Validation --> FeedbackModalOpened : Comment < 10 characters (Error UI updated)
  Validation --> SavingFeedback : Comment >= 10 characters
  
  SavingFeedback --> SuccessState : Upsert to `message_feedback` successful
  SavingFeedback --> ErrorState : Upload failed (Network/DB error)
  
  SuccessState --> [*] : Feedback logged, Modal closes, Trigger color updates
```

## 5. Client-Side Chat History Caching Flow
Describes how the frontend utilizes IndexedDB (`ChatCache`) to minimize backend fetch latency and DB load on page reloads.

```mermaid
stateDiagram-v2
  [*] --> InitializeApp

  InitializeApp --> CheckIndexedDB : Check for existing `NutriSyncDB` entries
  
  CheckIndexedDB --> FetchMessagesActive : Database exists, get latest message timestamp (after)
  CheckIndexedDB --> FetchMessagesAll : Database empty, fetch ALL messages
  
  FetchMessagesActive --> APICallWithAfter : GET /api/history/{guest_id}?after={timestamp}
  FetchMessagesAll --> APICallWithoutAfter : GET /api/history/{guest_id}
  
  APICallWithAfter --> RenderAndStore : Cache new messages in IndexedDB, prepend to UI
  APICallWithoutAfter --> RenderAndStore : Cache all messages in IndexedDB, render all
  
  RenderAndStore --> [*]
```

## 6. Workout Split Progression Logic
Describes the state flow internally managed when requesting the next workout (`get_next_workout` remotely via RPC).

```mermaid
stateDiagram-v2
  [*] --> RequestRpc

  RequestRpc --> CheckActiveSplit : Execute `get_next_workout(user_id)` inside PostgreSQL
  
  CheckActiveSplit --> NoActiveSplit : `is_active = False`
  CheckActiveSplit --> DetermineNextWorkout : `is_active = True`
  
  DetermineNextWorkout --> CalculatePosition : Find last completed workout in `workout_logs` for this split
  
  CalculatePosition --> WrapToBeginning : Last workout was final item in split
  CalculatePosition --> AdvanceIndex : Last workout in middle of split
  CalculatePosition --> FirstItem : No logs found yet
  
  WrapToBeginning --> ReturnNextScheduled : Select 1st split item
  AdvanceIndex --> ReturnNextScheduled : Select next sequential item
  FirstItem --> ReturnNextScheduled : Select 1st split item
  
  ReturnNextScheduled --> [*] : Returns `{next_workout, split_name, position, total, message}`
  NoActiveSplit --> [*] : Returns `{next_workout: null, message}`
```

## 7. Health Score Snapshot Generation Flow
Describes the on-demand generation of user improvement scores. The AI Agent uses the `get_health_scores` tool which delegates the logic to a Supabase Edge Function to compute moving averages and write snapshots.

```mermaid
stateDiagram-v2
  [*] --> AgentInvocation

  AgentInvocation --> EdgeFunctionCall : LLM calls get_health_scores(user_id)
  
  EdgeFunctionCall --> ComputeBaselines : Edge function `user-improvement-scorer` executes
  
  state ComputeBaselines {
      [*] --> AnalyzeNutrition
      [*] --> AnalyzeSleep
      [*] --> AnalyzeWorkouts
      AnalyzeNutrition --> AggregateScores
      AnalyzeSleep --> AggregateScores
      AnalyzeWorkouts --> AggregateScores
  }

  AggregateScores --> WriteSnapshots : Persist flag = True
  AggregateScores --> ReturnToAgent : Persist flag = False

  WriteSnapshots --> ReturnToAgent : Save to `scores_snapshots` and domain improvement tables

  ReturnToAgent --> [*] : JSON result injected into Agent context
```
