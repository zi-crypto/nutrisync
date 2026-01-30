-- Run this in your Supabase SQL Editor

CREATE TABLE public.persistent_context (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid DEFAULT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
  note_content text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  is_active boolean DEFAULT true,
  CONSTRAINT persistent_context_pkey PRIMARY KEY (id)
);

-- Index for fast lookup of active notes
CREATE INDEX idx_persistent_context_active ON persistent_context (user_id) WHERE is_active = true;
