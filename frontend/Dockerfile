FROM nginx:alpine

# Copy all built assets to nginx html directory
COPY . /usr/share/nginx/html/

# Remove the Dockerfile from the serve directory if it was copied
RUN rm -f /usr/share/nginx/html/Dockerfile /usr/share/nginx/html/nginx.conf

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
