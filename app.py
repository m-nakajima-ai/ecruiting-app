import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
from datetime import datetime
import PyPDF2

# ページ設定
st.set_page_config(page_title="人材エージェントAI Pro", page_icon="🚀", layout="wide")
st.title("🚀 人材エージェントAI Pro")

# --- サイドバー設定 ---
st.sidebar.header("設定")
sheet_name = st.sidebar.text_input("スプレッドシート名", value="案件管理DB")
candidate_sheet_name = "人材DB" # 保存先のシート名

# --- 1. 認証と準備 ---
try:
    if "GEMINI_API_KEY" not in st.secrets or "GCP_JSON_KEY" not in st.secrets:
        st.error("⚠️ Secrets（設定）がまだ完了していません。")
        st.stop()

    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.0-flash')

    service_account_info = json.loads(st.secrets["GCP_JSON_KEY"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc = gspread.authorize(creds)

except Exception as e:
    st.error(f"認証エラーが発生しました: {e}")
    st.stop()

# --- 画面構成（タブ分け） ---
# ★ここが重要！タブを作る命令です
tab1, tab2 = st.tabs(["📝 CA業務 (登録・メール作成)", "🤝 RA業務 (商談・提案)"])

# ==========================================
# 【タブ1】CA向け：面談メモ/PDF → メール作成 & DB登録
# ==========================================
with tab1:
    st.header("新規人材の登録 & 提案メール作成")
    
    col1, col2 = st.columns(2)
    with col1:
        uploaded_file = st.file_uploader("職務経歴書 (PDF) をアップロード", type="pdf")
    with col2:
        notes = st.text_area("面談メモ (補足情報)", height=150, placeholder="人柄、話し方、PDFにない希望条件など...")

    if st.button("🚀 AIを実行＆DB登録", type="primary"):
        if not notes and not uploaded_file:
            st.warning("メモかPDF、どちらかは入力してください！")
            st.stop()

        status_area = st.empty()
        status_area.info("📂 情報を解析中...")

        # --- A. PDFのテキスト抽出 ---
        resume_text = ""
        if uploaded_file:
            try:
                reader = PyPDF2.PdfReader(uploaded_file)
                for page in reader.pages:
                    resume_text += page.extract_text()
                status_area.info("✅ PDF読み込み完了。案件リストとマッチング中...")
            except Exception as e:
                st.error(f"PDF読み込みエラー: {e}")
                st.stop()

        # --- B. 案件リスト(Job List)の取得 ---
        try:
            worksheet = gc.open(sheet_name).sheet1 
            rows = worksheet.get_all_values()
            header = rows.pop(0)
            df = pd.DataFrame(rows, columns=header)
            job_list_text = df.to_string(index=False)
        except Exception as e:
            st.error(f"案件リスト読み込みエラー: {e}")
            st.stop()

        # --- C. プロンプト作成 ---
        prompt = f"""
        あなたは優秀な人材エージェントです。
        以下の【入力情報】と【保有案件リスト】をもとに、
        1. データベース登録用のJSONデータ
        2. 企業への提案メール文面
        を作成してください。

        【入力情報】
        面談メモ: {notes}
        職務経歴書(PDF内容): {resume_text}

        【保有案件リスト】
        {job_list_text}

        【出力形式】
        必ず以下のJSON形式のみを出力してください（Markdownの ```json は不要）。
        {{
            "db_data": {{
                "name": "氏名（不明なら「？」）",
                "age": "年齢（不明なら「？」）",
                "skills": "主要スキル・職種",
                "pr_summary": "経歴と強みの要約（100文字程度）",
                "conditions": "希望条件（金額や稼働率など）"
            }},
            "email_content": "ここにメール本文全体を入れる。\\n挨拶文、選定した案件（案件名・選定理由）、締めを含めること。"
        }}
        """

        try:
            response = model.generate_content(prompt)
            cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
            result_json = json.loads(cleaned_text)

            # --- D. DBへの保存 ---
            try:
                db_sheet = gc.open(sheet_name).worksheet(candidate_sheet_name)
                new_row = [
                    datetime.now().strftime("%Y-%m-%d"),
                    result_json["db_data"]["name"],
                    result_json["db_data"]["age"],
                    result_json["db_data"]["skills"],
                    result_json["db_data"]["pr_summary"],
                    result_json["db_data"]["conditions"]
                ]
                db_sheet.append_row(new_row)
                status_area.success(f"✅ {result_json['db_data']['name']} さんを「{candidate_sheet_name}」に保存しました！")
            except Exception as e:
                status_area.warning(f"⚠️ DB保存に失敗しましたが、メールは生成しました: {e}")

            # --- E. メール表示 ---
            st.subheader("📩 生成されたメール文面")
            st.text_area("コピー用", value=result_json["email_content"], height=400)
            
            with st.expander("登録されたデータを確認"):
                st.json(result_json["db_data"])

        except Exception as e:
            st.error(f"AI生成エラー: {e}")

# ==========================================
# 【タブ2】RA向け：商談メモからリアルタイム検索
# ==========================================
with tab2:
    st.header("商談中のリアルタイム人材提案")
    sales_notes = st.text_area("商談メモ (企業の課題・欲しい人物像)", height=100, 
                             placeholder="例：急募。PM経験があり、PHPの開発も見れるプレイングマネージャー。予算80万くらい。")
    
    if st.button("🔍 人材DBから検索", type="primary"):
        status_search = st.empty()
        status_search.info("📂 人材DBを検索中...")

        # --- A. 人材DB読み込み ---
        try:
            c_sheet = gc.open(sheet_name).worksheet(candidate_sheet_name)
            c_rows = c_sheet.get_all_values()
            if len(c_rows) < 2:
                st.error("人材DBにデータがありません。CAタブから登録してください。")
                st.stop()
                
            c_df = pd.DataFrame(c_rows[1:], columns=c_rows[0])
            candidates_text = c_df.to_string(index=False)
        except Exception as e:
            st.error(f"人材DB読み込みエラー: {e}")
            st.stop()

        # --- B. 検索プロンプト ---
        search_prompt = f"""
        あなたはマッチングのプロです。
        【商談メモ】のニーズに最も合致する人材を、【人材DB】から最大3名選び出してください。
        
        【商談メモ】
        {sales_notes}
        
        【人材DB】
        {candidates_text}
        
        【出力形式】
        各候補者について、以下のフォーマットで出力してください。
        
        ### 1. [氏名] ([年齢])
        - **一致ポイント**: なぜこの企業に合うのか
        - **懸念点**: もしあれば
        - **紹介トーク**: 「〇〇様は〜の経験があり、御社の△△という課題に即戦力です」
        """
        
        try:
            proposal = model.generate_content(search_prompt)
            status_search.success("✨ 提案候補が見つかりました")
            st.markdown(proposal.text)
        except Exception as e:
            st.error(f"検索エラー: {e}")
