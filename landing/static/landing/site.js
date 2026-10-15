const translateLandingText = text => typeof gettext === 'function' ? gettext(text) : text;
const menu = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#navigation');
if (menu && navigation) {
  const closeMenu = () => {
    menu.setAttribute('aria-expanded', 'false');
    navigation.classList.remove('is-open');
    navigation.querySelectorAll('details[open]').forEach(dropdown => dropdown.removeAttribute('open'));
  };
  menu.addEventListener('click', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(open));
    navigation.classList.toggle('is-open', open);
  });
  navigation.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
  document.addEventListener('click', event => {
    if (!menu.contains(event.target) && !navigation.contains(event.target)) closeMenu();
  });
  const mobileNavigation = matchMedia('(max-width: 900px)');
  mobileNavigation.addEventListener('change', closeMenu);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') {
      closeMenu();
      menu.focus();
    }
  });
}
const demoPlayer = document.querySelector('#demo-player');
if (demoPlayer) {
  const buttons = [...document.querySelectorAll('[data-demo-source]')];
  const status = document.querySelector('[data-demo-status]');
  let selected = buttons.find(button => button.getAttribute('aria-pressed') === 'true');
  let pendingTime = null;
  let resumePlayback = false;
  const describe = text => {
    if (!status) return;
    status.textContent = text;
    status.hidden = !text;
  };
  demoPlayer.addEventListener('loadedmetadata', () => {
    if (pendingTime !== null && Number.isFinite(demoPlayer.duration)) {
      demoPlayer.currentTime = Math.min(pendingTime, Math.max(0, demoPlayer.duration - 0.1));
    }
    pendingTime = null;
    describe('');
    if (resumePlayback) {
      resumePlayback = false;
      demoPlayer.play().catch(() => describe(translateLandingText('Appuyez sur Lecture pour écouter cette version.')));
    }
  });
  demoPlayer.addEventListener('error', () => {
    resumePlayback = false;
    describe(translateLandingText('La vidéo ne peut pas être lue. Cliquez sur une langue pour réessayer.'));
  });
  buttons.forEach(button => button.addEventListener('click', () => {
    if (button === selected && !demoPlayer.error) return;
    if (pendingTime === null) pendingTime = demoPlayer.currentTime || 0;
    resumePlayback = resumePlayback || (!demoPlayer.paused && !demoPlayer.ended);
    demoPlayer.pause();
    selected = button;
    buttons.forEach(tab => {
      const active = tab === button;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-pressed', String(active));
    });
    demoPlayer.src = button.dataset.demoSource;
    demoPlayer.lang = button.dataset.demoLang;
    demoPlayer.setAttribute('aria-label', `${translateLandingText("Démonstration doublée :")} ${button.dataset.demoLabel}`);
    describe('');
    demoPlayer.load();
  }));
}
