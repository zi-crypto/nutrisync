# System Requirements Specification (SRS) for NutriSync

## 1. Introduction
### 1.1 Purpose
The purpose of this document is to define the software requirements for NutriSync, an AI-powered fitness and nutrition coaching platform. This document covers the backend services, frontend application, database schema, and external integrations.

### 1.2 Scope
NutriSync is an application designed to help users track their nutrition, workouts, sleep, and body composition. It provides a chat-based AI coach that can answer questions, log data, and generate visual charts. A specific feature is the "Live Coach", a computer vision-based real-time form checker for exercises like squats, pushups, and pullups.

### 1.3 Definitions, Acronyms, and Abbreviations
- **ADK**: Agent Development Kit (Google ADK used for the AI Agent).
- **1RM**: One Repetition Maximum. Tracker for max weight lifted per exercise.
- **TDEE**: Total Daily Energy Expenditure.
- **BMR**: Basal Metabolic Rate.
- **TSS**: Training Stress Score (represented as Aerobic Training Stress).

## 2. Overall Description
### 2.1 Product Perspective
NutriSync is comprised of a FastAPI-based backend, a vanilla JS/HTML/CSS frontend, and a Supabase PostgreSQL database. It utilizes Google GenAI (specifically `gemini-flash-latest`) for the coaching agent and MediaPipe for in-browser pose detection. The entire application is containerized using Docker Compose and Nginx.

### 2.2 Product Functions
- **User Authentication**: Sign in and sign up functionality via Supabase Auth.
- **Onboarding Wizard**: Multi-step user profile setup including physical stats, goals, experience level, equipment access, granular equipment selection (chip/tag UI with 72+ presets across Gym/Home/Bodyweight tiers), workout schedules, diet typings, allergies, and sport types.
- **AI Chat Coach**: Conversational interface for tailored fitness/nutrition advice. Maintains context of user profile, daily goals, and persistent context notes.
- **Data Logging**: Logging workouts, nutrition, sleep, and body composition directly through chat utilizing AI tool calls.
- **Data Visualization**: AI agent can generate charts (e.g., body weight trends, nutrition breakdown) using QuickChart.io.
- **Live Form Coach**: Real-time webcam analysis detecting exercise reps and form quality using MediaPipe. Supports Squats, Pushups, and Pullups with dynamic range calibration.
- **Macro & Calorie Target Calculation**: Automatic offline calculation of daily calorie, protein, fat, and carb targets based on user physical stats and goals (Mifflin-St Jeor equation).
- **Message Feedback**: Users can like/dislike AI responses and provide mandatory text feedback for model quality tuning.
- **Workout Split Management**: Ability to define and track custom workout splits (e.g., Push/Pull/Legs, Arnold Split, PPL x2, Bro Split, Upper/Lower, Full Body) and retrieve the next scheduled workout, skipping missed days automatically.
- **1RM Tracking**: Ability to track One Repetition Maximum records for various exercises, with auto-update when heavy sets are logged.
- **AI Workout Plan Generation**: The AI agent scientifically generates full workout plans per split day, selecting compound and isolation exercises filtered by user equipment, applying Schoenfeld dose-response volume landmarks (MEV/MAV/MRV) by experience level, Epley-formula load percentages from 1RM records, and goal-appropriate rep ranges. Supports structured supersets (via `superset_group`) for antagonist pairings (critical for Arnold Split).
- **Set-Level Exercise Logging**: Logging individual exercises at the set level (weight × reps × RPE) with automatic PR detection (volume PR and weight PR axes), auto 1RM record updates, and session linking via `workout_log_id`.
- **Progressive Overload Tracking**: Weekly estimated 1RM trends (Epley formula), total volume trends, muscle volume heatmaps (sets per muscle group per week), all-time PR records, and per-exercise history for data-driven training progression.
- **User Health Scoring**: AI agent can invoke an Edge Function (`user-improvement-scorer`) to calculate user improvement health scores on demand.

### 2.3 User Classes and Characteristics
- **Standard User**: A fitness enthusiast or beginner looking to track habits, receive AI coaching, and analyze form via the Live Coach.

### 2.4 Operating Environment
- **Backend**: Python 3 (FastAPI) utilizing google-adk runners and asyncpg.
- **Frontend**: Modern Web Browser (supports WebRTC/Camera for MediaPipe, Canvas API, IndexedDB for caching). Must support SpeechSynthesis API for voice feedback.
- **Database**: Supabase PostgreSQL with PostgREST and Edge Functions.
- **LLM**: Google GenAI (`gemini-flash-latest`).

## 3. Functional Requirements

### FR-USER-01: Authentication
- **Description**: Users must be able to sign up or sign in using their email and password.
- **Flows**: Handled via Supabase JS client on the frontend.
- **Postconditions**: User session is established and JWT token is managed.

### FR-USER-02: Onboarding & Profile Management
- **Description**: New users must complete an onboarding flow capturing details like DOB, height, weight, target weight, fitness goal, experience, equipment, diet type, allergies, sport type, workout split, and 1RM records.
- **Implementation**: Frontend maps to `POST /api/profile` to upsert the `user_profile` (including initializing `starting_weight_kg`), generates target macros, handles custom `workout_splits`/`split_items`, updates `user_1rm_records`, and persists the user's specific `equipment_list` to the `user_equipment` table (delete-and-reinsert pattern). Also logs any provided weight to `body_composition_logs`. Frontend fetches existing profile using `GET /api/profile/{user_id}` which also returns the equipment list. The equipment UI features a chip/tag selector with 72+ preset items organized by category (machines, free weights, cardio, accessories) across three tiers (Gym/Home/Bodyweight), plus support for custom equipment entries via a text input.

### FR-CHAT-01: Conversational AI Coach
- **Description**: Users can chat with an AI coach that responds with text and charts.
- **Context Injection**: The `runners.py` fetches user profile, daily goals, current functional time (Cairo timezone logic), persistent context notes, user equipment list, 1RM records, and the current workout plan in parallel via `ContextService` (6 `asyncio.gather` fetchers), and injects all 7 keys into the ADK session state via the `state_delta` parameter on `run_async()` (the ADK-recommended approach for `DatabaseSessionService` that persists state through the event system rather than direct `session.state` mutation). An `InstructionProvider` callback (`_build_instruction`) reads state keys and substitutes 7 placeholders (`{user_profile}`, `{daily_totals}`, `{current_time}`, `{active_notes}`, `{equipment_list}`, `{one_rm_records}`, `{workout_plan}`) into the system prompt template.
- **Image Support**: Users can upload images which are sent as base64 to the multi-modal GenAI model via data URIs.
- **Concurrency**: Per-user `asyncio.Lock` prevents ADK session state race conditions.

### FR-CHAT-02: Tool-Assisted Data Logging & Querying
- **Description**: The AI agent calls native python tools to interact with the system.
- **Tools Available**: 
  - `body_comp.py` (`log_body_comp`, `get_body_comp_history`): Log and fetch weight/muscle/body fat/resting_hr data. Updating weight also synchronizes `user_profile.weight_kg`.
  - `charts.py` (`draw_chart`): Generate images via QuickChart.
  - `context_notes.py` (`set_status_note`, `clear_status_note`, `get_active_notes_tool`): Manage persistent user notes in `persistent_context` table.
  - `nutrition.py` (`log_meal`, `get_nutrition_history`, `calculate_macros`): Log meals (with a `healthy` flag), fetch nutrition history, estimate macros via LLM knowledge prompt.
  - `sleep.py` (`log_sleep`, `get_sleep_history`): Log sleep including deep/rem/light percentages, duration, wakeups, and sleep_start_time. Applies timezone corrections if sleep crosses midnight.
  - `workouts.py` — Session-level tools:
    - `log_workout`: Log workouts with type, duration, calories, heart rate, TSS. **Now returns `workout_log_id`** (UUID) for linking set-level exercise logs.
    - `get_workout_history`: Fetch workout history for N days.
    - `get_next_scheduled_workout`: Invoke RPC for next scheduled split workout.
  - `workouts.py` — Plan generation tools (NEW):
    - `generate_workout_plan(exercises_json)`: Persists AI-generated plan to `workout_plan_exercises`. Validates 8 required fields. Full-replacement pattern (deletes old → inserts new). Supports `superset_group` for paired exercises.
    - `get_workout_plan(split_day_name?)`: Returns current plan for active split, optionally filtered by day.
  - `workouts.py` — Set-level logging tools (NEW):
    - `log_exercise_sets(exercise_name, sets_json, workout_log_id?)`: Logs individual sets with weight/reps/RPE. Auto PR detection on two axes (volume PR: weight×reps, weight PR: heaviest weight). Auto-updates `user_1rm_records` via `_try_update_1rm` when 1-rep max sets are logged. Case-insensitive canonical name matching.
    - `get_exercise_history(exercise_name, days=30)`: Fetches chronological set history for progressive overload charts (limit 200 rows).
    - `get_progressive_overload_summary(exercise_name?, weeks=8)`: Single-exercise mode calls `get_exercise_progress` RPC for weekly e1RM/volume trends + all-time PRs. All-exercise mode aggregates in-code from recent logs.
  - `web_search.py` (`web_search`): Perform Google searches.
  - `utils.py` (`get_health_scores`): Invokes the `user-improvement-scorer` Edge function on demand. Manages Cairo functional time and functional date offsets (4-hour shift).
  - **Total: 21 tools** registered to the `coach_agent` (up from 16 pre-workout-planning).

### FR-CHAT-03: Message Feedback
- **Description**: Users can provide a thumbs up or thumbs down on an AI message, requiring a minimum 10-character comment.
- **Implementation**: Frontend feedback popup to `/api/chat/feedback` storing/upserting to `message_feedback` table.

### FR-CHAT-04: Client-Side Chat Caching
- **Description**: Chat history is cached locally to reduce DB calls on reload.
- **Implementation**: Frontend uses IndexedDB (`NutriSyncDB_<userId>`) to store messages and fetches messages created `after` the latest cached timestamp via `GET /api/history/{guest_id}?after={timestamp}` limit 50 at a time.

### FR-SYS-01: Health Check & System
- **Description**: Exposes system readiness endpoints and static files.
- **Implementation**: `GET /health` returns `{"status": "healthy"}`. `GET /` serves the main `index.html` interface. `GET /favicon.ico` returns a 204.

### FR-VISION-01: Live Coach (Pose Tracking)
- **Description**: Real-time form checking and rep counting using MediaPipe Pose.
- **Implementation**: 
  - Separated classes for `CameraManager`, `PoseEstimationService`, `UIRenderer`, and `ExerciseEngine` following SOLID principles.
  - Profiles for `SquatProfile`, `PushupProfile`, and `PullProfile`.
  - **Cross-Contamination Filtering**: Prevents misidentifying poses. Squats check horizontal width (`<35%`). Pushups check vertical height (`<50%`). Pullups check hands above shoulders.
  - **Dynamic Range Calibration**: Dynamically calculates arm extension distance during a 3-second hold for pushups (plank) and pullups (straight hang) to adjust depth triggers.
  - `VoiceCoach` provides spoken feedback and debounces spammy non-rep audio.

### FR-DATA-01: Chat History Persistence
- **Description**: The system must persist chat history, including tool call artifacts and base64 chart payloads.
- **Implementation**: Dual-written to `chat_history` by `HistoryService` in backend, saving tool json responses.

### FR-TIME-01: Functional Day Logic
- **Description**: Defines a "functional day" adjusting the cutoff for activities.
- **Implementation**: Configured for the Africa/Cairo timezone (`CAIRO_TZ`). Time between 00:00 and 04:00 is attributed to the previous calendar day across all DB logging and queries via `calculate_log_timestamp()` and `get_today_date_str()`.

### FR-WORKOUT-01: AI Workout Plan Generation
- **Description**: The AI agent generates scientifically-structured workout plans per split day and persists them to the database.
- **Trigger Conditions**: User asks to "create a workout plan", "generate my program", asks "what should I do for [split day]", or has a split but no plan yet.
- **Implementation**:
  - System prompt Protocol #11 defines exercise selection rules: compounds first (multi-joint), then isolations (single-joint), filtered by available equipment, covering ALL muscles for the split day.
  - **Volume Guidelines** based on Schoenfeld dose-response: Beginner 4-8 sets/muscle/week, Intermediate 10-16, Advanced 16-22+. Per session: 3-4 sets compounds, 2-3 isolations.
  - **Rep Ranges by Goal**: Strength (1-6 reps, 80-100% 1RM), Hypertrophy (6-12, 60-80%), Endurance (12-20+, <60%).
  - **Load Calculation**: If 1RM exists, `load_percentage` is set (e.g., 0.75 = 75% of 1RM). If no 1RM, `load_percentage` is null.
  - **Superset Support**: `superset_group` integer column — exercises sharing the same group number on the same day are performed as supersets. Critical for Arnold Split (e.g., Bench Press superset with Barbell Row on Chest & Back day).
  - **Tool**: `generate_workout_plan(exercises_json)` — full replacement of existing plan for the active split. Validates 8 required fields per exercise object.
  - **Split Templates** (frontend, 7 options): PPL, Bro Split, Upper/Lower, Full Body, Arnold Split, PPL x2 (6-Day), Custom.
  - **Split Day Muscle Mapping** (16 entries in `SPLIT_MUSCLE_MAP`): push, pull, legs, upper, lower, full body, chest/back, shoulders/arms, arms, chest, back, shoulders, chest & back (Arnold), shoulders & arms (Arnold), full body a, full body b.

### FR-WORKOUT-02: Set-Level Exercise Logging
- **Description**: Users can log individual exercise sets (weight × reps × RPE) for progressive overload tracking.
- **Implementation**:
  - System prompt Protocol #12 defines the workflow: `log_workout` (capture `workout_log_id`) → `log_exercise_sets` per exercise → report PRs → compare with previous session.
  - **PR Detection**: Two-axis detection per working set — volume PR (`weight_kg × reps` exceeds all-time best) and weight PR (heaviest weight ever logged for that exercise). Warmup sets are excluded.
  - **Auto 1RM Update**: When a 1-rep max set is logged, `_try_update_1rm()` auto-upserts `user_1rm_records` using case-insensitive canonical name matching to avoid duplicate entries from case variance.
  - **Tool**: `log_exercise_sets(exercise_name, sets_json, workout_log_id?)` — `workout_log_id` is Optional (UUID string) allowing standalone logging without a parent session.

### FR-WORKOUT-03: Progressive Overload Tracking
- **Description**: The system provides data-driven progressive overload analysis for individual exercises and across all exercises.
- **Implementation**:
  - System prompt Protocol #13 defines when to use and what to report.
  - **Single Exercise Mode**: Calls `get_exercise_progress` DB function for weekly e1RM trends (Epley: `weight × (1 + reps/30)`), volume trends, total sets, best weight/reps per week, and PR flags grouped by ISO week.
  - **All Exercises Mode**: In-code aggregation from recent exercise logs (limit 500 rows) returning per-exercise totals, bests, and PR counts.
  - **Muscle Volume**: `get_weekly_muscle_volume` DB function joins exercise_logs ↔ workout_plan_exercises via `UNNEST(target_muscles)`, returns completed sets per muscle group per week.
  - **Tools**: `get_exercise_history(exercise_name, days=30)`, `get_progressive_overload_summary(exercise_name?, weeks=8)`.

### FR-API-01: Workout Plan & Progress REST Endpoints
- **Description**: Direct REST API endpoints for frontend consumption of workout plan data and progressive overload metrics (independent of the chat interface).
- **Endpoints**:
  - `GET /api/workout-plan/{user_id}` → `{split_name, plan: [{split_day_name, exercise_order, exercise_name, exercise_type, target_muscles, sets, rep_range_low, rep_range_high, load_percentage, rest_seconds, superset_group, notes}]}`
  - `GET /api/progress/{user_id}?exercise=&weeks=8` → Single exercise: `{exercise, weekly_trend: [{week_start, best_e1rm, total_volume, total_sets, best_weight, best_reps, has_pr}], all_time_pr: {best_weight, best_volume_set, best_e1rm}}`. All exercises: `{exercises: [{exercise, total_sets, total_volume, best_weight, best_volume_set, pr_count, last_date}], total_tracked}`.
  - `GET /api/muscle-volume/{user_id}?week_offset=0` → `{week_offset, muscle_volumes: [{muscle_group, completed_sets}]}`

## 4. Non-Functional Requirements
- **Security**: Row Level Security (RLS) policies enforce isolated tenant access on all user-facing tables (including new `workout_plan_exercises` and `exercise_logs`). Context tools use `current_user_id` ContextVar to prevent prompt injection overriding user ID. The system prompt declares 6 XML context tags as UNTRUSTED DATA (`<user_profile>`, `<daily_totals>`, `<active_notes>`, `<equipment_list>`, `<one_rm_records>`, `<workout_plan>`) with explicit instructions to ignore any embedded prompt injection attempts.
- **Performance**: High parallelization of DB queries in `ContextService` (6 concurrent async fetchers). ADK `DatabaseSessionService` `connect_args` configured with zero statement caching (`prepared_statement_cache_size=0`) for Supavisor compatibility. Exercise log queries use partial indexes (e.g., `WHERE is_warmup = false`) and composite indexes for efficient progressive overload calculations.
- **Reliability**: Exponential Moving Average (EMA) smoothing inside the Live Coach (`MathUtils.calculateEMA`) mitigates camera jitter and false readings from MediaPipe. Graceful handling of QuickChart API timeouts. All new context fetchers include try/except with empty-list fallbacks to prevent single fetcher failures from blocking the entire context pipeline.

## 5. Data Requirements
- **Core Entities**:
  - `user_profile`: Central user state, demographics, current weight, and computed macro targets.
  - `daily_goals`: Tracks daily aggregates (calories, workouts) and target achievements.
  - `chat_history`: Message stream including system/tool calls.
  - `message_feedback`: Thumbs up/down and comments mapped to `message_id`.
  - `workout_splits` & `split_items`: Scheduled workout routines (e.g., Push/Pull/Legs).
  - `user_1rm_records`: Max lifts tracked per exercise.
  - `user_equipment`: Per-user granular equipment inventory (equipment_name, category) with RLS policies and a unique constraint on `(user_id, equipment_name)`.
  - `persistent_context`: Long-term user notes available in agent context.
  - `body_composition_logs`: Tracks weight, muscle kg, bf%, resting HR, and text notes.
  - `nutrition_logs`: Tracks food items, calories, macro splits, and a healthy boolean.
  - `sleep_logs`: Tracks sleep duration, score, times woke up, and sleep stage percentages.
  - `workout_logs`: Tracks exercise type, duration, calories, avg heart rate, hr recovery, and TSS. `id` is UUID and serves as FK target for `exercise_logs.workout_log_id`.
  - `workout_plan_exercises`: AI-prescribed workout plan per split day. Stores exercise name, compound/isolation type, target muscles (text array), sets, rep range (low/high), load %1RM, rest seconds, `superset_group` (int, nullable — exercises sharing same group number on same day are supersetted), and coaching notes. Linked to `workout_splits` via `split_id` FK. Unique index on `(user_id, split_id, split_day_name, exercise_order)`.
  - `exercise_logs`: Set-level performance logging for progressive overload tracking. Stores exercise name, set number, weight_kg, reps, RPE (1-10), warmup flag, PR flag (auto-detected), and auto-computed `volume_load` (GENERATED ALWAYS AS `weight_kg * reps` STORED). Optional UUID FK to `workout_logs(id)` ON DELETE CASCADE for session linking. 7 optimized indexes including partial indexes for PR and weight lookups (`WHERE is_warmup = false`).
  - `scores_snapshots`, `*_improvement_snapshots`: Snapshots of historical user health scores populated by the `user-improvement-scorer` edge function.
  - `sessions`, `app_states`, `user_states`, `events`, `adk_internal_metadata`: Tables managed internally by the Google ADK for agent session state and execution tracking.

## 6. External Interfaces
- **Google GenAI API**: LLM provider for the conversational agent (`google.adk`).
- **Supabase**: PostgreSQL database, Authentication (JWT), and Edge Functions (e.g., `user-improvement-scorer`).
- **Google MediaPipe Pose**: In-browser client-side ML model download via JSDelivr CDN.
- **QuickChart.io API**: External image generation service for Chart.js payloads.
- **Web Speech API**: Browser-native voice synthesis for Live Coach.
