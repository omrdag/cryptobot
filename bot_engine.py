<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>CryptoBot Terminal</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'IBM Plex Mono',monospace}
:root{
  --bg:#050810;--bg1:#080d1a;--bg2:#0c1224;
  --border:#1a2540;--border2:#243060;
  --green:#00ff88;--green-dim:rgba(0,255,136,.08);
  --red:#ff3355;--red-dim:rgba(255,51,85,.08);
  --blue:#0088ff;--cyan:#00ccff;--yellow:#ffcc00;--purple:#aa55ff;
  --text:#e8edf8;--text2:#8899bb;--text3:#445577;
}
html,body{height:100%;background:var(--bg);color:var(--text);overflow:hidden}
.pos{color:var(--green)}.neg{color:var(--red)}.neu{color:var(--text)}
/* TOPBAR */
#topbar{display:flex;align-items:center;justify-content:space-between;height:42px;padding:0 16px;background:var(--bg1);border-bottom:1px solid var(--border);position:fixed;top:0;left:0;right:0;z-index:100}
.logo{font-size:13px;font-weight:700;letter-spacing:3px;color:var(--cyan)}.logo span{color:var(--green)}
.live-badge{display:flex;align-items:center;gap:6px;font-size:10px;color:var(--green);letter-spacing:1px}
.live-dot{width:6px;height:6px;border-radius:50%;background:var(--green);animation:blink 1.2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.top-metrics{display:flex;gap:20px}
.tm{display:flex;flex-direction:column;align-items:flex-end}
.tm-label{font-size:9px;color:var(--text3);letter-spacing:1px;text-transform:uppercase}
.tm-val{font-size:13px;font-weight:600}
#clock{font-size:11px;color:var(--text2)}
/* LAYOUT */
#app{display:grid;grid-template-columns:200px 1fr 260px;margin-top:42px;height:calc(100vh - 42px)}
/* SIDEBAR */
#sidebar{background:var(--bg1);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.s-lbl{font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--text3);padding:10px 14px 6px;border-bottom:1px solid var(--border)}
.nav-btn{display:flex;align-items:center;gap:8px;padding:10px 14px;font-size:11px;color:var(--text2);cursor:pointer;border-left:2px solid transparent;background:none;border-top:none;border-right:none;border-bottom:none;width:100%;text-align:left;transition:all .15s}
.nav-btn:hover{color:var(--text);background:rgba(255,255,255,.02)}
.nav-btn.active{color:var(--cyan);border-left-color:var(--cyan);background:rgba(0,204,255,.04)}
.coin-strip{flex:1;overflow-y:auto}
.coin-strip::-webkit-scrollbar{width:3px}
.coin-strip::-webkit-scrollbar-thumb{background:var(--border2)}
.coin-row{display:flex;justify-content:space-between;align-items:center;padding:8px 14px;border-bottom:1px solid rgba(26,37,64,.5);cursor:pointer;transition:background .1s}
.coin-row:hover{background:rgba(255,255,255,.02)}
.cn{font-size:11px;font-weight:600}.cs{font-size:9px;color:var(--text3)}
.cp{font-size:12px;font-weight:600;text-align:right}.cpct{font-size:10px;text-align:right}
.flash-g{animation:fg .4s}@keyframes fg{0%{background:rgba(0,255,136,.2)}100%{background:transparent}}
.flash-r{animation:fr .4s}@keyframes fr{0%{background:rgba(255,51,85,.2)}100%{background:transparent}}
/* MAIN */
#main{display:flex;flex-direction:column;overflow:hidden}
.tabs{display:flex;border-bottom:1px solid var(--border);background:var(--bg1);flex-shrink:0}
.tab{padding:0 18px;height:36px;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--text3);cursor:pointer;display:flex;align-items:center;border-bottom:2px solid transparent;background:none;border-top:none;border-left:none;border-right:none;transition:all .15s}
.tab:hover{color:var(--text)}.tab.active{color:var(--cyan);border-bottom-color:var(--cyan)}
.page{display:none;flex:1;overflow-y:auto;padding:12px}
.page.active{display:block}
.page::-webkit-scrollbar{width:4px}
.page::-webkit-scrollbar-thumb{background:var(--border2)}
/* POS CARDS */
.pos-grid{display:flex;flex-direction:column;gap:8px}
.pos-card{background:var(--bg1);border:1px solid var(--border);border-radius:6px;overflow:hidden}
.pos-card.long-card{border-left:3px solid var(--green)}
.pos-card.short-card{border-left:3px solid var(--red)}
.pc-head{display:flex;justify-content:space-between;align-items:center;padding:10px 14px 8px}
.pc-left{display:flex;align-items:center;gap:10px}
.pc-icon{width:30px;height:30px;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700}
.ic-btc{background:rgba(255,153,0,.15);color:#ff9900}
.ic-bnb{background:rgba(255,193,7,.15);color:#ffc107}
.ic-sol{background:rgba(170,85,255,.15);color:var(--purple)}
.ic-ondo{background:rgba(0,136,255,.15);color:var(--blue)}
.ic-pump{background:rgba(0,255,136,.15);color:var(--green)}
.ic-hype{background:rgba(255,102,0,.15);color:#ff6600}
.ic-def{background:rgba(136,153,187,.15);color:var(--text2)}
.pc-sym{font-size:14px;font-weight:700}.pc-meta{font-size:9px;color:var(--text3);margin-top:2px}
.pc-dir{font-size:9px;font-weight:700;padding:3px 8px;border-radius:3px;letter-spacing:1px}
.dir-long{background:var(--green-dim);color:var(--green);border:1px solid rgba(0,255,136,.2)}
.dir-short{background:var(--red-dim);color:var(--red);border:1px solid rgba(255,51,85,.2)}
.pc-pnl{text-align:right}
.pc-pnl-val{font-size:20px;font-weight:700}
.pc-pnl-pct{font-size:11px;margin-top:2px}
.pc-stats{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--border)}
.pc-stat{padding:8px 12px;border-right:1px solid var(--border)}
.pc-stat:last-child{border-right:none}
.psl{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}
.psv{font-size:11px;font-weight:500;margin-top:3px}
.pc-bar{padding:8px 14px 10px}
.bl{display:flex;justify-content:space-between;font-size:9px;margin-bottom:5px}
.bar-outer{height:6px;background:rgba(255,255,255,.07);border-radius:3px;position:relative;overflow:hidden}
.bar-fill-g{position:absolute;right:0;top:0;bottom:0;background:rgba(0,255,136,.3);border-radius:3px}
.bar-fill-r{position:absolute;left:0;top:0;bottom:0;background:rgba(255,51,85,.3);border-radius:3px}
.bar-cur{position:absolute;top:-2px;bottom:-2px;width:3px;border-radius:2px;transform:translateX(-50%)}
.bc{display:flex;justify-content:space-between;font-size:9px;color:var(--text2);margin-top:4px}
/* EMPTY */
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 20px;color:var(--text3);gap:10px}
.empty-icon{font-size:28px;opacity:.3}.empty-text{font-size:12px;letter-spacing:1px}
/* SIGNAL CARDS */
.sig-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.sig-card{background:var(--bg1);border:1px solid var(--border);border-radius:6px;padding:14px;position:relative;overflow:hidden;transition:border-color .2s}
.sig-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.sig-buy::before{background:var(--green)}.sig-sell::before{background:var(--red)}.sig-hold::before{background:var(--text3)}
.sig-card.sig-buy{border-color:rgba(0,255,136,.3)}
.sg-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.sg-coin{font-size:16px;font-weight:700}
.sg-badge{font-size:10px;font-weight:700;padding:4px 10px;border-radius:4px;letter-spacing:1px}
.b-buy{background:var(--green-dim);color:var(--green);border:1px solid rgba(0,255,136,.3)}
.b-sell{background:var(--red-dim);color:var(--red);border:1px solid rgba(255,51,85,.3)}
.b-hold{background:rgba(68,85,119,.2);color:var(--text2)}
.sg-price{font-size:22px;font-weight:700;margin:8px 0 4px}
.sg-score-row{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.sg-score-track{flex:1;height:6px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden}
.sg-score-fill{height:100%;border-radius:3px;transition:width .5s}
.sg-score-num{font-size:11px;color:var(--text2);min-width:36px;text-align:right}
.sg-details{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px}
.sg-detail{background:var(--bg2);border-radius:4px;padding:6px 8px}
.sg-dl{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}
.sg-dv{font-size:12px;font-weight:600;margin-top:2px}
.sg-inds{display:flex;flex-wrap:wrap;gap:4px}
.ind{font-size:9px;padding:2px 7px;border-radius:3px;letter-spacing:.5px}
.ind-ok{background:rgba(0,255,136,.1);color:var(--green)}
.ind-no{background:rgba(68,85,119,.15);color:var(--text3)}
/* SCANNER TABLE */
.scanner-wrap{margin-top:16px}
.scanner-title{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--text3);margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.scanner-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px}
.sc-card{background:var(--bg1);border:1px solid var(--border);border-radius:5px;padding:8px 10px;display:flex;justify-content:space-between;align-items:center}
.sc-name{font-size:12px;font-weight:600}
.sc-right{text-align:right}
.sc-score{font-size:14px;font-weight:700}
.sc-reason{font-size:9px;color:var(--text3);margin-top:2px}
/* HISTORY */
.hist-table{width:100%;border-collapse:collapse;font-size:11px}
.hist-table th{padding:8px 12px;text-align:left;font-size:9px;color:var(--text3);letter-spacing:1px;text-transform:uppercase;border-bottom:1px solid var(--border);font-weight:400}
.hist-table td{padding:9px 12px;border-bottom:1px solid rgba(26,37,64,.5)}
.hist-table tr:hover td{background:rgba(255,255,255,.02)}
/* LOGS */
.log-wrap{font-size:10px;line-height:1.8;padding:4px}
.log-line{padding:2px 8px;border-radius:3px}
.log-time{color:var(--text3);margin-right:8px}
.lg{color:var(--green)}.lr{color:var(--red)}.ly{color:var(--yellow)}.lc{color:var(--cyan)}.li{color:var(--text2)}
/* RIGHT */
#right{background:var(--bg1);border-left:1px solid var(--border);overflow-y:auto}
#right::-webkit-scrollbar{width:3px}
#right::-webkit-scrollbar-thumb{background:var(--border2)}
.rp-sec{border-bottom:1px solid var(--border)}
.rp-title{font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--text3);padding:10px 14px 8px;display:flex;justify-content:space-between;align-items:center}
.rp-badge{font-size:9px;padding:2px 6px;border-radius:3px;background:rgba(0,136,255,.1);color:var(--blue)}
.acc-grid{padding:10px 14px 12px;display:grid;grid-template-columns:1fr 1fr;gap:6px}
.acc-card{background:var(--bg2);border-radius:4px;padding:8px 10px}
.ac-label{font-size:9px;color:var(--text3);letter-spacing:.5px;text-transform:uppercase}
.ac-val{font-size:14px;font-weight:700;margin-top:3px}
.regime-card{padding:10px 14px 14px}
.regime-name{font-size:16px;font-weight:700;margin-bottom:8px}
.rn-up{color:var(--green)}.rn-down{color:var(--red)}.rn-range{color:var(--yellow)}.rn-nt{color:var(--purple)}
.rm-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.rm-item{background:var(--bg2);border-radius:4px;padding:7px 10px}
.rm-label{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}
.rm-val{font-size:12px;font-weight:600;margin-top:2px}
.regime-bar{height:3px;border-radius:2px;background:rgba(255,255,255,.06);overflow:hidden;margin-top:8px}
.regime-bar-fill{height:100%;border-radius:2px}
.fund-rows{padding:8px 14px}
.fund-row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(26,37,64,.4);font-size:11px}
.fund-row:last-child{border-bottom:none}
.fc{color:var(--text2)}
/* 24H STATS PANEL */
.stat24-wrap{padding:10px 14px 14px}
.stat24-pnl{
  display:flex;justify-content:space-between;align-items:center;
  padding:10px 14px;border-radius:6px;margin-bottom:10px;
  background:var(--bg2);border:1px solid var(--border2);
}
.stat24-pnl-label{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:var(--text3)}
.stat24-pnl-val{font-size:22px;font-weight:700}
.stat24-pnl-sub{font-size:10px;color:var(--text2);margin-top:2px}
.stat24-counts{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:10px}
.stat24-box{background:var(--bg2);border-radius:5px;padding:8px 10px;text-align:center}
.stat24-box-val{font-size:18px;font-weight:700}
.stat24-box-lbl{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-top:2px}
.stat24-bar-wrap{margin-top:4px}
.stat24-bar-row{display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:10px}
.stat24-bar-label{width:48px;color:var(--text3)}
.stat24-bar-track{flex:1;height:5px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden}
.stat24-bar-fill{height:100%;border-radius:3px;transition:width .4s}
.stat24-bar-num{width:28px;text-align:right;font-weight:600}
.stat24-trades{margin-top:10px}
.stat24-trade-row{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid rgba(26,37,64,.4);font-size:10px}
.stat24-trade-row:last-child{border-bottom:none}
.str-sym{font-weight:600;color:var(--text)}
.str-dir{font-size:9px;font-weight:700}
.str-pnl{font-weight:600}
.str-time{font-size:9px;color:var(--text3)}
/* SIGNAL BAR PANEL */
.sbar-row{display:flex;align-items:center;gap:8px;padding:7px 12px;background:var(--bg1);border:1px solid var(--border);border-radius:5px;cursor:pointer;transition:all .15s}
.sbar-row:hover{border-color:var(--border2);background:var(--bg2)}
.sbar-row.sbar-buy{border-color:rgba(0,255,136,.4);background:rgba(0,255,136,.04)}
.sbar-row.sbar-sel{border-color:var(--cyan);background:rgba(0,204,255,.05)}
.sbar-name{font-size:12px;font-weight:600;width:48px;flex-shrink:0;color:var(--text)}
.sbar-track{flex:1;height:8px;background:rgba(255,255,255,.06);border-radius:4px;overflow:hidden;position:relative}
.sbar-fill{height:100%;border-radius:4px;transition:width .6s cubic-bezier(.4,0,.2,1)}
.sbar-thresh{position:absolute;top:0;bottom:0;width:2px;background:rgba(0,255,136,.5);z-index:1}
.sbar-score{font-size:11px;font-weight:500;width:32px;text-align:right;flex-shrink:0}
.sbar-badge{font-size:9px;font-weight:700;padding:2px 7px;border-radius:3px;width:38px;text-align:center;flex-shrink:0}
.sb-buy{background:rgba(0,255,136,.12);color:var(--green)}
.sb-hold{background:rgba(68,85,119,.2);color:var(--text3)}
.sbar-rsi{font-size:10px;width:40px;flex-shrink:0;text-align:right;color:var(--text3)}
.sc-mini{background:var(--bg1);border:1px solid var(--border);border-radius:4px;padding:6px 8px;display:flex;justify-content:space-between;align-items:center}
.sc-mini-name{font-size:11px;font-weight:600;color:var(--text)}
.sc-mini-score{font-size:13px;font-weight:700}
.sc-mini-rsi{font-size:9px;color:var(--text3)}
/* TOAST */
#toasts{position:fixed;bottom:20px;right:20px;z-index:9000;display:flex;flex-direction:column;gap:8px;align-items:flex-end}
.toast{background:var(--bg2);border:1px solid var(--border2);border-radius:6px;padding:10px 14px;font-size:11px;min-width:220px;display:flex;align-items:center;gap:10px;animation:tin .3s ease}
.toast.t-buy{border-left:3px solid var(--green)}.toast.t-info{border-left:3px solid var(--blue)}
@keyframes tin{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:translateX(0)}}
.t-title{font-weight:600}.t-sub{color:var(--text2);font-size:10px;margin-top:2px}
@media(max-width:768px){
  #app{grid-template-columns:1fr}
  #sidebar,#right{display:none}
  #mobnav{display:flex;position:fixed;bottom:0;left:0;right:0;height:52px;background:var(--bg1);border-top:1px solid var(--border);z-index:200}
  .mob{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:9px;color:var(--text3);cursor:pointer;background:none;border:none}
  .mob.active{color:var(--cyan)}
}
@media(min-width:769px){#mobnav{display:none}}
</style>
</head>
<body>
<div id="topbar">
  <div style="display:flex;align-items:center;gap:14px">
    <div class="logo">Crypto<span>Bot</span></div>
    <div class="live-badge"><div class="live-dot"></div><span id="live-txt">CANLI</span></div>
  </div>
  <div class="top-metrics">
    <div class="tm"><div class="tm-label">Bakiye</div><div class="tm-val neu" id="t-bal">--</div></div>
    <div class="tm"><div class="tm-label">Float PnL</div><div class="tm-val neu" id="t-pnl">--</div></div>
    <div class="tm"><div class="tm-label">Pozisyon</div><div class="tm-val neu" id="t-pos">0</div></div>
    <div class="tm"><div class="tm-label">Rejim</div><div class="tm-val neu" id="t-reg" style="font-size:11px">--</div></div>
  </div>
  <div id="clock">--:--:--</div>
</div>

<div id="app">
  <div id="sidebar">
    <div class="s-lbl">NAVİGASYON</div>
    <button class="nav-btn active" id="nb-positions" onclick="goPage('positions')">◈ &nbsp;Pozisyonlar</button>
    <button class="nav-btn" id="nb-signals" onclick="goPage('signals')">⟡ &nbsp;Sinyaller</button>
    <button class="nav-btn" id="nb-history" onclick="goPage('history')">◷ &nbsp;Geçmiş</button>
    <button class="nav-btn" id="nb-logs" onclick="goPage('logs')">≡ &nbsp;Loglar</button>
    <div class="s-lbl" style="margin-top:auto">PİYASA</div>
    <div class="coin-strip" id="coin-strip"></div>
  </div>

  <div id="main">
    <div class="tabs">
      <button class="tab active" id="tab-positions" onclick="goPage('positions')">Pozisyonlar</button>
      <button class="tab" id="tab-signals" onclick="goPage('signals')">Sinyaller</button>
      <button class="tab" id="tab-history" onclick="goPage('history')">Geçmiş</button>
      <button class="tab" id="tab-logs" onclick="goPage('logs')">Loglar</button>
    </div>
    <div class="page active" id="page-positions">
      <div class="pos-grid" id="pos-grid">
        <div class="empty"><div class="empty-icon">◈</div><div class="empty-text">Yükleniyor...</div></div>
      </div>
    </div>
    <div class="page" id="page-signals">
      <!-- Üst özet kartlar -->
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px">
        <div class="acc-card"><div class="ac-label">Rejim</div><div class="ac-val" id="sig-regime" style="font-size:12px;color:var(--text)">--</div></div>
        <div class="acc-card"><div class="ac-label">BUY Sinyal</div><div class="ac-val" id="sig-buy-cnt" style="color:var(--green)">0</div></div>
        <div class="acc-card"><div class="ac-label">Tarama</div><div class="ac-val" id="sig-scan-cnt" style="font-size:12px;color:var(--text2)">-- coin</div></div>
        <div class="acc-card"><div class="ac-label">Sonraki</div><div class="ac-val" id="sig-countdown" style="font-size:12px;color:var(--text2)">~60s</div></div>
      </div>
      <!-- Bar listesi -->
      <div style="font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--text3);margin-bottom:8px;display:flex;justify-content:space-between">
        <span>SİNYAL SKORU — EŞİK: 6/11</span>
        <span id="sig-updated" style="color:var(--text3)">güncelleniyor...</span>
      </div>
      <div id="sig-bar-list" style="display:flex;flex-direction:column;gap:5px"></div>
      <!-- Detay paneli -->
      <div id="sig-detail" style="display:none;margin-top:14px;background:var(--bg1);border:1px solid var(--border2);border-radius:6px;padding:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <div id="sig-det-coin" style="font-size:16px;font-weight:700;color:var(--text)">--</div>
          <span id="sig-det-badge" style="font-size:10px;padding:3px 10px;border-radius:3px;font-weight:700">--</span>
        </div>
        <div id="sig-det-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:12px"></div>
        <div style="font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:var(--text3);margin-bottom:6px">Göstergeler</div>
        <div id="sig-det-inds" style="display:flex;flex-wrap:wrap;gap:4px"></div>
      </div>
      <!-- Scanner puanları -->
      <div style="margin-top:16px">
        <div style="font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--text3);margin-bottom:8px">SCANNER — TÜM COINLER</div>
        <div id="sig-scanner-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:5px"></div>
      </div>
    </div>
    <div class="page" id="page-history">
      <table class="hist-table">
        <thead><tr><th>Sembol</th><th>Yön</th><th>Giriş</th><th>Çıkış</th><th>PnL</th><th>Zaman</th></tr></thead>
        <tbody id="hist-body"><tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text3)">Yükleniyor...</td></tr></tbody>
      </table>
    </div>
    <div class="page" id="page-logs">
      <div class="log-wrap" id="log-wrap"></div>
    </div>
  </div>

  <div id="right">
    <div class="rp-sec">
      <div class="rp-title">HESAP</div>
      <div class="acc-grid">
        <div class="acc-card"><div class="ac-label">Equity</div><div class="ac-val" style="color:var(--green)" id="r-equity">--</div></div>
        <div class="acc-card"><div class="ac-label">Kullanılan</div><div class="ac-val neu" id="r-used">--</div></div>
        <div class="acc-card"><div class="ac-label">Float PnL</div><div class="ac-val neu" id="r-fpnl">--</div></div>
        <div class="acc-card"><div class="ac-label">Açık Pos.</div><div class="ac-val" style="color:var(--cyan)" id="r-openpos">0</div></div>
      </div>
    </div>
    <div class="rp-sec">
      <div class="rp-title">PİYASA REJİMİ <span class="rp-badge" id="r-conf">--</span></div>
      <div class="regime-card">
        <div class="regime-name neu" id="r-regime">--</div>
        <div class="rm-grid">
          <div class="rm-item"><div class="rm-label">ADX (1H)</div><div class="rm-val neu" id="r-adx">--</div></div>
          <div class="rm-item"><div class="rm-label">Pos. Çarpanı</div><div class="rm-val neu" id="r-mult">--</div></div>
        </div>
        <div class="regime-bar"><div class="regime-bar-fill" id="r-bar" style="width:0%;background:var(--cyan)"></div></div>
      </div>
    </div>
    <div class="rp-sec">
      <div class="rp-title">FUNDING RATES</div>
      <div class="fund-rows">
        <div class="fund-row"><span class="fc">BTC</span><span id="fr-btc" style="color:var(--text2)">--</span></div>
        <div class="fund-row"><span class="fc">BNB</span><span id="fr-bnb" style="color:var(--text2)">--</span></div>
        <div class="fund-row"><span class="fc">SOL</span><span id="fr-sol" style="color:var(--text2)">--</span></div>
        <div class="fund-row"><span class="fc">ONDO</span><span id="fr-ondo" style="color:var(--text2)">--</span></div>
        <div class="fund-row"><span class="fc">HYPE</span><span id="fr-hype" style="color:var(--text2)">--</span></div>
      </div>
    </div>
    <div class="rp-sec">
      <div class="rp-title">DÖNGÜ</div>
      <div style="padding:8px 14px;font-size:11px;color:var(--text2)">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="color:var(--text3)">Döngü #</span><span id="r-loop">0</span></div>
        <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">Son Tarama</span><span id="r-scan" style="font-size:10px">--</span></div>
      </div>
    </div>
    <div class="rp-sec">
      <div class="rp-title">SON 24 SAAT <span class="rp-badge" id="s24-updated">--</span></div>
      <div class="stat24-wrap">
        <!-- PnL büyük gösterim -->
        <div class="stat24-pnl">
          <div>
            <div class="stat24-pnl-label">24s Net PnL</div>
            <div class="stat24-pnl-val" id="s24-pnl">$0.00</div>
            <div class="stat24-pnl-sub" id="s24-avg">Ort: $0.00 / işlem</div>
          </div>
          <div style="text-align:right">
            <div class="stat24-pnl-label">Win Rate</div>
            <div style="font-size:20px;font-weight:700;margin-top:4px" id="s24-wr">--%</div>
          </div>
        </div>
        <!-- İşlem sayıları -->
        <div class="stat24-counts">
          <div class="stat24-box">
            <div class="stat24-box-val neu" id="s24-total">0</div>
            <div class="stat24-box-lbl">Toplam</div>
          </div>
          <div class="stat24-box">
            <div class="stat24-box-val pos" id="s24-wins">0</div>
            <div class="stat24-box-lbl">Kazanan</div>
          </div>
          <div class="stat24-box">
            <div class="stat24-box-val neg" id="s24-losses">0</div>
            <div class="stat24-box-lbl">Kaybeden</div>
          </div>
        </div>
        <!-- Oransal bar -->
        <div class="stat24-bar-wrap">
          <div class="stat24-bar-row">
            <span class="stat24-bar-label" style="color:var(--green)">Kazanan</span>
            <div class="stat24-bar-track"><div class="stat24-bar-fill" id="s24-wbar" style="width:0%;background:var(--green)"></div></div>
            <span class="stat24-bar-num pos" id="s24-wpct">0%</span>
          </div>
          <div class="stat24-bar-row">
            <span class="stat24-bar-label" style="color:var(--red)">Kaybeden</span>
            <div class="stat24-bar-track"><div class="stat24-bar-fill" id="s24-lbar" style="width:0%;background:var(--red)"></div></div>
            <span class="stat24-bar-num neg" id="s24-lpct">0%</span>
          </div>
        </div>
        <!-- Son 5 işlem -->
        <div class="stat24-trades" id="s24-trades"></div>
      </div>
    </div>
    <div>
      <div class="rp-title">GRID</div>
      <div style="padding:10px 14px" id="r-grid"><div style="color:var(--text3);font-size:10px">--</div></div>
    </div>
  </div>
</div>

<div id="mobnav">
  <button class="mob active" onclick="goPage('positions')"><div>◈</div>Pozisyon</button>
  <button class="mob" onclick="goPage('signals')"><div>⟡</div>Sinyal</button>
  <button class="mob" onclick="goPage('history')"><div>◷</div>Geçmiş</button>
  <button class="mob" onclick="goPage('logs')"><div>≡</div>Log</button>
</div>
<div id="toasts"></div>

<script>
/* ── STATE ── */
const S = { positions:[], prices:{}, signals:{}, regime:{}, logs:[], balance:0, scannerScores:{} };
let curPage = 'positions';
const API = window.location.origin;

/* ── CLOCK ── */
setInterval(()=>{
  const n=new Date();
  document.getElementById('clock').textContent=
    [n.getHours(),n.getMinutes(),n.getSeconds()].map(x=>String(x).padStart(2,'0')).join(':');
},1000);

/* ── PAGE ── */
function goPage(p){
  curPage=p;
  ['positions','signals','history','logs'].forEach(pg=>{
    document.getElementById('page-'+pg).classList[pg===p?'add':'remove']('active');
    const t=document.getElementById('tab-'+pg); if(t) t.classList[pg===p?'add':'remove']('active');
    const n=document.getElementById('nb-'+pg);  if(n) n.classList[pg===p?'add':'remove']('active');
  });
  document.querySelectorAll('.mob').forEach(b=>b.classList.remove('active'));
  if(p==='history') loadHistory();
}

/* ── COIN STRIP ── */
const COINS=['BTCUSDT','BNBUSDT','SOLUSDT','ONDOUSDT','HYPEUSDT'];
const LBL={BTCUSDT:'BTC',BNBUSDT:'BNB',SOLUSDT:'SOL',ONDOUSDT:'ONDO',HYPEUSDT:'HYPE'};
document.getElementById('coin-strip').innerHTML=COINS.map(s=>
  `<div class="coin-row" id="cr-${s}">
    <div><div class="cn">${LBL[s]}</div><div class="cs">USDT PERP</div></div>
    <div><div class="cp neu" id="cp-${s}" data-v="0">--</div><div class="cpct pos" id="cc-${s}">+0.00%</div></div>
  </div>`).join('');

function updateStrip(sym,price,pct){
  const pEl=document.getElementById('cp-'+sym);
  const cEl=document.getElementById('cc-'+sym);
  const row=document.getElementById('cr-'+sym);
  if(!pEl) return;
  const prev=parseFloat(pEl.dataset.v||0);
  pEl.dataset.v=price; pEl.textContent=fmtP(price,sym);
  if(cEl&&pct!=null){cEl.textContent=(pct>=0?'+':'')+pct.toFixed(2)+'%'; cEl.className='cpct '+(pct>=0?'pos':'neg');}
  if(row&&prev>0){row.classList.remove('flash-g','flash-r');void row.offsetWidth;row.classList.add(price>=prev?'flash-g':'flash-r');}
}

/* ── OKX WS ── */
function connectWS(){
  try{
    const ws=new WebSocket('wss://ws.okx.com:8443/ws/v5/public');
    ws.onopen=()=>{
      ws.send(JSON.stringify({op:'subscribe',args:COINS.map(s=>({channel:'tickers',instId:s.replace('USDT','-USDT-SWAP')}))}));
      ws.send(JSON.stringify({op:'subscribe',args:['BTC','BNB','SOL','ONDO','HYPE'].map(s=>({channel:'funding-rate',instId:s+'-USDT-SWAP'}))}));
    };
    ws.onmessage=e=>{
      try{
        const m=JSON.parse(e.data); if(!m.data) return;
        if(m.arg?.channel==='tickers'){
          m.data.forEach(d=>{
            const sym=d.instId.replace('-USDT-SWAP','USDT');
            const p=parseFloat(d.last)||0; const pct=parseFloat(d.sodUtc8)||0;
            S.prices[sym]=p; updateStrip(sym,p,pct); liveCards(sym,p);
          });
        }
        if(m.arg?.channel==='funding-rate'){
          m.data.forEach(d=>{
            const sym=d.instId.replace('-USDT-SWAP','').toUpperCase();
            const r=parseFloat(d.fundingRate)*100;
            const el=document.getElementById('fr-'+sym.toLowerCase());
            if(el){el.textContent=(r>=0?'+':'')+r.toFixed(4)+'%'; el.style.color=r>0.01?'var(--green)':r<-0.01?'var(--red)':'var(--text2)';}
          });
        }
      }catch(_){}
    };
    ws.onclose=()=>setTimeout(connectWS,3000);
    ws.onerror=()=>{};
  }catch(_){setTimeout(connectWS,5000);}
}

/* ── SSE ── */
function connectSSE(){
  const es=new EventSource(API+'/api/stream');
  es.onmessage=e=>{
    try{
      const d=JSON.parse(e.data);
      const sigs=d.signals||d.botStatus?.signals||{};
      if(Object.keys(sigs).length){S.signals=sigs; if(curPage==='signals')renderSignals();}
      // Scanner scores
      const sc=d.scanner_scores||d.botStatus?.scanner_scores;
      if(sc&&Object.keys(sc).length){ S.scannerScores=sc; if(curPage==='signals')renderScannerScores(); }
      const reg=d.regime||d.botStatus?.regime||{};
      if(Object.keys(reg).length){S.regime=reg; renderRegime();}
      const logs=d.botStatus?.logs||[];
      if(logs.length){appendLogs(logs.filter(l=>!S.logs.includes(l))); S.logs=logs;}
      if(d.stats?.totalBalance){
        const b=d.stats.totalBalance; S.balance=b;
        document.getElementById('t-bal').textContent='$'+b.toFixed(2);
        document.getElementById('r-equity').textContent='$'+b.toFixed(2);
      }
      if(d.botStatus?.loop_count!=null) document.getElementById('r-loop').textContent='#'+d.botStatus.loop_count;
      if(d.botStatus?.last_scan){const t=new Date(d.botStatus.last_scan);if(!isNaN(t))document.getElementById('r-scan').textContent=[t.getHours(),t.getMinutes(),t.getSeconds()].map(x=>String(x).padStart(2,'0')).join(':');}
      if(d.gridState&&Object.keys(d.gridState).length) renderGrid(d.gridState);
    }catch(_){}
  };
  es.onerror=()=>{document.getElementById('live-txt').textContent='BAĞLANIYOR';es.close();setTimeout(connectSSE,4000);};
  es.onopen=()=>document.getElementById('live-txt').textContent='CANLI';
}

/* ── POLL POSITIONS ── */
function poll(){
  fetch(API+'/api/positions')
    .then(r=>{
      const ct=r.headers.get('content-type')||'';
      if(!ct.includes('json'))throw new Error('Not JSON');
      return r.json();
    })
    .then(data=>{
      /* mock_api.py returns plain JSON array */
      const pos=Array.isArray(data)?data:(Array.isArray(data.positions)?data.positions:[]);
      S.positions=pos;
      renderPositions();
    })
    .catch(e=>console.warn('[CB] poll:',e.message));
}

/* ── RENDER POSITIONS ── */
function icn(sym){
  const s=sym.toUpperCase();
  if(s.includes('BTC'))return 'ic-btc';
  if(s.includes('BNB'))return 'ic-bnb';
  if(s.includes('SOL'))return 'ic-sol';
  if(s.includes('ONDO'))return 'ic-ondo';
  if(s.includes('HYPE'))return 'ic-hype';
  return 'ic-def';
}

function renderPositions(){
  const grid=document.getElementById('pos-grid');
  const cnt=S.positions.length;
  document.getElementById('t-pos').textContent=cnt;
  document.getElementById('r-openpos').textContent=cnt;
  if(!cnt){
    grid.innerHTML='<div class="empty"><div class="empty-icon">◈</div><div class="empty-text">Açık pozisyon yok</div></div>';
    setTopPnL(0); return;
  }
  grid.innerHTML=S.positions.map(buildCard).join('');
  refreshTotalPnL();
  const used=S.positions.reduce((a,p)=>(+p.notional||0)/(+p.leverage||10)+a,0);
  document.getElementById('r-used').textContent='$'+used.toFixed(0);
}

function buildCard(p){
  const sym  = String(p.symbol||'');
  const side = String(p.side||'long');
  const entry= +p.entry_price||0;
  const cur  = S.prices[sym]||+p.current_price||entry;
  const sl   = +p.stop_loss||0;
  const tp   = +p.take_profit||0;
  const not  = +p.notional||0;
  const lev  = +p.leverage||10;
  const mgn  = not>0?not/lev:0;
  const qty  = entry>0&&not>0?not/entry:0;
  let pnl,pct;
  if(qty>0&&cur>0){pnl=side==='long'?(cur-entry)*qty:(entry-cur)*qty; pct=mgn>0?pnl/mgn*100:0;}
  else{pnl=+p.pnl||0; pct=+p.pnl_percent||0;}
  const pp=pnl>=0;
  let bar=50;
  if(sl>0&&tp>0&&cur>0){const rng=Math.abs(tp-sl);if(rng>0)bar=side==='long'?Math.max(0,Math.min(100,(cur-sl)/rng*100)):Math.max(0,Math.min(100,(sl-cur)/rng*100));}
  const bc=bar<30?'var(--red)':bar>70?'var(--green)':'var(--yellow)';
  const disp=sym.replace('USDT','').replace('-USDT-SWAP','');
  const strat=p.strategy_name||'Pullback'; const isMan=!!p.is_adopted;
  return `<div class="pos-card ${side}-card">
  <div class="pc-head">
    <div class="pc-left">
      <div class="pc-icon ${icn(sym)}">${disp.substring(0,4)}</div>
      <div>
        <div class="pc-sym">${disp}<span style="font-size:10px;color:var(--text3);font-weight:400">/USDT</span></div>
        <div class="pc-meta">${isMan?'👤 Manuel':strat} · ${lev}x${p.score?' · Skor:'+p.score:''}</div>
      </div>
      <span class="pc-dir dir-${side}">${side==='long'?'LONG':'SHORT'}</span>
    </div>
    <div class="pc-pnl">
      <div class="pc-pnl-val ${pp?'pos':'neg'}" id="pnl-${sym}">${pp?'+':'-'}$${Math.abs(pnl).toFixed(2)}</div>
      <div class="pc-pnl-pct ${pp?'pos':'neg'}" id="pp-${sym}">${pp?'+':''}${pct.toFixed(2)}%</div>
    </div>
  </div>
  <div class="pc-stats">
    <div class="pc-stat"><div class="psl">Giriş</div><div class="psv">${fmtP(entry,sym)}</div></div>
    <div class="pc-stat"><div class="psl">Güncel</div><div class="psv" id="cp2-${sym}">${fmtP(cur,sym)}</div></div>
    <div class="pc-stat"><div class="psl">SL</div><div class="psv" style="color:var(--red)">${sl?fmtP(sl,sym):'--'}</div></div>
    <div class="pc-stat"><div class="psl">TP</div><div class="psv" style="color:var(--green)">${tp?fmtP(tp,sym):'--'}</div></div>
  </div>
  <div class="pc-bar">
    <div class="bl">
      <span style="color:var(--red)">SL ${sl?fmtP(sl,sym):'--'}</span>
      <span style="color:var(--text2)">${fmtP(cur,sym)}</span>
      <span style="color:var(--green)">TP ${tp?fmtP(tp,sym):'--'}</span>
    </div>
    <div class="bar-outer">
      <div class="bar-fill-r" style="width:${Math.max(0,50-bar)*2}%"></div>
      <div class="bar-fill-g" style="width:${Math.max(0,bar-50)*2}%"></div>
      <div class="bar-cur" style="left:${bar}%;background:${bc};box-shadow:0 0 6px ${bc}"></div>
    </div>
    <div class="bc">
      <span>Marjin: $${mgn.toFixed(0)}</span>
      <span style="color:${bc}">${bar.toFixed(0)}% TP yönünde</span>
      <span>$${not.toFixed(0)}</span>
    </div>
  </div>
</div>`;
}

function liveCards(sym,price){
  S.positions.forEach(p=>{
    if(p.symbol!==sym) return;
    const entry=+p.entry_price||0; const not=+p.notional||0; const lev=+p.leverage||10;
    const mgn=not>0?not/lev:0; const side=p.side||'long';
    const qty=entry>0&&not>0?not/entry:0;
    const pnl=qty>0?(side==='long'?(price-entry)*qty:(entry-price)*qty):+p.pnl||0;
    const pct=mgn>0?pnl/mgn*100:0; const pp=pnl>=0;
    const pEl=document.getElementById('pnl-'+sym);
    const ppEl=document.getElementById('pp-'+sym);
    const cpEl=document.getElementById('cp2-'+sym);
    if(pEl){pEl.textContent=(pp?'+':'-')+'$'+Math.abs(pnl).toFixed(2); pEl.className='pc-pnl-val '+(pp?'pos':'neg');}
    if(ppEl){ppEl.textContent=(pp?'+':'')+pct.toFixed(2)+'%'; ppEl.className='pc-pnl-pct '+(pp?'pos':'neg');}
    if(cpEl) cpEl.textContent=fmtP(price,sym);
  });
  refreshTotalPnL();
}

function refreshTotalPnL(){
  let total=0;
  S.positions.forEach(p=>{
    const sym=p.symbol||''; const entry=+p.entry_price||0;
    const wsP=S.prices[sym]||0; const not=+p.notional||0; const side=p.side||'long';
    if(entry>0&&not>0&&wsP>0){const q=not/entry; total+=side==='long'?(wsP-entry)*q:(entry-wsP)*q;}
    else total+=+p.pnl||0;
  });
  setTopPnL(total);
}

function setTopPnL(total){
  const pp=total>=0; const str=(pp?'+':'')+`$${total.toFixed(2)}`;
  const tEl=document.getElementById('t-pnl'); const rEl=document.getElementById('r-fpnl');
  if(tEl){tEl.textContent=str; tEl.className='tm-val '+(pp?'pos':'neg');}
  if(rEl){rEl.textContent=str; rEl.style.color=pp?'var(--green)':'var(--red)';}
}

/* ── SİNYAL BAR PANELİ ── */
const MIN_SC = 6; const MAX_SC = 11; const THRESH_PCT = (MIN_SC/MAX_SC*100).toFixed(1);
let _selCoin = null;
let _sigCountdown = 60;

function renderSignals(){
  const sigs = S.signals;
  const scanner = S.scannerScores || {};
  const allEntries = {};

  // Merge signals + scanner
  Object.entries(sigs).forEach(([sym, sig]) => {
    const inst = sym.replace('USDT','-USDT-SWAP');
    allEntries[inst] = allEntries[inst] || {};
    allEntries[inst].sig = sig;
    allEntries[inst].name = sym.replace('USDT','');
  });
  Object.entries(scanner).forEach(([inst, sc]) => {
    allEntries[inst] = allEntries[inst] || {};
    allEntries[inst].sc = sc;
    allEntries[inst].name = inst.replace('-USDT-SWAP','');
  });

  const entries = Object.entries(allEntries);
  if(!entries.length){
    document.getElementById('sig-bar-list').innerHTML =
      '<div class="empty"><div class="empty-icon">⟡</div><div class="empty-text">Sinyal bekleniyor...</div></div>';
    return;
  }

  // Sort by signal score desc, then scanner score
  entries.sort((a,b)=>{
    const aS = a[1].sig?.long?.score||0; const bS = b[1].sig?.long?.score||0;
    if(bS!==aS) return bS-aS;
    return (b[1].sc?.score||0)-(a[1].sc?.score||0);
  });

  let buyCount = 0;
  const html = entries.map(([inst, data]) => {
    const name  = data.name || inst.replace('-USDT-SWAP','');
    const sig   = data.sig || {};
    const sc    = data.sc  || {};
    const ls    = sig.long || {};
    const sigSc = ls.score || 0;
    const scSc  = sc.score || 0;
    const isBuy = ls.enter && sigSc >= MIN_SC;
    if(isBuy) buyCount++;

    const dispSc  = sigSc || scSc;
    const dispMax = sigSc ? MAX_SC : 10;
    const pct     = Math.min(100, Math.round(dispSc/dispMax*100));
    const thresh  = sigSc ? THRESH_PCT : (4/10*100).toFixed(1);

    const barColor = isBuy ? 'var(--green)' : pct>=60 ? 'var(--yellow)' : 'var(--text3)';
    const rsiVal   = sc.rsi || ls.rsi || 0;
    const rsiColor = rsiVal>70 ? 'var(--red)' : rsiVal<30 ? 'var(--yellow)' : 'var(--text3)';
    const rowCls   = isBuy ? 'sbar-row sbar-buy' : (_selCoin===inst ? 'sbar-row sbar-sel' : 'sbar-row');

    return `<div class="${rowCls}" id="sbar-${inst}" onclick="selectSig('${inst}')">
      <div class="sbar-name">${name}</div>
      <div class="sbar-track">
        <div class="sbar-thresh" style="left:${thresh}%"></div>
        <div class="sbar-fill" id="sbf-${inst}" style="width:0%;background:${barColor}"></div>
      </div>
      <div class="sbar-score" style="color:${barColor}">${dispSc}/${dispMax}</div>
      <span class="sbar-badge ${isBuy?'sb-buy':'sb-hold'}">${isBuy?'BUY':'HOLD'}</span>
      <div class="sbar-rsi" style="color:${rsiColor}">${rsiVal?'RSI '+rsiVal.toFixed(0):''}</div>
    </div>`;
  }).join('');

  document.getElementById('sig-bar-list').innerHTML = html;
  document.getElementById('sig-buy-cnt').textContent = buyCount;
  document.getElementById('sig-scan-cnt').textContent = entries.length+' coin';

  // Animate bars
  requestAnimationFrame(()=>{
    entries.forEach(([inst, data])=>{
      const ls = data.sig?.long||{};
      const sc = data.sc||{};
      const dispSc  = ls.score||sc.score||0;
      const dispMax = ls.score ? MAX_SC : 10;
      const pct = Math.min(100, Math.round(dispSc/dispMax*100));
      const el = document.getElementById('sbf-'+inst);
      if(el) setTimeout(()=>{ el.style.width=pct+'%'; }, 60);
    });
  });

  // Timestamp
  const n=new Date();
  document.getElementById('sig-updated').textContent =
    [n.getHours(),n.getMinutes(),n.getSeconds()].map(x=>String(x).padStart(2,'0')).join(':')+' güncellendi';

  // Re-render scanner mini cards
  renderScannerScores();
}

function selectSig(inst){
  _selCoin = inst;
  document.querySelectorAll('.sbar-row').forEach(r=>{
    r.classList.remove('sbar-sel');
    if(r.id==='sbar-'+inst && !r.classList.contains('sbar-buy')) r.classList.add('sbar-sel');
  });

  const sc   = (S.scannerScores||{})[inst]||{};
  const name = inst.replace('-USDT-SWAP','');
  const sym  = name+'USDT';
  const sig  = S.signals[sym]||{};
  const ls   = sig.long||{};

  const det = document.getElementById('sig-detail');
  det.style.display = 'block';
  document.getElementById('sig-det-coin').textContent = name+'/USDT';

  const badge = document.getElementById('sig-det-badge');
  if(ls.enter){ badge.textContent='🟢 BUY'; badge.style.cssText='font-size:10px;padding:3px 10px;border-radius:3px;font-weight:700;background:rgba(0,255,136,.12);color:var(--green)'; }
  else { badge.textContent='⏸ HOLD'; badge.style.cssText='font-size:10px;padding:3px 10px;border-radius:3px;font-weight:700;background:rgba(68,85,119,.2);color:var(--text3)'; }

  const grid = document.getElementById('sig-det-grid');
  const items = [
    {l:'Sinyal Skoru', v:ls.score?(ls.score+'/'+MAX_SC):'--', c:ls.score>=MIN_SC?'var(--green)':'var(--text)'},
    {l:'Scanner Skoru', v:(sc.score||0)+'/10', c:(sc.score||0)>=7?'var(--green)':'var(--text)'},
    {l:'RSI', v:sc.rsi?sc.rsi.toFixed(1):'--', c:sc.rsi>70?'var(--red)':sc.rsi<30?'var(--yellow)':'var(--text)'},
    {l:'Giriş', v:ls.entry?fmtP(ls.entry,sym):'--', c:'var(--text)'},
    {l:'Stop Loss', v:ls.sl?fmtP(ls.sl,sym):'--', c:'var(--red)'},
    {l:'Take Profit', v:ls.tp?fmtP(ls.tp,sym):'--', c:'var(--green)'},
  ];
  grid.innerHTML = items.map(({l,v,c})=>`
    <div style="background:var(--bg2);border-radius:4px;padding:7px 10px">
      <div style="font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px">${l}</div>
      <div style="font-size:13px;font-weight:600;margin-top:3px;color:${c}">${v}</div>
    </div>`).join('');

  const reason = ls.reason||sc.reason||'';
  const inds = [];
  [['ST↑(+2)','ST↑',true],['ST↓','ST↓',false],
   ['EMA↑↑(+2)','EMA↑↑',true],['EMA↑(+1)','EMA↑',true],['EMA↓','EMA↓',false],
   ['MACD↑(+2)','MACD↑',true],['MACD+(+1)','MACD+',true],['MACD↓','MACD↓',false],
   ['P>EMA21(+1)','P>EMA21',true],['VWAP(+1)','VWAP',true],['VOL↑','VOL↑',true],
  ].forEach(([pat,lbl,ok])=>{
    if(reason.includes(pat)) inds.push({l:lbl,ok});
  });
  document.getElementById('sig-det-inds').innerHTML = inds.map(i=>
    `<span style="font-size:9px;padding:2px 7px;border-radius:3px;background:${i.ok?'rgba(0,255,136,.1)':'rgba(68,85,119,.2)'};color:${i.ok?'var(--green)':'var(--text3)'}">${i.l}</span>`
  ).join('');
}

function renderScannerScores(){
  const el = document.getElementById('sig-scanner-grid');
  if(!el||!S.scannerScores) return;
  const sorted = Object.entries(S.scannerScores).sort((a,b)=>(b[1].score||0)-(a[1].score||0));
  if(!sorted.length) return;
  el.innerHTML = sorted.map(([inst,sc])=>{
    const name = inst.replace('-USDT-SWAP','');
    const score = sc.score||0;
    const color = score>=7?'var(--green)':score>=5?'var(--yellow)':'var(--text3)';
    return `<div class="sc-mini" onclick="selectSig('${inst}')">
      <div><div class="sc-mini-name">${name}</div><div class="sc-mini-rsi">${sc.rsi?'RSI '+sc.rsi.toFixed(0):''}</div></div>
      <div class="sc-mini-score" style="color:${color}">${score}/10</div>
    </div>`;
  }).join('');
}
/* ── REGIME ── */
function renderRegime(){
  const r=S.regime; if(!r||!r.name) return;
  const name=r.name;
  const icons={TREND_UP:'↑ YUKARI',TREND_DOWN:'↓ AŞAĞI',RANGE:'↔ YATAY',HIGH_VOL:'⚡ YÜK.VOL',NO_TRADE:'✕ DUR'};
  const label=icons[name]||name;
  const cls=name.includes('UP')?'rn-up':name.includes('DOWN')?'rn-down':name.includes('RANGE')?'rn-range':'rn-nt';
  const bColor=name.includes('UP')?'var(--green)':name.includes('DOWN')?'var(--red)':'var(--yellow)';
  const conf=Math.round((r.confidence||0)*100);
  document.getElementById('r-regime').innerHTML=`<span class="${cls}">${label}</span>`;
  document.getElementById('t-reg').textContent=label;
  // Sinyal sayfası rejim kutusu
  const sigReg=document.getElementById('sig-regime');
  if(sigReg){ sigReg.textContent=label; sigReg.style.color=name.includes('UP')?'var(--green)':name.includes('DOWN')?'var(--red)':'var(--yellow)'; }
  document.getElementById('r-conf').textContent=conf+'% güven';
  document.getElementById('r-adx').textContent=r.adx_1h!=null?(+r.adx_1h).toFixed(1):'--';
  document.getElementById('r-mult').textContent='×'+(r.pos_mult||1);
  const bar=document.getElementById('r-bar');
  if(bar){bar.style.width=conf+'%'; bar.style.background=bColor;}
}

/* ── GRID ── */
function renderGrid(grid){
  const el=document.getElementById('r-grid'); if(!el) return;
  if(!grid||!Object.keys(grid).length){el.innerHTML='<div style="color:var(--text3);font-size:10px">--</div>';return;}
  el.innerHTML=Object.entries(grid).map(([k,g])=>
    `<div style="margin-bottom:8px">
      <div style="font-size:11px;font-weight:600;margin-bottom:3px">${k}</div>
      <div style="font-size:10px;color:var(--text2)">Alış:${g.buy_orders} Satış:${g.sell_orders}
        <span style="color:${g.total_pnl>=0?'var(--green)':'var(--red)'};margin-left:8px">PnL:${g.total_pnl>=0?'+':''}$${(g.total_pnl||0).toFixed(4)}</span>
      </div>
    </div>`
  ).join('');
}

/* ── 24H STATS ── */
function load24h(){
  fetch(API+'/api/trades')
    .then(r=>r.json())
    .then(data=>{
      const all=Array.isArray(data)?data:(data.trades||[]);
      const now=Date.now();
      const since=now-24*60*60*1000;
      // Filter last 24h closed trades
      const trades=all.filter(t=>{
        const ts=t.closed_at||t.opened_at||t.time||'';
        if(!ts) return false;
        const d=new Date(ts);
        return !isNaN(d)&&d.getTime()>=since&&(t.status==='closed'||t.pnl!==0);
      });
      const total=trades.length;
      const wins=trades.filter(t=>(+t.pnl||0)>0).length;
      const losses=total-wins;
      const netPnl=trades.reduce((a,t)=>a+(+t.pnl||0),0);
      const avgPnl=total>0?netPnl/total:0;
      const wr=total>0?Math.round(wins/total*100):0;
      const wpct=total>0?Math.round(wins/total*100):0;
      const lpct=100-wpct;
      const pp=netPnl>=0;

      // Update DOM
      const pEl=document.getElementById('s24-pnl');
      if(pEl){pEl.textContent=(pp?'+':'')+`$${Math.abs(netPnl).toFixed(2)}`;pEl.style.color=pp?'var(--green)':'var(--red)';}
      const avgEl=document.getElementById('s24-avg');
      if(avgEl) avgEl.textContent=`Ort: ${avgPnl>=0?'+':''}$${avgPnl.toFixed(2)} / işlem`;
      const wrEl=document.getElementById('s24-wr');
      if(wrEl){wrEl.textContent=wr+'%'; wrEl.style.color=wr>=50?'var(--green)':'var(--red)';}
      setText('s24-total',total);
      setText('s24-wins',wins);
      setText('s24-losses',losses);
      const wb=document.getElementById('s24-wbar'); if(wb) wb.style.width=wpct+'%';
      const lb=document.getElementById('s24-lbar'); if(lb) lb.style.width=lpct+'%';
      setText('s24-wpct',wpct+'%');
      setText('s24-lpct',lpct+'%');
      // Updated time
      const upEl=document.getElementById('s24-updated');
      if(upEl){const n=new Date();upEl.textContent=[n.getHours(),n.getMinutes()].map(x=>String(x).padStart(2,'0')).join(':')+'\'de güncellendi';}
      // Last 5 trades list
      const listEl=document.getElementById('s24-trades');
      if(listEl){
        const recent=trades.slice(0,5);
        if(!recent.length){listEl.innerHTML='<div style="color:var(--text3);font-size:10px;padding:4px 0">24s içinde işlem yok</div>';return;}
        listEl.innerHTML=recent.map(t=>{
          const pnl=+t.pnl||0; const pp2=pnl>=0;
          const sym=(t.symbol||'').replace('USDT','');
          const ts=fmtD(t.closed_at||t.opened_at||'');
          return `<div class="stat24-trade-row">
            <span class="str-sym">${sym}</span>
            <span class="str-dir" style="color:${t.side==='long'?'var(--green)':'var(--red)'}">${(t.side||'').toUpperCase()}</span>
            <span class="str-pnl" style="color:${pp2?'var(--green)':'var(--red)'}">${pp2?'+':''}$${Math.abs(pnl).toFixed(2)}</span>
            <span class="str-time">${ts}</span>
          </div>`;
        }).join('');
      }
    })
    .catch(()=>{});
}
function setText(id,val){const el=document.getElementById(id);if(el)el.textContent=val;}


function loadHistory(){
  fetch(API+'/api/trades').then(r=>r.json()).then(data=>{
    const trades=Array.isArray(data)?data:(data.trades||[]);
    const tbody=document.getElementById('hist-body');
    if(!trades.length){tbody.innerHTML='<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text3)">Geçmiş yok</td></tr>';return;}
    tbody.innerHTML=trades.slice(0,50).map(t=>{
      const pnl=+t.pnl||0; const pp=pnl>=0;
      return `<tr>
        <td style="font-weight:600">${t.symbol||'--'}</td>
        <td style="color:${t.side==='long'?'var(--green)':'var(--red)'};font-size:9px;font-weight:700">${(t.side||'').toUpperCase()}</td>
        <td style="color:var(--text2)">${fmtP(+t.entry_price||+t.entry||0,'')}</td>
        <td style="color:var(--text2)">${fmtP(+t.exit_price||+t.close_price||0,'')}</td>
        <td style="color:${pp?'var(--green)':'var(--red)'};font-weight:600">${pp?'+':''}$${Math.abs(pnl).toFixed(2)}</td>
        <td style="color:var(--text3);font-size:10px">${fmtD(t.opened_at||t.time||'')}</td>
      </tr>`;
    }).join('');
  }).catch(()=>{});
}

/* ── LOGS ── */
function appendLogs(lines){
  const wrap=document.getElementById('log-wrap'); if(!wrap) return;
  lines.forEach(line=>{
    const div=document.createElement('div'); div.className='log-line';
    const m=line.indexOf(']');
    const ts=m>0?line.substring(1,m):''; const msg=m>0?line.substring(m+1).trim():line;
    const cls=msg.includes('🟢')||msg.includes('✅')||msg.includes('💰')?'lg'
      :msg.includes('🔴')||msg.includes('❌')||msg.includes('⛔')?'lr'
      :msg.includes('⚠')||msg.includes('🔒')?'ly'
      :msg.includes('📊')||msg.includes('🔄')?'lc':'li';
    div.innerHTML=`<span class="log-time">${ts}</span><span class="${cls}">${msg}</span>`;
    wrap.appendChild(div);
    if(wrap.children.length>200) wrap.removeChild(wrap.firstChild);
  });
  wrap.scrollTop=wrap.scrollHeight;
}

/* ── HELPERS ── */
function fmtP(p,sym){
  if(!p||isNaN(p)) return '--';
  const s=(sym||'').toUpperCase(); const n=+p;
  if(s.includes('BTC'))  return '$'+n.toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1});
  if(s.includes('BNB')||s.includes('SOL')) return '$'+n.toFixed(2);
  if(s.includes('ONDO')) return '$'+n.toFixed(4);
  if(s.includes('HYPE')) return '$'+n.toFixed(3);
  if(n<0.001) return '$'+n.toFixed(8);
  if(n<1)     return '$'+n.toFixed(6);
  if(n<100)   return '$'+n.toFixed(4);
  return '$'+n.toFixed(2);
}
function fmtD(ts){
  if(!ts) return '--';
  const d=new Date(ts); if(isNaN(d)) return ts;
  return `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

/* ── INIT ── */
connectWS();
connectSSE();
poll();
load24h();
setInterval(poll, 15000);       // 15 saniyede bir (5'ten düşürüldü)
setInterval(load24h, 60000);    // 60 saniyede bir (30'dan düşürüldü)
setInterval(()=>{ if(curPage==='signals'){ renderSignals(); } }, 10000); // 10 saniye
setInterval(()=>{
  _sigCountdown--;
  if(_sigCountdown<=0) _sigCountdown=60;
  const el=document.getElementById('sig-countdown');
  if(el) el.textContent='~'+_sigCountdown+'s';
}, 1000);
</script>
</body>
</html>
