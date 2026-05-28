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

    const { product_id, user_id } = await req.json();

    if (!product_id) {
      return new Response(
        JSON.stringify({ error: "Missing product_id" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Fetch all reviews for this product
    const { data: reviews, error: revErr } = await supabase
      .from("library_ratings")
      .select("*")
      .eq("product_id", product_id)
      .order("created_at", { ascending: false });

    if (revErr) {
      return new Response(
        JSON.stringify({ error: `Failed to fetch reviews: ${revErr.message}` }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Optionally fetch the specific user's rating
    let user_rating = null;
    if (user_id) {
      const { data } = await supabase
        .from("library_ratings")
        .select("*")
        .eq("product_id", product_id)
        .eq("user_id", user_id)
        .maybeSingle();
      user_rating = data;
    }

    return new Response(
      JSON.stringify({ reviews: reviews ?? [], user_rating }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("get-product-ratings error:", err);
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
