# coding:gbk
import pandas as pd
import numpy as np
import time

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
  
  # 假设 get_trade_detail_data 是可用的全局函数
  try:
    # 'stock' 资产类型, 'position' 交易类型
    # 注意：get_trade_detail_data 需确保在您的运行环境中是可用的全局函数
    resultlist = get_trade_detail_data(accountid, 'stock', "position")
  except Exception as e:
    # 尝试 ContextInfo.get_positions 作为备用（虽然您提到它不可用）
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
  orderType = 1101        # 1101: 按股票数量 (股) 买卖
  prType = 14          # 14: 限价 (FIX)
  strategyName = "ETF_Min_Trend"
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
  
  # 修正点 3：启用完整的 ETF 股票池！
  ContextInfo.etf_pool = [
        # 宽基指数ETF
        '510300.SH',  # 沪深300ETF
        '510050.SH',  # 上证50ETF
        '159915.SZ',  # 创业板ETF
        '510500.SH',  # 中证500ETF
        '159919.SZ',  # 沪深300ETF
        '512100.SH',  # 中证1000ETF
        '512000.SH',  # 券商ETF
        '512880.SH',  # 证券ETF
        '515000.SH',  # 科技ETF
        '515050.SH',  # 5GETF
        
        # 行业ETF
        '512690.SH',  # 酒ETF
        '512170.SH',  # 医疗ETF
        '515790.SH',  # 光伏ETF
        '512400.SH',  # 有色金属ETF
        '512660.SH',  # 军工ETF
        '512980.SH',  # 传媒ETF
        '159995.SZ',  # 芯片ETF
        '512760.SH',  # 半导体ETF
        '515030.SH',  # 新能源车ETF
        '515210.SH',  # 钢铁ETF
        
        # 主题ETF
        '512800.SH',  # 银行ETF
        '512200.SH',  # 房地产ETF
        '512710.SH',  # 军工龙头ETF
        '515220.SH',  # 煤炭ETF
        '159806.SZ',  # 国证ETF
        '512950.SH',  # 央企ETF
        '515950.SH',  # 医药ETF
        '515230.SH',  # 软件ETF
        '512670.SH',  # 国防ETF
        '515060.SH',  # 人工智能ETF
  ]
  
  ContextInfo.DAILY_DATA = {}  
  ContextInfo.T_OPEN_PRICE = {} 

  # ---------------- 2. 数据预下载 ----------------
  print("正在下载历史日线(1d)和分钟线(1m)数据...")
  # 建议回溯到更早的日期，以确保回测起始日有足够的历史数据
  start_date = "20250101" # 建议改成更早的日期
  end_date = "" 
  
  for etf in ContextInfo.etf_pool:
    download_history_data(etf, "1d", start_date, end_date)
    download_history_data(etf, "1m", start_date, end_date) 
    
#   print("历史数据下载任务已发送。")
  
  # ---------------- 3. 数据订阅 (移除不必要的调用) ----------------
  # 修正点 1：移除 ContextInfo.subscribe_quote，完全依赖 set_universe + handlebar
#   print("已配置策略依赖 set_universe 自动推送 1m 行情到 handlebar。")

def handlebar(ContextInfo):
  
#   current_time_ms = ContextInfo.get_bar_timetag(ContextInfo.barpos)
#   dt_time = pd.to_datetime(current_time_ms, unit='ms')
  bar_timetag = ContextInfo.get_bar_timetag(ContextInfo.barpos)
  current_time_str = timetag_to_datetime(bar_timetag, '%H:%M')
  current_time_log = timetag_to_datetime(bar_timetag, '%Y-%m-%d %H:%M')
  current_time_full = timetag_to_datetime(bar_timetag, '%Y%m%d%H%M%S')
  current_day = timetag_to_datetime(bar_timetag, '%Y%m%d')
  
  OP_TIME_STR = '14:46'
  
#   current_time_str = dt_time.strftime('%H:%M')
#   print(f"当前时间: {current_time_log}")
  
  # --------------------------------------------------------
  # 【阶段一：每日数据初始化（早盘 09:31）】
  # --------------------------------------------------------
  if current_time_str == '09:31': 
    # print(f"[{current_time_log}] 策略启动：获取日线数据...")
    
    look_back_days = 10 
    
    # 使用完整的 etf_pool 来获取数据
    daily_data = ContextInfo.get_market_data_ex(
      fields=["open", "close"], 
      stock_code=ContextInfo.etf_pool, 
      period="1d", 
      end_time=current_day,
      count=look_back_days, 
      dividend_type='front'
    )
    
    ContextInfo.DAILY_DATA = {}
    valid_etf_for_daily = []
    
    for etf in ContextInfo.etf_pool:
      df_daily = daily_data.get(etf)
      
      # 至少需要 7 个 bar
      if df_daily is None or len(df_daily) < 7: 
        print(f"{etf} 无效日线数据，跳过...")
        continue

      valid_etf_for_daily.append(etf)

      t_minus_1 = df_daily.iloc[-2]
      t_minus_2 = df_daily.iloc[-3]
      
      ma5 = df_daily['close'].iloc[-5:].mean()
      
      ContextInfo.DAILY_DATA[etf] = {
        't_minus_1_open': t_minus_1['open'],
        't_minus_1_close': t_minus_1['close'],
        't_minus_2_open': t_minus_2['open'],
        't_minus_2_close': t_minus_2['close'],
        'ma5': ma5
      }
    
    # 3. 获取 T 日开盘价（使用 9:31 时的 Open）
    # 只需要获取有有效日线数据的 ETF 的开盘价
    t_open_data = ContextInfo.get_market_data_ex(
      fields=["open"], 
      stock_code=valid_etf_for_daily, 
      end_time=current_time_full,
      period="1m", 
      count=1,
      dividend_type='front'
    )
    # print(t_open_data)

    ContextInfo.T_OPEN_PRICE = {}
    for etf in valid_etf_for_daily:
      df_open = t_open_data.get(etf)
      if df_open is not None and not df_open.empty:
        ContextInfo.T_OPEN_PRICE[etf] = df_open['open'].iloc[-1]
      else:
        print(f"Warning: ETF {etf} 在 9:31 未能获取到 T 日开盘价，跳过。") 
        
  # --------------------------------------------------------
  # 【阶段二：买入检查（14:46）】
  # --------------------------------------------------------
  if current_time_str == OP_TIME_STR:
    print(f"[{current_time_log}] **执行买入检查**...")
    
    # A. 获取当前 14:46 的价格 (op价)
    # 修正：只从有有效数据的 ETF 中筛选
    etfs_to_check = list(ContextInfo.DAILY_DATA.keys())
    if not etfs_to_check:
      print("因缺少历史日线数据，无法执行买入检查。")
      return

    print(current_time_full)
    op_data = ContextInfo.get_market_data_ex(
      fields=["close"], 
      stock_code=etfs_to_check, 
      period="1m", 
      end_time=current_time_full,
      count=1, 
      dividend_type='front'
    )
    # print(op_data)
    # exit()
    
    buy_candidates = []
    
    for etf in etfs_to_check:
      daily_info = ContextInfo.DAILY_DATA.get(etf)
      t_open = ContextInfo.T_OPEN_PRICE.get(etf)
      op_close = op_data.get(etf)
      print(daily_info )
      print(t_open)
      print(op_close)

      
      if daily_info is None or t_open is None or op_close is None or op_close.empty:
        print(f"Warning: ETF {etf} 在 14:46 未能获取到必要数据，跳过。")
        continue

      op_price = op_close['close'].iloc[-1]
      
      # 1. 检查 T-2 和 T-1 阳线 (Close > Open)
      cond_a = (daily_info['t_minus_2_close'] > daily_info['t_minus_2_open']) and \
          (daily_info['t_minus_1_close'] > daily_info['t_minus_1_open'])
          
      # 2. 检查 T 日 op 阳线 (op > T日 Open)
      cond_b = op_price > t_open

      if cond_a and cond_b:
        buy_candidates.append({'code': etf, 'op_price': op_price})
    
    # B. 排序并执行买入
    if not buy_candidates:
      print("今日无符合三阳线条件的标的。")
      return
      
    target_buys = buy_candidates[:ContextInfo.hold_num]
    
    # 后续交易逻辑不变...
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
      
    print(f"买入操作完成。目标买入: {[item['code'] for item in target_buys]}")

  # --------------------------------------------------------
  # 【阶段三：持仓监控（全天）】
  # --------------------------------------------------------
  else:
    # T 日盘中时刻（非 14:46）执行卖出监控
    # 此处逻辑不变，只依赖 ContextInfo.DAILY_DATA 和 ContextInfo.T_OPEN_PRICE
    curr_holdings_dict = get_current_positions(ContextInfo.account_id, ContextInfo)
    
    if not curr_holdings_dict:
      return 

    if current_time_str < '09:32' or current_time_str > '14:59':
      return

    # print(f"[{current_time_str}] 盘中监控持仓...")
    
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
      t_open = ContextInfo.T_OPEN_PRICE.get(etf)
      latest_bar = latest_data.get(etf)
    #   print(latest_bar)

      if daily_info is None or t_open is None or latest_bar is None or latest_bar.empty:
        continue

      current_price = latest_bar['close'].iloc[-1]
      
      # --- 止损/止盈检查 ---
      should_sell = False
      sell_reason = ""
      
      stop_loss_t_open = t_open * (1 - 0.005)
      if current_price < stop_loss_t_open:
        should_sell = True
        sell_reason = "低于T日开盘价0.5%"
        
      stop_loss_t_minus_1 = daily_info['t_minus_1_close'] * (1 - 0.005)
      if current_price < stop_loss_t_minus_1:
        should_sell = True
        sell_reason = "低于T-1日收盘价0.5%"
        
      stop_loss_ma5 = daily_info['ma5']
      if current_price < stop_loss_ma5:
        should_sell = True
        sell_reason = "低于5日均线"

      if should_sell:
        print(f"卖出 {etf}：{sell_reason}，价格 {current_price:.2f}。")
        execute_trade(False, etf, volume, current_price, ContextInfo, ContextInfo.account_id)



