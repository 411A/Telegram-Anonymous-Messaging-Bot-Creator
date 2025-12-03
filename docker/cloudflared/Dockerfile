# Cloudflare Tunnel Docker Image
FROM cloudflare/cloudflared:latest

# Set working directory
WORKDIR /etc/cloudflared

# Copy configuration files
# These will be mounted as volumes at runtime
# COPY config.yml /etc/cloudflared/config.yml
# COPY credentials.json /etc/cloudflared/credentials.json

# Run cloudflared tunnel with reduced logging (only errors and fatal)
# Log levels: debug, info, warn, error, fatal
ENTRYPOINT ["cloudflared", "tunnel"]
CMD ["--config", "/etc/cloudflared/config.yml", "--loglevel", "error", "run"]
