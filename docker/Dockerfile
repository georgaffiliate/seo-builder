FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      librsvg2-bin \
      nodejs \
      zip \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pillow

WORKDIR /app
COPY . .

# snapshot static resource dirs so entrypoint can seed named volumes on first run
RUN mkdir -p content-dist plans-dist \
 && cp -R content/. content-dist/ \
 && cp -R plans/. plans-dist/ \
 && useradd -m builder \
 && chown -R builder:builder /app

USER builder
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

ENTRYPOINT ["/app/docker/entrypoint.sh"]
