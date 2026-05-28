import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const STRIPE_WEBHOOK_SECRET = Deno.env.get("STRIPE_WEBHOOK_SECRET") || "";
const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY") || "";

/**
 * Verify Stripe webhook signature (v1 scheme).
 * Stripe sends: stripe-signature header with "t=<timestamp>,v1=<sig>,..."
 */
async function verifyStripeSignature(
  payload: string,
  sigHeader: string
): Promise<boolean> {
  if (!STRIPE_WEBHOOK_SECRET) {
    console.error("STRIPE_WEBHOOK_SECRET not set — rejecting webhook");
    return false;
  }

  const elements: Record<string, string> = {};
  for (const part of sigHeader.split(",")) {
    const [key, val] = part.split("=", 2);
    if (key && val) elements[key] = val;
  }

  const timestamp = elements["t"];
  const signature = elements["v1"];
  if (!timestamp || !signature) {
    console.warn("Missing t or v1 in stripe-signature header");
    return false;
  }

  // Check timestamp is within 5 minutes
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - parseInt(timestamp, 10)) > 300) {
    console.warn("Stripe webhook timestamp too old");
    return false;
  }

  // Compute expected signature: HMAC-SHA256 of "timestamp.payload"
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(STRIPE_WEBHOOK_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const signed = await crypto.subtle.sign(
    "HMAC",
    key,
    encoder.encode(`${timestamp}.${payload}`)
  );

  // Convert to hex
  const expected = Array.from(new Uint8Array(signed))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return expected === signature;
}

Deno.serve(async (req) => {
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
  );

  try {
    const body = await req.text();

    // Verify webhook signature — reject unsigned/invalid requests
    const sigHeader = req.headers.get("stripe-signature") || "";
    const valid = await verifyStripeSignature(body, sigHeader);
    if (!valid) {
      console.error("Stripe webhook signature verification failed — rejecting request");
      return new Response("Invalid signature", { status: 401 });
    }

    const event = JSON.parse(body);
    const eventType = event.type;

    // Log every incoming webhook for diagnostics
    await supabase.from("webhook_logs").insert({
      event_type: eventType,
      payload: event,
      status: "received",
    });

    // Handle payment_intent.succeeded
    if (eventType === "payment_intent.succeeded") {
      const intent = event.data.object;
      const metadata = intent.metadata || {};
      const userId = metadata.supabase_user_id;
      const productId = metadata.supabase_product_id;
      const paymentIntentId = intent.id;
      const priceCents = intent.amount || 0;

      if (!userId || !productId) {
        const errorMsg = `Missing user_id (${userId}) or product_id (${productId})`;
        console.error(errorMsg);
        await supabase.from("webhook_logs").update({
          status: "error",
          error: errorMsg,
        }).eq("payload->>type", eventType).order("created_at", { ascending: false }).limit(1);
        return new Response("Missing data", { status: 400 });
      }

      // Upsert purchase record (idempotent)
      const { error: purchaseErr } = await supabase
        .from("library_purchases")
        .upsert(
          {
            user_id: userId,
            product_id: productId,
            price_paid_cents: priceCents,
            stripe_payment_intent_id: paymentIntentId,
            status: "completed",
          },
          { onConflict: "user_id,product_id" }
        );

      if (purchaseErr) {
        console.error("Purchase insert failed:", purchaseErr);
        await supabase.from("webhook_logs").update({
          status: "db_error",
          error: JSON.stringify(purchaseErr),
        }).eq("payload->>type", eventType).order("created_at", { ascending: false }).limit(1);
        return new Response("DB error", { status: 500 });
      }

      // --- Creator revenue tracking (fire-and-forget) ---
      try {
        const { data: product } = await supabase
          .from("library_products")
          .select("creator_id")
          .eq("id", productId)
          .single();

        if (product?.creator_id) {
          const { data: creator } = await supabase
            .from("creator_profiles")
            .select("payout_split_percent")
            .eq("creator_id", product.creator_id)
            .single();

          const splitPercent = creator?.payout_split_percent ?? 80;
          // Stripe processing fee: 2.9% + $0.30
          const processingFee = Math.round(priceCents * 0.029 + 30);
          const creatorNet = Math.max(
            Math.round((priceCents - processingFee) * splitPercent / 100),
            0
          );
          const platformFee = priceCents - processingFee - creatorNet;

          // Get the purchase ID for the FK
          const { data: purchase } = await supabase
            .from("library_purchases")
            .select("id")
            .eq("user_id", userId)
            .eq("product_id", productId)
            .single();

          // Insert transaction record
          const { error: txErr } = await supabase
            .from("library_transactions")
            .insert({
              purchase_id: purchase?.id || null,
              product_id: productId,
              creator_id: product.creator_id,
              buyer_id: userId,
              gross_amount_cents: priceCents,
              platform_fee_cents: platformFee,
              processing_fee_cents: processingFee,
              creator_net_cents: creatorNet,
              stripe_payment_intent_id: paymentIntentId,
              status: "completed",
            });

          if (txErr) {
            console.error("Transaction insert failed:", txErr);
          } else {
            // Insert earnings ledger entry
            const { data: lastEarning } = await supabase
              .from("creator_earnings")
              .select("balance_after_cents")
              .eq("creator_id", product.creator_id)
              .order("created_at", { ascending: false })
              .limit(1)
              .maybeSingle();

            const currentBalance = lastEarning?.balance_after_cents ?? 0;
            const newBalance = currentBalance + creatorNet;

            await supabase.from("creator_earnings").insert({
              creator_id: product.creator_id,
              entry_type: "sale",
              amount_cents: creatorNet,
              balance_after_cents: newBalance,
              transaction_id: null,
              description: `Sale of product ${productId}`,
            });

            console.log(
              `Creator revenue recorded: creator=${product.creator_id} net=${creatorNet}c balance=${newBalance}c`
            );
          }
        }
      } catch (revenueErr) {
        // Revenue tracking failure should not block the purchase
        console.error("Revenue tracking error (non-fatal):", revenueErr);
      }

      // Update webhook log to success
      await supabase.from("webhook_logs").update({
        status: "processed",
      }).eq("payload->>type", eventType).order("created_at", { ascending: false }).limit(1);

      console.log(
        `Purchase recorded: user=${userId} product=${productId} pi=${paymentIntentId}`
      );
      return new Response("OK", { status: 200 });
    }

    // Handle charge.refunded (future-proofing)
    if (eventType === "charge.refunded") {
      const charge = event.data.object;
      const paymentIntentId = charge.payment_intent;

      if (paymentIntentId) {
        // Update the purchase status to refunded
        await supabase
          .from("library_purchases")
          .update({ status: "refunded" })
          .eq("stripe_payment_intent_id", paymentIntentId);

        console.log(`Refund processed for PI: ${paymentIntentId}`);
      }

      await supabase.from("webhook_logs").update({
        status: "processed",
      }).eq("payload->>type", eventType).order("created_at", { ascending: false }).limit(1);

      return new Response("OK", { status: 200 });
    }

    // Unhandled event type — acknowledge receipt
    return new Response("OK", { status: 200 });
  } catch (err) {
    console.error("Webhook error:", err);
    try {
      await supabase.from("webhook_logs").insert({
        event_type: "unhandled_error",
        payload: {},
        status: "error",
        error: String(err),
      });
    } catch (_) { /* ignore logging errors */ }
    return new Response("Internal error", { status: 500 });
  }
});
