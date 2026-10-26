'use strict';
const resendButton = document.getElementById('resend-code');
if (resendButton) {
  const deadline = Date.now() + Number(resendButton.dataset.resendSeconds) * 1000;
  const countdown = document.getElementById('resend-countdown');
  function updateCountdown() {
    const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    resendButton.disabled = remaining > 0;
    countdown.textContent = remaining > 0 ? ` (${remaining}s)` : '';
    return remaining;
  }
  if (updateCountdown() > 0) {
    const timer = window.setInterval(() => {
      if (updateCountdown() === 0) window.clearInterval(timer);
    }, 1000);
  }
}
