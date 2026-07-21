/**
 * Options Tycoon — Sound Effects Module
 * 
 * Uses Web Audio API to generate synthesized sounds for trade events.
 * No external audio files needed.
 */

const AudioCtx = window.AudioContext || window.webkitAudioContext;
let audioCtx = null;
let soundMuted = false;

function getAudioCtx() {
    if (!audioCtx) audioCtx = new AudioCtx();
    return audioCtx;
}

function playSound(type) {
    if (soundMuted) return;
    const ctx = getAudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    switch (type) {
        case 'fill': // Trade executed
            osc.frequency.value = 800;
            osc.type = 'sine';
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.15);
            osc.start();
            osc.stop(ctx.currentTime + 0.15);
            break;

        case 'win': // Position closed at profit
            osc.frequency.value = 600;
            osc.type = 'sine';
            gain.gain.setValueAtTime(0.2, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
            osc.start();
            setTimeout(() => {
                const osc2 = ctx.createOscillator();
                const gain2 = ctx.createGain();
                osc2.connect(gain2);
                gain2.connect(ctx.destination);
                osc2.frequency.value = 900;
                osc2.type = 'sine';
                gain2.gain.setValueAtTime(0.2, ctx.currentTime);
                gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
                osc2.start();
                osc2.stop(ctx.currentTime + 0.3);
            }, 150);
            osc.stop(ctx.currentTime + 0.4);
            break;

        case 'loss': // Position closed at loss
            osc.frequency.value = 300;
            osc.type = 'sawtooth';
            gain.gain.setValueAtTime(0.2, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
            osc.start();
            osc.stop(ctx.currentTime + 0.5);
            break;

        case 'alert': // Risk gate warning
            osc.frequency.value = 1000;
            osc.type = 'square';
            gain.gain.setValueAtTime(0.15, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
            osc.start();
            osc.stop(ctx.currentTime + 0.1);
            setTimeout(() => {
                const o = ctx.createOscillator();
                const g = ctx.createGain();
                o.connect(g);
                g.connect(ctx.destination);
                o.frequency.value = 1000;
                o.type = 'square';
                g.gain.setValueAtTime(0.15, ctx.currentTime);
                g.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
                o.start();
                o.stop(ctx.currentTime + 0.1);
            }, 150);
            break;
    }
}

function toggleMute() {
    soundMuted = !soundMuted;
    const btn = document.getElementById('mute-toggle');
    if (btn) btn.textContent = soundMuted ? '🔇' : '🔊';
}
