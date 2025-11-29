# coding:gbk
import pandas as pd
import numpy as np
import time

# --------------------------------------------------------
# 【指标计算辅助函数】
# --------------------------------------------------------

# 辅助函数：计算 ATR (Average True Range) - **V16.0 启用**
def calculate_atr(df, period=14):
    """ 计算指定周期 (period) 的 ATR 指标。需要包含 high, low, close 列。 """
    if df is None or len(df) < period:
        # ATR 需要至少 period+1 天数据，但因为 df 已经被切片到 T 日，这里判断长度是否足够
        return np.nan
    
    # 确保 'close' 是数值类型
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    
    # 1. 计算 True Range (TR)
    # TR = max[(H - L), abs(H - C_prev), abs(L - C_prev)]
    df['prev_close'] = df['close'].shift(1)
    df['high_minus_low'] = df['high'] - df['low']
    df['high_minus_prev_close'] = abs(df['high'] - df['prev_close'])
    df['low_minus_prev_close'] = abs(df['low'] - df['prev_close'])
    tr = df[['high_minus_low', 'high_minus_prev_close', 'low_minus_prev_close']].max(axis=1)
    
    # 2. 计算 ATR (Smoothed Moving Average of TR)
    # 这里我们使用简单的移动平均 (SMA) 来简化回测实现，实际交易中通常用 EMA。
    # ATR 是整个序列的 SMA，但我们只需要最新的一个值
    atr = tr.iloc[-period:].mean()
    
    return atr # 返回ATR的绝对值 (价格单位)

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
    # ... (下单函数保持不变，策略名称改为 V16)
    opType = 23 if is_buy else 24 
    orderType = 1101          
    prType = 14               
    strategyName = "Stock_MACD_Momentum_V16" # **策略名称更新 V16**
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
    
    # **【V16.0 新增/修改】动态止损参数**
    ContextInfo.ATR_PERIOD = 14       # ATR 计算周期
    ContextInfo.ATR_MULTIPLIER = 2.0  # ATR 止损乘数 (例如 2.0 代表 2倍 ATR 止损)
    
    # 原有的 MAX_DAILY_DROP 参数不再使用，但保留以防万一
    ContextInfo.MAX_DAILY_DROP = -0.02 
    
    # 历史数据量需要满足 MACD 和 ATR 的最大周期
    ContextInfo.look_back_days = max(ContextInfo.MACD_LONG + ContextInfo.MACD_SIGNAL, ContextInfo.ATR_PERIOD) + 20 
    
    # # ！！！重要：此处为股票池的示例！！！
    # ContextInfo.stock_pool = [
    #     # '600030.SH',
    #     #  '600519.SH', 
    #     #  '000001.SZ', 
    #     '600036.SH', 
    #     # '300750.SZ', 
    #     #  '000333.SZ', '600887.SH', '000538.SZ', '601318.SH',
    #     #  '601398.SH',  '000651.SZ', '600000.SH', 
    #     #  '601857.SH', 
    #     #  '600028.SH', '000858.SZ',
    # ]
    stock_pool = ContextInfo.get_stock_list_in_sector('沪深300')
    ContextInfo.stock_pool = stock_pool
    
    ContextInfo.DAILY_DATA = {} 
    ContextInfo.HOLDING_BUY_DATE = {} 
    
    # ---------------- 2. 数据预下载 ----------------
    print("正在下载历史日线(1d)和分钟线(1m)数据...")
    start_date = "20250101" 
    end_date = "" 
    
    for stock in ContextInfo.stock_pool:
        # ATR 需要 high, low, close
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
        # 必须获取 close, open, preClose, high, low
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
            
            if df_daily is None or len(df_daily) < ContextInfo.look_back_days - 5: # 简化数据量检查
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
            
            # --- 波动率 ATR 计算 ---
            atr_abs = calculate_atr(df_daily, ContextInfo.ATR_PERIOD)
            
            # 获取当日开盘价 (作为止损/过滤基准价)
            t_day_open_price = df_daily['open'].iloc[-1]
            
            # **【V16.0 核心逻辑】计算动态止损/过滤百分比阈值**
            dynamic_drop_pct = np.nan
            if not np.isnan(atr_abs) and t_day_open_price > 0:
                # 跌幅的绝对价格 = ATR_ABS * MULTIPLIER
                drop_abs = atr_abs * ContextInfo.ATR_MULTIPLIER
                # 将绝对价格转化为相对于当日开盘价的百分比跌幅 (负值)
                dynamic_drop_pct = - (drop_abs / t_day_open_price)
            
            ContextInfo.DAILY_DATA[stock] = {
                't_day_open_price': t_day_open_price,         
                'dif_t_minus_1': dif_t_minus_1, 
                'dea_t_minus_1': dea_t_minus_1,
                'is_macd_golden_cross': is_macd_golden_cross,
                'dynamic_drop_pct': dynamic_drop_pct # **【V16.0 新增】动态百分比阈值**
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
            dynamic_drop_pct = daily_info['dynamic_drop_pct'] # 获取动态阈值
            t_day_open_price = daily_info.get('t_day_open_price', 0)
            
            # 严格入场条件：
            if is_golden_cross:
                
                # **【V16.0 修改】买入过滤：使用动态 ATR 百分比阈值**
                if not np.isnan(dynamic_drop_pct) and t_day_open_price > 0:
                    
                    # 计算 14:46 价格相对于当日开盘价的跌幅
                    current_drop_from_open = (op_price / t_day_open_price) - 1
                    
                    if current_drop_from_open < dynamic_drop_pct:
                        # 满足金叉，但日内跌幅超过动态限制 (例如：跌幅超过 2倍ATR)，不买入
                        print(f"[{current_time_log}] PASS BUY {stock}: 14:46价格 ({op_price:.2f}) 日内跌幅 ({current_drop_from_open*100:.2f}%) 超过动态阈值 ({dynamic_drop_pct*100:.2f}%)，跳过。")
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
            
            # 1. **【V16.0 修改】动态 ATR 日内止损检查** (基准价：当日开盘价)
            t_day_open_price = daily_info.get('t_day_open_price', 0)
            dynamic_drop_pct = daily_info.get('dynamic_drop_pct', np.nan)
            
            if t_day_open_price > 0 and not np.isnan(dynamic_drop_pct):
                # 跌幅相对于开盘价的百分比
                current_daily_drop_from_open = (current_price / t_day_open_price) - 1
                
                if current_daily_drop_from_open < dynamic_drop_pct:
                    should_sell = True
                    # 使用动态阈值进行日志记录
                    sell_reason = f"日内跌幅 ({current_daily_drop_from_open*100:.2f}%) 超过动态ATR止损 ({dynamic_drop_pct*100:.2f}%)"


            # 2. MACD 死叉检查 (14:55) - 保持不变
            if current_time_str == '14:55':
                if daily_info['dif_t_minus_1'] < daily_info['dea_t_minus_1']:
                    should_sell = True
                    sell_reason = "MACD趋势已死叉 (T-1 日已死叉)"
            
            
            if should_sell and volume > 0:
                print(f"[{current_time_log}] 卖出 {stock}：{sell_reason}，价格 {current_price:.2f}。")
                execute_trade(False, stock, volume, current_price, ContextInfo, ContextInfo.account_id)