import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

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
    const supabase = createClient(supabaseUrl, serviceKey);

    const { creator_id, slug } = await req.json();

    if (!creator_id && !slug) {
      return new Response(
        JSON.stringify({ error: "creator_id or slug required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // 1. Fetch creator profile
    let creatorQuery = supabase
      .from("creator_profiles")
      .select("*")
      .eq("seller_status", "approved");

    if (creator_id) {
      creatorQuery = creatorQuery.eq("creator_id", creator_id);
    } else {
      creatorQuery = creatorQuery.eq("slug", slug);
    }

    const { data: creator, error: creatorErr } = await creatorQuery.single();

    if (creatorErr || !creator) {
      return new Response(
        JSON.stringify({ error: "Creator not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // 2. Fetch their published products
    const { data: products, error: prodErr } = await supabase
      .from("library_products")
      .select("*")
      .eq("creator_id", creator.creator_id)
      .eq("status", "published")
      .order("created_at", { ascending: false });

    if (prodErr) {
      return new Response(JSON.stringify({ error: prodErr.message }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Attach thumbnail URLs
    const withThumb = (p: any) => ({
      ...p,
      thumbnail_url: p.thumbnail_path
        ? `${supabaseUrl}/storage/v1/object/public/library-thumbnails/${p.thumbnail_path}`
        : null,
    });

    // 3. Check if requesting user follows this creator (if auth token present)
    let isFollowing = false;
    const userToken = req.headers.get("x-user-token");
    if (userToken) {
      const token = userToken;
      const {
        data: { user },
      } = await supabase.auth.getUser(token);

      if (user) {
        const { data: follow } = await supabase
          .from("creator_followers")
          .select("creator_id")
          .eq("creator_id", creator.creator_id)
          .eq("user_id", user.id)
          .maybeSingle();

        isFollowing = !!follow;
      }
    }

    // Attach public URLs for avatar and banner
    const creatorWithUrls = {
      ...creator,
      avatar_url: creator.avatar_url
        ? creator.avatar_url.startsWith("http")
          ? creator.avatar_url
          : `${supabaseUrl}/storage/v1/object/public/creator-assets/${creator.avatar_url}`
        : null,
      banner_url: creator.banner_url
        ? creator.banner_url.startsWith("http")
          ? creator.banner_url
          : `${supabaseUrl}/storage/v1/object/public/creator-assets/${creator.banner_url}`
        : null,
    };

    return new Response(
      JSON.stringify({
        creator: creatorWithUrls,
        products: (products || []).map(withThumb),
        is_following: isFollowing,
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
