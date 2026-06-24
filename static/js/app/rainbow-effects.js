/** Rainbow-theme extras: success confetti (no dependency). */

const CONFETTI_COLORS = [
    "#ff3366",
    "#ff9933",
    "#ffee33",
    "#33ff99",
    "#33ddff",
    "#aa66ff",
    "#ff66cc",
];

function isRainbowThemeActive() {
    return document.body.classList.contains("theme-rainbow")
        || document.body.classList.contains("theme-rainbow-light");
}

function launchRainbowConfetti() {
    if (!isRainbowThemeActive()) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.cssText = [
        "position:fixed",
        "inset:0",
        "width:100%",
        "height:100%",
        "pointer-events:none",
        "z-index:10001",
    ].join(";");
    document.body.appendChild(canvas);

    const ctx = canvas.getContext("2d");
    if (!ctx) {
        canvas.remove();
        return;
    }

    const resize = () => {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    };
    resize();

    const count = 72;
    const particles = Array.from({ length: count }, () => ({
        x: canvas.width * (0.25 + Math.random() * 0.5),
        y: canvas.height * 0.12 + Math.random() * 40,
        vx: (Math.random() - 0.5) * 7,
        vy: 2 + Math.random() * 5,
        w: 5 + Math.random() * 5,
        h: 3 + Math.random() * 4,
        rot: Math.random() * Math.PI,
        spin: (Math.random() - 0.5) * 0.25,
        color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
        life: 1,
    }));

    const start = performance.now();
    const duration = 2400;

    function frame(now) {
        const elapsed = now - start;
        const fade = Math.max(0, 1 - elapsed / duration);
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        for (const p of particles) {
            p.x += p.vx;
            p.y += p.vy;
            p.vy += 0.12;
            p.rot += p.spin;
            p.life = fade;

            ctx.save();
            ctx.translate(p.x, p.y);
            ctx.rotate(p.rot);
            ctx.globalAlpha = p.life;
            ctx.fillStyle = p.color;
            ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
            ctx.restore();
        }

        if (elapsed < duration) {
            requestAnimationFrame(frame);
        } else {
            canvas.remove();
            window.removeEventListener("resize", resize);
        }
    }

    window.addEventListener("resize", resize);
    requestAnimationFrame(frame);
}
