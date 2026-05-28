import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-user-token",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

/**
 * Compare two semver strings.  Returns 1 if a > b, -1 if a < b, 0 if equal.
 */
function cmpVersion(a: string, b: string): number {
  const pa = a.replace(/^v/, "").split(".").map(Number);
  const pb = b.replace(/^v/, "").split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const na = pa[i] ?? 0;
    const nb = pb[i] ?? 0;
    if (na > nb) return 1;
    if (na < nb) return -1;
  }
  return 0;
}

/**
 * Deterministic rollout bucket: hash (current_version + release_version) → 0-99.
 * Keeps the same user on the same side of the rollout threshold across checks.
 */
function rolloutBucket(currentVersion: string, releaseVersion: string): number {
  const key = `${currentVersion}:${releaseVersion}`;
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = (hash * 31 + key.charCodeAt(i)) & 0x7fffffff;
  }
  return hash % 100;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    );

    const {
      current_version,
      platform,
      channel = "stable",
      host_version = null,
      os_info = null,
    } = await req.json();

    if (!current_version || !platform) {
      return new Response(
        JSON.stringify({ error: "current_version and platform are required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Query all published releases for the requested channel (or stable fallback).
    // Beta clients also see stable releases; stable clients only see stable.
    const channels = channel === "beta" ? ["stable", "beta"] : ["stable"];

    const { data: releases, error: queryErr } = await supabase
      .from("addon_releases")
      .select(
        "version, channel, changelog, release_notes, is_critical, " +
        "rollout_percent, min_update_version, " +
        "file_size_blender, file_size_maya, file_hash_blender, file_hash_maya"
      )
      .eq("is_published", true)
      .in("channel", channels)
      .order("version", { ascending: false })
      .limit(10);

    if (queryErr) {
      console.error("Query error:", queryErr);
      return new Response(
        JSON.stringify({ error: "Failed to query releases" }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Find the latest release that is newer than current_version and passes
    // rollout + min_update_version checks.
    let best: (typeof releases)[number] | null = null;

    for (const rel of releases ?? []) {
      // Must be newer than what the client already has
      if (cmpVersion(rel.version, current_version) <= 0) continue;

      // Respect min_update_version — client must be at least this version
      if (rel.min_update_version && cmpVersion(current_version, rel.min_update_version) < 0) {
        continue;
      }

      // Rollout gating
      if (rel.rollout_percent < 100) {
        const bucket = rolloutBucket(current_version, rel.version);
        if (bucket >= rel.rollout_percent) continue;
      }

      // This release qualifies — take the first (newest) match
      best = rel;
      break;
    }

    // Fire-and-forget: aggregate daily check (one row per user/platform/day)
    supabase
      .rpc("upsert_daily_check", {
        p_date: new Date().toISOString().slice(0, 10),
        p_platform: platform,
        p_host: host_version ?? "unknown",
        p_os: os_info ?? "unknown",
        p_version: current_version,
      })
      .then(() => {});

    if (!best) {
      return new Response(
        JSON.stringify({ update_available: false }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const fileSize = platform === "blender" ? best.file_size_blender : best.file_size_maya;
    const fileHash = platform === "blender" ? best.file_hash_blender : best.file_hash_maya;

    return new Response(
      JSON.stringify({
        update_available: true,
        version: best.version,
        channel: best.channel,
        changelog: best.changelog ?? "",
        release_notes: best.release_notes ?? "",
        is_critical: best.is_critical ?? false,
        file_size: fileSize ?? 0,
        file_hash: fileHash ?? "",
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("Unhandled error:", err);
    return new Response(
      JSON.stringify({ error: String(err) }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
