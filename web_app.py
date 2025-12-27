import streamlit as st
import google.generativeai as genai
import sqlite3
import json
import time
from datetime import datetime
from streamlit_agraph import agraph, Node, Edge, Config


# --- 1. 数据库逻辑 (统一路径，适配云端) ---
def init_db():
    # 删掉了 ../ 确保在云端也能正常创建数据库
    conn = sqlite3.connect('story_station_pro.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS analysis_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  filename TEXT,
                  summary TEXT,
                  time TEXT)''')
    conn.commit()
    return conn


# --- 2. 关系图渲染逻辑 (保持不变) ---
def render_graph(raw_text):
    try:
        start = raw_text.find('{')
        end = raw_text.rfind('}') + 1
        if start == -1 or end == 0:
            return st.info("该条记录未包含可识别的人物关系数据。")

        data = json.loads(raw_text[start:end])
        nodes = [Node(id=name, label=name, size=20, color="#FF4B4B") for name in data.get('nodes', [])]
        edges = [Edge(source=e[0], target=e[1], label=e[2]) for e in data.get('edges', [])]

        config = Config(width=800, height=500, directed=True, nodeHighlightBehavior=True)
        return agraph(nodes=nodes, edges=edges, config=config)
    except Exception:
        st.warning("暂无法生成关系图谱，可能 JSON 格式不规范。")


# --- 3. 页面配置与初始化 ---
st.set_page_config(layout="wide", page_title="AI 文学深度分析站", page_icon="📑")
conn = init_db()

# 侧边栏：历史档案管理
with st.sidebar:
    st.title("📚 历史分析档案")
    st.write("---")
    cursor = conn.cursor()
    history = cursor.execute("SELECT id, filename, time FROM analysis_history ORDER BY id DESC").fetchall()

    for item in history:
        col_name, col_del = st.columns([4, 1])
        with col_name:
            if st.button(f"📄 {item[1]}\n({item[2]})", key=f"hist_{item[0]}"):
                st.session_state.selected_id = item[0]

    if st.button("🗑️ 清空所有记录"):
        conn.execute("DELETE FROM analysis_history")
        conn.commit()
        st.rerun()

# --- 4. 主界面：逻辑结构优化 ---
st.title("🧠 深度故事分析工作站")
st.markdown("支持多文件处理、流式实时输出及人物关系建模")

# --- 优化后的 API Key 处理逻辑 ---
api_key = ""
# 1. 优先尝试从 Secrets（云端/本地配置）读取
if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("🔑 API Key 已安全加载")
else:
    # 2. 如果没配，才在主页显示输入框
    api_key = st.text_input("Gemini API Key", type="password", help="请在后台配置以隐藏此框")

# --- 统一的文件上传区 (只写一次) ---
uploaded_files = st.file_uploader("📂 上传 TXT 文件 (支持批量)", type="txt", accept_multiple_files=True)

if uploaded_files and st.button("🚀 开始批量分析"):
    if not api_key:
        st.error("请输入 API Key 后再继续。")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')

        for index, file in enumerate(uploaded_files):
            if file.size > 1024 * 1024:
                st.warning(f"跳过 {file.name}: 文件超过 1MB 限制。")
                continue

            try:
                # 确保每次循环都读取文件内容
                content = file.read().decode("utf-8", errors="ignore")

                prompt = f"""
                作为文学分析专家，请阅读下文并输出：
                1. 文章大意总结。
                2. 故事主要情节。
                3. 人物关系 JSON (必须严格放在回答最后)。
                格式模板：
                {{ "nodes": ["角色A"], "edges": [["角色A", "角色B", "关系"]] }}
                内容：{content}
                """

                st.subheader(f"正在分析: {file.name}")

                # 流式生成
                response = model.generate_content(prompt, stream=True)


                def stream_data():
                    full_res = ""
                    for chunk in response:
                        full_res += chunk.text
                        yield chunk.text

                    # 只有流结束后才写入数据库
                    now = datetime.now().strftime("%m-%d %H:%M")
                    # 使用当前线程的连接
                    temp_conn = sqlite3.connect('story_station_pro.db')
                    temp_conn.execute("INSERT INTO analysis_history (filename, summary, time) VALUES (?, ?, ?)",
                                      (file.name, full_res, now))
                    temp_conn.commit()
                    temp_conn.close()


                st.write_stream(stream_data)
                st.success(f"{file.name} 分析完毕！")

                if index < len(uploaded_files) - 1:
                    time.sleep(5)  # 稍微缩短等待时间

            except Exception as e:
                st.error(f"分析 {file.name} 时出错: {e}")

# --- 5. 结果展示区 ---
if 'selected_id' in st.session_state:
    res = conn.execute("SELECT filename, summary FROM analysis_history WHERE id=?",
                       (st.session_state.selected_id,)).fetchone()

    if res:
        st.divider()
    st.header(f"📑 报告详情：{res[0]}")
    tab1, tab2 = st.tabs(["📖 阅读总结", "🕸️ 人物关系图谱"])
    with tab1:
        st.markdown(res[1].split('{')[0])
    with tab2:
        render_graph(res[1])