FROM golang:1.24-alpine AS build

ARG MINIO_VERSION=RELEASE.2025-10-15T17-29-55Z
ENV MINIO_VERSION=${MINIO_VERSION}

RUN apk add --no-cache git make bash \
 && git clone --depth 1 --branch ${MINIO_VERSION} https://github.com/minio/minio.git /src \
 && cd /src \
 && go build -trimpath -ldflags "-s -w" -o /out/minio

FROM alpine:3.20
COPY --from=build /out/minio /usr/local/bin/minio

RUN apk add --no-cache ca-certificates curl && \
    chmod +x /usr/local/bin/minio

EXPOSE 9000 9001
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
