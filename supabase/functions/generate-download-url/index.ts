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

    const { product_id } = await req.json();

    // Verify entitlement in our DB
    const { data: purchase } = await supabase
      .from("library_purchases")
      .select("id, download_count")
      .eq("user_id", user.id)
      .eq("product_id", product_id)
      .eq("status", "completed")
      .single();

    if (!purchase) {
      return new Response(JSON.stringify({ error: "Not purchased" }), {
        status: 403,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Get product's storage path from our DB
    const { data: product } = await supabase
      .from("library_products")
      .select("storage_path, download_count")
      .eq("id", product_id)
      .single();

    if (!product?.storage_path) {
      return new Response(
        JSON.stringify({ error: "Product download not configured" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Generate signed URL from private Supabase Storage bucket
    const { data: signedUrlData, error: storageErr } = await supabase.storage
      .from("library-assets")
      .createSignedUrl(product.storage_path, 3600); // 1-hour expiry

    if (storageErr || !signedUrlData?.signedUrl) {
      console.error("Storage signed URL error:", storageErr);
      return new Response(
        JSON.stringify({ error: "Failed to generate download URL" }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Increment download counts (fire-and-forget)
    supabase
      .from("library_purchases")
      .update({ download_count: (purchase.download_count || 0) + 1 })
      .eq("id", purchase.id)
      .then(() => {});

    supabase
      .from("library_products")
      .update({ download_count: (product.download_count || 0) + 1 })
      .eq("id", product_id)
      .then(() => {});

    return new Response(JSON.stringify({ url: signedUrlData.signedUrl }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
