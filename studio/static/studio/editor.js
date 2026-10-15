/* Native HTML5 media + Alpine state. Billing is always verified by Django/Celery. */
(function () {
  'use strict';
  const translateStudioText = text => typeof gettext === 'function' ? gettext(text) : text;

  window.dublaoStudio = function () {
    let objectUrl = '', audioEpoch = 0, frame = 0, observer = null, peaks = [], context = null;
    return {
      mode: 'create', title: '', status: 'draft', statusLabel: translateStudioText('Nouveau projet'),
      availableUnits: 0, reservedUnits: 0, reservationStatus: '', reservationUnits: 0, consumedUnits: 0,
      billingEnabled: true, frozen: false, versions: [], selectedLanguages: [],
      originalUrl: '', currentUrl: '', filename: '', fileSizeLabel: '', sourceLabel: translateStudioText('Détection automatique'),
      selectedVersion: 'original', selectedLabel: translateStudioText('Aperçu de votre vidéo'), selectedDownloadUrl: '',
      originalDuration: 0, duration: 0, currentTime: 0, playing: false, volume: 1, muted: false,
      initialized: false, mediaError: false, hasWaveform: false, waveformMessage: translateStudioText('Importez un fichier pour analyser son audio.'),
      errorMessage: '', resumeUrl: '', sending: false, launchConfirmed: false, notice: '', fullscreenSupported: false,
      get minutesPerLanguage() { return this.originalDuration > 0 ? Math.ceil(Math.ceil(this.originalDuration * 1000) / 60000) : 0; },
      get estimate() { return this.minutesPerLanguage && this.selectedLanguages.length ? this.minutesPerLanguage * this.selectedLanguages.length : null; },
      get insufficient() {
        const required = this.estimate === null ? this.selectedLanguages.length : this.estimate;
        return this.billingEnabled && required * 60000 > this.availableUnits;
      },
      get playbackPercent() { return this.duration ? Math.min(100, Math.max(0, this.currentTime / this.duration * 100)) : 0; },
      init() {
        const config = JSON.parse(document.getElementById('studio-config').textContent);
        for (const key of ['mode', 'title', 'status', 'statusLabel', 'availableUnits', 'reservedUnits', 'reservationStatus', 'reservationUnits', 'consumedUnits', 'frozen', 'billingEnabled', 'versions', 'originalUrl', 'filename', 'sourceLabel', 'errorMessage', 'resumeUrl']) {
          if (config[key] !== undefined) this[key] = config[key];
        }
        this.originalDuration = config.durationMs ? config.durationMs / 1000 : 0;
        this.duration = this.originalDuration;
        this.currentUrl = this.originalUrl;
        this.selectedLabel = this.mode === 'project' ? translateStudioText('Vidéo originale') : translateStudioText('Aperçu de votre vidéo');
        if (this.mode === 'project') this.waveformMessage = translateStudioText('Waveform non analysée pour cette vidéo stockée.');
        this.$nextTick(() => {
          this.initialized = true;
          this.updateSelection();
          if (!this.originalUrl) {
            const first = this.versions.find(version => version.watchUrl);
            if (first) this.selectVersion(first.locale);
          }
          this.fullscreenSupported = Boolean(this.$refs.videoStage?.requestFullscreen || this.$refs.video?.webkitEnterFullscreen);
          if (matchMedia('(max-width: 900px)').matches) {
            this.$root.querySelectorAll('[data-mobile-collapse]').forEach(panel => {
              if (!panel.querySelector('[role=alert]')) panel.open = false;
            });
          }
          if (window.ResizeObserver && this.$refs.waveform) {
            observer = new ResizeObserver(() => this.drawWaveform());
            observer.observe(this.$refs.waveform.parentElement);
          }
        });
      },
      destroy() {
        ++audioEpoch;
        this.stopPlaybackLoop();
        observer?.disconnect();
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        if (context && context.state !== 'closed') context.close().catch(() => {});
      },
      time(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
        const total = Math.floor(seconds), hours = Math.floor(total / 3600);
        const minutes = String(Math.floor(total / 60) % 60).padStart(2, '0');
        const remainder = String(total % 60).padStart(2, '0');
        return hours ? `${hours}:${minutes}:${remainder}` : `${minutes}:${remainder}`;
      },
      credits(units) { return (units / 60000).toLocaleString(typeof document === 'undefined' ? 'fr' : document.documentElement.lang, { maximumFractionDigits: 2 }); },
      openImportPanel() { const panel = this.$root.querySelector('[data-mobile-collapse]'); if (panel) panel.open = true; },
      updateSelection() {
        if (!this.$refs.uploadForm) return;
        this.selectedLanguages = Array.from(this.$refs.uploadForm.querySelectorAll('input[name=target_locales]:checked')).map(input => {
          const label = input.closest('label');
          return { locale: input.value, name: label.querySelector('.language-option__body > span')?.textContent.trim() || input.value,
            flagUrl: label.querySelector('img')?.getAttribute('src') || '', state: 'waiting', statusLabel: translateStudioText('À produire') };
        });
        const source = this.$refs.uploadForm.querySelector('input[name=source_locale]:checked');
        if (source) this.sourceLabel = source.closest('label').querySelector('.language-option__body > span')?.textContent.trim() || translateStudioText('Détection automatique');
      },
      setSourceLabel(label) { this.sourceLabel = label; },
      importFile(event) {
        const file = event.target.files?.[0];
        if (!file) return;
        this.stopPlaybackLoop();
        this.$refs.video?.pause();
        ++audioEpoch;
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = URL.createObjectURL(file);
        this.filename = file.name;
        this.fileSizeLabel = `${(file.size / 1024 / 1024).toLocaleString(typeof document === 'undefined' ? 'fr' : document.documentElement.lang, { maximumFractionDigits: 1 })} ${translateStudioText("Mo")}`;
        if (!this.title) this.title = file.name.replace(/\.[^.]+$/, '').slice(0, 120);
        this.originalUrl = objectUrl;
        this.originalDuration = 0;
        this.hasWaveform = false;
        this.analyzingAudio = false;
        peaks = [];
        this.selectVersion('original');
        this.notice = translateStudioText('Vidéo sélectionnée. Vérifiez les langues avant de lancer le doublage.');
        // Optional audio decoding is explicit to avoid loading large videos into memory automatically.
        this.waveformMessage = file.size <= 128 * 1024 * 1024 ? translateStudioText('Audio prêt à être analysé.') : translateStudioText('Analyse audio locale indisponible pour ce fichier volumineux.');
        this.localFile = file;
        this.canAnalyzeAudio = file.size <= 128 * 1024 * 1024;
      },
      localFile: null, canAnalyzeAudio: false, analyzingAudio: false,
      async analyzeAudio() {
        if (!this.localFile || !this.canAnalyzeAudio || this.analyzingAudio) return;
        const token = ++audioEpoch, AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) { this.waveformMessage = 'L’analyse audio n’est pas disponible dans ce navigateur.'; return; }
        this.analyzingAudio = true;
        this.waveformMessage = 'Analyse de la piste audio…';
        let decoder;
        try {
          decoder = new AudioContext({ sampleRate: 8000 });
          context = decoder;
          const decoded = await decoder.decodeAudioData(await this.localFile.arrayBuffer());
          if (token !== audioEpoch) return;
          const channels = Array.from({ length: decoded.numberOfChannels }, (_, channel) => decoded.getChannelData(channel));
          const bins = 600, samplesPerBin = Math.max(1, Math.floor(decoded.length / bins));
          peaks = Array.from({ length: bins }, (_, bin) => {
            let peak = 0;
            const start = bin * samplesPerBin, end = Math.min(decoded.length, start + samplesPerBin);
            const stride = Math.max(1, Math.floor(samplesPerBin / 256));
            for (let index = start; index < end; index += stride) {
              for (const channel of channels) peak = Math.max(peak, Math.abs(channel[index]));
            }
            return peak;
          });
          this.hasWaveform = this.selectedVersion === 'original';
          this.canAnalyzeAudio = false;
          this.waveformMessage = translateStudioText('Amplitude réelle de la piste audio originale.');
          this.$nextTick(() => this.drawWaveform());
        } catch (_) {
          if (token === audioEpoch) this.waveformMessage = translateStudioText('L’audio de ce format ne peut pas être analysé par ce navigateur.');
        } finally {
          if (decoder && decoder.state !== 'closed') await decoder.close().catch(() => {});
          if (context === decoder) context = null;
          if (token === audioEpoch) this.analyzingAudio = false;
        }
      },
      drawWaveform() {
        const canvas = this.$refs.waveform;
        if (!canvas || !this.hasWaveform || !peaks.length) return;
        const width = canvas.parentElement.clientWidth, height = 44, ratio = Math.min(devicePixelRatio || 1, 2);
        if (!width) return;
        if (canvas.width !== Math.round(width * ratio)) canvas.width = Math.round(width * ratio);
        if (canvas.height !== Math.round(height * ratio)) canvas.height = Math.round(height * ratio);
        const pen = canvas.getContext('2d');
        pen.setTransform(ratio, 0, 0, ratio, 0, 0); pen.clearRect(0, 0, width, height);
        const bars = Math.min(peaks.length, Math.floor(width / 3)), played = this.playbackPercent / 100;
        for (let index = 0; index < bars; index++) {
          const value = peaks[Math.floor(index / bars * peaks.length)];
          const barHeight = Math.max(1, value * (height - 6));
          pen.fillStyle = index / bars <= played ? '#53d99b' : '#426553';
          pen.fillRect(index * width / bars, (height - barHeight) / 2, 2, barHeight);
        }
      },
      metadataLoaded() {
        const media = this.$refs.video;
        if (!media || !this.currentUrl || !Number.isFinite(media.duration) || media.duration <= 0) return;
        this.duration = media.duration;
        if (this.selectedVersion === 'original') this.originalDuration = media.duration;
        this.mediaError = false;
        this.updatePlayback();
      },
      updatePlayback() { if (this.$refs.video) this.currentTime = this.$refs.video.currentTime || 0; this.drawWaveform(); },
      startPlaybackLoop() {
        if (frame || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        const update = () => { this.updatePlayback(); frame = this.playing ? requestAnimationFrame(update) : 0; };
        frame = requestAnimationFrame(update);
      },
      stopPlaybackLoop() { if (frame) cancelAnimationFrame(frame); frame = 0; },
      async togglePlayback() {
        const media = this.$refs.video;
        if (!media || !this.currentUrl) return;
        if (!media.paused) media.pause();
        else { try { await media.play(); } catch (_) { this.notice = translateStudioText('La lecture n’a pas démarré. Vérifiez le format de la vidéo.'); } }
      },
      seekTo(seconds) { if (this.$refs.video && this.duration && Number.isFinite(seconds)) { this.$refs.video.currentTime = Math.max(0, Math.min(seconds, this.duration)); this.updatePlayback(); } },
      seekFromTimeline(event) { const rect = event.currentTarget.getBoundingClientRect(); if (rect.width) this.seekTo((event.clientX - rect.left) / rect.width * this.duration); },
      setVolume(value) { if (this.$refs.video) { this.$refs.video.volume = Math.max(0, Math.min(1, value)); this.$refs.video.muted = false; } },
      toggleMute() { if (this.$refs.video) this.$refs.video.muted = !this.$refs.video.muted; },
      async fullscreen() {
        try { if (this.$refs.videoStage.requestFullscreen) await this.$refs.videoStage.requestFullscreen(); else this.$refs.video?.webkitEnterFullscreen?.(); }
        catch (_) { this.notice = translateStudioText('Le plein écran n’est pas disponible dans ce navigateur.'); }
      },
      selectVersion(locale) {
        const version = locale === 'original' ? null : this.versions.find(item => item.locale === locale);
        const next = locale === 'original' ? this.originalUrl : version?.watchUrl;
        if (!next) return;
        if (this.currentUrl === next && this.selectedVersion === locale && this.$refs.video?.currentSrc) return;
        this.$refs.video?.pause(); this.stopPlaybackLoop();
        this.currentTime = 0; this.playing = false; this.mediaError = false;
        this.selectedVersion = locale; this.currentUrl = next;
        this.selectedLabel = locale === 'original' ? translateStudioText('Vidéo originale') : version.name;
        this.selectedDownloadUrl = version?.downloadUrl || '';
        this.duration = locale === 'original' ? this.originalDuration : 0;
        this.hasWaveform = locale === 'original' && peaks.length > 0;
        if (locale !== 'original') this.waveformMessage = translateStudioText('Waveform non analysée pour cette version doublée.');
        else if (peaks.length) this.waveformMessage = translateStudioText('Amplitude réelle de la piste audio originale.');
        else this.waveformMessage = this.localFile ? (this.canAnalyzeAudio ? translateStudioText('Audio prêt à être analysé.') : translateStudioText('Analyse audio locale indisponible pour ce fichier volumineux.')) : translateStudioText('Waveform non analysée pour cette vidéo stockée.');
        this.$nextTick(() => {
          if (this.$refs.video) { this.$refs.video.src = next; this.$refs.video.load(); }
          this.drawWaveform();
        });
      },
      reloadMedia() { if (this.$refs.video && this.currentUrl) { this.mediaError = false; this.$refs.video.src = this.currentUrl.startsWith('blob:') ? this.currentUrl : this.currentUrl + '?refresh=' + Date.now(); this.$refs.video.load(); } },
      syncState(state) {
        if (this.mode !== 'project') return;
        const before = this.versions.filter(version => version.state === 'ready').length;
        this.versions = state.versions;
        for (const key of ['status', 'statusLabel', 'availableUnits', 'reservedUnits', 'reservationStatus', 'reservationUnits', 'consumedUnits', 'frozen', 'errorMessage', 'resumeUrl']) this[key] = state[key];
        if (state.durationMs && !this.originalDuration) this.originalDuration = state.durationMs / 1000;
        if (this.versions.filter(version => version.state === 'ready').length > before) this.notice = translateStudioText('Une nouvelle version doublée est disponible.');
        if (!this.currentUrl) { const first = this.versions.find(version => version.watchUrl); if (first) this.selectVersion(first.locale); }
      },
      handleSubmit(event) {
        if (this.sending || this.insufficient || (this.billingEnabled && this.frozen)) { event.preventDefault(); return; }
        if (!this.launchConfirmed && this.$refs.confirmation?.showModal) { event.preventDefault(); this.updateSelection(); this.$refs.confirmation.showModal(); return; }
        this.sending = true;
      },
      confirmLaunch() {
        if (this.insufficient || (this.billingEnabled && this.frozen)) return;
        this.launchConfirmed = true;
        this.$refs.confirmation.close();
        this.$refs.uploadForm.requestSubmit();
      },
    };
  };
})();
