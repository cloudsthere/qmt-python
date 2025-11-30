# coding:gbk
import pandas as pd
import numpy as np
import time

# --------------------------------------------------------
# 【指标计算辅助函数】
# --------------------------------------------------------

# 辅助函数：计算 ATR (Average True Range) - **V17.0 不使用，但保留函数定义**
def calculate_atr(df, period=14):
    """ 计算指定周期 (period) 的 ATR 指标。 """
    if df is None or len(df) < period:
        return np.nan
    
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df['prev_close'] = df['close'].shift(1)
    df['high_minus_low'] = df['high'] - df['low']
    df['high_minus_prev_close'] = abs(df['high'] - df['prev_close'])
    df['low_minus_prev_close'] = abs(df['low'] - df['prev_close'])
    tr = df[['high_minus_low', 'high_minus_prev_close', 'low_minus_prev_close']].max(axis=1)
    
    atr = tr.iloc[-period:].mean()
    
    return atr 

# MACD 指标计算函数 (保持不变)
def calculate_macd(close_series, short_period=12, long_period=26, signal_period=9):
    """ 计算 MACD 指标 (DIF, DEA, MACD Hist)。 """
    if close_series.empty or len(close_series) < long_period:
        return np.nan, np.nan, np.nan
    
    ema_short = close_series.ewm(span=short_period, adjust=False).mean()
    ema_long = close_series.ewm(span=long_period, adjust=False).mean()
    
    dif = ema_short - ema_long
    dea = dif.ewm(span=signal_period, adjust=False).mean()
    macd_hist = (dif - dea) * 2
    
    # 返回整个序列
    return dif, dea, macd_hist

# --------------------------------------------------------
# 【辅助函数：持仓和交易】
# --------------------------------------------------------

def get_current_positions(accountid, ContextInfo):
    # ... (持仓获取函数保持不变)
    holdinglist = {}
    try:
        positions = ContextInfo.get_positions(accountid)
        for pos in positions:
            if pos.m_nCanUseVolume > 0 and pos.m_nCanSellVolume > 0:
                holdinglist[pos.m_strInstrumentID + "." + pos.m_strExchangeID] = pos.m_nCanUseVolume
        return holdinglist
    except Exception as e:
        try:
            resultlist = get_trade_detail_data(accountid, 'stock', "position")
            for obj in resultlist:
                if hasattr(obj, 'm_nCanUseVolume') and obj.m_nCanUseVolume > 0:
                    holdinglist[obj.m_strInstrumentID + "." + obj.m_strExchangeID] = obj.m_nCanUseVolume
            return holdinglist
        except Exception as e2:
            return holdinglist

def execute_trade(is_buy, stock_code, volume_abs, price, ContextInfo, account_id):
    # ... (下单函数，策略名称改为 V17)
    opType = 23 if is_buy else 24 
    orderType = 1101          
    prType = 14               
    strategyName = "Stock_MACD_Momentum_V17" # **策略名称更新 V17**
    quickTrade = 1 
    userOrderId = str(int(time.time() * 1000)) 
    
    volume_final = int(volume_abs)
    
    if volume_final < 100 and is_buy: 
        print(f"PASSORDER 忽略: {stock_code} 买入量不足 100 股 ({volume_final})")
        return

    passorder(
        opType, 
        orderType, 
        account_id, 
        stock_code, 
        prType, 
        price, 
        volume_final, 
        strategyName, 
        quickTrade, 
        userOrderId, 
        ContextInfo
    )
    
    action = "买入" if is_buy else "卖出"
    # print(f"PASSORDER {action} {stock_code}: {volume_final} 股 @ {price:.2f}")

# --------------------------------------------------------
# 【策略主体：init 和 handlebar】
# --------------------------------------------------------

def init(ContextInfo):
    # ---------------- 1. 策略参数设置 ----------------
    ContextInfo.account_id = '40098981' 
    ContextInfo.hold_num = 10
    
    # MACD 参数
    ContextInfo.MACD_SHORT = 12 
    ContextInfo.MACD_LONG = 26
    ContextInfo.MACD_SIGNAL = 9
    
    # **【V17.0 恢复使用】固定百分比止损/过滤参数**
    ContextInfo.MAX_DAILY_DROP = -0.02 # 单日最大跌幅限制 (-2%)
    
    # ATR 相关参数移除，仅保留 MAX_DAILY_DROP
    # ContextInfo.ATR_PERIOD = 14
    # ContextInfo.ATR_MULTIPLIER = 2.0
    
    # 历史数据量需要满足 MACD 的最大周期
    ContextInfo.look_back_days = ContextInfo.MACD_LONG + ContextInfo.MACD_SIGNAL + 20 
    
    # 股票池 (保持不变，使用沪深300+中证500)
    stock_pool = ContextInfo.get_stock_list_in_sector('沪深300') + ContextInfo.get_stock_list_in_sector('中证500')
    ContextInfo.stock_pool = list(set(stock_pool))
    
    ContextInfo.DAILY_DATA = {} 
    ContextInfo.HOLDING_BUY_DATE = {} 
    
    # ---------------- 2. 数据预下载 ----------------
    print("正在下载历史日线(1d)和分钟线(1m)数据...")
    start_date = "20250101" 
    end_date = "" 
    
    for stock in ContextInfo.stock_pool:
        download_history_data(stock, "1d", start_date, end_date) 
        download_history_data(stock, "1m", start_date, end_date) 
        
    print("历史数据下载任务已发送。")

def handlebar(ContextInfo):
    
    bar_timetag = ContextInfo.get_bar_timetag(ContextInfo.barpos)
    current_time_str = timetag_to_datetime(bar_timetag, '%H:%M')
    current_time_log = timetag_to_datetime(bar_timetag, '%Y-%m-%d %H:%M')
    current_time_full = timetag_to_datetime(bar_timetag, '%Y%m%d%H%M%S')
    current_day = timetag_to_datetime(bar_timetag, '%Y%m%d')
    
    OP_TIME_STR = '14:46'
    
    # --------------------------------------------------------
    # 【阶段一：每日数据初始化（早盘 09:31）】
    # --------------------------------------------------------
    if current_time_str == '09:31': 
        
        all_codes = ContextInfo.stock_pool
        # 必须获取 close, open, high, low, preClose
        daily_data = ContextInfo.get_market_data_ex(
            fields=["close", "high", "low", "open", "preClose"], 
            stock_code=all_codes, 
            period="1d", 
            end_time=current_day,
            count=ContextInfo.look_back_days, 
            dividend_type='none'
        )
        
        ContextInfo.DAILY_DATA = {}
        
        for stock in ContextInfo.stock_pool:
            df_daily = daily_data.get(stock)
            
            if df_daily is None or len(df_daily) < ContextInfo.MACD_LONG + ContextInfo.MACD_SIGNAL + 2: 
                continue

            df_daily['close'] = pd.to_numeric(df_daily['close'], errors='coerce')
            
            # --- MACD 计算 ---
            close_series = df_daily['close']
            dif_series, dea_series, macd_hist_series = calculate_macd(
                close_series, 
                ContextInfo.MACD_SHORT, 
                ContextInfo.MACD_LONG, 
                ContextInfo.MACD_SIGNAL
            )
            
            dif_t_minus_1 = dif_series.iloc[-2]
            dea_t_minus_1 = dea_series.iloc[-2]
            dif_t_minus_2 = dif_series.iloc[-3]
            dea_t_minus_2 = dea_series.iloc[-3]
            
            is_macd_golden_cross = (dif_t_minus_2 <= dea_t_minus_2) and (dif_t_minus_1 > dea_t_minus_1)
            
            # 获取当日开盘价 (作为日内止损/过滤基准价)
            t_day_open_price = df_daily['open'].iloc[-1]
            
            # V17.0 不再计算 dynamic_drop_pct
            
            ContextInfo.DAILY_DATA[stock] = {
                't_day_open_price': t_day_open_price,         
                'dif_t_minus_1': dif_t_minus_1, 
                'dea_t_minus_1': dea_t_minus_1,
                'is_macd_golden_cross': is_macd_golden_cross,
            }
        
    # --------------------------------------------------------
    # 【阶段二：买入检查（14:46）】
    # --------------------------------------------------------
    if current_time_str == OP_TIME_STR:
        
        stocks_to_check = list(ContextInfo.DAILY_DATA.keys())
        if not stocks_to_check:
            print("因缺少指标数据，无法执行买入检查。")
            return

        # A. 获取当前 14:46 的价格 (close)
        op_data = ContextInfo.get_market_data_ex(
            fields=["close"], 
            stock_code=stocks_to_check, 
            period="1m", 
            end_time=current_time_full,
            count=1, 
            dividend_type='none'
        )

        qualified_candidates = []
        
        for stock in stocks_to_check:
            daily_info = ContextInfo.DAILY_DATA.get(stock)
            op_close_bar = op_data.get(stock)
            
            if daily_info is None or op_close_bar is None or op_close_bar.empty:
                continue

            op_price = op_close_bar['close'].iloc[-1]
            dif_t_minus_1 = daily_info['dif_t_minus_1']
            is_golden_cross = daily_info['is_macd_golden_cross']
            
            t_day_open_price = daily_info.get('t_day_open_price', 0)
            
            # 严格入场条件：
            if is_golden_cross:
                
                # **【V17.0 恢复】买入过滤：使用固定的 MAX_DAILY_DROP 百分比阈值**
                if t_day_open_price > 0:
                    
                    # 计算 14:46 价格相对于当日开盘价的跌幅
                    current_drop_from_open = (op_price / t_day_open_price) - 1
                    
                    if current_drop_from_open < ContextInfo.MAX_DAILY_DROP:
                        # 满足金叉，但日内跌幅超过限制 (例如：跌幅超过-2%)，不买入
                        print(f"[{current_time_log}] PASS BUY {stock}: 14:46价格 ({op_price:.2f}) 日内跌幅 ({current_drop_from_open*100:.2f}%) 超过固定阈值 ({ContextInfo.MAX_DAILY_DROP*100:.2f}%)，跳过。")
                        continue # 跳过当前股票，不加入候选列表
                
                qualified_candidates.append({
                    'code': stock, 
                    'op_price': op_price,
                    'macd_strength': dif_t_minus_1, 
                })
        
        # B. 相对强度排序（DIF 越高越好）
        qualified_candidates.sort(key=lambda x: x['macd_strength'], reverse=True)
        
        target_buys = qualified_candidates[:ContextInfo.hold_num]
        
        # C. 执行买入
        curr_holdings_dict = get_current_positions(ContextInfo.account_id, ContextInfo)
        try:
            acc_obj = ContextInfo.get_account(ContextInfo.account_id)
            total_asset = acc_obj.m_dAvailable + acc_obj.m_dMarketValue
        except:
            total_asset = 1000000 
        
        target_per_stock = total_asset / ContextInfo.hold_num
        current_hold_count = len(curr_holdings_dict)
        
        for item in target_buys:
            stock = item['code']
            buy_price = item['op_price']
            
            if current_hold_count < ContextInfo.hold_num and stock not in curr_holdings_dict:
                amount = int(target_per_stock / buy_price / 100) * 100
                
                if amount >= 100:
                    execute_trade(True, stock, amount, buy_price, ContextInfo, ContextInfo.account_id)
                    current_hold_count += 1
                    ContextInfo.HOLDING_BUY_DATE[stock] = current_day 
            
        if len(target_buys) > 0:
            print(f"[{current_time_log}]买入操作完成。目标买入（按MACD强度排序）: {[item['code'] for item in target_buys]}")

    # --------------------------------------------------------
    # 【阶段三：持仓监控（MACD 死叉/日内开盘价跌幅 清仓）】
    # --------------------------------------------------------
    else:
        curr_holdings_dict = get_current_positions(ContextInfo.account_id, ContextInfo)
        
        if not curr_holdings_dict:
            return 

        if current_time_str < '09:32' or current_time_str > '14:59':
            return

        holding_stocks = list(curr_holdings_dict.keys())
        latest_data = ContextInfo.get_market_data_ex(
            fields=["close"], 
            stock_code=holding_stocks, 
            period="1m", 
            end_time=current_time_full,
            count=1, 
            dividend_type='none'
        )
        
        for stock, volume in curr_holdings_dict.items():
            daily_info = ContextInfo.DAILY_DATA.get(stock)
            latest_bar = latest_data.get(stock)
            
            if daily_info is None or latest_bar is None or latest_bar.empty:
                continue

            current_price = latest_bar['close'].iloc[-1]
            
            should_sell = False
            sell_reason = ""
            
            # 1. **【V17.0 恢复】固定百分比日内止损检查** (基准价：当日开盘价)
            t_day_open_price = daily_info.get('t_day_open_price', 0)
            
            if t_day_open_price > 0:
                # 跌幅相对于开盘价的百分比
                current_daily_drop_from_open = (current_price / t_day_open_price) - 1
                
                if current_daily_drop_from_open < ContextInfo.MAX_DAILY_DROP:
                    should_sell = True
                    sell_reason = f"日内跌破开盘价 {abs(ContextInfo.MAX_DAILY_DROP)*100:.0f}% ({current_daily_drop_from_open*100:.2f}%)"


            # 2. MACD 死叉检查 (14:55) - 保持不变
            if current_time_str == '14:55':
                if daily_info['dif_t_minus_1'] < daily_info['dea_t_minus_1']:
                    should_sell = True
                    sell_reason = "MACD趋势已死叉 (T-1 日已死叉)"
            
            
            if should_sell and volume > 0:
                print(f"[{current_time_log}] 卖出 {stock}：{sell_reason}，价格 {current_price:.2f}。")
                execute_trade(False, stock, volume, current_price, ContextInfo, ContextInfo.account_id)