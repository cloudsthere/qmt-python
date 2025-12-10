# coding:gbk
import importlib.util
import os
import pandas as pd

class ContextInfo:
    def __init__(self):
        # 这些属性会在策略 init 中被设置或读取
        self.is_debug = False
        self.strategyName = None
        self.account_id = None
        self.hold_num = None
        self.MACD_SHORT = None
        self.MACD_LONG = None
        self.MACD_SIGNAL = None
        self.ATR_PERIOD = None
        self.ATR_MULTIPLIER = None
        self.look_back_days = None
        self.stock_pool = []

        # runtime/backtest helpers
        self.barpos = 0
        self.current_timetag = None

    def get_stock_list_in_sector(self, name):
        # 从 storage/sectors/{name}.txt 读取股票列表，只取第一列代码并自动加后缀
        sector_path = os.path.join(os.path.dirname(__file__), 'storage', 'sectors', f'{name}.txt')
        sector_path = os.path.normpath(sector_path)
        # print(f"加载板块文件: {sector_path}")
        codes = []
        try:
            with open(sector_path, encoding='gbk') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('代码'):
                        continue
                    code = line.split('\t')[0]
                    # 自动加后缀：深市0开头加.SZ，沪市6开头加.SH，其他原样
                    if code.startswith('0') or code.startswith('3'):  # 深市
                        code_full = f'{code}.SZ'
                    elif code.startswith('6'):  # 沪市
                        code_full = f'{code}.SH'
                    else:
                        code_full = code
                    codes.append(code_full)
            return codes
        except Exception as e:
            # print(f"读取板块文件失败: {sector_path}, 错误: {e}")
            return []

    # --- Minimal stubs to let handlebar run without platform ---
    def is_new_bar(self):
        return True

    def is_last_bar(self):
        return True

    def get_bar_timetag(self, barpos):
        # Return the currently-set timetag (string or datetime)
        return self.current_timetag

    def get_market_data_ex(self, **kwargs):
        # Return empty dicts to keep strategy logic safe; the strategy checks for None/empty.
        stock_code = kwargs.get('stock_code', [])
        if isinstance(stock_code, str):
            stock_code = [stock_code]
        res = {}
        for s in stock_code:
            # empty DataFrame
            res[s] = pd.DataFrame()
        return res

    def get_trade_detail_data(self, *args, **kwargs):
        # For ACCOUNT queries, return a list with an object providing m_dAvailable and m_dBalance
        class AccountObj:
            def __init__(self):
                self.m_dAvailable = 1000000.0
                self.m_dBalance = 1000000.0

        # For POSITION queries, return empty list (no holdings)
        qtype = args[2] if len(args) >= 3 else None
        if qtype == 'ACCOUNT':
            return [AccountObj()]
        return []

def download_history_data(stock, duration, start_date, end_date):
    # print(f"下载历史数据: 股票={stock}, 周期={duration}, 起始日期={start_date}, 结束日期={end_date}")
    pass


def timetag_to_datetime(timetag, fmt):
    import datetime as _dt
    # Accept datetime or strings like 'YYYYMMDDHHMMSS' or 'YYYY-MM-DD HH:MM:SS'
    if isinstance(timetag, _dt.datetime):
        return timetag.strftime(fmt)
    s = str(timetag)
    for fmt_try in ('%Y%m%d%H%M%S', '%Y-%m-%d %H:%M:%S', '%Y%m%d'):
        try:
            dt = _dt.datetime.strptime(s, fmt_try)
            return dt.strftime(fmt)
        except Exception:
            continue
    # fallback: if s already matches desired slice, try simple formatting
    try:
        return _dt.datetime.fromtimestamp(float(s)).strftime(fmt)
    except Exception:
        return s


def passorder(*args, **kwargs):
    # Minimal passorder stub used by execute_trade to avoid NameError
    print("passorder called with:", args[:5])

def main():
    # 计算策略文件的绝对路径（相对于本文件）
    base_dir = os.path.dirname(__file__)
    strategy_path = os.path.normpath(os.path.join(base_dir, '..', '股票趋势跟踪分钟级策略.py'))
    print(f"加载策略文件: {strategy_path}")

    # 动态从文件加载策略模块
    spec = importlib.util.spec_from_file_location("strategy_module", strategy_path)
    strategy = importlib.util.module_from_spec(spec)
    # 在模块执行前注入需要的全局函数，避免策略文件在导入或 init 中调用未定义的全局名时报错
    # 目前策略中在调试分支会调用 download_history_data
    # 注入常用全局函数，避免策略模块中对平台全局名的直接引用导致 NameError
    strategy.download_history_data = download_history_data
    strategy.timetag_to_datetime = timetag_to_datetime
    strategy.get_trade_detail_data = lambda *a, **k: ctx.get_trade_detail_data(*a, **k)
    strategy.passorder = passorder
    spec.loader.exec_module(strategy)

    # 提供一个最小的 ContextInfo 以便调用策略的 init(ContextInfo)

    ctx = ContextInfo()

    try:
        strategy.init(ctx)
        print("init 执行完成。")
        # print("ContextInfo.stock_pool:", getattr(ctx, 'stock_pool', None))
        # print("ContextInfo.strategyName:", getattr(ctx, 'strategyName', None))
    except Exception as e:
        print("运行 init 时发生异常:", e)

    # --- 简单回测驱动：按 period 列表每个 period 调用一次 handlebar ---
    print("开始模拟 backtest，按周期调用 handlebar...")
    # 生成A股常规交易时段的每一分钟时间点（09:31-11:30, 13:01-14:59）
    import datetime as _dt
    date_base = _dt.datetime.strptime(backtest_start_time, '%Y-%m-%d')
    times_to_run = []
    # 上午 09:31-11:30
    t = date_base.replace(hour=9, minute=31, second=0)
    end_am = date_base.replace(hour=11, minute=30, second=0)
    while t <= end_am:
        times_to_run.append(t.strftime('%H:%M'))
        t += _dt.timedelta(minutes=1)
    # 下午 13:01-14:59
    t = date_base.replace(hour=13, minute=1, second=0)
    end_pm = date_base.replace(hour=14, minute=59, second=0)
    while t <= end_pm:
        times_to_run.append(t.strftime('%H:%M'))
        t += _dt.timedelta(minutes=1)

    for idx, t in enumerate(times_to_run):
        hh, mm = t.split(':')
        dt_tag = date_base.replace(hour=int(hh), minute=int(mm), second=0)
        # set ctx timetag in format YYYYMMDDHHMMSS
        ctx.current_timetag = dt_tag.strftime('%Y%m%d%H%M%S')
        ctx.barpos = idx
        try:
            # print(f"调用 handlebar for timetag {ctx.current_timetag} (barpos={ctx.barpos})")
            strategy.handlebar(ctx)
        except Exception as e:
            print(f"handlebar 调用时发生异常 (timetag={ctx.current_timetag}):", e)
    print(f"模拟 backtest 完成，共调用 {len(times_to_run)} 次 handlebar。")


if __name__ == "__main__":
    backtest_start_time = "2025-05-12"
    backtest_end_day = "2025-12-08"
    backtest_period = "1m"
    main()