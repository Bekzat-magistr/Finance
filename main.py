import streamlit as st
import pandas as pd
import plotly.express as px
import psycopg2
from datetime import datetime

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="Менің қаржым", layout="wide")

# --- ПОДКЛЮЧЕНИЕ К БАЗЕ ---
DB_URL = st.secrets["DATABASE_URL"]

def get_connection():
    return psycopg2.connect(DB_URL, sslmode='require')




# --- ФУНКЦИИ ЗАГРУЗКИ (SQL) ---
# --- ФУНКЦИИ ЗАГРУЗКИ (Исправленные) ---
def load_data_from_db():
    query = "SELECT * FROM finance_transactions;"
    conn = get_connection()
    try:
        df = pd.read_sql(query, conn)
        # Если данных нет, создаем пустой DF с английскими именами
        if df.empty:
            df = pd.DataFrame(columns=["id", "date", "type", "category", "payment_method", "amount", "description", "segment"])
        
        # ВСЕГДА переименовываем, чтобы код ниже понимал казахские названия
        df = df.rename(columns={
            "type": "Түрі", 
            "category": "Санат", 
            "payment_method": "Төлем түрі",
            "amount": "Сома", 
            "description": "Сипаттама", 
            "date": "Күн"
        })
        return df
    except Exception as e:
        st.error(f"Ошибка загрузки транзакций: {e}")
        return pd.DataFrame(columns=["Күн", "Түрі", "Санат", "Төлем түрі", "Сома", "Сипаттама", "segment"])
    finally:
        conn.close()

def load_debts_from_db():
    query = "SELECT * FROM finance_debts;"
    conn = get_connection()
    try:
        df = pd.read_sql(query, conn)
        if df.empty:
            df = pd.DataFrame(columns=["id", "date", "name", "type", "bank", "amount", "status", "segment"])
        
        # Маппинг для долгов (тоже всегда)
        df = df.rename(columns={
            "status": "Мәртебе", 
            "amount": "Сома", 
            "type": "Түрі", 
            "name": "Аты", 
            "date": "Күн", 
            "bank": "Банк"
        })
        return df
    except Exception as e:
        return pd.DataFrame(columns=["id", "Күн", "Аты", "Түрі", "Банк", "Сома", "Мәртебе", "segment"])
    finally:
        conn.close()

# --- ФУНКЦИИ ЗАПИСИ (SQL) ---
def add_transaction_db(date, t_type, category, payment_method, amount, description, segment):
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        query = """INSERT INTO finance_transactions (date, type, category, payment_method, amount, description, segment) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        cur.execute(query, (date, t_type, category, payment_method, amount, description, segment))
        conn.commit()
    finally:
        cur.close()
        conn.close()

def add_debt_db(d_id, date, name, d_type, bank, amount, segment):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Записываем в таблицу долгов
        query_debt = """INSERT INTO finance_debts (id, date, name, type, bank, amount, status, segment) 
                        VALUES (%s, %s, %s, %s, %s, %s, 'Ашық', %s)"""
        cur.execute(query_debt, (d_id, date, name, d_type, bank, amount, segment))
        
        # 2. Формируем понятное описание для истории транзакций
        if d_type == "Маған қарыз":
            t_type = "Шығын" # Деньги ушли из кармана
            desc = f"💸 Қарыз берілді: {name}" # Понятное описание вместо минуса
        else:
            t_type = "Кіріс" # Деньги пришли в карман
            desc = f"💰 Қарыз алынды: {name}"

        # 3. Записываем в общую таблицу транзакций (чтобы баланс сошелся)
        query_trans = """INSERT INTO finance_transactions (date, type, category, payment_method, amount, description, segment) 
                         VALUES (%s, %s, 'Қарыз', %s, %s, %s, %s)"""
        cur.execute(query_trans, (date, t_type, bank, amount, desc, segment))
        
        conn.commit()
    except Exception as e:
        st.error(f"Қате: {e}")
    finally:
        cur.close()
        conn.close()

def close_debt_db(d_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE finance_debts SET status = 'Жабылды' WHERE id = %s", (d_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()

def delete_transaction_db(row_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM finance_transactions WHERE id = %s", (row_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()

# --- ИНИЦИАЛИЗАЦИЯ ДАННЫХ ---
data = load_data_from_db()
debts_data = load_debts_from_db()
banks = ["Каспи", "Халық", "Freedom", "Халық Инвест", "Қолма-қол"]

def format_num(value):
    try: return "{:,.0f}".format(value).replace(",", " ")
    except: return str(value)

# --- ИНТЕРФЕЙС ---
st.title("💰 Жеке және Бизнес қаржы")

tab_business, tab_personal = st.tabs(["💼 Бизнес", "👤 Жеке шығындар"])

def render_segment(segment_name, segment_label):
    # Проверка: есть ли вообще данные
    seg_data = data[data['segment'] == segment_name] if 'segment' in data.columns and not data.empty else pd.DataFrame(columns=data.columns)

    with st.expander(f"🏦 {segment_label}: Шоттар жағдайы", expanded=False):
        cols = st.columns(len(banks))
        for i, bank in enumerate(banks):
            # Безопасный расчет баланса
            if not seg_data.empty and "Төлем түрі" in seg_data.columns:
                inc = seg_data[(seg_data["Төлем түрі"] == bank) & (seg_data["Түрі"] == "Кіріс")]["Сома"].sum()
                exp = seg_data[(seg_data["Төлем түрі"] == bank) & (seg_data["Түрі"] == "Шығын")]["Сома"].sum()
                
                # Поиск переводов через str.contains
                t_in = seg_data[(seg_data["Түрі"] == "Аударым") & (seg_data["Төлем түрі"].str.contains(f"-> {bank}$", na=False))]["Сома"].sum()
                t_out = seg_data[(seg_data["Түрі"] == "Аударым") & (seg_data["Төлем түрі"].str.contains(f"^{bank} ->", na=False))]["Сома"].sum()
                balance = inc - exp + t_in - t_out
            else:
                balance = 0
                
            cols[i].metric(bank, f"{format_num(balance)} ₸")
        
    def render_debt_summary(seg_debts):
        st.markdown("### 💸 Қарыздар есебі (Учет долгов)")
        
        # Считаем суммы только для открытых (Ашық) долгов
        if not seg_debts.empty:
            # 1. Кто должен мне (Asset)
            i_lent = seg_debts[(seg_debts["Түрі"] == "Маған қарыз") & (seg_debts["Мәртебе"] == "Ашық")]["Сома"].sum()
            # 2. Кому должен я (Liability)
            i_borrowed = seg_debts[(seg_debts["Түрі"] == "Мен қарызбын") & (seg_debts["Мәртебе"] == "Ашық")]["Сома"].sum()
        else:
            i_lent, i_borrowed = 0, 0

        # Выводим две колонки, как ты просил
        c1, c2 = st.columns(2)
        with c1:
            st.info("**Кім маған қарыз? (Мне должны)**")
            st.subheader(f"{format_num(i_lent)} ₸")
        with c2:
            st.warning("**Кімге мен қарызбын? (Я должен)**")
            st.subheader(f"{format_num(i_borrowed)} ₸")

    # 2. Новая операция (свернута)
    with st.expander(f"📝 {segment_label}: Жаңа операция қосу", expanded=False):
        t1, t2, t3, t4 = st.tabs(["📉 Шығын", "📈 Кіріс", "🔄 Аударым", "💸 Қарыз"])
        
        with t1:
            with st.form(f"ex_{segment_name}"):
                c1, c2, c3 = st.columns(3)
                d = c1.date_input("Күн")
                cat = c2.selectbox("Санат", ["Тамақ", "Көлік", "Тұрғын үй", "Бизнес шығын", "Денсаулық", "Басқа"])
                bk = c3.selectbox("Шот", banks)
                amt = st.number_input("Сома", min_value=0, step=1000)
                desc = st.text_input("Сипаттама")
                if st.form_submit_button("Сақтау"):
                    add_transaction_db(d, "Шығын", cat, bk, amt, desc, segment_name)
                    st.success("Сақталды!"); st.rerun()

        with t2:
            with st.form(f"in_{segment_name}"):
                c1, c2, c3 = st.columns(3)
                d = c1.date_input("Күн")
                cat = c2.selectbox("Кіріс түрі", ["Жалақы", "Табыс", "Сыйлық", "Бизнес табыс"])
                bk = c3.selectbox("Шот", banks)
                amt = st.number_input("Сома", min_value=0, step=1000)
                desc = st.text_input("Сипаттама")
                if st.form_submit_button("Сақтау"):
                    add_transaction_db(d, "Кіріс", cat, bk, amt, desc, segment_name)
                    st.success("Сақталды!"); st.rerun()

        with t3:
            with st.form(f"tr_{segment_name}"):
                c1, c2, c3 = st.columns(3)
                d = c1.date_input("Күн")
                f_bk = c2.selectbox("Қайдан", banks)
                t_bk = c3.selectbox("Қайда", banks)
                amt = st.number_input("Сома", min_value=0)
                if st.form_submit_button("Аудару"):
                    if f_bk != t_bk:
                        add_transaction_db(d, "Аударым", "Аударым", f"{f_bk} -> {t_bk}", amt, "Аударым", segment_name)
                        st.success("Аударылды!"); st.rerun()

        with t4:
            with st.form(f"db_{segment_name}"):
                c1, c2, c3 = st.columns(3)
                d = c1.date_input("Күн")
                name = c2.text_input("Кім?")
                tp = c3.selectbox("Түрі", ["Маған қарыз", "Мен қарызбын"])
                amt = st.number_input("Сома", min_value=0)
                bk = st.selectbox("Шот", banks)
                if st.form_submit_button("Қарызды жазу"):
                    d_id = datetime.now().strftime("%Y%m%d%H%M%S")
                    add_debt_db(d_id, d, name, tp, bk, amt, segment_name)
                    # Также в общую ленту
                    t_tp = "Шығын" if tp == "Маған қарыз" else "Кіріс"
                    add_transaction_db(d, t_tp, "Қарыз", bk, amt, f"Қарыз: {name}", segment_name)
                    st.success("Жазылды!"); st.rerun()

    # 3. Аналитика (свернута)
    with st.expander(f"📊 {segment_label}: Аналитика", expanded=False):
        if not seg_data.empty:
            c1, c2 = st.columns(2)
            exp_only = seg_data[(seg_data["Түрі"] == "Шығын") & (seg_data["Санат"] != "Аударым")]
            if not exp_only.empty:
                fig = px.pie(exp_only, values='Сома', names='Санат', title="Шығындар құрылымы")
                c1.plotly_chart(fig, use_container_width=True)
            
            # Удаление записей
            st.write("---")
            st.write("🗑️ Соңғы жазбаны өшіру")
            if not seg_data.empty:
                last_row = seg_data.iloc[-1]
                if st.button(f"Өшіру: {last_row['Күн']} | {last_row['Сома']} ₸", key=f"del_{segment_name}"):
                    delete_transaction_db(last_row['id'])
                    st.success("Өшірілді!"); st.rerun()

    # 4. История (свернута)
    with st.expander(f"📜 {segment_label}: Транзакциялар тарихы", expanded=False):
        if not seg_data.empty:
            st.dataframe(seg_data.sort_values("Күн", ascending=False), use_container_width=True)
        else:
            st.info("Мәлімет жоқ")

with tab_business:
    render_segment("Бизнес", "Бизнес")

with tab_personal:
    render_segment("Личное", "Жеке шығындар")

# --- ОБЩИЙ БЛОК ҚАРЫЗДАР (внизу) ---
st.divider()
with st.expander("⏳ Өтелмеген қарыздар (Барлығы)", expanded=False):
    active = debts_data[debts_data["Мәртебе"] == "Ашық"] if not debts_data.empty else pd.DataFrame()
    if not active.empty:
        for i, row in active.iterrows():
            col_text, col_btn = st.columns([4, 1])
            col_text.write(f"**{row['Аты']}** — {format_num(row['Сома'])} ₸ ({row['segment']})")
            if col_btn.button("Жабу", key=f"close_{row['id']}"):
                close_debt_db(row['id'])
                # Отражаем возврат
                t_tp = "Кіріс" if row['Түрі'] == "Маған қарыз" else "Шығын"
                add_transaction_db(datetime.now(), t_tp, "Қарыз қайтару", row['Банк'], row['Сома'], f"Қайтарылды: {row['Аты']}", row['segment'])
                st.rerun()
    else:
        st.info("Белсенді қарыздар жоқ.")