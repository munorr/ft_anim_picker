import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY") || "";
const STRIPE_PUBLISHABLE_KEY = Deno.env.get("STRIPE_PUBLISHABLE_KEY") || "";

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

    // Free product — create entitlement directly, no checkout
    if (product.price_cents === 0) {
      const { data: purchaseData, error: insertErr } = await supabase
        .from("library_purchases")
        .upsert(
          {
            user_id: user.id,
            product_id: product_id,
            price_paid_cents: 0,
            status: "completed",
          },
          { onConflict: "user_id,product_id" }
        )
        .select("id")
        .single();

      if (insertErr) {
        return new Response(JSON.stringify({ error: insertErr.message }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }

      // Create transaction record so sales-count trigger fires
      if (product.creator_id && purchaseData?.id) {
        // Skip if already exists (idempotency for retries)
        const { data: existingTx } = await supabase
          .from("library_transactions")
          .select("id")
          .eq("purchase_id", purchaseData.id)
          .maybeSingle();

        if (!existingTx) {
          const { error: txErr } = await supabase
            .from("library_transactions")
            .insert({
              purchase_id: purchaseData.id,
              product_id,
              creator_id: product.creator_id,
              buyer_id: user.id,
              gross_amount_cents: 0,
              platform_fee_cents: 0,
              processing_fee_cents: 0,
              creator_net_cents: 0,
              status: "completed",
            });

          if (txErr) {
            console.error("Free transaction insert failed:", txErr);
          }
        }
      }

      return new Response(JSON.stringify({ free: true, owned: true }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Paid product — create Stripe PaymentIntent
    if (!STRIPE_SECRET_KEY || !STRIPE_PUBLISHABLE_KEY) {
      return new Response(
        JSON.stringify({ error: "Payment system not configured" }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
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
      // Create new Stripe Customer
      const customer = await stripeRequest("POST", "/customers", {
        email: user.email || "",
        "metadata[supabase_user_id]": user.id,
      });
      stripeCustomerId = customer.id;

      // Store on user_profiles
      await supabase
        .from("user_profiles")
        .update({ stripe_customer_id: stripeCustomerId })
        .eq("id", user.id);
    }

    // Create PaymentIntent
    const intent = await stripeRequest("POST", "/payment_intents", {
      amount: String(product.price_cents),
      currency: "usd",
      customer: stripeCustomerId!,
      setup_future_usage: "on_session",
      "automatic_payment_methods[enabled]": "true",
      "metadata[supabase_user_id]": user.id,
      "metadata[supabase_product_id]": product_id,
    });

    // Create Customer Session so Payment Element shows saved cards
    const customerSession = await stripeRequest("POST", "/customer_sessions", {
      customer: stripeCustomerId!,
      "components[payment_element][enabled]": "true",
      "components[payment_element][features][payment_method_redisplay]": "enabled",
      "components[payment_element][features][payment_method_save]": "enabled",
      "components[payment_element][features][payment_method_remove]": "enabled",
    });

    return new Response(
      JSON.stringify({
        client_secret: intent.client_secret,
        customer_session_secret: customerSession.client_secret,
        publishable_key: STRIPE_PUBLISHABLE_KEY,
        product_name: product.name,
        price_cents: product.price_cents,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("create-stripe-intent error:", err);
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
