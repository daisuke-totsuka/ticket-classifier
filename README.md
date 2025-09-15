# チケット分類アプリ（Gemini API 版）

このアプリケーションは、Google Gemini API を使用してチケット内容を自動分類する Web アプリケーションです。

## セットアップ手順

### 1. Gemini API キーの取得

1. [Google AI Studio](https://makersuite.google.com/app/apikey)にアクセス
2. Google アカウントでログイン
3. 「Create API Key」をクリックして API キーを生成
4. 生成された API キーをコピー

### 2. 環境変数の設定

#### Windows (PowerShell)

```powershell
$env:GEMINI_API_KEY="your-api-key-here"
```

#### Windows (Command Prompt)

```cmd
set GEMINI_API_KEY=your-api-key-here
```

#### Linux/Mac

```bash
export GEMINI_API_KEY="your-api-key-here"
```

### 3. バックエンドのセットアップ

```bash
cd backend
pip install -r requirements.txt
python app.py
```

### 4. フロントエンドのセットアップ

```bash
cd frontend
npm install
npm start
```

## 使用方法

1. ブラウザで `http://localhost:3000` にアクセス
2. テキストエリアにチケット内容を入力
3. 「分類」ボタンをクリック
4. AI がチケットを適切なカテゴリに分類します

## Gemini API の無料枠について

- 1 分間に 60 リクエストまで
- 1 日あたり 15,000 リクエストまで
- 入力トークン: 1 分間に 32,000 トークンまで
- 出力トークン: 1 分間に 32,000 トークンまで

## 注意事項

- API キーは環境変数として設定し、コード内に直接記述しないでください
- 本番環境では適切なセキュリティ対策を実施してください

