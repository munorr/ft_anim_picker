import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY") || "";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-user-token",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

/**
 * Helper: call Stripe REST API directly.
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

    const { action, payment_method_id } = await req.json();

    // Get user's stripe_customer_id
    const { data: profile } = await supabase
      .from("user_profiles")
      .select("stripe_customer_id")
      .eq("id", user.id)
      .single();

    if (!profile?.stripe_customer_id) {
      return new Response(
        JSON.stringify({ payment_methods: [] }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const customerId = profile.stripe_customer_id;

    // LIST payment methods
    if (action === "list") {
      const data = await stripeRequest(
        "GET",
        `/payment_methods?customer=${encodeURIComponent(customerId)}&type=card&limit=10`
      );

      const methods = (data.data || []).map((pm: any) => ({
        id: pm.id,
        brand: pm.card?.brand || "unknown",
        last4: pm.card?.last4 || "????",
        exp_month: pm.card?.exp_month,
        exp_year: pm.card?.exp_year,
      }));

      return new Response(
        JSON.stringify({ payment_methods: methods }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // DELETE (detach) a payment method
    if (action === "delete") {
      if (!payment_method_id) {
        return new Response(
          JSON.stringify({ error: "Missing payment_method_id" }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }

      // Verify the payment method belongs to this customer
      const pm = await stripeRequest(
        "GET",
        `/payment_methods/${encodeURIComponent(payment_method_id)}`
      );

      if (pm.customer !== customerId) {
        return new Response(
          JSON.stringify({ error: "Payment method does not belong to this user" }),
          { status: 403, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }

      // Detach the payment method from the customer
      await stripeRequest(
        "POST",
        `/payment_methods/${encodeURIComponent(payment_method_id)}/detach`
      );

      return new Response(
        JSON.stringify({ success: true }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(
      JSON.stringify({ error: "Invalid action. Use 'list' or 'delete'." }),
      { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("manage-payment-methods error:", err);
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
