/**
 * Options Tycoon — Tester Feedback Widget
 * 
 * Adds a floating "Report Issue" button on every page.
 * Testers can submit bugs, suggestions, and test results.
 */

(function() {
    // Inject floating button + modal
    const widget = document.createElement('div');
    widget.innerHTML = `
        <button id="feedback-btn" style="
            position: fixed; bottom: 20px; right: 20px; z-index: 9998;
            background: #ff9100; color: #000; border: none; border-radius: 50px;
            padding: 12px 20px; font-size: 13px; font-weight: 700; cursor: pointer;
            box-shadow: 0 4px 16px rgba(255,145,0,0.4);
            transition: transform 0.15s;
        ">🐛 Report Issue</button>

        <div id="feedback-modal" style="
            display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7); z-index: 9999;
            display: none; align-items: center; justify-content: center;
        ">
            <div style="
                background: #1a2332; border: 1px solid #2d3748; border-radius: 10px;
                padding: 28px; max-width: 440px; width: 90%; color: #e0e0e0;
            ">
                <h3 style="margin-bottom:16px; font-size:1.1rem;">🐛 Tester Feedback</h3>
                <div style="margin-bottom:12px;">
                    <label style="font-size:11px; color:#8b9bb4; display:block; margin-bottom:4px;">Your Name</label>
                    <input id="fb-name" type="text" placeholder="Tester name" style="width:100%; padding:8px; background:#0d1117; border:1px solid #2d3748; border-radius:6px; color:#e0e0e0; font-size:13px;">
                </div>
                <div style="margin-bottom:12px;">
                    <label style="font-size:11px; color:#8b9bb4; display:block; margin-bottom:4px;">Category</label>
                    <select id="fb-category" style="width:100%; padding:8px; background:#0d1117; border:1px solid #2d3748; border-radius:6px; color:#e0e0e0; font-size:13px;">
                        <option value="bug">🐛 Bug — Something broken</option>
                        <option value="confusion">❓ Confusion — Didn't understand</option>
                        <option value="suggestion">💡 Suggestion — Could be better</option>
                        <option value="positive">👍 Positive — This works great</option>
                        <option value="test_result">✅ Test Result — Completed a test</option>
                    </select>
                </div>
                <div style="margin-bottom:12px;">
                    <label style="font-size:11px; color:#8b9bb4; display:block; margin-bottom:4px;">Severity</label>
                    <select id="fb-severity" style="width:100%; padding:8px; background:#0d1117; border:1px solid #2d3748; border-radius:6px; color:#e0e0e0; font-size:13px;">
                        <option value="low">Low — Minor issue</option>
                        <option value="medium" selected>Medium — Noticeable</option>
                        <option value="high">High — Blocks usage</option>
                        <option value="critical">Critical — App crashes</option>
                    </select>
                </div>
                <div style="margin-bottom:16px;">
                    <label style="font-size:11px; color:#8b9bb4; display:block; margin-bottom:4px;">Description</label>
                    <textarea id="fb-description" rows="4" placeholder="What happened? What did you expect?" style="width:100%; padding:8px; background:#0d1117; border:1px solid #2d3748; border-radius:6px; color:#e0e0e0; font-size:13px; resize:vertical;"></textarea>
                </div>
                <div style="display:flex; gap:10px; justify-content:flex-end;">
                    <button id="fb-cancel" style="padding:8px 16px; background:#2d3748; color:#e0e0e0; border:none; border-radius:6px; cursor:pointer; font-size:13px;">Cancel</button>
                    <button id="fb-submit" style="padding:8px 16px; background:#00c853; color:#000; border:none; border-radius:6px; cursor:pointer; font-size:13px; font-weight:700;">Submit</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(widget);

    const btn = document.getElementById('feedback-btn');
    const modal = document.getElementById('feedback-modal');
    const cancelBtn = document.getElementById('fb-cancel');
    const submitBtn = document.getElementById('fb-submit');

    btn.addEventListener('click', () => {
        modal.style.display = 'flex';
        // Auto-fill name from localStorage
        const saved = localStorage.getItem('ot_tester_name');
        if (saved) document.getElementById('fb-name').value = saved;
    });

    cancelBtn.addEventListener('click', () => { modal.style.display = 'none'; });
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.style.display = 'none'; });

    submitBtn.addEventListener('click', async () => {
        const name = document.getElementById('fb-name').value.trim();
        const category = document.getElementById('fb-category').value;
        const severity = document.getElementById('fb-severity').value;
        const description = document.getElementById('fb-description').value.trim();

        if (!name || !description) {
            alert('Please fill in your name and description.');
            return;
        }

        localStorage.setItem('ot_tester_name', name);

        try {
            const res = await fetch('/api/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tester_name: name,
                    category: category,
                    page: window.location.pathname,
                    description: description,
                    severity: severity,
                }),
            });

            if (res.ok) {
                alert('✅ Feedback submitted! Thank you.');
                document.getElementById('fb-description').value = '';
                modal.style.display = 'none';
            } else {
                alert('Failed to submit. Try again.');
            }
        } catch (e) {
            alert('Error: ' + e.message);
        }
    });
})();
