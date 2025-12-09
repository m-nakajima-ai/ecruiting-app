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
candidate_sheet_name = "人材DB" 

# --- 認証と準備 ---
try:
    if "GEMINI_API_KEY" not in st.secrets or "GCP_JSON_KEY" not in st.secrets:
        st.error("⚠️ Secrets未設定")
        st.stop()

    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    
    # ★ここを一番安定して動く「gemini-pro」に変更しました（これで404は出ません）
    model = genai.GenerativeModel('gemini-pro')

    service_account_info = json.loads(st.secrets["GCP_JSON_KEY"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc = gspread.authorize(creds)
except Exception as e:
    st.error(f"認証エラー: {e}")
    st.stop()

# --- タブ構成 ---
tab1, tab2 = st.tabs(["📝 CA業務 (登録・メール作成)", "🤝 RA業務 (商談・提案)"])

# ==========================================
# 【タブ1】CA向け：フォーマット指定版
# ==========================================
with tab1:
    st.header("新規人材の登録 & 提案メール作成")
    
    col1, col2 = st.columns(2)
    with col1:
        uploaded_file = st.file_uploader("職務経歴書 (PDF) をアップロード", type="pdf")
    with col2:
        notes = st.text_area("面談メモ", height=150, placeholder="永長さん、32歳、Javaが得意...")

    if st.button("🚀 AIを実行＆DB登録", type="primary"):
        if not notes and not uploaded_file:
            st.warning("メモかPDFを入力してください")
            st.stop()

        status_area = st.empty()
        status_area.info("📂 情報を解析中...")

        # PDF解析
        resume_text = ""
        if uploaded_file:
            try:
                reader = PyPDF2.PdfReader(uploaded_file)
                for page in reader.pages:
                    resume_text += page.extract_text()
            except: pass

        # 案件リスト取得
        try:
            worksheet = gc.open(sheet_name).sheet1 
            rows = worksheet.get_all_values()
            header = rows.pop(0)
            df = pd.DataFrame(rows, columns=header)
            job_list_text = df.to_string(index=False)
        except Exception as e:
            st.error(f"案件リストエラー: {e}")
            st.stop()

        # --- プロンプト（フォーマット指定）---
        prompt = f"""
        あなたは優秀な人材エージェントです。
        以下の情報をもとに、指定のJSON形式で出力してください。
        メール本文や登録データには、以下の【出力フォーマット】の構成を必ず含めてください。

        【入力情報】
        面談メモ: {notes}
        職務経歴書: {resume_text}
        保有案件リスト: {job_list_text}

        【出力形式】
        必ず以下のJSON形式のみを出力してください（Markdown不要）。
        {{
            "display_text": "ここに【以前のフォーマット通りのテキスト】を入れる。\\n-------------------\\n【新規/既存】...から始まり、メール本文まで全て含めること。",
            "db_data": {{
                "name": "氏名",
                "age": "年齢",
                "skills": "スキル",
                "pr_summary": "PR要約",
                "conditions": "希望条件"
            }}
        }}

        【以前のフォーマット構成（display_textの中身）】
        --------------------------------------------------
        【新規/既存】[新規か既存か判定]
        氏名：[氏名]
        年齢：[年齢]
        時給：[時給]
        対応可能職種：[職種]
        稼動可能時間：[時間]
        対面稼動可否：[可否]
        在住：[在住地]
        PR文：[PR文を要約]
        --------------------------------------------------

        --------------------------------------------------
        [氏名] 様

        お世話になっております。プロの副業の中島です。
        （中略：以前と同じテンプレート）
        下記案件概要になります。
        [ここに推奨案件を挿入]
        --------------------------------------------------
        """

        try:
            response = model.generate_content(prompt)
            cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
            result_json = json.loads(cleaned_text)

            # --- DB保存 ---
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
                status_area.success(f"✅ {result_json['db_data']['name']} さんをDB保存しました")
            except:
                status_area.warning("⚠️ DB保存失敗（でもテキスト生成は完了）")

            # --- 表示 ---
            st.subheader("出力結果")
            st.text_area("チャット共有・メール送信用", value=result_json["display_text"], height=600)

        except Exception as e:
            st.error(f"AIエラー: {e}")

# ==========================================
# 【タブ2】RA向け：商談メモからリアルタイム検索
# ==========================================
with tab2:
    st.header("商談中のリアルタイム人材提案")
    sales_notes = st.text_area("商談メモ", height=100)
    
    if st.button("🔍 人材DBから検索", type="primary"):
        status_search = st.empty()
        status_search.info("検索中...")

        try:
            c_sheet = gc.open(sheet_name).worksheet(candidate_sheet_name)
            c_rows = c_sheet.get_all_values()
            c_df = pd.DataFrame(c_rows[1:], columns=c_rows[0])
            candidates_text = c_df.to_string(index=False)
            
            search_prompt = f"""
            商談メモに基づき、人材DBから最適な3名を選んで提案してください。
            【商談メモ】{sales_notes}
            【人材DB】{candidates_text}
            """
            proposal = model.generate_content(search_prompt)
            status_search.success("完了")
            st.markdown(proposal.text)
        except Exception as e:
            st.error(f"検索エラー: {e}")
