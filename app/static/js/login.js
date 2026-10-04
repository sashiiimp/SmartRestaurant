// Show / hide the password on the login page (an external file, because the CSP allows no inline script).
(function () {
  var btn = document.getElementById('pw-toggle'), input = document.getElementById('password');
  if (!btn || !input || !window.SRIcons) return;
  btn.addEventListener('click', function () {
    var show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.setAttribute('aria-pressed', show ? 'true' : 'false');
    btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    btn.replaceChildren(window.SRIcons.svg(show ? 'eyeoff' : 'eye', 18));
  });
})();
