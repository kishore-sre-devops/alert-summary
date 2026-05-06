# Build stage - compile React app
FROM node:18-alpine3.19 AS build
RUN apk update && apk upgrade
WORKDIR /app

# Copy package files first for better caching
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci --silent || npm install --no-audit --no-fund

# Copy source code
COPY . .

# Build the React app
ARG REACT_APP_ENV
ENV REACT_APP_ENV=$REACT_APP_ENV
RUN npm run build

# Production stage - serve with nginx
FROM nginx:stable-alpine
RUN apk update && apk upgrade

# Install curl for healthcheck
RUN apk add --no-cache curl

# Copy built React app to nginx html directory
COPY --from=build /app/build /usr/share/nginx/html/

# Set proper permissions
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx /var/log/nginx /etc/nginx/conf.d && \
    touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid

# Expose ports (Must be > 1024 for non-root, unless we use capabilities, but sticking to 8080 is safer for VAPT)
# But wait, the Nginx config listens on 80/443.
# Non-root user CANNOT bind to 80.
# We must update Nginx config to listen on 8080/8443.
# And update docker-compose ports mapping.
# This is a risky change ("breaking functionality").
# ALTERNATIVE: Use `setcap` to allow binding to port 80.
RUN apk add --no-cache libcap && \
    setcap 'cap_net_bind_service=+ep' /usr/sbin/nginx

# Switch to non-root user
USER nginx

# Expose ports
EXPOSE 80 443

# Default command (will be overridden by entrypoint in docker-compose)
CMD ["nginx", "-g", "daemon off;"]
