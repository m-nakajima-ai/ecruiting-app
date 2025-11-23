import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd

# ページ設定
st.set_page_config(page_title="人材エージェントAI", page_icon="🚀")
st.title("🚀 人材エージェントAI")

# --- サイドバー設定 ---
st.sidebar.header("設定")
sheet_name = st.sidebar.text_input("スプレッドシート名", value="案件管理DB")

# --- 1. 認証と準備 ---
try:
    # SecretsからAPIキーとGCP鍵を読み込む
    if "GEMINI_API_KEY" not in st.secrets or "GCP_JSON_KEY" not in st.secrets:
        st.error("⚠️ Secrets（設定）がまだ完了していません。Streamlitの管理画面でキーを設定してください。")
        st.stop()

    # Gemini API設定
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.0-flash')

    # スプレッドシート認証
    # JSON文字列を辞書データに戻す
    service_account_info = json.loads(st.secrets["GCP_JSON_KEY"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc = gspread.authorize(creds)

except Exception as e:
    st.error(f"認証エラーが発生しました: {e}")
    st.stop()

# --- 2. 画面構成 ---
st.markdown("### 面談メモ入力")
notes = st.text_area("ここにメモを貼り付けてください", height=150, placeholder="永長さん、32歳、Javaが得意...")

if st.button("🚀 AIを実行する", type="primary"):
    if not notes:
        st.warning("面談メモを入力してください！")
        st.stop()

    status_area = st.empty()
    status_area.info("📂 スプレッドシートを読み込み中...")

    # --- 3. スプレッドシート読み込み ---
    try:
        worksheet = gc.open(sheet_name).sheet1
        rows = worksheet.get_all_values()
        if not rows:
            st.error("❌ シートが空っぽです！")
            st.stop()
        
        header = rows.pop(0)
        df = pd.DataFrame(rows, columns=header)
        csv_text = df.to_string(index=False)
        status_area.info(f"✅ 案件リスト取得成功: 全{len(df)}件。AIが生成中...")

    except Exception as e:
        st.error(f"❌ スプレッドシートが見つかりません: {sheet_name}")
        st.info("ヒント: ロボット(サービスアカウント)のメールアドレスをスプレッドシートに「共有」しましたか？")
        st.stop()

    # --- 4. プロンプト作成と実行 ---
    prompt = f"""
    あなたは几帳面な人材エージェントのアシスタントです。
    以下の【面談メモ】と【案件リスト】をもとに、指定された【出力フォーマット】を厳密に守って出力してください。

    【面談メモ】
    {notes}

    【案件リスト】
    {csv_text}

    【指示事項】
    1. プロフィールの各項目について、情報がメモにない場合は推測せず「？」と記入すること。
    2. メールのテンプレートは挨拶文や締め文を一言一句変更せず使用すること。
    3. メール内の [ここに推奨案件を挿入] の部分にのみ、CSVから選定した案件（案件名、条件、選定理由）を記載すること。

    【出力フォーマット】
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

    本日はお忙しい所貴重なお時間を頂きまして、誠にありがとうございました。
    また、今後案件をご紹介させて頂くにあたり、
    こちらのメールにて職務経歴書をお送りいただくことは可能でしょうか。

    今後マッチングした案件をご紹介できればと思いますので、
    何卒よろしくお願いいたします。

    下記案件概要になります。
    よろしければご確認いただけますと幸いです。

    [ここに推奨案件を挿入]

    何卒ご確認いただけますと幸いです。
    引き続きよろしくお願いいたします。
    --------------------------------------------------
    """

    try:
        response = model.generate_content(prompt)
        status_area.success("✨ 完成しました！")
        st.markdown("---")
        st.text_area("生成結果（コピー用）", value=response.text, height=600)
        
    except Exception as e:
        st.error(f"AI生成エラー: {e}")
