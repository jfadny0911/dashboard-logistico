// scripts.js - interactions for neumorphism UI

document.addEventListener('DOMContentLoaded', function () {
  // Elements
  const btnDashboard = document.getElementById('btnDashboard');
  const btnDashboardMobile = document.getElementById('btnDashboardMobile');
  const modal = document.getElementById('loginModal');
  const backdrop = document.getElementById('modalBackdrop');
  const closeModal = document.getElementById('closeModal');
  const loginForm = document.getElementById('loginForm');
  const loginError = document.getElementById('loginError');
  const navToggle = document.getElementById('navToggle');
  const mobileNav = document.getElementById('mobileNav');
  const navToggleOpen = () => mobileNav.setAttribute('aria-hidden','false');
  const navToggleClose = () => mobileNav.setAttribute('aria-hidden','true');

  // Show modal helper
  function showModal(){
    modal.style.display = 'flex';
    backdrop.style.display = 'block';
    modal.setAttribute('aria-hidden','false');
    loginError.style.display = 'none';
    document.body.style.overflow = 'hidden';
    document.getElementById('adminUser').focus();
  }
  function hideModal(){
    modal.style.display = 'none';
    backdrop.style.display = 'none';
    modal.setAttribute('aria-hidden','true');
    document.body.style.overflow = '';
  }

  // Dashboard buttons open modal
  if(btnDashboard) btnDashboard.addEventListener('click', showModal);
  if(btnDashboardMobile) btnDashboardMobile.addEventListener('click', showModal);

  // Close modal
  if(closeModal) closeModal.addEventListener('click', hideModal);
  if(backdrop) backdrop.addEventListener('click', hideModal);
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape') hideModal();
  });

  // Mobile nav toggle
  navToggle?.addEventListener('click', function(){
    const visible = mobileNav.getAttribute('aria-hidden') === 'false';
    if(visible) navToggleClose(); else navToggleOpen();
  });

  // Simple navbar shrink on scroll (subtle)
  const navbar = document.querySelector('.navbar');
  function onScroll(){
    if(window.scrollY > 30) navbar.classList.add('scrolled'); else navbar.classList.remove('scrolled');
  }
  onScroll();
  document.addEventListener('scroll', onScroll);

  // LOGIN (simple client-side)
  // IMPORTANT: Cambia estas credenciales antes de producción
  const ADMIN_USER = "admin";
  const ADMIN_PASS = "1234";

  loginForm?.addEventListener('submit', function(e){
    e.preventDefault();
    const user = document.getElementById('adminUser').value.trim();
    const pass = document.getElementById('adminPass').value.trim();

    if(user === ADMIN_USER && pass === ADMIN_PASS){
      // éxito -> redirigir al dashboard
      window.location.href = "https://dashboard-logistico-su73vcvpqwwjayshptkxbr.streamlit.app/";
    } else {
      loginError.style.display = 'block';
      loginError.textContent = 'Credenciales incorrectas';
      // pequeño shake
      const card = document.querySelector('.modal-card');
      card.classList.remove('shake');
      void card.offsetWidth;
      card.classList.add('shake');
    }
  });

  // Contact form: simple UX (no envío real)
  const contactForm = document.getElementById('contactForm');
  contactForm?.addEventListener('submit', function(e){
    e.preventDefault();
    alert('¡Gracias! Te notificaremos al correo ingresado.');
  });
});

/* CSS animations injection for small shake effect */
(function addStyles(){
  const css = `.shake{animation:shake .45s ease}
  @keyframes shake{0%{transform:translateX(0)}25%{transform:translateX(-6px)}50%{transform:translateX(6px)}75%{transform:translateX(-4px)}100%{transform:translateX(0)}}`;
  const style = document.createElement('style'); style.appendChild(document.createTextNode(css)); document.head.appendChild(style);
})();
