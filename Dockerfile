FROM python:3.10-slim

# 1. התקנת תלויות מערכת
# libasound2 + libpulse0: חובה בשביל Agora Audio Engine
# libssl-dev: לתקשורת מאובטחת
# ca-certificates: לוודא שהאימות מול השרתים עובד
RUN apt-get update --allow-releaseinfo-change \
 && apt-get install -y --no-install-recommends \
    libasound2 \
    libpulse0 \
    libssl-dev \
    ca-certificates \
    libc++-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# הגדרת משתנה עזר לנתיב (פותר את ה-Warnings)
ENV AGORA_SDK_PATH=/usr/local/lib/python3.10/site-packages/agora/agora_sdk

# 2. העתקת ה-SDK
COPY agora_rtc_sdk.zip /usr/local/lib/python3.10/site-packages/agora/agora_rtc_sdk.zip
COPY agora_sdk/ $AGORA_SDK_PATH/

# 3. רישום הספריות במערכת (השיטה של ldconfig - הכי יציב)
# זה גורם ללינוקס "להכיר" את הספריות של אגורה כאילו הן ספריות מערכת רגילות
RUN echo "$AGORA_SDK_PATH" > /etc/ld.so.conf.d/agora.conf && ldconfig

# הגדרה כפולה ליתר ביטחון (למקרה שסקריפטים מסוימים מסתמכים על זה)
ENV LD_LIBRARY_PATH=$AGORA_SDK_PATH

# הוספת התיקייה הנוכחית לפייתון
ENV PYTHONPATH=/app

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]