"""
비트코인 시황 리포트 - 텔레그램 전송
CoinGecko API 사용 (GitHub Actions 호환)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import requests
import os
import time
warnings.filterwarnings('ignore')


class BTCReport:
    
    def __init__(self):
        self.data = {}
        self.report = []
        
        self.TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.CHAT_ID = os.getenv('CHAT_ID')
    
    
    def log(self, text=''):
        """로그 추가"""
        self.report.append(text)
        print(text)
    
    
    def fetch_coingecko_data(self, days, max_retries=3):
        """CoinGecko API로 데이터 수집"""
        print(f"수집 중: {days}일 데이터...", end=" ")
        
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        params = {
            'vs_currency': 'usd',
            'days': days,
            'interval': 'hourly' if days <= 90 else 'daily'
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # 데이터 변환
                    prices = data['prices']
                    volumes = data['total_volumes']
                    
                    df = pd.DataFrame(prices, columns=['timestamp', 'close'])
                    df['volume'] = [v[1] for v in volumes]
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    
                    # OHLC 근사치 (1시간/1일 단위)
                    df['open'] = df['close'].shift(1)
                    df['high'] = df[['open', 'close']].max(axis=1)
                    df['low'] = df[['open', 'close']].min(axis=1)
                    df = df.dropna()
                    
                    print(f"완료 ({len(df)}개)")
                    return df
                else:
                    print(f"오류 {response.status_code} (시도 {attempt + 1}/{max_retries})")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"오류: {e} (시도 {attempt + 1}/{max_retries})")
                time.sleep(2)
        
        print("실패")
        return pd.DataFrame()
    
    
    def calc_indicators(self, df):
        """지표 계산"""
        if df.empty or len(df) < 100:
            return df
            
        df['MA7'] = df['close'].rolling(7).mean()
        df['MA20'] = df['close'].rolling(20).mean()
        df['MA50'] = df['close'].rolling(50).mean()
        df['MA99'] = df['close'].rolling(99).mean()
        
        df['EMA12'] = df['close'].ewm(span=12).mean()
        df['EMA26'] = df['close'].ewm(span=26).mean()
        
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        df['MACD'] = df['EMA12'] - df['EMA26']
        df['MACD_signal'] = df['MACD'].ewm(span=9).mean()
        
        df['BB_mid'] = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df['BB_upper'] = df['BB_mid'] + (std * 2)
        df['BB_lower'] = df['BB_mid'] - (std * 2)
        
        return df
    
    
    def resample_to_4h(self, df):
        """1시간 데이터를 4시간으로 리샘플링"""
        if df.empty:
            return df
        
        df_4h = df.resample('4H').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        return df_4h
    
    
    def resample_to_daily(self, df):
        """1시간 데이터를 1일로 리샘플링"""
        if df.empty:
            return df
        
        df_1d = df.resample('1D').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        return df_1d
    
    
    def analyze(self):
        """분석"""
        # 데이터 수집 (90일치 시간봉)
        df_hourly = self.fetch_coingecko_data(90)
        
        if df_hourly.empty:
            print("\n데이터 수집 실패")
            self.log("❌ 데이터 수집 실패")
            return False
        
        # 리샘플링
        self.data['1h'] = df_hourly
        self.data['4h'] = self.resample_to_4h(df_hourly)
        self.data['1d'] = self.resample_to_daily(df_hourly)
        
        # 지표 계산
        for tf in ['1h', '4h', '1d']:
            if not self.data[tf].empty:
                self.data[tf] = self.calc_indicators(self.data[tf])
        
        # 현재가
        if len(self.data['1h']) < 24:
            self.log("❌ 데이터 부족")
            return False
            
        current = self.data['1h']['close'].iloc[-1]
        prev_1h = self.data['1h']['close'].iloc[-2]
        prev_24h = self.data['1h']['close'].iloc[-24]
        
        change_1h = ((current / prev_1h - 1) * 100)
        change_24h = ((current / prev_24h - 1) * 100)
        
        self.log("=" * 70)
        self.log("📈 비트코인 시황 리포트")
        self.log("=" * 70)
        self.log(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        self.log(f"현재가: ${current:,.0f}")
        self.log(f"1시간: {change_1h:+.2f}% | 24시간: {change_24h:+.2f}%")
        self.log()
        
        # 각 타임프레임 분석
        scores = []
        for tf_name, tf_data in [('1시간', '1h'), ('4시간', '4h'), ('일봉', '1d')]:
            if self.data[tf_data].empty:
                continue
                
            df = self.data[tf_data].dropna()
            
            if len(df) < 50:
                continue
                
            latest = df.iloc[-1]
            
            close = latest['close']
            ma7 = latest['MA7']
            ma20 = latest['MA20']
            ma50 = latest['MA50']
            rsi = latest['RSI']
            macd = latest['MACD']
            macd_sig = latest['MACD_signal']
            
            # 추세 점수
            if close > ma7 > ma20 > ma50:
                trend = "강한 상승"
                score = 5
            elif close > ma7 > ma20:
                trend = "상승"
                score = 4
            elif close > ma50:
                trend = "약한 상승"
                score = 3
            elif close < ma7 < ma20 < ma50:
                trend = "강한 하락"
                score = 1
            elif close < ma7 < ma20:
                trend = "하락"
                score = 2
            else:
                trend = "횡보"
                score = 3
            
            scores.append(score)
            
            self.log(f"▶ [{tf_name}봉]")
            self.log(f"  추세: {trend}")
            self.log(f"  RSI: {rsi:.1f}")
            self.log(f"  MACD: {'골든크로스' if macd > macd_sig else '데드크로스'}")
            self.log()
        
        if not scores:
            self.log("❌ 분석 데이터 부족")
            return False
        
        # 종합 의견
        avg_score = sum(scores) / len(scores)
        
        self.log("=" * 70)
        self.log("💡 종합 의견")
        self.log("=" * 70)
        
        if avg_score >= 4:
            view = "강세 시장"
            comment = "상승 추세 우세. 조정 시 매수 기회."
        elif avg_score >= 3:
            view = "중립"
            comment = "방향성 불명확. 관망 권장."
        else:
            view = "약세 시장"
            comment = "하락 추세 우세. 반등 시 매도 고려."
        
        self.log(f"시장 상태: {view}")
        self.log(f"전략: {comment}")
        self.log()
        
        # RSI 종합
        rsi_values = []
        for tf in ['1h', '4h', '1d']:
            if not self.data[tf].empty and len(self.data[tf].dropna()) > 0:
                rsi_values.append(self.data[tf].dropna().iloc[-1]['RSI'])
        
        if rsi_values:
            avg_rsi = sum(rsi_values) / len(rsi_values)
            
            if avg_rsi > 70:
                self.log(f"⚠️  과매수 구간 (RSI {avg_rsi:.0f}) - 조정 위험")
            elif avg_rsi < 30:
                self.log(f"✨ 과매도 구간 (RSI {avg_rsi:.0f}) - 반등 기회")
            else:
                self.log(f"📊 RSI {avg_rsi:.0f} - 정상 구간")
        
        self.log()
        self.log("=" * 70)
        return True
    
    
    def send_telegram(self):
        """텔레그램 전송"""
        if not self.TOKEN or not self.CHAT_ID:
            print("텔레그램 설정 없음")
            return
        
        message = '\n'.join(self.report)
        
        url = f"https://api.telegram.org/bot{self.TOKEN}/sendMessage"
        data = {"chat_id": self.CHAT_ID, "text": message}
        
        try:
            r = requests.post(url, data=data, timeout=10)
            if r.status_code == 200:
                print("\n✅ 텔레그램 전송 완료")
            else:
                print(f"\n❌ 전송 실패: {r.status_code}")
        except Exception as e:
            print(f"\n❌ 오류: {e}")
    
    
    def run(self):
        """실행"""
        print("\n비트코인 리포트 생성 시작\n")
        success = self.analyze()
        
        if success:
            self.send_telegram()
            print("\n완료")
        else:
            print("\n실패 - 분석 불가")
            if self.report:
                self.send_telegram()


if __name__ == "__main__":
    report = BTCReport()
    report.run()