FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY . /app/routes
RUN useradd --system --uid 10001 routeuser && mkdir -p /data && chown routeuser /data
USER routeuser
EXPOSE 8080
CMD ["python", "-m", "routes.proxy_server", "--container", "--db", "/data/proxies.db", "--manifest", "/input/working_proxies.json", "--proxy-list", "/input/working_proxies.txt", "--health-checks"]
