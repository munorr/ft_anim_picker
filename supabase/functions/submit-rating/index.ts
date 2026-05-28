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

    // Verify JWT
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

    const { product_id, rating, review } = await req.json();

    if (!product_id || !rating || rating < 1 || rating > 5) {
      return new Response(
        JSON.stringify({ error: "Missing or invalid product_id/rating (1-5)" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Upsert the rating (service_role bypasses RLS)
    const { error: upsertErr } = await supabase
      .from("library_ratings")
      .upsert(
        {
          user_id: user.id,
          product_id,
          rating,
          review: review || null,
          updated_at: new Date().toISOString(),
        },
        { onConflict: "user_id,product_id" }
      );

    if (upsertErr) {
      return new Response(
        JSON.stringify({ error: `Failed to submit rating: ${upsertErr.message}` }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // The DB trigger updates rating_avg/rating_count — re-fetch them
    const { data: product, error: fetchErr } = await supabase
      .from("library_products")
      .select("rating_avg, rating_count")
      .eq("id", product_id)
      .single();

    if (fetchErr) {
      return new Response(
        JSON.stringify({ error: `Failed to fetch updated rating: ${fetchErr.message}` }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(
      JSON.stringify({
        rating_avg: product.rating_avg ?? 0,
        rating_count: product.rating_count ?? 0,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("submit-rating error:", err);
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
