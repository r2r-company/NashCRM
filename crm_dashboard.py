import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json

# Конфігурація
BASE_URL = "http://127.0.0.1:8000"
API_URL = f"{BASE_URL}/api"

# Налаштування сторінки
st.set_page_config(
    page_title="НашCRM Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS стилі
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
    .sidebar .element-container {
        margin-bottom: 1rem;
    }
    .stButton > button {
        width: 100%;
        border-radius: 10px;
        border: none;
        background: linear-gradient(45deg, #667eea, #764ba2);
        color: white;
    }
</style>
""", unsafe_allow_html=True)


class CRMClient:
    def __init__(self, base_url, token=None):
        self.base_url = base_url
        self.token = token
        self.headers = {}
        if token:
            self.headers['Authorization'] = f'Bearer {token}'

    def login(self, username, password):
        """Авторизація користувача"""
        try:
            # Підготовляємо дані
            login_data = {"username": username, "password": password}
            headers = {"Content-Type": "application/json"}

            # Спробуємо через /api/token/
            response = requests.post(
                f"{self.base_url}/token/",
                json=login_data,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                # Ваш API повертає токен в data.access, а не просто access
                if 'data' in data and 'access' in data['data']:
                    self.token = data['data']['access']
                    self.headers['Authorization'] = f'Bearer {self.token}'
                    return True, "Успішна авторизація"
                elif 'access' in data:
                    # Fallback для стандартного формату
                    self.token = data['access']
                    self.headers['Authorization'] = f'Bearer {self.token}'
                    return True, "Успішна авторизація"
                else:
                    return False, f"Відсутній токен в відповіді: {data}"
            else:
                return False, f"Помилка авторизації. Код: {response.status_code}, Відповідь: {response.text}"

        except Exception as e:
            return False, f"Помилка з'єднання: {str(e)}"

    def get_dashboard(self):
        """Отримання даних дашборду"""
        try:
            response = requests.get(f"{self.base_url}/crm/dashboard/", headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None

    def get_clients(self, filters=None):
        """Отримання списку клієнтів"""
        try:
            url = f"{self.base_url}/clients/"
            if filters:
                params = "&".join([f"{k}={v}" for k, v in filters.items() if v])
                if params:
                    url += f"?{params}"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return []
        except:
            return []

    def get_leads(self, filters=None):
        """Отримання списку заявок"""
        try:
            url = f"{self.base_url}/leads/"
            if filters:
                params = "&".join([f"{k}={v}" for k, v in filters.items() if v])
                if params:
                    url += f"?{params}"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return []
        except:
            return []

    def create_lead(self, lead_data):
        """Створення нової заявки"""
        try:
            response = requests.post(f"{self.base_url}/leads/", json=lead_data, headers=self.headers)
            return response.status_code == 201, response.json() if response.status_code == 201 else response.text
        except Exception as e:
            return False, str(e)

    def get_funnel(self, filters=None):
        """Отримання воронки продажів"""
        try:
            url = f"{self.base_url}/funnel/"
            if filters:
                params = "&".join([f"{k}={v}" for k, v in filters.items() if v])
                if params:
                    url += f"?{params}"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None

    def get_payments(self, filters=None):
        """Отримання платежів"""
        try:
            url = f"{self.base_url}/payments/"
            if filters:
                params = "&".join([f"{k}={v}" for k, v in filters.items() if v])
                if params:
                    url += f"?{params}"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return []
        except:
            return []

    def get_client_interactions(self, client_id=None):
        """Отримання взаємодій з клієнтами"""
        try:
            url = f"{self.base_url}/client-interactions/"
            if client_id:
                url += f"?client_id={client_id}"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return []
        except:
            return []

    def create_interaction(self, interaction_data):
        """Створення взаємодії"""
        try:
            response = requests.post(f"{self.base_url}/client-interactions/", json=interaction_data,
                                     headers=self.headers)
            return response.status_code == 201, response.json() if response.status_code == 201 else response.text
        except Exception as e:
            return False, str(e)

    def get_tasks(self, task_type="my"):
        """Отримання задач"""
        try:
            if task_type == "my":
                url = f"{self.base_url}/client-tasks/my_tasks/"
            elif task_type == "overdue":
                url = f"{self.base_url}/client-tasks/overdue_tasks/"
            else:
                url = f"{self.base_url}/client-tasks/"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return []
        except:
            return []


# Ініціалізація сесії
if 'crm_client' not in st.session_state:
    st.session_state.crm_client = CRMClient(API_URL)
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False


def login_page():
    """Сторінка авторизації"""
    st.markdown('<h1 class="main-header">🔐 НашCRM - Вхід до системи</h1>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        with st.form("login_form"):
            st.markdown("### Авторизація")
            username = st.text_input("Логін", value="admin")
            password = st.text_input("Пароль", type="password", value="11111")
            submit = st.form_submit_button("Увійти", use_container_width=True)

            if submit:
                with st.spinner("Авторизація..."):
                    success, message = st.session_state.crm_client.login(username, password)
                    if success:
                        st.session_state.authenticated = True
                        st.success("Успішна авторизація!")
                        st.rerun()
                    else:
                        st.error(message)

                        # Додаткова діагностика
                        st.warning("💡 Діагностика:")
                        st.info(f"🔗 Спроба підключення до: {API_URL}/token/")
                        st.info("📝 Переконайтеся що Django сервер запущений на правильному порту")

                        # Тест доступності API
                        try:
                            # Просто перевіряємо чи доступний сервер
                            test_response = requests.get(f"{BASE_URL}/", timeout=5)
                            st.info(f"🌐 Django сервер доступний, статус: {test_response.status_code}")
                        except Exception as e:
                            st.error(f"❌ Django сервер недоступний: {str(e)}")


def main_dashboard():
    """Головний дашборд"""
    st.markdown('<h1 class="main-header">📊 НашCRM Dashboard</h1>', unsafe_allow_html=True)

    # Отримання даних дашборду
    dashboard_data = st.session_state.crm_client.get_dashboard()

    if dashboard_data and 'summary' in dashboard_data:
        summary = dashboard_data['summary']

        # Метрики у верхній частині
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                label="👥 Всього клієнтів",
                value=summary.get('total_clients', 0),
                delta=f"+{summary.get('new_clients_today', 0)} сьогодні"
            )

        with col2:
            st.metric(
                label="💎 АКБ клієнтів",
                value=summary.get('akb_clients', 0),
                delta=f"{summary.get('akb_percentage', 0):.1f}%"
            )

        with col3:
            st.metric(
                label="🔥 Гарячі ліди",
                value=summary.get('hot_leads', 0),
                delta=f"{summary.get('hot_leads_percentage', 0):.1f}%"
            )

        with col4:
            revenue = summary.get('total_revenue', 0)
            try:
                formatted_revenue = f"{float(revenue):,.0f} ₴"
                revenue_today = summary.get('revenue_today', 0)
                delta_revenue = f"+{float(revenue_today):,.0f} ₴ сьогодні"
            except (ValueError, TypeError):
                formatted_revenue = "0 ₴"
                delta_revenue = "+0 ₴ сьогодні"

            st.metric(
                label="💰 Загальна виручка",
                value=formatted_revenue,
                delta=delta_revenue
            )

        st.markdown("---")

        # Графіки
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("🌡️ Розподіл клієнтів по температурі")
            temp_data = {
                'Холодні': summary.get('cold_leads', 0),
                'Теплі': summary.get('warm_leads', 0),
                'Гарячі': summary.get('hot_leads', 0),
                'Клієнти': summary.get('customers', 0),
                'Лояльні': summary.get('loyal_clients', 0)
            }

            if any(temp_data.values()):
                fig_temp = px.pie(
                    values=list(temp_data.values()),
                    names=list(temp_data.keys()),
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig_temp.update_layout(height=400)
                st.plotly_chart(fig_temp, use_container_width=True)

        with col2:
            st.subheader("💎 Сегменти АКБ")
            akb_data = {
                'VIP': summary.get('vip_clients', 0),
                'Premium': summary.get('premium_clients', 0),
                'Standard': summary.get('standard_clients', 0),
                'Basic': summary.get('basic_clients', 0),
                'Нові': summary.get('new_clients', 0)
            }

            if any(akb_data.values()):
                fig_akb = px.bar(
                    x=list(akb_data.keys()),
                    y=list(akb_data.values()),
                    color=list(akb_data.values()),
                    color_continuous_scale="Viridis"
                )
                fig_akb.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig_akb, use_container_width=True)

        # ТОП клієнти
        if 'top_clients' in dashboard_data and dashboard_data['top_clients']:
            st.subheader("🏆 ТОП клієнти")
            top_clients_df = pd.DataFrame(dashboard_data['top_clients'])
            st.dataframe(top_clients_df, use_container_width=True)

    else:
        st.warning("Не вдалося завантажити дані дашборду")


def clients_page():
    """Сторінка клієнтів"""
    st.markdown('<h1 class="main-header">👥 Управління клієнтами</h1>', unsafe_allow_html=True)

    # Фільтри
    col1, col2, col3 = st.columns(3)

    with col1:
        temperature_filter = st.selectbox(
            "Температура:",
            ["", "cold", "warm", "hot", "customer", "loyal", "sleeping"],
            format_func=lambda x: {
                "": "Всі",
                "cold": "Холодні",
                "warm": "Теплі",
                "hot": "Гарячі",
                "customer": "Клієнти",
                "loyal": "Лояльні",
                "sleeping": "Сплячі"
            }.get(x, x)
        )

    with col2:
        akb_filter = st.selectbox(
            "Сегмент АКБ:",
            ["", "vip", "premium", "standard", "basic", "new", "inactive"],
            format_func=lambda x: {
                "": "Всі",
                "vip": "VIP",
                "premium": "Premium",
                "standard": "Standard",
                "basic": "Basic",
                "new": "Новий",
                "inactive": "Неактивний"
            }.get(x, x)
        )

    with col3:
        if st.button("🔄 Оновити дані"):
            st.rerun()

    # Отримання клієнтів з фільтрами
    filters = {}
    if temperature_filter:
        filters['temperature'] = temperature_filter
    if akb_filter:
        filters['akb_segment'] = akb_filter

    clients = st.session_state.crm_client.get_clients(filters)

    if clients:
        # Конвертуємо в DataFrame для зручності
        if isinstance(clients, list) and len(clients) > 0:
            clients_df = pd.DataFrame(clients)

            # Статистика по клієнтах
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Знайдено клієнтів", len(clients_df))
            with col2:
                if 'total_spent' in clients_df.columns:
                    total_revenue = clients_df['total_spent'].sum()
                    st.metric("Загальна виручка", f"{total_revenue:,.0f} ₴")
            with col3:
                if 'temperature' in clients_df.columns:
                    hot_count = len(clients_df[clients_df['temperature'] == 'hot'])
                    st.metric("Гарячі ліди", hot_count)

            # Таблиця клієнтів
            st.subheader("📋 Список клієнтів")

            # Відображаємо основні колонки
            display_cols = []
            if 'full_name' in clients_df.columns:
                display_cols.append('full_name')
            if 'phone' in clients_df.columns:
                display_cols.append('phone')
            if 'email' in clients_df.columns:
                display_cols.append('email')
            if 'temperature' in clients_df.columns:
                display_cols.append('temperature')
            if 'akb_segment' in clients_df.columns:
                display_cols.append('akb_segment')
            if 'total_spent' in clients_df.columns:
                display_cols.append('total_spent')
            if 'last_purchase_date' in clients_df.columns:
                display_cols.append('last_purchase_date')

            if display_cols:
                st.dataframe(clients_df[display_cols], use_container_width=True)
            else:
                st.dataframe(clients_df, use_container_width=True)
    else:
        st.warning("Не знайдено клієнтів або помилка завантаження даних")


def leads_page():
    """Сторінка заявок"""
    st.markdown('<h1 class="main-header">📝 Управління заявками</h1>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📋 Список заявок", "🆕 Створити заявку"])

    with tab1:
        # Фільтри для заявок
        col1, col2, col3 = st.columns(3)

        with col1:
            status_filter = st.selectbox(
                "Статус:",
                ["", "new", "queued", "in_progress", "completed", "paid", "canceled"],
                format_func=lambda x: {
                    "": "Всі",
                    "new": "Нова",
                    "queued": "В черзі",
                    "in_progress": "В роботі",
                    "completed": "Завершена",
                    "paid": "Оплачена",
                    "canceled": "Скасована"
                }.get(x, x)
            )

        with col2:
            source_filter = st.selectbox(
                "Джерело:",
                ["", "phone", "email", "instagram", "facebook", "website", "referral"],
                format_func=lambda x: {
                    "": "Всі",
                    "phone": "Телефон",
                    "email": "Email",
                    "instagram": "Instagram",
                    "facebook": "Facebook",
                    "website": "Сайт",
                    "referral": "Рекомендації"
                }.get(x, x)
            )

        with col3:
            if st.button("🔄 Оновити заявки"):
                st.rerun()

        # Отримання заявок
        filters = {}
        if status_filter:
            filters['status'] = status_filter
        if source_filter:
            filters['source'] = source_filter

        leads = st.session_state.crm_client.get_leads(filters)

        if leads:
            if isinstance(leads, list) and len(leads) > 0:
                leads_df = pd.DataFrame(leads)

            # Статистика
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Всього заявок", len(leads_df))
            with col2:
                if 'price' in leads_df.columns:
                    total_amount = leads_df['price'].sum()
                    # Безпечне форматування числа
                    try:
                        formatted_amount = f"{float(total_amount):,.0f} ₴"
                    except (ValueError, TypeError):
                        formatted_amount = "0 ₴"
                    st.metric("Загальна сума", formatted_amount)
            with col3:
                if 'status' in leads_df.columns:
                    completed = len(leads_df[leads_df['status'] == 'completed'])
                    st.metric("Завершено", completed)
            with col4:
                if 'status' in leads_df.columns:
                    paid = len(leads_df[leads_df['status'] == 'paid'])
                    st.metric("Оплачено", paid)

                # Таблиця заявок
                st.subheader("📋 Заявки")

                # Відображаємо основні колонки
                display_cols = []
                for col in ['id', 'full_name', 'phone', 'source', 'status', 'price', 'created_at']:
                    if col in leads_df.columns:
                        display_cols.append(col)

                if display_cols:
                    st.dataframe(leads_df[display_cols], use_container_width=True)
                else:
                    st.dataframe(leads_df, use_container_width=True)
        else:
            st.warning("Не знайдено заявок")

    with tab2:
        # Форма створення заявки
        st.subheader("Створення нової заявки")

        with st.form("create_lead_form"):
            col1, col2 = st.columns(2)

            with col1:
                full_name = st.text_input("Повне ім'я*", placeholder="Іван Іванович")
                phone = st.text_input("Телефон*", placeholder="+380997777777")
                email = st.text_input("Email", placeholder="ivan@example.com")
                price = st.number_input("Ціна*", min_value=0.0, value=1000.0, step=100.0)

            with col2:
                source = st.selectbox(
                    "Джерело*",
                    ["phone", "email", "instagram", "facebook", "website", "referral"],
                    format_func=lambda x: {
                        "phone": "Телефон",
                        "email": "Email",
                        "instagram": "Instagram",
                        "facebook": "Facebook",
                        "website": "Сайт",
                        "referral": "Рекомендації"
                    }.get(x, x)
                )

                advance = st.number_input("Передоплата", min_value=0.0, value=0.0, step=50.0)
                delivery_cost = st.number_input("Вартість доставки", min_value=0.0, value=0.0, step=10.0)
                order_number = st.text_input("Номер замовлення", placeholder="ORD-2024-001")

            description = st.text_area("Опис", placeholder="Детальний опис заявки")
            comment = st.text_area("Коментар", placeholder="Додаткові коментарі")

            # Адреса
            st.subheader("📍 Адреса доставки")
            col1, col2 = st.columns(2)
            with col1:
                country = st.text_input("Країна", value="Україна")
                city = st.text_input("Місто", placeholder="Київ")
            with col2:
                postal_code = st.text_input("Поштовий індекс", placeholder="01001")
                street = st.text_input("Вулиця", placeholder="вул. Хрещатик, 1")

            full_address = st.text_input("Повна адреса", placeholder="м. Київ, вул. Хрещатик, 1")

            submit_lead = st.form_submit_button("🚀 Створити заявку", use_container_width=True)

            if submit_lead:
                if not full_name or not phone or not source:
                    st.error("Заповніть обов'язкові поля (ім'я, телефон, джерело)")
                else:
                    lead_data = {
                        "full_name": full_name,
                        "phone": phone,
                        "source": source,
                        "price": price
                    }

                    # Додаємо необов'язкові поля
                    if email:
                        lead_data["email"] = email
                    if description:
                        lead_data["description"] = description
                    if comment:
                        lead_data["comment"] = comment
                    if advance > 0:
                        lead_data["advance"] = advance
                    if delivery_cost > 0:
                        lead_data["delivery_cost"] = delivery_cost
                    if order_number:
                        lead_data["order_number"] = order_number
                    if country:
                        lead_data["country"] = country
                    if city:
                        lead_data["city"] = city
                    if postal_code:
                        lead_data["postal_code"] = postal_code
                    if street:
                        lead_data["street"] = street
                    if full_address:
                        lead_data["full_address"] = full_address

                    success, result = st.session_state.crm_client.create_lead(lead_data)
                    if success:
                        st.success(f"✅ Заявку створено успішно! ID: {result.get('id', 'N/A')}")
                        st.rerun()
                    else:
                        st.error(f"❌ Помилка створення заявки: {result}")


def funnel_page():
    """Сторінка воронки продажів"""
    st.markdown('<h1 class="main-header">🌪️ Воронка продажів</h1>', unsafe_allow_html=True)

    # Фільтри
    col1, col2, col3 = st.columns(3)

    with col1:
        date_from = st.date_input("Від дати:", value=datetime.now() - timedelta(days=30))
    with col2:
        date_to = st.date_input("До дати:", value=datetime.now())
    with col3:
        if st.button("📊 Побудувати воронку"):
            st.rerun()

    # Отримання даних воронки
    filters = {
        "from": date_from.strftime("%Y-%m-%d"),
        "to": date_to.strftime("%Y-%m-%d")
    }

    funnel_data = st.session_state.crm_client.get_funnel(filters)

    if funnel_data and 'funnel' in funnel_data:
        funnel = funnel_data['funnel']

        # Метрики воронки
        col1, col2, col3 = st.columns(3)

        with col1:
            total_leads = sum(funnel.values())
            st.metric("Всього лідів", total_leads)

        with col2:
            conversion = funnel_data.get('conversion_rate', 0)
            # Безпечне форматування конверсії
            try:
                formatted_conversion = f"{float(conversion):.1f}%"
            except (ValueError, TypeError):
                formatted_conversion = "0.0%"
            st.metric("Конверсія", formatted_conversion)

        with col3:
            completed = funnel.get('completed', 0)
            if total_leads > 0:
                completion_rate = (completed / total_leads) * 100
                try:
                    formatted_completion = f"{float(completion_rate):.1f}%"
                except (ValueError, TypeError):
                    formatted_completion = "0.0%"
                st.metric("% завершених", formatted_completion)
            else:
                st.metric("% завершених", "0.0%")

        # Візуалізація воронки
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📊 Воронка по етапах")

            # Конвертуємо назви статусів
            status_names = {
                'new': 'Нові',
                'queued': 'В черзі',
                'in_progress': 'В роботі',
                'completed': 'Завершені',
                'paid': 'Оплачені',
                'canceled': 'Скасовані'
            }

            funnel_df = pd.DataFrame([
                {"Етап": status_names.get(status, status), "Кількість": count}
                for status, count in funnel.items()
            ])

            fig_funnel = px.bar(
                funnel_df,
                x="Етап",
                y="Кількість",
                color="Кількість",
                color_continuous_scale="Viridis"
            )
            fig_funnel.update_layout(height=400)
            st.plotly_chart(fig_funnel, use_container_width=True)

        with col2:
            st.subheader("🥧 Розподіл по статусах")

            fig_pie = px.pie(
                values=list(funnel.values()),
                names=[status_names.get(status, status) for status in funnel.keys()],
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_pie.update_layout(height=400)
            st.plotly_chart(fig_pie, use_container_width=True)

        # Детальна таблиця
        st.subheader("📋 Детальна статистика")

        funnel_table = []
        total = sum(funnel.values())

        for status, count in funnel.items():
            percentage = (count / total * 100) if total > 0 else 0
            funnel_table.append({
                "Етап": status_names.get(status, status),
                "Кількість": count,
                "Відсоток": f"{percentage:.1f}%"
            })

        st.dataframe(pd.DataFrame(funnel_table), use_container_width=True)

    else:
        st.warning("Не вдалося завантажити дані воронки")


def finance_page():
    """Сторінка фінансів"""
    st.markdown('<h1 class="main-header">💰 Фінансові операції</h1>', unsafe_allow_html=True)

    # Фільтри
    col1, col2, col3 = st.columns(3)

    with col1:
        payment_type = st.selectbox(
            "Тип операції:",
            ["", "expected", "received"],
            format_func=lambda x: {
                "": "Всі",
                "expected": "Очікувані",
                "received": "Отримані"
            }.get(x, x)
        )

    with col2:
        date_from = st.date_input("Від дати:", value=datetime.now() - timedelta(days=30))

    with col3:
        date_to = st.date_input("До дати:", value=datetime.now())

    # Отримання платежів
    filters = {}
    if payment_type:
        filters['type'] = payment_type

    payments = st.session_state.crm_client.get_payments(filters)

    if payments:
        if isinstance(payments, list) and len(payments) > 0:
            payments_df = pd.DataFrame(payments)

            # Фільтруємо по датах якщо є колонка created_at
            if 'created_at' in payments_df.columns:
                payments_df['created_at'] = pd.to_datetime(payments_df['created_at'])
                mask = (payments_df['created_at'].dt.date >= date_from) & (payments_df['created_at'].dt.date <= date_to)
                payments_df = payments_df[mask]

            # Фінансові метрики
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Всього операцій", len(payments_df))

            with col2:
                if 'amount' in payments_df.columns:
                    total_amount = payments_df['amount'].sum()
                    st.metric("Загальна сума", f"{total_amount:,.0f} ₴")

            with col3:
                if 'operation_type' in payments_df.columns:
                    received = payments_df[payments_df['operation_type'] == 'received'][
                        'amount'].sum() if 'amount' in payments_df.columns else 0
                    st.metric("Отримано", f"{received:,.0f} ₴")

            with col4:
                if 'operation_type' in payments_df.columns:
                    expected = payments_df[payments_df['operation_type'] == 'expected'][
                        'amount'].sum() if 'amount' in payments_df.columns else 0
                    st.metric("Очікується", f"{expected:,.0f} ₴")

            # Графіки
            col1, col2 = st.columns(2)

            with col1:
                if 'operation_type' in payments_df.columns and 'amount' in payments_df.columns:
                    st.subheader("💰 Розподіл по типах")

                    type_summary = payments_df.groupby('operation_type')['amount'].sum().reset_index()
                    type_names = {
                        'expected': 'Очікувані',
                        'received': 'Отримані'
                    }
                    type_summary['operation_type'] = type_summary['operation_type'].map(type_names)

                    fig_types = px.pie(
                        type_summary,
                        values='amount',
                        names='operation_type',
                        color_discrete_sequence=px.colors.qualitative.Set2
                    )
                    fig_types.update_layout(height=400)
                    st.plotly_chart(fig_types, use_container_width=True)

            with col2:
                if 'created_at' in payments_df.columns and 'amount' in payments_df.columns:
                    st.subheader("📈 Динаміка платежів")

                    payments_df['date'] = payments_df['created_at'].dt.date
                    daily_payments = payments_df.groupby('date')['amount'].sum().reset_index()

                    fig_timeline = px.line(
                        daily_payments,
                        x='date',
                        y='amount',
                        title="Платежі по днях"
                    )
                    fig_timeline.update_layout(height=400)
                    st.plotly_chart(fig_timeline, use_container_width=True)

            # Таблиця платежів
            st.subheader("📋 Список операцій")

            display_cols = []
            for col in ['id', 'lead', 'amount', 'operation_type', 'comment', 'created_at']:
                if col in payments_df.columns:
                    display_cols.append(col)

            if display_cols:
                st.dataframe(payments_df[display_cols], use_container_width=True)
            else:
                st.dataframe(payments_df, use_container_width=True)

    else:
        st.warning("Не знайдено фінансових операцій")


def interactions_page():
    """Сторінка взаємодій з клієнтами"""
    st.markdown('<h1 class="main-header">📞 Взаємодії з клієнтами</h1>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📋 Список взаємодій", "🆕 Створити взаємодію"])

    with tab1:
        # Фільтри
        col1, col2 = st.columns(2)

        with col1:
            client_id_filter = st.number_input("ID клієнта:", min_value=0, value=0, step=1)

        with col2:
            if st.button("🔄 Оновити взаємодії"):
                st.rerun()

        # Отримання взаємодій
        interactions = st.session_state.crm_client.get_client_interactions(
            client_id_filter if client_id_filter > 0 else None
        )

        if interactions:
            if isinstance(interactions, list) and len(interactions) > 0:
                interactions_df = pd.DataFrame(interactions)

                # Статистика
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Всього взаємодій", len(interactions_df))

                with col2:
                    if 'interaction_type' in interactions_df.columns:
                        calls_count = len(interactions_df[interactions_df['interaction_type'] == 'call'])
                        st.metric("Дзвінків", calls_count)

                with col3:
                    if 'outcome' in interactions_df.columns:
                        positive_count = len(interactions_df[interactions_df['outcome'] == 'positive'])
                        st.metric("Позитивних", positive_count)

                # Графіки взаємодій
                col1, col2 = st.columns(2)

                with col1:
                    if 'interaction_type' in interactions_df.columns:
                        st.subheader("📊 Типи взаємодій")

                        type_counts = interactions_df['interaction_type'].value_counts()
                        type_names = {
                            'call': 'Дзвінки',
                            'email': 'Email',
                            'meeting': 'Зустрічі',
                            'sms': 'SMS'
                        }

                        fig_types = px.bar(
                            x=[type_names.get(t, t) for t in type_counts.index],
                            y=type_counts.values,
                            color=type_counts.values,
                            color_continuous_scale="Blues"
                        )
                        fig_types.update_layout(height=300)
                        st.plotly_chart(fig_types, use_container_width=True)

                with col2:
                    if 'outcome' in interactions_df.columns:
                        st.subheader("🎯 Результати взаємодій")

                        outcome_counts = interactions_df['outcome'].value_counts()
                        outcome_names = {
                            'positive': 'Позитивні',
                            'negative': 'Негативні',
                            'neutral': 'Нейтральні',
                            'follow_up': 'Потребують продовження'
                        }

                        fig_outcomes = px.pie(
                            values=outcome_counts.values,
                            names=[outcome_names.get(o, o) for o in outcome_counts.index],
                            color_discrete_sequence=px.colors.qualitative.Pastel
                        )
                        fig_outcomes.update_layout(height=300)
                        st.plotly_chart(fig_outcomes, use_container_width=True)

                # Таблиця взаємодій
                st.subheader("📋 Деталі взаємодій")

                display_cols = []
                for col in ['id', 'client', 'interaction_type', 'direction', 'subject', 'outcome', 'created_at']:
                    if col in interactions_df.columns:
                        display_cols.append(col)

                if display_cols:
                    st.dataframe(interactions_df[display_cols], use_container_width=True)
                else:
                    st.dataframe(interactions_df, use_container_width=True)
        else:
            st.warning("Не знайдено взаємодій")

    with tab2:
        # Форма створення взаємодії
        st.subheader("Створення нової взаємодії")

        with st.form("create_interaction_form"):
            col1, col2 = st.columns(2)

            with col1:
                client_id = st.number_input("ID клієнта*", min_value=1, value=1, step=1)
                interaction_type = st.selectbox(
                    "Тип взаємодії*",
                    ["call", "email", "meeting", "sms"],
                    format_func=lambda x: {
                        "call": "Дзвінок",
                        "email": "Email",
                        "meeting": "Зустріч",
                        "sms": "SMS"
                    }.get(x, x)
                )
                direction = st.selectbox(
                    "Напрямок*",
                    ["incoming", "outgoing"],
                    format_func=lambda x: {
                        "incoming": "Вхідний",
                        "outgoing": "Вихідний"
                    }.get(x, x)
                )

            with col2:
                outcome = st.selectbox(
                    "Результат*",
                    ["positive", "negative", "neutral", "follow_up"],
                    format_func=lambda x: {
                        "positive": "Позитивний",
                        "negative": "Негативний",
                        "neutral": "Нейтральний",
                        "follow_up": "Потребує продовження"
                    }.get(x, x)
                )

                follow_up_date = st.date_input(
                    "Дата наступного контакту",
                    value=datetime.now().date() + timedelta(days=1)
                )

                follow_up_time = st.time_input(
                    "Час наступного контакту",
                    value=datetime.now().time()
                )

            subject = st.text_input("Тема*", placeholder="Консультація по товару")
            description = st.text_area("Опис", placeholder="Детальний опис взаємодії з клієнтом")

            submit_interaction = st.form_submit_button("📞 Створити взаємодію", use_container_width=True)

            if submit_interaction:
                if not subject:
                    st.error("Заповніть обов'язкові поля")
                else:
                    interaction_data = {
                        "client": client_id,
                        "interaction_type": interaction_type,
                        "direction": direction,
                        "subject": subject,
                        "outcome": outcome
                    }

                    if description:
                        interaction_data["description"] = description

                    if follow_up_date:
                        interaction_data["follow_up_date"] = follow_up_date.isoformat()

                    success, result = st.session_state.crm_client.create_interaction(interaction_data)
                    if success:
                        st.success("✅ Взаємодію створено успішно!")
                        st.rerun()
                    else:
                        st.error(f"❌ Помилка створення взаємодії: {result}")


def tasks_page():
    """Сторінка задач"""
    st.markdown('<h1 class="main-header">📋 Управління задачами</h1>', unsafe_allow_html=True)

    # Типи задач
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📋 Мої задачі", use_container_width=True):
            st.session_state.task_type = "my"

    with col2:
        if st.button("⏰ Прострочені", use_container_width=True):
            st.session_state.task_type = "overdue"

    with col3:
        if st.button("🔄 Оновити", use_container_width=True):
            st.rerun()

    # Ініціалізуємо тип задач якщо не встановлено
    if 'task_type' not in st.session_state:
        st.session_state.task_type = "my"

    # Отримання задач
    tasks = st.session_state.crm_client.get_tasks(st.session_state.task_type)

    if tasks:
        if isinstance(tasks, list) and len(tasks) > 0:
            tasks_df = pd.DataFrame(tasks)

            # Статистика задач
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Всього задач", len(tasks_df))

            with col2:
                if 'status' in tasks_df.columns:
                    pending_count = len(tasks_df[tasks_df['status'] == 'pending'])
                    st.metric("Очікують виконання", pending_count)

            with col3:
                if 'priority' in tasks_df.columns:
                    urgent_count = len(tasks_df[tasks_df['priority'] == 'urgent'])
                    st.metric("Терміново", urgent_count)

            # Розподіл задач по пріоритету
            if 'priority' in tasks_df.columns:
                st.subheader("🎯 Розподіл по пріоритету")

                priority_counts = tasks_df['priority'].value_counts()
                priority_names = {
                    'low': 'Низький',
                    'medium': 'Середній',
                    'high': 'Високий',
                    'urgent': 'Терміново'
                }

                fig_priority = px.bar(
                    x=[priority_names.get(p, p) for p in priority_counts.index],
                    y=priority_counts.values,
                    color=priority_counts.values,
                    color_continuous_scale="Reds"
                )
                fig_priority.update_layout(height=300)
                st.plotly_chart(fig_priority, use_container_width=True)

            # Таблиця задач
            st.subheader(f"📋 {['Мої задачі', 'Прострочені задачі'][st.session_state.task_type == 'overdue']}")

            display_cols = []
            for col in ['id', 'title', 'client', 'priority', 'status', 'due_date', 'created_at']:
                if col in tasks_df.columns:
                    display_cols.append(col)

            if display_cols:
                st.dataframe(tasks_df[display_cols], use_container_width=True)
            else:
                st.dataframe(tasks_df, use_container_width=True)
        else:
            st.info("Задач не знайдено")
    else:
        st.warning("Не вдалося завантажити задачі")


def reports_page():
    """Сторінка звітів"""
    st.markdown('<h1 class="main-header">📊 Звіти та аналітика</h1>', unsafe_allow_html=True)

    # Параметри звіту
    col1, col2, col3 = st.columns(3)

    with col1:
        date_from = st.date_input("Від дати:", value=datetime.now() - timedelta(days=30))

    with col2:
        date_to = st.date_input("До дати:", value=datetime.now())

    with col3:
        if st.button("📈 Сформувати звіт"):
            st.rerun()

    # Отримуємо дані для звіту
    leads = st.session_state.crm_client.get_leads()
    clients = st.session_state.crm_client.get_clients()
    payments = st.session_state.crm_client.get_payments()

    if leads and clients:
        # Конвертуємо в DataFrame
        leads_df = pd.DataFrame(leads) if isinstance(leads, list) else pd.DataFrame()
        clients_df = pd.DataFrame(clients) if isinstance(clients, list) else pd.DataFrame()
        payments_df = pd.DataFrame(payments) if isinstance(payments, list) and payments else pd.DataFrame()

        # Фільтруємо по датах
        if not leads_df.empty and 'created_at' in leads_df.columns:
            leads_df['created_at'] = pd.to_datetime(leads_df['created_at'])
            mask = (leads_df['created_at'].dt.date >= date_from) & (leads_df['created_at'].dt.date <= date_to)
            leads_df = leads_df[mask]

        # Загальна статистика
        st.subheader("📈 Загальна статистика")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Заявок за період", len(leads_df))

        with col2:
            if not leads_df.empty and 'price' in leads_df.columns:
                total_revenue = leads_df['price'].sum()
                st.metric("Загальна виручка", f"{total_revenue:,.0f} ₴")
            else:
                st.metric("Загальна виручка", "0 ₴")

        with col3:
            if not leads_df.empty and 'price' in leads_df.columns:
                avg_deal = leads_df['price'].mean()
                st.metric("Середня угода", f"{avg_deal:,.0f} ₴")
            else:
                st.metric("Середня угода", "0 ₴")

        with col4:
            st.metric("Всього клієнтів", len(clients_df))

        # Графіки звітності
        col1, col2 = st.columns(2)

        with col1:
            if not leads_df.empty and 'source' in leads_df.columns:
                st.subheader("📱 Джерела лідів")

                source_counts = leads_df['source'].value_counts()
                source_names = {
                    'phone': 'Телефон',
                    'email': 'Email',
                    'instagram': 'Instagram',
                    'facebook': 'Facebook',
                    'website': 'Сайт',
                    'referral': 'Рекомендації'
                }

                fig_sources = px.pie(
                    values=source_counts.values,
                    names=[source_names.get(s, s) for s in source_counts.index],
                    color_discrete_sequence=px.colors.qualitative.Set1
                )
                fig_sources.update_layout(height=400)
                st.plotly_chart(fig_sources, use_container_width=True)

        with col2:
            if not leads_df.empty and 'status' in leads_df.columns:
                st.subheader("📊 Статуси заявок")

                status_counts = leads_df['status'].value_counts()
                status_names = {
                    'new': 'Нові',
                    'queued': 'В черзі',
                    'in_progress': 'В роботі',
                    'completed': 'Завершені',
                    'paid': 'Оплачені',
                    'canceled': 'Скасовані'
                }

                fig_statuses = px.bar(
                    x=[status_names.get(s, s) for s in status_counts.index],
                    y=status_counts.values,
                    color=status_counts.values,
                    color_continuous_scale="Viridis"
                )
                fig_statuses.update_layout(height=400)
                st.plotly_chart(fig_statuses, use_container_width=True)

        # Динаміка по днях
        if not leads_df.empty and 'created_at' in leads_df.columns:
            st.subheader("📈 Динаміка заявок по днях")

            leads_df['date'] = leads_df['created_at'].dt.date
            daily_leads = leads_df.groupby('date').size().reset_index(name='count')

            if 'price' in leads_df.columns:
                daily_revenue = leads_df.groupby('date')['price'].sum().reset_index()
                daily_stats = daily_leads.merge(daily_revenue, on='date', how='left')
            else:
                daily_stats = daily_leads
                daily_stats['price'] = 0

            fig_timeline = go.Figure()

            # Додаємо лінію кількості заявок
            fig_timeline.add_trace(go.Scatter(
                x=daily_stats['date'],
                y=daily_stats['count'],
                mode='lines+markers',
                name='Кількість заявок',
                yaxis='y',
                line=dict(color='blue')
            ))

            # Додаємо лінію виручки (якщо є)
            if 'price' in daily_stats.columns:
                fig_timeline.add_trace(go.Scatter(
                    x=daily_stats['date'],
                    y=daily_stats['price'],
                    mode='lines+markers',
                    name='Виручка (₴)',
                    yaxis='y2',
                    line=dict(color='green')
                ))

            # Налаштування осей
            fig_timeline.update_layout(
                height=400,
                yaxis=dict(title='Кількість заявок', side='left'),
                yaxis2=dict(title='Виручка (₴)', side='right', overlaying='y'),
                xaxis=dict(title='Дата')
            )

            st.plotly_chart(fig_timeline, use_container_width=True)

        # Топ клієнти
        if not clients_df.empty:
            st.subheader("🏆 ТОП клієнти")

            # Якщо є інформація про витрати клієнтів
            if 'total_spent' in clients_df.columns:
                top_clients = clients_df.nlargest(10, 'total_spent')[['full_name', 'total_spent', 'temperature']]
                st.dataframe(top_clients, use_container_width=True)
            else:
                # Показуємо просто список клієнтів
                display_cols = []
                for col in ['full_name', 'phone', 'email', 'temperature', 'akb_segment']:
                    if col in clients_df.columns:
                        display_cols.append(col)

                if display_cols:
                    st.dataframe(clients_df[display_cols].head(10), use_container_width=True)

    else:
        st.warning("Не вдалося завантажити дані для звіту")


def main():
    """Головна функція"""

    # Перевірка аутентифікації
    if not st.session_state.authenticated:
        login_page()
        return

    # Бічна панель навігації
    st.sidebar.title("🚀 НашCRM")
    st.sidebar.markdown("---")

    # Меню навігації
    menu_items = {
        "📊 Дашборд": "dashboard",
        "👥 Клієнти": "clients",
        "📝 Заявки": "leads",
        "🌪️ Воронка продажів": "funnel",
        "💰 Фінанси": "finance",
        "📞 Взаємодії": "interactions",
        "📋 Задачі": "tasks",
        "📊 Звіти": "reports"
    }

    selected = st.sidebar.radio("Навігація", list(menu_items.keys()))
    page = menu_items[selected]

    st.sidebar.markdown("---")

    # Кнопка виходу
    if st.sidebar.button("🚪 Вийти", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.crm_client.token = None
        st.rerun()

    # Інформація про користувача
    st.sidebar.markdown("### 👤 Користувач")
    st.sidebar.info("Ви увійшли як admin")

    # Швидкі дії
    st.sidebar.markdown("### ⚡ Швидкі дії")
    if st.sidebar.button("🆕 Нова заявка", use_container_width=True):
        st.session_state.quick_action = "new_lead"

    if st.sidebar.button("📞 Нова взаємодія", use_container_width=True):
        st.session_state.quick_action = "new_interaction"

    # Відображення сторінок
    if page == "dashboard":
        main_dashboard()
    elif page == "clients":
        clients_page()
    elif page == "leads":
        leads_page()
    elif page == "funnel":
        funnel_page()
    elif page == "finance":
        finance_page()
    elif page == "interactions":
        interactions_page()
    elif page == "tasks":
        tasks_page()
    elif page == "reports":
        reports_page()


if __name__ == "__main__":
    main()