# System Requirements Specification (SRS) for NutriSync

## 1. Introduction
### 1.1 Purpose
The purpose of this document is to define the software requirements for NutriSync, an AI-powered fitness and nutrition coaching platform. This document covers the backend services, frontend application, database schema, and external integrations.

### 1.2 Scope
NutriSync is an application designed to help users track their nutrition, workouts, sleep, and body composition. It provides a chat-based AI coach that can answer questions, log data, and generate visual charts. A specific feature is the "Live Coach", a computer vision-based real-time form checker for exercises like squats, pushups, and pullups. The application supports **full internationalization (i18n)** with English and Arabic (Egyptian dialect) including Right-to-Left (RTL) rendering.

### 1.3 Definitions, Acronyms, and Abbreviations
- **ADK**: Agent Development Kit (Google ADK used for the AI Agent).
- **1RM**: One Repetition Maximum. Tracker for max weight lifted per exercise.
- **TDEE**: Total Daily Energy Expenditure.
- **BMR**: Basal Metabolic Rate.
- **TSS**: Training Stress Score (represented as Aerobic Training Stress).
- **i18n**: Internationalization — the system for multi-language support.
- **RTL**: Right-to-Left — text direction for Arabic and similar languages.

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
- **Internationalization (i18n) & RTL**: Full Arabic (Egyptian dialect) support with Right-to-Left rendering. Client-side i18n engine with 311 locale keys per language, language-aware AI prompts, CSS logical properties, RTL Canvas rendering, and Chart.js RTL support. Language preference persisted in database and localStorage.
- **Exercise Video Demos**: AI agent cites working YouTube video links when discussing exercises, using `web_search` with `site:youtube.com` queries. Exercise names serve as clickable hyperlinks opening in new tabs.
- **Custom Coach Naming**: Users can name their AI coach during onboarding (default: "NutriSync"). The coach name is injected into the system prompt via `{coach_name}` placeholder.

### 2.3 User Classes and Characteristics
- **Standard User**: A fitness enthusiast or beginner looking to track habits, receive AI coaching, and analyze form via the Live Coach.

### 2.4 Operating Environment
- **Backend**: Python 3.11 (FastAPI) utilizing google-adk runners and asyncpg. Timezone defaults to `Europe/Berlin`.
- **Frontend**: Modern Web Browser (supports WebRTC/Camera for MediaPipe, Canvas API, IndexedDB for caching, Chart.js for data visualization). Must support SpeechSynthesis API for voice feedback. Must support CSS logical properties and `dir` attribute for RTL layouts.
- **Database**: Supabase PostgreSQL with PostgREST, Supavisor connection pooler, and Edge Functions.
- **LLM**: Google GenAI (`gemini-flash-latest`).
- **Web Search**: Tavily API (via `tavily-python` SDK) for internet searches.
- **Analytics**: PostHog EU Cloud (`posthog` Python SDK + JS SDK).
- **Deployment**: Docker Compose with 4 services — `nutrisync` (application), `nginx-proxy` (reverse proxy + SSL termination), `acme-companion` (automated Let's Encrypt certificate provisioning), and `watchtower` (auto-update every 300 s). Served at `bot.ziadamer.com`.

## 3. Functional Requirements

### FR-USER-01: Authentication
- **Description**: Users must be able to sign up or sign in using their email and password.
- **Flows**: Handled via Supabase JS client on the frontend.
- **Postconditions**: User session is established and JWT token is managed.

### FR-USER-02: Onboarding & Profile Management
- **Description**: New users must complete an onboarding flow capturing details like DOB, height, weight, target weight, fitness goal, experience, equipment, diet type, allergies, sport type, workout split, 1RM records, and coach name.
- **Implementation**: Frontend maps to `POST /api/profile` to upsert the `user_profile` (including initializing `starting_weight_kg` and persisting `coach_name` and `language`), generates target macros, handles custom `workout_splits`/`split_items` via an **upsert pattern** (reuses the existing active split UUID if one exists, only creates a new split on first-time onboarding — this preserves the `workout_plan_exercises.split_id` FK and prevents orphaned plan data; `split_items` are replaced via delete-and-reinsert since no other tables FK to them), updates `user_1rm_records`, and persists the user's specific `equipment_list` to the `user_equipment` table (delete-and-reinsert pattern). Also logs any provided weight to `body_composition_logs`. Frontend fetches existing profile using `GET /api/profile/{user_id}` which also returns the equipment list. The equipment UI features a chip/tag selector with 72+ preset items organized by category (machines, free weights, cardio, accessories) across three tiers (Gym/Home/Bodyweight), plus support for custom equipment entries via a text input.

### FR-CHAT-01: Conversational AI Coach
- **Description**: Users can chat with an AI coach that responds with text and charts.
- **Context Injection**: The `runners.py` fetches user profile, daily goals, current functional time (Cairo timezone logic), persistent context notes, user equipment list, 1RM records, split structure, and the current workout plan in parallel via `ContextService` (**7 `asyncio.gather` fetchers**), and injects all **10 keys** into the ADK session state via the `state_delta` parameter on `run_async()` (the ADK-recommended approach for `DatabaseSessionService` that persists state through the event system rather than direct `session.state` mutation). An `InstructionProvider` callback (`_build_instruction`) reads the `language` state key to select the correct prompt template (English or Arabic), then substitutes **9 placeholders** (`{user_profile}`, `{daily_totals}`, `{current_time}`, `{active_notes}`, `{equipment_list}`, `{one_rm_records}`, `{split_structure}`, `{workout_plan}`, `{coach_name}`) into the system prompt template.
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
  - `web_search.py` (`web_search`): Perform live internet searches via the **Tavily API** (`TavilyClient`). Returns AI-generated answer summaries and source URLs. Used for exercise video demos (YouTube), branded food lookups, and real-time fact verification. Requires `TAVILY_API_KEY` environment variable.
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

### FR-VISION-02: Live Coach Exercise Logging API
- **Description**: The Live Coach frontend can persist completed exercise sets (tracked via MediaPipe pose detection) to the backend database, bypassing the chat interface.
- **Endpoint**: `POST /api/live-coach/log`
- **Request Model** (`LiveCoachLogRequest`):
  - `user_id` (str, required): Supabase user UUID.
  - `exercise_key` (str, required): Exercise identifier — one of `"squat"`, `"pushup"`, `"pullup"` (mapped via `LIVE_COACH_EXERCISE_MAP` to display names: `"Bodyweight Squats"`, `"Push-ups"`, `"Pull-ups"`).
  - `reps` (int, required): Number of repetitions completed. Must be > 0.
  - `weight_kg` (float, optional): Weight used. If null, falls back to the user's `weight_kg` from `user_profile` (bodyweight exercises).
- **Implementation** (in `main.py`):
  - Resolves the next `set_number` for the exercise on the current functional day (auto-incrementing).
  - **PR Detection**: Two-axis PR check — volume PR (`weight_kg × reps` exceeds all-time best `volume_load`) and weight PR (`weight_kg` exceeds all-time best). Both exclude warmup sets.
  - Inserts into `exercise_logs` with `notes = "Logged via Live Coach"`.
  - Returns `{success, exercise_name, set_number, reps, weight_kg, volume_load, is_pr, pr_type}`.
  - Tracks `api_live_coach_logged` event in PostHog with exercise, reps, weight, set number, PR metadata.
- **Validation**: Returns HTTP 400 (`"error.reps_zero"`) if `reps <= 0`.

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
### FR-WORKOUT-03: Progressive Overload Tracking
- **Description**: The system provides data-driven progressive overload analysis for individual exercises and across all exercises via a standalone `WorkoutTracker` UI and AI tools.
- **Implementation**:
  - System prompt Protocol #13 defines when to use and what to report contextually in chat.
  - **Frontend UI (`WorkoutTracker` overlay)**: Provides three persistent tabs:
    - **Plan Tab**: Displays the parsed, active split workout plan grouped by day tabs. Renders superset badges and calculated total sets per muscle group.
    - **Progress Tab**: Uses `Chart.js` to render Estimated 1RM Trends and Volume Load Trends. Shows session history pills and all-time PR badges. Populates a dropdown to filter by specific exercises.
    - **Volume Tab**: Renders a Weekly Muscle Volume Heatmap with progress bars, comparing completed sets against weekly targets derived from the user's experience level (e.g. 16 sets/week for chest, 12 for triceps). Allows navigation back in time week-by-week.
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

### FR-I18N-01: Internationalization & RTL Support
- **Description**: The application must support multiple UI languages with full Right-to-Left (RTL) layout for Arabic.
- **Supported Languages**: English (`en`), Arabic — Egyptian dialect (`ar`).
- **Frontend Implementation**:
  - **i18n Engine** (`i18n.js`): Loads locale JSON files from `/static/locales/`. Public API: `t(key, params)`, `setLang(lang)`, `getLang()`, `getDir()`, `onI18nReady(cb)`. Persists language in `localStorage` (`nutrisync_lang`). Detects initial language from localStorage → browser → default. Always loads English as fallback. On switch: reloads locale, sets `<html dir>` and `<html lang>`, scans DOM for `data-i18n*` attributes, dispatches `languagechange` CustomEvent.
  - **Locale Files** (`locales/en.json`, `locales/ar.json`): 311 keys each, flat key-value format. Namespaces: header, chat, auth, coach (UI/feedback/instruction/HUD/labels), tracker (plan/progress/volume/PRs), wizard (all 5 steps), feedback, profile, equipment categories, muscles, splits, units/time, language picker, error codes.
  - **String Externalization**: `script.js` uses ~95+ `t()` calls; `workout_coach.js` uses ~30 `t()` calls. No hardcoded user-facing strings remain in JavaScript.
  - **CSS Logical Properties**: 19 physical→logical conversions in `style.css` (e.g., `margin-left` → `margin-inline-start`). `[dir=rtl]` selector for font-family override (Cairo) and form control background-position flip.
  - **Canvas RTL**: `workout_coach.js` `drawOverlayText` sets `ctx.direction` based on `getDir()`, adjusts `textAlign`, uses Cairo font for RTL, mirrors X positioning.
  - **Chart.js RTL**: Conditional `x.reverse`, `y.position: 'right'`, `tooltip.rtl`, `legend.rtl` when `getDir() === 'rtl'`.
  - **Language Switcher**: `<select id="lang-switcher">` in header, bound to `setLang()`.
- **Backend Implementation**:
  - **Language-Aware Prompts**: `runners.py` caches prompts in `_PROMPT_TEMPLATES: Dict[str, str]`. `_load_prompt_template(lang)` loads `prompts/system.md` (English) or `prompts/system_{lang}.md` (e.g., `system_ar.md` for Arabic) with English fallback. `_build_instruction` reads `ctx.state.get("language", "en")` to select the template.
  - **Arabic System Prompt** (`prompts/system_ar.md`): Full Arabic (Egyptian dialect) translation of `system.md` with identical 17 protocols and 9 template placeholders. Instructs AI to always respond in Arabic.
  - **API Language Fields**: `ChatRequest.language` (default `"en"`) propagated to `process_message()`. `ProfileRequest.language` (default `"en"`) saved to `user_profiles.language`.
  - **Error Code i18n**: `HTTPException` detail strings use i18n key codes (e.g., `"error.reps_zero"`) instead of English text, enabling frontend `t()` mapping.
- **Database**: Migration `014_add_language.sql` adds `language TEXT NOT NULL DEFAULT 'en'` to `user_profiles`.

### FR-I18N-02: Exercise Video Demo Protocol
- **Description**: The AI agent must cite working YouTube video demonstration links when discussing exercises in workout plans or form guidance.
- **Implementation** (System Prompt Protocol #17):
  - Agent uses `web_search` tool with `site:youtube.com {exercise_name} form tutorial` queries.
  - Exercise name is rendered as the clickable hyperlink: `<a href="..." target="_blank"><b>Exercise Name</b></a>`.
  - Multiple exercises are batched into a single search when possible.
  - **Fallback**: Agent never hallucinate URLs — if search returns no results, omits the link gracefully.
  - **Quality Filter**: Prioritizes reputable fitness channels (Jeff Nippard, Renaissance Periodization, AthleanX, etc.).

### FR-ANALYTICS-01: Product Analytics (PostHog)
- **Description**: Dual-layer analytics capturing both frontend user interactions and backend system metrics for product insight.
- **Configuration**:
  - `POSTHOG_API_KEY`: Shared project API key (used by both frontend Jinja2 injection and backend Python SDK).
  - `POSTHOG_HOST`: PostHog instance URL (default: `https://eu.i.posthog.com`).
- **Frontend Events** (JS SDK via `script.js`):
  - `user_signed_up` / `user_signed_in` — auth funnel.
  - `chat_message_sent` (`message_length`, `has_image`) / `chat_message_error` (`error`) — chat usage.
  - `message_feedback_submitted` (`feedback_value`, `message_id`) — response quality signal.
  - `live_coach_started` / `live_coach_stopped` (`exercise`, `duration_seconds`) / `live_coach_exercise_logged` (`exercise`, `reps`, `good_form_pct`) — vision coach engagement.
  - `onboarding_step_viewed` (`step`, `total_steps`) / `onboarding_completed` — wizard funnel.
  - `profile_settings_opened` / `workout_tracker_opened` / `workout_tracker_tab_viewed` (`tab`) — feature engagement.
- **Backend Events** (Python SDK via `services/analytics.py`):
  - `api_chat_processed` (`message_length`, `has_image`, `response_length`, `has_chart`, `latency_ms`) — API performance.
  - `api_feedback_submitted` (`feedback_value`, `message_id`) — server-side feedback confirmation.
  - `api_profile_saved` — profile persistence.
  - `api_live_coach_logged` — live coach data saved.
  - `ai_tool_called` (`tool_name`, `has_args`) — per-tool invocation tracking.
  - `ai_agent_run_completed` (`context_load_ms`, `total_duration_ms`, `tool_call_count`, `tools_used`, `has_image_input`, `has_chart_output`, `response_length`) — full agent run metrics.
- **Adblocker Bypass**: Frontend SDK configured with `api_host: '/ingest'`. Nginx proxies `/ingest/*` to PostHog EU cloud via server-level `location` blocks in `nginx/vhost.d/bot.ziadamer.com`, making events appear as first-party requests.
- **Resilience**: Backend analytics never block or crash the application — all captures wrapped in try/except. Missing API key gracefully disables analytics. Frontend checks `typeof posthog !== 'undefined'` before every capture.

## 4. Non-Functional Requirements
- **Security**: Row Level Security (RLS) policies enforce isolated tenant access on all user-facing tables (including new `workout_plan_exercises` and `exercise_logs`). Context tools use `current_user_id` ContextVar to prevent prompt injection overriding user ID. The system prompt declares **7** XML context tags as UNTRUSTED DATA (`<user_profile>`, `<daily_totals>`, `<active_notes>`, `<equipment_list>`, `<one_rm_records>`, `<split_structure>`, `<workout_plan>`) with explicit instructions to ignore any embedded prompt injection attempts. The backend uses the Supabase `service_role` key which bypasses RLS and connects from server-side only; API keys are never exposed to the frontend.
- **Model Configuration**: The AI agent uses `temperature=0.2` (`generate_content_config` in `agents/coach.py`) to ensure deterministic, reliable coaching responses.
- **Performance**: High parallelization of DB queries in `ContextService` (7 concurrent async fetchers). ADK `DatabaseSessionService` `connect_args` configured with zero statement caching (`prepared_statement_cache_size=0`) for Supavisor compatibility. Exercise log queries use partial indexes (e.g., `WHERE is_warmup = false`) and composite indexes for efficient progressive overload calculations.
- **Reliability**: Exponential Moving Average (EMA) smoothing inside the Live Coach (`MathUtils.calculateEMA`) mitigates camera jitter and false readings from MediaPipe. Graceful handling of QuickChart API timeouts. All new context fetchers include try/except with empty-list fallbacks to prevent single fetcher failures from blocking the entire context pipeline.
- **Internationalization**: Full i18n coverage across frontend (311 locale keys, CSS logical properties, RTL Canvas, Chart.js RTL) and backend (language-aware prompts, i18n error codes). Language fallback to English is guaranteed at every layer (locale loading, prompt loading, error display). Language preference persisted in both `localStorage` (frontend) and `user_profiles.language` (database).

## 5. Data Requirements
- **Core Entities**:
  - `user_profile`: Central user state, demographics, current weight, computed macro targets, `coach_name` (custom AI coach name, default `'NutriSync'`), and `language` preference (`'en'` or `'ar'`, default `'en'`).
  - `daily_goals`: Tracks daily aggregates (calories, workouts) and target achievements.
  - `chat_history`: Message stream including system/tool calls.
  - `message_feedback`: Thumbs up/down and comments mapped to `message_id`.
  - `workout_splits` & `split_items`: Scheduled workout routines (e.g., Push/Pull/Legs). Profile saves use an **upsert pattern** — the active split's UUID is reused across profile updates (only the name and `split_items` are refreshed), preserving `workout_plan_exercises.split_id` FK integrity. A new split row is only created when no active split exists (first-time onboarding).
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
- **Google GenAI API**: LLM provider for the conversational agent via `google.adk` (`gemini-flash-latest`).
- **Supabase**: PostgreSQL database, Authentication (JWT via Supabase JS Client on frontend), Edge Functions (e.g., `user-improvement-scorer`), and PostgREST auto-generated REST API.
- **Google MediaPipe Pose**: In-browser client-side ML model for real-time pose detection (loaded via JSDelivr CDN).
- **QuickChart.io API**: External HTTP API for server-side generation of Chart.js-based PNG chart images.
- **Tavily API**: Web search API (`tavily-python` SDK) for live internet searches, YouTube exercise video lookups, branded food macro data, and real-time fact verification. Configured via `TAVILY_API_KEY` env var.
- **Web Speech API**: Browser-native `SpeechSynthesis` for Live Coach voice feedback and rep counting.
- **PostHog EU Cloud** (`eu.i.posthog.com`): Product analytics platform. Dual-layer integration:
  - *Frontend*: JS SDK loaded via Jinja2 template. Events routed through first-party nginx proxy (`/ingest/*` → PostHog EU) to bypass adblockers. Auto-captures pageviews, pageleaves, and clicks. Custom events track chat usage, auth, onboarding funnel, live coach sessions, feedback, and workout tracker engagement.
  - *Backend*: Python SDK (`posthog` package) singleton client in `services/analytics.py`. Captures server-side events invisible to the browser: API latency, AI tool invocations, agent run metrics, and profile saves. Configured via `POSTHOG_API_KEY` and `POSTHOG_HOST` environment variables.
  - *Nginx Proxy*: `nginx/vhost.d/bot.ziadamer.com` defines two `location` blocks (`/ingest/static/` and `/ingest/`) that proxy to `eu-assets.i.posthog.com` and `eu.i.posthog.com` respectively, with SNI, HTTP/1.1 keepalive, and forwarded client IP headers.

## 7. Testing Infrastructure

### 7.1 Test Framework
- **Framework**: `pytest` with `pytest-asyncio` for async test support.
- **Configuration**: `pytest.ini` in the project root.
- **Fixtures**: `tests/conftest.py` provides shared test fixtures.

### 7.2 Test Suites
- **Unit Tests** (`tests/unit/`):
  - `test_api_endpoints.py` — FastAPI endpoint response validation.
  - `test_calculate_targets.py` — Mifflin-St Jeor macro/TDEE calculation logic.
  - `test_query_user_logs.py` — Time-series query utility validation.
  - `test_runner.py` — ADK Runner integration tests.
- **Integration Tests** (`tests/`):
  - `test_chart.py` — QuickChart.io chart generation integration.
  - `test_google_fit.py` — Google Fit data fetching (with `setup_google_fit.py` helper).
  - `verify_agent.py` — End-to-end agent verification script.
  - `verify_env.py` — Environment variable and dependency verification.
- **Database Setup** (`tests/`):
  - `setup_db.sql` — Test database initialization.
  - `migration_context_notes.sql`, `migration_triggers.sql`, `migration_workout_splits.sql` — Test migration scripts.
- **Test Images** (`tests/test_images/`) — Sample images for multimodal input testing.

## 8. Supplementary Components

### 8.1 Trainer Demo Module (`nutrisync_adk/trainer/`)
A standalone **Streamlit** application demonstrating pose estimation and exercise form analysis using MediaPipe. Not part of the main NutriSync deployment but serves as a research prototype and demo for the Live Coach feature.
- **Entry Point**: `🏠️_Demo.py` (Streamlit multi-page app).
- **Infrastructure**: Separate `Dockerfile`, `requirements.txt`, and `setup.sh`.
- **Capabilities**: Frame-by-frame pose processing (`process_frame.py`), configurable angle thresholds (`thresholds.py`), and utility functions (`utils.py`).
- **Origin**: Integrated from the `pradnya_repo/` research codebase (Apache License 2.0).

### 8.2 Legacy N8N Implementation (`n8n_implementation/`)
Historical workflow definitions from a prior architecture where NutriSync was built on **n8n** (workflow automation platform) before being rebuilt with Google ADK. These JSON files (`AddRow.json`, `DrawChart.json`, `GetHealthScores.json`, `MyHealthBrain.json`) are preserved for reference and are **not** part of the current system.

### 8.3 Known Schema Discrepancy
Migration `014_add_language.sql` targets table `user_profiles` (plural), but the actual production table is `user_profile` (singular). The `language` column does not appear in the current `user_profile` schema definition, suggesting this migration may target a different (or renamed) table or has not been applied. The `ProfileRequest.language` field is present in the API model but may not persist to the database if the column is missing.
