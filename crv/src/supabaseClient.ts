// src/supabaseClient.ts
// Client do Supabase pro FRONTEND. Usa a chave pública (anon key) -
// nunca a service_role key, essa fica só no backend (Python).

import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    "VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY precisam estar definidos no .env do frontend"
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
