FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install --timeout=120 --retries=10 --resume-retries=10 -r requirements.txt
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=8 -o Acquire::https::Timeout=120 update --error-on=any \
    && apt-get -o Acquire::Retries=8 -o Acquire::https::Timeout=120 install -y --no-install-recommends ffmpeg gettext
COPY . .
RUN msgfmt --check -o locale/en/LC_MESSAGES/django.mo locale/en/LC_MESSAGES/django.po \
    && msgfmt --check -o locale/en/LC_MESSAGES/djangojs.mo locale/en/LC_MESSAGES/djangojs.po

# Django via WSGI. Compose remplace cette commande pour le worker et Beat.
EXPOSE 8000
CMD ["gunicorn", "dublao.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--error-logfile", "-"]
