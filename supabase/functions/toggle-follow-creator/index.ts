import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-user-token",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    );

    // Verify JWT — prefer x-user-token (client sends anon key in Authorization for gateway)
    const userToken = req.headers.get("x-user-token");
    const authHeader = req.headers.get("Authorization");
    if (!userToken && !authHeader) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const token = userToken || authHeader!.replace("Bearer ", "");
    const {
      data: { user },
      error: authErr,
    } = await supabase.auth.getUser(token);

    if (authErr || !user) {
      return new Response(JSON.stringify({ error: "Invalid token" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const { creator_id } = await req.json();
    if (!creator_id) {
      return new Response(
        JSON.stringify({ error: "creator_id required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Check if already following
    const { data: existing } = await supabase
      .from("creator_followers")
      .select("creator_id")
      .eq("creator_id", creator_id)
      .eq("user_id", user.id)
      .maybeSingle();

    let following: boolean;

    if (existing) {
      // Unfollow
      const { error: delErr } = await supabase
        .from("creator_followers")
        .delete()
        .eq("creator_id", creator_id)
        .eq("user_id", user.id);

      if (delErr) {
        return new Response(JSON.stringify({ error: delErr.message }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
      following = false;
    } else {
      // Follow
      const { error: insErr } = await supabase
        .from("creator_followers")
        .insert({ creator_id, user_id: user.id });

      if (insErr) {
        return new Response(JSON.stringify({ error: insErr.message }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
      following = true;
    }

    // Fetch updated follower count (trigger updates it, but read fresh)
    const { data: creator } = await supabase
      .from("creator_profiles")
      .select("follower_count")
      .eq("creator_id", creator_id)
      .single();

    return new Response(
      JSON.stringify({
        following,
        follower_count: creator?.follower_count ?? 0,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
