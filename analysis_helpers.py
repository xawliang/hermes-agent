"""
Hermes A股分析辅助函数
本地技术指标计算 (pandas+numpy, 无需额外包)
数据源：新浪API (日K线) + 问小达MCP (行情/资金/板块)
"""

import json
import urllib.request
import pandas as pd
import numpy as np
from datetime import datetime

# ========== 指标计算（本地，0额外依赖） ==========

def calc_ma(df, periods=(5, 10, 20, 30, 60)):
    for p in periods:
        df[f'MA{p}'] = df['close'].rolling(p).mean()
    return df

def calc_macd(df, fast=12, slow=26, signal=9):
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    diff = ema_fast - ema_slow
    dea = diff.ewm(span=signal, adjust=False).mean()
    df['MACD'] = 2 * (diff - dea)
    df['MACD_DIF'] = diff
    df['MACD_DEA'] = dea
    return df

def calc_kdj(df, n=9, k=3, d=3):
    low_min = df['low'].rolling(n).min()
    high_max = df['high'].rolling(n).max()
    rsv = (df['close'] - low_min) / (high_max - low_min) * 100
    df['KDJ_K'] = rsv.ewm(com=k-1, adjust=False).mean()
    df['KDJ_D'] = df['KDJ_K'].ewm(com=d-1, adjust=False).mean()
    df['KDJ_J'] = 3 * df['KDJ_K'] - 2 * df['KDJ_D']
    return df

def calc_rsi(df, periods=(6, 12, 24)):
    for p in periods:
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(p).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(p).mean()
        rs = gain / loss
        df[f'RSI{p}'] = 100 - (100 / (1 + rs))
    return df

def calc_bollinger(df, period=20, std=2):
    df['BOLL_MID'] = df['close'].rolling(period).mean()
    std_val = df['close'].rolling(period).std()
    df['BOLL_UP'] = df['BOLL_MID'] + std * std_val
    df['BOLL_LOW'] = df['BOLL_MID'] - std * std_val
    return df

def calc_all_indicators(df):
    """对DataFrame计算全部技术指标"""
    df = df.sort_values('date').reset_index(drop=True)
    calc_ma(df)
    calc_macd(df)
    calc_kdj(df)
    calc_rsi(df)
    calc_bollinger(df)
    return df


# ========== 新浪数据获取 ==========

def get_sina_kline(code, count=120):
    """获取新浪日K线数据，返回DataFrame"""
    market = get_sina_market_prefix(code)
    url = (f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={market}{code}&scale=240&ma=no&datalen={count}")
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://finance.sina.com.cn'
    })
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode('gbk')
    data = json.loads(raw)
    df = pd.DataFrame(data)
    df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)
    df['volume'] = df['volume'].astype(int)
    df['date'] = pd.to_datetime(df['date'])
    return df

def get_sina_market_prefix(code):
    """判断新浪行情前缀: sh/sz/bj"""
    if code.startswith(('6', '51', '58')):
        return 'sh'
    if code.startswith(('8')):
        return 'bj'
    return 'sz'  # 0, 3, 1, 15, 16, 18, 30 都是sz

def get_sina_realtime(code):
    """获取新浪实时行情快照"""
    market = get_sina_market_prefix(code)
    url = f"https://hq.sinajs.cn/list={market}{code}"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://finance.sina.com.cn'
    })
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode('gbk')
    parts = raw.split('"')[1].split(',')
    return {
        'name': parts[0],
        'open': float(parts[1]),
        'pre_close': float(parts[2]),
        'price': float(parts[3]),
        'high': float(parts[4]),
        'low': float(parts[5]),
        'volume': float(parts[8]),  # 股/份
        'amount': float(parts[9]),  # 元
    }


# ========== 格式化输出 ==========

def format_indicator_summary(df, code):
    """从最新的指标数据生成总结字符串"""
    last = df.iloc[-1]
    signals = []
    sig_ma = []
    
    # 均线排列
    mas = {'MA5': 'ma5', 'MA10': 'ma10', 'MA20': 'ma20', 'MA30': 'ma30', 'MA60': 'ma60'}
    ma_vals = {k: last.get(v, 0) for k, v in mas.items() if v in last}
    
    if all(v in ma_vals for v in ['MA5', 'MA10', 'MA20', 'MA30', 'MA60']):
        if ma_vals['MA5'] > ma_vals['MA10'] > ma_vals['MA20'] > ma_vals['MA30']:
            signals.append(('均线', '✅ 完整多头排列'))
        elif ma_vals['MA5'] < ma_vals['MA10'] < ma_vals['MA20'] < ma_vals['MA30']:
            signals.append(('均线', '❌ 完整空头排列'))
        elif ma_vals['MA5'] > ma_vals['MA20']:
            signals.append(('均线', '⚠️ 短期>中期，偏多'))
        else:
            signals.append(('均线', '⚠️ 短期<中期，偏空'))
    
    # MACD
    if 'MACD' in last and 'MACD_DIF' in last and 'MACD_DEA' in last:
        macd_val = last['MACD']
        dif_val = last['MACD_DIF']
        dea_val = last['MACD_DEA']
        col = ''
        if macd_val > 0:
            col = '✅ 红柱'
        else:
            col = '❌ 绿柱'
        cross = '零轴上金叉' if dif_val > dea_val > 0 else ('零轴上死叉' if dif_val < dea_val and dif_val > 0 else '零轴下')
        signals.append(('MACD', f'{col}, DIF={dif_val:.2f}, DEA={dea_val:.2f} ({cross})'))
    
    # KDJ
    if 'KDJ_K' in last:
        k, d, j = last['KDJ_K'], last['KDJ_D'], last['KDJ_J']
        kdj_sig = '金叉' if k > d and d < 30 else ('死叉' if k < d and k > 80 else '')
        kdj_note = f'K={k:.1f} D={d:.1f} J={j:.1f}'
        if kdj_sig:
            kdj_note += f' ({kdj_sig})'
        signals.append(('KDJ', kdj_note))
    
    # RSI
    rsi_vals = []
    for p in [6, 12, 24]:
        col = f'RSI{p}'
        if col in last:
            rsi_vals.append(f'{col}={last[col]:.1f}')
    if rsi_vals:
        signals.append(('RSI', ', '.join(rsi_vals)))
    
    # BOLL
    if 'BOLL_UP' in last and 'BOLL_LOW' in last:
        close = last['close']
        up, low = last['BOLL_UP'], last['BOLL_LOW']
        pos = '上轨上方' if close > up else ('下轨下方' if close < low else '中轨附近')
        signals.append(('布林带', f'上{up:.2f} 下{low:.2f} ({pos})'))
    
    # 最新K线
    date_str = last['date'].strftime('%m-%d') if hasattr(last['date'], 'strftime') else str(last['date'])[:10]
    vol_wan = last.get('volume', 0) / 1e4
    kline_str = f"{date_str}: O={last['open']:.2f} H={last['high']:.2f} L={last['low']:.2f} C={last['close']:.2f} V={vol_wan:.0f}万"
    
    return signals, kline_str


def get_22_strategy_votes(code):
    """读取项目22策略分析缓存"""
    base = "/mnt/i/wsl/project/QuantitativeTrading_STOCK_A/analysis_output"
    today = datetime.now().strftime("%Y%m%d")
    path = f"{base}/{code}_{today}.json"
    import os
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    # 尝试前一天
    from datetime import timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    path2 = f"{base}/{code}_{yesterday}.json"
    if os.path.exists(path2):
        with open(path2) as f:
            return json.load(f)
    return None


# ========== 完整分析 ==========

def run_full_analysis(code, name_hint=""):
    """
    集成分析入口：
    1. 新浪实时行情
    2. 新浪日K线 + 本地算指标
    3. 项目22策略缓存 (如有)
    4. 返回结构化分析数据
    """
    result = {'code': code, 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    # 1. 实时行情
    rt = get_sina_realtime(code)
    result['realtime'] = rt
    result['name'] = rt.get('name', name_hint)
    
    # 2. K线 + 本地指标
    df = get_sina_kline(code, 120)
    df = calc_all_indicators(df)
    result['kline_count'] = len(df)
    
    sigs, last_kline = format_indicator_summary(df, code)
    result['last_kline'] = last_kline
    result['indicators'] = {k: v for k, v in sigs}
    
    # 最新一条的原始指标值
    last = df.iloc[-1]
    result['indicator_values'] = {}
    for col in ['close', 'open', 'high', 'low', 'volume',
                'MA5', 'MA10', 'MA20', 'MA30', 'MA60',
                'MACD', 'MACD_DIF', 'MACD_DEA',
                'KDJ_K', 'KDJ_D', 'KDJ_J',
                'RSI6', 'RSI12', 'RSI24',
                'BOLL_UP', 'BOLL_MID', 'BOLL_LOW']:
        if col in last:
            v = last[col]
            result['indicator_values'][col] = round(float(v), 4) if isinstance(v, (int, float)) else str(v)
    
    # 120日高低
    result['high_120d'] = float(df['high'].max())
    result['low_120d'] = float(df['low'].min())
    
    # 近5日K线
    recent = df.tail(5)
    result['recent_klines'] = [
        {'date': str(r['date'])[:10], 'open': float(r['open']), 'high': float(r['high']),
         'low': float(r['low']), 'close': float(r['close']), 'volume': int(r['volume'])}
        for _, r in recent.iterrows()
    ]
    
    # 3. 22策略缓存
    strategy = get_22_strategy_votes(code)
    if strategy:
        result['strategy_votes'] = strategy.get('strategy_votes', strategy.get('overall', {}).get('votes', {}))
        result['weighted_votes'] = strategy.get('weighted_votes', strategy.get('overall', {}).get('weighted_votes', {}))
        overall = strategy.get('overall', {})
        result['strategy_signal'] = overall.get('signal', 'N/A')
        result['strategy_confidence'] = overall.get('confidence', 0)
        result['strategy_capital_flow'] = strategy.get('capital_flow', {})
    
    return result
