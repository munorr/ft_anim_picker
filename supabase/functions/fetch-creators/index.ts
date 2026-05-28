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
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const supabase = createClient(supabaseUrl, serviceKey);

    // Parse optional query params from body
    let search: string | null = null;
    let featured: boolean | null = null;
    let limit = 20;
    let offset = 0;

    if (req.method === "POST") {
      try {
        const body = await req.json();
        search = body.search || null;
        featured = body.featured ?? null;
        limit = Math.min(body.limit || 20, 50);
        offset = body.offset || 0;
      } catch {
        // Empty body is fine — use defaults
      }
    }

    // Build query for approved creators
    let query = supabase
      .from("creator_profiles")
      .select("*", { count: "exact" })
      .eq("seller_status", "approved")
      .order("is_featured", { ascending: false })
      .order("total_sales_count", { ascending: false })
      .range(offset, offset + limit - 1);

    if (search) {
      query = query.ilike("display_name", `%${search}%`);
    }

    if (featured === true) {
      query = query.eq("is_featured", true);
    }

    const { data: creators, count, error } = await query;

    if (error) {
      return new Response(JSON.stringify({ error: error.message }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Attach public avatar URLs from creator-assets bucket
    const withUrls = (creators || []).map((c: any) => ({
      ...c,
      avatar_url: c.avatar_url
        ? c.avatar_url.startsWith("http")
          ? c.avatar_url
          : `${supabaseUrl}/storage/v1/object/public/creator-assets/${c.avatar_url}`
        : null,
      banner_url: c.banner_url
        ? c.banner_url.startsWith("http")
          ? c.banner_url
          : `${supabaseUrl}/storage/v1/object/public/creator-assets/${c.banner_url}`
        : null,
    }));

    return new Response(
      JSON.stringify({
        creators: withUrls,
        total: count || 0,
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
