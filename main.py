import pandas as pd
import numpy as np
# 增强版：包含实时数据获取功能
import akshare as ak  # 需要安装: pip install akshare
from typing import Dict, List, Tuple, Optional, Union
import yaml
import requests

from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# === 配置管理 ===
def load_config():
    """加载配置文件"""
    config_path = "config/config.yaml"

    if not Path(config_path).exists():
        raise FileNotFoundError(f"配置文件 {config_path} 不存在")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    print(f"配置文件加载成功: {config_path}, {config_data}")

def send_to_wework(
    webhook_url: str,
    report_data: Dict,
    report_type: str,
    update_info: Optional[Dict] = None,
    proxy_url: Optional[str] = None,
    mode: str = "daily",
) -> bool:
    """发送到企业微信（支持分批发送）"""
    headers = {"Content-Type": "application/json"}
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}

    # 获取分批内容
    batches = split_content_into_batches(report_data, "wework", update_info, mode=mode)

    print(f"企业微信消息分为 {len(batches)} 批次发送 [{report_type}]")

    # 逐批发送
    for i, batch_content in enumerate(batches, 1):
        batch_size = len(batch_content.encode("utf-8"))
        print(
            f"发送企业微信第 {i}/{len(batches)} 批次，大小：{batch_size} 字节 [{report_type}]"
        )

        # 添加批次标识
        if len(batches) > 1:
            batch_header = f"**[第 {i}/{len(batches)} 批次]**\n\n"
            batch_content = batch_header + batch_content

        payload = {"msgtype": "markdown", "markdown": {"content": batch_content}}

        try:
            response = requests.post(
                webhook_url, headers=headers, json=payload, proxies=proxies, timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("errcode") == 0:
                    print(f"企业微信第 {i}/{len(batches)} 批次发送成功 [{report_type}]")
                    # 批次间间隔
                    if i < len(batches):
                        time.sleep(CONFIG["BATCH_SEND_INTERVAL"])
                else:
                    print(
                        f"企业微信第 {i}/{len(batches)} 批次发送失败 [{report_type}]，错误：{result.get('errmsg')}"
                    )
                    return False
            else:
                print(
                    f"企业微信第 {i}/{len(batches)} 批次发送失败 [{report_type}]，状态码：{response.status_code}"
                )
                return False
        except Exception as e:
            print(f"企业微信第 {i}/{len(batches)} 批次发送出错 [{report_type}]：{e}")
            return False

    print(f"企业微信所有 {len(batches)} 批次发送完成 [{report_type}]")
    return True

class LimitUpStrengthModel:
    """
    连板强度模型
    基于开盘上涨点数1-3-5-7-9区间的强度分析
    """
    
    def __init__(self):
        self.strength_levels = {
            'L1': (1, 2, 0.1, 0.2, '弱势高开'),
            'L3': (3, 4, 0.3, 0.4, '强势高开'), 
            'L5': (5, 6, 0.5, 0.6, '强力高开'),
            'L7': (7, 8, 0.7, 0.8, '极强高开'),
            'L9': (9, 100, 0.9, 10.0, '顶级强度')
        }
        
        # 预估概率（基于历史经验，可调整）
        self.success_probability = {
            'L1': 0.15, 'L3': 0.38, 'L5': 0.60, 'L7': 0.78, 'L9': 0.90
        }
    
    def calculate_open_gain(self, pre_close, open_price):
        """
        计算开盘涨幅（点数）
        """
        if pre_close == 0:
            return 0
        gain_points = (open_price - pre_close) / pre_close * 100
        return round(gain_points, 2)
    
    def get_strength_level(self, gain_points):
        """
        根据开盘涨幅确定强度等级
        """
        for level, (min_pt, max_pt, min_pct, max_pct, desc) in self.strength_levels.items():
            if min_pt <= gain_points <= max_pt:
                return level, desc
        return 'L0', '平开或低开'
    
    def get_trading_strategy(self, level, stock_data):
        """
        根据强度等级生成交易策略
        """
        strategies = {
            'L1': {
                'action': '观望或放弃',
                'reason': '弱势高开，成功率低',
                'suggestion': '等待更强信号或放弃该标的'
            },
            'L3': {
                'action': '谨慎关注', 
                'reason': '强势高开，需确认信号',
                'suggestion': '观察15-30分钟资金承接，分时突破时考虑介入'
            },
            'L5': {
                'action': '重点出击',
                'reason': '强力高开，性价比高',
                'suggestion': '分时回踩均线不破时介入，设置止损'
            },
            'L7': {
                'action': '激进抢筹',
                'reason': '极强高开，机会短暂', 
                'suggestion': '集合竞价或开盘瞬间介入，注意风险控制'
            },
            'L9': {
                'action': '通道党或观望',
                'reason': '顶级强度，难有买点',
                'suggestion': '作为情绪风向标，普通投资者观望'
            }
        }
        
        strategy = strategies.get(level, {'action': '观望', 'reason': '未知等级', 'suggestion': '谨慎操作'})
        strategy['success_rate'] = f"{self.success_probability.get(level, 0)*100:.1f}%"
        
        return strategy
    
    def analyze_stock(self, stock_code, stock_name, pre_close, open_price, limit_up_count=1):
        """
        分析单只股票的连板强度
        """
        # 计算开盘涨幅
        gain_points = self.calculate_open_gain(pre_close, open_price)
        
        # 获取强度等级
        level, level_desc = self.get_strength_level(gain_points)
        
        # 获取交易策略
        strategy = self.get_trading_strategy(level, {})
        
        result = {
            '股票代码': stock_code,
            '股票名称': stock_name,
            '前收价': pre_close,
            '开盘价': open_price,
            '开盘涨幅点数': gain_points,
            '强度等级': level,
            '等级描述': level_desc,
            '连板数': limit_up_count,
            '建议操作': strategy['action'],
            '操作理由': strategy['reason'],
            '具体建议': strategy['suggestion'],
            '预估成功率': strategy['success_rate']
        }
        
        return result
    
    def analyze_strength_sequence(self, stock_data):
        """
        分析强度序列
        stock_data: DataFrame包含历史开盘强度数据
        """
        if len(stock_data) < 2:
            return "数据不足，无法分析序列"
        
        sequences = stock_data['强度等级'].tolist()
        sequence_str = ' -> '.join(sequences)
        
        # 分析序列趋势
        level_values = {'L1': 1, 'L3': 2, 'L5': 3, 'L7': 4, 'L9': 5}
        numeric_seq = [level_values.get(level, 0) for level in sequences]
        
        if len(numeric_seq) >= 2:
            trend = numeric_seq[-1] - numeric_seq[-2]
            if trend > 0:
                trend_desc = "强度递增 ↗ - 动能增强，龙头特征"
            elif trend < 0:
                trend_desc = "强度递减 ↘ - 动能衰竭，注意风险"
            else:
                trend_desc = "强度平稳 → - 换手推进，健康走势"
        else:
            trend_desc = "无法判断趋势"
        
        return {
            '强度序列': sequence_str,
            '序列趋势': trend_desc,
            '当前强度': sequences[-1] if sequences else '无',
            '昨日强度': sequences[-2] if len(sequences) >= 2 else '无'
        }

# 增强版：包含实时数据获取功能
import akshare as ak  # 需要安装: pip install akshare

class EnhancedLimitUpModel(LimitUpStrengthModel):
    """增强版连板强度模型 - 包含实时数据获取"""
    
    def get_realtime_limit_up_stocks(self):
        """
        获取昨日涨停股票今日的开盘数据
        注意：这里需要根据实际情况调整数据源
        """
        try:
            # 使用akshare获取涨停板数据（示例）
            limit_up_df = ak.stock_zt_pool_em(date=datetime.now().strftime('%Y%m%d'))
            return limit_up_df
        except:
            print("无法获取实时数据，使用示例数据")
            return generate_sample_data()
    
    def batch_analyze(self, stocks_data):
        """
        批量分析股票
        """
        results = []
        for _, stock in stocks_data.iterrows():
            try:
                analysis = self.analyze_stock(
                    stock.get('code', ''),
                    stock.get('name', ''),
                    stock.get('pre_close', 0),
                    stock.get('open_price', 0),
                    stock.get('limit_up_count', 1)
                )
                results.append(analysis)
            except Exception as e:
                print(f"分析股票 {stock.get('name', '')} 时出错: {e}")
        
        return pd.DataFrame(results)

# 使用示例
def enhanced_demo():
    model = EnhancedLimitUpModel()
    
    # 获取数据（这里用示例数据代替）
    stocks_data = generate_sample_data()
    
    # 批量分析
    results = model.batch_analyze(stocks_data)
    
    # 按强度排序
    sorted_results = results.sort_values('开盘涨幅点数', ascending=False)
    
    print("🔥 重点关注股票 (L5及以上):")
    strong_stocks = sorted_results[sorted_results['强度等级'].isin(['L5', 'L7', 'L9'])]
    for _, stock in strong_stocks.iterrows():
        print(f"{stock['股票名称']}: {stock['强度等级']} ({stock['开盘涨幅点数']}点) - {stock['建议操作']}")


def generate_sample_data():
    """
    生成示例数据
    """
    sample_stocks = [
        {'code': '000001', 'name': '平安银行', 'pre_close': 10.0, 'open_price': 10.5, 'limit_up_count': 2},
        {'code': '000002', 'name': '万科A', 'pre_close': 8.0, 'open_price': 8.3, 'limit_up_count': 1},
        {'code': '000003', 'name': '宁德时代', 'pre_close': 20.0, 'open_price': 21.2, 'limit_up_count': 3},
        {'code': '000004', 'name': '贵州茅台', 'pre_close': 15.0, 'open_price': 15.9, 'limit_up_count': 2},
        {'code': '000005', 'name': '中兴通讯', 'pre_close': 12.0, 'open_price': 12.1, 'limit_up_count': 1},
        {'code': '000006', 'name': '比亚迪', 'pre_close': 25.0, 'open_price': 26.8, 'limit_up_count': 4},
        {'code': '000007', 'name': '立讯精密', 'pre_close': 18.0, 'open_price': 19.5, 'limit_up_count': 2},
        {'code': '000008', 'name': '药明康德', 'pre_close': 9.0, 'open_price': 9.9, 'limit_up_count': 3},
    ]
    return pd.DataFrame(sample_stocks)

def main():
    """
    主函数 - 演示模型使用
    """
    print("=" * 60)
    print("           连板强度分析模型 v1.0")
    print("        基于开盘上涨点数1-3-5-7-9区间")
    print("=" * 60)
    
    # 初始化模型
    model = LimitUpStrengthModel()
    
    # 生成示例数据
    sample_data = generate_sample_data()
    
    print("\n📊 今日连板股强度分析:")
    print("-" * 80)
    
    results = []
    for _, stock in sample_data.iterrows():
        analysis = model.analyze_stock(
            stock['code'], 
            stock['name'],
            stock['pre_close'],
            stock['open_price'],
            stock['limit_up_count']
        )
        results.append(analysis)
    
    # 显示分析结果
    results_df = pd.DataFrame(results)
    display_columns = ['股票名称', '开盘涨幅点数', '强度等级', '等级描述', '连板数', '建议操作', '预估成功率']
    print(results_df[display_columns].to_string(index=False))
    
    print("\n🎯 强度等级说明:")
    print("-" * 40)
    for level, (min_pt, max_pt, min_pct, max_pct, desc) in model.strength_levels.items():
        prob = model.success_probability.get(level, 0) * 100
        print(f"{level}: {min_pt}-{max_pt}点 ({desc}) - 成功率: {prob:.1f}%")
    
    print("\n💡 操作建议汇总:")
    print("-" * 40)
    
    # 按强度等级分组统计
    strength_groups = results_df.groupby('强度等级')
    for level, group in strength_groups:
        if level not in ['L0']:
            stocks = group['股票名称'].tolist()
            print(f"\n{level}级别 ({len(stocks)}只): {', '.join(stocks)}")
            strategy = model.get_trading_strategy(level, {})
            print(f"  建议: {strategy['action']} - {strategy['suggestion']}")
    
    # 演示强度序列分析
    print("\n📈 强度序列分析演示:")
    print("-" * 40)
    
    # 模拟某只股票的历史强度序列
    mock_history_data = pd.DataFrame({
        '日期': ['D-3', 'D-2', 'D-1', 'D0'],
        '强度等级': ['L3', 'L5', 'L7', 'L9']
    })
    
    sequence_analysis = model.analyze_strength_sequence(mock_history_data)
    print(f"模拟序列: {sequence_analysis['强度序列']}")
    print(f"趋势判断: {sequence_analysis['序列趋势']}")
    print(f"当前强度: {sequence_analysis['当前强度']}")
    
    print("\n" + "=" * 60)
    print("分析完成！建议结合市场情绪和个股地位综合判断。")
    print("=" * 60)

if __name__ == "__main__":
    main()
    # 运行增强版演示
    enhanced_demo()
    wework_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=8f4856d7-f3fa-470f-8b3b-b821efa2e8d8"
    report_data = {
        "stats": [],
        "new_titles": "这是标题",
        "failed_ids": [],
        "total_new_count": 1,
    }
    results["wework"] = send_to_wework(
            wework_url, report_data, report_type
        )
