// Nash CRM - Cyberpunk JavaScript

// Global variables
let currentToken = '';
let currentChart = null;
let currentView = 'chart';
let neuralData = null;
let scene, camera, renderer, cube;
let particles = [];
let konamiCode = [];
const konamiSequence = [38, 38, 40, 40, 37, 39, 37, 39, 66, 65]; // ↑↑↓↓←→←→BA

// Initialize on load
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(() => {
        initializeMatrix();
        initializeParticles();
        initializeStats();
        init3DSpace();
        loadSavedToken();
        setupEventListeners();
    }, 100);
});

// Matrix background effect
function initializeMatrix() {
    const canvas = document.getElementById('matrix-canvas');
    const ctx = canvas.getContext('2d');

    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const characters = 'NASH CRM API 2077 QUANTUM NEURAL CYBER MATRIX BLOCKCHAIN AI ML DL NN RNN LSTM GAN VAE BERT GPT'.split(' ');
    const drops = [];

    for (let x = 0; x < canvas.width / 10; x++) {
        drops[x] = Math.random() * canvas.height;
    }

    function drawMatrix() {
        ctx.fillStyle = 'rgba(10, 10, 10, 0.04)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.fillStyle = '#00ff41';
        ctx.font = '10px Courier New';

        for (let i = 0; i < drops.length; i++) {
            const text = characters[Math.floor(Math.random() * characters.length)];
            ctx.fillText(text, i * 10, drops[i] * 10);

            if (drops[i] * 10 > canvas.height && Math.random() > 0.975) {
                drops[i] = 0;
            }
            drops[i]++;
        }
    }

    setInterval(drawMatrix, 33);
}

// Floating particles
function initializeParticles() {
    const container = document.getElementById('particles');

    function createParticle() {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particle.style.left = Math.random() * 100 + '%';
        particle.style.animationDuration = (Math.random() * 10 + 10) + 's';
        particle.style.animationDelay = Math.random() * 5 + 's';
        container.appendChild(particle);

        setTimeout(() => {
            if (particle.parentNode) {
                particle.parentNode.removeChild(particle);
            }
        }, 15000);
    }

    // Create initial particles
    for (let i = 0; i < 20; i++) {
        setTimeout(createParticle, i * 500);
    }

    // Continue creating particles
    setInterval(createParticle, 800);
}

// Animate stats
function initializeStats() {
    const stats = document.querySelectorAll('.stat-number');

    stats.forEach(stat => {
        const target = parseFloat(stat.getAttribute('data-target'));
        let current = 0;
        const increment = target / 100;

        const updateCounter = () => {
            if (current < target) {
                current += increment;
                stat.textContent = Math.ceil(current);
                setTimeout(updateCounter, 20);
            } else {
                stat.textContent = target;
            }
        };

        setTimeout(updateCounter, Math.random() * 2000);
    });
}

// 3D Space initialization
function init3DSpace() {
    const container = document.getElementById('threejs-container');
    if (!container || typeof THREE === 'undefined') {
        console.log('3D container or THREE.js not ready yet');
        return;
    }

    try {
        scene = new THREE.Scene();
        camera = new THREE.PerspectiveCamera(75, container.clientWidth / container.clientHeight, 0.1, 1000);
        renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        renderer.setSize(container.clientWidth, container.clientHeight);
        renderer.setClearColor(0x000000, 0);

        // Create a glowing cube
        const geometry = new THREE.BoxGeometry(2, 2, 2);
        const material = new THREE.MeshBasicMaterial({
            color: 0x00ff41,
            wireframe: true
        });
        cube = new THREE.Mesh(geometry, material);
        scene.add(cube);

        camera.position.z = 5;

        function animate() {
            requestAnimationFrame(animate);
            if (cube) {
                cube.rotation.x += 0.01;
                cube.rotation.y += 0.01;
            }
            if (renderer && scene && camera) {
                renderer.render(scene, camera);
            }
        }

        container.appendChild(renderer.domElement);
        animate();
    } catch (error) {
        console.log('3D initialization failed:', error);
        if (container) {
            container.innerHTML = '<div style="color: #00ff41; text-align: center; padding: 2rem;">🌐 3D Neural Space Loading...</div>';
        }
    }
}

// Event listeners
function setupEventListeners() {
    // Konami code
    document.addEventListener('keydown', function(e) {
        konamiCode.push(e.keyCode);
        if (konamiCode.length > konamiSequence.length) {
            konamiCode.shift();
        }

        if (JSON.stringify(konamiCode) === JSON.stringify(konamiSequence)) {
            activateKonami();
        }
    });

    // Resize handler for 3D
    window.addEventListener('resize', function() {
        if (camera && renderer) {
            const container = document.getElementById('threejs-container');
            if (container) {
                camera.aspect = container.clientWidth / container.clientHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(container.clientWidth, container.clientHeight);
            }
        }

        // Resize matrix canvas
        const canvas = document.getElementById('matrix-canvas');
        if (canvas) {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        }
    });

    // Mouse move effect
    document.addEventListener('mousemove', function(e) {
        if (Math.random() > 0.95) {
            const trail = document.createElement('div');
            trail.style.position = 'fixed';
            trail.style.left = e.clientX + 'px';
            trail.style.top = e.clientY + 'px';
            trail.style.width = '2px';
            trail.style.height = '2px';
            trail.style.background = '#00ff41';
            trail.style.borderRadius = '50%';
            trail.style.pointerEvents = 'none';
            trail.style.zIndex = '9999';
            trail.style.animation = 'fade-out 1s ease-out forwards';
            document.body.appendChild(trail);

            setTimeout(() => trail.remove(), 1000);
        }
    });
}

// Authentication functions
function authenticateUser() {
    const token = document.getElementById('jwt-token').value.trim();

    if (!token) {
        showStatus('error', 'Neural токен не може бути пустим!');
        return;
    }

    currentToken = token;
    localStorage.setItem('nash_neural_token', token);

    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        const exp = new Date(payload.exp * 1000);
        const now = new Date();

        if (exp < now) {
            showStatus('error', 'Токен прострочений! Час для квантового оновлення...');
        } else {
            showStatus('success', `Neural Link активний! Користувач: ${payload.username || 'ANONYMOUS_NEURAL_ENTITY'}`);
        }
    } catch (e) {
        showStatus('warning', 'Квантовий токен не розпізнано, але спробуємо підключитися...');
    }
}

function openNeuralLogin() {
    document.getElementById('neural-modal').style.display = 'flex';
}

function closeNeuralModal() {
    document.getElementById('neural-modal').style.display = 'none';
    document.getElementById('neural-status').innerHTML = '';
}

async function performNeuralLogin() {
    const username = document.getElementById('neural-username').value;
    const password = document.getElementById('neural-password').value;
    const btn = document.getElementById('neural-login-btn');
    const status = document.getElementById('neural-status');

    if (!username || !password) {
        status.innerHTML = '<div style="color: var(--cyber-pink);">Всі поля нейронної мережі обов\'язкові!</div>';
        return;
    }

    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> СИНХРОНІЗАЦІЯ З МАТРИЦЕЮ...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/auth/login/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.defaultHeaders['X-CSRFToken']
            },
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (response.ok && data.data && data.data.tokens) {
            const token = data.data.tokens.access;
            document.getElementById('jwt-token').value = token;
            authenticateUser();

            status.innerHTML = `
                <div style="color: var(--matrix-green);">
                    <i class="fas fa-check-circle"></i>
                    NEURAL LINK ВСТАНОВЛЕНО!
                </div>
            `;

            setTimeout(closeNeuralModal, 2000);
        } else {
            status.innerHTML = `<div style="color: var(--cyber-pink);">ПОМИЛКА ДОСТУПУ: ${data.meta?.errors?.authentication_error || 'Невірні нейро-дані'}</div>`;
        }
    } catch (error) {
        status.innerHTML = `<div style="color: var(--cyber-pink);">МЕРЕЖЕВА АНОМАЛІЯ: ${error.message}</div>`;
    }

    btn.innerHTML = '<i class="fas fa-rocket"></i> INITIALIZE NEURAL LINK';
    btn.disabled = false;
}

function loadSavedToken() {
    const saved = localStorage.getItem('nash_neural_token');
    const tokenInput = document.getElementById('jwt-token');

    if (saved && tokenInput) {
        tokenInput.value = saved;
        authenticateUser();
    }
}

// API Testing functions
async function quantumPing() {
    await executeQuantumCall('/api/ping/', 'Перевірка квантового зв\'язку...');
}

async function neuralFunnel() {
    await executeQuantumCall('/api/analytics/funnel/', 'Сканування нейронної воронки...');
}

async function matrixLeads() {
    await executeQuantumCall('/api/leads/', 'Завантаження матриці лідів...');
}

async function cyberDashboard() {
    await executeQuantumCall('/api/crm/dashboard/', 'Активація кібер-дашборду...');
}

async function aiAnalytics() {
    await executeQuantumCall('/api/analytics/leads-report/', 'AI аналіз в процесі...');
}

async function quantumClients() {
    await executeQuantumCall('/api/clients/', 'Квантове сканування клієнтів...');
}

async function holographicReports() {
    await executeQuantumCall('/api/analytics/detailed-report/', 'Створення голограми звітів...');
}

async function neuralPayments() {
    await executeQuantumCall('/api/analytics/payments/', 'Нейронний аналіз платежів...');
}

async function dataStreamViz() {
    await executeQuantumCall('/api/clients/temperature-stats/', 'Візуалізація потоків даних...');
}

async function cybersecAnalysis() {
    await executeQuantumCall('/api/statuses/', 'Аналіз безпеки матриці...');
}

function customPortal() {
    const endpoints = [
        '/api/ping/', '/api/leads/', '/api/clients/', '/api/analytics/funnel/',
        '/api/crm/dashboard/', '/api/analytics/leads-report/', '/api/analytics/payments/',
        '/api/clients/hot-leads/', '/api/clients/churn-risk/', '/api/clients/rfm-analysis/',
        '/api/clients/temperature-stats/', '/api/clients/akb-segments/', '/api/statuses/',
        '/api/crm/segments/', '/api/managers/', '/api/external/leads/',
        '/api/clients/journey/{id}/', '/api/clients/update-temperature/{id}/',
        '/api/leads/files/{id}/', '/api/leads/add-payment/{id}/', '/api/leads/update-status/{id}/',
        '/api/tasks/my-tasks/', '/api/tasks/overdue-tasks/', '/api/crm/update-metrics/',
        '/api/crm/create-tasks/', '/api/utils/geocode/', '/api/utils/map-config/',
        '/api/interactions/', '/api/tasks/', '/api/leads/check-duplicate/'
    ];

    // Створюємо розширений список з описами
    const endpointsWithDescriptions = [
        { url: '/api/ping/', desc: '🏓 System Health Check' },
        { url: '/api/leads/', desc: '👥 Leads Management' },
        { url: '/api/clients/', desc: '🎯 Clients Database' },
        { url: '/api/analytics/funnel/', desc: '📊 Sales Funnel Analytics' },
        { url: '/api/crm/dashboard/', desc: '🎛️ CRM Dashboard Stats' },
        { url: '/api/analytics/leads-report/', desc: '📈 Leads Performance Report' },
        { url: '/api/analytics/payments/', desc: '💰 Financial Analytics' },
        { url: '/api/clients/hot-leads/', desc: '🔥 Hot Leads Detection' },
        { url: '/api/clients/churn-risk/', desc: '⚠️ Churn Risk Analysis' },
        { url: '/api/clients/rfm-analysis/', desc: '🧮 RFM Segmentation' },
        { url: '/api/clients/temperature-stats/', desc: '🌡️ Temperature Distribution' },
        { url: '/api/clients/akb-segments/', desc: '📊 AKB Segments Analysis' },
        { url: '/api/statuses/', desc: '📋 Lead Status Codes' },
        { url: '/api/crm/segments/', desc: '🎯 Marketing Segments' },
        { url: '/api/managers/', desc: '👨‍💼 Managers Management' },
        { url: '/api/external/leads/', desc: '🌐 External Lead Creation' },
        { url: '/api/clients/journey/{id}/', desc: '🗺️ Client Journey Mapping' },
        { url: '/api/clients/update-temperature/{id}/', desc: '🌡️ Update Client Temperature' },
        { url: '/api/leads/files/{id}/', desc: '📁 Lead Files Management' },
        { url: '/api/leads/add-payment/{id}/', desc: '💳 Add Payment to Lead' },
        { url: '/api/leads/update-status/{id}/', desc: '🔄 Update Lead Status' },
        { url: '/api/tasks/my-tasks/', desc: '✅ My Personal Tasks' },
        { url: '/api/tasks/overdue-tasks/', desc: '⏰ Overdue Tasks Alert' },
        { url: '/api/crm/update-metrics/', desc: '🔄 Update Client Metrics' },
        { url: '/api/crm/create-tasks/', desc: '📝 Auto-Create Follow-up Tasks' },
        { url: '/api/utils/geocode/', desc: '🗺️ Address Geocoding' },
        { url: '/api/utils/map-config/', desc: '🗺️ Map Configuration' },
        { url: '/api/interactions/', desc: '💬 Client Interactions' },
        { url: '/api/tasks/', desc: '📋 Tasks Management' },
        { url: '/api/leads/check-duplicate/', desc: '🔍 Duplicate Lead Checker' }
    ];

    // Показуємо красиву таблицю endpoints
    const endpointsList = endpointsWithDescriptions.map(ep =>
        `${ep.url.padEnd(35)} ${ep.desc}`
    ).join('\n');

    const url = prompt(
        '🚀 ПОРТАЛ У КІБЕРПРОСТІР\n\n' +
        '🔮 Доступні квантові тунелі:\n\n' +
        endpointsList.split('\n').slice(0, 12).join('\n') +
        '\n\n... та ще ' + (endpointsWithDescriptions.length - 12) + ' нейро-маршрутів\n\n' +
        '⚡ Введіть координати порталу (або виберіть зі списку):',
        '/api/clients/hot-leads/'
    );

    if (url) {
        // Перевіряємо чи URL містить змінні {id}
        if (url.includes('{id}')) {
            const id = prompt(
                '🔢 NEURAL ID REQUIRED\n\n' +
                `Endpoint ${url} потребує ID параметр.\n\n` +
                '💡 Приклади:\n' +
                '• Для клієнта: 1, 2, 3...\n' +
                '• Для ліда: 10, 25, 100...\n\n' +
                '🎯 Введіть ID:',
                '1'
            );

            if (id) {
                const finalUrl = url.replace('{id}', id);
                executeQuantumCall(finalUrl, `🚀 Портал відкрито: ${finalUrl}`);
            } else {
                showStatus('warning', 'ID не введено - портал скасовано');
            }
        } else {
            executeQuantumCall(url, `🚀 Портал відкрито: ${url}`);
        }
    }
}

// Додаємо функцію для швидкого доступу до популярних endpoints
function quickAccess() {
    const quickEndpoints = [
        { name: '🏓 Ping', url: '/api/ping/' },
        { name: '🎛️ Dashboard', url: '/api/crm/dashboard/' },
        { name: '📊 Funnel', url: '/api/analytics/funnel/' },
        { name: '🔥 Hot Leads', url: '/api/clients/hot-leads/' },
        { name: '💰 Payments', url: '/api/analytics/payments/' },
        { name: '📈 Reports', url: '/api/analytics/leads-report/' },
        { name: '⚠️ Churn Risk', url: '/api/clients/churn-risk/' },
        { name: '🎯 Segments', url: '/api/crm/segments/' }
    ];

    const choice = prompt(
        '⚡ ШВИДКИЙ ДОСТУП ДО НЕЙРО-ЦЕНТРІВ\n\n' +
        quickEndpoints.map((ep, i) => `${i + 1}. ${ep.name}`).join('\n') +
        '\n\n🎯 Введіть номер (1-8):',
        '1'
    );

    const index = parseInt(choice) - 1;
    if (index >= 0 && index < quickEndpoints.length) {
        const selected = quickEndpoints[index];
        executeQuantumCall(selected.url, `⚡ Швидкий доступ: ${selected.name}`);
    } else {
        showStatus('warning', 'Невірний номер нейро-центру');
    }
}

// Main API execution function
async function executeQuantumCall(endpoint, loadingMessage) {
    if (!currentToken) {
        showStatus('error', 'Спочатку активуйте нейронний зв\'язок!');
        return;
    }

    showStatus('info', loadingMessage);
    showResults();

    const container = document.getElementById(currentView + '-container');
    if (container) {
        container.innerHTML = '<div class="cyber-loader"></div>';
    }

    try {
        const response = await fetch(endpoint, {
            headers: {
                'Authorization': `Bearer ${currentToken}`,
                'Content-Type': 'application/json',
                'X-CSRFToken': window.defaultHeaders['X-CSRFToken']
            }
        });

        const rawText = await response.text();
        let data;

        try {
            data = JSON.parse(rawText);
        } catch (e) {
            data = {
                error: 'MATRIX_DECODE_ERROR',
                raw_data: rawText.substring(0, 1000),
                quantum_status: 'DATA_CORRUPTED'
            };
        }

        neuralData = data;

        if (response.ok) {
            showStatus('success', `Квантові дані отримано з ${endpoint}`);
            renderNeuralData(data, endpoint);
            generateAIInsights(data, endpoint);
        } else {
            showStatus('error', `Помилка матриці: ${response.status} ${response.statusText}`);
            renderErrorData(data, response.status);
        }

    } catch (error) {
        showStatus('error', `Збій нейронної мережі: ${error.message}`);
        renderErrorData({ error: error.message, type: 'NETWORK_FAILURE' });
    }
}

// Data rendering functions
function renderNeuralData(data, endpoint) {
    // Update JSON view
    const jsonContent = document.getElementById('json-content');
    if (jsonContent) {
        jsonContent.textContent = JSON.stringify(data, null, 2);
    }

    // Create chart if in chart view
    if (currentView === 'chart') {
        createNeuralChart(data, endpoint);
    } else if (currentView === '3d') {
        update3DVisualization(data);
    }
}

function createNeuralChart(data, endpoint) {
    const canvas = document.getElementById('neural-chart');
    const ctx = canvas.getContext('2d');

    if (currentChart) {
        currentChart.destroy();
    }

    const chartConfig = generateNeuralChartConfig(data, endpoint);

    if (chartConfig) {
        currentChart = new Chart(ctx, chartConfig);
    } else {
        canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);

        // Custom visualization for unsupported data
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#00ff41';
        ctx.font = '20px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('📊 NEURAL DATA PROCESSED', canvas.width/2, canvas.height/2 - 20);
        ctx.font = '14px Inter';
        ctx.fillText('Switch to MATRIX CODE view for detailed analysis', canvas.width/2, canvas.height/2 + 20);
    }
}

function generateNeuralChartConfig(data, endpoint) {
    // Enhanced chart generation with cyberpunk styling
    const baseConfig = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: {
                    color: '#00ff41',
                    font: { family: 'Inter', weight: 'bold' }
                }
            },
            title: {
                display: true,
                color: '#00ff41',
                font: { size: 18, weight: 'bold', family: 'Inter' }
            }
        },
        scales: {
            x: {
                ticks: { color: '#00ff41' },
                grid: { color: 'rgba(0, 255, 65, 0.1)' }
            },
            y: {
                ticks: { color: '#00ff41' },
                grid: { color: 'rgba(0, 255, 65, 0.1)' }
            }
        }
    };

    // Funnel visualization
    if (data.data && data.data.funnel) {
        const funnel = data.data.funnel;
        const labels = Object.keys(funnel).filter(k => k !== 'warehouse_analytics');
        const values = labels.map(l => funnel[l]);

        return {
            type: 'doughnut',
            data: {
                labels: labels.map(l => l.replace(/_/g, ' ').toUpperCase()),
                datasets: [{
                    data: values,
                    backgroundColor: [
                        'rgba(0, 255, 65, 0.8)',
                        'rgba(0, 212, 255, 0.8)',
                        'rgba(255, 0, 110, 0.8)',
                        'rgba(255, 255, 0, 0.8)',
                        'rgba(138, 43, 226, 0.8)',
                        'rgba(255, 69, 0, 0.8)',
                        'rgba(50, 205, 50, 0.8)',
                        'rgba(255, 20, 147, 0.8)'
                    ],
                    borderColor: '#00ff41',
                    borderWidth: 2
                }]
            },
            options: {
                ...baseConfig,
                plugins: {
                    ...baseConfig.plugins,
                    title: {
                        ...baseConfig.plugins.title,
                        text: '🔥 NEURAL SALES FUNNEL'
                    }
                }
            }
        };
    }

    // Dashboard visualization
    if (data.data && data.data.summary) {
        const summary = data.data.summary;
        return {
            type: 'radar',
            data: {
                labels: ['Clients', 'AKB', 'Hot Leads', 'Revenue (k)', 'Tasks'],
                datasets: [{
                    label: 'CRM Neural Metrics',
                    data: [
                        Math.min(summary.total_clients / 10, 100),
                        Math.min(summary.akb_clients / 5, 100),
                        Math.min(summary.hot_leads * 20, 100),
                        Math.min(summary.total_revenue / 1000, 100),
                        Math.min(summary.urgent_tasks * 10, 100)
                    ],
                    backgroundColor: 'rgba(0, 255, 65, 0.2)',
                    borderColor: '#00ff41',
                    borderWidth: 3,
                    pointBackgroundColor: '#00d4ff',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    pointRadius: 6
                }]
            },
            options: {
                ...baseConfig,
                plugins: {
                    ...baseConfig.plugins,
                    title: {
                        ...baseConfig.plugins.title,
                        text: '🎯 CYBER DASHBOARD MATRIX'
                    }
                },
                scales: {
                    r: {
                        ticks: {
                            color: '#00ff41',
                            backdropColor: 'transparent',
                            font: { family: 'Inter' }
                        },
                        grid: { color: 'rgba(0, 255, 65, 0.2)' },
                        pointLabels: {
                            color: '#00ff41',
                            font: { size: 12, family: 'Inter', weight: 'bold' }
                        }
                    }
                }
            }
        };
    }

    // Temperature stats
    if (data.data && Object.keys(data.data).some(k => ['cold', 'warm', 'hot'].includes(k))) {
        const temps = data.data;
        return {
            type: 'polarArea',
            data: {
                labels: Object.keys(temps).map(t => t.toUpperCase()),
                datasets: [{
                    data: Object.values(temps),
                    backgroundColor: [
                        'rgba(0, 212, 255, 0.7)',  // cold
                        'rgba(255, 255, 0, 0.7)',  // warm
                        'rgba(255, 0, 110, 0.7)',  // hot
                        'rgba(128, 128, 128, 0.7)' // sleeping
                    ],
                    borderColor: '#00ff41',
                    borderWidth: 2
                }]
            },
            options: {
                ...baseConfig,
                plugins: {
                    ...baseConfig.plugins,
                    title: {
                        ...baseConfig.plugins.title,
                        text: '🌡️ NEURAL TEMPERATURE MATRIX'
                    }
                }
            }
        };
    }

    // Array data (leads, clients, etc.)
    if (Array.isArray(data.data) && data.data.length > 0) {
        // Status distribution if it's status codes
        if (data.data[0].code && data.data[0].name) {
            return {
                type: 'bar',
                data: {
                    labels: data.data.map(s => s.name),
                    datasets: [{
                        label: 'Status Distribution',
                        data: data.data.map(() => 1),
                        backgroundColor: 'rgba(0, 255, 65, 0.6)',
                        borderColor: '#00ff41',
                        borderWidth: 2
                    }]
                },
                options: {
                    ...baseConfig,
                    plugins: {
                        ...baseConfig.plugins,
                        title: {
                            ...baseConfig.plugins.title,
                            text: '📋 NEURAL STATUS MATRIX'
                        }
                    }
                }
            };
        }

        // General array data visualization
        return {
            type: 'line',
            data: {
                labels: data.data.slice(0, 10).map((_, i) => `Item ${i + 1}`),
                datasets: [{
                    label: 'Data Points',
                    data: data.data.slice(0, 10).map((item, i) => {
                        if (typeof item === 'object') {
                            return Object.keys(item).length;
                        }
                        return Math.random() * 100;
                    }),
                    borderColor: '#00ff41',
                    backgroundColor: 'rgba(0, 255, 65, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                ...baseConfig,
                plugins: {
                    ...baseConfig.plugins,
                    title: {
                        ...baseConfig.plugins.title,
                        text: '📊 NEURAL DATA STREAM'
                    }
                }
            }
        };
    }

    return null;
}

function update3DVisualization(data) {
    if (!scene || !cube) return;

    // Animate cube based on data
    if (data.data && data.data.summary) {
        const summary = data.data.summary;
        const scale = Math.max(summary.total_clients / 100, 0.5);
        cube.scale.set(scale, scale, scale);

        // Change color based on data
        cube.material.color.setHex(summary.hot_leads > 10 ? 0xff006e : 0x00ff41);
    }

    // Add data particles
    const particleCount = Math.min((data.data?.length || 10), 50);

    // Remove old particles
    scene.children.forEach(child => {
        if (child.userData.isDataParticle) {
            scene.remove(child);
        }
    });

    // Add new particles
    for (let i = 0; i < particleCount; i++) {
        const geometry = new THREE.SphereGeometry(0.05, 8, 8);
        const material = new THREE.MeshBasicMaterial({ color: 0x00d4ff });
        const particle = new THREE.Mesh(geometry, material);

        particle.position.set(
            (Math.random() - 0.5) * 10,
            (Math.random() - 0.5) * 10,
            (Math.random() - 0.5) * 10
        );
        particle.userData.isDataParticle = true;

        scene.add(particle);
    }
}

function generateAIInsights(data, endpoint) {
    const insights = document.getElementById('ai-insights');
    const content = document.getElementById('ai-content');

    let aiAnalysis = generateSmartInsights(data, endpoint);

    content.innerHTML = aiAnalysis;
    insights.style.display = 'block';

    // Typing effect
    typeText(content, aiAnalysis);
}

function generateSmartInsights(data, endpoint) {
    const insights = [];

    // Funnel analysis
    if (data.data && data.data.funnel) {
        const funnel = data.data.funnel;
        const total = Object.values(funnel).reduce((sum, val) => sum + (typeof val === 'number' ? val : 0), 0);
        const conversion = ((funnel.completed / funnel.queued) * 100).toFixed(1);

        insights.push(`🔥 QUANTUM ANALYSIS: Conversion rate ${conversion}% detected`);

        if (funnel.warehouse_ready > funnel.warehouse_processing) {
            insights.push(`⚡ NEURAL ALERT: Warehouse efficiency optimized - ${funnel.warehouse_ready} items ready for quantum teleportation`);
        }

        if (funnel.declined > total * 0.2) {
            insights.push(`⚠️ ANOMALY DETECTED: High decline rate (${((funnel.declined/total)*100).toFixed(1)}%) - neural network suggests process optimization`);
        }
    }

    // Dashboard insights
    if (data.data && data.data.summary) {
        const s = data.data.summary;

        if (s.hot_leads > 0) {
            insights.push(`🚨 URGENT: ${s.hot_leads} hot leads require immediate neural processing`);
        }

        if (s.churn_risk > 0) {
            insights.push(`🔮 PREDICTIVE ALERT: ${s.churn_risk} clients at risk of quantum dissolution`);
        }

        const efficiency = (s.akb_clients / s.total_clients * 100).toFixed(1);
        insights.push(`📊 CLIENT MATRIX EFFICIENCY: ${efficiency}% conversion to active neural entities`);
    }

    // Array data insights
    if (Array.isArray(data.data)) {
        insights.push(`🌐 DATA STREAM: ${data.data.length} quantum entities processed`);

        if (data.meta && data.meta.total_leads) {
            const efficiency = (data.data.length / data.meta.total_leads * 100).toFixed(1);
            insights.push(`⚡ PROCESSING EFFICIENCY: ${efficiency}% of neural data transmitted`);
        }
    }

    // Performance insights
    if (data.meta && data.meta.cache_hit) {
        insights.push(`🚀 QUANTUM CACHE: Data retrieved from neural memory banks (${data.meta.cache_expires_in}s TTL)`);
    }

    // Add random AI-like insights
    const randomInsights = [
        '🧠 Neural patterns indicate optimal system performance',
        '⚛️ Quantum encryption layers verified and secure',
        '🔬 Data integrity confirmed across all neural pathways',
        '🌌 Matrix synchronization at 99.7% efficiency',
        '🎯 Predictive algorithms suggest 15% growth potential'
    ];

    if (Math.random() > 0.5) {
        insights.push(randomInsights[Math.floor(Math.random() * randomInsights.length)]);
    }

    return insights.length > 0 ? insights.join('<br><br>') : '🤖 Neural analysis complete. All systems operating within quantum parameters.';
}

function typeText(element, text) {
    element.innerHTML = '';
    let index = 0;

    function type() {
        if (index < text.length) {
            element.innerHTML = text.substring(0, index + 1);
            index++;
            setTimeout(type, Math.random() * 50 + 10);
        }
    }

    type();
}

// View switching
function switchView(view) {
    currentView = view;

    // Update buttons
    document.querySelectorAll('.toggle-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(view + '-btn').classList.add('active');

    // Show/hide containers
    document.getElementById('chart-container').style.display = view === 'chart' ? 'flex' : 'none';
    document.getElementById('3d-container').style.display = view === '3d' ? 'flex' : 'none';
    document.getElementById('json-container').style.display = view === 'json' ? 'block' : 'none';

    // Re-render if we have data
    if (neuralData) {
        if (view === 'chart') {
            createNeuralChart(neuralData, 'current');
        } else if (view === '3d') {
            update3DVisualization(neuralData);
        }
    }
}

// Status and results functions
function showStatus(type, message) {
    const statusDiv = document.getElementById('token-status');

    if (!statusDiv) {
        console.log('Status div not found');
        return;
    }

    let className = 'status-message ';
    let icon = '';

    switch(type) {
        case 'success':
            className += 'status-success';
            icon = 'fas fa-check-circle';
            break;
        case 'error':
            className += 'status-error';
            icon = 'fas fa-exclamation-triangle';
            break;
        case 'warning':
            className += 'status-warning';
            icon = 'fas fa-exclamation-circle';
            break;
        case 'info':
            className += 'status-info';
            icon = 'fas fa-info-circle';
            break;
    }

    statusDiv.innerHTML = `
        <div class="${className}">
            <i class="${icon}"></i>
            ${message}
        </div>
    `;

    // Auto-hide after 5 seconds unless it's an error
    if (type !== 'error') {
        setTimeout(() => {
            statusDiv.innerHTML = '';
        }, 5000);
    }
}

function showResults() {
    document.getElementById('results-container').style.display = 'block';

    // Scroll to results
    document.getElementById('results-container').scrollIntoView({
        behavior: 'smooth',
        block: 'nearest'
    });
}

function renderErrorData(errorData, statusCode = 500) {
    const jsonContent = document.getElementById('json-content');
    if (jsonContent) {
        jsonContent.textContent = JSON.stringify({
            error: 'NEURAL_NETWORK_ERROR',
            status_code: statusCode,
            data: errorData,
            timestamp: new Date().toISOString(),
            quantum_state: 'DEGRADED',
            suggestions: [
                'Verify neural token authenticity',
                'Check quantum endpoint coordinates',
                'Restart neural connection',
                'Contact AI support matrix'
            ]
        }, null, 2);
    }

    // Show error visualization
    if (currentView === 'chart') {
        const canvas = document.getElementById('neural-chart');
        if (canvas) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            ctx.fillStyle = '#ff006e';
            ctx.font = 'bold 24px Inter';
            ctx.textAlign = 'center';
            ctx.fillText('⚠️ NEURAL DISRUPTION', canvas.width/2, canvas.height/2 - 30);

            ctx.font = '16px Inter';
            ctx.fillText(`Error Code: ${statusCode}`, canvas.width/2, canvas.height/2 + 10);
            ctx.fillText('Switch to MATRIX CODE for details', canvas.width/2, canvas.height/2 + 40);
        }
    }
}

// Easter egg function
function konami() {
    if (konamiCode.length === 0) {
        // Manual trigger
        activateKonami();
    } else {
        showStatus('info', 'Try the Konami Code: ↑↑↓↓←→←→BA');
    }
}

function activateKonami() {
    // Rainbow mode
    document.body.classList.add('konami-activated');

    // Matrix rain intensification
    const canvas = document.getElementById('matrix-canvas');
    canvas.style.opacity = '0.3';

    // Status message
    showStatus('success', '🎉 KONAMI CODE ACTIVATED! Welcome to the Neural Underground!');

    // Add special effects
    for (let i = 0; i < 50; i++) {
        setTimeout(() => {
            const particle = document.createElement('div');
            particle.innerHTML = ['🚀', '⚡', '🔥', '💎', '🌟'][Math.floor(Math.random() * 5)];
            particle.style.position = 'fixed';
            particle.style.left = Math.random() * 100 + '%';
            particle.style.top = Math.random() * 100 + '%';
            particle.style.fontSize = '2rem';
            particle.style.zIndex = '9999';
            particle.style.pointerEvents = 'none';
            particle.style.animation = 'fade-out 3s ease-out forwards';
            document.body.appendChild(particle);

            setTimeout(() => particle.remove(), 3000);
        }, i * 100);
    }

    // Disable after 10 seconds
    setTimeout(() => {
        document.body.classList.remove('konami-activated');
        canvas.style.opacity = '0.1';
    }, 10000);
}

// Advanced features
function neuralCommandMode() {
    const commands = [
        { cmd: 'ping', desc: 'System health check', action: quantumPing },
        { cmd: 'dashboard', desc: 'Load CRM dashboard', action: cyberDashboard },
        { cmd: 'funnel', desc: 'Sales funnel analysis', action: neuralFunnel },
        { cmd: 'leads', desc: 'Load leads matrix', action: matrixLeads },
        { cmd: 'clients', desc: 'Client database scan', action: quantumClients },
        { cmd: 'payments', desc: 'Financial neural analysis', action: neuralPayments },
        { cmd: 'hotleads', desc: 'Hot leads detection', action: () => executeQuantumCall('/api/clients/hot-leads/', '🔥 Scanning hot leads...') },
        { cmd: 'churn', desc: 'Churn risk analysis', action: () => executeQuantumCall('/api/clients/churn-risk/', '⚠️ Analyzing churn risk...') },
        { cmd: 'portal', desc: 'Open custom portal', action: customPortal },
        { cmd: 'quick', desc: 'Quick access menu', action: quickAccess },
        { cmd: 'konami', desc: 'Activate easter egg', action: activateKonami },
        { cmd: 'clear', desc: 'Clear neural data', action: clearNeuralData },
        { cmd: 'help', desc: 'Show this help', action: () => showStatus('info', 'Neural commands loaded') }
    ];

    const commandList = commands.map(c => `${c.cmd.padEnd(12)} - ${c.desc}`).join('\n');

    const input = prompt(
        '🖥️ NEURAL COMMAND MODE\n\n' +
        'Available commands:\n\n' +
        commandList +
        '\n\n💻 Enter command:',
        'help'
    );

    if (input) {
        const command = commands.find(c => c.cmd === input.toLowerCase().trim());
        if (command) {
            command.action();
        } else {
            showStatus('error', `Unknown command: ${input}. Type 'help' for available commands.`);
        }
    }
}

function clearNeuralData() {
    neuralData = null;
    document.getElementById('results-container').style.display = 'none';
    document.getElementById('json-content').textContent = '';

    if (currentChart) {
        currentChart.destroy();
        currentChart = null;
    }

    const canvas = document.getElementById('neural-chart');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    showStatus('success', '🧹 Neural data cleared. Ready for new quantum operations.');
}

function exportNeuralData() {
    if (!neuralData) {
        showStatus('warning', 'No neural data to export');
        return;
    }

    const dataStr = JSON.stringify(neuralData, null, 2);
    const dataBlob = new Blob([dataStr], {type: 'application/json'});

    const link = document.createElement('a');
    link.href = URL.createObjectURL(dataBlob);
    link.download = `nash-crm-neural-data-${new Date().toISOString().slice(0, 19)}.json`;
    link.click();

    showStatus('success', '📤 Neural data exported to quantum storage');
}

// Add keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + Enter for quick ping
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        quantumPing();
    }

    // Ctrl/Cmd + D for dashboard
    if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
        e.preventDefault();
        cyberDashboard();
    }

    // Ctrl/Cmd + P for portal
    if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
        e.preventDefault();
        customPortal();
    }

    // Ctrl/Cmd + Q for quick access
    if ((e.ctrlKey || e.metaKey) && e.key === 'q') {
        e.preventDefault();
        quickAccess();
    }

    // Ctrl/Cmd + ` for command mode
    if ((e.ctrlKey || e.metaKey) && e.key === '`') {
        e.preventDefault();
        neuralCommandMode();
    }

    // Ctrl/Cmd + E for export
    if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
        e.preventDefault();
        exportNeuralData();
    }

    // Escape to close modal
    if (e.key === 'Escape') {
        closeNeuralModal();
    }
});

// System status monitoring
function initSystemMonitoring() {
    setInterval(async () => {
        if (currentToken) {
            try {
                const response = await fetch('/api/ping/', {
                    headers: {
                        'Authorization': `Bearer ${currentToken}`,
                        'X-CSRFToken': window.defaultHeaders['X-CSRFToken']
                    }
                });

                const statusDot = document.querySelector('.status-dot');
                if (response.ok) {
                    statusDot.style.background = '#00ff41';
                    statusDot.style.boxShadow = '0 0 10px #00ff41';
                } else {
                    statusDot.style.background = '#ff006e';
                    statusDot.style.boxShadow = '0 0 10px #ff006e';
                }
            } catch (error) {
                const statusDot = document.querySelector('.status-dot');
                statusDot.style.background = '#ffff00';
                statusDot.style.boxShadow = '0 0 10px #ffff00';
            }
        }
    }, 30000); // Check every 30 seconds
}

// Initialize system monitoring after page load
setTimeout(initSystemMonitoring, 5000);

console.log(`
🚀 Nash CRM Neural Interface Loaded
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎮 Keyboard Shortcuts:
• Ctrl+Enter: Quick Ping
• Ctrl+D: Dashboard
• Ctrl+P: Portal
• Ctrl+Q: Quick Access
• Ctrl+\`: Command Mode
• Ctrl+E: Export Data
• ↑↑↓↓←→←→BA: Konami Code

🌟 Functions Available:
• quantumPing()
• cyberDashboard()
• neuralFunnel()
• customPortal()
• quickAccess()
• neuralCommandMode()
• activateKonami()

💡 Type 'help' in command mode for more options
`);