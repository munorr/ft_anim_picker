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

    const { version, platform } = await req.json();

    if (!version || !platform) {
      return new Response(
        JSON.stringify({ error: "version and platform are required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Look up the release
    const { data: release, error: queryErr } = await supabase
      .from("addon_releases")
      .select(
        "storage_path_blender, storage_path_maya, " +
        "file_hash_blender, file_hash_maya, " +
        "file_size_blender, file_size_maya"
      )
      .eq("version", version)
      .eq("is_published", true)
      .single();

    if (queryErr || !release) {
      return new Response(
        JSON.stringify({ error: "Release not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const storagePath =
      platform === "blender" ? release.storage_path_blender : release.storage_path_maya;
    const fileHash =
      platform === "blender" ? release.file_hash_blender : release.file_hash_maya;
    const fileSize =
      platform === "blender" ? release.file_size_blender : release.file_size_maya;

    if (!storagePath) {
      return new Response(
        JSON.stringify({ error: `No ${platform} download configured for this release` }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Generate a signed URL from the private addon-releases bucket (1-hour expiry)
    const { data: signedUrlData, error: storageErr } = await supabase.storage
      .from("addon-releases")
      .createSignedUrl(storagePath, 3600);

    if (storageErr || !signedUrlData?.signedUrl) {
      console.error("Storage signed URL error:", storageErr);
      return new Response(
        JSON.stringify({ error: "Failed to generate download URL" }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Fire-and-forget: record download_start event
    let userId: string | null = null;
    const userToken = req.headers.get("x-user-token");
    if (userToken) {
      try {
        const { data: { user } } = await supabase.auth.getUser(userToken);
        userId = user?.id ?? null;
      } catch { /* ignore auth errors for analytics */ }
    }

    supabase
      .from("addon_update_events")
      .insert({
        user_id: userId,
        from_version: "",  // not known at download time
        to_version: version,
        platform,
        event_type: "download_start",
      })
      .then(() => {});

    return new Response(
      JSON.stringify({
        url: signedUrlData.signedUrl,
        file_hash: fileHash ?? "",
        file_size: fileSize ?? 0,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("Unhandled error:", err);
    return new Response(
      JSON.stringify({ error: String(err) }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
