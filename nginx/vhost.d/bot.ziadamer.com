# ── PostHog Reverse Proxy ────────────────────────────────────────────────────
# Routes /ingest/* through our own domain to bypass adblockers.
# Frontend JS SDK sends events to https://bot.ziadamer.com/ingest/
# which nginx forwards to PostHog EU cloud.

location /ingest/static/ {
    resolver 1.1.1.1 8.8.8.8 valid=300s;
    resolver_timeout 5s;

    proxy_pass https://eu-assets.i.posthog.com/static/;
    proxy_set_header Host eu-assets.i.posthog.com;

    proxy_ssl_server_name on;
    proxy_ssl_name eu-assets.i.posthog.com;
    proxy_ssl_verify off;

    proxy_http_version 1.1;
    proxy_set_header Connection '';
}

location /ingest/ {
    resolver 1.1.1.1 8.8.8.8 valid=300s;
    resolver_timeout 5s;

    proxy_pass https://eu.i.posthog.com/;
    proxy_set_header Host eu.i.posthog.com;

    proxy_ssl_server_name on;
    proxy_ssl_name eu.i.posthog.com;
    proxy_ssl_verify off;

    proxy_http_version 1.1;
    proxy_set_header Connection '';

    # Pass through real client IP for geo data
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Host $host;
}
