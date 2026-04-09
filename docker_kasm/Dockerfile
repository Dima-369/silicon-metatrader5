FROM ghcr.io/linuxserver/baseimage-kasmvnc:debianbookworm


LABEL org.opencontainers.image.title="pysiliconwinekasm" \
      org.opencontainers.image.description="KasmVNC-based Wine runtime for MetaTrader 5 and siliconmetatrader5 on Apple Silicon workflows" \
      org.opencontainers.image.vendor="bahadirumutiscimen" \
      org.opencontainers.image.source="https://github.com/bahadirumutiscimen/silicon-metatrader5"

ENV TITLE=SiliconMetaTrader5-Kasm \
    WINEPREFIX=/opt/wineprefix-base \
    WINEDEBUG=-all \
    DEBIAN_FRONTEND=noninteractive \
    CUSTOM_PORT=3000 \
    NO_FULL=true \
    PYTHON_VERSION=3.13.9 \
    PYTHON_URL=https://www.python.org/ftp/python/3.13.9/python-3.13.9-amd64.exe \
    MT5_URL=https://download.mql5.com/cdn/web/metaquotes.ltd/mt5/mt5setup.exe \
    KCLIENT_AUDIO=0

WORKDIR /siliconmt5

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        python3-xdg \
        curl \
        wget \
        cabextract \
        unzip \
        procps \
        iproute2 \
        ca-certificates \
        gnupg2 \
        software-properties-common \
        xvfb \
    && mkdir -pm755 /etc/apt/keyrings \
    && wget -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key \
    && wget -NP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/debian/dists/bookworm/winehq-bookworm.sources \
    && dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install --install-recommends -y winehq-stable \
    && curl -L -o /usr/local/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks \
    && chmod +x /usr/local/bin/winetricks \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY requirements.txt ./requirements.txt
COPY mt5cfg.ini ./mt5cfg.ini
COPY scripts/ ./scripts/
COPY defaults/ /defaults/
COPY custom-cont-init.d/ /custom-cont-init.d/

RUN chmod +x /siliconmt5/scripts/*.sh /custom-cont-init.d/*.sh \
    && python3 /siliconmt5/scripts/patch-kclient-audio.py \
    && /siliconmt5/scripts/build-runtime.sh \
    && test -f "/opt/wineprefix-base/.runtime_baked"

EXPOSE 3000 3001 8001
VOLUME /config
