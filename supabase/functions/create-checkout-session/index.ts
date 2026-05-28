import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY") || "";

/**
 * Helper: call Stripe REST API directly (no SDK needed in Deno).
 */
async function stripeRequest(
  method: string,
  path: string,
  body?: Record<string, string>
) {
  const url = `https://api.stripe.com/v1${path}`;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${STRIPE_SECRET_KEY}`,
  };

  let reqBody: string | undefined;
  if (body) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    reqBody = new URLSearchParams(body).toString();
  }

  const res = await fetch(url, { method, headers, body: reqBody });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error?.message || `Stripe ${res.status}`);
  }
  return data;
}

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-user-token, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    if (!STRIPE_SECRET_KEY) {
      return new Response(
        JSON.stringify({ error: "Payment system not configured" }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

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

    const { product_id, success_url, cancel_url } = await req.json();

    if (!product_id || !success_url || !cancel_url) {
      return new Response(
        JSON.stringify({ error: "Missing product_id, success_url, or cancel_url" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Lookup product
    const { data: product } = await supabase
      .from("library_products")
      .select("*")
      .eq("id", product_id)
      .eq("status", "published")
      .single();

    if (!product) {
      return new Response(JSON.stringify({ error: "Product not found" }), {
        status: 404,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    if (product.price_cents === 0) {
      return new Response(
        JSON.stringify({ error: "Use create-stripe-intent for free products" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Check if already owned
    const { data: existing } = await supabase
      .from("library_purchases")
      .select("id")
      .eq("user_id", user.id)
      .eq("product_id", product_id)
      .eq("status", "completed")
      .maybeSingle();

    if (existing) {
      return new Response(
        JSON.stringify({ error: "Already owned", already_owned: true }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Get or create Stripe Customer
    let stripeCustomerId: string | null = null;

    const { data: profile } = await supabase
      .from("user_profiles")
      .select("stripe_customer_id")
      .eq("id", user.id)
      .single();

    if (profile?.stripe_customer_id) {
      stripeCustomerId = profile.stripe_customer_id;
    } else {
      const customer = await stripeRequest("POST", "/customers", {
        email: user.email || "",
        "metadata[supabase_user_id]": user.id,
      });
      stripeCustomerId = customer.id;

      await supabase
        .from("user_profiles")
        .update({ stripe_customer_id: stripeCustomerId })
        .eq("id", user.id);
    }

    // Append session_id placeholder to success URL so the success page can verify
    const successWithSession = success_url.includes("?")
      ? `${success_url}&session_id={CHECKOUT_SESSION_ID}`
      : `${success_url}?session_id={CHECKOUT_SESSION_ID}`;

    // Create Stripe Checkout Session
    const session = await stripeRequest("POST", "/checkout/sessions", {
      mode: "payment",
      customer: stripeCustomerId!,
      "line_items[0][price_data][currency]": "usd",
      "line_items[0][price_data][product_data][name]": product.name,
      "line_items[0][price_data][unit_amount]": String(product.price_cents),
      "line_items[0][quantity]": "1",
      success_url: successWithSession,
      cancel_url: cancel_url,
      "payment_intent_data[metadata][supabase_user_id]": user.id,
      "payment_intent_data[metadata][supabase_product_id]": product_id,
      "metadata[supabase_user_id]": user.id,
      "metadata[supabase_product_id]": product_id,
    });

    return new Response(
      JSON.stringify({ checkout_url: session.url }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("create-checkout-session error:", err);
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
