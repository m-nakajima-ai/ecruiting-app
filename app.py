import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
import re

# ページ設定
st.set_page_config(page_title="人材エージェントAI", page_icon="🚀", layout="wide")
st.title("🚀 人材エージェントAI")

# --- サイドバー設定 ---
st.sidebar.header("設定")
sheet_name = st.sidebar.text_input("スプレッドシート名", value="案件管理DB")

# --- 認証と準備 ---
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

# --- タブの作成 ---
tab1, tab2 = st.tabs(["📧 メール＆プロフィール作成", "➕ 案件登録 (テキスト解析)"])

# ==========================================
# タブ1：メール＆プロフィール作成機能
# ==========================================
with tab1:
    st.markdown("### 📝 面談メモから作成")
    notes = st.text_area("面談メモ", height=150, placeholder="中島さん、30代、Webデザイン経験あり...", key="note_input")

    # ★ここに追加！手動か自動か選べるスイッチ
    use_ai_matching = st.checkbox("✅ AIに案件を提案させる（チェックを外すとプロフィールとメールの型だけ作ります）", value=True)

    if st.button("🚀 作成する", type="primary"):
        if not notes:
            st.warning("面談メモを入力してください！")
            st.stop()

        status_area = st.empty()
        
        # 案件リストの取得（AI提案がオンのときだけ読み込む）
        csv_text = ""
        if use_ai_matching:
            status_area.info("📂 スプレッドシートを読み込み中...")
            try:
                worksheet = gc.open(sheet_name).sheet1
                rows = worksheet.get_all_values()
                if rows:
                    header = rows.pop(0)
                    df = pd.DataFrame(rows, columns=header)
                    csv_text = df.to_string(index=False)
                    status_area.info(f"✅ 案件リスト取得成功: 全{len(df)}件。AIが生成中...")
            except Exception as e:
                st.error(f"❌ スプレッドシートが見つかりません: {sheet_name}")
                st.stop()
        else:
            status_area.info("📝 AI提案はOFFです。プロフィールとメールの型のみ作成します...")

        # プロンプトの切り替えロジック
        if use_ai_matching:
            # 自動モードの指示
            instruction_job = """
            3. 【案件リストデータ】の中から、候補者に最も適した案件を1つ選び、メール内の [ここに案件情報を挿入] の部分に記載すること。
            4. 案件情報のスタイル（■を使う形式）は完全に再現すること。
            """
            data_context = f"【案件リストデータ】\n{csv_text}"
        else:
            # 手動モードの指示
            instruction_job = """
            3. メール内の [ここに案件情報を挿入] の部分には、具体的な案件は入れず、「**（ここに手動で案件を貼り付けてください）**」というプレースホルダーの文字だけを残すこと。
            4. 勝手に案件を捏造したり提案したりしないこと。
            """
            data_context = ""

        # メインプロンプト
        prompt = f"""
        あなたはプロの人材エージェントのアシスタントです。
        以下の【面談メモ】をもとに、以下の2つを出力してください。
        
        1. **候補者プロフィール**（指定フォーマットで抽出）
        2. **候補者への提案メール**（指定フォーマットで作成）

        【面談メモ】
        {notes}

        {data_context}

        【重要ルール】
        1. 「内部メモ_送付NG」列の内容はメールには記載しないこと。
        2. プロフィール項目の情報がない場合は推測せず空欄または「？」とすること。
        {instruction_job}
        5. メール本文のテンプレートは一言一句変えずに使うこと。

        【出力フォーマット】
        以下の点線で区切られた形式で出力してください。

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
        
        （以下、メールドラフト）

        --------------------------------------------------
        [氏名]様

        お世話になります。プロの副業の中島です。

        先程はお忙しいところお電話にてご対応いただき、
        誠にありがとうございました。

        今後案件をご紹介させて頂くにあたり、こちらのメールにて職務経歴書をお送り頂くことは可能でしょうか？
        マッチングした案件をご紹介させていただければと思いますので、何卒ご確認いただけますと幸いです。

        また、下記直近の案件概要になります。もしよろしければ、是非お力添えいただけますと幸いです。

        [ここに案件情報を挿入]

        引き続きどうぞよろしくお願いいたします。
        --------------------------------------------------

        【（参考）案件記載スタイル】
        [社名]：
        [案件タイトル]

        ■概要
        [概要の内容]
        ...
        """

        try:
            response = model.generate_content(prompt)
            status_area.success("✨ 完成しました！")
            st.text_area("生成結果", value=response.text, height=800)
            
        except Exception as e:
            st.error(f"AI生成エラー: {e}")

# ==========================================
# タブ2：案件登録機能（変更なし）
# ==========================================
with tab2:
    st.markdown("### ➕ テキストから案件を自動登録")
    st.info("チャットやメールで来た案件情報をそのまま貼り付けてください。AIが自動で項目に分けます。")
    
    raw_job_text = st.text_area("案件テキストを貼り付け", height=300, placeholder="社名：株式会社〇〇\n概要：...\n(そのままペーストしてください)")

    if st.button("🤖 解析してシートに追加", type="secondary"):
        if not raw_job_text:
            st.warning("テキストを入力してください")
            st.stop()
        
        status_box = st.empty()
        status_box.info("🤖 AIがテキストを解析中...")

        # 解析用プロンプト
        parse_prompt = f"""
        以下の求人案件テキストを解析し、指定のJSON形式で出力してください。
        
        【入力テキスト】
        {raw_job_text}

        【出力すべき項目（キー）】
        "社名", "案件タイトル", "概要", "業務内容", "稼働条件", "求める人物像", "内部メモ_送付NG"

        【ルール】
        1. 必ず純粋なJSON形式のみを出力すること（Markdown記法は不要）。
        2. 情報がない項目は空文字 "" にすること。
        3. 「👇ここから下はいくらない」などの記述があれば、それ以降の内容はすべて「内部メモ_送付NG」に入れること。
        """

        try:
            # AIに解析させる
            response = model.generate_content(parse_prompt)
            cleaned_json = response.text.replace("```json", "").replace("```", "").strip()
            job_data = json.loads(cleaned_json)

            # プレビュー表示
            st.write("▼ 解析結果プレビュー（まだ保存されていません）")
            preview_df = pd.DataFrame([job_data])
            st.dataframe(preview_df)

            # スプレッドシートに追加
            worksheet = gc.open(sheet_name).sheet1
            
            # データの並び順をシートに合わせる
            row_to_add = [
                job_data.get("社名", ""),
                job_data.get("案件タイトル", ""),
                job_data.get("概要", ""),
                job_data.get("業務内容", ""),
                job_data.get("稼働条件", ""),
                job_data.get("求める人物像", ""),
                job_data.get("内部メモ_送付NG", "")
            ]
            
            worksheet.append_row(row_to_add)
            
            status_box.success(f"✅ 「{job_data.get('社名')}」の案件をスプレッドシートに追加しました！")
            st.balloons()

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            st.write("AIの生出力:", response.text)
