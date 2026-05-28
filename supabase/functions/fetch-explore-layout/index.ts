import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-user-token",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve(async (_req) => {
  // Handle CORS preflight
  if (_req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const supabase = createClient(supabaseUrl, serviceKey);

    // 1. Fetch active sections (RLS handles schedule filtering)
    const { data: sections, error: secErr } = await supabase
      .from("library_sections")
      .select("*")
      .eq("is_active", true)
      .order("position");

    if (secErr) {
      return new Response(JSON.stringify({ error: secErr.message }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // 2. Fetch all published products
    const { data: allProducts, error: prodErr } = await supabase
      .from("library_products")
      .select("*")
      .eq("status", "published");

    // 2b. Fetch approved creators for creator strip / spotlight
    const { data: approvedCreators } = await supabase
      .from("creator_profiles")
      .select("*")
      .eq("seller_status", "approved")
      .order("is_featured", { ascending: false })
      .order("total_sales_count", { ascending: false })
      .limit(20);

    const creatorsById = new Map(
      (approvedCreators || []).map((c: any) => [c.creator_id, c])
    );

    // Helper: attach public URLs for creator assets
    const withCreatorUrls = (c: any) => ({
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
    });

    if (prodErr) {
      return new Response(JSON.stringify({ error: prodErr.message }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const productsById = new Map(
      (allProducts || []).map((p: any) => [p.id, p])
    );

    // Helper: attach public thumbnail URL
    const withThumb = (p: any) => ({
      ...p,
      thumbnail_url: p.thumbnail_path
        ? `${supabaseUrl}/storage/v1/object/public/library-thumbnails/${p.thumbnail_path}`
        : null,
    });

    // 3. Resolve each section
    const resolved = (sections || []).map((sec: any) => {
      const s = { ...sec };

      if (s.type === "algorithmic") {
        const algo = s.algorithm || {};
        let products = [...(allProducts || [])];

        if (algo.filter === "free") {
          products = products.filter((p: any) => p.price_cents === 0);
        }

        products.sort((a: any, b: any) => {
          if (algo.sort === "newest")
            return (
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime()
            );
          if (algo.sort === "rating")
            return (b.rating_avg || 0) - (a.rating_avg || 0);
          if (algo.sort === "featured") {
            if (a.featured !== b.featured) return a.featured ? -1 : 1;
            return (b.download_count || 0) - (a.download_count || 0);
          }
          // Default: sort by downloads
          return (b.download_count || 0) - (a.download_count || 0);
        });

        s.products = products.slice(0, algo.limit || 8).map(withThumb);
      } else if (s.type === "hero") {
        s.slides = (s.slides || []).map((slide: any) => ({
          ...slide,
          product: productsById.has(slide.product_id)
            ? withThumb(productsById.get(slide.product_id))
            : null,
        }));
      } else if (s.type === "creator_spotlight") {
        const pids: string[] = s.product_ids || [];
        s.products = pids
          .map((pid: string) => productsById.get(pid))
          .filter(Boolean)
          .map(withThumb);
        // Enrich with full creator profile if creator_id is set
        if (s.creator_id && creatorsById.has(s.creator_id)) {
          const cp = creatorsById.get(s.creator_id)!;
          s.creator_info = withCreatorUrls(cp);
        } else {
          s.creator_info = { name: s.creator_name };
        }
        // Include all approved creators for the horizontal strip
        s.creators = (approvedCreators || []).map(withCreatorUrls);
      } else if (s.type === "collection_grid") {
        s.collections = (s.collections || []).map((coll: any) => ({
          ...coll,
          products: (coll.product_ids || [])
            .map((pid: string) => productsById.get(pid))
            .filter(Boolean)
            .map(withThumb),
        }));
      }

      return s;
    });

    // 4. Fetch feature flags
    const { data: flags } = await supabase
      .from("library_feature_flags")
      .select("key, value");

    const featureFlags: Record<string, any> = {};
    (flags || []).forEach((f: any) => {
      featureFlags[f.key] = f.value;
    });

    // 5. Return everything
    return new Response(
      JSON.stringify({
        sections: resolved,
        products: (allProducts || []).map(withThumb),
        creators: (approvedCreators || []).map(withCreatorUrls),
        feature_flags: featureFlags,
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
