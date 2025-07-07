function boolIcon(val) {
    return val ? "✅" : "❌";
}

function translate(key) {
    const dict = {
        "view": "Перегляд",
        "create": "Створення",
        "edit": "Редагування",
        "delete": "Видалення",
        "change_status": "Зміна статусу",
        "assign_manager": "Призначення менеджера",
        "view_payments": "Перегляд оплат",
        "view_analytics": "Перегляд аналітики",
        "export": "Експорт",
        "add": "Додавання",
        "user_management": "Користувачі",
        "system_settings": "Системні налаштування",
        "database_access": "Доступ до БД",
        "logs": "Логи",
        "bulk_operations": "Масові дії",
        "assign_leads": "Призначення лідів",
        "team_stats": "Статистика команди",
        "dashboard": "Дашборд",
        "admin_panel": "Адмін-панель",
        "advanced_filters": "Розширені фільтри",
        "bulk_edit": "Масове редагування",
        "export_data": "Експорт даних",
        "can_change_status": "Може змінювати статуси",
        "warehouse_operations": "Складські дії",
        "can_complete": "Може завершувати",
        "can_decline": "Може відхиляти"
    };
    return dict[key] || key;
}

function formatBlock(title, obj) {
    let html = `<div style="border:1px solid #00ff41;padding:1rem;margin-bottom:1rem;border-radius:10px;"><h3>${title}</h3><table style='width:100%;margin-top:10px;'>`;
    for (let key in obj) {
        html += `<tr><td style='padding:4px;'>${translate(key)}</td><td>${boolIcon(obj[key])}</td></tr>`;
    }
    html += "</table></div>";
    return html;
}

async function authLogin() {
    const u = document.getElementById("username").value.trim();
    const p = document.getElementById("password").value.trim();
    const result = document.getElementById("login-result");
    const grid = document.getElementById("permissions-grid");
    const roleDiv = document.getElementById("role-info");
    result.innerText = "⏳ Авторизація...";
    grid.innerHTML = "";
    roleDiv.innerHTML = "";

    try {
        const res = await fetch("/api/auth/token/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: u, password: p })
        });

        const data = await res.json();
        if (!res.ok) {
            result.innerText = "❌ Помилка: " + (data.meta?.errors?.authentication_error || "невірні дані");
            return;
        }

        const user = data.data.user;
        const perms = user.frontend_permissions;
        const status = user.status_permissions;
        const stats = user.stats;

        result.innerText = `✅ Авторизовано: ${user.full_name} (${user.role.name})`;

        roleDiv.innerHTML = `
            <div style="padding: 0.5rem 1rem; background: ${user.role.color}; color:black; display:inline-block; border-radius:5px;">
                ${user.role.name} • Рівень ${user.role.level}
            </div>
            <p style='margin-top:5px;'>${user.role.description}</p>
        `;

        let out = "";
        for (let section in perms) {
            out += formatBlock(section.toUpperCase(), perms[section]);
        }
        out += formatBlock("Статусні дозволи", {
            "can_change_status": status.can_change_status,
            "warehouse_operations": status.role_limitations?.warehouse_operations,
            "can_complete": status.role_limitations?.can_complete,
            "can_decline": status.role_limitations?.can_decline
        });

        out += formatBlock("Статистика", stats);

        grid.style.display = "block";
        grid.innerHTML = out;
    } catch (err) {
        result.innerText = "❌ Помилка мережі: " + err.message;
    }
}
