# coding:gbk
import pandas as pd
import numpy as np
import time

# --------------------------------------------------------
# 【指标计算辅助函数】
# --------------------------------------------------------

# 辅助函数：计算ATR (Average True Range)
def calculate_atr(df, period=14):
    """ 计算指定周期 (period) 的 ATR 指标。需要包含 high, low, close 列。 """
    if df is None or len(df) < period:
        return np.nan
    
    # 1. 计算 True Range (TR)
    df['prev_close'] = df['close'].shift(1)
    df['high_minus_low'] = df['high'] - df['low']
    df['high_minus_prev_close'] = abs(df['high'] - df['prev_close'])
    df['low_minus_prev_close'] = abs(df['low'] - df['prev_close'])
    
    # TR 是三个差值中的最大值
    tr = df[['high_minus_low', 'high_minus_prev_close', 'low_minus_prev_close']].max(axis=1)
    
    # 2. 计算 Average True Range (ATR)
    # 使用 SMA 作为平台兼容性更好的平均方法
    atr = tr.iloc[-period:].mean()
    
    return atr

# --------------------------------------------------------
# 【辅助函数：持仓和交易】
# --------------------------------------------------------

# 保持不变：继续使用兼容的持仓获取函数
def get_current_positions(accountid, ContextInfo):
    """
    通过 get_trade_detail_data 获取当前持仓的股票代码和可用份额。
    返回格式: {'510300.SH': 1000, '510500.SH': 500}
    """
    holdinglist = {}
    
    try:
        # 'stock' 资产类型, 'position' 交易类型
        resultlist = get_trade_detail_data(accountid, 'stock', "position")
    except Exception as e:
        # 尝试 ContextInfo.get_positions 作为备用
        try:
            positions = ContextInfo.get_positions(accountid)
            for pos in positions:
                if pos.m_nCanUseVolume > 0:
                    holdinglist[pos.m_strInstrumentID + "." + pos.m_strExchangeID] = pos.m_nCanUseVolume
            return holdinglist
        except Exception as e2:
            return holdinglist

    for obj in resultlist:
        # 仅考虑可用份额 (m_nCanUseVolume)
        if hasattr(obj, 'm_nCanUseVolume') and obj.m_nCanUseVolume > 0:
            holdinglist[obj.m_strInstrumentID + "." + obj.m_strExchangeID] = obj.m_nCanUseVolume
            
    return holdinglist

# 下单函数封装 (使用 passorder)
def execute_trade(is_buy, stock_code, volume_abs, price, ContextInfo, account_id):
    """ 封装 passorder 函数调用。 """
    opType = 23 if is_buy else 24  # 23: 买入 (BUY)，24: 卖出 (SELL)
    orderType = 1101             # 1101: 按股票数量 (股) 买卖
    prType = 14                  # 14: 限价 (FIX)
    strategyName = "ETF_Momentum_Rank" 
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
    print(f"PASSORDER {action} {stock_code}: {volume_final} 股 @ {price:.2f}")

# --------------------------------------------------------
# 【策略主体：init 和 handlebar】
# --------------------------------------------------------

def init(ContextInfo):
    # ---------------- 1. 策略参数设置 ----------------
    ContextInfo.account_id = '40098981' 
    ContextInfo.hold_num = 5
    ContextInfo.R10_LOOKBACK = 10     # 升级：10日回报率作为动量周期
    ContextInfo.MA20_LOOKBACK = 20    # 20日均线计算周期
    ContextInfo.MA120_LOOKBACK = 120  # 升级：基准趋势过滤周期
    ContextInfo.ATR_PERIOD = 14       # ATR计算周期
    ContextInfo.ATR_MULTIPLIER = 3    # 升级：ATR止损乘数调整为 3
    
    # 设置一个足够长的历史回溯天数
    ContextInfo.look_back_days = ContextInfo.MA120_LOOKBACK + 5 
    
    ContextInfo.etf_pool = [
        # ... (ETF 列表不变)
        '510300.SH', '510050.SH', '159915.SZ', '510500.SH', '159919.SZ', '512100.SH', 
        '512000.SH', '512880.SH', '515000.SH', '515050.SH', '512690.SH', '512170.SH', 
        '515790.SH', '512400.SH', '512660.SH', '512980.SH', '159995.SZ', '512760.SH', 
        '515030.SH', '515210.SH', '512800.SH', '512200.SH', '512710.SH', '515220.SH', 
        '159806.SZ', '512950.SH', '515950.SH', '515230.SH', '512670.SH', '515060.SH',
    ]
    ContextInfo.BENCHMARK_CODE = '510300.SH' # 沪深300 ETF 作为基准趋势过滤
    
    ContextInfo.DAILY_DATA = {} 
    ContextInfo.IS_MARKET_BULL = False # 全局趋势判断
    
    # ---------------- 2. 数据预下载 ----------------
    print("正在下载历史日线(1d)和分钟线(1m)数据...")
    start_date = "20250101" 
    end_date = "" 
    
    # 确保基准也下载
    all_codes = list(set(ContextInfo.etf_pool + [ContextInfo.BENCHMARK_CODE]))
    for etf in all_codes:
        download_history_data(etf, "1d", start_date, end_date)
        download_history_data(etf, "1m", start_date, end_date) 
        
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
        print(f"[{current_time_log}] 策略启动：获取日线数据，计算动量和均线...")
        
        # 1. 获取所有 ETF 和基准的日线数据
        all_codes = list(set(ContextInfo.etf_pool + [ContextInfo.BENCHMARK_CODE]))
        daily_data = ContextInfo.get_market_data_ex(
            fields=["open", "close", "high", "low", "volume"],
            stock_code=all_codes, 
            period="1d", 
            end_time=current_day,
            count=ContextInfo.look_back_days, 
            dividend_type='front'
        )
        
        ContextInfo.DAILY_DATA = {}
        ContextInfo.T_OPEN_PRICE = {} 
        valid_etf_for_daily = []
        
        # --- 1.1 全局趋势过滤检查 (MA120) ---
        df_bench = daily_data.get(ContextInfo.BENCHMARK_CODE)
        ContextInfo.IS_MARKET_BULL = False
        if df_bench is not None and len(df_bench) > ContextInfo.MA120_LOOKBACK:
            bench_close = pd.to_numeric(df_bench['close'], errors='coerce')
            ma120 = bench_close.iloc[-ContextInfo.MA120_LOOKBACK - 1:-1].mean()
            t_minus_1_close = bench_close.iloc[-2]
            
            if t_minus_1_close > ma120:
                ContextInfo.IS_MARKET_BULL = True
                print(f"全局趋势检查：基准 {ContextInfo.BENCHMARK_CODE} 处于多头趋势 (C > MA120)。")
            else:
                print(f"全局趋势检查：基准 {ContextInfo.BENCHMARK_CODE} 处于空头趋势 (C < MA120)，今日暂停买入。")
        else:
            print("全局趋势检查：基准数据不足。")


        # --- 1.2 计算个股指标 ---
        for etf in ContextInfo.etf_pool:
            df_daily = daily_data.get(etf)
            
            # 确保有足够数据计算所有指标
            if df_daily is None or len(df_daily) < ContextInfo.look_back_days - 1: 
                continue

            valid_etf_for_daily.append(etf)

            df_daily['close'] = pd.to_numeric(df_daily['close'], errors='coerce')
            df_daily['volume'] = pd.to_numeric(df_daily['volume'], errors='coerce')
            df_daily['high'] = pd.to_numeric(df_daily['high'], errors='coerce')
            df_daily['low'] = pd.to_numeric(df_daily['low'], errors='coerce')

            # --- 计算指标 ---
            # 1. 10日回报率 (R10)
            r10_return = (df_daily['close'].iloc[-2] / df_daily['close'].iloc[-ContextInfo.R10_LOOKBACK - 2]) - 1
            
            # 2. 5日均线 (MA5)
            ma5 = df_daily['close'].iloc[-6:-1].mean()
            
            # 3. 20日均线 (MA20)
            ma20 = df_daily['close'].iloc[-ContextInfo.MA20_LOOKBACK - 1:-1].mean()
            
            # 4. 5日日均成交量
            avg_volume_5d = df_daily['volume'].iloc[-6:-1].mean()
            
            # 5. ATR (14日平均真实波幅)
            atr_14d = calculate_atr(df_daily.iloc[:-1], period=ContextInfo.ATR_PERIOD)

            ContextInfo.DAILY_DATA[etf] = {
                'ma5': ma5,
                'ma20': ma20,
                'r10_return': r10_return, # 字段名称更新
                'avg_volume_5d': avg_volume_5d,
                'atr_14d': atr_14d,
                't_minus_1_close': df_daily['close'].iloc[-2] 
            }
        
        # 3. 获取 T 日开盘价（9:31 Open）
        t_open_data = ContextInfo.get_market_data_ex(
            fields=["open"], 
            stock_code=valid_etf_for_daily, 
            end_time=current_time_full,
            period="1m", 
            count=1,
            dividend_type='front'
        )

        for etf in valid_etf_for_daily:
            df_open = t_open_data.get(etf)
            if df_open is not None and not df_open.empty:
                ContextInfo.T_OPEN_PRICE[etf] = df_open['open'].iloc[-1]
            else:
                ContextInfo.T_OPEN_PRICE[etf] = None # 显式设为None
        
    # --------------------------------------------------------
    # 【阶段二：买入检查（14:46）】
    # --------------------------------------------------------
    if current_time_str == OP_TIME_STR:
        print(f"[{current_time_log}] **执行相对强度买入检查**...")
        
        # 0. 全局趋势过滤：如果市场处于空头，则不买入
        if not ContextInfo.IS_MARKET_BULL:
            print("因市场处于 MA120 下方空头趋势，暂停买入。")
            return

        etfs_to_check = list(ContextInfo.DAILY_DATA.keys())
        if not etfs_to_check:
            print("因缺少历史日线数据，无法执行买入检查。")
            return

        # A. 获取当前 14:46 的价格 (close) 和 T 日累计成交量 (volume)
        op_data = ContextInfo.get_market_data_ex(
            fields=["close", "volume"], 
            stock_code=etfs_to_check, 
            period="1m", 
            end_time=current_time_full,
            count=1, 
            dividend_type='front'
        )
        
        t_day_volume_data = ContextInfo.get_market_data_ex(
            fields=["volume"], 
            stock_code=etfs_to_check, 
            period="1d", 
            end_time=current_day,
            count=1, 
            dividend_type='front'
        )

        qualified_candidates = []
        
        for etf in etfs_to_check:
            daily_info = ContextInfo.DAILY_DATA.get(etf)
            op_close_bar = op_data.get(etf)
            t_day_vol_bar = t_day_volume_data.get(etf)
            
            if daily_info is None or op_close_bar is None or op_close_bar.empty or t_day_vol_bar is None or t_day_vol_bar.empty:
                continue

            op_price = op_close_bar['close'].iloc[-1]
            t_day_volume = t_day_vol_bar['volume'].iloc[-1]
            
            r10_return = daily_info['r10_return'] # 使用 R10
            ma20 = daily_info['ma20']
            avg_volume_5d = daily_info['avg_volume_5d']
            
            # --- 升级后的买入筛选条件 ---
            
            # 1. 动量初筛: 10日回报率必须为正 (R10 > 0)
            cond_r10 = r10_return > 0 
            
            # 2. 趋势过滤: 当前价格必须在 MA20 之上 
            cond_ma20 = op_price > ma20
            
            # 3. 量能确认: T日累计成交量 > 5日日均量的 80%
            cond_volume = t_day_volume > (avg_volume_5d * 0.8)
            
            if cond_r10 and cond_ma20 and cond_volume:
                qualified_candidates.append({
                    'code': etf, 
                    'op_price': op_price,
                    'r10_return': r10_return, # 用于排序
                    'ma5': daily_info['ma5'],
                    'atr_14d': daily_info['atr_14d']
                })
        
        # B. 相对强度排序（R10_return 越高越好）
        qualified_candidates.sort(key=lambda x: x['r10_return'], reverse=True)
        
        target_buys = qualified_candidates[:ContextInfo.hold_num]
        
        if not target_buys:
            print("今日无符合动量和趋势条件的标的。")
            return
            
        # C. 执行买入（资金管理逻辑不变）
        curr_holdings_dict = get_current_positions(ContextInfo.account_id, ContextInfo)
        try:
            acc_obj = ContextInfo.get_account(ContextInfo.account_id)
            total_asset = acc_obj.m_dAvailable + acc_obj.m_dMarketValue
        except:
            total_asset = 1000000 
        
        target_per_stock = total_asset / ContextInfo.hold_num
        current_hold_count = len(curr_holdings_dict)
        
        for item in target_buys:
            etf = item['code']
            buy_price = item['op_price']
            
            if current_hold_count < ContextInfo.hold_num and etf not in curr_holdings_dict:
                amount = int(target_per_stock / buy_price / 100) * 100
                
                if amount >= 100:
                    execute_trade(True, etf, amount, buy_price, ContextInfo, ContextInfo.account_id)
                    current_hold_count += 1
            
        print(f"买入操作完成。目标买入（按强度排序）: {[item['code'] for item in target_buys]}")

    # --------------------------------------------------------
    # 【阶段三：持仓监控（全天）】
    # --------------------------------------------------------
    else:
        # T 日盘中时刻（非 14:46）执行卖出监控
        curr_holdings_dict = get_current_positions(ContextInfo.account_id, ContextInfo)
        
        if not curr_holdings_dict:
            return 

        if current_time_str < '09:32' or current_time_str > '14:59':
            return

        # 获取最新的 1m 行情（用于当前价格）
        latest_data = ContextInfo.get_market_data_ex(
            fields=["close"], 
            stock_code=list(curr_holdings_dict.keys()), 
            period="1m", 
            end_time=current_time_full,
            count=1, 
            dividend_type='front'
        )
        
        for etf, volume in curr_holdings_dict.items():
            daily_info = ContextInfo.DAILY_DATA.get(etf)
            latest_bar = latest_data.get(etf)

            # 确保当日日线数据和最新行情数据存在，以及ATR是有效数值
            if daily_info is None or latest_bar is None or latest_bar.empty or np.isnan(daily_info.get('atr_14d', np.nan)):
                continue

            current_price = latest_bar['close'].iloc[-1]
            ma5 = daily_info['ma5']
            atr_14d = daily_info['atr_14d']
            
            # --- 动态 ATR 止损检查 ---
            should_sell = False
            sell_reason = ""
            
            # 卖出条件：当前价格低于 MA5 下方 3 倍 ATR
            stop_loss_dynamic = ma5 - (ContextInfo.ATR_MULTIPLIER * atr_14d) 

            if current_price < stop_loss_dynamic:
                should_sell = True
                sell_reason = f"低于动态止损位 (MA5 - {ContextInfo.ATR_MULTIPLIER}xATR)"
                
            if should_sell:
                print(f"卖出 {etf}：{sell_reason}，价格 {current_price:.2f}。")
                execute_trade(False, etf, volume, current_price, ContextInfo, ContextInfo.account_id)