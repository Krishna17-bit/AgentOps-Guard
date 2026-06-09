
APP_CSS = """
<style>
:root {
  --bg: #f6f7fb;
  --card: #ffffff;
  --card2: #f9fafc;
  --ink: #111827;
  --muted: #5f6675;
  --line: #e5e7eb;
  --soft: #f1f5f9;
  --primary: #ff5a1f;
  --primary-dark: #c2410c;
  --blue: #2563eb;
  --green: #059669;
  --red: #dc2626;
  --yellow: #b7791f;
  --purple: #7c3aed;
}
html, body, [class*="css"] { color: var(--ink); }
.stApp { background: var(--bg); color: var(--ink); }
section[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid var(--line); }
section[data-testid="stSidebar"] * { color: var(--ink) !important; }
.block-container { padding-top: 1.6rem; max-width: 1320px; }
.hero {
  padding: 28px 30px;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: radial-gradient(circle at top right, #fff1e8 0, #ffffff 42%, #f8fafc 100%);
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.08);
  margin-bottom: 20px;
}
.hero-kicker {
  display: inline-block;
  font-size: 12px;
  font-weight: 800;
  color: var(--primary-dark);
  background: #fff0e8;
  border: 1px solid #fed7c2;
  padding: 6px 10px;
  border-radius: 999px;
  margin-bottom: 10px;
  letter-spacing: .04em;
  text-transform: uppercase;
}
.hero-title { font-size: 46px; font-weight: 900; letter-spacing: -1.8px; color: var(--ink); }
.hero-subtitle { color: var(--muted); font-size: 16px; line-height: 1.65; max-width: 1080px; }
.metric-card {
  border: 1px solid var(--line);
  background: var(--card);
  padding: 18px;
  border-radius: 20px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
}
.metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 800; }
.metric-value { color: var(--ink); font-size: 34px; font-weight: 900; margin-top: 4px; }
.metric-note { color: var(--muted); font-size: 13px; margin-top: 4px; }
.panel {
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 18px;
  background: var(--card);
  color: var(--ink);
  line-height: 1.58;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05);
}
.panel-soft {
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 16px;
  background: #f8fafc;
  color: var(--ink);
}
.connector-card {
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 16px;
  background: #ffffff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
  min-height: 150px;
}
.connector-title { font-weight: 900; font-size: 18px; color: var(--ink); margin-bottom: 4px; }
.connector-desc { color: var(--muted); font-size: 13px; line-height: 1.45; }
.small-muted { color: var(--muted); font-size: 13px; }
.status-pill {
  display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 12px;
  border: 1px solid var(--line); color: var(--ink); background: #f8fafc; margin-right: 6px; margin-bottom: 5px;
  font-weight: 700;
}
.pill-ok { border-color: #bbf7d0; color: #047857; background: #ecfdf5; }
.pill-danger { border-color: #fecaca; color: #b91c1c; background: #fef2f2; }
.pill-warn { border-color: #fde68a; color: #92400e; background: #fffbeb; }
.pill-blue { border-color: #bfdbfe; color: #1d4ed8; background: #eff6ff; }
.pill-critical { border-color: #fecaca; color: #991b1b; background: #fff1f2; }
.evidence { background: #fff; border: 1px solid var(--line); border-left: 4px solid var(--primary); padding: 14px; border-radius: 12px; margin: 8px 0; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] {
  background: #ffffff; border: 1px solid var(--line); border-bottom: 0; border-radius: 14px 14px 0 0;
  padding: 10px 14px; color: var(--muted); font-weight: 800;
}
.stTabs [aria-selected="true"] { color: var(--primary-dark) !important; background: #fff7ed !important; border-color: #fed7aa !important; }
div.stButton > button { background: var(--primary) !important; color: white !important; border: 0 !important; font-weight: 900 !important; border-radius: 14px !important; padding: 0.68rem 1rem !important; box-shadow: 0 10px 24px rgba(255, 90, 31, 0.22); }
div.stDownloadButton > button { background: var(--blue) !important; color: white !important; border: 0 !important; font-weight: 900 !important; border-radius: 14px !important; padding: 0.68rem 1rem !important; }
.stAlert { color: var(--ink) !important; background: #ffffff !important; border: 1px solid var(--line) !important; }
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 16px; overflow: hidden; background: #ffffff; }
textarea, input, div[data-baseweb="select"] > div { color: var(--ink) !important; background: #ffffff !important; border-color: var(--line) !important; }
code, pre { color: #111827 !important; background: #f8fafc !important; border: 1px solid var(--line); border-radius: 12px; }
hr { border-color: var(--line); }
</style>
"""
