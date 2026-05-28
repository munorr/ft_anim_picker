"""
Supabase REST Client
Thin HTTP client for Supabase GoTrue auth, PostgREST, and Edge Functions.
Uses only urllib.request — zero external dependencies.
"""

import json
import urllib.request
import urllib.error
import urllib.parse


class SupabaseError(Exception):
    """Error from a Supabase API call."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class SupabaseClient:
    """
    Lightweight Supabase HTTP client.

    Covers GoTrue (auth), PostgREST (database), and Edge Functions.
    All methods are synchronous — run them inside a worker thread
    to keep the UI responsive.
    """

    def __init__(self, url: str, anon_key: str):
        self.url = url.rstrip("/")
        self.anon_key = anon_key

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _request(self, method, path, headers=None, body=None, timeout=15):
        """Make an HTTP request and return parsed JSON.

        Raises ``SupabaseError`` on HTTP errors or connection failures.
        """
        full_url = f"{self.url}{path}"
        base_headers = {
            "apikey": self.anon_key,
            "Content-Type": "application/json",
        }
        if headers:
            base_headers.update(headers)

        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(
            full_url, data=data, headers=base_headers, method=method
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            # Try to extract Supabase error message from response body
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
                msg = err_body.get("error_description") or err_body.get("msg") or err_body.get("message") or str(err_body)
            except Exception:
                msg = str(exc)
            raise SupabaseError(msg, status_code=exc.code) from exc
        except urllib.error.URLError as exc:
            raise SupabaseError(f"Connection error: {exc.reason}") from exc
        except Exception as exc:
            raise SupabaseError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Auth — GoTrue REST API
    # ------------------------------------------------------------------

    def send_otp(self, email: str) -> dict:
        """Send a 6-digit OTP code to *email*.

        Uses the ``/auth/v1/otp`` endpoint with ``email`` type.
        Returns the raw API response (usually empty on success).
        """
        return self._request("POST", "/auth/v1/otp", body={
            "email": email,
        })

    def verify_otp(self, email: str, token: str) -> dict:
        """Verify an OTP code and return a session.

        Returns a dict with ``access_token``, ``refresh_token``,
        ``expires_in``, ``user``, etc.
        """
        return self._request("POST", "/auth/v1/verify", body={
            "email": email,
            "token": token,
            "type": "email",
        })

    def refresh_session(self, refresh_token: str) -> dict:
        """Exchange a refresh token for a new session.

        Returns a dict with fresh ``access_token``, ``refresh_token``,
        ``expires_in``, etc.
        """
        return self._request(
            "POST",
            "/auth/v1/token?grant_type=refresh_token",
            body={"refresh_token": refresh_token},
            timeout=8,
        )

    def sign_out(self, access_token: str, scope: str = "local") -> dict:
        """Invalidate the current session server-side.

        *scope* can be ``"local"`` (default — current session only),
        ``"others"`` (all other sessions), or ``"global"`` (all sessions
        including the current one).
        """
        return self._request(
            "POST",
            "/auth/v1/logout",
            headers={"Authorization": f"Bearer {access_token}"},
            body={"scope": scope} if scope != "local" else None,
        )

    def get_user(self, access_token: str) -> dict:
        """Fetch the authenticated user's profile from GoTrue."""
        return self._request(
            "GET",
            "/auth/v1/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------

    def get_oauth_url(self, provider: str, redirect_to: str) -> str:
        """Build the Supabase OAuth authorization URL for *provider*.

        Returns the full URL to open in the user's browser.  Supabase will
        redirect back to *redirect_to* after the OAuth flow completes,
        appending the session tokens as URL-fragment parameters.
        """
        params = urllib.parse.urlencode({
            "provider": provider,
            "redirect_to": redirect_to,
        })
        return f"{self.url}/auth/v1/authorize?{params}"

    # ------------------------------------------------------------------
    # Database — PostgREST
    # ------------------------------------------------------------------

    def query(self, table: str, access_token: str, params: str = "") -> list:
        """Read rows from a table using PostgREST query string.

        *params* is an already-encoded query string, e.g.
        ``"select=id,email&id=eq.some-uuid"``.
        """
        path = f"/rest/v1/{table}"
        if params:
            path = f"{path}?{params}"
        return self._request(
            "GET",
            path,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=10,
        )

    def update(self, table: str, access_token: str, match_params: str, body: dict) -> dict:
        """Update rows in a table via PostgREST PATCH.

        *match_params* is an already-encoded query string that identifies
        the row(s) to update, e.g. ``"id=eq.some-uuid"``.
        """
        path = f"/rest/v1/{table}?{match_params}"
        return self._request(
            "PATCH",
            path,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Prefer": "return=minimal",
            },
            body=body,
            timeout=10,
        )

    def insert(self, table: str, access_token: str, body: dict) -> dict:
        """Insert a row into a table via PostgREST POST."""
        return self._request(
            "POST",
            f"/rest/v1/{table}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Prefer": "return=minimal",
            },
            body=body,
            timeout=10,
        )

    def upsert(self, table: str, access_token: str, body: dict) -> dict:
        """Insert or update a row (PostgREST upsert via Prefer header)."""
        return self._request(
            "POST",
            f"/rest/v1/{table}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            body=body,
            timeout=10,
        )

    def delete(self, table: str, access_token: str, match_params: str) -> dict:
        """Delete rows from a table via PostgREST DELETE.

        *match_params* identifies the row(s), e.g. ``"session_id=eq.abc-123"``.
        """
        path = f"/rest/v1/{table}?{match_params}"
        return self._request(
            "DELETE",
            path,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Prefer": "return=minimal",
            },
            timeout=10,
        )

    def rpc(self, fn_name: str, access_token: str, body: dict = None) -> dict:
        """Call a Postgres function via PostgREST RPC."""
        return self._request(
            "POST",
            f"/rest/v1/rpc/{fn_name}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            body=body or {},
        )

    # ------------------------------------------------------------------
    # Edge Functions
    # ------------------------------------------------------------------

    def invoke(self, fn_name: str, access_token: str, body: dict = None) -> dict:
        """Invoke a Supabase Edge Function.

        The anon key is sent in the Authorization header so the Supabase
        gateway always accepts the request (``verify_jwt`` validation).
        The user's access token is passed via a custom ``x-user-token``
        header so the function can authenticate the caller internally
        via ``supabase.auth.getUser()``.
        """
        headers = {
            "Authorization": f"Bearer {self.anon_key}",
        }
        if access_token and access_token != self.anon_key:
            headers["x-user-token"] = access_token
        return self._request(
            "POST",
            f"/functions/v1/{fn_name}",
            headers=headers,
            body=body or {},
            timeout=20,
        )

    # ------------------------------------------------------------------
    # Storage / file download
    # ------------------------------------------------------------------

    def download_file(self, url: str, dest_path: str, access_token: str = None,
                      progress_callback=None, chunk_size: int = 8192) -> str:
        """Download a file from *url* to *dest_path* with optional progress.

        Parameters
        ----------
        url : str
            Full URL to download (e.g. a signed Storage URL).
        dest_path : str
            Local file path to write.
        access_token : str, optional
            Bearer token (only needed for non-signed URLs).
        progress_callback : callable, optional
            ``callback(bytes_downloaded, total_bytes)`` called per chunk.
            *total_bytes* may be 0 if the server doesn't send Content-Length.
        chunk_size : int
            Read buffer size in bytes (default 8192).

        Returns
        -------
        str
            The *dest_path* on success.

        Raises
        ------
        SupabaseError
            On HTTP or connection errors.
        """
        headers = {"apikey": self.anon_key}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(dest_path, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total)
            return dest_path
        except urllib.error.HTTPError as exc:
            raise SupabaseError(f"Download failed: {exc}", status_code=exc.code) from exc
        except urllib.error.URLError as exc:
            raise SupabaseError(f"Connection error: {exc.reason}") from exc
