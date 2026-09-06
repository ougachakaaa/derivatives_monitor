FROM ubuntu:24.04 AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY experiments/ctp/common/ experiments/ctp/common/
COPY experiments/ctp/sdk/ experiments/ctp/sdk/
COPY collector/CMakeLists.txt collector/config.example.ini collector/
COPY collector/src/ collector/src/
COPY collector/tests/ collector/tests/

RUN cmake -S collector -B /build -DCMAKE_BUILD_TYPE=Release \
        -DCTP_LINK_MODE=SHARED -DBUILD_TESTING=ON \
    && cmake --build /build --parallel 2 \
    && ctest --test-dir /build --output-on-failure

FROM ubuntu:24.04 AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 libsqlite3-0 sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /build/bin/data_collector /build/bin/thostmduserapi_se.so /opt/collector/
RUN ldd /opt/collector/data_collector > /tmp/collector-ldd \
    && cat /tmp/collector-ldd \
    && ! grep -q 'not found' /tmp/collector-ldd

WORKDIR /app
USER 65532:65532
STOPSIGNAL SIGTERM
ENTRYPOINT ["/opt/collector/data_collector"]
CMD ["--config", "/app/config.ini"]
