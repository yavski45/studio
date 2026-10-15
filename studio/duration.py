from django.utils.translation import gettext_lazy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from credits.services import milliseconds


def video_duration_ms(source):
    """Durée calculée sur le fichier privé, jamais fournie par le navigateur."""
    with tempfile.TemporaryDirectory(prefix='dublao-duration-') as directory:
        path = Path(directory) / ('source' + Path(source.name).suffix.lower())
        with source.storage.open(source.name, 'rb') as original, path.open('wb') as destination:
            shutil.copyfileobj(original, destination, length=1024 * 1024)
        try:
            result = subprocess.run([getattr(settings, 'FFPROBE_BINARY', os.getenv('FFPROBE_BINARY', 'ffprobe')), '-v', 'error',
                '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,webm,avi',
                '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', str(path)],
                capture_output=True, timeout=90, check=False)
        except subprocess.TimeoutExpired:
            raise ValueError('Analyse vidéo trop longue.') from None
        if result.returncode:
            raise ValueError(gettext_lazy('La durée de cette vidéo ne peut pas être déterminée.'))
        try:
            data = json.loads(result.stdout)
            if not isinstance(data, dict) or not isinstance(data.get('streams'), list):
                raise ValueError('Métadonnées vidéo invalides.')
            if not any(isinstance(stream, dict) and stream.get('codec_type') == 'video' for stream in data['streams']):
                raise ValueError('Aucune piste vidéo.')
            return milliseconds(data['format']['duration'])
        except (KeyError, TypeError, json.JSONDecodeError):
            raise ValueError('Durée vidéo manquante.') from None
