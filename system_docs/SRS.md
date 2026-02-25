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
- **Workout Split Management**: Ability to define and track custom workout splits (e.g., Push/Pull/Legs) and retrieve the next scheduled workout, skipping missed days automatically.
- **1RM Tracking**: Ability to track One Repetition Maximum records for various exercises.
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
- **Context Injection**: The `runners.py` fetches user profile, daily goals, current functional time (Cairo timezone logic), persistent context notes, and user equipment list in parallel via `ContextService` (`asyncio.gather`), and injects them into the ADK session state via the `state_delta` parameter on `run_async()` (the ADK-recommended approach for `DatabaseSessionService` that persists state through the event system rather than direct `session.state` mutation). An `InstructionProvider` callback (`_build_instruction`) reads state keys and substitutes them into the system prompt template.
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
  - `workouts.py` (`log_workout`, `get_workout_history`, `get_next_scheduled_workout`): Log workouts, fetch history, and invoke RPC for next scheduled split workout.
  - `web_search.py` (`web_search`): Perform Google searches.
  - `utils.py` (`get_health_scores`): Invokes the `user-improvement-scorer` Edge function on demand. Manages Cairo functional time and functional date offsets (4-hour shift).

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

## 4. Non-Functional Requirements
- **Security**: Row Level Security (RLS) policies enforce isolated tenant access. Context tools use `current_user_id` ContextVar to prevent prompt injection overriding user ID.
- **Performance**: High parallelization of DB queries in `ContextService`. ADK `DatabaseSessionService` `connect_args` configured with zero statement caching (`prepared_statement_cache_size=0`) for Supavisor compatibility.
- **Reliability**: Exponential Moving Average (EMA) smoothing inside the Live Coach (`MathUtils.calculateEMA`) mitigates camera jitter and false readings from MediaPipe. Graceful handling of QuickChart API timeouts.

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
  - `workout_logs`: Tracks exercise type, duration, calories, avg heart rate, hr recovery, and TSS.
  - `scores_snapshots`, `*_improvement_snapshots`: Snapshots of historical user health scores populated by the `user-improvement-scorer` edge function.
  - `sessions`, `app_states`, `user_states`, `events`, `adk_internal_metadata`: Tables managed internally by the Google ADK for agent session state and execution tracking.

## 6. External Interfaces
- **Google GenAI API**: LLM provider for the conversational agent (`google.adk`).
- **Supabase**: PostgreSQL database, Authentication (JWT), and Edge Functions (e.g., `user-improvement-scorer`).
- **Google MediaPipe Pose**: In-browser client-side ML model download via JSDelivr CDN.
- **QuickChart.io API**: External image generation service for Chart.js payloads.
- **Web Speech API**: Browser-native voice synthesis for Live Coach.
