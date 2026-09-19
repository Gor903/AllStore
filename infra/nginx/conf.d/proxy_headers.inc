# Included by every proxying location: nginx drops the whole inherited proxy_set_header set
# as soon as a location declares one of its own, and Host would silently become the upstream name.
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_http_version 1.1;
