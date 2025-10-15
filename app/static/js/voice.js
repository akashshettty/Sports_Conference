// SpeechRecognition wrapper with hooks for wake-word and fallback
(function(){
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const supportsSR = !!SpeechRecognition;
  const wakeWord = window.WAKE_WORD || 'hey smashbot';
  const lowercase = s => (s||'').toLowerCase();

  let recognizing = false;
  let active = false; // becomes true after wake word detected
  let userStopped = false;
  let rec = null;

  // Voice modes
  let voiceMode = 'off'; // 'off', 'continuous', 'wake_word', 'ptt'
  let wakeWordActive = false; // true when wake word detected and waiting for command
  let wakeWordTimeout = null;

  // Continuous mode control
  let continuousEnabled = false; // true after start(); false after stop()

  // Dedup/throttle state
  let lastTranscript = '';
  let lastSentAt = 0;
  const SEND_DEBOUNCE_MS = 1200;
  const WAKE_WORD_TIMEOUT = 5000; // 5 seconds to speak command after wake word

  function notifyStatus(){
    window.dispatchEvent(new CustomEvent('voice.status', { 
      detail: { 
        listening: recognizing, 
        mode: voiceMode,
        wakeWordActive: wakeWordActive
      } 
    }));
  }

  function ensureRecognizer(){
    if (rec || !supportsSR) return rec;
    rec = new SpeechRecognition();
    rec.lang = 'en-US';
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++){
        const t = e.results[i][0].transcript.trim();
        const isFinal = e.results[i].isFinal;
        const text = lowercase(t);
        const ww = lowercase(wakeWord);
        const hasWake = text.includes(ww);
        
        // Handle different voice modes
        if (voiceMode === 'wake_word') {
          if (hasWake && !wakeWordActive) {
            // Wake word detected, activate push-to-talk mode
            wakeWordActive = true;
            clearTimeout(wakeWordTimeout);
            wakeWordTimeout = setTimeout(() => {
              wakeWordActive = false;
              notifyStatus();
            }, WAKE_WORD_TIMEOUT);
            notifyStatus();
            
            // If final contains command immediately after wake word
            if (isFinal) {
              const idx = lowercase(t).indexOf(ww);
              const originalRemainder = idx >= 0 ? t.slice(idx + ww.length).replace(/^[,:\s]+/, '').trim() : t;
              if (originalRemainder) {
                const now = Date.now();
                if (originalRemainder !== lastTranscript || (now - lastSentAt) > SEND_DEBOUNCE_MS){
                  lastTranscript = originalRemainder;
                  lastSentAt = now;
                  window.dispatchEvent(new CustomEvent('voice.transcript', {detail: {transcript: originalRemainder}}));
                }
                wakeWordActive = false;
                clearTimeout(wakeWordTimeout);
                notifyStatus();
              }
            }
          } else if (wakeWordActive && isFinal) {
            // In wake word active state, process command
            const now = Date.now();
            if (t && (t !== lastTranscript || (now - lastSentAt) > SEND_DEBOUNCE_MS)){
              lastTranscript = t;
              lastSentAt = now;
              window.dispatchEvent(new CustomEvent('voice.transcript', {detail: {transcript: t}}));
            }
            wakeWordActive = false;
            clearTimeout(wakeWordTimeout);
            notifyStatus();
          }
        } else if (voiceMode === 'continuous') {
          // Original continuous mode logic
          if (!active) {
            if (hasWake) {
              active = true;
              if (isFinal) {
                const idx = lowercase(t).indexOf(ww);
                const originalRemainder = idx >= 0 ? t.slice(idx + ww.length).replace(/^[,:\s]+/, '').trim() : t;
                const now = Date.now();
                if (originalRemainder && (originalRemainder !== lastTranscript || (now - lastSentAt) > SEND_DEBOUNCE_MS)){
                  lastTranscript = originalRemainder;
                  lastSentAt = now;
                  window.dispatchEvent(new CustomEvent('voice.transcript', {detail: {transcript: originalRemainder}}));
                }
                active = false;
                break;
              }
            }
          } else if (isFinal) {
            const now = Date.now();
            if (t && (t !== lastTranscript || (now - lastSentAt) > SEND_DEBOUNCE_MS)){
              lastTranscript = t;
              lastSentAt = now;
              window.dispatchEvent(new CustomEvent('voice.transcript', {detail: {transcript: t}}));
            }
            active = false;
            break;
          }
        }
      }
    };
    rec.onstart = ()=> { recognizing = true; notifyStatus(); };
    rec.onend = ()=> {
      recognizing = false; notifyStatus();
      // Auto-restart only if continuous mode is enabled and not explicitly stopped
      if (continuousEnabled && !userStopped) setTimeout(()=>{ try { rec && rec.start(); } catch(e) {} }, 200);
    };
    rec.onerror = (e)=> {
      // Auto-recover only for continuous mode
      if (continuousEnabled && !userStopped) {
        try { rec && rec.stop(); } catch(_) {}
        setTimeout(()=>{ try { rec && rec.start(); } catch(_) {} }, 400);
      }
    };
    return rec;
  }

  function start(mode = 'continuous'){
    if (!supportsSR) { return; }
    userStopped = false;
    voiceMode = mode;
    continuousEnabled = (mode === 'continuous' || mode === 'wake_word');
    wakeWordActive = false;
    clearTimeout(wakeWordTimeout);
    ensureRecognizer();
    try { rec && rec.start(); } catch(e) { /* already started */ }
  }

  function stop(){
    continuousEnabled = false;
    userStopped = true;
    voiceMode = 'off';
    wakeWordActive = false;
    clearTimeout(wakeWordTimeout);
    try { rec && rec.stop(); } catch(e) {}
  }

  // One-shot listener for push-to-talk (PTT). Resolves with first final transcript or null
  async function listenOnce(timeoutMs = 6000){
    if (!supportsSR) return null;
    return new Promise((resolve) => {
      const one = new SpeechRecognition();
      one.lang = 'en-US';
      one.continuous = false;
      one.interimResults = false;
      let done = false;
      const finish = (val)=>{ if (done) return; done = true; try{ one.stop(); }catch(_){} resolve((val||'').trim()||null); };
      let timer = setTimeout(()=> finish(null), timeoutMs);
      one.onresult = (e)=>{ try{ clearTimeout(timer); }catch(_){}
        const res = e.results && e.results[0] && e.results[0][0] && e.results[0][0].transcript;
        finish(res);
      };
      one.onerror = ()=>{ try{ clearTimeout(timer); }catch(_){} finish(null); };
      one.onend = ()=>{ finish(null); };
      try{ one.start(); } catch(_){ finish(null); }
    });
  }

  // Smart PTT: pause continuous if needed, run one-shot, then resume
  async function listenOnceSmart(timeoutMs = 6000){
    const wasContinuousActive = continuousEnabled && recognizing;
    const currentMode = voiceMode;
    const shouldResume = continuousEnabled; // user preference
    // Temporarily stop continuous to avoid conflicts
    if (recognizing) {
      try { userStopped = true; rec && rec.stop(); } catch(_) {}
      await new Promise(r=>setTimeout(r,150));
    }
    const t = await listenOnce(timeoutMs);
    // Dispatch transcript so existing handler posts to server
    if (t) window.dispatchEvent(new CustomEvent('voice.transcript', {detail: {transcript: t}}));
    // Resume continuous if it was enabled by user
    if (shouldResume) {
      userStopped = false;
      start(currentMode);
    }
    return t;
  }

  // Auto-post transcripts
  window.addEventListener('voice.transcript', async (ev)=>{
    const { transcript } = ev.detail || {};
    if (!transcript) return;
    if (typeof window.matchId === 'number'){
      try {
        await fetch('/api/voice/transcript', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({match_id: window.matchId, transcript})});
      } catch (err) {
        // ignore
      }
    }
  });

  // Hardware / Bluetooth earpods: use Media Session play/pause to trigger PTT
  if ('mediaSession' in navigator && navigator.mediaSession && supportsSR){
    try { 
      navigator.mediaSession.setActionHandler('play', ()=> { 
        console.log('Earpods play button pressed - activating PTT');
        listenOnceSmart(7000); 
      }); 
    } catch(_){}
    try { 
      navigator.mediaSession.setActionHandler('pause', ()=> { 
        console.log('Earpods pause button pressed - activating PTT');
        listenOnceSmart(7000); 
      }); 
    } catch(_){}
  }
  // Fallback: listen for MediaPlayPause key
  window.addEventListener('keydown', (e)=>{
    if (e.code === 'MediaPlayPause' || e.key === 'MediaPlayPause'){
      console.log('Media play/pause key pressed - activating PTT');
      listenOnceSmart(7000);
    }
  });

  // Public API
  window.Voice = { 
    start, 
    stop, 
    isAvailable: () => supportsSR, 
    listenOnce, 
    listenOnceSmart,
    getMode: () => voiceMode,
    setMode: (mode) => { voiceMode = mode; },
    isWakeWordActive: () => wakeWordActive
  };

  // One-time activation helper: after a user gesture, auto-restart on pages
  window.enableAutoVoice = function(mode = 'wake_word'){
    if (!supportsSR) return false;
    start(mode);
    return true;
  };
})();


