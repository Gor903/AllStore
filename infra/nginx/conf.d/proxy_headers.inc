# Included by every proxying location: nginx drops the whole inherited proxy_set_header set
# as soon as a location declares one of its own, and Host would silently become the upstream name.
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
# Overwritten, not appended. `$proxy_add_x_forwarded_for` keeps whatever the caller sent and
# adds our view of them on the end — which means a caller can put any address they like in
# front of it, and the backend, walking the chain, believes the first hop it cannot vouch for.
# That made every rate limit keyed on an address bypassable by typing a different one.
# There is exactly one proxy here, so its own view is the whole truth. Put a CDN or a load
# balancer in front of this and it becomes `$proxy_add_x_forwarded_for` again — and then
# TRUSTED_PROXIES has to name that thing, and only that thing.
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_http_version 1.1;
