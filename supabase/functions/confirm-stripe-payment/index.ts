import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY") || "";

/**
 * Helper: call Stripe REST API directly.
 */
async function stripeRequest(method: string, path: string) {
  const res = await fetch(`https://api.stripe.com/v1${path}`, {
    method,
    headers: { Authorization: `Bearer ${STRIPE_SECRET_KEY}` },
  });
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

    const { payment_intent_id, product_id } = await req.json();

    if (!payment_intent_id || !product_id) {
      return new Response(
        JSON.stringify({ error: "Missing payment_intent_id or product_id" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    // Retrieve PaymentIntent from Stripe
    const intent = await stripeRequest(
      "GET",
      `/payment_intents/${encodeURIComponent(payment_intent_id)}`
    );

    // Security: verify this payment belongs to the requesting user
    if (intent.metadata?.supabase_user_id !== user.id) {
      return new Response(
        JSON.stringify({ error: "Payment does not belong to this user" }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      );
    }

    if (intent.metadata?.supabase_product_id !== product_id) {
      return new Response(
        JSON.stringify({ error: "Payment/product mismatch" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    if (intent.status !== "succeeded") {
      return new Response(
        JSON.stringify({
          status: intent.status === "requires_payment_method" ? "failed" : "pending",
          product_id,
        }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Payment succeeded — upsert purchase record
    const priceCents = intent.amount || 0;

    const { data: purchaseData, error: purchaseErr } = await supabase
      .from("library_purchases")
      .upsert(
        {
          user_id: user.id,
          product_id: product_id,
          price_paid_cents: priceCents,
          stripe_payment_intent_id: payment_intent_id,
          status: "completed",
        },
        { onConflict: "user_id,product_id" }
      )
      .select("id")
      .single();

    if (purchaseErr) {
      console.error("Purchase upsert failed:", purchaseErr);
      return new Response(
        JSON.stringify({ error: "Failed to record purchase" }),
        { status: 500, headers: { "Content-Type": "application/json" } }
      );
    }

    // Lookup product to get creator_id and payout split
    const { data: product } = await supabase
      .from("library_products")
      .select("creator_id")
      .eq("id", product_id)
      .single();

    if (product?.creator_id && purchaseData?.id) {
      // Skip if transaction already exists for this purchase (idempotency)
      const { data: existingTx } = await supabase
        .from("library_transactions")
        .select("id")
        .eq("purchase_id", purchaseData.id)
        .maybeSingle();

      if (!existingTx) {
        // Lookup creator payout split
        const { data: creator } = await supabase
          .from("creator_profiles")
          .select("payout_split_percent")
          .eq("creator_id", product.creator_id)
          .single();

        const splitPercent = creator?.payout_split_percent ?? 80;
        const platformFeeCents = Math.round(
          priceCents * ((100 - splitPercent) / 100)
        );
        const creatorNetCents = priceCents - platformFeeCents;

        const { error: txErr } = await supabase
          .from("library_transactions")
          .insert({
            purchase_id: purchaseData.id,
            product_id,
            creator_id: product.creator_id,
            buyer_id: user.id,
            gross_amount_cents: priceCents,
            platform_fee_cents: platformFeeCents,
            processing_fee_cents: 0,
            creator_net_cents: creatorNetCents,
            status: "completed",
          });

        if (txErr) {
          console.error("Transaction insert failed:", txErr);
        }
      }
    }

    return new Response(
      JSON.stringify({ status: "completed", product_id }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("confirm-stripe-payment error:", err);
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
