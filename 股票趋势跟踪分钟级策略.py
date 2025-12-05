# coding:gbk
import pandas as pd
import numpy as np
import time
import datetime 

class G(): pass

g = G()


# --------------------------------------------------------
# 【指标计算辅助函数】
# --------------------------------------------------------

# 辅助函数：计算 ATR (Average True Range) - **V1.18.2 启用**
def calculate_atr(df, period=14):
	""" 计算指定周期 (period) 的 ATR 指标。需要包含 high, low, close 列。 """
	if df is None or len(df) < period:
		return np.nan
	
	df['close'] = pd.to_numeric(df['close'], errors='coerce')
	
	# 1. 计算 True Range (TR)
	# TR = max[(H - L), abs(H - C_prev), abs(L - C_prev)]
	df['prev_close'] = df['close'].shift(1)
	df['high_minus_low'] = df['high'] - df['low']
	df['high_minus_prev_close'] = abs(df['high'] - df['prev_close'])
	df['low_minus_prev_close'] = abs(df['low'] - df['prev_close'])
	# 使用 .max(axis=1) 找出每一行 (即每一天) 的最大值
	tr = df[['high_minus_low', 'high_minus_prev_close', 'low_minus_prev_close']].max(axis=1)
	
	# 2. 计算 ATR (Smoothed Moving Average of TR)
	# 使用 SMA 简化实现，取最新的 period 天的平均值
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
	
	return dif, dea, macd_hist

# --------------------------------------------------------
# 【辅助函数：持仓和交易】
# --------------------------------------------------------

def get_current_positions(accountid, ContextInfo):
	# ... (持仓获取函数保持不变)
	holdinglist = {}

	resultlist = get_trade_detail_data(accountid, 'STOCK', "POSITION")
	for obj in resultlist:
		if hasattr(obj, 'm_nCanUseVolume') and obj.m_nCanUseVolume > 0:
			holdinglist[obj.m_strInstrumentID + "." + obj.m_strExchangeID] = obj.m_nCanUseVolume
	return holdinglist


def get_account_asset(account_id):
	account = get_trade_detail_data(account_id, 'STOCK', 'ACCOUNT')
	# print(account)
	return account[0].m_dBalance

def execute_trade(is_buy, stock_code, volume_abs, price, ContextInfo, account_id):
	"""
	下单函数，在生产环境应包含健壮的异常处理。
	"""
	opType = 23 if is_buy else 24     
	orderType = 1101          
	prType = 14               
	strategyName = "Stock_MACD_Momentum_V18_2_ATR" # **策略名称更新 V18.2**
	quickTrade = 1 
	userOrderId = str(int(time.time() * 1000)) 
	
	volume_final = int(volume_abs)
	action = "买入" if is_buy else "卖出"
	
	if volume_final < 100 and is_buy: 
		print(f"忽略: {stock_code} 买入量不足 100 股 ({volume_final})")
		return

	try:
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
		print(f"交易成功: {action} {stock_code}: {volume_final} 股 @ {price:.2f}")
		
	except Exception as e:
		print(f"交易失败: {action} {stock_code} {volume_final} 股 @ {price:.2f}. 错误: {e}")

# --------------------------------------------------------
# 【策略主体：init 和 handlebar】
# --------------------------------------------------------

def init(ContextInfo):
	ContextInfo.is_debug = False # 生产环境：设置为 False
	print("策略初始化开始。")
	
	# ---------------- 1. 策略参数设置 ----------------
	ContextInfo.account_id = '40098981' if ContextInfo.is_debug else '8887911006'
	ContextInfo.hold_num = 10
	
	# MACD 参数
	ContextInfo.MACD_SHORT = 12 
	ContextInfo.MACD_LONG = 26
	ContextInfo.MACD_SIGNAL = 9
	
	# **【V1.18.2 修改】动态 ATR 止损/过滤参数**
	ContextInfo.ATR_PERIOD = 14       # ATR 计算周期
	ContextInfo.ATR_MULTIPLIER = 2.0  # ATR 止损乘数 (例如 2.0 代表 2倍 ATR 止损)
	# ContextInfo.MAX_DAILY_DROP 参数不再使用
	
	# 历史数据量需要满足 MACD 和 ATR 的最大周期
	ContextInfo.look_back_days = max(ContextInfo.MACD_LONG + ContextInfo.MACD_SIGNAL, ContextInfo.ATR_PERIOD) + 20 
	
	# 股票池 (保持不变，使用沪深300+中证500)
	stock_pool = ContextInfo.get_stock_list_in_sector('沪深300') + ContextInfo.get_stock_list_in_sector('中证500')
	ContextInfo.stock_pool = list(set(stock_pool))
	
	g.DAILY_DATA = {} 
	g.HOLDING_BUY_DATE = {} 
	
	# ---------------- 2. 数据预下载 【动态计算 start_date】 ----------------
	
	if ContextInfo.is_debug:
		start_date = "20250101"
	else:
		# 动态计算所需的起始日期：当前日期 - look_back_days
		today = datetime.date.today()
		start_dt = today - datetime.timedelta(days=ContextInfo.look_back_days + 10) 
		start_date = start_dt.strftime('%Y%m%d')
	
	# print(f"正在下载策略所需历史日线数据。起始日期: {start_date} (需 {ContextInfo.look_back_days}日数据量)")
	# download_history_data 等函数调用省略
	
	# print("历史日线数据下载任务已发送。")

def handlebar(ContextInfo):
	if not ContextInfo.is_last_bar() and not ContextInfo.is_debug: 
		return
	
	bar_timetag = ContextInfo.get_bar_timetag(ContextInfo.barpos)
	current_time_str = timetag_to_datetime(bar_timetag, '%H:%M')
	current_time_log = timetag_to_datetime(bar_timetag, '%Y-%m-%d %H:%M')
	current_time_full = timetag_to_datetime(bar_timetag, '%Y%m%d%H%M%S')
	current_day = timetag_to_datetime(bar_timetag, '%Y%m%d')
	
	START_TIME_STR = '09:31'
	OP_TIME_STR = '09:35'
	CHECK_MACD_SELL_TIME = '14:55'
	
	# --------------------------------------------------------
	# 【阶段一：每日数据初始化（早盘 09:31）】
	# --------------------------------------------------------
	if current_time_str == START_TIME_STR : 
		print(f"[{current_time_log}] 阶段一：每日数据初始化开始。")
		
		all_codes = ContextInfo.stock_pool
		daily_data = ContextInfo.get_market_data_ex(
			fields=["close", "high", "low", "open", "preClose"], 
			stock_code=all_codes, 
			period="1d", 
			end_time=current_day,
			count=ContextInfo.look_back_days, 
			dividend_type='none'
		)
		
		g.DAILY_DATA = {}
		
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
			
			if pd.isna(dif_series.iloc[-1]) or len(dif_series) < 3:
				continue
				
			dif_t_minus_1 = dif_series.iloc[-2]
			dea_t_minus_1 = dea_series.iloc[-2]
			dif_t_minus_2 = dif_series.iloc[-3]
			dea_t_minus_2 = dea_series.iloc[-3]
			
			is_macd_golden_cross = (dif_t_minus_2 <= dea_t_minus_2) and (dif_t_minus_1 > dea_t_minus_1)
			
			# --- 波动率 ATR 计算 --- **【V1.18.2 新增】**
			atr_abs = calculate_atr(df_daily, ContextInfo.ATR_PERIOD)
			
			t_day_open_price = df_daily['open'].iloc[-1]
			
			# **【V1.18.2 核心逻辑】计算动态止损/过滤百分比阈值**
			dynamic_drop_pct = np.nan
			if not np.isnan(atr_abs) and t_day_open_price > 0:
				# 跌幅的绝对价格 = ATR_ABS * MULTIPLIER
				drop_abs = atr_abs * ContextInfo.ATR_MULTIPLIER
				# 将绝对价格转化为相对于当日开盘价的百分比跌幅 (负值)
				dynamic_drop_pct = - (drop_abs / t_day_open_price)
			
			g.DAILY_DATA[stock] = {
				't_day_open_price': t_day_open_price,            
				'dif_t_minus_1': dif_t_minus_1, 
				'dea_t_minus_1': dea_t_minus_1,
				'is_macd_golden_cross': is_macd_golden_cross,
				'dynamic_drop_pct': dynamic_drop_pct # **【V1.18.2 新增】动态百分比阈值**
			}
		
		print(f"[{current_time_log}] 阶段一：每日数据初始化完成。计算了 {len(g.DAILY_DATA)} 只股票指标。")
		
	# --------------------------------------------------------
	# 【阶段二：买入检查（09:35）】
	# --------------------------------------------------------
	if current_time_str == OP_TIME_STR:

		
		print(f"[{current_time_log}] 阶段二：买入检查开始。")
		
		stocks_to_check = list(g.DAILY_DATA.keys())
		if not stocks_to_check:
			print("因缺少指标数据，无法执行买入检查。")
			return

		# A. 获取当前 09:35 的价格 (close)
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
			daily_info = g.DAILY_DATA.get(stock)
			op_close_bar = op_data.get(stock)
			
			if daily_info is None or op_close_bar is None or op_close_bar.empty:
				continue

			op_price = op_close_bar['close'].iloc[-1]
			dif_t_minus_1 = daily_info['dif_t_minus_1']
			is_golden_cross = daily_info['is_macd_golden_cross']
			
			t_day_open_price = daily_info.get('t_day_open_price', 0)
			dynamic_drop_pct = daily_info.get('dynamic_drop_pct', np.nan) # **【V1.18.2 动态 ATR 阈值】**
			
			# 严格入场条件：
			if is_golden_cross:
				
				# **【V1.18.2 核心修改】买入过滤：使用动态 ATR 百分比阈值**
				if t_day_open_price > 0 and not np.isnan(dynamic_drop_pct):
					current_drop_from_open = (op_price / t_day_open_price) - 1
					
					if current_drop_from_open < dynamic_drop_pct:
						# 满足金叉，但日内跌幅超过动态限制 (例如：跌幅超过 2倍ATR)，不买入
						print(f"[{current_time_log}] 过滤买入 {stock}: 日内跌幅 ({current_drop_from_open*100:.2f}%) 超过动态ATR阈值 ({dynamic_drop_pct*100:.2f}%)。")
						continue 
					
				qualified_candidates.append({
					'code': stock, 
					'op_price': op_price,
					'macd_strength': dif_t_minus_1, 
				})
		
		# B. 相对强度排序
		qualified_candidates.sort(key=lambda x: x['macd_strength'], reverse=True)
		target_buys = qualified_candidates[:ContextInfo.hold_num]
		
		# C. 执行买入 (资金管理部分保持不变)
		curr_holdings_dict = get_current_positions(ContextInfo.account_id, ContextInfo)
		total_asset = get_account_asset(ContextInfo.account_id)
		account = get_trade_detail_data(ContextInfo.account_id, 'STOCK', 'ACCOUNT')
		# print(account)
		available_asset = account[0].m_dAvailable
		total_asset = account[0].m_dBalance
		print(f"目前可用资金: {available_asset:.2f} 元, 账户总资产: {total_asset:.2f} 元")
		# print(f"目前总资产: {total_asset:.2f} 元")
		# total_asset = 1000000
		
		current_hold_count = len(curr_holdings_dict)
		if current_hold_count >= ContextInfo.hold_num: 
			print(f"[{current_time_log}] 阶段二：已满仓，不进行买入。")
			return
		target_per_stock = available_asset / (ContextInfo.hold_num - current_hold_count)
		
		for item in target_buys:
			stock = item['code']
			buy_price = item['op_price']
			
			if current_hold_count < ContextInfo.hold_num and stock not in curr_holdings_dict:
				amount = int(target_per_stock / buy_price / 100) * 100
				
				if amount >= 100:
					execute_trade(True, stock, amount, buy_price, ContextInfo, ContextInfo.account_id)
					current_hold_count += 1
					g.HOLDING_BUY_DATE[stock] = current_day 
			
		if len(target_buys) > 0:
			print(f"[{current_time_log}] 买入操作完成。目标: {[item['code'] for item in target_buys]}")

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
			daily_info = g.DAILY_DATA.get(stock)
			latest_bar = latest_data.get(stock)
			
			if daily_info is None or latest_bar is None or latest_bar.empty:
				continue

			current_price = latest_bar['close'].iloc[-1]
			
			should_sell = False
			sell_reason = ""
			
			# 1. **【V1.18.2 核心修改】动态 ATR 日内止损检查** (基准价：当日开盘价)
			t_day_open_price = daily_info.get('t_day_open_price', 0)
			dynamic_drop_pct = daily_info.get('dynamic_drop_pct', np.nan)
			
			if t_day_open_price > 0 and not np.isnan(dynamic_drop_pct):
				# 跌幅相对于开盘价的百分比
				current_daily_drop_from_open = (current_price / t_day_open_price) - 1
				
				if current_daily_drop_from_open < dynamic_drop_pct:
					should_sell = True
					sell_reason = f"日内跌幅 ({current_daily_drop_from_open*100:.2f}%) 超过动态ATR止损 ({dynamic_drop_pct*100:.2f}%)"
					print(f"[{current_time_log}] 触发止损 {stock}：{sell_reason}")


			# 2. MACD 死叉检查 (14:55) - 保持不变
			if current_time_str == CHECK_MACD_SELL_TIME and not should_sell: 
				if daily_info['dif_t_minus_1'] < daily_info['dea_t_minus_1']:
					should_sell = True
					sell_reason = "MACD趋势已死叉 (T-1 日已死叉)"
					print(f"[{current_time_log}] 触发卖出 {stock}：{sell_reason}")
			
			
			if should_sell and volume > 0:
				execute_trade(False, stock, volume, current_price, ContextInfo, ContextInfo.account_id)