import streamlit as st
import google.generativeai as genai
import sqlite3
import json
import time
from datetime import datetime
from streamlit_agraph import agraph, Node, Edge, Config


# --- 1. 数据库逻辑 (持久化存储历史记录) ---
def init_db():
    conn = sqlite3.connect('../story_station_pro.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS analysis_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  filename TEXT,
                  summary TEXT,
                  time TEXT)''')
    conn.commit()
    return conn


# --- 2. 关系图渲染逻辑 ---
def render_graph(raw_text):
    try:
        # 从混合文本中提取最后的 JSON 块
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

# --- 4. 主界面：文件处理与流式分析 ---
st.title("🧠 深度故事分析工作站")
st.markdown("支持多文件处理、流式实时输出及人物关系建模")

# 尝试从 secrets 获取，如果不存在则设为 None
try:
    default_key = st.secrets["GEMINI_API_KEY"]
except:
    default_key = ""

col_api, col_file = st.columns([1, 2])
with col_api:
    # 如果 secrets 里有值，这里会自动填入
    api_key = st.text_input(
        "Gemini API Key",
        value=default_key,
        type="password",
        help="已自动加载本地配置，如需更换请在此修改"
    )
    uploaded_files = st.file_uploader("上传 TXT 文件 (支持批量)", type="txt", accept_multiple_files=True)

if uploaded_files and st.button("🚀 开始批量分析"):
    if not api_key:
        st.error("请输入 API Key 后再继续。")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')

        for index, file in enumerate(uploaded_files):
            # A. 文件大小限制 (1MB)
            if file.size > 1024 * 1024:
                st.warning(f"跳过 {file.name}: 文件超过 1MB 限制。")
                continue

            try:
                content = file.read().decode("utf-8", errors="ignore")

                # B. 构建 Prompt
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

                # C. 流式输出效果
                # 使用 stream=True 开启流式传输
                response = model.generate_content(prompt, stream=True)


                def stream_data():
                    full_response = ""
                    for chunk in response:
                        full_response += chunk.text
                        yield chunk.text
                    # 保存到数据库
                    now = datetime.now().strftime("%m-%d %H:%M")
                    conn.execute("INSERT INTO analysis_history (filename, summary, time) VALUES (?, ?, ?)",
                                 (file.name, full_response, now))
                    conn.commit()


                # 在界面上展示打字机效果
                st.write_stream(stream_data)
                st.success(f"{file.name} 分析并保存成功！")
                # D. 频率限制保护 (多文件时)
                if index < len(uploaded_files) - 1:
                    st.info("等待 API 配额刷新 (10秒)...")
                    time.sleep(10)

            except Exception as e:
                st.error(f"分析 {file.name} 时出错: {e}")
# --- 5. 结果展示区 (查看历史或刚生成的记录) ---
if 'selected_id' in st.session_state:
    res = conn.execute("SELECT filename, summary FROM analysis_history WHERE id=?",
                       (st.session_state.selected_id,)).fetchone()
    if res:
        st.divider()
        st.header(f"📑 报告详情：{res[0]}")

        tab1, tab2 = st.tabs(["📖 阅读总结", "🕸️ 人物关系图谱"])

        with tab1:
            # 过滤掉 JSON，只显示文字
            text_only = res[1].split('{')[0]
            st.markdown(text_only)

        with tab2:
            st.info("💡 提示：你可以用鼠标拖动节点，或使用滚轮缩放图谱。")
            render_graph(res[1])