# NutriSync State Diagrams

This document contains text-based state diagrams (Mermaid) representing the actual runtime states and workflows within the NutriSync application.

## 1. User Onboarding Flow
Describes the multi-step wizard shown during initial account creation to capture physiological data and goals to formulate the user's macronutrients profile, save 1RM records, and persist granular equipment selections.

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
    Step4_Logistics --> Step5_Sport : Next (Workout Days/Equipment Tier/Equipment Chips entered)
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
Describes the backend state machine running within Google's Agent Development Kit (ADK) Runner (`runners.py`) for processing a single user message. Includes 6 parallel context fetchers, 7 state_delta keys, and async locks.

```mermaid
stateDiagram-v2
  [*] --> RequestReceived : POST /api/chat

  RequestReceived --> AcquireLock : Request user-specific Asyncio Lock
  AcquireLock --> ContextLoading : Fetch dynamic context (local_context.py)
  
  state ContextLoading {
     [*] --> FetchProfile
     [*] --> FetchDailyGoals
     [*] --> FetchPersistentContext
     [*] --> FetchUserEquipment
     [*] --> Fetch1RMRecords
     [*] --> FetchWorkoutPlan
     FetchProfile --> MergeContext
     FetchDailyGoals --> MergeContext
     FetchPersistentContext --> MergeContext
     FetchUserEquipment --> MergeContext
     Fetch1RMRecords --> MergeContext
     FetchWorkoutPlan --> MergeContext
  }
  
  MergeContext --> SessionUpdate : Apply state_delta (7 keys) via run_async()
  
  note right of SessionUpdate
    Keys: user_profile, daily_totals,
    current_time, active_notes,
    equipment_list, one_rm_records,
    workout_plan
  end note
  
  SessionUpdate --> UserMessageLogged : Dual-write User Message to chat_history
  
  UserMessageLogged --> AgentExecution : Dispatch streaming async event generator
  
  state AgentExecution {
    [*] --> GeneratingContent
    GeneratingContent --> ToolCallRequested : LLM decides it needs data
    ToolCallRequested --> ExecutingTool : Runner calls Python Tool (1 of 21 tools)
    ExecutingTool --> GeneratingContent : Return tool json result back to LLM context
    GeneratingContent --> FinalResponseReady : event.is_final_response() == True
  }

  AgentExecution --> HistorySaving : Dual-write Model Response to chat_history
  
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

## 8. AI Workout Plan Generation Flow
Describes the state machine when the AI agent generates a structured workout plan. The agent selects exercises based on user context (profile, equipment, 1RM, split) and calls `generate_workout_plan` to persist the plan.

```mermaid
stateDiagram-v2
  [*] --> TriggerDetected

  TriggerDetected --> ContextGathered : Agent reads session state (profile, equipment, 1RM, active split)
  
  state ExerciseSelection {
    [*] --> IterateSplitDays : For each day in active split
    
    IterateSplitDays --> LookupMuscles : Map day name via SPLIT_MUSCLE_MAP (16 types)
    LookupMuscles --> SelectCompounds : Compounds FIRST (multi-joint)
    SelectCompounds --> SelectIsolations : Fill volume gaps with isolations
    SelectIsolations --> FilterByEquipment : Only exercises user can do with their equipment
    FilterByEquipment --> SetVolume : Apply Schoenfeld volume (MEV/MAV/MRV by experience)
    SetVolume --> SetRepRange : Apply goal-based rep range + load %1RM
    SetRepRange --> AssignSupersets : Group antagonist pairs (superset_group) if Arnold Split
    AssignSupersets --> SetRestPeriods : 120-180s compounds, 60-90s isolations
    SetRestPeriods --> IterateSplitDays : Next day
    SetRestPeriods --> BuildJSON : All days complete
  }
  
  ContextGathered --> ExerciseSelection
  
  BuildJSON --> CallTool : generate_workout_plan(exercises_json)
  
  state PersistPlan {
    [*] --> FetchActiveSplit : Get active split_id
    FetchActiveSplit --> DeleteOldPlan : Remove existing plan for this split
    DeleteOldPlan --> ValidateFields : Check 8 required fields per exercise
    ValidateFields --> BatchInsert : Insert all rows to workout_plan_exercises
    BatchInsert --> [*] : Return summary (exercises per day)
  }

  CallTool --> PersistPlan
  PersistPlan --> DisplayPlan : Agent presents plan to user
  DisplayPlan --> [*]
```

## 9. Set-Level Exercise Logging & PR Detection Flow
Describes the state machine when a user reports what they actually did in a workout. Includes the dual-tool workflow (session-level `log_workout` → set-level `log_exercise_sets`), PR detection, and auto 1RM updates.

```mermaid
stateDiagram-v2
  [*] --> UserReportsWorkout : "I did bench press 80kg for 10, 9, 8"

  UserReportsWorkout --> LogSession : Agent calls log_workout(type, duration, calories)
  LogSession --> CaptureSessionId : Returns workout_log_id (UUID)
  
  CaptureSessionId --> LogExerciseSets : For each exercise reported
  
  state LogExerciseSets {
    [*] --> ParseSetsJSON : Parse [{weight_kg, reps, rpe?, is_warmup?, notes?}]
    ParseSetsJSON --> FetchExistingPRs : Query best volume_load + best weight_kg from exercise_logs
    
    FetchExistingPRs --> ProcessEachSet : Iterate sets
    
    state ProcessEachSet {
      [*] --> CheckWarmup
      CheckWarmup --> SkipPR : is_warmup = true
      CheckWarmup --> CheckVolumePR : is_warmup = false (working set)
      
      CheckVolumePR --> FlagVolumePR : weight × reps > existing best volume
      CheckVolumePR --> CheckWeightPR : Not a volume PR
      CheckWeightPR --> FlagWeightPR : weight > existing best weight
      CheckWeightPR --> NoNewPR : Not a weight PR either
      
      FlagVolumePR --> AccumulateStats
      FlagWeightPR --> AccumulateStats
      NoNewPR --> AccumulateStats
      SkipPR --> AccumulateStats
      AccumulateStats --> [*] : Next set
    }
    
    ProcessEachSet --> BatchInsertSets : Insert all rows to exercise_logs (linked via workout_log_id)
    BatchInsertSets --> Check1RM : Any 1-rep max working sets?
    Check1RM --> AutoUpdate1RM : Yes — _try_update_1rm (case-insensitive canonical upsert)
    Check1RM --> BuildResponse : No
    AutoUpdate1RM --> BuildResponse
    BuildResponse --> [*] : Return volume summary + PR flags
  }
  
  LogExerciseSets --> CompareHistory : Agent calls get_exercise_history for comparison
  CompareHistory --> CelebratePRs : Any PRs? Celebrate!
  CompareHistory --> ReportTrend : Show improvement/regression vs last session
  CelebratePRs --> [*]
  ReportTrend --> [*]
```

## 10. Progressive Overload Query Flow
Describes the two query modes for progressive overload analysis: single-exercise (uses DB function) and all-exercises (in-code aggregation).

```mermaid
stateDiagram-v2
  [*] --> QueryRequested : User asks "Am I getting stronger?"

  QueryRequested --> CheckMode : get_progressive_overload_summary(exercise_name?, weeks)
  
  CheckMode --> SingleExerciseMode : exercise_name provided
  CheckMode --> AllExercisesMode : exercise_name omitted
  
  state SingleExerciseMode {
    [*] --> CallRPC : get_exercise_progress(user_id, exercise, weeks)
    CallRPC --> WeeklyTrend : Returns weekly e1RM, volume, sets, PRs
    WeeklyTrend --> FetchAllTimePRs : Best weight, best volume_load, best e1RM
    FetchAllTimePRs --> FetchRecentSession : Latest dated sets for this exercise
    FetchRecentSession --> [*] : Return {exercise, weekly_trend, all_time_pr, pr_history, recent_session}
  }
  
  state AllExercisesMode {
    [*] --> QueryRecentLogs : exercise_logs WHERE log_date >= cutoff (limit 500)
    QueryRecentLogs --> GroupByExercise : Aggregate per exercise name
    GroupByExercise --> [*] : Return {exercises: [{total_sets, total_volume, best_weight, pr_count, last_date}]}
  }
  
  SingleExerciseMode --> VisualizeData : Agent calls draw_chart (e1RM trend line, neon palette)
  AllExercisesMode --> ReportSummary : Agent presents table of all exercises
  
  VisualizeData --> [*]
  ReportSummary --> [*]
```

## 11. Muscle Volume Heatmap Query Flow
Describes how the weekly muscle volume data is computed by joining exercise logs with the workout plan to map exercises → target muscles.

```mermaid
stateDiagram-v2
  [*] --> QueryRequested : GET /api/muscle-volume/{user_id}?week_offset=0

  QueryRequested --> CallRPC : get_weekly_muscle_volume(user_id, week_offset)
  
  state DBFunction {
    [*] --> CalculateWeekWindow : week_start = date_trunc(CURRENT_DATE + offset)
    CalculateWeekWindow --> JoinTables : exercise_logs INNER JOIN workout_plan_exercises
    
    note right of JoinTables
      Join ON user_id + LOWER(exercise_name)
      Filter: is_warmup = false, log_date in week window
    end note
    
    JoinTables --> UnnestMuscles : UNNEST(wpe.target_muscles) as muscle_group
    UnnestMuscles --> CountSets : GROUP BY muscle_group, COUNT(exercise_log.id)
    CountSets --> [*] : Return [{muscle_group, completed_sets}]
  }
  
  CallRPC --> DBFunction
  DBFunction --> ReturnResponse : {week_offset, muscle_volumes: [...]}
  ReturnResponse --> [*]
```
