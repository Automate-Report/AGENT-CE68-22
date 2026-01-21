# เก็บ Script สำหรับ Inject ลง Browser

MONKEY_PATCH_SCRIPT = """
    // ฟังก์ชันวาดกล่องแดง
    window.drawFakeAlert = function(type, msg) {
        const root = document.body || document.documentElement;
        if (!root) return;
        
        const div = document.createElement('div');
        div.style.cssText = `
            position: fixed !important;
            top: 20px !important;
            left: 50% !important;
            transform: translateX(-50%) !important;
            background-color: #ffcccc !important;
            border: 3px solid red !important;
            color: red !important;
            padding: 20px !important;
            font-weight: bold !important;
            font-size: 16px !important;
            font-family: sans-serif !important;
            z-index: 2147483647 !important;
            box-shadow: 0 10px 20px rgba(0,0,0,0.5) !important;
            pointer-events: none !important;
        `;
        div.innerText = '🚨 DOM XSS DETECTED! (' + type + '): ' + msg;
        root.appendChild(div);
    };

    // เขียนทับ alert, confirm, prompt
    window.alert = function(msg) {
        window.drawFakeAlert('Alert', msg);
        console.log('__XSS_DETECTED__:' + msg);
    };
    window.confirm = function(msg) {
        window.drawFakeAlert('Confirm', msg);
        console.log('__XSS_DETECTED__:' + msg);
        return true;
    };
    window.prompt = function(msg) {
        window.drawFakeAlert('Prompt', msg);
        console.log('__XSS_DETECTED__:' + msg);
        return "test";
    };
"""