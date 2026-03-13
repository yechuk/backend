/**
 * MLB 선수 시뮬레이션 — 스탯 조정 시 예측 가치 실시간 계산 (플레이스홀더)
 * 실제 모델 연동 시 API 호출로 대체
 */
(function() {
    function getInputValues() {
        const avg = parseFloat(document.getElementById('simAvg')?.value) || 0.28;
        const hr = parseInt(document.getElementById('simHr')?.value, 10) || 30;
        const ops = parseFloat(document.getElementById('simOps')?.value) || 0.85;
        return { avg, hr, ops };
    }

    /**
     * 플레이스홀더 공식: baseValue * (avg/0.28) * (hr/30) * (ops/0.85)
     * 실제 구현 시 MRP 모델 또는 API 호출로 대체
     */
    function calculatePredictedValue(avg, hr, ops) {
        const baseValue = 25000000;
        const avgFactor = (avg || 0.28) / 0.28;
        const hrFactor = (hr || 30) / 30;
        const opsFactor = (ops || 0.85) / 0.85;
        return Math.round(baseValue * avgFactor * hrFactor * opsFactor);
    }

    function updateDisplay() {
        const { avg, hr, ops } = getInputValues();
        const value = calculatePredictedValue(avg, hr, ops);

        const avgValEl = document.getElementById('simAvgVal');
        if (avgValEl) avgValEl.textContent = avg.toFixed(3);

        const valueEl = document.getElementById('simValue');
        if (valueEl) valueEl.textContent = '$' + value.toLocaleString();
    }

    function init() {
        const avgSlider = document.getElementById('simAvg');
        const hrInput = document.getElementById('simHr');
        const opsInput = document.getElementById('simOps');

        if (avgSlider) {
            avgSlider.addEventListener('input', updateDisplay);
        }
        if (hrInput) {
            hrInput.addEventListener('input', updateDisplay);
            hrInput.addEventListener('change', updateDisplay);
        }
        if (opsInput) {
            opsInput.addEventListener('input', updateDisplay);
            opsInput.addEventListener('change', updateDisplay);
        }

        updateDisplay();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
