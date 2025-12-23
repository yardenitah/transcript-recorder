#FROM python:3.10-slim
#
## Install minimal system dependencies required for Agora SDK and Audio
#RUN apt-get update --allow-releaseinfo-change && apt-get install -y --no-install-recommends \
#    libasound2 \
#    libssl-dev \
#    ca-certificates \
#    libc++-dev \
#    && rm -rf /var/lib/apt/lists/*
#
#WORKDIR /app
#
## Install Python dependencies
#COPY requirements.txt .
#RUN pip install --no-cache-dir -r requirements.txt
#
## Configure Agora SDK paths
#ENV AGORA_SDK_PATH=/usr/local/lib/python3.10/site-packages/agora/agora_sdk
#COPY agora_rtc_sdk.zip /usr/local/lib/python3.10/site-packages/agora/agora_rtc_sdk.zip
#COPY agora_sdk/ $AGORA_SDK_PATH/
#RUN echo "$AGORA_SDK_PATH" > /etc/ld.so.conf.d/agora.conf && ldconfig
#
#ENV LD_LIBRARY_PATH=$AGORA_SDK_PATH
#ENV PYTHONPATH=/app
#
## Copy application code
#COPY . .
#
#EXPOSE 8000
#
## Start the application using Uvicorn
#CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM python:3.10-slim

# 1. התקנת תלויות מערכת כולל PulseAudio
RUN apt-get update --allow-releaseinfo-change && apt-get install -y --no-install-recommends \
    libasound2 \
    libasound2-plugins \
    pulseaudio \
    pulseaudio-utils \
    libssl-dev \
    ca-certificates \
    libc++-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. הגדרת PulseAudio לרוץ כ-Root (נדרש בדוקר)
RUN useradd -ms /bin/bash agora && \
    adduser root pulse-access

# עריכת קובץ הקונפיגורציה של PulseAudio כדי לאפשר הרצת Root
RUN sed -i 's/^; enable-shm = yes/enable-shm = no/g' /etc/pulse/daemon.conf && \
    sed -i 's/^; system-instance = no/system-instance = yes/g' /etc/pulse/daemon.conf && \
    sed -i 's/^; exit-idle-time = 20/exit-idle-time = -1/g' /etc/pulse/daemon.conf

# 3. התקנת ספריות פייתון
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. הגדרת נתיבי Agora SDK
ENV AGORA_SDK_PATH=/usr/local/lib/python3.10/site-packages/agora/agora_sdk
COPY agora_rtc_sdk.zip /usr/local/lib/python3.10/site-packages/agora/agora_rtc_sdk.zip
COPY agora_sdk/ $AGORA_SDK_PATH/
RUN echo "$AGORA_SDK_PATH" > /etc/ld.so.conf.d/agora.conf && ldconfig

ENV LD_LIBRARY_PATH=$AGORA_SDK_PATH
ENV PYTHONPATH=/app

# 5. תיקון הבאג הפנימי של ה-SDK
RUN sed -i 's/if custome_specified >= 0:/if custome_specified is not None and custome_specified >= 0:/g' /usr/local/lib/python3.10/site-packages/agora/rtc/rtc_connection.py

# 6. העתקת הקוד והסקריפט
COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

# שימוש ב-Entrypoint להפעלת הסאונד לפני הבוט
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]