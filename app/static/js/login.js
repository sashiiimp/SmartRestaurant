// Login page behaviour (an external file, because the CSP allows no inline script): show / hide the password,
// friendly checks for empty fields, a Caps Lock hint and a loading state. The server still does every real check.
(function () {
  var form = document.getElementById('login-form');
  var user = document.getElementById('username'), pass = document.getElementById('password');
  var btn = document.getElementById('pw-toggle'), submit = document.getElementById('login-submit');
  var caps = document.getElementById('caps-msg'), status = document.getElementById('login-status');
  if (!form || !user || !pass) return;

  if (btn && window.SRIcons) {
    btn.addEventListener('click', function () {
      var show = pass.type === 'password';
      pass.type = show ? 'text' : 'password';
      btn.setAttribute('aria-pressed', show ? 'true' : 'false');
      btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      btn.replaceChildren(window.SRIcons.svg(show ? 'eyeoff' : 'eye', 18));
      pass.focus();
    });
  }

  // After a failed login the username is filled in again, so put the cursor in the password field.
  if (document.getElementById('form-error') && user.value) pass.focus();

  function setError(input, text) {
    var msg = document.getElementById(input.id + '-msg');
    input.closest('.field').classList.toggle('has-error', !!text);
    if (text) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid');
    if (msg) { msg.textContent = text || ''; msg.hidden = !text; }
  }

  [user, pass].forEach(function (input) {
    input.addEventListener('input', function () {
      if (input.value.trim() || input === pass && input.value) setError(input, '');
    });
  });

  function updateCaps(e) {
    if (!caps || !e.getModifierState) return;
    caps.hidden = !e.getModifierState('CapsLock');
  }
  pass.addEventListener('keydown', updateCaps);
  pass.addEventListener('keyup', updateCaps);
  pass.addEventListener('blur', function () { if (caps) caps.hidden = true; });

  form.addEventListener('submit', function (e) {
    if (form.classList.contains('is-loading')) { e.preventDefault(); return; }   // no double submit
    var missingUser = !user.value.trim(), missingPass = !pass.value;
    setError(user, missingUser ? 'Enter your username.' : '');
    setError(pass, missingPass ? 'Enter your password.' : '');
    if (missingUser || missingPass) {
      e.preventDefault();
      (missingUser ? user : pass).focus();
      return;
    }
    form.classList.add('is-loading');
    if (submit) {
      submit.setAttribute('aria-disabled', 'true');
      submit.querySelector('.btn-label').textContent = 'Logging in…';
    }
    if (status) status.textContent = 'Logging in, please wait.';
  });

  // Coming back with the browser's Back button can restore the page from the cache in its loading state.
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    form.classList.remove('is-loading');
    if (submit) { submit.removeAttribute('aria-disabled'); submit.querySelector('.btn-label').textContent = 'Log in'; }
    if (status) status.textContent = '';
  });
})();
